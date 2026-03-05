"""Shell backend preset for AnyMate-CC."""
import shutil

from .base import Backend, BackendCapabilities
from .stdio import StdioSession, make_sentinel

_SHELL_WRAPPER = '''\
SENTINEL="{sentinel}"
while IFS= read -r line; do
    case "$line" in
        __ANYMATE__:*)
            cmd="${{line#__ANYMATE__:}}"
            cmd="${{cmd//\\\\n/$'\\n'}}"
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
        )
