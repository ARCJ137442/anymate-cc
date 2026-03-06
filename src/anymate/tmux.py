"""Tmux pane management for AnyMate-CC teammates."""
import logging
import os
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Map AnyMate color names to tmux color names
_TMUX_COLORS = {
    "blue": "blue", "green": "green", "yellow": "yellow",
    "purple": "magenta", "orange": "colour208", "pink": "colour213",
    "cyan": "cyan", "red": "red",
}


def is_tmux_available() -> bool:
    """Check if we're inside a tmux session and tmux binary exists."""
    return shutil.which("tmux") is not None and "TMUX" in os.environ


def create_pane(name: str, log_file: Path, color: str = "blue") -> str | None:
    """Create a tmux pane showing tail -f of a log file.

    Returns the pane ID (e.g. '%42') or None if tmux is unavailable.
    """
    if not is_tmux_available():
        return None

    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.touch()

    try:
        result = subprocess.run(
            [
                "tmux", "split-window", "-d", "-v",
                "-l", "15",
                "-P", "-F", "#{pane_id}",
                "tail", "-f", str(log_file),
            ],
            capture_output=True, text=True, timeout=5,
        )
        pane_id = result.stdout.strip()
        if not pane_id:
            logger.warning("tmux split-window did not return a pane ID")
            return None

        _set_pane_title(pane_id, f"AnyMate: {name}")
        _set_pane_border_color(pane_id, color)
        logger.info("Created tmux pane %s for teammate '%s'", pane_id, name)
        return pane_id
    except Exception as e:
        logger.warning("Failed to create tmux pane: %s", e)
        return None


def kill_pane(pane_id: str) -> bool:
    """Kill a tmux pane by ID."""
    if not pane_id:
        return False
    try:
        subprocess.run(["tmux", "kill-pane", "-t", pane_id],
                        capture_output=True, timeout=5)
        logger.info("Killed tmux pane %s", pane_id)
        return True
    except Exception as e:
        logger.warning("Failed to kill tmux pane %s: %s", pane_id, e)
        return False


def _set_pane_title(pane_id: str, title: str) -> None:
    try:
        subprocess.run(["tmux", "select-pane", "-t", pane_id, "-T", title],
                        capture_output=True, timeout=5)
    except Exception:
        pass


def _set_pane_border_color(pane_id: str, color: str) -> None:
    tmux_color = _TMUX_COLORS.get(color, color)
    try:
        subprocess.run(
            ["tmux", "select-pane", "-t", pane_id, "-P", f"border-fg={tmux_color}"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


class PaneLogger:
    """Writes formatted I/O log entries to a file for tmux pane display."""

    def __init__(self, log_file: Path, name: str):
        self._log_file = log_file
        self._name = name
        self._file = None

    def open(self) -> None:
        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._log_file, "a", encoding="utf-8")
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"{'=' * 50}")
        self._write(f"  AnyMate: {self._name}")
        self._write(f"  Started at {ts}")
        self._write(f"{'=' * 50}\n")

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None

    def log_input(self, text: str, from_agent: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"\n[{ts}] <<< FROM {from_agent} >>>")
        self._write(text)

    def log_output(self, text: str, to_agent: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"\n[{ts}] >>> TO {to_agent} >>>")
        self._write(text)

    def _write(self, text: str) -> None:
        if self._file:
            self._file.write(text + "\n")
            self._file.flush()

    @staticmethod
    def log_path(name: str, team_name: str) -> Path:
        return Path(tempfile.gettempdir()) / f"anymate-{team_name}-{name}.log"
