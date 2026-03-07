"""Targeted unit tests for backend/runtime edge cases."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from anymate.backends.codex import CodexBackend
from anymate.backends import codex as codex_module
from anymate.bridge import _split_chunks


def test_codex_backend_uses_anymate_python_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANYMATE_PYTHON", "custom-python")
    backend = CodexBackend(codex_binary="codex")
    session = backend.create_session(
        name="codex-agent",
        team_name="team",
        prompt="",
        cwd=".",
        on_output=None,
    )
    assert session._command[0] == "custom-python"


def test_codex_backend_falls_back_to_sys_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANYMATE_PYTHON", raising=False)
    backend = CodexBackend(codex_binary="codex")
    session = backend.create_session(
        name="codex-agent",
        team_name="team",
        prompt="",
        cwd=".",
        on_output=None,
    )
    assert session._command[0] == sys.executable


def test_codex_backend_uses_anymate_codex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANYMATE_CODEX", "custom-codex")
    backend = CodexBackend()
    assert backend._codex == "custom-codex"


def test_codex_backend_resolves_from_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANYMATE_CODEX", raising=False)
    monkeypatch.setattr(codex_module.shutil, "which", lambda name: "/tmp/codex-bin" if name == "codex" else None)
    backend = CodexBackend(codex_binary=None)
    assert backend._codex == "/tmp/codex-bin"


def test_codex_backend_falls_back_to_plain_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANYMATE_CODEX", raising=False)
    monkeypatch.setattr(codex_module.shutil, "which", lambda _name: None)
    backend = CodexBackend(codex_binary=None)
    assert backend._codex == "codex"


def test_split_chunks_rejects_non_positive_size() -> None:
    with pytest.raises(ValueError):
        _split_chunks("abc", 0)
    with pytest.raises(ValueError):
        _split_chunks("abc", -1)


def test_split_chunks_preserves_blank_lines_after_newline_split() -> None:
    chunks = _split_chunks("aa\n\nbb", 3)
    assert chunks == ["aa", "\nbb"]
