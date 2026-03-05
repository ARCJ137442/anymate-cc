"""Team config operations for injecting external teammates."""
import json
from pathlib import Path
from .paths import PathResolver
from .fileops import locked_read_modify_write, locked_read_json

def read_config(paths: PathResolver, team_name: str) -> dict | None:
    """Read team config. Returns None if team doesn't exist."""
    config = paths.config_path(team_name)
    lock = paths.inboxes_lock_path(team_name)
    return locked_read_json(config, lock)

def inject_member(paths: PathResolver, team_name: str, member_dict: dict) -> None:
    """Inject a new member into an existing team's config.json.
    Raises ValueError if team doesn't exist or name is duplicate."""
    config_path = paths.config_path(team_name)
    lock = paths.inboxes_lock_path(team_name)
    
    def _inject(config):
        if config is None:
            raise ValueError(f"Team '{team_name}' does not exist")
        name = member_dict.get("name")
        for m in config.get("members", []):
            if m.get("name") == name:
                raise ValueError(f"Member '{name}' already exists in team '{team_name}'")
        config.setdefault("members", []).append(member_dict)
        return config
    
    locked_read_modify_write(config_path, lock, _inject)

def remove_member(paths: PathResolver, team_name: str, agent_name: str) -> dict | None:
    """Remove a member from team config by name. Returns removed member dict or None."""
    config_path = paths.config_path(team_name)
    lock = paths.inboxes_lock_path(team_name)
    removed = [None]
    
    def _remove(config):
        if config is None:
            return config
        members = config.get("members", [])
        for i, m in enumerate(members):
            if m.get("name") == agent_name:
                removed[0] = members.pop(i)
                break
        config["members"] = members
        return config
    
    locked_read_modify_write(config_path, lock, _remove)
    return removed[0]

def get_member(paths: PathResolver, team_name: str, agent_name: str) -> dict | None:
    """Get a specific member from team config."""
    config = read_config(paths, team_name)
    if config is None:
        return None
    for m in config.get("members", []):
        if m.get("name") == agent_name:
            return m
    return None
