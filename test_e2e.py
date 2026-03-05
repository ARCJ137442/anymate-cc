"""End-to-end integration test: full MVP flow without MCP transport.

Validates: team setup → spawn teammate → inbox relay → REPL eval/exec → reply delivery.
"""
import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anymate.protocol.paths import PathResolver
from anymate.protocol.messaging import ensure_inbox, append_message, now_iso
from anymate.protocol.fileops import atomic_write_json, locked_read_json
from anymate.backends import get_backend
from anymate.bridge import MessageBridge


async def wait_for_reply(paths, team_name: str, sender: str, expected: str, timeout_s: float = 6.0) -> str:
    attempts = int(timeout_s / 0.2)
    for _ in range(attempts):
        await asyncio.sleep(0.2)
        inbox_data = locked_read_json(
            paths.inbox_path(team_name, "team-lead"),
            paths.inboxes_lock_path(team_name),
        )
        if not inbox_data:
            continue
        for msg in inbox_data:
            if msg.get("from") == sender and not msg.get("text", "").startswith("{"):
                text = msg.get("text", "")
                assert expected in text, f"Expected {expected!r} in reply, got: {text!r}"
                return text
    raise AssertionError(f"Timed out waiting for reply from {sender!r} containing {expected!r}")


async def main():
    # ── Step 1: Create temporary team directory structure ──────────────
    tmpdir = Path(tempfile.mkdtemp(prefix="anymate_e2e_"))
    print(f"[SETUP] Temp dir: {tmpdir}")

    paths = PathResolver(base_dir=tmpdir)
    team_name = "test-team"

    # Create config.json with a lead member
    config_dir = paths.team_dir(team_name)
    config_dir.mkdir(parents=True, exist_ok=True)
    initial_config = {
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
    }
    atomic_write_json(paths.config_path(team_name), initial_config)

    # Create inboxes directory and team-lead inbox
    ensure_inbox(paths, team_name, "team-lead")
    print("[PASS] Step 1: Team directory structure created")

    # ── Step 2: Spawn python-repl teammate ────────────────────────────
    backend = get_backend("python-repl")
    assert backend is not None, "python-repl backend not found"
    assert backend.is_available(), "python3 not available"

    poll_interval = 0.3  # fast polling for test
    bridge = MessageBridge(paths, team_name, poll_interval)
    on_output = bridge._make_output_handler("py-repl", color="green")

    session = backend.create_session(
        name="py-repl",
        team_name=team_name,
        prompt="",
        cwd=str(tmpdir),
        on_output=on_output,
    )

    # Create py-repl inbox
    ensure_inbox(paths, team_name, "py-repl")

    # Start session and bridge
    await session.start()
    assert session.is_alive, "Session should be alive after start"
    await bridge.register("py-repl", session)
    await bridge.start()
    print("[PASS] Step 2: py-repl spawned, bridge running")

    # ── Step 3: Simulate team-lead sends "1+1" to py-repl ────────────
    append_message(paths, team_name, "py-repl", {
        "from": "team-lead",
        "text": "1+1",
        "timestamp": now_iso(),
        "read": False,
    })
    print("[    ] Step 3: Sent '1+1' to py-repl inbox")

    # ── Step 4: Wait for bridge poll → REPL eval → reply ─────────────
    reply = await wait_for_reply(paths, team_name, "py-repl", "2")
    print(f"[PASS] Steps 3-5: eval path — sent '1+1', got reply: {reply!r}")

    # ── Step 6: Test exec path — send "print('hello')" ───────────────
    # Clear team-lead inbox for clean check
    atomic_write_json(paths.inbox_path(team_name, "team-lead"), [])

    append_message(paths, team_name, "py-repl", {
        "from": "team-lead",
        "text": "print('hello')",
        "timestamp": now_iso(),
        "read": False,
    })
    print("[    ] Step 6: Sent \"print('hello')\" to py-repl inbox")

    reply = await wait_for_reply(paths, team_name, "py-repl", "hello")
    print(f"[PASS] Step 6: exec path — sent \"print('hello')\", got reply: {reply!r}")

    # ── Step 7: Spawn stdio teammate (silence-timeout mode) ──────────
    await bridge.unregister("py-repl")
    assert not session.is_alive, "python-repl session should be stopped after unregister"

    stdio_backend = get_backend("stdio")
    assert stdio_backend is not None, "stdio backend not found"
    assert stdio_backend.is_available(), "stdio backend should always be available"

    stdio_name = "stdio-echo"
    stdio_session = stdio_backend.create_session(
        name=stdio_name,
        team_name=team_name,
        prompt="",
        cwd=str(tmpdir),
        command=[
            "python3",
            "-u",
            "-c",
            "import sys\nfor line in sys.stdin:\n    print(line.rstrip('\\n'), flush=True)",
        ],
        silence_timeout=0.5,
        on_output=bridge._make_output_handler(stdio_name, color="orange"),
    )
    ensure_inbox(paths, team_name, stdio_name)
    await stdio_session.start()
    assert stdio_session.is_alive, "stdio session should be alive after start"
    await bridge.register(stdio_name, stdio_session)
    print("[PASS] Step 7: stdio echo teammate spawned")

    atomic_write_json(paths.inbox_path(team_name, "team-lead"), [])
    append_message(paths, team_name, stdio_name, {
        "from": "team-lead",
        "text": "stdio ping",
        "timestamp": now_iso(),
        "read": False,
    })
    print("[    ] Step 8: Sent 'stdio ping' to stdio echo inbox")

    reply = await wait_for_reply(paths, team_name, stdio_name, "stdio ping", timeout_s=8.0)
    print(f"[PASS] Step 8: stdio silence-timeout path — got reply: {reply!r}")

    # ── Step 9: Cleanup ───────────────────────────────────────────────
    await bridge.stop()
    assert not stdio_session.is_alive, "Session should be stopped after bridge.stop()"
    print("[PASS] Step 9: Bridge stopped, sessions cleaned up")

    # Verify config.json is intact
    final_config = locked_read_json(
        paths.config_path(team_name),
        paths.inboxes_lock_path(team_name),
    )
    assert final_config is not None, "config.json should still exist"
    print(f"[PASS] Config intact: {len(final_config.get('members', []))} member(s)")

    # Remove temp dir
    shutil.rmtree(tmpdir)
    print(f"[PASS] Temp dir cleaned: {tmpdir}")

    print("\n===== ALL E2E TESTS PASSED =====")


if __name__ == "__main__":
    asyncio.run(main())
