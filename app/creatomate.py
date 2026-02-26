"""
creatomate.py — Assemblage vidéo final (PRD §4.4)

Responsabilités :
  - Envoyer voix off + clips + timestamps à Creatomate
  - Polling du rendu (toutes les 15s, timeout 15 min)
  - Retry x2 si le rendu échoue (PRD §5.1)
  - Deux templates : vertical_ad (9:16) et horizontal_ad (16:9)
  - Synchronisation sous-titres mot par mot (ElevenLabs → Creatomate)
"""
import asyncio
import logging

import httpx

from app.config import Settings
from app.errors import CreatomateAPIError, CreatomateRenderTimeoutError
from app.models import (
    CreatomateRenderRequest,
    CreatomateRenderResult,
    ElevenLabsResult,
    ScriptAnalysis,
    SheetsRow,
    VideoClip,
    VideoFormat,
    WordTimestamp,
)

logger = logging.getLogger(__name__)


async def assemble_video(
    script_analysis: ScriptAnalysis,
    elevenlabs_result: ElevenLabsResult,
    clips: list[VideoClip],
    row: SheetsRow,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> CreatomateRenderResult:
    """
    Assemble la vidéo finale via Creatomate (PRD §4.4).

    Ce que Creatomate reçoit :
      - audio_url   : MP3 voix off ElevenLabs
      - clips       : N MP4 dans l'ordre des sections
      - timestamps  : [{word, start_ms, end_ms}] pour sous-titres animés
      - logo_url    : URL du logo (overlay automatique)
      - cta_text    : Texte call-to-action final
      - music_url   : Musique de fond (volume ajusté par template)
      - template_id : vertical_ad (9:16) ou horizontal_ad (16:9)

    Args:
        script_analysis:   Résultat Claude (sections ordonnées)
        elevenlabs_result: Audio MP3 + timestamps
        clips:             Clips vidéo ordonnés par section_id
        row:               Données Google Sheets (format, cta, musique, logo)
        http_client:       Client HTTP partagé
        settings:          Configuration application

    Returns:
        CreatomateRenderResult avec URL du MP4 final

    Raises:
        CreatomateAPIError:           Erreur API Creatomate
        CreatomateRenderTimeoutError: Rendu > CREATOMATE_RENDER_TIMEOUT secondes
    """
    template_id = (
        settings.CREATOMATE_TEMPLATE_VERTICAL
        if row.format == VideoFormat.VERTICAL
        else settings.CREATOMATE_TEMPLATE_HORIZONTAL
    )

    request = CreatomateRenderRequest(
        template_id=template_id,
        audio_url=elevenlabs_result.audio_path,
        clips=sorted(clips, key=lambda c: c.section_id),
        timestamps=elevenlabs_result.timestamps,
        logo_url=row.logo_url,
        cta_text=row.cta,
        music_url=row.music_url,
        format=row.format,
    )

    last_error: Exception | None = None
    for attempt in range(settings.CREATOMATE_MAX_RETRIES + 1):
        try:
            render_id = await _submit_render(request, http_client, settings)
            result = await _poll_render(render_id, request.format, http_client, settings)
            return result
        except CreatomateRenderTimeoutError:
            raise
        except Exception as e:
            last_error = e
            logger.warning(
                "Creatomate tentative %d/%d échouée : %s",
                attempt + 1,
                settings.CREATOMATE_MAX_RETRIES + 1,
                e,
            )
            if attempt < settings.CREATOMATE_MAX_RETRIES:
                await asyncio.sleep(5.0)

    raise CreatomateAPIError(
        f"Creatomate échec après {settings.CREATOMATE_MAX_RETRIES + 1} tentatives : {last_error}"
    )


async def _submit_render(
    request: CreatomateRenderRequest,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> str:
    """POST /renders — soumet le job de rendu et retourne le render_id."""
    payload = _build_render_payload(request, settings)
    resp = await http_client.post(
        f"{settings.CREATOMATE_BASE_URL}/renders",
        headers={
            "Authorization": f"Bearer {settings.creatomate_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30.0,
    )
    resp.raise_for_status()
    renders = resp.json()
    render_id = renders[0]["id"]
    logger.info("Creatomate render soumis : render_id=%s", render_id)
    return render_id


async def _poll_render(
    render_id: str,
    format_: VideoFormat,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> CreatomateRenderResult:
    """
    Polling GET /renders/{render_id} toutes les CREATOMATE_POLLING_INTERVAL secondes.
    Statuts Creatomate : planned / rendering / succeeded / failed.
    """
    elapsed = 0.0
    while elapsed < settings.CREATOMATE_RENDER_TIMEOUT:
        await asyncio.sleep(settings.CREATOMATE_POLLING_INTERVAL)
        elapsed += settings.CREATOMATE_POLLING_INTERVAL

        resp = await http_client.get(
            f"{settings.CREATOMATE_BASE_URL}/renders/{render_id}",
            headers={"Authorization": f"Bearer {settings.creatomate_api_key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data["status"]

        if status == "succeeded":
            logger.info("Creatomate render terminé : %s", render_id)
            return CreatomateRenderResult(
                render_id=render_id,
                video_url=data["url"],
                duration_seconds=float(data.get("duration", 0)),
                file_size_bytes=data.get("file_size"),
                format=format_,
            )
        if status == "failed":
            raise CreatomateAPIError(
                f"Creatomate render {render_id} a échoué : {data.get('error_message')}"
            )

        logger.debug(
            "Creatomate polling render=%s status=%s elapsed=%.0fs",
            render_id,
            status,
            elapsed,
        )

    raise CreatomateRenderTimeoutError(
        f"Render {render_id} timeout après {settings.CREATOMATE_RENDER_TIMEOUT}s"
    )


def _build_render_payload(request: CreatomateRenderRequest, settings: Settings) -> dict:
    """
    Construit le payload JSON pour l'API Creatomate.
    Inclut la conversion des timestamps ElevenLabs en sous-titres animés.
    """
    modifications: dict = {}

    for i, clip in enumerate(request.clips):
        modifications[f"clip_{i + 1}"] = clip.url

    modifications["voiceover"] = request.audio_url

    if request.logo_url:
        modifications["logo"] = request.logo_url
    if request.cta_text:
        modifications["cta_text"] = request.cta_text
    if request.music_url:
        modifications["music"] = request.music_url

    if request.timestamps:
        modifications["subtitles"] = _timestamps_to_creatomate_subtitles(request.timestamps)

    return {"template_id": request.template_id, "modifications": modifications}


def _timestamps_to_creatomate_subtitles(timestamps: list[WordTimestamp]) -> list[dict]:
    """
    Convertit les timestamps ElevenLabs [{word, start_ms, end_ms}]
    en éléments texte Creatomate avec animations entrée/sortie synchronisées.
    PRD §4.4 : "Chaque mot apparaît exactement au moment où il est prononcé."
    """
    return [
        {
            "text": ts.word,
            "time": ts.start_ms / 1000.0,
            "duration": (ts.end_ms - ts.start_ms) / 1000.0,
        }
        for ts in timestamps
    ]
