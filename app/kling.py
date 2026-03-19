"""
kling.py — Module génération clips IA asynchrone (PRD §4.3)

Responsabilités :
  - Lancer N jobs Kling via PiAPI (revendeur officiel Kling)
  - Polling individuel toutes les 30s, timeout 10 min par clip
  - Retry auto x3 par clip, puis fallback Pexels sur échec définitif
  - Authentification via x-api-key (PiAPI)
"""
import asyncio
import logging
from collections.abc import Callable

import httpx

from app.config import Settings
from app.errors import KlingAPIError, KlingClipTimeoutError, KlingMaxRetriesError, KlingUnavailableError
from app.models import ClipSource, ScriptSection, VideoClip, VideoFormat

logger = logging.getLogger(__name__)


def _piapi_headers(settings: Settings) -> dict:
    return {"x-api-key": settings.piapi_api_key, "Content-Type": "application/json"}


async def generate_clips(
    sections: list[ScriptSection],
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[VideoClip]:
    """
    Génère les clips vidéo IA pour toutes les sections (Stratégie A — Kling pur).

    Utilise asyncio.gather avec sémaphore (max KLING_MAX_PARALLEL_JOBS=5).
    Les échecs définitifs par clip sont remplacés automatiquement par un fallback Pexels.

    Args:
        sections:          Sections Claude à convertir en clips
        format_:           VideoFormat pour le ratio dans les prompts
        http_client:       Client HTTP partagé
        settings:          Configuration application
        progress_callback: Appelé à chaque clip terminé (done, total)

    Returns:
        list[VideoClip] ordonnée par section_id, sans trou.
    """
    semaphore = asyncio.Semaphore(settings.KLING_MAX_PARALLEL_JOBS)
    done_count = 0
    total = len(sections)
    results: list[VideoClip | Exception] = [None] * total  # type: ignore

    async def run_one(idx: int, section: ScriptSection):
        nonlocal done_count
        async with semaphore:
            try:
                clip = await generate_single_clip(section, format_, http_client, settings)
                results[idx] = clip
            except Exception as e:
                logger.error("Clip section %d échoué après retries : %s", section.id, e)
                results[idx] = e
            finally:
                done_count += 1
                if progress_callback:
                    progress_callback(done_count, total)

    await asyncio.gather(*[run_one(i, s) for i, s in enumerate(sections)])

    # Pexels fallback for failed clips
    clips: list[VideoClip] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Fallback Pexels pour section %d", sections[i].id)
            fallback = await _pexels_fallback(sections[i], format_, http_client, settings)
            clips.append(fallback)
        else:
            clips.append(result)  # type: ignore

    return sorted(clips, key=lambda c: c.section_id)


async def generate_single_clip(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
    attempt: int = 1,
) -> VideoClip:
    """
    Génère un clip Kling pour une section, avec polling asynchrone.

    Raises:
        KlingMaxRetriesError: Après KLING_MAX_RETRIES tentatives
        KlingClipTimeoutError: Si le clip dépasse KLING_CLIP_TIMEOUT secondes
        KlingUnavailableError: Si l'API Kling répond HTTP 429/503
        KlingAPIError: Pour toute autre erreur HTTP Kling
    """
    if attempt > settings.KLING_MAX_RETRIES:
        raise KlingMaxRetriesError(
            f"Section {section.id} : max retries ({settings.KLING_MAX_RETRIES}) atteint"
        )

    aspect = "9:16" if format_ == VideoFormat.VERTICAL else "16:9"

    try:
        create_resp = await http_client.post(
            f"{settings.KLING_BASE_URL}/api/v1/task",
            headers=_piapi_headers(settings),
            json={
                "model": "kling",
                "task_type": "video_generation",
                "input": {
                    "prompt": section.broll_prompt,
                    "duration": settings.KLING_DURATION,
                    "aspect_ratio": aspect,
                    "version": settings.PIAPI_KLING_VERSION,
                    "mode": "pro",
                },
            },
            timeout=30.0,
        )
        create_resp.raise_for_status()
        data = create_resp.json()
        task_id = data["data"]["task_id"]
        logger.info("Kling job créé (PiAPI) : task_id=%s section=%d", task_id, section.id)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            if attempt <= settings.KLING_MAX_RETRIES:
                wait_s = 60 * attempt
                logger.warning(
                    "Kling 429 section %d — rate limit, attente %ds (retry %d/%d)",
                    section.id, wait_s, attempt, settings.KLING_MAX_RETRIES,
                )
                await asyncio.sleep(wait_s)
                return await generate_single_clip(section, format_, http_client, settings, attempt + 1)
            raise KlingUnavailableError(f"Kling rate limit persistant après {attempt} tentatives")
        if e.response.status_code == 503:
            raise KlingUnavailableError(f"Kling indisponible : HTTP 503")
        raise KlingAPIError(f"Kling create error HTTP {e.response.status_code} : {e}")

    # Polling loop
    elapsed = 0.0
    while elapsed < settings.KLING_CLIP_TIMEOUT:
        await asyncio.sleep(settings.KLING_POLLING_INTERVAL)
        elapsed += settings.KLING_POLLING_INTERVAL

        poll_resp = await http_client.get(
            f"{settings.KLING_BASE_URL}/api/v1/task/{task_id}",
            headers=_piapi_headers(settings),
            timeout=15.0,
        )
        poll_resp.raise_for_status()
        poll_data = poll_resp.json()["data"]
        status_str = poll_data["status"]

        if status_str in ("Completed", "completed"):
            output = poll_data.get("output", {})
            # PiAPI retourne video_url soit dans output.video soit dans output.works[0]
            video_url = output.get("video") or ""
            if not video_url:
                works = output.get("works", [])
                if works:
                    video_url = (
                        works[0].get("video", {}).get("resource_without_watermark")
                        or works[0].get("video", {}).get("resource", "")
                    )
            logger.info(
                "Kling clip OK (PiAPI) : task_id=%s section=%d url=%s", task_id, section.id, video_url
            )
            return VideoClip(
                section_id=section.id,
                source=ClipSource.KLING,
                url=video_url,
                duration_seconds=float(settings.KLING_DURATION),
                prompt_used=section.broll_prompt,
            )

        if status_str in ("Failed", "failed"):
            error_msg = poll_data.get("error", {}).get("message", "unknown")
            if attempt < settings.KLING_MAX_RETRIES:
                logger.warning(
                    "Kling clip Failed (%s), retry %d/%d section %d",
                    error_msg, attempt, settings.KLING_MAX_RETRIES, section.id,
                )
                return await generate_single_clip(
                    section, format_, http_client, settings, attempt + 1
                )
            raise KlingMaxRetriesError(
                f"Section {section.id} Kling failed après {attempt} tentatives : {error_msg}"
            )

        logger.info(
            "Kling polling task=%s status=%s elapsed=%.0fs section=%d",
            task_id, status_str, elapsed, section.id,
        )

    raise KlingClipTimeoutError(
        f"Section {section.id} : timeout {settings.KLING_CLIP_TIMEOUT}s dépassé",
    )


async def _pexels_fallback(
    section: ScriptSection,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> VideoClip:
    """Fallback Pexels when Kling fails definitively."""
    orientation = "portrait" if format_ == VideoFormat.VERTICAL else "landscape"
    query = " ".join(section.keywords[:3]) if section.keywords else section.broll_prompt[:50]

    try:
        resp = await http_client.get(
            f"{settings.PEXELS_BASE_URL}/videos/search",
            headers={"Authorization": settings.pexels_api_key},
            params={"query": query, "per_page": 5, "orientation": orientation},
            timeout=15.0,
        )
        resp.raise_for_status()
        videos = resp.json().get("videos", [])
        if videos:
            best = videos[0]
            video_files = best.get("video_files", [])
            mp4_files = sorted(
                [f for f in video_files if f.get("file_type") == "video/mp4" and f.get("link")],
                key=lambda f: (f.get("width", 0) or 0) * (f.get("height", 0) or 0),
                reverse=True,
            )
            file_url = mp4_files[0]["link"] if mp4_files else ""
            return VideoClip(
                section_id=section.id,
                source=ClipSource.PEXELS,
                url=file_url,
                duration_seconds=float(best.get("duration", 5)),
                keywords_used=section.keywords,
            )
    except Exception as e:
        logger.error("Pexels fallback échoué pour section %d : %s", section.id, e)

    # If even Pexels fails: empty clip (Creatomate will handle it)
    return VideoClip(
        section_id=section.id,
        source=ClipSource.PEXELS,
        url="",
        duration_seconds=float(settings.KLING_DURATION),
    )
