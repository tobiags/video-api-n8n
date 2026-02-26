"""
test_integration.py — Test du pipeline complet avec tous les modules mockés.

Couvre :
- Stratégie A : Claude → ElevenLabs → Kling → Creatomate (happy path)
- Stratégie B : Claude → ElevenLabs → select_library_clips → Creatomate (happy path)
- Timeout global : asyncio.TimeoutError → job.status == FAILED
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import MINIMAL_ENV


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


def _make_mock_analysis(section_count: int = 0, total_duration: int = 90) -> MagicMock:
    """Helper — ScriptAnalysis mock avec les attributs accédés par run_pipeline."""
    mock = MagicMock()
    mock.sections = []
    mock.section_count = section_count
    mock.total_duration = total_duration
    return mock


def _make_mock_el(audio_duration_ms: int = 90_000) -> MagicMock:
    """Helper — ElevenLabsResult mock."""
    mock = MagicMock()
    mock.audio_path = "/tmp/audio.mp3"
    mock.audio_duration_ms = audio_duration_ms
    # Simule la propriété calculée audio_duration_seconds
    mock.audio_duration_seconds = audio_duration_ms / 1000.0
    mock.timestamps = []
    return mock


def _make_mock_render() -> MagicMock:
    """Helper — CreatomateRenderResult mock."""
    mock = MagicMock()
    mock.render_id = "render-xyz"
    mock.video_url = "https://cdn.creatomate.com/final.mp4"
    mock.duration_seconds = 90.0
    return mock


# ──────────────────────────────────────────────────────────────────────────────
# Stratégie A — Kling pur
# ──────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_strategy_a(env_vars, tmp_path, monkeypatch):
    """Pipeline Stratégie A : Claude → ElevenLabs → Kling → Creatomate."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.models import JobStatus

    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))

    mock_analysis = _make_mock_analysis()
    mock_el = _make_mock_el()
    mock_clips: list = []
    mock_render = _make_mock_render()

    settings = Settings()

    with (
        patch("app.main.analyze_script", return_value=mock_analysis) as p_claude,
        patch("app.main.generate_voiceover", return_value=mock_el) as p_el,
        patch("app.main.generate_clips", return_value=mock_clips) as p_kling,
        patch("app.main.assemble_video", return_value=mock_render) as p_creat,
    ):
        with TestClient(create_app_fresh(settings)) as client:
            resp = client.post(
                "/generate",
                headers={"Authorization": f"Bearer {settings.api_secret_key}"},
                json={
                    "sheets_row": {
                        "row_id": "row_1",
                        "script": "Script de test complet pour le pipeline A. " * 3,
                        "format": "vertical",
                        "strategy": "A",
                        "duration": 90,
                        "voice_id": "voice-test",
                        "cta": "Contactez-nous",
                    }
                },
            )
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]

    # Tous les modules du chemin A ont été appelés
    p_claude.assert_called_once()
    p_el.assert_called_once()
    p_kling.assert_called_once()
    p_creat.assert_called_once()

    # select_library_clips n'est pas appelé en stratégie A — pas de vérification
    # explicite car il n'est pas patché ici


# ──────────────────────────────────────────────────────────────────────────────
# Stratégie B — Library / Pexels / Kling
# ──────────────────────────────────────────────────────────────────────────────

def test_full_pipeline_strategy_b(env_vars, tmp_path, monkeypatch):
    """Pipeline Stratégie B : Claude → ElevenLabs → select_library_clips → Creatomate."""
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.models import JobStatus

    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))

    mock_analysis = _make_mock_analysis()
    mock_el = _make_mock_el()
    mock_clips: list = []
    mock_render = _make_mock_render()

    settings = Settings()

    with (
        patch("app.main.analyze_script", return_value=mock_analysis) as p_claude,
        patch("app.main.generate_voiceover", return_value=mock_el) as p_el,
        patch("app.main.select_library_clips", return_value=mock_clips) as p_lib,
        patch("app.main.assemble_video", return_value=mock_render) as p_creat,
    ):
        with TestClient(create_app_fresh(settings)) as client:
            resp = client.post(
                "/generate",
                headers={"Authorization": f"Bearer {settings.api_secret_key}"},
                json={
                    "sheets_row": {
                        "row_id": "row_2",
                        "script": "Script de test complet pour le pipeline B. " * 3,
                        "format": "vertical",
                        "strategy": "B",
                        "duration": 90,
                        "voice_id": "voice-test",
                        "cta": "En savoir plus",
                    }
                },
            )
            assert resp.status_code == 202

    p_claude.assert_called_once()
    p_el.assert_called_once()
    p_lib.assert_called_once()
    p_creat.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# Timeout global — asyncio.TimeoutError → job FAILED
# ──────────────────────────────────────────────────────────────────────────────

def test_pipeline_timeout_marks_job_failed(env_vars, tmp_path, monkeypatch):
    """
    Quand asyncio.TimeoutError est levé dans run_pipeline,
    le job doit passer à l'état FAILED avec un message de timeout.
    """
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.models import JobStatus

    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))

    settings = Settings()

    async def slow_analyze(*args, **kwargs):
        raise asyncio.TimeoutError

    with (
        patch("app.main.analyze_script", side_effect=slow_analyze),
        patch("app.main.generate_voiceover", return_value=_make_mock_el()),
        patch("app.main.generate_clips", return_value=[]),
        patch("app.main.assemble_video", return_value=_make_mock_render()),
    ):
        with TestClient(create_app_fresh(settings)) as client:
            resp = client.post(
                "/generate",
                headers={"Authorization": f"Bearer {settings.api_secret_key}"},
                json={
                    "sheets_row": {
                        "row_id": "row_timeout",
                        "script": "Script de test timeout pour le pipeline. " * 3,
                        "format": "vertical",
                        "strategy": "A",
                        "duration": 90,
                        "voice_id": "voice-test",
                        "cta": "CTA",
                    }
                },
            )
            assert resp.status_code == 202
            job_id = resp.json()["job_id"]

            # Interroge le statut après que le background task s'est terminé
            status_resp = client.get(
                f"/status/{job_id}",
                headers={"Authorization": f"Bearer {settings.api_secret_key}"},
            )
            assert status_resp.status_code == 200
            data = status_resp.json()
            assert data["status"] == JobStatus.FAILED.value
            assert "timeout" in data["progress"]["detail"].lower()


# ──────────────────────────────────────────────────────────────────────────────
# Helper interne — fabrique une app fraîche sans réutiliser le singleton
# ──────────────────────────────────────────────────────────────────────────────

def create_app_fresh(settings):
    """
    Crée une instance FastAPI fraîche en contournant le module-level singleton
    `app = create_app()` qui serait partagé entre les tests.
    """
    from app.main import create_app
    return create_app(settings)
