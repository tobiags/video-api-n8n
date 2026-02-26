"""
test_elevenlabs.py — Tests unitaires pour app/elevenlabs.py (PRD §4.2)

Tests :
  1. Réponse valide → ElevenLabsResult correct avec timestamps
  2. Erreur HTTP → retry x2 → ElevenLabsAPIError
"""
import base64

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import MINIMAL_ENV


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)


def _fake_audio_b64() -> str:
    return base64.b64encode(b"fake-mp3-data").decode()


def _fake_el_response() -> dict:
    return {
        "audio_base64": _fake_audio_b64(),
        "normalized_alignment": {
            "characters": ["H", "e", "l", "l", "o", " ", "w", "o", "r", "l", "d"],
            "character_start_times_seconds": [0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
            "character_end_times_seconds":   [0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6],
        },
    }


@pytest.mark.asyncio
async def test_generate_voiceover_returns_result(env_vars, tmp_path, monkeypatch):
    from app.elevenlabs import generate_voiceover
    from app.config import Settings

    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))
    settings = Settings()

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = _fake_el_response()
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = mock_response

    monkeypatch.setattr("app.elevenlabs.AUDIO_STORAGE_DIR", str(tmp_path))

    result = await generate_voiceover(
        script="Hello world",
        voice_id="voice-123",
        http_client=mock_client,
        settings=settings,
    )

    assert result.voice_id == "voice-123"
    assert result.audio_duration_ms > 0
    assert len(result.timestamps) > 0
    assert result.timestamps[0].word  # at least one word
    mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_generate_voiceover_retries_on_error(env_vars, tmp_path, monkeypatch):
    from app.elevenlabs import generate_voiceover
    from app.config import Settings
    from app.errors import ElevenLabsAPIError

    monkeypatch.setattr("app.elevenlabs.AUDIO_STORAGE_DIR", str(tmp_path))
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.HTTPError("Connection failed")

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ElevenLabsAPIError):
            await generate_voiceover("Hello", "voice-123", mock_client, settings)

    # ELEVENLABS_MAX_RETRIES=2 → 2 calls total (attempt 0 and 1)
    assert mock_client.post.call_count == 2


@pytest.mark.asyncio
async def test_generate_voiceover_raises_timeout_error(env_vars, tmp_path, monkeypatch):
    from app.elevenlabs import generate_voiceover
    from app.config import Settings
    from app.errors import ElevenLabsTimeoutError

    monkeypatch.setattr("app.elevenlabs.AUDIO_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("LIBRARY_PATH", str(tmp_path / "clips"))
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = httpx.TimeoutException("timed out")

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ElevenLabsTimeoutError):
            await generate_voiceover("Hello", "voice-123", mock_client, settings)

    assert mock_client.post.call_count == 2
