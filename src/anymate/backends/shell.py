"""Shell backend for AnyMate-CC — runs a persistent bash session."""
import asyncio
import shutil
import uuid
from .base import Backend, BridgeSession, BackendCapabilities, BackendStatus, OutputCallback

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


class ShellSession(BridgeSession):
    def __init__(self, name: str, team_name: str, cwd: str,
                 shell_binary: str = "bash",
                 on_output: OutputCallback | None = None):
        super().__init__(name, team_name, on_output)
        self._cwd = cwd
        self._shell = shell_binary
        self._sentinel = f"__ANYMATE_DONE_{uuid.uuid4().hex[:8]}"
        self._process: asyncio.subprocess.Process | None = None
        self._read_task: asyncio.Task | None = None
        self._pending_reply_to: str = "team-lead"

    async def start(self) -> None:
        self._status = BackendStatus.STARTING
        wrapper_code = _SHELL_WRAPPER.format(sentinel=self._sentinel)
        self._process = await asyncio.create_subprocess_exec(
            self._shell, "-c", wrapper_code,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._cwd,
        )
        self._status = BackendStatus.RUNNING
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        buffer = []
        assert self._process is not None
        assert self._process.stdout is not None
        while self._process.returncode is None:
            try:
                raw = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=300.0
                )
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip("\n")
                if line == self._sentinel:
                    output = "\n".join(buffer).strip()
                    buffer.clear()
                    if self._on_output:
                        self._on_output(
                            output if output else "(no output)",
                            self._pending_reply_to,
                        )
                    self._status = BackendStatus.IDLE
                else:
                    buffer.append(line)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
        self._status = BackendStatus.STOPPED

    async def send_message(self, text: str, reply_to: str = "team-lead") -> None:
        if not self._process or self._process.returncode is not None:
            return
        self._status = BackendStatus.RUNNING
        self._pending_reply_to = reply_to
        escaped = text.strip().replace("\n", "\\n")
        cmd = f"__ANYMATE__:{escaped}\n"
        assert self._process.stdin is not None
        self._process.stdin.write(cmd.encode())
        await self._process.stdin.drain()

    async def stop(self, timeout: float = 10.0) -> None:
        if self._process and self._process.returncode is None:
            assert self._process.stdin is not None
            self._process.stdin.close()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        self._status = BackendStatus.STOPPED

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None


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

    def create_session(self, name, team_name, prompt, cwd, *,
                       on_output=None, **kwargs):
        return ShellSession(
            name=name, team_name=team_name, cwd=cwd,
            shell_binary=self._shell, on_output=on_output,
        )
