import pytest

from src.utils.priority_scorer import score_priority


def test_score_priority_rejects_ignored_existing_todos_argument() -> None:
    with pytest.raises(TypeError):
        score_priority("Ship the security integration", "workspace", existing_todos=[])