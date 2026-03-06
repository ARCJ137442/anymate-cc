"""Universal stdio backend and session for AnyMate-CC."""
import asyncio
import re
import shlex
import uuid

from .base import (
    Backend,
    BackendCapabilities,
    BackendStatus,
    BridgeSession,
    OutputCallback,
)


class StdioSession(BridgeSession):
    def __init__(
        self,
        name: str,
        team_name: str,
        command: list[str],
        cwd: str,
        *,
        silence_timeout: float | None = None,
        sentinel: str | None = None,
        input_prefix: str | None = None,
        prompt_pattern: str | None = None,
        on_output: OutputCallback | None = None,
        pane_logger=None,
    ):
        super().__init__(name, team_name, on_output)
        self._command = command
        self._cwd = cwd
        self._silence_timeout = silence_timeout if silence_timeout is not None else 5.0
        self._sentinel = sentinel
        self._input_prefix = input_prefix or "__ANYMATE__:"
        self._prompt_re = re.compile(prompt_pattern) if prompt_pattern else None
        self._process: asyncio.subprocess.Process | None = None
        self._read_task: asyncio.Task | None = None
        self._pending_reply_to: str = "team-lead"
        self._buffer: list[str] = []
        self._pane_logger = pane_logger

    async def start(self) -> None:
        self._status = BackendStatus.STARTING
        self._process = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self._cwd,
        )
        self._status = BackendStatus.RUNNING
        self._read_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        try:
            if self._sentinel:
                await self._read_loop_sentinel()
            else:
                await self._read_loop_silence()
        finally:
            self._status = BackendStatus.STOPPED

    async def _read_loop_sentinel(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        assert self._sentinel is not None

        while self._process.returncode is None:
            try:
                raw = await asyncio.wait_for(self._process.stdout.readline(), timeout=120.0)
            except asyncio.TimeoutError:
                continue
            except Exception:
                break

            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line == self._sentinel:
                self._emit_buffer(default_when_empty=True)
                self._status = BackendStatus.IDLE
            else:
                self._buffer.append(line)

        self._emit_buffer(default_when_empty=False)

    async def _read_loop_silence(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None

        timeout = self._silence_timeout if self._silence_timeout > 0 else 1.0
        while self._process.returncode is None:
            try:
                raw = await asyncio.wait_for(self._process.stdout.readline(), timeout=timeout)
            except asyncio.TimeoutError:
                if self._buffer:
                    self._emit_buffer(default_when_empty=False)
                    self._status = BackendStatus.IDLE
                continue
            except Exception:
                break

            if not raw:
                break

            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            self._buffer.append(line)
            if self._prompt_re and self._prompt_re.search(line):
                self._emit_buffer(default_when_empty=False)
                self._status = BackendStatus.IDLE

        self._emit_buffer(default_when_empty=False)

    def _emit_buffer(self, *, default_when_empty: bool) -> None:
        if not self._on_output:
            self._buffer.clear()
            return
        output = "\n".join(self._buffer).strip()
        self._buffer.clear()
        if output:
            if self._pane_logger:
                self._pane_logger.log_output(output, self._pending_reply_to)
            self._on_output(output, self._pending_reply_to)
        elif default_when_empty:
            self._on_output("(no output)", self._pending_reply_to)

    async def send_message(self, text: str, reply_to: str = "team-lead") -> None:
        if not self._process or self._process.returncode is not None:
            return

        self._status = BackendStatus.RUNNING
        self._pending_reply_to = reply_to
        assert self._process.stdin is not None

        if self._pane_logger:
            self._pane_logger.log_input(text, reply_to)

        if self._sentinel:
            escaped = text.replace("\n", "\\n")
            payload = f"{self._input_prefix}{escaped}\n"
        else:
            payload = f"{text}\n"

        self._process.stdin.write(payload.encode("utf-8"))
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

        if self._pane_logger:
            self._pane_logger.close()
        self._status = BackendStatus.STOPPED

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None


class StdioBackend(Backend):
    @property
    def name(self) -> str:
        return "stdio"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_streaming=True,
            supports_interrupt=True,
            is_conversational=True,
            supports_cwd=True,
        )

    def is_available(self) -> bool:
        return True

    def create_session(self, name, team_name, prompt, cwd, *, on_output=None, **kwargs):
        command = kwargs.get("command")
        silence_timeout = kwargs.get("silence_timeout", 5.0)
        prompt_pattern = kwargs.get("prompt_pattern")

        if command is None:
            raise ValueError("Stdio backend requires 'command'")

        if isinstance(command, str):
            parsed = shlex.split(command)
        else:
            parsed = list(command)

        if not parsed:
            raise ValueError("Stdio backend requires a non-empty 'command'")

        return StdioSession(
            name=name,
            team_name=team_name,
            command=parsed,
            cwd=cwd,
            silence_timeout=silence_timeout,
            sentinel=kwargs.get("sentinel"),
            input_prefix=kwargs.get("input_prefix"),
            prompt_pattern=prompt_pattern,
            on_output=on_output,
            pane_logger=kwargs.get("pane_logger"),
        )


def make_sentinel() -> str:
    return f"__ANYMATE_DONE_{uuid.uuid4().hex[:8]}"
