# AnyMate-CC

Inject external programs as teammates into Claude Code Agent Teams.

AnyMate-CC is an [MCP](https://modelcontextprotocol.io/) server that lets you spawn persistent subprocess backends (Python REPL, shell, etc.) and expose them as first-class teammates in Claude Code's multi-agent system. Messages flow through Claude Code's file-based inbox protocol — no custom transport needed.

## How It Works

```
Claude Code (team lead)
    │
    ├── SendMessage → writes JSON to teammate inbox
    │
    ▼
AnyMate-CC (MCP server)
    │
    ├── MessageBridge polls inbox files for unread messages
    ├── Relays message text to subprocess via stdin
    ├── Subprocess executes, prints output, prints sentinel
    ├── Bridge collects output up to sentinel
    └── Writes reply back to sender's inbox JSON
```

AnyMate-CC hooks into Claude Code's existing team infrastructure:

1. **Team config injection** — `spawn_teammate` adds a member entry to `~/.claude/teams/{team}/config.json`, making Claude Code recognize the external process as a teammate.
2. **Inbox polling** — A `MessageBridge` polls each teammate's inbox file (`inboxes/{name}.json`) for unread messages and marks them read.
3. **Sentinel-delimited I/O** — Each backend wraps the subprocess in a read-eval loop. Input is prefixed with `__ANYMATE__:`, output is terminated by a unique sentinel string, allowing reliable capture of multi-line results.
4. **Reply delivery** — Captured output is written to the sender's inbox as a standard Claude Code message, followed by an idle notification.

## Backends

| Backend | Key | Description |
|---------|-----|-------------|
| **Python REPL** | `python-repl` | Persistent Python session. Supports `eval` (expressions) and `exec` (statements). State persists across messages. |
| **Shell** | `shell` | Persistent bash session. Runs arbitrary commands via `eval`. Useful for CLI tools, file operations, git, etc. |

Backends are pluggable — implement `Backend` and `BridgeSession` from `anymate.backends.base` to add your own.

## Installation

Requires Python 3.12+. The only runtime dependency is `filelock`.

```bash
# From source
pip install -e .

# Or just set PYTHONPATH
export PYTHONPATH=/path/to/anymate-cc/src
```

### MCP Configuration

Add to your `.mcp.json` (project-level) or `~/.claude/claude_code_config.json` (global):

```json
{
  "mcpServers": {
    "anymate": {
      "command": "python3",
      "args": ["-m", "anymate.server"],
      "env": {
        "PYTHONPATH": "/path/to/anymate-cc/src"
      }
    }
  }
}
```

## Usage

Once configured, AnyMate-CC exposes four MCP tools to Claude Code:

### `spawn_teammate`

Spawn an external process as a teammate in an existing team.

```
Parameters:
  team_name    (required)  Name of the Claude Code team
  name         (required)  Teammate name (e.g. "py-repl")
  backend_type (optional)  "python-repl" (default) or "shell"
  cwd          (optional)  Working directory for the subprocess
  prompt       (optional)  Initial context/description
```

The team must already exist (create it with Claude Code's `TeamCreate` tool first).

### `stop_teammate`

Stop a running teammate and remove it from the team config.

### `check_teammate`

Check the status of a managed teammate (process alive, backend status, etc.).

### `list_teammates`

List all AnyMate-managed teammates in a team.

### Example Session

```
You:    "Create a team called 'data-analysis'"
Claude: [uses TeamCreate]

You:    "Spawn a Python REPL teammate called 'py'"
Claude: [uses spawn_teammate with team_name="data-analysis", name="py"]

You:    "Ask py to compute the first 10 Fibonacci numbers"
Claude: [uses SendMessage to py]
        → py receives message, runs Python code, returns result
        → Claude sees the reply in its inbox
```

## Configuration

Environment variables (all optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANYMATE_CLAUDE_DIR` | `~/.claude` | Base directory for Claude Code teams/inboxes |
| `ANYMATE_POLL_INTERVAL` | `1.0` | Inbox polling interval in seconds |
| `ANYMATE_PYTHON` | `python3` | Python binary for the python-repl backend |

## Project Structure

```
src/anymate/
├── server.py              # MCP server (JSON-RPC 2.0 over stdio)
├── bridge.py              # Message relay between inboxes and subprocesses
├── config.py              # Environment-based configuration
├── models.py              # Data models (TeammateMember, InboxMessage, etc.)
├── backends/
│   ├── base.py            # Abstract Backend / BridgeSession interfaces
│   ├── python_repl.py     # Python REPL backend
│   └── shell.py           # Shell (bash) backend
└── protocol/
    ├── paths.py           # Path resolution for team dirs and inboxes
    ├── teams.py           # Team config read/write (inject/remove members)
    ├── messaging.py       # Inbox operations (read, append, reply)
    └── fileops.py         # Atomic file writes with file locking
```

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Design Decisions

- **Zero heavy dependencies** — No pydantic, no fastmcp, no aiohttp. The MCP server is a bare-bones JSON-RPC 2.0 implementation over stdio (~100 lines). Only runtime dependency is `filelock`.
- **File-based IPC** — Reuses Claude Code's native inbox JSON files instead of inventing a new transport. This means teammates "just work" with Claude Code's existing `SendMessage` / message delivery.
- **Sentinel protocol** — Each backend uses a unique random sentinel string to delimit output boundaries, enabling reliable capture of multi-line output without special escaping.
- **Pluggable backends** — Adding a new backend (e.g., Node.js REPL, R session) requires implementing two classes: `Backend` (factory) and `BridgeSession` (lifecycle + I/O).

## License

MIT
