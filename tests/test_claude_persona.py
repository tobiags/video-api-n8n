"""Tests for persona/ambiance injection in Claude system prompt."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import MINIMAL_ENV


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


@pytest.mark.asyncio
async def test_analyze_script_with_persona(env_vars):
    """When persona is provided, it appears in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "woman walking", "keywords": ["woman"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "woman smiling", "keywords": ["woman"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            result = await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
                persona="femme 30 ans, mère de famille",
            )

        # Check persona was injected in system prompt
        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "femme 30 ans, mère de famille" in system_text
        assert result.total_duration == 10


@pytest.mark.asyncio
async def test_analyze_script_without_persona(env_vars):
    """When persona is None, the persona block is NOT in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "person walking", "keywords": ["person"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "person smiling", "keywords": ["person"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            result = await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
            )

        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "CONTEXTE PERSONNAGE" not in system_text


@pytest.mark.asyncio
async def test_analyze_script_with_ambiance(env_vars):
    """When ambiance is provided, it appears in the system prompt."""
    from app.claude import analyze_script
    from app.config import get_settings
    from app.models import VideoFormat
    import httpx

    settings = get_settings()

    mock_response = MagicMock()
    mock_response.content = [MagicMock()]
    mock_response.content[0].text = json.dumps({
        "total_duration": 10,
        "sections": [
            {"id": 1, "text": "Test", "start": 0, "end": 5, "duration": 5,
             "broll_prompt": "warm scene", "keywords": ["warm"], "scene_type": "ambient"},
            {"id": 2, "text": "Test2", "start": 5, "end": 10, "duration": 5,
             "broll_prompt": "golden light", "keywords": ["golden"], "scene_type": "ambient"},
        ],
    })

    with patch("app.claude.anthropic.AsyncAnthropic") as MockClient:
        instance = MockClient.return_value
        instance.messages.create = AsyncMock(return_value=mock_response)

        async with httpx.AsyncClient() as http_client:
            await analyze_script(
                script="A" * 50,
                format_=VideoFormat.VERTICAL,
                duration=10,
                aspect_ratio="9:16",
                http_client=http_client,
                settings=settings,
                ambiance="cinématique chaud, lumière dorée",
            )

        call_kwargs = instance.messages.create.call_args
        system_text = call_kwargs.kwargs["system"]
        assert "cinématique chaud, lumière dorée" in system_text
        assert "AMBIANCE VISUELLE" in system_text
