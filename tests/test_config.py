"""
test_config.py — Tests unitaires config.py + models.py (Jour 1)

Lance avec : pytest tests/test_config.py -v
"""
import os

import pytest
from pydantic import ValidationError

# ─── Fixtures env minimales ───────────────────────────────────────────────────

MINIMAL_ENV = {
    "API_SECRET_KEY": "test-secret-key-32-chars-minimum!!",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ELEVENLABS_API_KEY": "el-test",
    "ELEVENLABS_DEFAULT_VOICE_ID": "voice-id-test",
    "KLING_ACCESS_KEY": "kling-access-test",
    "KLING_SECRET_KEY": "kling-secret-test",
    "PEXELS_API_KEY": "pexels-test",
    "CREATOMATE_API_KEY": "creat-test",
    "CREATOMATE_TEMPLATE_VERTICAL": "tmpl-vertical",
    "CREATOMATE_TEMPLATE_HORIZONTAL": "tmpl-horizontal",
    "GOOGLE_SERVICE_ACCOUNT_PATH": "/tmp/sa.json",
    "GOOGLE_DRIVE_FOLDER_ID": "drive-folder-id",
    "GOOGLE_SHEETS_ID": "sheets-id",
}


@pytest.fixture
def env_vars(monkeypatch):
    """Injecte les variables d'environnement minimales."""
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


# ─── Tests Settings ───────────────────────────────────────────────────────────

def test_settings_loads_from_env(env_vars):
    from app.config import Settings
    s = Settings()
    assert s.APP_NAME == "VideoGen API"
    assert s.ENVIRONMENT == "development"
    assert s.is_production is False


def test_settings_secrets_not_exposed_in_repr(env_vars):
    from app.config import Settings
    s = Settings()
    repr_str = repr(s)
    assert "sk-ant-test" not in repr_str
    assert "el-test" not in repr_str


def test_settings_expose_via_property(env_vars):
    from app.config import Settings
    s = Settings()
    assert s.anthropic_api_key == "sk-ant-test"
    assert s.elevenlabs_api_key == "el-test"


def test_settings_kling_parallel_jobs_max_5(env_vars, monkeypatch):
    monkeypatch.setenv("KLING_MAX_PARALLEL_JOBS", "10")
    from app.config import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_settings_environment_lowercased(env_vars, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
    from app.config import Settings
    s = Settings()
    assert s.ENVIRONMENT == "production"
    assert s.is_production is True


def test_get_settings_singleton(env_vars):
    from app.config import get_settings
    # lru_cache : même instance retournée
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


# ─── Tests Models ─────────────────────────────────────────────────────────────

def test_sheets_row_valid():
    from app.models import GenerationStrategy, SheetsRow, VideoFormat
    row = SheetsRow(
        row_id="row_1",
        script="A" * 50,
        format=VideoFormat.VERTICAL,
        strategy=GenerationStrategy.A,
        duration=90,
        voice_id="voice-id",
    )
    assert row.aspect_ratio == "9:16"


def test_sheets_row_invalid_duration():
    from app.models import SheetsRow
    with pytest.raises(ValidationError):
        SheetsRow(row_id="r1", script="A" * 50, voice_id="v", duration=45)


def test_script_section_timecode_validation():
    from app.models import ScriptSection
    with pytest.raises(ValidationError):
        ScriptSection(
            id=1, text="test", start=5, end=3, duration=5,
            broll_prompt="test prompt here ok"
        )


def test_script_analysis_duration_mismatch():
    from app.models import ScriptAnalysis, ScriptSection
    with pytest.raises(ValidationError):
        ScriptAnalysis(
            total_duration=10,
            sections=[
                ScriptSection(
                    id=1, text="test", start=0, end=5, duration=5,
                    broll_prompt="prompt ok"
                )
            ],
        )


def test_script_analysis_valid():
    from app.models import ScriptAnalysis, ScriptSection
    analysis = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="part1", start=0, end=5, duration=5, broll_prompt="entrepreneur bureau lumière chaude 9:16"),
            ScriptSection(id=2, text="part2", start=5, end=10, duration=5, broll_prompt="produit gros plan studio moderne 9:16"),
        ],
    )
    assert analysis.section_count == 2


def test_word_timestamp_validation():
    from app.models import WordTimestamp
    with pytest.raises(ValidationError):
        WordTimestamp(word="hello", start_ms=100, end_ms=50)


# ─── Tests FastAPI endpoints ──────────────────────────────────────────────────

def test_health_endpoint(env_vars):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    app = create_app(Settings())
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["version"] == "1.0.0"


def test_generate_requires_auth(env_vars):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    app = create_app(Settings())
    client = TestClient(app)
    resp = client.post("/generate", json={})
    assert resp.status_code == 401


def test_status_job_not_found(env_vars):
    from fastapi.testclient import TestClient
    from app.main import create_app
    from app.config import Settings
    import uuid
    settings = Settings()
    app = create_app(settings)
    # Utiliser le context manager pour déclencher le lifespan (init app.state.jobs)
    with TestClient(app) as client:
        resp = client.get(
            f"/status/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {settings.api_secret_key}"},
        )
    assert resp.status_code == 404
    assert resp.json()["error_code"] == "JOB_NOT_FOUND"
