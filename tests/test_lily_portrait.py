"""Tests for src/utils/lily_portrait.py — mocked integrations, no real API calls."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Bootstrap project path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.utils.lily_portrait as _lp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_generate(prompt: str, output_dir: Path, **kwargs) -> Path:
    """Simulate a successful image client by writing a stub PNG."""
    p = output_dir / "generated_stub.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    return p


# ---------------------------------------------------------------------------
# _parse_size / _build_prompt / _today_cache_path
# ---------------------------------------------------------------------------

def test_build_prompt_contains_outfit() -> None:
    prompt = _lp._build_prompt()
    assert "portrait" in prompt.lower()
    # At least one outfit descriptor appears
    assert any(o.split()[0].lower() in prompt.lower() for o in _lp._OUTFIT_DESCRIPTORS)


def test_today_cache_path_contains_date() -> None:
    path = _lp._today_cache_path()
    assert date.today().isoformat() in path.name
    assert path.suffix == ".png"


# ---------------------------------------------------------------------------
# get_daily_portrait — cache hit
# ---------------------------------------------------------------------------

def test_returns_cached_portrait_if_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    today = date.today().isoformat()
    cached = tmp_path / f"lily_portrait_{today}.png"
    cached.write_bytes(b"fake png data")

    result = _lp.get_daily_portrait()
    assert result == cached


# ---------------------------------------------------------------------------
# get_daily_portrait — DALL-E 3 success
# ---------------------------------------------------------------------------

def test_dalle3_success_renames_to_canonical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)

    generated = tmp_path / "abcdef123456.png"
    generated.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)

    monkeypatch.setattr(_lp, "_try_dalle3", lambda prompt, save_dir: generated)
    monkeypatch.setattr(_lp, "_try_huggingface", lambda prompt, save_dir: None)

    result = _lp.get_daily_portrait()
    today = date.today().isoformat()
    assert result.name == f"lily_portrait_{today}.png"
    assert result.exists()


# ---------------------------------------------------------------------------
# get_daily_portrait — DALL-E 3 fails, HuggingFace succeeds
# ---------------------------------------------------------------------------

def test_huggingface_fallback_when_dalle3_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)

    generated = tmp_path / "hf_stub.png"
    generated.write_bytes(b"\x89PNG\r\n\x1a\n" + b"y" * 64)

    monkeypatch.setattr(_lp, "_try_dalle3", lambda prompt, save_dir: None)
    monkeypatch.setattr(_lp, "_try_huggingface", lambda prompt, save_dir: generated)

    result = _lp.get_daily_portrait()
    today = date.today().isoformat()
    assert result.name == f"lily_portrait_{today}.png"
    assert result.exists()


# ---------------------------------------------------------------------------
# get_daily_portrait — both fail → SVG fallback
# ---------------------------------------------------------------------------

def test_svg_fallback_when_all_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_try_dalle3", lambda prompt, save_dir: None)
    monkeypatch.setattr(_lp, "_try_huggingface", lambda prompt, save_dir: None)

    result = _lp.get_daily_portrait()
    assert result.exists()
    assert result.suffix == ".svg"
    content = result.read_text(encoding="utf-8")
    assert "<svg" in content


# ---------------------------------------------------------------------------
# _prune_old_portraits
# ---------------------------------------------------------------------------

def test_prune_keeps_n_most_recent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_MAX_CACHED_PORTRAITS", 2)

    # Create 4 portrait files
    for i in range(4):
        (tmp_path / f"lily_portrait_2026-01-0{i+1}.png").write_bytes(b"x")

    _lp._prune_old_portraits()

    remaining = sorted(tmp_path.glob("lily_portrait_*.png"))
    assert len(remaining) == 2
    # Should keep the two most recent
    assert remaining[-1].name == "lily_portrait_2026-01-04.png"
    assert remaining[-2].name == "lily_portrait_2026-01-03.png"


# ---------------------------------------------------------------------------
# get_portrait_img_tag
# ---------------------------------------------------------------------------

def test_img_tag_contains_data_uri_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    # Create a fake cached portrait
    today = date.today().isoformat()
    cached = tmp_path / f"lily_portrait_{today}.png"
    cached.write_bytes(b"\x89PNG\r\n\x1a\n" + b"z" * 64)

    tag = _lp.get_portrait_img_tag()
    assert "data:image/png;base64," in tag
    assert "<img" in tag
    assert 'alt="Lily' in tag


def test_img_tag_svg_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_try_dalle3", lambda p, d: None)
    monkeypatch.setattr(_lp, "_try_huggingface", lambda p, d: None)

    tag = _lp.get_portrait_img_tag()
    assert "data:image/svg+xml;base64," in tag
    assert "<img" in tag


def test_img_tag_respects_max_width(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_try_dalle3", lambda p, d: None)
    monkeypatch.setattr(_lp, "_try_huggingface", lambda p, d: None)

    tag = _lp.get_portrait_img_tag(max_width=80)
    assert "max-width:80px" in tag
