from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.integrations.elevenlabs import mcp_server


def test_play_audio_file_plays_governed_mp3_synchronously(tmp_path: Path) -> None:
    audio_path = tmp_path / "brief.mp3"
    audio_path.write_bytes(b"ID3 audio")
    commands: list[str] = []

    def fake_mci(command: str, *_args: object) -> int:
        commands.append(command)
        return 0

    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server, "IS_WINDOWS_PLATFORM", True
    ), patch.object(mcp_server, "get_audio_duration_seconds", return_value=2.0), patch.object(
        mcp_server.ctypes,
        "windll",
        Mock(winmm=Mock(mciSendStringW=fake_mci)),
        create=True,
    ):
        result = mcp_server.play_audio_file("brief.mp3")

    assert result["status"] == "completed"
    assert result["filename"] == "brief.mp3"
    assert any(command.startswith("play ") and command.endswith(" wait") for command in commands)
    assert any(command.startswith("close ") for command in commands)


def test_play_audio_file_is_registered_as_an_mcp_tool() -> None:
    registered_tools = mcp_server.mcp._tool_manager._tools

    assert "play_audio_file" in registered_tools


@pytest.mark.parametrize(
    "filename",
    [
        "../escape.mp3",
        "nested/brief.mp3",
        r"nested\brief.mp3",
        "brief.wav",
        "",
        "brief.exe",
        "missing.mp3",
    ],
)
def test_play_audio_file_rejects_unsafe_or_unsupported_names(
    tmp_path: Path, filename: str
) -> None:
    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server, "play_audio_path"
    ) as playback:
        with pytest.raises((ValueError, FileNotFoundError)):
            mcp_server.play_audio_file(filename)

    playback.assert_not_called()


def test_play_audio_file_rejects_absolute_name(tmp_path: Path) -> None:
    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server, "play_audio_path"
    ) as playback:
        with pytest.raises(ValueError):
            mcp_server.play_audio_file(str(tmp_path / "brief.mp3"))

    playback.assert_not_called()


def test_native_playback_rejects_non_windows_platform(tmp_path: Path) -> None:
    with patch.object(mcp_server, "IS_WINDOWS_PLATFORM", False):
        with pytest.raises(OSError, match="Windows"):
            mcp_server.play_audio_path(tmp_path / "brief.mp3")


def test_native_playback_closes_alias_when_play_fails(tmp_path: Path) -> None:
    commands: list[str] = []

    def failing_mci(command: str, *_args: object) -> int:
        commands.append(command)
        return int(command.startswith("play "))

    with patch.object(mcp_server, "IS_WINDOWS_PLATFORM", True), patch.object(
        mcp_server.ctypes,
        "windll",
        Mock(winmm=Mock(mciSendStringW=failing_mci)),
        create=True,
    ):
        with pytest.raises(OSError, match="playback"):
            mcp_server.play_audio_path(tmp_path / "brief.mp3")

    assert commands[0].startswith("open ")
    assert commands[1].endswith(" wait")
    assert commands[2].startswith("close ")


def test_play_audio_file_rejects_oversized_or_excessively_long_audio(
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "brief.mp3"
    audio_path.write_bytes(b"audio")

    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server, "MAX_AUDIO_FILE_BYTES", 4
    ):
        with pytest.raises(ValueError, match="size"):
            mcp_server.play_audio_file("brief.mp3")

    with patch.object(mcp_server, "OUTPUT_DIR", tmp_path), patch.object(
        mcp_server, "get_audio_duration_seconds", return_value=121.0
    ), patch.object(mcp_server, "MAX_AUDIO_DURATION_SECONDS", 120.0):
        with pytest.raises(ValueError, match="duration"):
            mcp_server.play_audio_file("brief.mp3")