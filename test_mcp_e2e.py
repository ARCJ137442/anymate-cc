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

        invalid_chunk = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {
                    "name": "spawn_teammate",
                    "arguments": {
                        "team_name": team_name,
                        "name": "bad-chunk",
                        "backend_type": "stdio",
                        "cwd": str(tmp_path),
                        "command": [
                            sys.executable,
                            "-u",
                            "-c",
                            "print('ok')",
                        ],
                        "max_chunk_size": -1,
                    },
                },
                2,
            )
        )
        assert "error" in invalid_chunk
        assert "max_chunk_size" in invalid_chunk["error"]
        assert not (inbox_dir / "bad-chunk.json").exists()

        invalid_spawn = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {
                    "name": "spawn_teammate",
                    "arguments": {
                        "team_name": team_name,
                        "name": "bad-start",
                        "backend_type": "stdio",
                        "cwd": str(tmp_path),
                        "command": ["definitely-missing-executable-xyz"],
                    },
                },
                3,
            )
        )
        assert "error" in invalid_spawn
        assert "Failed to start teammate" in invalid_spawn["error"]
        assert not (inbox_dir / "bad-start.json").exists()
        config_after_failed_spawn = _read_json(team_dir / "config.json")
        failed_member_names = [member.get("name") for member in config_after_failed_spawn.get("members", [])]
        assert "bad-start" not in failed_member_names

        py_payload = _tool_payload(
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
                4,
            )
        )
        assert py_payload["success"] is True

        stdio_payload = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {
                    "name": "spawn_teammate",
                    "arguments": {
                        "team_name": team_name,
                        "name": "stdio-echo",
                        "backend_type": "stdio",
                        "cwd": str(tmp_path),
                        "command": [
                            sys.executable,
                            "-u",
                            "-c",
                            "import sys\nfor line in sys.stdin:\n    print(line.rstrip('\\n'), flush=True)",
                        ],
                        "silence_timeout": 0.5,
                    },
                },
                5,
            )
        )
        assert stdio_payload["success"] is True

        check_py = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "check_teammate", "arguments": {"team_name": team_name, "name": "py-calc"}},
                6,
            )
        )
        assert check_py["process_alive"] is True
        assert check_py["backend_type"] == "python-repl"

        py_calc_inbox = inbox_dir / "py-calc.json"
        stdio_inbox = inbox_dir / "stdio-echo.json"
        lead_inbox = inbox_dir / "team-lead.json"
        assert py_calc_inbox.exists()
        assert stdio_inbox.exists()

        py_messages = _read_json(py_calc_inbox)
        py_messages.append(
            {
                "from": "team-lead",
                "to": "py-calc",
                "text": "print(2 ** 10)",
                "timestamp": time.time(),
                "read": False,
            }
        )
        _write_json(py_calc_inbox, py_messages)

        stdio_messages = _read_json(stdio_inbox)
        stdio_messages.append(
            {
                "from": "team-lead",
                "to": "stdio-echo",
                "text": "stdio ping",
                "timestamp": time.time(),
                "read": False,
            }
        )
        _write_json(stdio_inbox, stdio_messages)

        def _has_replies() -> bool:
            messages = _read_json(lead_inbox)
            saw_py = any(
                msg.get("from") == "py-calc"
                and not msg.get("text", "").startswith("{")
                and "1024" in msg.get("text", "")
                for msg in messages
            )
            saw_stdio = any(
                msg.get("from") == "stdio-echo"
                and not msg.get("text", "").startswith("{")
                and "stdio ping" in msg.get("text", "")
                for msg in messages
            )
            return saw_py and saw_stdio

        assert _wait_until(_has_replies, timeout=15.0), "Timed out waiting for py-calc + stdio-echo replies"

        listed = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "list_teammates", "arguments": {"team_name": team_name}},
                7,
            )
        )
        names = {item["name"] for item in listed["teammates"]}
        assert {"py-calc", "stdio-echo"} <= names
        type_map = {item["name"]: item["backend_type"] for item in listed["teammates"]}
        assert type_map["py-calc"] == "python-repl"
        assert type_map["stdio-echo"] == "stdio"

        stop_py = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "stop_teammate", "arguments": {"team_name": team_name, "name": "py-calc"}},
                8,
            )
        )
        assert stop_py["success"] is True

        stop_stdio = _tool_payload(
            _send_rpc(
                proc,
                "tools/call",
                {"name": "stop_teammate", "arguments": {"team_name": team_name, "name": "stdio-echo"}},
                9,
            )
        )
        assert stop_stdio["success"] is True

        config_after = _read_json(team_dir / "config.json")
        member_names = [member.get("name") for member in config_after.get("members", [])]
        assert "py-calc" not in member_names
        assert "stdio-echo" not in member_names
    finally:
        if proc.stdin is not None and not proc.stdin.closed:
            proc.stdin.close()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
