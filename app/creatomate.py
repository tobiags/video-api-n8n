"""
creatomate.py — Assemblage vidéo final (PRD §4.4)

Responsabilités :
  - Générer dynamiquement la composition JSON (approche "source", pas de template statique)
  - Envoyer voix off + clips + timestamps à Creatomate
  - Polling du rendu (toutes les 15s, timeout 15 min)
  - Retry x2 si le rendu échoue (PRD §5.1)
  - Deux formats : vertical_ad (9:16) et horizontal_ad (16:9)

NOTE : on n'utilise plus CREATOMATE_TEMPLATE_VERTICAL / HORIZONTAL.
La composition est construite en code selon le nombre de clips retourné par Claude.
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

# Dimensions par format
_DIMENSIONS: dict[VideoFormat, tuple[int, int]] = {
    VideoFormat.VERTICAL:   (1080, 1920),  # 9:16
    VideoFormat.HORIZONTAL: (1920, 1080),  # 16:9
}


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

    Génère dynamiquement la composition JSON (source) selon :
      - audio_url   : MP3 voix off ElevenLabs (URL publique)
      - clips       : N MP4 dans l'ordre des sections
      - logo_url    : URL du logo (overlay)
      - cta_text    : Texte call-to-action final
      - music_url   : Musique de fond (volume 15%)
      - format      : vertical (9:16) ou horizontal (16:9)

    Returns:
        CreatomateRenderResult avec URL du MP4 final

    Raises:
        CreatomateAPIError:           Erreur API Creatomate
        CreatomateRenderTimeoutError: Rendu > CREATOMATE_RENDER_TIMEOUT secondes
    """
    # Calcul du multiplicateur audio Creatomate pour les vitesses > 1.2 (max ElevenLabs)
    # Ex: voice_speed=1.5 → ElevenLabs tourne à 1.2, Creatomate accélère de 1.5/1.2 = 1.25x
    eleven_speed = min(row.voice_speed, 1.2)
    audio_speed = row.voice_speed / eleven_speed if row.voice_speed > 1.2 else 1.0

    # template_id factice (modèle Pydantic l'exige, non utilisé dans le payload source)
    section_durations = {s.id: float(s.duration) for s in script_analysis.sections}
    request = CreatomateRenderRequest(
        template_id="source",
        audio_url=elevenlabs_result.audio_path,
        clips=sorted(clips, key=lambda c: c.section_id),
        timestamps=elevenlabs_result.timestamps,
        logo_url=row.logo_url,
        cta_text=row.cta if settings.CREATOMATE_SHOW_CTA else "",
        music_url=row.music_url,
        format=row.format,
        target_duration_seconds=elevenlabs_result.audio_duration_seconds / audio_speed,
        audio_speed=audio_speed,
        section_durations=section_durations,
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
    payload = _build_source_payload(request)
    resp = await http_client.post(
        f"{settings.CREATOMATE_BASE_URL}/renders",
        headers={
            "Authorization": f"Bearer {settings.creatomate_api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30.0,
    )
    if not resp.is_success:
        raise CreatomateAPIError(
            f"Creatomate API {resp.status_code} : {resp.text[:300]}"
        )
    render = resp.json()
    # Response is a single dict — some doc examples use "id", others "render_id"
    render_id = render.get("id") or render.get("render_id")
    if not render_id:
        raise CreatomateAPIError(
            f"Réponse Creatomate sans id : {str(render)[:300]}"
        )
    n_clips = sum(1 for c in request.clips if c.url)
    logger.info(
        "Creatomate render soumis : render_id=%s | %d clips | audio=%s",
        render_id, n_clips, request.audio_url[:60],
    )
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
        resp = await http_client.get(
            f"{settings.CREATOMATE_BASE_URL}/renders/{render_id}",
            headers={"Authorization": f"Bearer {settings.creatomate_api_key}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        render_status = data["status"]

        if render_status == "succeeded":
            logger.info("Creatomate render terminé : %s", render_id)
            return CreatomateRenderResult(
                render_id=render_id,
                video_url=data["url"],
                duration_seconds=float(data.get("duration", 0)),
                file_size_bytes=data.get("file_size"),
                format=format_,
            )
        if render_status == "failed":
            raise CreatomateAPIError(
                f"Creatomate render {render_id} a échoué : {data.get('error_message')}"
            )

        logger.info(
            "Creatomate polling render=%s status=%s elapsed=%.0fs",
            render_id, render_status, elapsed,
        )
        await asyncio.sleep(settings.CREATOMATE_POLLING_INTERVAL)
        elapsed += settings.CREATOMATE_POLLING_INTERVAL

    raise CreatomateRenderTimeoutError(
        f"Render {render_id} timeout après {settings.CREATOMATE_RENDER_TIMEOUT}s"
    )


def _build_source_payload(request: CreatomateRenderRequest) -> dict:
    """
    Construit le payload RenderScript Creatomate /v2/renders.

    Doc : https://creatomate.com/docs/api/quick-start/synchronize-multiple-elements
    Format : {output_format, width, height, elements} à la racine (PAS de wrapper "source").
    Clips sur le même track → lecture séquentielle automatique (pas de time offset manuel).

    Structure des tracks :
      1 — Clips vidéo séquentiels (même track = auto-séquentiel)
      2 — Voix off (audio ElevenLabs, duration=null → s'adapte à la composition)
      3 — Musique de fond (optionnel, 15% volume)
      4 — Logo overlay (optionnel)
      5 — CTA texte (optionnel)
    """
    width, height = _DIMENSIONS.get(request.format, (1080, 1920))
    elements: list[dict] = []

    # ── Track 1 : Clips vidéo séquentiels ────────────────────────────────────
    # time + duration explicites : chaque clip joue exactement la durée de sa section.
    # Sans ça, Creatomate utilise la durée native du fichier source (Pexels = 10-60s).
    valid_clips = 0
    current_time = 0.0
    for clip in sorted(request.clips, key=lambda c: c.section_id):
        section_dur = request.section_durations.get(clip.section_id)
        if not clip.url:
            logger.warning("Clip section=%d sans URL — ignoré", clip.section_id)
            if section_dur:
                current_time += section_dur
            continue
        clip_element: dict = {
            "type": "video",
            "track": 1,
            "source": clip.url,
            "fit": "cover",
            "volume": "0%",
            "time": round(current_time, 3),
        }
        if section_dur:
            clip_element["duration"] = section_dur
        elements.append(clip_element)
        current_time += section_dur if section_dur else 5.0
        valid_clips += 1

    logger.info(
        "Creatomate payload : %d clips valides / %d total",
        valid_clips, len(request.clips),
    )

    # ── Track 2 : Voix off ────────────────────────────────────────────────────
    # duration=null → s'adapte à la longueur totale de la composition
    voiceover_element: dict = {
        "type": "audio",
        "track": 2,
        "source": request.audio_url,
        "duration": None,
        "audio_fade_out": 0.5,
    }
    if request.audio_speed != 1.0:
        voiceover_element["speed"] = round(request.audio_speed, 4)
    elements.append(voiceover_element)

    # ── Track 3 : Musique de fond (optionnel) ─────────────────────────────────
    if request.music_url:
        elements.append({
            "type": "audio",
            "track": 3,
            "source": request.music_url,
            "duration": None,
            "volume": "15%",
            "audio_fade_in": 1.0,
            "audio_fade_out": 2.0,
        })

    # ── Track 4 : Logo overlay (optionnel, coin haut-gauche) ─────────────────
    if request.logo_url:
        elements.append({
            "type": "image",
            "track": 4,
            "source": request.logo_url,
            "fit": "contain",
            "width": "20%",
            "height": "10%",
            "x": "5%",
            "y": "5%",
            "x_anchor": "0%",
            "y_anchor": "0%",
        })

    # ── Track 5 : CTA texte (optionnel) ──────────────────────────────────────
    if request.cta_text:
        elements.append({
            "type": "text",
            "track": 5,
            "text": request.cta_text,
            "font_family": "Montserrat",
            "font_size": "4 vmin",
            "font_weight": "700",
            "fill_color": "#ffffff",
            "stroke_color": "#000000",
            "stroke_width": "0.3 vmin",
            "x": "50%",
            "y": "85%",
            "width": "85%",
            "x_anchor": "50%",
            "y_anchor": "50%",
            "text_align": "center",
        })

    # ── Payload racine (format RenderScript /v2) ──────────────────────────────
    # duration = durée audio réelle → cap la composition (évite 7min de clips Pexels)
    payload: dict = {
        "output_format": "mp4",
        "width": width,
        "height": height,
        "frame_rate": 25,
        "elements": elements,
    }
    if request.target_duration_seconds:
        # +2.0s buffer: last video clip continues 2s after voiceover ends (avoids hard cut on final word)
        payload["duration"] = round(request.target_duration_seconds + 2.0, 2)
    return payload
