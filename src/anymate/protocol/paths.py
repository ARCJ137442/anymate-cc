"""Resolve Claude Code teams/tasks directory paths."""
from pathlib import Path
import os
import re


def _validate_safe_name(name: str, field_name: str) -> None:
    """Validate that name contains only safe characters (no path traversal).

    Raises ValueError if name contains unsafe characters or path traversal patterns.
    """
    if not name:
        raise ValueError(f"{field_name} cannot be empty")

    # Only allow alphanumeric, underscore, hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', name):
        raise ValueError(
            f"{field_name} '{name}' contains invalid characters. "
            "Only alphanumeric, underscore, and hyphen are allowed."
        )

    # Explicit check for path traversal patterns (defense in depth)
    if '..' in name or '/' in name or '\\' in name:
        raise ValueError(f"{field_name} '{name}' contains path traversal characters")


class PathResolver:
    def __init__(self, base_dir: Path | None = None):
        if base_dir:
            self._base = base_dir
        elif "ANYMATE_CLAUDE_DIR" in os.environ:
            self._base = Path(os.environ["ANYMATE_CLAUDE_DIR"])
        else:
            self._base = Path.home() / ".claude"

    @property
    def base_dir(self) -> Path:
        return self._base

    def team_dir(self, team_name: str) -> Path:
        _validate_safe_name(team_name, "team_name")
        path = self._base / "teams" / team_name
        # Ensure resolved path is still within base directory (defense in depth)
        try:
            path.resolve().relative_to(self._base.resolve())
        except ValueError:
            raise ValueError(f"team_name '{team_name}' escapes base directory")
        return path

    def config_path(self, team_name: str) -> Path:
        return self.team_dir(team_name) / "config.json"

    def inboxes_dir(self, team_name: str) -> Path:
        return self.team_dir(team_name) / "inboxes"

    def inbox_path(self, team_name: str, agent_name: str) -> Path:
        _validate_safe_name(agent_name, "agent_name")
        path = self.inboxes_dir(team_name) / f"{agent_name}.json"
        # Ensure resolved path is still within team inboxes directory
        try:
            path.resolve().relative_to(self.inboxes_dir(team_name).resolve())
        except ValueError:
            raise ValueError(f"agent_name '{agent_name}' escapes inboxes directory")
        return path

    def inboxes_lock_path(self, team_name: str) -> Path:
        return self.inboxes_dir(team_name) / ".lock"
