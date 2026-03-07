"""Shell backend preset for AnyMate-CC.

SECURITY WARNING:
This backend executes arbitrary shell commands via 'eval'. It is designed for
trusted environments where team members are authorized to run shell commands.

THREAT MODEL:
- Any process that can write to the team inbox JSON files can send commands
  to shell backend teammates
- Commands are executed with the same privileges as the AnyMate-CC server process
- This is by design - shell backend is meant for executing shell commands

MITIGATIONS:
1. Only use shell backend teammates in trusted teams
2. Ensure team inbox directories have restrictive permissions (0o700)
3. Consider using more restricted backends (python-repl with restricted globals,
   stdio with vetted commands) for untrusted environments
4. Monitor teammate messages and audit shell command execution

If you need sandbox protection, use the 'codex' backend with sandbox mode enabled.
"""
import shutil

from .base import Backend, BackendCapabilities
from .stdio import StdioSession, make_sentinel

# Security: This wrapper uses 'eval' to execute arbitrary shell commands
# This is intentional for the shell backend, but be aware of the security implications
_SHELL_WRAPPER = '''\
SENTINEL="{sentinel}"
while IFS= read -r line; do
    case "$line" in
        __ANYMATE__:*)
            cmd="${{line#__ANYMATE__:}}"
            cmd="${{cmd//\\\\n/$'\\n'}}"
            # Security: eval executes arbitrary commands - only use in trusted environments
            eval "$cmd" 2>&1
            printf '%s\\n' "$SENTINEL"
            ;;
    esac
done
'''


class ShellBackend(Backend):
    def __init__(self, shell_binary: str = "bash"):
        self._shell = shell_binary

    @property
    def name(self) -> str:
        return "shell"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_streaming=True,
            supports_interrupt=True,
            is_conversational=True,
            supports_cwd=True,
        )

    def is_available(self) -> bool:
        return shutil.which(self._shell) is not None

    def create_session(self, name, team_name, prompt, cwd, *, on_output=None, **kwargs):
        sentinel = make_sentinel()
        wrapper_code = _SHELL_WRAPPER.format(sentinel=sentinel)
        return StdioSession(
            name=name,
            team_name=team_name,
            command=[self._shell, "-c", wrapper_code],
            cwd=cwd,
            sentinel=sentinel,
            input_prefix="__ANYMATE__:",
            on_output=on_output,
            pane_logger=kwargs.get("pane_logger"),
        )
