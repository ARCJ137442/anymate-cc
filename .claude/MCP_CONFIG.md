# MCP Configuration Templates

This directory contains platform-specific MCP configuration templates.

## Automatic Configuration (Recommended)

Use `mcp-launcher.py` in the project root - it works across all platforms:

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

**Note**: If `python` command is not available on your system, replace it with:
- `python3` (Linux/macOS/Termux)
- Full path like `/usr/bin/python3` or `C:/Python311/python.exe`

## Platform-Specific Templates

If the automatic launcher doesn't work, use these platform-specific configs:

### Windows (`.mcp.json` or `.claude/mcp.json`)
```json
{
  "mcpServers": {
    "anymate": {
      "command": "python",
      "args": ["-m", "anymate.server"],
      "env": {}
    }
  }
}
```

### Linux/macOS (`.mcp.json` or `.claude/mcp.json`)
```json
{
  "mcpServers": {
    "anymate": {
      "command": "python3",
      "args": ["-m", "anymate.server"],
      "env": {}
    }
  }
}
```

### Termux/Android (`.mcp.json` or `.claude/mcp.json`)
```json
{
  "mcpServers": {
    "anymate": {
      "command": "python",
      "args": ["-m", "anymate.server"],
      "env": {}
    }
  }
}
```

## Configuration File Location

Claude Code looks for MCP configuration in:
1. `.mcp.json` (project root) - **highest priority**
2. `.claude/mcp.json` (project-level)
3. `~/.config/claude/mcp.json` (global)

## Troubleshooting

### "ModuleNotFoundError: No module named 'anymate'"

Make sure the package is installed:
```bash
pip install -e .
# or with dev dependencies
pip install -e ".[dev]"
```

### "python3: command not found"

Change `"command": "python3"` to `"command": "python"` in your config.

### Connection Failed

Check MCP server logs in Claude Code's diagnostic panel:
1. Open Claude Code
2. Run `/mcp` command
3. Check server status and logs
