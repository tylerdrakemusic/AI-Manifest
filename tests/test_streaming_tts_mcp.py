from __future__ import annotations

from unittest.mock import Mock, patch

from src.integrations.elevenlabs import mcp_server


def test_streaming_tools_are_registered() -> None:
    registered_tools = mcp_server.mcp._tool_manager._tools

    assert "start_streaming_tts" in registered_tools
    assert "streaming_tts_status" in registered_tools
    assert "cancel_streaming_tts" in registered_tools


def test_start_status_and_cancel_delegate_direct_inputs() -> None:
    service = Mock()
    service.start.return_value = {"session_id": "opaque"}
    service.status.return_value = {"session_id": "opaque", "state": "running"}
    service.cancel.return_value = {"session_id": "opaque", "state": "cancelled"}

    with patch.object(mcp_server, "STREAMING_TTS_SERVICE", service):
        assert mcp_server.start_streaming_tts("hello", "voice", "model") == {
            "session_id": "opaque"
        }
        assert mcp_server.streaming_tts_status("opaque")["state"] == "running"
        assert mcp_server.cancel_streaming_tts("opaque")["state"] == "cancelled"

    service.start.assert_called_once_with("hello", "voice", "model")
    service.status.assert_called_once_with("opaque")
    service.cancel.assert_called_once_with("opaque")