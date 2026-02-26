"""
tests/test_creatomate.py — Tests TDD pour app/creatomate.py (PRD §4.4)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import unittest.mock

from tests.conftest import MINIMAL_ENV
from app.models import (
    ElevenLabsResult, ScriptSection, ScriptAnalysis,
    VideoClip, ClipSource, VideoFormat, WordTimestamp, SheetsRow,
)


@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)



@pytest.mark.asyncio
async def test_assemble_video_returns_render_result(env_vars):
    from app.creatomate import assemble_video
    from app.config import Settings
    settings = Settings()

    submitted = MagicMock(spec=httpx.Response)
    submitted.raise_for_status = MagicMock()
    submitted.json.return_value = [{"id": "render-123", "status": "planned"}]

    done = MagicMock(spec=httpx.Response)
    done.raise_for_status = MagicMock()
    done.json.return_value = {
        "id": "render-123",
        "status": "succeeded",
        "url": "https://cdn/final.mp4",
        "duration": 10.0,
        "file_size": 5000000,
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = submitted
    mock_client.get.return_value = done

    row = SheetsRow(
        row_id="r1",
        script="A" * 50,
        voice_id="v1",
        duration=90,
        cta="Contactez-nous",
    )
    analysis = ScriptAnalysis(
        total_duration=10,
        sections=[
            ScriptSection(id=1, text="p1", start=0, end=5, duration=5,
                          broll_prompt="entrepreneur bureau lumière 9:16"),
            ScriptSection(id=2, text="p2", start=5, end=10, duration=5,
                          broll_prompt="produit gros plan 9:16"),
        ]
    )
    el_result = ElevenLabsResult(
        audio_path="/tmp/a.mp3",
        audio_duration_ms=10000,
        timestamps=[],
        voice_id="v1",
        character_count=100,
    )
    clips = [
        VideoClip(section_id=i, source=ClipSource.KLING,
                  url=f"https://cdn/{i}.mp4", duration_seconds=5.0)
        for i in [1, 2]
    ]

    with unittest.mock.patch("app.creatomate.asyncio.sleep", new=AsyncMock()):
        result = await assemble_video(analysis, el_result, clips, row, mock_client, settings)

    assert result.render_id == "render-123"
    assert result.video_url == "https://cdn/final.mp4"
