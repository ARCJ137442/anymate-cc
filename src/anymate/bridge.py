"""Message bridge: relay between Claude Code inbox JSON files and external processes."""
import asyncio
import logging
from .protocol.paths import PathResolver
from .protocol.messaging import read_unread_messages, send_reply, send_idle_notification
from .protocol.teams import read_config
from .backends.base import BridgeSession

logger = logging.getLogger(__name__)


def _split_chunks(text: str, size: int) -> list[str]:
    """Split text into chunks, breaking at newlines when possible."""
    if size <= 0:
        raise ValueError("Chunk size must be > 0")
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    while text:
        if len(text) <= size:
            chunks.append(text)
            break
        # Try to break at the last newline within the chunk
        cut = text.rfind("\n", 0, size)
        if cut <= 0:
            cut = size  # No good newline break; hard cut
        chunks.append(text[:cut])
        if cut < len(text) and text[cut] == "\n":
            text = text[cut + 1 :]
        else:
            text = text[cut:]
    return chunks

class MessageBridge:
    """Monitors inbox files for external teammates and relays messages."""

    def __init__(self, paths: PathResolver, team_name: str, poll_interval: float = 1.0):
        self._paths = paths
        self._team_name = team_name
        self._poll_interval = poll_interval
        self._sessions: dict[str, BridgeSession] = {}
        self._monitors: dict[str, asyncio.Task] = {}
        self._running = False
        self._team_members_cache: set[str] | None = None
        self._config_mtime: float | None = None

    def _get_team_members(self) -> set[str]:
        """Get set of valid team member names (cached with mtime invalidation).

        Security: Cache is automatically invalidated when team config file changes.
        """
        config_path = self._paths.config_path(self._team_name)
        try:
            current_mtime = config_path.stat().st_mtime if config_path.exists() else None
        except OSError:
            current_mtime = None

        # Invalidate cache if config file has been modified
        if current_mtime != self._config_mtime:
            self._team_members_cache = None
            self._config_mtime = current_mtime

        if self._team_members_cache is None:
            config = read_config(self._paths, self._team_name)
            if config:
                members = config.get("members", [])
                self._team_members_cache = {m.get("name") for m in members if m.get("name")}
            else:
                self._team_members_cache = set()
        return self._team_members_cache

    def _invalidate_members_cache(self) -> None:
        """Invalidate cached team members (call when team config changes)."""
        self._team_members_cache = None

    async def register(self, agent_name: str, session: BridgeSession) -> None:
        self._sessions[agent_name] = session
        if self._running:
            self._monitors[agent_name] = asyncio.create_task(
                self._monitor_loop(agent_name, session)
            )

    async def unregister(self, agent_name: str) -> None:
        if agent_name in self._monitors:
            self._monitors[agent_name].cancel()
            try:
                await self._monitors[agent_name]
            except asyncio.CancelledError:
                pass
            del self._monitors[agent_name]
        if agent_name in self._sessions:
            await self._sessions[agent_name].stop()
            del self._sessions[agent_name]

    async def start(self) -> None:
        self._running = True
        for name, session in self._sessions.items():
            if name not in self._monitors:
                self._monitors[name] = asyncio.create_task(
                    self._monitor_loop(name, session)
                )

    async def stop(self) -> None:
        self._running = False
        for name in list(self._monitors):
            await self.unregister(name)

    async def _monitor_loop(self, agent_name: str, session: BridgeSession) -> None:
        """Poll inbox for unread messages, relay to session."""
        while self._running and session.is_alive:
            try:
                messages = read_unread_messages(self._paths, self._team_name, agent_name)
                valid_members = self._get_team_members()

                for msg in messages:
                    sender = msg.get("from", "team-lead")
                    if sender == agent_name:
                        continue  # Skip own echo

                    # Security: Verify sender is a valid team member
                    # LIMITATION: This only checks if the sender NAME is in the team member list.
                    # It does NOT verify sender authenticity - any process that can write to
                    # the inbox JSON file can impersonate any team member by setting "from" field.
                    # This is an architectural limitation of the file-based IPC design.
                    # Potential mitigations: file owner checks, cryptographic signatures, or
                    # switching to a more secure IPC mechanism (sockets, pipes, etc).
                    #
                    # Security fix: Remove special treatment for "team-lead" - it must also be
                    # in the valid members list. This prevents trivial impersonation attacks.
                    if sender not in valid_members:
                        logger.warning(
                            "Rejecting message from unrecognized sender '%s' to %s (not in team member list)",
                            sender, agent_name
                        )
                        continue

                    text = msg.get("text", "")
                    # Skip structured protocol messages (idle, shutdown, etc)
                    if text.startswith("{") and '"type"' in text:
                        continue
                    logger.info("Relaying message from %s to %s: %s", sender, agent_name, text[:80])
                    await session.send_message(text, reply_to=sender)
            except Exception as e:
                logger.warning("Monitor error for %s: %s", agent_name, e)
            await asyncio.sleep(self._poll_interval)
        logger.info("Monitor loop ended for %s", agent_name)

    def _make_output_handler(self, agent_name: str, color: str | None = None,
                             max_chunk_size: int | None = 4096):
        """Create an on_output callback that writes replies to sender's inbox.

        Args:
            max_chunk_size: Split output into chunks of this many characters.
                            None or 0 disables chunking (deliver as-is).
        """
        def on_output(text: str, reply_to: str) -> None:
            try:
                effective_chunk_size = max_chunk_size if (max_chunk_size is not None and max_chunk_size > 0) else None
                chunks = _split_chunks(text, effective_chunk_size) if effective_chunk_size else [text]
                total = len(chunks)
                for i, chunk in enumerate(chunks, 1):
                    label = f"[{i}/{total}] " if total > 1 else ""
                    send_reply(self._paths, self._team_name, agent_name, reply_to,
                               f"{label}{chunk}", color=color)
                send_idle_notification(self._paths, self._team_name, agent_name, reply_to)
                logger.info("Sent reply from %s to %s (%d chunk(s), %d chars)",
                            agent_name, reply_to, total, len(text))
            except Exception as e:
                logger.error("Failed to send reply from %s: %s", agent_name, e)
        return on_output

    def get_session(self, agent_name: str) -> BridgeSession | None:
        return self._sessions.get(agent_name)
