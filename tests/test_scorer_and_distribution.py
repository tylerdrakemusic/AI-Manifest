"""Tests for scorer Ollama path wiring and distribution reporting.

All external calls are mocked — no Ollama server or OpenAI key needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Scorer Ollama path wiring
# ---------------------------------------------------------------------------

_SCORER_MODULE = "src.utils.priority_scorer"
_CLIENT_IN_SCORER = f"{_SCORER_MODULE}.OllamaClient"


class TestScorerOllamaPath:
    def test_uses_ollama_client_for_generate(self) -> None:
        """_score_via_ollama must call OllamaClient().generate, not raw urllib."""
        from src.utils.priority_scorer import _score_via_ollama

        mock_client = MagicMock()
        mock_client.list_models.return_value = [{"name": "test-model"}]
        mock_client.generate.return_value = "8"

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            result = _score_via_ollama("Fix CI pipeline", "workspace", [])

        assert result == 8
        mock_client.generate.assert_called_once()
        assert mock_client.generate.call_args.kwargs["model"] == "test-model"

    def test_raises_on_unparseable_response(self) -> None:
        from src.utils.priority_scorer import _score_via_ollama

        mock_client = MagicMock()
        mock_client.list_models.return_value = [{"name": "test-model"}]
        mock_client.generate.return_value = "not a number"

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            with pytest.raises(ValueError, match="unparseable response"):
                _score_via_ollama("some task", "life", [])

    def test_prefers_any_installed_model_when_configured_model_missing(self) -> None:
        from src.utils.priority_scorer import _score_via_ollama

        mock_client = MagicMock()
        mock_client.list_models.return_value = [{"name": "qwen2:0.5b"}]
        mock_client.generate.return_value = "7"

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            result = _score_via_ollama("Rate this task", "workspace", [])

        assert result == 7
        assert mock_client.generate.call_args.kwargs["model"] == "qwen2:0.5b"

    def test_score_priority_falls_back_to_openai_when_ollama_fails(self) -> None:
        """score_priority() must try Ollama, then fall back to OpenAI."""
        from src.utils.priority_scorer import score_priority

        mock_client = MagicMock()
        mock_client.list_models.return_value = [{"name": "test-model"}]
        mock_client.generate.side_effect = RuntimeError("connection refused")

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            with patch(f"{_SCORER_MODULE}._score_via_openai", return_value=6) as mock_openai:
                result = score_priority("Refactor auth module", "manifest")

        assert result == 6
        mock_openai.assert_called_once()

    def test_score_priority_uses_heuristic_when_both_fail(self) -> None:
        from src.utils.priority_scorer import score_priority

        mock_client = MagicMock()
        mock_client.generate.side_effect = RuntimeError("offline")
        mock_client.list_models.return_value = [{"name": "qwen2:0.5b"}]

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            with patch(f"{_SCORER_MODULE}._score_via_openai", side_effect=RuntimeError("no key")):
                result = score_priority("some task", "workspace")

        assert result == 4

    def test_score_priority_uses_heuristic_fallback_when_both_llms_fail(self) -> None:
        from src.utils.priority_scorer import _heuristic_priority, score_priority

        mock_client = MagicMock()
        mock_client.list_models.return_value = [{"name": "qwen2:0.5b"}]
        mock_client.generate.side_effect = RuntimeError("offline")

        task = "some task"

        with patch(_CLIENT_IN_SCORER, return_value=mock_client):
            with patch(f"{_SCORER_MODULE}._score_via_openai", side_effect=RuntimeError("no key")):
                result = score_priority(task, "quantum")

        assert result == _heuristic_priority(task, "quantum")
        assert result == 4

    def test_score_priority_uses_ollama_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OllamaClient constructed inside scorer must respect env var overrides."""
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://custom:9999")
        monkeypatch.setenv("OLLAMA_MODEL", "phi3:mini")

        captured: list[dict] = []

        def fake_client_factory(base_url=None, model=None):  # type: ignore[override]
            c = MagicMock()
            c.list_models.return_value = [{"name": "phi3:mini"}]
            c.generate.return_value = "7"
            # OllamaClient reads env in __init__, so capture init args here
            # (we just verify the scorer doesn't hard-code base_url/model)
            captured.append({"base_url": base_url, "model": model})
            return c

        with patch(_CLIENT_IN_SCORER, side_effect=fake_client_factory):
            from src.utils.priority_scorer import _score_via_ollama
            result = _score_via_ollama("task", "quantum", [])

        assert result == 7
        # Constructor called with no hard-coded args → env vars take effect
        assert captured[0]["base_url"] is None
        assert captured[0]["model"] is None


# ---------------------------------------------------------------------------
# Distribution report helpers in bulk_score_todos
# ---------------------------------------------------------------------------


class TestDistributionReport:
    def _make_preview_rows(self, old_new_pairs: list[tuple[int, int]]) -> list[dict]:
        return [
            {
                "id": i + 1,
                "project": "test",
                "text": f"todo {i}",
                "old_priority": old,
                "new_priority": new,
                "changed": old != new,
            }
            for i, (old, new) in enumerate(old_new_pairs)
        ]

    def test_priority_bucket_mapping(self) -> None:
        from tools.bulk_score_todos import _priority_bucket

        assert _priority_bucket(10) == "critical (9-10)"
        assert _priority_bucket(9) == "critical (9-10)"
        assert _priority_bucket(8) == "high (7-8)"
        assert _priority_bucket(7) == "high (7-8)"
        assert _priority_bucket(6) == "medium (4-6)"
        assert _priority_bucket(4) == "medium (4-6)"
        assert _priority_bucket(3) == "low (1-3)"
        assert _priority_bucket(1) == "low (1-3)"

    def test_distribution_counts(self) -> None:
        from tools.bulk_score_todos import _distribution

        priorities = [1, 2, 4, 5, 7, 8, 9, 10]
        dist = _distribution(priorities)
        assert dist["low (1-3)"] == 2
        assert dist["medium (4-6)"] == 2
        assert dist["high (7-8)"] == 2
        assert dist["critical (9-10)"] == 2

    def test_print_distribution_report_no_output_when_empty(self, capsys) -> None:
        from tools.bulk_score_todos import _print_distribution_report

        _print_distribution_report([])
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_print_distribution_report_shows_before_after(self, capsys) -> None:
        from tools.bulk_score_todos import _print_distribution_report

        rows = self._make_preview_rows([(5, 9), (3, 7), (6, 2)])
        _print_distribution_report(rows)
        captured = capsys.readouterr()
        assert "Before" in captured.out
        assert "After" in captured.out
        assert "critical" in captured.out
        assert "low" in captured.out

    def test_distribution_report_integrated_in_dry_run(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch, capsys
    ) -> None:
        """dry-run path must include distribution report in output."""
        import sys

        # Patch get_open_todos to return synthetic rows
        fake_todos = [
            {"id": 1, "project": "test", "text": "Task A", "priority": 5, "done": 0},
            {"id": 2, "project": "test", "text": "Task B", "priority": 3, "done": 0},
        ]

        with (
            patch("tools.bulk_score_todos.get_open_todos", return_value=fake_todos),
            patch("tools.bulk_score_todos.update_priority"),
            patch("tools.bulk_score_todos._detect_backends", return_value=(True, False)),
            patch("tools.bulk_score_todos.score_priority", side_effect=[8, 9]),
        ):
            monkeypatch.setattr(sys, "argv", ["bulk_score_todos.py"])
            from tools.bulk_score_todos import main

            exit_code = main()

        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Proposed priority distribution" in captured.out
        assert "Before" in captured.out
        assert "DRY-RUN" in captured.out
