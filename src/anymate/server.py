"""AnyMate-CC MCP Server — inject external teammates into Claude Code Agent Teams.

Implements a minimal MCP (Model Context Protocol) server over JSON-RPC 2.0 stdio,
with zero compiled dependencies (no pydantic, no fastmcp).
"""
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from .config import AnyMateConfig
from .protocol.paths import PathResolver
from .protocol.messaging import ensure_inbox
from .protocol.teams import inject_member, remove_member, get_member, read_config
from .backends import discover_backends, get_backend
from .bridge import MessageBridge
from .models import COLOR_PALETTE

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal MCP stdio server (JSON-RPC 2.0, newline-delimited)
# ---------------------------------------------------------------------------

ToolHandler = Callable[..., Awaitable[dict]]


@dataclass
class _ToolDef:
    handler: ToolHandler
    description: str
    input_schema: dict


class McpStdioServer:
    """Bare-bones MCP server over stdin/stdout using JSON-RPC 2.0."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, name: str, version: str):
        self.name = name
        self.version = version
        self._tools: dict[str, _ToolDef] = {}
        self._on_startup: Callable | None = None
        self._on_shutdown: Callable | None = None

    # -- registration helpers ------------------------------------------------

    def tool(self, name: str, description: str, input_schema: dict):
        """Decorator to register a tool handler."""
        def decorator(fn: ToolHandler) -> ToolHandler:
            self._tools[name] = _ToolDef(fn, description, input_schema)
            return fn
        return decorator

    def on_startup(self, fn):
        self._on_startup = fn
        return fn

    def on_shutdown(self, fn):
        self._on_shutdown = fn
        return fn

    # -- JSON-RPC helpers ----------------------------------------------------

    @staticmethod
    def _result(msg_id: Any, result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    @staticmethod
    def _error(msg_id: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}

    # -- message handling ----------------------------------------------------

    async def _handle(self, msg: dict) -> dict | None:
        method = msg.get("method", "")
        msg_id = msg.get("id")  # None for notifications
        params = msg.get("params", {})

        if method == "initialize":
            return self._result(msg_id, {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": self.name, "version": self.version},
            })

        if method == "notifications/initialized":
            return None  # notification — no response

        if method == "tools/list":
            tools = [
                {
                    "name": t_name,
                    "description": t_def.description,
                    "inputSchema": t_def.input_schema,
                }
                for t_name, t_def in self._tools.items()
            ]
            return self._result(msg_id, {"tools": tools})

        if method == "tools/call":
            return await self._handle_tool_call(msg_id, params)

        if method == "ping":
            return self._result(msg_id, {})

        # Unknown method
        if msg_id is not None:
            return self._error(msg_id, -32601, f"Method not found: {method}")
        return None

    async def _handle_tool_call(self, msg_id: Any, params: dict) -> dict:
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        tool_def = self._tools.get(tool_name)

        if tool_def is None:
            return self._error(msg_id, -32602, f"Unknown tool: {tool_name}")

        try:
            result = await tool_def.handler(**arguments)
            text = json.dumps(result, ensure_ascii=False)
            return self._result(msg_id, {
                "content": [{"type": "text", "text": text}],
            })
        except Exception as exc:
            logger.exception("Tool %s raised an error", tool_name)
            return self._result(msg_id, {
                "content": [{"type": "text", "text": f"Error: {exc}"}],
                "isError": True,
            })

    # -- stdio transport -----------------------------------------------------

    @staticmethod
    def _write(msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False)
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    async def run(self) -> None:
        """Main event loop: read JSON-RPC from stdin, write responses to stdout."""
        if self._on_startup:
            await self._on_startup()

        try:
            while True:
                raw = await asyncio.to_thread(sys.stdin.buffer.readline)
                if not raw:
                    break  # EOF
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Ignoring invalid JSON: %s", line[:120])
                    continue

                response = await self._handle(msg)
                if response is not None:
                    self._write(response)
        finally:
            if self._on_shutdown:
                await self._on_shutdown()


# ---------------------------------------------------------------------------
# Application: tools & lifecycle
# ---------------------------------------------------------------------------

_config: AnyMateConfig | None = None
_paths: PathResolver | None = None
_bridges: dict[str, MessageBridge] = {}

mcp = McpStdioServer("anymate-cc", "0.1.0")


@mcp.on_startup
async def _startup():
    global _config, _paths
    _config = AnyMateConfig.from_env()
    _paths = PathResolver(base_dir=_config.claude_dir)
    backends = discover_backends()
    logger.info("AnyMate-CC started. Available backends: %s", list(backends.keys()))


@mcp.on_shutdown
async def _shutdown():
    for bridge in _bridges.values():
        await bridge.stop()
    _bridges.clear()


def _get_or_create_bridge(team_name: str) -> MessageBridge:
    if team_name not in _bridges:
        assert _paths is not None and _config is not None
        _bridges[team_name] = MessageBridge(_paths, team_name, _config.poll_interval)
    return _bridges[team_name]


# -- Tool definitions -------------------------------------------------------

@mcp.tool(
    name="spawn_teammate",
    description=(
        "Spawn an external program as a teammate in an existing Claude Code team. "
        "Injects the program into config.json and starts monitoring its inbox."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "Name of the existing Claude Code team to join"},
            "name": {"type": "string", "description": "Name for the new teammate (e.g. 'py-repl')"},
            "backend_type": {"type": "string", "default": "stdio", "description": "Backend type"},
            "command": {
                "description": "Command for stdio backend (required when backend_type='stdio')",
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
            },
            "cwd": {"type": "string", "default": ".", "description": "Working directory for subprocess"},
            "prompt": {"type": "string", "default": "", "description": "Initial prompt/context"},
            "silence_timeout": {"type": "number", "default": 5.0, "description": "Flush output after N seconds of silence"},
            "prompt_pattern": {"type": "string", "description": "Optional regex prompt terminator pattern"},
            "max_chunk_size": {"type": "integer", "default": 4096, "description": "Split output into chunks of N chars. 0 or null to disable chunking."},
        },
        "required": ["team_name", "name"],
    },
)
async def spawn_teammate(
    team_name: str,
    name: str,
    backend_type: str = "stdio",
    command: str | list[str] | None = None,
    cwd: str = ".",
    prompt: str = "",
    silence_timeout: float = 5.0,
    prompt_pattern: str | None = None,
    max_chunk_size: int | None = 4096,
) -> dict:
    assert _paths is not None and _config is not None

    config = read_config(_paths, team_name)
    if config is None:
        return {"error": f"Team '{team_name}' does not exist. Create it with Claude Code's TeamCreate first."}

    backend = get_backend(backend_type)
    if backend is None:
        return {"error": f"Backend '{backend_type}' not available. Available: {list(discover_backends().keys())}"}
    if max_chunk_size is not None and max_chunk_size < 0:
        return {"error": "Parameter 'max_chunk_size' must be >= 0"}
    if backend_type == "stdio" and command is None:
        return {"error": "Parameter 'command' is required when backend_type='stdio'"}
    if backend_type == "stdio":
        if isinstance(command, str) and not command.strip():
            return {"error": "Parameter 'command' cannot be empty when backend_type='stdio'"}
        if isinstance(command, list) and not command:
            return {"error": "Parameter 'command' cannot be empty when backend_type='stdio'"}
        if silence_timeout <= 0:
            return {"error": "Parameter 'silence_timeout' must be > 0"}

    existing_count = len(config.get("members", []))
    color = COLOR_PALETTE[existing_count % len(COLOR_PALETTE)]

    member = {
        "agentId": f"{name}@{team_name}",
        "name": name,
        "agentType": "general-purpose",
        "model": "",
        "prompt": prompt or f"External {backend_type} teammate managed by AnyMate-CC",
        "color": color,
        "planModeRequired": False,
        "joinedAt": int(time.time() * 1000),
        "tmuxPaneId": "",
        "cwd": cwd,
        "subscriptions": [],
        "backendType": "anymate",
        "anymateBackendType": backend_type,
        "opencodeSessionId": None,
        "isActive": True,
    }

    try:
        inject_member(_paths, team_name, member)
    except ValueError as e:
        return {"error": str(e)}

    inbox_path = ensure_inbox(_paths, team_name, name)
    bridge = _get_or_create_bridge(team_name)
    chunk_size = max_chunk_size if (max_chunk_size is not None and max_chunk_size > 0) else None
    session = None
    registered = False

    try:
        on_output = bridge._make_output_handler(name, color=color, max_chunk_size=chunk_size)
        session = backend.create_session(
            name=name,
            team_name=team_name,
            prompt=prompt,
            cwd=cwd,
            on_output=on_output,
            command=command,
            silence_timeout=silence_timeout,
            prompt_pattern=prompt_pattern,
        )
        await session.start()
        await bridge.register(name, session)
        registered = True
        if not bridge._running:
            await bridge.start()
    except Exception as exc:
        if registered:
            try:
                await bridge.unregister(name)
            except Exception:
                logger.warning("Failed to unregister teammate %s during rollback", name, exc_info=True)
        elif session is not None and session.is_alive:
            try:
                await session.stop()
            except Exception:
                logger.warning("Failed to stop teammate %s during rollback", name, exc_info=True)

        try:
            remove_member(_paths, team_name, name)
        except Exception:
            logger.warning("Failed to rollback member %s from team %s", name, team_name, exc_info=True)

        try:
            if inbox_path.exists():
                inbox_path.unlink()
        except OSError:
            logger.warning("Failed to rollback inbox for teammate %s", name, exc_info=True)

        return {"error": f"Failed to start teammate '{name}': {exc}"}

    return {
        "success": True,
        "name": name,
        "team_name": team_name,
        "backend": backend_type,
        "agent_id": member["agentId"],
        "color": color,
        "message": f"Teammate '{name}' ({backend_type}) spawned and monitoring inbox.",
    }


@mcp.tool(
    name="stop_teammate",
    description="Stop an external teammate and remove it from the team.",
    input_schema={
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "Name of the Claude Code team"},
            "name": {"type": "string", "description": "Name of the teammate to stop"},
        },
        "required": ["team_name", "name"],
    },
)
async def stop_teammate(team_name: str, name: str) -> dict:
    assert _paths is not None

    bridge = _bridges.get(team_name)
    if bridge:
        session = bridge.get_session(name)
        if session:
            await bridge.unregister(name)

    removed = remove_member(_paths, team_name, name)
    if removed:
        return {"success": True, "message": f"Teammate '{name}' stopped and removed from team.", "removed": removed}
    return {"success": False, "message": f"Teammate '{name}' not found in team '{team_name}'."}


@mcp.tool(
    name="check_teammate",
    description="Check the status of an external teammate.",
    input_schema={
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "Name of the Claude Code team"},
            "name": {"type": "string", "description": "Name of the teammate to check"},
        },
        "required": ["team_name", "name"],
    },
)
async def check_teammate(team_name: str, name: str) -> dict:
    assert _paths is not None

    member = get_member(_paths, team_name, name)
    if member is None:
        return {"error": f"Teammate '{name}' not found in team '{team_name}'."}

    bridge = _bridges.get(team_name)
    session = bridge.get_session(name) if bridge else None

    return {
        "name": name,
        "team_name": team_name,
        "registered": True,
        "process_alive": session.is_alive if session else False,
        "status": session.status.value if session else "not_managed",
        "backend_type": member.get("anymateBackendType") or "unknown",
        "color": member.get("color", ""),
    }


@mcp.tool(
    name="list_teammates",
    description="List all external (AnyMate-managed) teammates in a team.",
    input_schema={
        "type": "object",
        "properties": {
            "team_name": {"type": "string", "description": "Name of the Claude Code team"},
        },
        "required": ["team_name"],
    },
)
async def list_teammates(team_name: str) -> dict:
    assert _paths is not None

    config = read_config(_paths, team_name)
    if config is None:
        return {"error": f"Team '{team_name}' does not exist."}

    anymate_members = [
        {
            "name": m.get("name"),
            "agent_id": m.get("agentId"),
            "backend_type": m.get("anymateBackendType") or "unknown",
            "is_active": m.get("isActive", False),
            "color": m.get("color", ""),
        }
        for m in config.get("members", [])
        if m.get("backendType") == "anymate"
    ]

    return {"team_name": team_name, "count": len(anymate_members), "teammates": anymate_members}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,  # MCP stdout is for JSON-RPC only
    )
    asyncio.run(mcp.run())


if __name__ == "__main__":
    main()
