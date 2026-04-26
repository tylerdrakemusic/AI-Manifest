"""Lily portrait generator — daily cached AI-generated portrait for the executive brief.

Generates a headshot portrait of "Lily" (the executive brief voice persona) using
DALL-E 3 → HuggingFace fallback → SVG silhouette fallback.

The portrait is cached by calendar date so it is generated at most once per day.
Up to 3 daily cached images are kept; older ones are pruned.

Usage::

    from src.utils.lily_portrait import get_daily_portrait

    path = get_daily_portrait()  # Path to cached PNG (or SVG fallback stub)
    # path is always valid — never raises
"""

from __future__ import annotations

import base64
import sys
from datetime import date, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Workspace integration path bootstrap
# ---------------------------------------------------------------------------
_WORKSPACE_ROOT = Path(r"f:\⊕Workspace")
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IMAGE_CACHE_DIR = _PROJECT_ROOT / "output" / "images"
_MAX_CACHED_PORTRAITS = 3

# ---------------------------------------------------------------------------
# Outfit rotation — 7 descriptors cycling by ISO weekday (1=Mon … 7=Sun)
# ---------------------------------------------------------------------------
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
    today = date.today().isoformat()
    return _IMAGE_CACHE_DIR / f"lily_portrait_{today}.png"


def _prune_old_portraits() -> None:
    """Keep only the _MAX_CACHED_PORTRAITS most recent portrait files."""
    portraits = sorted(_IMAGE_CACHE_DIR.glob("lily_portrait_*.png"), reverse=True)
    for old in portraits[_MAX_CACHED_PORTRAITS:]:
        try:
            old.unlink()
        except OSError:
            pass


def _build_prompt() -> str:
    """Build today's portrait prompt with the daily outfit descriptor."""
    weekday = datetime.today().isoweekday()  # 1=Mon … 7=Sun
    outfit = _OUTFIT_DESCRIPTORS[(weekday - 1) % len(_OUTFIT_DESCRIPTORS)]
    return _BASE_PROMPT.format(outfit=outfit)


def _try_dalle3(prompt: str, save_dir: Path) -> Path | None:
    """Attempt to generate the portrait via DALL-E 3. Returns Path or None."""
    try:
        from src.integrations.dalle3 import DallE3Client, DallE3Error  # type: ignore[import]

        client = DallE3Client()
        path = client.generate_image(prompt, output_dir=save_dir, size="1024x1024")
        return path
    except Exception:
        return None


def _try_huggingface(prompt: str, save_dir: Path) -> Path | None:
    """Attempt to generate the portrait via HuggingFace Inference. Returns Path or None."""
    try:
        from src.integrations.huggingface import HuggingFaceImageClient, HuggingFaceImageError  # type: ignore[import]

        client = HuggingFaceImageClient()
        path = client.generate_image(prompt, output_dir=save_dir, size="1024x1024")
        return path
    except Exception:
        return None


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
    1. Return cached portrait if already generated today.
    2. Try DALL-E 3 (requires ``OPENAPI_TOKEN``).
    3. Fall back to HuggingFace Inference (requires ``HF_TOKEN``).
    4. Fall back to inline SVG silhouette (always succeeds).

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

    prompt = _build_prompt()
    save_dir = _IMAGE_CACHE_DIR

    # 2. DALL-E 3
    result = _try_dalle3(prompt, save_dir)
    if result and result.exists():
        # Rename to canonical dated name so cache check works on re-entry
        result.rename(today_path)
        _prune_old_portraits()
        return today_path

    # 3. HuggingFace
    result = _try_huggingface(prompt, save_dir)
    if result and result.exists():
        result.rename(today_path)
        _prune_old_portraits()
        return today_path

    # 4. SVG silhouette fallback (always works)
    return _svg_fallback_path()


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
        f'style="max-width:{max_width}px; border-radius:50%; '
        f'border:2px solid rgba(88,166,255,0.4); display:block; margin:0 auto;" '
        f'title="Lily · Generated {date.today().isoformat()}" />'
    )
