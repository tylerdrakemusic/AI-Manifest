"""Seed lily_config.db with the initial active Lily portrait prompt.

Idempotent — skips insertion if an active row already exists.

Usage::

    C:\\G\\python.exe tools/lily/seed_lily_config.py
"""

from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolve DB path relative to project root
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DB_PATH = _PROJECT_ROOT / "src" / "data" / "lily_config.db"

# ---------------------------------------------------------------------------
# Prompt content (self-contained — no outfit rotation appended)
# ---------------------------------------------------------------------------
_POSITIVE_PROMPT = (
    "a facial portrait of a stunning fit gorgeous 43 year old business executive woman, "
    "sharply professionally and stylish tailored dressed, "
    "telepathically injecting your mind and character with phenomenally positive creative energy "
    "and confidence for your \u2295Workspace \u2764Music \u221eLife \u27e8\u03c8\u27e9Quantum projects, "
    "the base64 encoded communication flows through you an abundance, faith, honor, charisma and trust, "
    "she admires you, believes in you, fully supports your visions, and loves you in a healthy professional manner\n"
    "An ultra-realistic RAW photo captured on a Canon EOS 5D Mark IV with a Canon EF 50mm f/1.8 STM lens. "
    "Shot at f/1.8, 1/125s, ISO 100. Soft natural ambient lighting with subtle rim light, "
    "daylight white balance 5500K. Extremely shallow depth of field, sharp subject focus with smooth background bokeh. "
    "High-resolution digital capture with minimal processing, subtle natural sensor noise, "
    "authentic lens characteristics including soft vignetting and slight chromatic aberration on high-contrast edges. "
    "Neutral color profile preserving true-to-life tones, perfectly composed using the rule of thirds. "
    "sharp|soft focus, depth of field, 8k photo, HDR, professional lighting, taken with Canon EOS R5, DSLR, 75mm lens"
)

_NEGATIVE_PROMPT = (
    "illustration, painting, drawing, sketch, anime, manga, 3D render, CGI, V-Ray, Unreal Engine, "
    "Octane render, digital art, concept art, matte painting, fantasy, sci-fi, surreal, supernatural, "
    "ugly, deformed, mutated, disfigured, poorly drawn hands, extra limbs, missing limbs, painterly, "
    "watercolor, oil painting, impressionistic, abstract, HDR, over-saturated, vibrant colors, "
    "unnatural colors, high contrast, garish, loud, glamour photography, airbrushed, smoothed skin, "
    "plastic skin, perfect skin, blurry, motion blur, out of focus, text, watermark, signature, logo, "
    "username, artist name, jpeg artifacts, compression artifacts, banding, pixelated, weird, bizarre, "
    "grotesque, unsettling"
)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lily_prompts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    positive_prompt TEXT    NOT NULL,
    negative_prompt TEXT,
    updated_at      TEXT    NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1
);
"""


def seed() -> None:
    """Create and seed lily_config.db (idempotent)."""
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(_DB_PATH))
    try:
        conn.execute(_CREATE_TABLE_SQL)
        conn.commit()

        # Check if an active row already exists
        row = conn.execute(
            "SELECT id FROM lily_prompts WHERE is_active = 1 LIMIT 1"
        ).fetchone()

        if row is not None:
            print(f"[seed] Active row already exists (id={row[0]}). Skipping insert.")
        else:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO lily_prompts (positive_prompt, negative_prompt, updated_at, is_active) "
                "VALUES (?, ?, ?, 1)",
                (_POSITIVE_PROMPT, _NEGATIVE_PROMPT, now),
            )
            conn.commit()
            print(f"[seed] Inserted active prompt row into {_DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
    print("[seed] Done.")
    sys.exit(0)
