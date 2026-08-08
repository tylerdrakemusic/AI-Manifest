"""Tests for the deterministic priority scorer and distribution reporting."""

from __future__ import annotations

from unittest.mock import patch

import pytest

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
