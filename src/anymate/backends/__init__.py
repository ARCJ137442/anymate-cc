"""Backend registry for AnyMate-CC."""
from .base import Backend, BridgeSession, BackendCapabilities, BackendStatus, OutputCallback

_REGISTRY: dict[str, type[Backend]] = {}

def register_backend(cls: type[Backend]) -> type[Backend]:
    instance = cls()
    _REGISTRY[instance.name] = cls
    return cls

def get_backend(name: str) -> Backend | None:
    cls = _REGISTRY.get(name)
    return cls() if cls else None

def discover_backends() -> dict[str, Backend]:
    available = {}
    for name, cls in _REGISTRY.items():
        instance = cls()
        if instance.is_available():
            available[name] = instance
    return available

# Auto-register built-in backends
from .python_repl import PythonReplBackend
register_backend(PythonReplBackend)
