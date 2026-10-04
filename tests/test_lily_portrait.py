"""Tests for src/utils/lily_portrait.py — mocked integrations, no real API calls."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

# Bootstrap project path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.utils.lily_portrait as _lp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FailingCascade:
    def generate(
        self,
        prompt: str,
        *,
        output_dir: Path,
        negative_prompt: str | None = None,
    ) -> SimpleNamespace:
        raise RuntimeError("all image providers unavailable")


# ---------------------------------------------------------------------------
# _parse_size / _build_prompt / _today_cache_path
# ---------------------------------------------------------------------------

def test_build_prompt_contains_outfit() -> None:
    positive, _negative = _lp._build_prompt()
    assert "portrait" in positive.lower() or any(
        o.split()[0].lower() in positive.lower() for o in _lp._OUTFIT_DESCRIPTORS
    )
    # Result is a 2-tuple
    assert isinstance(positive, str)


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
# get_daily_portrait — shared cascade
# ---------------------------------------------------------------------------

def test_daily_portrait_uses_shared_cascade_with_lily_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    prompt = "Lily portrait with Tuesday's navy blazer"
    negative_prompt = "blurry, low quality"
    monkeypatch.setattr(_lp, "_build_prompt", lambda: (prompt, negative_prompt))
    generated = tmp_path / "cascade-result.png"
    generated.write_bytes(b"shared cascade image")
    factory_paths: list[Path] = []
    calls: list[tuple[str, Path, str | None]] = []

    class FakeCascade:
        def generate(
            self,
            actual_prompt: str,
            *,
            output_dir: Path,
            negative_prompt: str | None,
        ) -> SimpleNamespace:
            calls.append((actual_prompt, output_dir, negative_prompt))
            return SimpleNamespace(path=generated)

    def fake_import_module(module_name: str, *args: object, **kwargs: object) -> object:
        if module_name == "integrations.image_cascade":
            def fake_portrait_cascade(path: Path) -> FakeCascade:
                factory_paths.append(path)
                return FakeCascade()

            return SimpleNamespace(
                portrait_image_cascade=fake_portrait_cascade
            )
        return real_import_module(module_name, *args, **kwargs)

    real_import_module = _lp.importlib.import_module
    persona_svg = tmp_path / f"lily_portrait_{date.today().isoformat()}.svg"
    monkeypatch.setattr(_lp.importlib, "import_module", fake_import_module)

    result = _lp.get_daily_portrait()
    cached_path = tmp_path / f"lily_portrait_{date.today().isoformat()}.png"

    assert factory_paths == [persona_svg]
    assert calls == [(prompt, tmp_path, negative_prompt)]
    assert result == cached_path
    assert result.read_bytes() == b"shared cascade image"
    assert _lp.get_daily_portrait() == cached_path
    assert len(calls) == 1


# ---------------------------------------------------------------------------
def test_workspace_src_uses_configured_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKSPACE_ROOT", str(tmp_path))

    assert _lp._workspace_src_path() == tmp_path / "src"


# ---------------------------------------------------------------------------
# get_daily_portrait — both fail → SVG fallback
# ---------------------------------------------------------------------------

def test_svg_fallback_when_all_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_workspace_portrait_cascade", lambda _svg: _FailingCascade())

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
    monkeypatch.setattr(_lp, "_workspace_portrait_cascade", lambda _svg: _FailingCascade())

    tag = _lp.get_portrait_img_tag()
    assert "data:image/svg+xml;base64," in tag
    assert "<img" in tag


def test_img_tag_respects_max_width(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_lp, "_IMAGE_CACHE_DIR", tmp_path)
    monkeypatch.setattr(_lp, "_workspace_portrait_cascade", lambda _svg: _FailingCascade())

    tag = _lp.get_portrait_img_tag(max_width=80)
    assert "max-width:80px" in tag
