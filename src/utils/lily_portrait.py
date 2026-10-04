"""Lily portrait generator — daily cached AI-generated portrait for the executive brief.

Generates a headshot portrait of "Lily" (the executive brief voice persona) using
the shared Workspace image cascade with Lily's SVG artwork as the final fallback.

The portrait is cached by calendar date so it is generated at most once per day.
Up to 3 daily cached images are kept; older ones are pruned.

Usage::

    from src.utils.lily_portrait import get_daily_portrait

    path = get_daily_portrait()  # Path to cached PNG or SVG fallback
    # path is always valid — never raises
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _workspace_src_path() -> Path:
    """Find the Workspace source directory from configuration or the sibling checkout."""
    configured_root = os.environ.get("WORKSPACE_ROOT", "").strip()
    if configured_root:
        return Path(configured_root) / "src"

    for parent in Path(__file__).resolve().parents:
        sibling_src = parent / "⊕Workspace" / "src"
        if sibling_src.is_dir():
            return sibling_src
    raise ModuleNotFoundError("Workspace source directory is not configured or discoverable")


def _workspace_portrait_cascade(persona_svg: Path) -> Any:
    """Build the shared Workspace image cascade for Lily's SVG fallback."""
    workspace_src = _workspace_src_path()
    if str(workspace_src) not in sys.path:
        sys.path.insert(0, str(workspace_src))
    module = importlib.import_module("integrations.image_cascade")
    return module.portrait_image_cascade(persona_svg)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IMAGE_CACHE_DIR = _PROJECT_ROOT / "output" / "images"
_MAX_CACHED_PORTRAITS = 3

# Outfit rotation — 7 descriptors cycling by ISO weekday (1=Mon … 7=Sun)
_OUTFIT_DESCRIPTORS: list[str] = [
    "cream silk blouse with delicate pearl buttons",          # Monday
    "navy blazer over a soft white t-shirt",                  # Tuesday
    "burgundy turtleneck sweater",                            # Wednesday
    "crisp white linen shirt, collar open",                   # Thursday
    "charcoal grey ribbed cardigan",                          # Friday
    "emerald green wrap top",                                 # Saturday
    "soft heather grey oversized knit sweater",               # Sunday
]

_BASE_PROMPT = (
    "A photorealistic studio portrait of an elegant, professional woman in her early 30s. "
    "Warm studio lighting, velvety soft-focus neutral background, square crop, headshot style. "
    "Confident expression, natural makeup, professional appearance. "
    "Attire: {outfit}. "
    "High resolution, clean composition."
)

# Inline SVG fallback (monochrome silhouette)
_SVG_FALLBACK_B64 = base64.b64encode(
    b"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" width="200" height="200">
  <rect width="200" height="200" fill="#1a2233"/>
  <circle cx="100" cy="70" r="38" fill="#4a5568"/>
  <ellipse cx="100" cy="170" rx="60" ry="50" fill="#4a5568"/>
  <text x="100" y="198" text-anchor="middle" fill="#8b949e" font-size="11" font-family="sans-serif">Lily</text>
</svg>"""
).decode("ascii")


def _today_cache_path() -> Path:
    """Return the expected cache path for today's portrait."""
    return _IMAGE_CACHE_DIR / f"lily_portrait_{date.today().isoformat()}.png"


def _prune_old_portraits() -> None:
    """Keep only the _MAX_CACHED_PORTRAITS most recent portrait files."""
    portraits = sorted(_IMAGE_CACHE_DIR.glob("lily_portrait_*.png"), reverse=True)
    for old in portraits[_MAX_CACHED_PORTRAITS:]:
        try:
            old.unlink()
        except OSError:
            pass


def _build_prompt() -> tuple[str, str | None]:
    """Build the portrait prompt, preferring the DB active row.

    Returns
    -------
    tuple[str, str | None]
        (positive_prompt, negative_prompt).  negative_prompt may be None.
        If the DB is unavailable or has no active row, falls back to the
        _BASE_PROMPT + outfit rotation logic; negative_prompt is None in
        that case.
    """
    # --- Attempt DB load -------------------------------------------------
    try:
        import importlib.util as _ilu
        import sys as _sys
        _db_mod_key = "_lily_config_db"
        if _db_mod_key not in _sys.modules:
            _db_path = Path(__file__).resolve().parent / "lily_config_db.py"
            _spec = _ilu.spec_from_file_location(_db_mod_key, _db_path)
            if _spec and _spec.loader:
                _mod = _ilu.module_from_spec(_spec)
                _sys.modules[_db_mod_key] = _mod
                _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
        _db_mod = _sys.modules.get(_db_mod_key)
        if _db_mod is not None:
            positive, negative = _db_mod.get_active_prompt()
            return positive, negative
    except Exception:  # nosec B110
        pass

    # --- Fallback: outfit rotation ---------------------------------------
    weekday = datetime.today().isoweekday()  # 1=Mon … 7=Sun
    outfit = _OUTFIT_DESCRIPTORS[(weekday - 1) % len(_OUTFIT_DESCRIPTORS)]
    return _BASE_PROMPT.format(outfit=outfit), None


def _svg_fallback_path() -> Path:
    """Write inline SVG to a dated .svg file and return its path."""
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    svg_path = _IMAGE_CACHE_DIR / f"lily_portrait_{today}.svg"
    svg_data = base64.b64decode(_SVG_FALLBACK_B64)
    svg_path.write_bytes(svg_data)
    return svg_path


def get_daily_portrait() -> Path:
    """Return the path to today's Lily portrait.

    Generation cascade:
    1. Return the cached PNG if already generated today.
    2. Use the shared Workspace portrait cascade with Lily's SVG fallback.

    Returns
    -------
    Path
        Absolute path to the portrait file. Never raises.
    """
    _IMAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Cache hit
    today_path = _today_cache_path()
    if today_path.exists():
        return today_path

    positive_prompt, negative_prompt = _build_prompt()
    save_dir = _IMAGE_CACHE_DIR

    persona_svg = _svg_fallback_path()
    try:
        result = _workspace_portrait_cascade(persona_svg).generate(
            positive_prompt,
            output_dir=save_dir,
            negative_prompt=negative_prompt,
        )
        generated_path = result.path
    except Exception:
        return persona_svg

    if generated_path.suffix.lower() == ".svg":
        return generated_path if generated_path.is_file() else persona_svg
    if not generated_path.exists():
        return persona_svg

    try:
        if generated_path != today_path:
            generated_path.rename(today_path)
    except (FileExistsError, PermissionError):
        if not today_path.exists():
            return persona_svg

    if today_path.exists():
        _prune_old_portraits()
        try:
            persona_svg.unlink()
        except OSError:
            pass
        return today_path
    return persona_svg


def get_portrait_img_tag(max_width: int = 160) -> str:
    """Return an ``<img>`` HTML tag for the Lily portrait.

    Uses a data-URI so the HTML file is self-contained.  Falls back to an
    inline SVG data-URI if the portrait is an SVG silhouette.

    Parameters
    ----------
    max_width:
        CSS max-width in pixels. Default: 160.
    """
    portrait_path = get_daily_portrait()
    suffix = portrait_path.suffix.lower()

    if suffix == ".png":
        mime = "image/png"
        data = base64.b64encode(portrait_path.read_bytes()).decode("ascii")
        src = f"data:{mime};base64,{data}"
    elif suffix == ".svg":
        # SVG fallback — encode as SVG data-URI
        src = f"data:image/svg+xml;base64,{_SVG_FALLBACK_B64}"
    else:
        # Unknown — use fallback SVG
        src = f"data:image/svg+xml;base64,{_SVG_FALLBACK_B64}"

    return (
        f'<img src="{src}" alt="Lily — Executive Brief Host" '
        f'style="max-width:{max_width}px; width:{max_width}px; height:{max_width}px; '
        f'object-fit:cover; border-radius:12px; '
        f'border:2px solid rgba(88,166,255,0.4); display:block; margin:0 auto;" '
        f'title="Lily · Generated {date.today().isoformat()}" />'
    )
