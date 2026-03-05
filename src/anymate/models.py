"""Data models for Claude Code JSON protocol (pure dataclasses, no pydantic)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class TeammateMember:
    """Mirrors the camelCase member dict in config.json."""

    agent_id: str
    name: str
    agent_type: str = "general-purpose"
    model: str = ""
    prompt: str = ""
    color: str = "blue"
    plan_mode_required: bool = False
    joined_at: int = 0
    tmux_pane_id: str = ""
    cwd: str = ""
    subscriptions: list = field(default_factory=list)
    backend_type: str = "anymate"
    opencode_session_id: str | None = None
    is_active: bool = True

    def to_dict(self) -> dict:
        """Serialize to camelCase dict matching Claude Code's schema."""
        return {
            "agentId": self.agent_id,
            "name": self.name,
            "agentType": self.agent_type,
            "model": self.model,
            "prompt": self.prompt,
            "color": self.color,
            "planModeRequired": self.plan_mode_required,
            "joinedAt": self.joined_at,
            "tmuxPaneId": self.tmux_pane_id,
            "cwd": self.cwd,
            "subscriptions": self.subscriptions,
            "backendType": self.backend_type,
            "opencodeSessionId": self.opencode_session_id,
            "isActive": self.is_active,
        }


@dataclass
class InboxMessage:
    from_: str
    text: str
    timestamp: str
    read: bool = False
    summary: str | None = None
    color: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"from": self.from_, "text": self.text, "timestamp": self.timestamp, "read": self.read}
        if self.summary is not None:
            d["summary"] = self.summary
        if self.color is not None:
            d["color"] = self.color
        return d


@dataclass
class IdleNotification:
    from_: str
    timestamp: str
    type: Literal["idle_notification"] = "idle_notification"
    idle_reason: str = "available"

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "from": self.from_,
            "timestamp": self.timestamp,
            "idleReason": self.idle_reason,
        }


COLOR_PALETTE: list[str] = ["blue", "green", "yellow", "purple", "orange", "pink", "cyan", "red"]
