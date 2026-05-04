"""Standalone Flask server exposing Lily prompt management endpoints.

Endpoints::

    GET  /lily/prompt          → JSON {"positive_prompt": "<current active>"}
    POST /lily/prompt          → JSON body {"positive_prompt": "..."} → 200 OK
    GET  /lily/portrait/regen  → deletes today's cache + calls get_daily_portrait()
                                 → JSON {"status": "ok", "path": "<new path>"}

Usage::

    C:\\G\\python.exe tools/lily/lily_prompt_server.py [--port 8201]

CORS: restricted to localhost origins only.

Note: When the main executive_audio_brief.py --serve is running on port 8200,
these same endpoints are available there without a separate process.  This
standalone server is for standalone / testing use only.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap — allow project-local imports
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from flask import Flask, jsonify, request, Response
except ImportError:
    print(
        "Flask is required. Install with: C:\\G\\python.exe -m pip install flask",
        file=sys.stderr,
    )
    sys.exit(1)

from src.utils.lily_config_db import get_active_prompt, update_active_prompt
from src.utils.lily_portrait import _today_cache_path, _IMAGE_CACHE_DIR, get_daily_portrait

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(__name__)

_ALLOWED_ORIGINS = {"http://127.0.0.1", "http://localhost"}


def _cors_headers(response: Response) -> Response:
    """Restrict CORS to localhost origins."""
    origin = request.headers.get("Origin", "")
    # Strip port from origin for matching
    origin_base = origin.rsplit(":", 1)[0] if ":" in origin.replace("://", "--") else origin
    if origin_base in _ALLOWED_ORIGINS or origin in _ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response


app.after_request(_cors_headers)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route("/lily/prompt", methods=["GET", "OPTIONS"])
def get_prompt() -> Response:
    """Return the current active positive prompt."""
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        positive, _negative = get_active_prompt()
        return jsonify({"positive_prompt": positive})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/lily/prompt", methods=["POST"])
def post_prompt() -> Response:
    """Update the active positive prompt."""
    body = request.get_json(silent=True) or {}
    positive_prompt: str = body.get("positive_prompt", "").strip()
    if not positive_prompt:
        return jsonify({"error": "positive_prompt is required"}), 400
    try:
        update_active_prompt(positive_prompt)
        return jsonify({"ok": True})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/lily/portrait/regen", methods=["GET", "OPTIONS"])
def regen_portrait() -> Response:
    """Delete today's cached portrait and regenerate it."""
    if request.method == "OPTIONS":
        return Response(status=204)
    try:
        # Delete today's PNG cache
        today_path = _today_cache_path()
        if today_path.exists():
            today_path.unlink()
        # Delete today's SVG fallback if present
        today_iso = date.today().isoformat()
        svg_path = _IMAGE_CACHE_DIR / f"lily_portrait_{today_iso}.svg"
        if svg_path.exists():
            svg_path.unlink()
        # Regenerate
        new_path = get_daily_portrait()
        return jsonify({"status": "ok", "path": str(new_path)})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Lily Prompt Management Server")
    parser.add_argument("--port", type=int, default=8201, help="Port to listen on (default: 8201)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host (default: 127.0.0.1)")
    args = parser.parse_args()

    print(f"[lily-prompt-server] Listening on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
