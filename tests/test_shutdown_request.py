"""Tests for shutdown_request protocol message handling in the bridge.

Covers:
- Protocol message detection (JSON shutdown_request recognized correctly)
- Plain text not misidentified as protocol messages
- shutdown_request intercepted by bridge (not forwarded to backend stdin)
- Session correctly stopped upon receiving shutdown_request
- shutdown_response sent back to the original sender
- Malformed / adversarial protocol message handling (security)
- Regression: existing tests remain unaffected
"""
import asyncio
import json
import time

import pytest

from anymate.backends.base import BackendStatus, BridgeSession
from anymate.bridge import MessageBridge
from anymate.protocol.fileops import atomic_write_json
from anymate.protocol.messaging import append_message, ensure_inbox, now_iso
from anymate.protocol.paths import PathResolver


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

class _RecordingSession(BridgeSession):
    """Minimal session that records send_message calls and tracks stop()."""

    def __init__(self, name: str, team_name: str):
        super().__init__(name, team_name, None)
        self.messages: list[tuple[str, str]] = []
        self._alive = True
        self.stop_called = False

    async def start(self) -> None:
        self._status = BackendStatus.RUNNING

    async def send_message(self, text: str, reply_to: str = "team-lead") -> None:
        self.messages.append((text, reply_to))

    async def stop(self, timeout: float = 10.0) -> None:
        self.stop_called = True
        self._alive = False
        self._status = BackendStatus.STOPPED

    @property
    def is_alive(self) -> bool:
        return self._alive


def _make_team(tmp_path, team_name="test-team", members=None):
    """Create a minimal team config and return (PathResolver, team_name)."""
    resolver = PathResolver(tmp_path)
    config_dir = resolver.team_dir(team_name)
    config_dir.mkdir(parents=True, exist_ok=True)

    if members is None:
        members = [
            {"name": "team-lead", "agentId": "team-lead@test-team"},
            {"name": "agent", "agentId": "agent@test-team"},
        ]

    atomic_write_json(
        resolver.config_path(team_name),
        {"members": members},
    )
    return resolver, team_name


def _make_shutdown_request_text(request_id="req-001"):
    """Build a shutdown_request JSON text payload."""
    return json.dumps({
        "type": "shutdown_request",
        "requestId": request_id,
        "content": "Task complete, wrapping up the session",
    })


async def _run_monitor_briefly(bridge, agent_name, session, cycles=15, interval=0.05):
    """Run the bridge monitor loop for a short period, then stop it."""
    bridge._running = True
    monitor = asyncio.create_task(bridge._monitor_loop(agent_name, session))
    try:
        for _ in range(cycles):
            await asyncio.sleep(interval)
            if not session.is_alive:
                break
    finally:
        bridge._running = False
        await asyncio.sleep(interval)
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# 1. Protocol message detection
# ---------------------------------------------------------------------------

class TestProtocolMessageDetection:
    """Verify that JSON protocol messages are correctly identified."""

    def test_shutdown_request_json_is_detected_as_protocol(self, tmp_path):
        """A well-formed shutdown_request JSON should be recognized as a protocol message."""
        text = _make_shutdown_request_text()
        # The bridge uses: text.startswith("{") and '"type"' in text
        assert text.startswith("{")
        assert '"type"' in text

    def test_shutdown_request_with_whitespace_prefix_not_detected(self, tmp_path):
        """Leading whitespace means startswith('{') is False -- not detected as protocol."""
        text = "  " + _make_shutdown_request_text()
        # Current heuristic requires text to start with '{'
        assert not text.startswith("{")

    def test_idle_notification_also_detected(self, tmp_path):
        """Other protocol message types (idle_notification) should also be detected."""
        text = json.dumps({"type": "idle_notification", "from": "agent", "timestamp": now_iso()})
        assert text.startswith("{")
        assert '"type"' in text

    def test_shutdown_response_detected(self, tmp_path):
        """shutdown_response is also a protocol message."""
        text = json.dumps({
            "type": "shutdown_response",
            "requestId": "req-001",
            "approve": True,
        })
        assert text.startswith("{")
        assert '"type"' in text


# ---------------------------------------------------------------------------
# 2. Plain text not misidentified
# ---------------------------------------------------------------------------

class TestPlainTextNotMisidentified:
    """Ensure normal text messages are NOT treated as protocol messages."""

    def test_plain_text_not_protocol(self):
        text = "Hello, please run the tests"
        assert not (text.startswith("{") and '"type"' in text)

    def test_json_without_type_field_not_protocol(self):
        text = json.dumps({"command": "run_tests", "args": []})
        assert not (text.startswith("{") and '"type"' in text)

    def test_text_containing_type_word_but_not_json(self):
        text = 'The "type" of backend is stdio'
        assert not text.startswith("{")

    def test_text_starting_with_brace_but_invalid_json(self):
        text = '{not valid json at all'
        # startswith("{") is True, but '"type"' not in text
        assert text.startswith("{")
        assert '"type"' not in text

    def test_plain_text_relayed_to_session(self, tmp_path):
        """Plain text messages should be forwarded to the session's send_message."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": "run pytest",
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) >= 1
        assert any("run pytest" in msg[0] for msg in relayed)


# ---------------------------------------------------------------------------
# 3. shutdown_request intercepted (not forwarded to backend)
# ---------------------------------------------------------------------------

class TestShutdownRequestIntercepted:
    """Verify shutdown_request is NOT forwarded to the backend's stdin."""

    def test_shutdown_request_not_forwarded_to_session(self, tmp_path):
        """The bridge should intercept shutdown_request and NOT relay it to send_message."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            # Send a shutdown_request protocol message
            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": _make_shutdown_request_text(),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        # No messages should have been forwarded (the shutdown_request is a protocol msg)
        assert len(relayed) == 0, f"shutdown_request was unexpectedly relayed: {relayed}"

    def test_mixed_messages_only_plain_text_forwarded(self, tmp_path):
        """When both plain text and shutdown_request are in the inbox,
        only the plain text should be forwarded."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            # First: plain text
            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": "hello world",
                "timestamp": now_iso(),
                "read": False,
            })
            # Second: protocol message
            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": _make_shutdown_request_text(),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        # Only the plain text should be forwarded
        assert len(relayed) == 1
        assert "hello world" in relayed[0][0]


# ---------------------------------------------------------------------------
# 4. Session stopped on shutdown_request
# ---------------------------------------------------------------------------

class TestSessionStoppedOnShutdown:
    """After processing a shutdown_request, the session should be stopped."""

    def test_session_stopped_after_shutdown_request(self, tmp_path):
        """The bridge should call session.stop() when it receives a shutdown_request."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": _make_shutdown_request_text("req-stop-001"),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session, cycles=30)
            return session

        session = asyncio.run(_exercise())
        # The session should have been stopped
        assert session.stop_called, "Session.stop() was not called after shutdown_request"
        assert not session.is_alive, "Session should not be alive after shutdown_request"


# ---------------------------------------------------------------------------
# 5. shutdown_response sent back to sender
# ---------------------------------------------------------------------------

class TestShutdownResponseSent:
    """The bridge should send a shutdown_response back to the sender's inbox."""

    def test_shutdown_response_written_to_sender_inbox(self, tmp_path):
        """After receiving a shutdown_request from team-lead, a shutdown_response
        should appear in team-lead's inbox."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")
            ensure_inbox(resolver, team_name, "team-lead")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": _make_shutdown_request_text("req-resp-001"),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session, cycles=30)

            # Read team-lead's inbox to check for shutdown_response
            from anymate.protocol.fileops import locked_read_json
            inbox_data = locked_read_json(
                resolver.inbox_path(team_name, "team-lead"),
                resolver.inboxes_lock_path(team_name),
            )
            return inbox_data or []

        inbox = asyncio.run(_exercise())
        # Look for a shutdown_response message
        responses = []
        for msg in inbox:
            text = msg.get("text", "")
            if text.startswith("{"):
                try:
                    payload = json.loads(text)
                    if payload.get("type") == "shutdown_response":
                        responses.append(payload)
                except json.JSONDecodeError:
                    pass

        assert len(responses) >= 1, (
            f"Expected a shutdown_response in team-lead inbox, got: {inbox}"
        )
        resp = responses[0]
        assert resp.get("requestId") == "req-resp-001"
        assert resp.get("approve") is True


# ---------------------------------------------------------------------------
# 6. Malformed / adversarial protocol messages (security)
# ---------------------------------------------------------------------------

class TestMalformedProtocolMessages:
    """Ensure malformed or adversarial protocol messages are handled safely."""

    def test_invalid_json_with_brace_prefix_not_crash(self, tmp_path):
        """Text starting with '{' but not valid JSON should not crash the bridge."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": '{this is not valid JSON at all',
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session

        # Should not raise
        session = asyncio.run(_exercise())
        # Invalid JSON without '"type"' should be forwarded as plain text
        assert len(session.messages) >= 1

    def test_json_with_unknown_type_not_crash(self, tmp_path):
        """A valid JSON with an unrecognized 'type' should be handled gracefully."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": json.dumps({"type": "unknown_protocol_v99", "data": "test"}),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session

        session = asyncio.run(_exercise())
        # Protocol messages are skipped (not forwarded)
        assert len(session.messages) == 0

    def test_shutdown_request_missing_request_id(self, tmp_path):
        """A shutdown_request without requestId should still be handled
        (the bridge should not crash)."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": json.dumps({"type": "shutdown_request"}),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session, cycles=30)
            return session

        # Should not raise
        session = asyncio.run(_exercise())
        # Message should not be forwarded (it's a protocol message)
        assert len(session.messages) == 0

    def test_deeply_nested_json_not_crash(self, tmp_path):
        """A deeply nested JSON object should not cause stack overflow or crash."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            # Create a reasonable but deeply nested JSON
            nested = {"type": "shutdown_request", "requestId": "deep"}
            for i in range(20):
                nested = {"wrapper": nested, "type": "shutdown_request"}

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": json.dumps(nested),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session

        # Should not raise
        session = asyncio.run(_exercise())
        # Detected as protocol message (has "type"), so not forwarded
        assert len(session.messages) == 0

    def test_shutdown_request_from_non_member_rejected(self, tmp_path):
        """A shutdown_request from an unknown sender should be rejected."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "evil-hacker",
                "text": _make_shutdown_request_text("req-evil"),
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session, cycles=20)
            return session

        session = asyncio.run(_exercise())
        # Should not be forwarded AND should not stop the session
        assert len(session.messages) == 0
        assert not session.stop_called, "Session should NOT be stopped by unauthorized sender"
        assert session.is_alive

    def test_empty_text_message_not_crash(self, tmp_path):
        """An empty text field should not crash the bridge."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": "",
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session

        # Should not raise
        session = asyncio.run(_exercise())
        # Empty text is still "plain text" and gets forwarded
        # (unless the bridge explicitly filters empty messages)


# ---------------------------------------------------------------------------
# 7. Regression: existing functionality not broken
# ---------------------------------------------------------------------------

class TestRegressionExistingBehavior:
    """Ensure existing bridge behavior is preserved after shutdown_request changes."""

    def test_normal_message_still_relayed(self, tmp_path):
        """Regular text messages must still be forwarded to the session."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": "print('hello')",
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) == 1
        assert relayed[0][0] == "print('hello')"
        assert relayed[0][1] == "team-lead"

    def test_idle_notification_still_skipped(self, tmp_path):
        """idle_notification protocol messages should still be silently skipped."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            idle_text = json.dumps({
                "type": "idle_notification",
                "from": "agent",
                "timestamp": now_iso(),
                "idleReason": "available",
            })
            append_message(resolver, team_name, "agent", {
                "from": "team-lead",
                "text": idle_text,
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) == 0

    def test_own_echo_still_skipped(self, tmp_path):
        """Messages from the agent itself should still be skipped."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "agent",
                "text": "echo from self",
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) == 0

    def test_sender_validation_still_works(self, tmp_path):
        """Messages from non-members should still be rejected."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            append_message(resolver, team_name, "agent", {
                "from": "unknown-user",
                "text": "should be rejected",
                "timestamp": now_iso(),
                "read": False,
            })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) == 0

    def test_multiple_normal_messages_all_relayed(self, tmp_path):
        """Multiple normal messages should all be forwarded in order."""
        async def _exercise():
            resolver, team_name = _make_team(tmp_path)
            ensure_inbox(resolver, team_name, "agent")

            for i in range(3):
                append_message(resolver, team_name, "agent", {
                    "from": "team-lead",
                    "text": f"message-{i}",
                    "timestamp": now_iso(),
                    "read": False,
                })

            bridge = MessageBridge(resolver, team_name, poll_interval=0.05)
            session = _RecordingSession("agent", team_name)
            await _run_monitor_briefly(bridge, "agent", session)
            return session.messages

        relayed = asyncio.run(_exercise())
        assert len(relayed) == 3
        texts = [msg[0] for msg in relayed]
        assert texts == ["message-0", "message-1", "message-2"]
