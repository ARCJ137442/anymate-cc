"""Resolve Claude Code teams/tasks directory paths."""
from pathlib import Path
import os

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
        return self._base / "teams" / team_name

    def config_path(self, team_name: str) -> Path:
        return self.team_dir(team_name) / "config.json"

    def inboxes_dir(self, team_name: str) -> Path:
        return self.team_dir(team_name) / "inboxes"

    def inbox_path(self, team_name: str, agent_name: str) -> Path:
        return self.inboxes_dir(team_name) / f"{agent_name}.json"

    def inboxes_lock_path(self, team_name: str) -> Path:
        return self.inboxes_dir(team_name) / ".lock"
