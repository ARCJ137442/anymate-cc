"""Atomic file operations with file locking."""
import json
import os
import tempfile
from pathlib import Path
from filelock import FileLock

def atomic_write_json(path: Path, data) -> None:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
        os.replace(tmp, str(path))
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

def locked_read_modify_write(path: Path, lock_path: Path, modify_fn):
    lock = FileLock(str(lock_path), timeout=10)
    with lock:
        if path.exists():
            data = json.loads(path.read_text())
        else:
            data = None
        result = modify_fn(data)
        atomic_write_json(path, result)
        return result

def locked_read_json(path: Path, lock_path: Path):
    lock = FileLock(str(lock_path), timeout=10)
    with lock:
        if path.exists():
            return json.loads(path.read_text())
        return None
