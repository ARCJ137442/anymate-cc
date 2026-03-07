# Changelog

All notable changes to AnyMate-CC will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned for v0.2
- Cryptographic sender authentication (HMAC or message signing)
- Or migration to secure IPC mechanism (sockets, named pipes)
- shutdown_request protocol handling
- Enhanced team validation
- CI Windows test matrix
- Native PowerShell/cmd.exe backend
- Cross-platform split-window beyond tmux

---

## [0.1.0] - 2026-03-07

### Added

#### Core Features
- Cross-platform MCP server for Claude Code Agent Teams
- Support for Windows (Cygwin/MSYS2), Linux, macOS, and Termux
- Four built-in backends: `stdio`, `python-repl`, `shell`, `codex`
- Pluggable backend architecture for custom teammates
- File-based inbox message routing with automatic polling
- Sentinel-delimited subprocess I/O capture
- Chunked output delivery for long responses (configurable `max_chunk_size`)
- tmux pane integration for visual feedback (when available)
- Cross-platform MCP launcher (`mcp-launcher.py`)

#### MCP Tools
- `spawn_teammate` - Launch external programs as teammates
- `stop_teammate` - Stop and remove teammates
- `check_teammate` - Check teammate status
- `list_teammates` - List all active teammates

#### Security Features
- Strict input validation with regex-based name checking
- Path traversal prevention with `resolve()` boundary checks
- Defense-in-depth architecture with multi-layer validation
- Secure logging with private directories (0o700 permissions on Unix)
- Team member authentication in message bridge
- Configurable logging disable option (`ANYMATE_DISABLE_LOGGING=1`)
- Comprehensive security test suite (8 security tests)

#### Documentation
- Comprehensive README with platform support matrix
- MCP configuration guide
- Platform-specific troubleshooting
- Security architecture documentation
- Threat model and mitigation strategies
- Chinese (Simplified) README translation

### Changed

#### Breaking Changes
- **Codex backend security defaults** (commit 47568ec):
  - `sandbox` now defaults to `None` (requires user approval) instead of `"danger-full-access"`
  - `full_auto` now defaults to `False` instead of `True`
  - **Migration**: Explicitly pass `sandbox="danger-full-access"` and `full_auto=True` to restore previous behavior

#### Improvements
- Python requirement lowered from 3.12+ to 3.11+ for broader compatibility
- UTF-8 encoding enforced across all backends and wrappers
- Blank line preservation in output splitting
- Windows path handling with `posix=False` in shlex.split
- Auto-detection of `codex.cmd`/`.bat` on Windows
- JSONL output filtering for clean agent messages

### Fixed

#### Security Fixes (4 Rounds)

**Round 1** (commit 47568ec):
1. **HIGH/BLOCKER**: Path traversal vulnerability in `team_name`/`agent_name` parameters
   - Added strict validation (only alphanumeric, underscore, hyphen)
   - Added `resolve()` checks to prevent directory escape
2. **HIGH**: Unvalidated senders + dangerous default privileges
   - Added team member validation in message bridge
   - Changed codex defaults to require user approval
3. **MEDIUM**: Information disclosure in tmux logs
   - Moved logs to private directory (`~/.anymate/logs`)
   - Set restrictive permissions (0o700/0o600)

**Round 2** (commit 4d5e7b3):
1. **HIGH**: Name validation timing (dirty config on failure)
   - Moved validation to START of `spawn_teammate` before any state changes
2. **MEDIUM**: Member authorization cache never invalidated
   - Added config file mtime tracking with automatic cache invalidation
3. **MEDIUM**: Sender validation lacks authenticity check (documented)
   - Added comprehensive documentation of architectural limitation
4. **LOW**: Log security fallback degradation
   - Created private subdirectory in temp with restrictive permissions

**Round 3** (commit ad9c2de):
1. **CRITICAL**: Arbitrary file deletion in `stop_teammate`
   - Added name validation in `stop_teammate` and `check_teammate`
   - Added defense-in-depth validation in `PaneLogger.log_path()`
   - Added path boundary checks with `resolve().relative_to()`

**Round 4** (commit 38099a2):
1. **HIGH**: Sender forgery via team-lead bypass
   - Removed special treatment for "team-lead" in sender validation
2. **LOW**: Log security final fallback degradation
   - Changed to fail-fast with RuntimeError instead of unsafe temp fallback
3. Added comprehensive security documentation for shell backend

#### Platform Compatibility
- Fixed Windows quoted path handling (strip quotes after `shlex.split`)
- Fixed UTF-8 corruption in non-UTF-8 locales (TextIOWrapper initialization)
- Fixed leading/trailing blank line stripping (changed to `rstrip("\r\n")`)
- Fixed Windows path escaping in codex backend (use `repr()` for paths)

#### Reliability
- Rollback failed teammate spawns (kill pane, close logger on error)
- Track concrete backend type in team config
- Hardened codex launcher (removed hardcoded timeout)

### Security

#### Vulnerabilities Fixed
- **1 CRITICAL**: Arbitrary file deletion (CVE-worthy)
- **4 HIGH**: Path traversal, name validation timing, sender bypass, team-lead bypass
- **4 MEDIUM**: Cache invalidation, logging disclosure, sender authenticity (documented)
- **2 LOW**: Logging fallback degradation

#### Defense-in-Depth Measures
1. **Entry point validation**: All MCP tools validate parameters before processing
2. **Function-level validation**: Utility functions validate their own inputs
3. **Path boundary checks**: `resolve().relative_to()` prevents escapes
4. **Test coverage**: 8 security tests covering all attack vectors

#### Architectural Security Model
- File-based IPC requires trust in processes with inbox write access
- Documented threat model and recommended mitigations:
  - Restrictive file permissions (0o700 on team directories)
  - Deployment in isolated environments (containers, VMs)
  - Trusted team members only for shell/python-repl backends
  - Consider codex backend with sandbox for untrusted code execution

### Known Issues

#### Architectural Limitations (Deferred to v0.2)
- **Sender authentication**: Messages can be forged by impersonating valid member names
  - Current implementation only validates sender NAME exists in team config
  - Does NOT verify message authenticity (who actually sent it)
  - Any process with inbox write access can forge messages
  - **Tracked**: xfail test added (commit 65d9f91)
  - **Mitigation**: Use restrictive file permissions, isolated environments, trusted teams
  - **Planned**: Cryptographic authentication (HMAC/signatures) or secure IPC (sockets/pipes) in v0.2

### Testing
- 19 core and security tests passing
- 1 xfail test documenting sender forgery limitation
- 100% pass rate, zero regressions
- Test coverage across:
  - Unit tests (backends, utilities)
  - End-to-end tests (bridge, message routing)
  - MCP protocol tests
  - Security tests (path traversal, validation, logging)

### Contributors
- Initial development and security hardening by the AnyMate-CC team
- Security review and testing assistance from Codex CLI

[0.1.0]: https://github.com/ARCJ137442/anymate-cc/releases/tag/v0.1.0
