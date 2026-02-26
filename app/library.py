"""
library.py — Bibliothèque clips locale + cascade Stratégie B (PRD §3)
"""
import json
import logging
from collections.abc import Callable
from pathlib import Path

import anthropic
import httpx

from app.config import Settings
from app.models import (ClipSource, LibraryClip, LibrarySearchResult,
                        ScriptSection, VideoClip, VideoFormat)

logger = logging.getLogger(__name__)


def load_library_index(settings: Settings) -> list[LibraryClip]:
    index_path = Path(settings.LIBRARY_INDEX_FILE)
    if not index_path.exists():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
        return [LibraryClip(**item) for item in data]
    except Exception as e:
        logger.error("Erreur lecture index bibliothèque : %s", e)
        return []


def save_library_index(clips: list[LibraryClip], settings: Settings) -> None:
    index_path = Path(settings.LIBRARY_INDEX_FILE)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps([c.model_dump(mode="json") for c in clips], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def library_search(
    section: ScriptSection,
    format_: VideoFormat,
    settings: Settings,
) -> LibrarySearchResult | None:
    clips = load_library_index(settings)
    candidates = [c for c in clips if c.format == format_]
    if not candidates:
        return None

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    clips_summary = "\n".join(
        f"- id:{c.clip_id} theme:{c.theme} keywords:{c.keywords}"
        for c in candidates[:20]  # limit to avoid context explosion
    )
    prompt = (
        f"Section vidéo : '{section.text}'\n"
        f"Keywords : {section.keywords}\n\n"
        f"Clips disponibles :\n{clips_summary}\n\n"
        "Quel clip correspond le mieux ? Réponds en JSON : "
        '{"score": <0.0-1.0>, "clip_id": "<id ou null>", "reason": "<explication>"}'
    )
    try:
        response = await client.messages.create(
            model=settings.CLAUDE_MODEL, max_tokens=256,
            messages=[{"role": "user", "content": prompt}],
        )
        data = json.loads(response.content[0].text)
        score = float(data.get("score", 0))
        if score < settings.LIBRARY_SCORE_THRESHOLD:
            return None
        clip_id = data.get("clip_id")
        matched = next((c for c in candidates if c.clip_id == clip_id), None)
        if matched is None:
            return None
        return LibrarySearchResult(
            clip=matched, relevance_score=score,
            matched_keywords=[k for k in section.keywords if k in matched.keywords],
        )
    except Exception as e:
        logger.warning("library_search Claude error : %s", e)
        return None


async def pexels_search(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> VideoClip | None:
    orientation = "portrait" if format_ == VideoFormat.VERTICAL else "landscape"
    query = " ".join(section.keywords[:3]) if section.keywords else section.text[:40]
    try:
        resp = await http_client.get(
            f"{settings.PEXELS_BASE_URL}/videos/search",
            headers={"Authorization": settings.pexels_api_key},
            params={"query": query, "per_page": 5, "orientation": orientation},
            timeout=15.0,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if not videos:
            return None
        best = videos[0]
        file_url = best["video_files"][0]["link"]
        return VideoClip(section_id=section.id, source=ClipSource.PEXELS,
                         url=file_url, duration_seconds=float(best.get("duration", 5)),
                         keywords_used=section.keywords)
    except Exception as e:
        logger.warning("Pexels search erreur section %d : %s", section.id, e)
        return None


async def add_to_library(
    clip: VideoClip,
    section: ScriptSection,
    settings: Settings,
    format_: VideoFormat = VideoFormat.VERTICAL,
) -> LibraryClip:
    clips = load_library_index(settings)
    lib_clip = LibraryClip(
        filename=clip.url.split("/")[-1] if clip.url else f"{section.id}.mp4",
        theme=section.scene_type.value,
        keywords=section.keywords,
        duration_seconds=clip.duration_seconds,
        format=format_,
    )
    clips.append(lib_clip)
    save_library_index(clips, settings)
    logger.info("Clip ajouté à la bibliothèque : %s", lib_clip.clip_id)
    return lib_clip


async def select_library_clips(
    sections: list[ScriptSection],
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[VideoClip]:
    from app.kling import generate_single_clip
    clips: list[VideoClip] = []
    total = len(sections)

    for i, section in enumerate(sections):
        clip: VideoClip | None = None

        # 1. Local library
        lib_result = await library_search(section, format_, settings)
        if lib_result:
            logger.info("Library hit section %d score=%.2f", section.id, lib_result.relevance_score)
            clip = VideoClip(
                section_id=section.id, source=ClipSource.LIBRARY,
                url=str(Path(settings.LIBRARY_PATH) / lib_result.clip.filename),
                duration_seconds=lib_result.clip.duration_seconds,
                library_clip_id=lib_result.clip.clip_id,
            )
        # 2. Pexels fallback
        if clip is None:
            clip = await pexels_search(section, format_, http_client, settings)
            if clip:
                logger.info("Pexels hit section %d", section.id)

        # 3. Kling last resort
        if clip is None:
            logger.info("Kling generation section %d (aucun clip en bibliothèque/Pexels)", section.id)
            try:
                clip = await generate_single_clip(section, format_, http_client, settings)
                await add_to_library(clip, section, settings, format_)
            except Exception as e:
                logger.error("Kling échec section %d : %s — clip vide", section.id, e)
                clip = VideoClip(section_id=section.id, source=ClipSource.KLING,
                                 url="", duration_seconds=float(settings.KLING_DURATION))

        clips.append(clip)
        if progress_callback:
            progress_callback(i + 1, total)

    return clips
