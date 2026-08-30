"""Regression tests for MCP audio artifact path boundaries."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.integrations.elevenlabs import mcp_server


@pytest.mark.parametrize(
    "filename",
    ["../escape.mp3", "nested/name.mp3", r"nested\name.mp3", "", "bad\n.mp3", "bad\x00.mp3", "audio.wav"],
)
def test_mcp_rejects_unsafe_or_disallowed_output_filename(
    tmp_path: Path, filename: str
) -> None:
    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server.httpx, "post"
    ) as post:
        with pytest.raises(ValueError):
            mcp_server.text_to_speech("hello", output_filename=filename)

    post.assert_not_called()
    assert list(tmp_path.iterdir()) == []


def test_mcp_rejects_absolute_output_filename(tmp_path: Path) -> None:
    absolute_filename = str(tmp_path / "escape.mp3")

    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server.httpx, "post"
    ) as post:
        with pytest.raises(ValueError):
            mcp_server.text_to_speech("hello", output_filename=absolute_filename)

    post.assert_not_called()


def test_mcp_writes_valid_mp3_inside_output_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ELEVENLABS_API_KEY", "fake-key")
    response = MagicMock(content=b"ID3fake-audio")
    response.raise_for_status.return_value = None

    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server.httpx, "post", return_value=response
    ):
        result = json.loads(
            mcp_server.text_to_speech("hello", output_filename="session_take.mp3")
        )

    output_path = Path(result["path"]).resolve()
    assert output_path == (tmp_path / "session_take.mp3").resolve()
    assert output_path.is_relative_to(tmp_path.resolve())
    assert output_path.read_bytes() == b"ID3fake-audio"
    assert result["size_bytes"] == len(b"ID3fake-audio")