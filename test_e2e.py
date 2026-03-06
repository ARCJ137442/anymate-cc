"""End-to-end integration test for message bridge + python-repl backend."""
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anymate.backends import get_backend
from anymate.bridge import MessageBridge
from anymate.protocol.fileops import atomic_write_json, locked_read_json
from anymate.protocol.messaging import append_message, ensure_inbox, now_iso
from anymate.protocol.paths import PathResolver


async def _wait_for_reply(
    paths: PathResolver,
    team_name: str,
    expected_from: str,
    expected_text: str,
    timeout: float = 8.0,
) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        inbox_data = locked_read_json(
            paths.inbox_path(team_name, "team-lead"),
            paths.inboxes_lock_path(team_name),
        )
        for msg in inbox_data or []:
            text = msg.get("text", "")
            if msg.get("from") == expected_from and not text.startswith("{") and expected_text in text:
                return msg
        await asyncio.sleep(0.2)
    raise AssertionError(f"Timed out waiting for reply containing {expected_text!r}")


async def _run_bridge_e2e() -> None:
    tmpdir = Path(tempfile.mkdtemp(prefix="anymate_e2e_"))
    bridge: MessageBridge | None = None
    try:
        paths = PathResolver(base_dir=tmpdir)
        team_name = "test-team"

        config_dir = paths.team_dir(team_name)
        config_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            paths.config_path(team_name),
            {
                "team_name": team_name,
                "members": [
                    {
                        "agentId": "team-lead@test-team",
                        "name": "team-lead",
                        "agentType": "general-purpose",
                        "color": "blue",
                        "joinedAt": int(time.time() * 1000),
                        "isActive": True,
                    }
                ],
            },
        )

        ensure_inbox(paths, team_name, "team-lead")
        ensure_inbox(paths, team_name, "py-repl")

        backend = get_backend("python-repl")
        assert backend is not None, "python-repl backend not found"
        assert backend.is_available(), "python backend is not available in this environment"

        bridge = MessageBridge(paths, team_name, poll_interval=0.2)
        on_output = bridge._make_output_handler("py-repl", color="green")
        session = backend.create_session(
            name="py-repl",
            team_name=team_name,
            prompt="",
            cwd=str(tmpdir),
            on_output=on_output,
        )

        await session.start()
        await bridge.register("py-repl", session)
        await bridge.start()

        append_message(
            paths,
            team_name,
            "py-repl",
            {"from": "team-lead", "text": "1+1", "timestamp": now_iso(), "read": False},
        )
        first = await _wait_for_reply(paths, team_name, expected_from="py-repl", expected_text="2")
        assert "2" in first["text"]

        atomic_write_json(paths.inbox_path(team_name, "team-lead"), [])
        append_message(
            paths,
            team_name,
            "py-repl",
            {"from": "team-lead", "text": "print('hello')", "timestamp": now_iso(), "read": False},
        )
        second = await _wait_for_reply(paths, team_name, expected_from="py-repl", expected_text="hello")
        assert "hello" in second["text"]
    finally:
        if bridge is not None:
            await bridge.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bridge_python_repl_roundtrip() -> None:
    asyncio.run(_run_bridge_e2e())
