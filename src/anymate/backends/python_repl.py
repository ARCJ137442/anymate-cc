"""Python REPL backend preset for AnyMate-CC."""
import os
import shutil
import sys

from .base import Backend, BackendCapabilities
from .stdio import StdioSession, make_sentinel

_REPL_WRAPPER = '''\
import sys, io, traceback
# Force UTF-8 encoding for stdin/stdout to match parent process
sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', line_buffering=True)
SENTINEL = "{sentinel}"
while True:
    try:
        line = input()
    except EOFError:
        break
    if not line.startswith("__ANYMATE__:"):
        continue
    code = line[12:].replace("\\\\n", "\\n")
    old_stdout, old_stderr = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = buf = io.StringIO()
    try:
        try:
            result = eval(compile(code, "<repl>", "eval"))
            if result is not None:
                print(repr(result))
        except SyntaxError:
            exec(compile(code, "<repl>", "exec"))
    except Exception:
        traceback.print_exc()
    finally:
        sys.stdout, sys.stderr = old_stdout, old_stderr
    output = buf.getvalue()
    if output:
        print(output, end="", file=sys.stdout, flush=True)
    print(SENTINEL, file=sys.stdout, flush=True)
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


class PythonReplBackend(Backend):
    def __init__(self, python_binary: str | None = None):
        self._python = _resolve_python_binary(python_binary)

    @property
    def name(self) -> str:
        return "python-repl"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_streaming=True,
            supports_interrupt=True,
            is_conversational=True,
            supports_cwd=True,
        )

    def is_available(self) -> bool:
        return shutil.which(self._python) is not None or os.path.isfile(self._python)

    def create_session(self, name, team_name, prompt, cwd, *, on_output=None, **kwargs):
        sentinel = make_sentinel()
        wrapper_code = _REPL_WRAPPER.format(sentinel=sentinel)
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
