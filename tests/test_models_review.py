"""Tests for review-related model fields."""
import pytest
from uuid import uuid4

from app.models import ScriptAnalysis, ScriptSection, VideoJob, VideoGenerationRequest, SheetsRow, NotificationPayload, NotificationType


def test_script_analysis_source_review():
    """source accepts 'review' literal."""
    sa = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="T", start=0, end=5, duration=5,
                          broll_prompt="test prompt here for kling", keywords=["t"], scene_type="ambient"),
            ScriptSection(id=2, text="T2", start=5, end=10, duration=5,
                          broll_prompt="test prompt two for kling", keywords=["t"], scene_type="ambient"),
        ],
        source="review",
        original_source="claude",
    )
    assert sa.source == "review"
    assert sa.original_source == "claude"


def test_script_analysis_original_source_default_none():
    """original_source defaults to None."""
    sa = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="T", start=0, end=5, duration=5,
                          broll_prompt="test prompt here for kling", keywords=["t"], scene_type="ambient"),
            ScriptSection(id=2, text="T2", start=5, end=10, duration=5,
                          broll_prompt="test prompt two for kling", keywords=["t"], scene_type="ambient"),
        ],
    )
    assert sa.original_source is None


def test_video_job_parent_job_id_default():
    """parent_job_id defaults to None."""
    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req)
    assert job.parent_job_id is None
    assert job.relaunch_count == 0


def test_video_job_parent_job_id_set():
    """parent_job_id can be set to a UUID."""
    jid = uuid4()
    parent = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req, parent_job_id=parent, relaunch_count=1)
    assert job.parent_job_id == parent
    assert job.relaunch_count == 1


def test_video_job_review_url_default():
    """review_url defaults to None."""
    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="1", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="1", request=req)
    assert job.review_url is None


def test_notification_payload_review_url():
    """NotificationPayload accepts review_url."""
    payload = NotificationPayload(
        type=NotificationType.SUCCESS,
        job_id=uuid4(),
        row_id="1",
        message="Done",
        review_url="https://api.example.com/review/abc-123",
    )
    assert payload.review_url == "https://api.example.com/review/abc-123"
