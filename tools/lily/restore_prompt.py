"""Restore Tyler's original Lily prompt."""
import sqlite3
import pathlib

db = pathlib.Path(__file__).resolve().parent.parent.parent / "src" / "data" / "lily_config.db"
prompt = (
    "masterpiece, best quality, highly detailed, sharp focus, 8k UHD, "
    "a facial portrait of a stunning fit gorgeous sexy 43 year old business executive woman, "
    "sharply professionally and stylish tailored dressed, telepathically injecting your mind "
    "and character with phenomenally positive creative energy and confidence, "
    "(professional executive assistant Lily), (sharp facial profile), "
    "(shoulder-length vibrant 5th element ginger hair in soft waves), "
    "(fair skin with prominent freckles distinguished beauty marks), "
    "(golden hue blue eyes), photorealistic, cinematic lighting, studio portrait"
)
with sqlite3.connect(db) as c:
    cur = c.execute(
        "UPDATE lily_prompts SET positive_prompt=?, updated_at=datetime('now') WHERE is_active=1",
        (prompt,)
    )
    print(f"Updated {cur.rowcount} row(s)")
    row = c.execute("SELECT positive_prompt FROM lily_prompts WHERE is_active=1").fetchone()
    print("Active prompt:", row[0][:100] if row else "MISSING")
