"""Full end-to-end test of AnyMate-CC MCP server via JSON-RPC."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _send_rpc(proc: subprocess.Popen, method: str, params: dict, req_id: int) -> dict:
    assert proc.stdin is not None
    assert proc.stdout is not None
    request = json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        ensure_ascii=False,
    )
    proc.stdin.write(request + "\n")
    proc.stdin.flush()
    line = proc.stdout.readline()
    if not line:
        stderr_text = ""
        if proc.stderr is not None:
            stderr_text = proc.stderr.read() or ""
        raise AssertionError(f"No JSON-RPC response from MCP server. stderr: {stderr_text}")
    return json.loads(line.strip())


def _tool_payload(response: dict) -> dict:
    return json.loads(response["result"]["content"][0]["text"])


def _wait_until(predicate, timeout: float = 10.0, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


def test_mcp_server_jsonrpc_e2e(tmp_path: Path) -> None:
    team_name = "anymate-test-live"
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / "src"
    claude_dir = tmp_path / ".claude"
    team_dir = claude_dir / "teams" / team_name
    inbox_dir = team_dir / "inboxes"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    _write_json(
        team_dir / "config.json",
        {
            "team_name": team_name,
            "members": [
                {
                    "name": "team-lead",
                    "agentId": "lead-001",
                    "agentType": "team-lead",
                    "isActive": True,
                }
            ],
        },
    )
    _write_json(inbox_dir / "team-lead.json", [])

    env = os.environ.copy()
    env["PYTHONPATH"] = str(src_dir)
    env["ANYMATE_CLAUDE_DIR"] = str(claude_dir)
    env["ANYMATE_PYTHON"] = sys.executable
    env["ANYMATE_POLL_INTERVAL"] = "0.2"

    proc = subprocess.Popen(
        [sys.executable, "-m", "anymate.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(repo_root),
        env=env,
    )

    try:
        initialize = _send_rpc(
            proc,
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "pytest-e2e", "version": "1.0"},
            },
            1,
        )
        assert initialize["result"]["serverInfo"]["name"] == "anymate-cc"

        spawn_payload = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {
                    "name": "spawn_teammate",
                    "arguments": {
                        "team_name": team_name,
                        "name": "py-calc",
                        "backend_type": "python-repl",
                        "cwd": str(tmp_path),
                    },
                },
                2,
            )
        )
        assert spawn_payload["success"] is True
        assert spawn_payload["name"] == "py-calc"

        check_payload = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "check_teammate", "arguments": {"team_name": team_name, "name": "py-calc"}},
                3,
            )
        )
        assert check_payload["registered"] is True
        assert check_payload["process_alive"] is True

        py_calc_inbox = inbox_dir / "py-calc.json"
        assert py_calc_inbox.exists()

        incoming = _read_json(py_calc_inbox)
        incoming.append(
            {
                "from": "team-lead",
                "to": "py-calc",
                "text": "print(2 ** 10)",
                "timestamp": time.time(),
                "read": False,
            }
        )
        _write_json(py_calc_inbox, incoming)

        lead_inbox = inbox_dir / "team-lead.json"

        def _has_python_reply() -> bool:
            messages = _read_json(lead_inbox)
            for msg in messages:
                text = msg.get("text", "")
                if msg.get("from") == "py-calc" and not text.startswith("{") and "1024" in text:
                    return True
            return False

        assert _wait_until(_has_python_reply, timeout=12.0), "Timed out waiting for py-calc reply"

        list_payload = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "list_teammates", "arguments": {"team_name": team_name}},
                4,
            )
        )
        assert list_payload["count"] == 1
        assert list_payload["teammates"][0]["name"] == "py-calc"

        stop_payload = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "stop_teammate", "arguments": {"team_name": team_name, "name": "py-calc"}},
                5,
            )
        )
        assert stop_payload["success"] is True

        config_after = _read_json(team_dir / "config.json")
        member_names = [member.get("name") for member in config_after.get("members", [])]
        assert "py-calc" not in member_names
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
