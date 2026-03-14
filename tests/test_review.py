"""Tests for review page and relaunch endpoint."""
import hmac
import hashlib
import json
import pytest
from uuid import uuid4

from tests.conftest import MINIMAL_ENV
from app.models import (
    SheetsRow, VideoGenerationRequest, VideoJob, ScriptAnalysis,
    ScriptSection, JobStatus,
)


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


def _make_job_with_analysis(job_id=None):
    """Helper: create a VideoJob with script_analysis populated."""
    jid = job_id or uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(
            row_id="2", script="A" * 50, voice_id="v1",
            format="vertical", strategy="B", duration=60,
        ),
        webhook_url="https://example.com/webhook",
    )
    job = VideoJob(job_id=jid, row_id="2", request=req)
    job.script_analysis = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="Voix off un", start=0, end=5, duration=5,
                          broll_prompt="A woman walking in a park at sunset",
                          keywords=["woman", "park", "sunset"], scene_type="emotion"),
            ScriptSection(id=2, text="Voix off deux", start=5, end=10, duration=5,
                          broll_prompt="Close-up hands typing on laptop",
                          keywords=["hands", "laptop", "typing"], scene_type="ambient"),
        ],
        source="claude",
    )
    return job


def test_review_page_returns_html(env_vars):
    """GET /review/{job_id} returns HTML when job has script_analysis."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    job = _make_job_with_analysis()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.get(f"/review/{job.job_id}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "woman walking" in resp.text
        assert "Voix off un" in resp.text


def test_review_page_job_not_found(env_vars):
    """GET /review/{job_id} returns 404 for unknown job."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    with TestClient(app) as client:
        resp = client.get(f"/review/{uuid4()}")
        assert resp.status_code == 404


def test_review_page_waiting(env_vars):
    """GET /review/{job_id} returns waiting page when script_analysis not ready."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)

    jid = uuid4()
    req = VideoGenerationRequest(
        job_id=jid,
        sheets_row=SheetsRow(row_id="2", script="A" * 50, voice_id="v1"),
    )
    job = VideoJob(job_id=jid, row_id="2", request=req)
    # script_analysis is None

    with TestClient(app) as client:
        app.state.jobs[jid] = job
        resp = client.get(f"/review/{jid}")
        assert resp.status_code == 200
        assert "Analyse en cours" in resp.text


def test_relaunch_creates_new_job(env_vars):
    """POST /review/{job_id}/relaunch creates a new job with modified prompts."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient
    from unittest.mock import patch, AsyncMock

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    # Generate valid HMAC token
    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job

        with patch("app.main.run_pipeline") as mock_run_pipeline:
            resp = client.post(
                f"/review/{job.job_id}/relaunch?token={token}",
                json={
                    "sections": [
                        {"id": 1, "broll_prompt": "Modified prompt one here",
                         "keywords": ["modified"], "scene_type": "emotion"},
                        {"id": 2, "broll_prompt": "Modified prompt two here",
                         "keywords": ["changed"], "scene_type": "ambient"},
                    ]
                },
            )

        assert resp.status_code == 201
        # Verify pipeline was launched
        mock_run_pipeline.assert_called_once()
        data = resp.json()
        assert "job_id" in data
        new_job_id = data["job_id"]
        assert new_job_id != str(job.job_id)

        # Verify new job exists with modified prompts
        from uuid import UUID
        new_job = app.state.jobs[UUID(new_job_id)]
        assert new_job.parent_job_id == job.job_id
        assert new_job.script_analysis.source == "review"
        assert new_job.script_analysis.original_source == "claude"
        assert new_job.script_analysis.sections[0].broll_prompt == "Modified prompt one here"
        # Original text preserved
        assert new_job.script_analysis.sections[0].text == "Voix off un"


def test_relaunch_invalid_token(env_vars):
    """POST with invalid HMAC token returns 403."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token=invalid",
            json={"sections": [
                {"id": 1, "broll_prompt": "test prompt modified", "keywords": ["t"], "scene_type": "ambient"},
                {"id": 2, "broll_prompt": "test prompt two mod", "keywords": ["t"], "scene_type": "ambient"},
            ]},
        )
        assert resp.status_code == 403


def test_relaunch_max_count(env_vars):
    """POST relaunch beyond max 2 returns 429."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()
    job.relaunch_count = 2  # Already at max

    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token={token}",
            json={"sections": [
                {"id": 1, "broll_prompt": "test prompt modified", "keywords": ["t"], "scene_type": "ambient"},
                {"id": 2, "broll_prompt": "test prompt two mod", "keywords": ["t"], "scene_type": "ambient"},
            ]},
        )
        assert resp.status_code == 429


def test_relaunch_empty_sections_rejected(env_vars):
    """POST with empty sections list returns 422 (min_length=1)."""
    from app.main import create_app
    from app.config import get_settings
    from starlette.testclient import TestClient

    settings = get_settings()
    app = create_app(settings)
    job = _make_job_with_analysis()

    token = hmac.new(
        settings.api_secret_key.encode(),
        str(job.job_id).encode(),
        hashlib.sha256,
    ).hexdigest()

    with TestClient(app) as client:
        app.state.jobs[job.job_id] = job
        resp = client.post(
            f"/review/{job.job_id}/relaunch?token={token}",
            json={"sections": []},
        )
        assert resp.status_code == 422
