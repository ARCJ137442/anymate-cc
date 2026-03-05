#!/usr/bin/env python3
"""Full end-to-end test of AnyMate-CC MCP server via JSON-RPC."""
import subprocess, json, time, os, shutil, sys

HOME = os.path.expanduser("~")
ANYMATE_SRC = os.path.join(HOME, "A137442/anymate-cc/src")
sys.path.insert(0, ANYMATE_SRC)

TEAM_NAME = "anymate-test-live"

# Step 1: Ensure clean state
team_dir = os.path.join(HOME, f".claude/teams/{TEAM_NAME}")
if os.path.exists(team_dir):
    shutil.rmtree(team_dir)

# Create team directory structure (simulating Claude Code's TeamCreate)
os.makedirs(os.path.join(team_dir, "inboxes"), exist_ok=True)

config = {
    "teamName": TEAM_NAME,
    "members": [
        {"name": "team-lead", "agentId": "lead-001", "agentType": "team-lead"}
    ]
}
with open(os.path.join(team_dir, "config.json"), "w") as f:
    json.dump(config, f, indent=2)

lead_inbox = os.path.join(team_dir, "inboxes/team-lead.json")
with open(lead_inbox, "w") as f:
    json.dump([], f)

print("✓ Step 1: Team directory created")

# Step 2: Start MCP server
env = os.environ.copy()
env["PYTHONPATH"] = ANYMATE_SRC
proc = subprocess.Popen(
    ["python3", "-m", "anymate.server"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env=env, cwd=os.path.join(HOME, "A137442/anymate-cc")
)
print(f"✓ Step 2: MCP server started (PID: {proc.pid})")

def send_rpc(method, params, req_id):
    msg = json.dumps({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
    proc.stdin.write((msg + "\n").encode())
    proc.stdin.flush()
    line = proc.stdout.readline().decode().strip()
    return json.loads(line) if line else None

# Step 3: Initialize
resp = send_rpc("initialize", {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "e2e-test", "version": "1.0"}
}, 1)
print(f"✓ Step 3: Initialize: {resp['result']['serverInfo']}")

# Step 4: Spawn Python REPL teammate
resp = send_rpc("tools/call", {
    "name": "spawn_teammate",
    "arguments": {"team_name": TEAM_NAME, "name": "py-calc", "backend_type": "python-repl"}
}, 2)
spawn_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 4: spawn_teammate → {spawn_text}")

time.sleep(2)

# Step 5: Check teammate
resp = send_rpc("tools/call", {
    "name": "check_teammate",
    "arguments": {"team_name": TEAM_NAME, "name": "py-calc"}
}, 3)
check_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 5: check_teammate → {check_text}")

# Step 6: Verify config updated
with open(os.path.join(team_dir, "config.json")) as f:
    members = [m["name"] for m in json.load(f)["members"]]
print(f"✓ Step 6: Config members: {members}")

# Step 7: Send message to py-calc (simulating Claude Code's SendMessage)
py_calc_inbox = os.path.join(team_dir, "inboxes/py-calc.json")
assert os.path.exists(py_calc_inbox), "py-calc inbox not created!"

message = {"from": "team-lead", "to": "py-calc", "text": "print(2 ** 10)", "timestamp": time.time(), "read": False}
with open(py_calc_inbox) as f:
    inbox = json.load(f)
inbox.append(message)
with open(py_calc_inbox, "w") as f:
    json.dump(inbox, f, indent=2)
print("✓ Step 7: Sent 'print(2 ** 10)' to py-calc")

# Step 8: Wait for bridge relay
print("  ⏳ Waiting for bridge to relay message...")
time.sleep(6)

with open(lead_inbox) as f:
    lead_messages = json.load(f)
print(f"✓ Step 8: Lead inbox has {len(lead_messages)} message(s):")
for msg in lead_messages:
    print(f"  [{msg.get('from','?')}]: {msg.get('text','')[:200]}")

# Step 9: Send eval expression
message2 = {"from": "team-lead", "to": "py-calc", "text": "sum(range(1, 101))", "timestamp": time.time(), "read": False}
with open(py_calc_inbox) as f:
    inbox = json.load(f)
inbox.append(message2)
with open(py_calc_inbox, "w") as f:
    json.dump(inbox, f, indent=2)
print("✓ Step 9: Sent 'sum(range(1, 101))' to py-calc")

time.sleep(6)

with open(lead_inbox) as f:
    lead_messages = json.load(f)
print(f"✓ Step 10: Lead inbox now has {len(lead_messages)} message(s):")
for msg in lead_messages:
    print(f"  [{msg.get('from','?')}]: {msg.get('text','')[:200]}")

# Step 11: Spawn stdio teammate (silence-timeout mode)
resp = send_rpc("tools/call", {
    "name": "spawn_teammate",
    "arguments": {
        "team_name": TEAM_NAME,
        "name": "stdio-echo",
        "backend_type": "stdio",
        "command": [
            "python3",
            "-u",
            "-c",
            "import sys\nfor line in sys.stdin:\n    print(line.rstrip('\\n'), flush=True)",
        ],
        "silence_timeout": 0.5,
    },
}, 4)
stdio_spawn_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 11: spawn stdio teammate → {stdio_spawn_text}")

stdio_inbox = os.path.join(team_dir, "inboxes/stdio-echo.json")
assert os.path.exists(stdio_inbox), "stdio-echo inbox not created!"

message3 = {"from": "team-lead", "to": "stdio-echo", "text": "stdio ping", "timestamp": time.time(), "read": False}
with open(stdio_inbox) as f:
    inbox = json.load(f)
inbox.append(message3)
with open(stdio_inbox, "w") as f:
    json.dump(inbox, f, indent=2)
print("✓ Step 12: Sent 'stdio ping' to stdio-echo")

time.sleep(6)
with open(lead_inbox) as f:
    lead_messages = json.load(f)
assert any(m.get("from") == "stdio-echo" and "stdio ping" in m.get("text", "") for m in lead_messages), (
    "Expected stdio-echo reply containing 'stdio ping'"
)
print("✓ Step 13: stdio-echo reply observed")

# Step 14: List teammates
resp = send_rpc("tools/call", {
    "name": "list_teammates",
    "arguments": {"team_name": TEAM_NAME}
}, 5)
list_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 14: list_teammates → {list_text}")

# Step 15: Stop teammates
resp = send_rpc("tools/call", {
    "name": "stop_teammate",
    "arguments": {"team_name": TEAM_NAME, "name": "py-calc"}
}, 6)
stop_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 15a: stop_teammate py-calc → {stop_text}")

resp = send_rpc("tools/call", {
    "name": "stop_teammate",
    "arguments": {"team_name": TEAM_NAME, "name": "stdio-echo"}
}, 7)
stop_stdio_text = resp["result"]["content"][0]["text"]
print(f"✓ Step 15b: stop_teammate stdio-echo → {stop_stdio_text}")

# Cleanup
proc.stdin.close()
proc.wait(timeout=5)
shutil.rmtree(team_dir)
print("\n🎉 All tests passed! Team directory cleaned up.")
