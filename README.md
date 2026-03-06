# AnyMate-CC

**Cross-platform MCP server for injecting external programs as teammates into Claude Code Agent Teams.**

AnyMate-CC is an [MCP](https://modelcontextprotocol.io/) server that lets you spawn persistent subprocess backends (Python REPL, shell, Codex AI, custom programs) and expose them as first-class teammates in Claude Code's multi-agent system. Messages flow through Claude Code's file-based inbox protocol — no custom transport needed.

**Platform Support:** Windows (Cygwin/MSYS2), Linux, macOS, Termux

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
| **Stdio** | `stdio` | Generic persistent command backend. Flushes output on sentinel or silence timeout; suitable for custom CLIs and scripts. |
| **Python REPL** | `python-repl` | Persistent Python session. Supports `eval` (expressions) and `exec` (statements). State persists across messages. |
| **Shell** | `shell` | Persistent bash session. Runs arbitrary commands via `eval`. Useful for CLI tools, file operations, git, etc. |
| **Codex CLI** | `codex` | Calls `codex exec --json` and returns the final `agent_message` for each request. |

Backends are pluggable — implement `Backend` and `BridgeSession` from `anymate.backends.base` to add your own.

## Installation

**Requirements:** Python 3.11+ (cross-platform: Windows/Linux/macOS/Termux)

The only runtime dependency is `filelock`.

```bash
# From source
pip install -e .

# Or with dev dependencies (includes pytest)
pip install -e ".[dev]"
```

### MCP Configuration

**Recommended (Cross-Platform):** Use the included launcher script

Add to `.claude/mcp.json` (project-level) or `~/.config/claude/mcp.json` (global):

```json
{
  "mcpServers": {
    "anymate": {
      "command": "python",
      "args": ["mcp-launcher.py"],
      "cwd": "${workspaceFolder}",
      "env": {}
    }
  }
}
```

<details>
<summary>Alternative: Direct module invocation</summary>

```json
{
  "mcpServers": {
    "anymate": {
      "command": "python",
      "args": ["-m", "anymate.server"],
      "env": {
        "PYTHONPATH": "/path/to/anymate-cc/src"
      }
    }
  }
}
```

**Note:** On Linux/macOS, you may need to use `python3` instead of `python`.
</details>

See `.claude/MCP_CONFIG.md` for platform-specific configuration templates and troubleshooting.

## Usage

Once configured, AnyMate-CC exposes four MCP tools to Claude Code:

### `spawn_teammate`

Spawn an external process as a teammate in an existing team.

```
Parameters:
  team_name    (required)  Name of the Claude Code team
  name         (required)  Teammate name (e.g. "py-repl")
  backend_type (optional)  "stdio" (default), "python-repl", "shell", or "codex"
  command      (required for stdio) Command to run (string or argv list)
  cwd          (optional)  Working directory for the subprocess
  prompt       (optional)  Initial context/description
  silence_timeout (optional, stdio) Flush output after N seconds of silence
  prompt_pattern  (optional, stdio) Regex prompt terminator
  max_chunk_size  (optional) Split long outputs into chunks (0 disables)
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
| `ANYMATE_PYTHON` | current Python executable | Python binary for python-repl/codex wrapper launchers |
| `ANYMATE_CODEX` | auto-detected via `which codex` | Codex CLI binary path (for codex backend) |

## Project Structure

```
src/anymate/
├── server.py              # MCP server (JSON-RPC 2.0 over stdio)
├── bridge.py              # Message relay between inboxes and subprocesses
├── config.py              # Environment-based configuration
├── models.py              # Data models (TeammateMember, InboxMessage, etc.)
├── backends/
│   ├── base.py            # Abstract Backend / BridgeSession interfaces
│   ├── stdio.py           # Generic stdio backend/session
│   ├── python_repl.py     # Python REPL backend
│   ├── shell.py           # Shell (bash) backend
│   └── codex.py           # Codex CLI backend
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
- **Cross-platform** — Tested on Windows (Cygwin/MSYS2), Linux, macOS, and Termux. Path resolution, subprocess management, and file locking work consistently across platforms.

## Testing & Validation

All backends have been integration-tested on Windows (Cygwin/MSYS2):

- ✅ **Python REPL**: Persistent Python sessions with state preservation
- ✅ **Shell**: Bash command execution via Cygwin/MSYS2
- ✅ **Stdio**: Custom command wrapping and I/O handling
- ✅ **Codex**: AI-powered coding assistant (requires [Codex CLI](https://openai.com/blog/codex))
- ✅ **Parallel teammates**: Multiple backends running simultaneously with correct message routing

Run the test suite:
```bash
pytest  # 8 tests passing
```

## License

MIT
