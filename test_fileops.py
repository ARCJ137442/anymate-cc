"""Regression tests for protocol file operations."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anymate.protocol.fileops import atomic_write_json, locked_read_json, locked_read_modify_write


def test_atomic_write_json_uses_utf8_for_non_ascii(tmp_path: Path) -> None:
    path = tmp_path / "payload.json"
    payload = {"text": "中文-emoji-like: []"}
    atomic_write_json(path, payload)

    raw = path.read_bytes()
    assert b"\\u4e2d\\u6587" not in raw
    assert "中文".encode("utf-8") in raw


def test_locked_read_modify_write_preserves_utf8_content(tmp_path: Path) -> None:
    path = tmp_path / "messages.json"
    lock_path = tmp_path / ".lock"
    atomic_write_json(path, {"message": "你好"})

    def _modify(data: dict) -> dict:
        data["message"] = data["message"] + "-世界"
        return data

    locked_read_modify_write(path, lock_path, _modify)
    loaded = locked_read_json(path, lock_path)
    assert loaded == {"message": "你好-世界"}
