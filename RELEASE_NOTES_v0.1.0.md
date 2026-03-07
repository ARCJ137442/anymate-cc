# AnyMate-CC v0.1.0

**First stable and secure release** - Cross-platform MCP server for Claude Code Agent Teams

## 🔒 Security First Release

v0.1.0 is the result of **4 rounds of rigorous security review** fixing 11 vulnerabilities across CRITICAL, HIGH, MEDIUM, and LOW severities. All users should upgrade immediately.

### Security Fixes (11 Issues Across 4 Rounds)

#### Round 1 - Initial Security Hardening (47568ec)
1. **HIGH/BLOCKER**: Path Traversal Vulnerability
   - **Risk**: Arbitrary JSON file writes outside intended directories
   - **Fix**: Strict validation (alphanumeric, underscore, hyphen only) + resolve() boundary checks

2. **HIGH**: Unvalidated Senders + Dangerous Defaults
   - **Risk**: Unvalidated message senders + codex backend with full privileges by default
   - **Fix**: Team member validation in message bridge + safer codex defaults (requires approval)

3. **MEDIUM**: Information Disclosure in Tmux Logs
   - **Risk**: Sensitive data (prompts, code, secrets) logged to world-readable /tmp
   - **Fix**: Private directory (~/.anymate/logs) with 0o700/0o600 permissions

#### Round 2 - Validation & Caching (4d5e7b3)
4. **HIGH**: Name Validation Timing
   - **Risk**: Validation after state changes left dirty config on failure
   - **Fix**: Validate at START of spawn_teammate before any operations

5. **MEDIUM**: Member Cache Never Invalidates
   - **Risk**: Removed team members still validated as legitimate
   - **Fix**: Config file mtime tracking with automatic cache invalidation

6. **MEDIUM**: Sender Authenticity (Documented)
   - **Limitation**: Can't verify message authenticity, only name existence
   - **Action**: Comprehensive documentation + mitigations

7. **LOW**: Log Fallback Degradation
   - **Risk**: Double failure caused fallback to insecure temp directory
   - **Fix**: Private subdirectory with restrictive permissions

#### Round 3 - CRITICAL Blocker (ad9c2de)
8. **CRITICAL**: Arbitrary File Deletion (CVE-worthy)
   - **Risk**: stop_teammate(name='../../../../secret') could delete ANY file
   - **Fix**: Defense-in-depth - validation at entry points, utility functions, and path checks
   - **Impact**: BEFORE: MCP client could delete arbitrary files | AFTER: All blocked

#### Round 4 - Final Hardening (38099a2)
9. **HIGH**: team-lead Validation Bypass
   - **Risk**: team-lead exempt from sender validation - trivial impersonation
   - **Fix**: Removed special treatment - team-lead must be in valid_members

10. **LOW**: Log Security Final Fallback
    - **Risk**: After two failures, fell back to world-readable system temp
    - **Fix**: Fail-fast with RuntimeError instead of unsafe fallback

11. **Documentation**: Shell Backend Security Warning
    - **Action**: Comprehensive security docs for shell backend eval usage

### 🛡️ Defense-in-Depth Architecture

Three layers of protection:
1. **Entry Point Validation**: All MCP tools (spawn/stop/check) validate parameters
2. **Function-Level Validation**: Utility functions validate their own inputs
3. **Path Boundary Checks**: resolve().relative_to() prevents directory escape

**Result**: 19 tests passing + 1 xfail documenting architectural limitation

## ✨ Features

### Cross-Platform Support
- **Platforms**: Windows (Cygwin/MSYS2), Linux, macOS, Termux
- **Auto-detection**: Python/Codex binaries across platforms
- **Path handling**: Cross-platform path escaping and quoting
- **Encoding**: UTF-8 enforcement across all backends

### Built-in Backends
- **stdio**: Run any command-line program as a teammate
- **python-repl**: Persistent Python REPL with state preservation
- **shell**: Bash shell execution (use with trusted teams only)
- **codex**: AI-powered coding assistant with configurable sandbox

### MCP Tools
- `spawn_teammate`: Launch external programs as teammates
- `stop_teammate`: Stop and remove teammates (now with validation!)
- `check_teammate`: Check teammate status
- `list_teammates`: List all active teammates

### Features
- **Message routing**: File-based inbox with automatic polling
- **Chunked output**: Configurable splitting for long responses
- **tmux integration**: Visual feedback panes (when available)
- **Blank line preservation**: Output formatting maintained
- **Rollback on failure**: Failed spawns clean up automatically

## ⚠️ Breaking Changes

### Codex Backend Defaults (Security)
**Previous behavior**:
```python
spawn_teammate(backend_type="codex", ...)
# Used: sandbox="danger-full-access", full_auto=True
```

**New behavior** (requires user approval):
```python
spawn_teammate(backend_type="codex", ...)
# Uses: sandbox=None, full_auto=False
```

**Migration** - Restore previous behavior by explicit parameters:
```python
spawn_teammate(
    backend_type="codex",
    sandbox="danger-full-access",  # Explicitly opt-in
    full_auto=True,                 # Explicitly opt-in
    ...
)
```

**Rationale**: Security-first defaults prevent accidental high-privilege execution

## 📦 Installation

```bash
pip install anymate-cc
```

From source:
```bash
git clone https://github.com/ARCJ137442/anymate-cc.git
cd anymate-cc
pip install -e .
```

For development:
```bash
pip install -e ".[dev]"
```

## 🚀 Quick Start

### 1. Configure MCP Server

Create `.claude/mcp.json`:
```json
{
  "mcpServers": {
    "anymate": {
      "command": "python",
      "args": ["mcp-launcher.py"],
      "cwd": "${workspaceFolder}"
    }
  }
}
```

### 2. Create a Team (in Claude Code)
```python
TeamCreate(team_name="my-team")
```

### 3. Spawn a Teammate (via MCP)
```python
spawn_teammate(
    team_name="my-team",
    name="py-repl",
    backend_type="python-repl"
)
```

### 4. Send Messages
Teammates communicate via Claude Code's inbox protocol automatically!

See [README.md](README.md) for detailed examples and configuration.

## 🔐 Security Model

### Architectural Trust Model
AnyMate-CC uses **file-based IPC** which requires trust in processes with inbox write access:
- Any process that can write inbox JSON can send messages to teammates
- shell/python-repl backends execute received commands
- This is by design - teammates are for automation and tool use

### Recommended Deployment Practices

**For Production**:
1. **File Permissions**: Set 0o700 on `~/.claude/teams/` directory
2. **Isolation**: Deploy in containers or VMs
3. **Backend Choice**: Use codex with sandbox for untrusted code
4. **Logging**: Set `ANYMATE_DISABLE_LOGGING=1` for sensitive environments

**For Development**:
- Trusted local environment OK
- Use shell/python-repl with awareness of trust model
- Monitor teammate messages for unexpected behavior

### Known Limitations (v0.2 Improvements)

**Sender Authentication** (tracked in xfail test):
- Messages validated by sender NAME in config, not cryptographic authenticity
- Local process can impersonate valid team member by forging `from` field
- **Mitigation**: Restrictive file permissions + trusted environment
- **Planned**: HMAC signatures or secure IPC in v0.2

See [CHANGELOG.md](CHANGELOG.md) for complete security documentation.

## 📊 What's Included

- **Source code**: Full Python implementation with pluggable backends
- **Tests**: 19 tests (11 core + 8 security) + 1 xfail
- **Documentation**: README, CHANGELOG, security docs (EN + ZH)
- **MCP launcher**: Cross-platform server initialization
- **Examples**: Configuration templates and usage patterns

## 🎯 Use Cases

- **Multi-agent automation**: Combine Claude with specialized tools
- **Persistent tool sessions**: Keep Python REPL or shell state across messages
- **Code execution**: Safe codex backend for AI-powered coding
- **Custom teammates**: Build your own backends with stdio interface

## 🙏 Acknowledgments

- **Security Review**: Multiple rounds of thorough security analysis
- **Testing**: Cross-platform validation on Windows, Linux, macOS, Termux
- **Community**: Feedback and testing from early users

## 📚 Documentation

- [README.md](README.md) - Full documentation and examples
- [CHANGELOG.md](CHANGELOG.md) - Detailed change history
- [README.zh.md](README.zh.md) - Chinese documentation
- [MCP Configuration Guide](.claude/MCP_CONFIG.md) - Setup instructions

## 🐛 Known Issues

See "Known Limitations" section above and [CHANGELOG.md](CHANGELOG.md) for architectural limitations and planned improvements.

## 📄 License

See [LICENSE](LICENSE) file.

## 🔗 Links

- **Repository**: https://github.com/ARCJ137442/anymate-cc
- **Issues**: https://github.com/ARCJ137442/anymate-cc/issues
- **Discussions**: https://github.com/ARCJ137442/anymate-cc/discussions

---

**Upgrade Priority**: **HIGH** - Contains critical security fixes including arbitrary file deletion vulnerability. All users should upgrade immediately.

**Stability**: Stable - Production-ready with comprehensive testing and security hardening.

**Support**: Python 3.11+ on Windows, Linux, macOS, Termux
