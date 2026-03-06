"""Codex CLI backend for AnyMate-CC.

Wraps `codex exec --json` in a persistent Python loop that extracts only the
final agent message from each invocation, filtering out thinking/exec noise.
"""
import os
import shutil
import sys

from .base import Backend, BackendCapabilities
from .stdio import StdioSession, make_sentinel

# Python wrapper that loops: read prompt from stdin → call codex exec --json
# → parse JSONL → extract last agent_message → print result + sentinel.
_CODEX_WRAPPER = '''\
import json, subprocess, sys, os, io

# Force UTF-8 encoding for stdin/stdout to match parent process
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)

SENTINEL = "{sentinel}"
CODEX_BIN = {codex_binary}
EXTRA_ARGS = {extra_args}
CWD = os.getcwd()

while True:
    try:
        line = input()
    except EOFError:
        break
    if not line.startswith("__ANYMATE__:"):
        continue
    prompt = line[12:].replace("\\\\n", "\\n")

    cmd = [CODEX_BIN, "exec", "--json", "--skip-git-repo-check"] + EXTRA_ARGS + [prompt]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, encoding='utf-8', cwd=CWD,
        )
        # Parse JSONL, collect agent_message items
        messages = []
        for jline in proc.stdout.splitlines():
            try:
                event = json.loads(jline)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "item.completed":
                item = event.get("item", {{}})
                if item.get("type") == "agent_message":
                    messages.append(item.get("text", ""))

        output = messages[-1] if messages else proc.stderr.strip() or "(no output)"
    except Exception as e:
        output = f"(codex error: {{e}})"

    print(output, flush=True)
    print(SENTINEL, flush=True)
'''


def _resolve_python_binary(explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env_python = os.environ.get("ANYMATE_PYTHON")
    if env_python:
        return env_python
    if sys.executable:
        return sys.executable
    if shutil.which("python3"):
        return "python3"
    return "python"


def _resolve_codex_binary(explicit: str | None = None) -> str:
    """Resolve codex binary path cross-platform (Windows/Linux/macOS)."""
    if explicit:
        return explicit
    # Check environment variable
    env_codex = os.environ.get("ANYMATE_CODEX")
    if env_codex:
        return env_codex
    # Use shutil.which() which handles platform-specific extensions (.cmd, .bat on Windows)
    found = shutil.which("codex")
    if found:
        return found
    # Fallback to plain "codex"
    return "codex"


class CodexBackend(Backend):
    def __init__(self, codex_binary: str | None = None, python_binary: str | None = None):
        self._codex = _resolve_codex_binary(codex_binary)
        self._python = _resolve_python_binary(python_binary)

    @property
    def name(self) -> str:
        return "codex"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_streaming=False,
            supports_interrupt=True,
            is_conversational=False,
            supports_cwd=True,
        )

    def is_available(self) -> bool:
        return shutil.which(self._codex) is not None or os.path.isfile(self._codex)

    def create_session(self, name, team_name, prompt, cwd, *, on_output=None, **kwargs):
        sentinel = make_sentinel()

        # Build extra args for `codex exec`
        extra_args: list[str] = []
        model = kwargs.get("model")
        if model:
            extra_args.extend(["-m", model])
        sandbox = kwargs.get("sandbox", "danger-full-access")
        if sandbox:
            extra_args.extend(["-s", sandbox])
        # codex exec uses --full-auto or --dangerously-bypass-approvals-and-sandbox
        # instead of -a (which is interactive-only)
        if kwargs.get("full_auto", True):
            extra_args.append("--full-auto")

        wrapper_code = _CODEX_WRAPPER.format(
            sentinel=sentinel,
            codex_binary=repr(self._codex),
            extra_args=repr(extra_args),
        )
        return StdioSession(
            name=name,
            team_name=team_name,
            command=[self._python, "-u", "-c", wrapper_code],
            cwd=cwd,
            sentinel=sentinel,
            input_prefix="__ANYMATE__:",
            on_output=on_output,
            pane_logger=kwargs.get("pane_logger"),
        )
