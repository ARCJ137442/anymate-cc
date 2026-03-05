"""Codex CLI backend for AnyMate-CC.

Wraps `codex exec --json` in a persistent Python loop that extracts only the
final agent message from each invocation, filtering out thinking/exec noise.
"""
import shutil

from .base import Backend, BackendCapabilities
from .stdio import StdioSession, make_sentinel

# Python wrapper that loops: read prompt from stdin → call codex exec --json
# → parse JSONL → extract last agent_message → print result + sentinel.
_CODEX_WRAPPER = '''\
import json, subprocess, sys, os

SENTINEL = "{sentinel}"
CODEX_BIN = "{codex_binary}"
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
            cmd, capture_output=True, text=True, timeout=600, cwd=CWD,
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
    except subprocess.TimeoutExpired:
        output = "(codex timed out after 600s)"
    except Exception as e:
        output = f"(codex error: {{e}})"

    print(output, flush=True)
    print(SENTINEL, flush=True)
'''


class CodexBackend(Backend):
    def __init__(self, codex_binary: str = "codex"):
        self._codex = codex_binary

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
        return shutil.which(self._codex) is not None

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
            codex_binary=self._codex,
            extra_args=repr(extra_args),
        )
        return StdioSession(
            name=name,
            team_name=team_name,
            command=["python3", "-u", "-c", wrapper_code],
            cwd=cwd,
            sentinel=sentinel,
            input_prefix="__ANYMATE__:",
            on_output=on_output,
        )
