"""Inbox operations for Claude Code teams."""
import json
from datetime import datetime, timezone
from pathlib import Path
from .paths import PathResolver
from .fileops import atomic_write_json, locked_read_modify_write, locked_read_json

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ensure_inbox(paths: PathResolver, team_name: str, agent_name: str) -> Path:
    inbox = paths.inbox_path(team_name, agent_name)
    inbox.parent.mkdir(parents=True, exist_ok=True)
    if not inbox.exists():
        atomic_write_json(inbox, [])
    return inbox

def read_unread_messages(paths: PathResolver, team_name: str, agent_name: str) -> list[dict]:
    """Read unread messages and mark them as read. Returns the unread messages."""
    lock = paths.inboxes_lock_path(team_name)
    inbox = paths.inbox_path(team_name, agent_name)
    
    def _mark_and_extract(messages):
        if messages is None:
            return []
        unread = []
        for msg in messages:
            if not msg.get("read", False):
                unread.append(dict(msg))
                msg["read"] = True
        return messages  # Return full list (with read=True) for write-back
    
    # We need to both extract unread AND write back. Do it in two steps.
    unread = []
    def _modify(messages):
        nonlocal unread
        if messages is None:
            messages = []
        for msg in messages:
            if not msg.get("read", False):
                unread.append(dict(msg))
                msg["read"] = True
        return messages
    
    locked_read_modify_write(inbox, lock, _modify)
    return unread

def append_message(paths: PathResolver, team_name: str, agent_name: str, message: dict) -> None:
    """Append a message to agent's inbox."""
    lock = paths.inboxes_lock_path(team_name)
    inbox = paths.inbox_path(team_name, agent_name)
    ensure_inbox(paths, team_name, agent_name)
    
    def _append(messages):
        if messages is None:
            messages = []
        messages.append(message)
        return messages
    
    locked_read_modify_write(inbox, lock, _append)

def send_reply(paths: PathResolver, team_name: str, from_name: str, to_name: str, text: str, color: str | None = None) -> None:
    """Send a plain text reply from an external teammate to someone's inbox."""
    message = {
        "from": from_name,
        "text": text,
        "timestamp": now_iso(),
        "read": False,
        "summary": (text[:57] + "...") if len(text) > 60 else text,
    }
    if color:
        message["color"] = color
    append_message(paths, team_name, to_name, message)

def send_idle_notification(paths: PathResolver, team_name: str, from_name: str, to_name: str = "team-lead") -> None:
    """Send idle notification (structured message) to indicate teammate is available."""
    payload = {
        "type": "idle_notification",
        "from": from_name,
        "timestamp": now_iso(),
        "idleReason": "available",
    }
    message = {
        "from": from_name,
        "text": json.dumps(payload),
        "timestamp": now_iso(),
        "read": False,
        "summary": f"{from_name} is idle",
    }
    append_message(paths, team_name, to_name, message)
