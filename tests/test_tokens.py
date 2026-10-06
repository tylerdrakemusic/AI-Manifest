import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load_tokens_module(
    monkeypatch: pytest.MonkeyPatch, dotenv_calls: list[object]
) -> ModuleType:
    dotenv_stub = ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: dotenv_calls.append(args)
    monkeypatch.setitem(sys.modules, "dotenv", dotenv_stub)
    monkeypatch.delitem(sys.modules, "src.utils.tokens", raising=False)
    return importlib.import_module("src.utils.tokens")


def test_token_module_does_not_load_dotenv_on_import(monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv_calls: list[object] = []

    _load_tokens_module(monkeypatch, dotenv_calls)

    assert dotenv_calls == []


def test_load_token_rejects_file_fallback_when_environment_is_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dotenv_calls: list[object] = []
    tokens = _load_tokens_module(monkeypatch, dotenv_calls)
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.setattr(tokens, "TOKENS_DIR", tmp_path, raising=False)
    (tmp_path / "elevenlabs").write_text("fixture-only-token", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        tokens.load_token("elevenlabs")


def test_load_token_reads_mapped_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv_calls: list[object] = []
    tokens = _load_tokens_module(monkeypatch, dotenv_calls)
    monkeypatch.setenv("ELEVENLABS_API_KEY", "environment-only-token")

    assert tokens.load_token("elevenlabs") == "environment-only-token"