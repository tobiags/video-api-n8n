# tests/test_kling.py
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from tests.conftest import MINIMAL_ENV

@pytest.fixture
def env_vars(monkeypatch):
    for k, v in MINIMAL_ENV.items():
        monkeypatch.setenv(k, v)

def _make_section(id_=1, keywords=None):
    from app.models import ScriptSection
    return ScriptSection(
        id=id_, text="test", start=(id_-1)*5, end=id_*5, duration=5,
        broll_prompt=f"entrepreneur bureau lumière 9:16 section {id_}",
        keywords=keywords or ["entrepreneur"],
    )

def _kling_created_response(task_id="task-abc"):
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {"code": 0, "data": {"task_id": task_id, "task_status": "submitted"}}
    return m

def _kling_done_response(task_id="task-abc", video_url="https://kling.cdn/clip.mp4"):
    m = MagicMock(spec=httpx.Response)
    m.status_code = 200
    m.raise_for_status = MagicMock()
    m.json.return_value = {
        "code": 0,
        "data": {
            "task_id": task_id,
            "task_status": "succeed",
            "task_result": {"videos": [{"url": video_url, "duration": "5.0"}]},
        }
    }
    return m

@pytest.mark.asyncio
async def test_generate_single_clip_success(env_vars):
    from app.kling import generate_single_clip
    from app.models import VideoFormat, ClipSource
    from app.config import Settings
    settings = Settings()

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.return_value = _kling_created_response()
    mock_client.get.return_value = _kling_done_response()

    with patch("app.kling.asyncio.sleep", new=AsyncMock()):
        clip = await generate_single_clip(_make_section(), VideoFormat.VERTICAL, mock_client, settings)

    assert clip.source == ClipSource.KLING
    assert clip.url == "https://kling.cdn/clip.mp4"
    assert clip.section_id == 1

@pytest.mark.asyncio
async def test_generate_clips_respects_semaphore(env_vars):
    """Verify that max KLING_MAX_PARALLEL_JOBS clips run simultaneously."""
    from app.kling import generate_clips, generate_single_clip
    from app.models import VideoFormat, VideoClip, ClipSource
    from app.config import Settings
    settings = Settings()

    max_concurrent = 0
    current_concurrent = 0

    async def fake_generate_single_clip(section, format_, http_client, _settings, attempt=1):
        nonlocal max_concurrent, current_concurrent
        current_concurrent += 1
        max_concurrent = max(max_concurrent, current_concurrent)
        await asyncio.sleep(0)  # yield to allow other coroutines to start
        current_concurrent -= 1
        return VideoClip(
            section_id=section.id, source=ClipSource.KLING,
            url=f"https://cdn/{section.id}.mp4", duration_seconds=5.0,
        )

    sections = [_make_section(i) for i in range(1, 8)]  # 7 sections > max 5 parallel
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    with patch("app.kling.generate_single_clip", side_effect=fake_generate_single_clip):
        clips = await generate_clips(sections, VideoFormat.VERTICAL, mock_client, settings)

    assert len(clips) == 7
    assert all(c.source.value == "kling" for c in clips)
    assert max_concurrent <= settings.KLING_MAX_PARALLEL_JOBS  # key assertion: semaphore enforced

@pytest.mark.asyncio
async def test_generate_single_clip_retries_then_raises(env_vars):
    from app.kling import generate_single_clip
    from app.models import VideoFormat
    from app.config import Settings
    from app.errors import KlingMaxRetriesError
    settings = Settings()

    # 3 create responses + 3 poll responses (all "failed")
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post.side_effect = [_kling_created_response(f"t{i}") for i in range(3)]
    mock_client.get.side_effect = [
        MagicMock(spec=httpx.Response, **{
            "raise_for_status": MagicMock(),
            "json.return_value": {"code": 0, "data": {"task_id": f"t{i}", "task_status": "failed"}}
        })
        for i in range(3)
    ]

    with patch("app.kling.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(KlingMaxRetriesError):
            await generate_single_clip(_make_section(), VideoFormat.VERTICAL, mock_client, settings)

    # All 3 attempts made a POST request
    assert mock_client.post.call_count == 3
