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
import importlib
import os
import shutil
import sys
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

class ImageProviderAdapter(Protocol):
    """AI-Manifest boundary for Workspace-owned image providers."""

    def generate_dalle3(self, prompt: str, save_dir: Path) -> Path:
        ...

    def generate_huggingface(
        self, prompt: str, save_dir: Path, negative_prompt: str | None = None
    ) -> Path:
        ...

    def generate_hf_spaces(self, prompt: str, save_dir: Path) -> Path:
        ...

    def generate_pollinations(self, prompt: str, save_dir: Path) -> Path:
        ...


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


def _workspace_client(module_name: str, class_name: str) -> Any:
    """Resolve a Workspace client through Python's normal import system."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        workspace_src = _workspace_src_path()
        if str(workspace_src) not in sys.path:
            sys.path.insert(0, str(workspace_src))
        module = importlib.import_module(module_name)
    return getattr(module, class_name)()


class WorkspaceImageProviderAdapter:
    """Delegate portrait generation to clients owned by ⊕Workspace.

    Factories are injectable so AI-Manifest tests and callers can provide
    provider implementations without importing or contacting external APIs.
    """

    def __init__(
        self,
        dalle3_factory: Callable[[], Any] | None = None,
        huggingface_factory: Callable[[], Any] | None = None,
        hf_spaces_factory: Callable[[], Any] | None = None,
        pollinations_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._factories = (
            dalle3_factory
            or (lambda: _workspace_client("integrations.dalle3.client", "DallE3Client")),
            huggingface_factory
            or (lambda: _workspace_client("integrations.huggingface.client", "HuggingFaceImageClient")),
            hf_spaces_factory
            or (lambda: _workspace_client("integrations.huggingface.spaces_client", "HFSpacesImageClient")),
            pollinations_factory
            or (lambda: _workspace_client("integrations.pollinations.client", "PollinationsClient")),
        )

    def _generate(self, index: int, prompt: str, save_dir: Path, **kwargs: Any) -> Path:
        client = self._factories[index]()
        return client.generate_image(prompt, output_dir=save_dir, **kwargs)

    def generate_dalle3(self, prompt: str, save_dir: Path) -> Path:
        return self._generate(0, prompt, save_dir, size="1024x1024")

    def generate_huggingface(
        self, prompt: str, save_dir: Path, negative_prompt: str | None = None
    ) -> Path:
        return self._generate(
            1, prompt, save_dir, size="1024x1024", negative_prompt=negative_prompt
        )

    def generate_hf_spaces(self, prompt: str, save_dir: Path) -> Path:
        return self._generate(2, prompt, save_dir, width=1024, height=1024)

    def generate_pollinations(self, prompt: str, save_dir: Path) -> Path:
        return self._generate(3, prompt, save_dir, width=1024, height=1024)


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


def _try_dalle3(
    prompt: str, save_dir: Path, provider_adapter: ImageProviderAdapter | None = None
) -> Path | None:
    """Attempt to generate the portrait via DALL-E 3. Returns Path or None."""
    try:
        adapter = provider_adapter or WorkspaceImageProviderAdapter()
        return adapter.generate_dalle3(prompt, save_dir)
    except Exception:
        return None


def _try_huggingface(
    prompt: str,
    save_dir: Path,
    negative_prompt: str | None = None,
    provider_adapter: ImageProviderAdapter | None = None,
) -> Path | None:
    """Attempt to generate the portrait via HuggingFace Inference. Returns Path or None."""
    try:
        adapter = provider_adapter or WorkspaceImageProviderAdapter()
        return adapter.generate_huggingface(prompt, save_dir, negative_prompt)
    except Exception:
        return None


def _try_hf_spaces(
    prompt: str, save_dir: Path, provider_adapter: ImageProviderAdapter | None = None
) -> Path | None:
    """Attempt to generate via HF Spaces FLUX.1-schnell (ZeroGPU). Returns Path or None."""
    try:
        adapter = provider_adapter or WorkspaceImageProviderAdapter()
        return adapter.generate_hf_spaces(prompt, save_dir)
    except Exception:
        return None


def _try_pollinations(
    prompt: str, save_dir: Path, provider_adapter: ImageProviderAdapter | None = None
) -> Path | None:
    """Attempt to generate the portrait via Pollinations.AI (free, no API key). Returns Path or None."""
    try:
        adapter = provider_adapter or WorkspaceImageProviderAdapter()
        return adapter.generate_pollinations(prompt, save_dir)
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


def get_daily_portrait(provider_adapter: ImageProviderAdapter | None = None) -> Path:
    """Return the path to today's Lily portrait.

    Generation cascade:
    1. Return cached portrait if already generated today.
    2. Try DALL-E 3 (requires ``OPENAPI_TOKEN``).
    3. Fall back to HuggingFace Inference API (requires ``HF_TOKEN`` with credits).
    4. Try HuggingFace Spaces FLUX.1-schnell (free, ZeroGPU quota).
    5. Try Pollinations.AI (free, photorealistic, no API key required).
    6. Fall back to inline SVG silhouette (always succeeds).

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

    # 2. DALL-E 3
    result = (
        _try_dalle3(positive_prompt, save_dir, provider_adapter)
        if provider_adapter is not None
        else _try_dalle3(positive_prompt, save_dir)
    )
    if result and result.exists():
        result.rename(today_path)
        _prune_old_portraits()
        return today_path

    # 3. HuggingFace Inference API (requires HF_TOKEN with credits)
    result = (
        _try_huggingface(
            positive_prompt,
            save_dir,
            negative_prompt=negative_prompt,
            provider_adapter=provider_adapter,
        )
        if provider_adapter is not None
        else _try_huggingface(positive_prompt, save_dir, negative_prompt=negative_prompt)
    )
    if result and result.exists():
        result.rename(today_path)
        _prune_old_portraits()
        return today_path

    # 4. HuggingFace Spaces FLUX.1-schnell (free, ZeroGPU quota)
    result = (
        _try_hf_spaces(positive_prompt, save_dir, provider_adapter)
        if provider_adapter is not None
        else _try_hf_spaces(positive_prompt, save_dir)
    )
    if result and result.exists():
        result.rename(today_path)
        _prune_old_portraits()
        return today_path

    # 5. Pollinations.AI (free, photorealistic, no API key)
    result = (
        _try_pollinations(positive_prompt, save_dir, provider_adapter)
        if provider_adapter is not None
        else _try_pollinations(positive_prompt, save_dir)
    )
    if result and result.exists():
        try:
            result.rename(today_path)
        except FileExistsError:
            if today_path.exists():
                return today_path
            raise
        except PermissionError:
            if today_path.exists():
                return today_path
            fallback = _svg_fallback_path()
            return fallback
        _prune_old_portraits()
        return today_path

    # 6. SVG silhouette fallback (always works)
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
        f'style="max-width:{max_width}px; width:{max_width}px; height:{max_width}px; '
        f'object-fit:cover; border-radius:12px; '
        f'border:2px solid rgba(88,166,255,0.4); display:block; margin:0 auto;" '
        f'title="Lily · Generated {date.today().isoformat()}" />'
    )
