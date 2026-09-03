"""Backward-compatible aliases for the repository-voice boundary."""

from src.services.governed_repository_voice import (
    RepositoryVoiceSubmissionResult,
    submit_repository_voice,
)

AlertSubmissionResult = RepositoryVoiceSubmissionResult
submit_alert = submit_repository_voice