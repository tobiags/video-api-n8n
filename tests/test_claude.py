"""
test_claude.py — Tests unitaires pour app/claude.py (PRD §4.1)

Tests :
  1. Réponse JSON valide → ScriptAnalysis correct
  2. JSON invalide → retry x3 → ClaudeInvalidJSONError
"""
import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import ScriptAnalysis, VideoFormat

VALID_CLAUDE_JSON = {
    "total_duration": 10,
    "sections": [
        {
            "id": 1,
            "text": "Intro",
            "start": 0,
            "end": 5,
            "duration": 5,
            "broll_prompt": "entrepreneur moderne bureau lumière chaude 9:16",
            "keywords": ["entrepreneur", "bureau"],
            "scene_type": "emotion",
        },
        {
            "id": 2,
            "text": "CTA",
            "start": 5,
            "end": 10,
            "duration": 5,
            "broll_prompt": "produit gros plan fond blanc épuré 9:16",
            "keywords": ["produit"],
            "scene_type": "cta",
        },
    ],
}

MINIMAL_ENV = {
    "API_SECRET_KEY": "test-secret-key-32-chars-minimum!!",
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "ELEVENLABS_API_KEY": "el-test",
    "ELEVENLABS_DEFAULT_VOICE_ID": "voice-id-test",
    "KLING_ACCESS_KEY": "kling-access-test",
    "KLING_SECRET_KEY": "kling-secret-test",
    "PEXELS_API_KEY": "pexels-test",
    "CREATOMATE_API_KEY": "creat-test",
    "CREATOMATE_TEMPLATE_VERTICAL": "tmpl-v",
    "CREATOMATE_TEMPLATE_HORIZONTAL": "tmpl-h",
    "GOOGLE_SERVICE_ACCOUNT_PATH": "/tmp/sa.json",
    "GOOGLE_DRIVE_FOLDER_ID": "drive-id",
    "GOOGLE_SHEETS_ID": "sheets-id",
}


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


@pytest.mark.asyncio
async def test_analyze_script_returns_valid_analysis(env_vars):
    from app.claude import analyze_script
    from app.config import Settings

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(VALID_CLAUDE_JSON))]

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=mock_message)

    with patch("app.claude.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        result = await analyze_script(
            script="Vous perdez des heures à créer vos pubs. Notre outil change tout.",
            format_=VideoFormat.VERTICAL,
            duration=10,
            aspect_ratio="9:16",
            http_client=AsyncMock(spec=httpx.AsyncClient),
            settings=Settings(),
        )

    assert isinstance(result, ScriptAnalysis)
    assert result.total_duration == 10
    assert result.section_count == 2
    assert result.sections[0].broll_prompt == "entrepreneur moderne bureau lumière chaude 9:16"


@pytest.mark.asyncio
async def test_analyze_script_retries_on_invalid_json(env_vars):
    from app.claude import analyze_script
    from app.config import Settings
    from app.errors import ClaudeInvalidJSONError

    bad_response = MagicMock()
    bad_response.content = [MagicMock(text="not json at all")]

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=bad_response)

    with patch("app.claude.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        with pytest.raises(ClaudeInvalidJSONError):
            await analyze_script(
                script="Script test " * 10,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=AsyncMock(spec=httpx.AsyncClient),
                settings=Settings(),
            )

    # Must have been called CLAUDE_MAX_RETRIES=3 times
    assert mock_client_instance.messages.create.call_count == 3


@pytest.mark.asyncio
async def test_analyze_script_retries_on_duration_mismatch(env_vars):
    from app.claude import analyze_script
    from app.config import Settings
    from app.errors import ClaudeInvalidJSONError

    # Valid JSON but section durations don't sum to total_duration (3+3=6 != 10)
    bad_durations_json = {
        "total_duration": 10,
        "sections": [
            {
                "id": 1,
                "text": "p1",
                "start": 0,
                "end": 3,
                "duration": 3,
                "broll_prompt": "entrepreneur bureau lumière 9:16 section 1",
                "keywords": ["entrepreneur"],
                "scene_type": "emotion",
            },
            {
                "id": 2,
                "text": "p2",
                "start": 3,
                "end": 6,
                "duration": 3,
                "broll_prompt": "produit gros plan 9:16 section 2",
                "keywords": ["produit"],
                "scene_type": "cta",
            },
        ],
    }

    bad_response = MagicMock()
    bad_response.content = [MagicMock(text=json.dumps(bad_durations_json))]

    mock_client_instance = AsyncMock()
    mock_client_instance.messages.create = AsyncMock(return_value=bad_response)

    with patch("app.claude.anthropic.AsyncAnthropic", return_value=mock_client_instance):
        with pytest.raises(ClaudeInvalidJSONError):
            await analyze_script(
                script="Script test " * 10,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=AsyncMock(spec=httpx.AsyncClient),
                settings=Settings(),
            )

    # Must have exhausted all CLAUDE_MAX_RETRIES=3 attempts
    assert mock_client_instance.messages.create.call_count == 3
