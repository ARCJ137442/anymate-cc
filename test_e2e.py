"""End-to-end integration test for bridge + built-in backends."""
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
    py_session = None
    stdio_session = None
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

        py_backend = get_backend("python-repl")
        assert py_backend is not None, "python-repl backend not found"
        assert py_backend.is_available(), "python backend is not available in this environment"

        bridge = MessageBridge(paths, team_name, poll_interval=0.2)
        py_session = py_backend.create_session(
            name="py-repl",
            team_name=team_name,
            prompt="",
            cwd=str(tmpdir),
            on_output=bridge._make_output_handler("py-repl", color="green"),
        )

        await py_session.start()
        await bridge.register("py-repl", py_session)
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

        await bridge.unregister("py-repl")
        assert not py_session.is_alive

        stdio_backend = get_backend("stdio")
        assert stdio_backend is not None, "stdio backend not found"
        ensure_inbox(paths, team_name, "stdio-echo")

        stdio_session = stdio_backend.create_session(
            name="stdio-echo",
            team_name=team_name,
            prompt="",
            cwd=str(tmpdir),
            command=[
                sys.executable,
                "-u",
                "-c",
                "import sys\nfor line in sys.stdin:\n    print(line.rstrip('\\n'), flush=True)",
            ],
            silence_timeout=0.5,
            on_output=bridge._make_output_handler("stdio-echo", color="orange"),
        )
        await stdio_session.start()
        await bridge.register("stdio-echo", stdio_session)

        atomic_write_json(paths.inbox_path(team_name, "team-lead"), [])
        append_message(
            paths,
            team_name,
            "stdio-echo",
            {"from": "team-lead", "text": "stdio ping", "timestamp": now_iso(), "read": False},
        )
        third = await _wait_for_reply(paths, team_name, expected_from="stdio-echo", expected_text="stdio ping")
        assert "stdio ping" in third["text"]
    finally:
        if bridge is not None:
            await bridge.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_bridge_backends_roundtrip() -> None:
    asyncio.run(_run_bridge_e2e())
