# tests/test_library.py
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tests.conftest import MINIMAL_ENV

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

@pytest.fixture
def library_dir(tmp_path):
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    return tmp_path

def _make_section(id_=1):
    from app.models import ScriptSection
    return ScriptSection(id=id_, text="Entrepreneur", start=0, end=5, duration=5,
                         broll_prompt="entrepreneur bureau 9:16", keywords=["entrepreneur", "bureau"])

@pytest.mark.asyncio
async def test_library_search_returns_match_above_threshold(env_vars, library_dir, monkeypatch):
    from app.library import library_search
    from app.config import Settings
    from app.models import VideoFormat, LibraryClip

    monkeypatch.setenv("LIBRARY_INDEX_FILE", str(library_dir / "index.json"))
    settings = Settings()

    existing_clip = LibraryClip(
        clip_id="clip-1", filename="entrepreneur_01.mp4",
        theme="entrepreneur", keywords=["entrepreneur", "bureau"],
        duration_seconds=5.0, format=VideoFormat.VERTICAL
    )
    (library_dir / "index.json").write_text(
        json.dumps([existing_clip.model_dump(mode="json")])
    )

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 0.85, "reason": "Correspondance directe"}')]

    with patch("app.library.anthropic.AsyncAnthropic") as mock_anthro:
        mock_client_instance = AsyncMock()
        mock_client_instance.messages.create = AsyncMock(return_value=mock_message)
        mock_anthro.return_value = mock_client_instance

        result = await library_search(_make_section(), VideoFormat.VERTICAL, settings)

    assert result is not None
    assert result.relevance_score >= 0.7
    assert result.clip.clip_id == "clip-1"

@pytest.mark.asyncio
async def test_library_search_returns_none_below_threshold(env_vars, library_dir, monkeypatch):
    from app.library import library_search
    from app.config import Settings
    from app.models import VideoFormat, LibraryClip

    monkeypatch.setenv("LIBRARY_INDEX_FILE", str(library_dir / "index.json"))
    settings = Settings()

    (library_dir / "index.json").write_text(json.dumps([
        LibraryClip(clip_id="c1", filename="f.mp4", theme="cuisine",
                    keywords=["cuisine"], duration_seconds=5.0, format=VideoFormat.VERTICAL
                    ).model_dump(mode="json")
    ]))

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 0.3, "reason": "Thème différent"}')]

    with patch("app.library.anthropic.AsyncAnthropic") as mock_anthro:
        instance = AsyncMock()
        instance.messages.create = AsyncMock(return_value=mock_message)
        mock_anthro.return_value = instance
        result = await library_search(_make_section(), VideoFormat.VERTICAL, settings)

    assert result is None
