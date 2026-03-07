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


def _get_secure_log_dir() -> Path:
    """Get or create a secure directory for tmux logs.

    Returns a private directory with restrictive permissions (0o700 on Unix).
    Falls back to temp directory if private directory cannot be created.

    Security: Fallback path also attempts to use restrictive permissions.
    """
    # Try to use ~/.anymate/logs (or ANYMATE_CLAUDE_DIR if set)
    if "ANYMATE_CLAUDE_DIR" in os.environ:
        base_dir = Path(os.environ["ANYMATE_CLAUDE_DIR"])
    else:
        base_dir = Path.home() / ".anymate"

    log_dir = base_dir / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        # Set restrictive permissions (owner-only read/write/execute)
        # Note: chmod works on Unix; Windows uses filesystem ACLs
        if os.name != "nt":
            log_dir.chmod(0o700)
        return log_dir
    except (OSError, PermissionError) as e:
        logger.warning("Cannot create secure log directory %s: %s. Falling back to temp.", log_dir, e)
        # Security: Even in fallback, create a private subdirectory with restrictive permissions
        fallback_dir = Path(tempfile.gettempdir()) / f".anymate-{os.getuid() if hasattr(os, 'getuid') else 'logs'}"
        try:
            fallback_dir.mkdir(parents=True, exist_ok=True)
            if os.name != "nt":
                fallback_dir.chmod(0o700)
            return fallback_dir
        except (OSError, PermissionError):
            # Last resort: use temp directory directly (less secure)
            logger.error("Cannot create secure fallback directory. Using temp directory without protection.")
            return Path(tempfile.gettempdir())


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
    """Writes formatted I/O log entries to a file for tmux pane display.

    Security: Logs are stored in a private directory with restrictive permissions.
    Set ANYMATE_DISABLE_LOGGING=1 environment variable to disable logging entirely.
    """

    def __init__(self, log_file: Path, name: str):
        self._log_file = log_file
        self._name = name
        self._file = None
        self._logging_disabled = os.environ.get("ANYMATE_DISABLE_LOGGING") == "1"

    def open(self) -> None:
        if self._logging_disabled:
            logger.info("Logging disabled for %s (ANYMATE_DISABLE_LOGGING=1)", self._name)
            return

        self._log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create log file with restrictive permissions (owner-only read/write)
        # Note: os.open with mode flag works on Unix; Windows uses ACLs instead
        if os.name == "nt":
            # Windows: Use standard open (permissions handled by filesystem ACLs)
            self._file = open(self._log_file, "a", encoding="utf-8")
        else:
            # Unix: Use os.open with explicit mode for restrictive permissions
            fd = os.open(self._log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            self._file = os.fdopen(fd, "a", encoding="utf-8")

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
        if self._logging_disabled:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"\n[{ts}] <<< FROM {from_agent} >>>")
        self._write(text)

    def log_output(self, text: str, to_agent: str) -> None:
        if self._logging_disabled:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"\n[{ts}] >>> TO {to_agent} >>>")
        self._write(text)

    def _write(self, text: str) -> None:
        if self._file:
            self._file.write(text + "\n")
            self._file.flush()

    @staticmethod
    def log_path(name: str, team_name: str) -> Path:
        """Get the log file path for a teammate.

        Security: Logs are stored in a private directory (~/.anymate/logs) with
        restrictive permissions (0o700). Set ANYMATE_DISABLE_LOGGING=1 to disable.

        Defense-in-depth: Validates name and team_name to prevent path traversal,
        even if caller forgot to validate.
        """
        # Security: Validate inputs to prevent path traversal
        from anymate.protocol.paths import _validate_safe_name
        _validate_safe_name(team_name, "team_name")
        _validate_safe_name(name, "name")

        log_dir = _get_secure_log_dir()
        log_file = log_dir / f"anymate-{team_name}-{name}.log"

        # Security: Ensure resolved path is still within log_dir
        try:
            log_file.resolve().relative_to(log_dir.resolve())
        except ValueError:
            raise ValueError(f"Log path escape attempt detected: {log_file}")

        return log_file
