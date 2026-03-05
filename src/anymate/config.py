"""Configuration for AnyMate-CC."""
from dataclasses import dataclass, field
from pathlib import Path
import os

@dataclass
class AnyMateConfig:
    claude_dir: Path | None = None
    poll_interval: float = 1.0
    python_binary: str = "python3"

    @classmethod
    def from_env(cls) -> "AnyMateConfig":
        return cls(
            claude_dir=Path(os.environ["ANYMATE_CLAUDE_DIR"]) if "ANYMATE_CLAUDE_DIR" in os.environ else None,
            poll_interval=float(os.environ.get("ANYMATE_POLL_INTERVAL", "1.0")),
            python_binary=os.environ.get("ANYMATE_PYTHON", "python3"),
        )
