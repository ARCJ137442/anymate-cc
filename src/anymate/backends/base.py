"""Abstract base classes for AnyMate backends."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Callable

class BackendStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    IDLE = "idle"
    STOPPED = "stopped"
    ERROR = "error"

@dataclass
class BackendCapabilities:
    supports_streaming: bool = False
    supports_interrupt: bool = False
    is_conversational: bool = False
    supports_cwd: bool = True

OutputCallback = Callable[[str, str], None]  # (output_text, reply_to) -> None

class BridgeSession(ABC):
    def __init__(self, name: str, team_name: str, on_output: OutputCallback | None = None):
        self._name = name
        self._team_name = team_name
        self._on_output = on_output
        self._status = BackendStatus.STOPPED

    @property
    def name(self) -> str:
        return self._name

    @property
    def status(self) -> BackendStatus:
        return self._status

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def send_message(self, text: str) -> None: ...

    @abstractmethod
    async def stop(self, timeout: float = 10.0) -> None: ...

    @property
    @abstractmethod
    def is_alive(self) -> bool: ...

class Backend(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def capabilities(self) -> BackendCapabilities: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def create_session(self, name: str, team_name: str, prompt: str, cwd: str, *, on_output: OutputCallback | None = None, **kwargs) -> BridgeSession: ...
