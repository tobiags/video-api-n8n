"""
elevenlabs.py — Module voix off + timestamps (PRD §4.2)

Responsabilités :
  - Appel API ElevenLabs avec le script et l'ID du clone vocal
  - Récupération du MP3 + timestamps mot par mot
  - Retry x2 avec backoff exponentiel (PRD §5.1)
  - I3 fix : fallback vers ELEVENLABS_DEFAULT_VOICE_ID si voice_id est vide/None
"""
import asyncio
import base64
import logging
import os
import uuid
from pathlib import Path

import httpx

from app.config import Settings
from app.errors import ElevenLabsAPIError, ElevenLabsTimeoutError
from app.models import ElevenLabsResult, WordTimestamp

logger = logging.getLogger(__name__)

# Audio storage directory on VPS (override in tests via monkeypatch)
AUDIO_STORAGE_DIR = "/opt/videogen/audio"


async def generate_voiceover(
    script: str,
    voice_id: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ElevenLabsResult:
    """
    Génère la voix off depuis le clone vocal ElevenLabs.

    Endpoint : POST /v1/text-to-speech/{voice_id}/with-timestamps
    Retourne le MP3 + tableau de timestamps mot par mot.

    Args:
        script:      Script complet à synthétiser
        voice_id:    ID du clone vocal ElevenLabs (ligne Google Sheets)
        http_client: Client HTTP partagé
        settings:    Configuration application

    Returns:
        ElevenLabsResult avec chemin audio et timestamps

    Raises:
        ElevenLabsAPIError:     Erreur API ElevenLabs après épuisement des retries
        ElevenLabsTimeoutError: Timeout après backoff exponentiel x2
    """
    # I3 fix: fallback to default voice_id if empty/None
    effective_voice_id = voice_id or settings.elevenlabs_default_voice_id
    last_error: Exception | None = None

    for attempt in range(settings.ELEVENLABS_MAX_RETRIES):
        try:
            response = await http_client.post(
                f"{settings.ELEVENLABS_BASE_URL}/text-to-speech/{effective_voice_id}/with-timestamps",
                headers={
                    "xi-api-key": settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": script,
                    "model_id": settings.ELEVENLABS_MODEL_ID,
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return _parse_response(data, effective_voice_id, script)

        except httpx.TimeoutException as e:
            last_error = e
            logger.warning(
                "ElevenLabs timeout tentative %d/%d",
                attempt + 1,
                settings.ELEVENLABS_MAX_RETRIES,
            )
        except httpx.HTTPStatusError as e:
            last_error = e
            logger.warning(
                "ElevenLabs HTTP %d tentative %d/%d",
                e.response.status_code,
                attempt + 1,
                settings.ELEVENLABS_MAX_RETRIES,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "ElevenLabs erreur tentative %d/%d : %s",
                attempt + 1,
                settings.ELEVENLABS_MAX_RETRIES,
                e,
            )

        if attempt < settings.ELEVENLABS_MAX_RETRIES - 1:
            # attempt=0 → 5s * 1 = 5s, attempt=1 → 5s * 2 = 10s
            delay = settings.ELEVENLABS_BACKOFF_BASE * (2 ** attempt)
            logger.info("ElevenLabs retry dans %.0fs...", delay)
            await asyncio.sleep(delay)

    if isinstance(last_error, httpx.TimeoutException):
        raise ElevenLabsTimeoutError(
            f"ElevenLabs timeout après {settings.ELEVENLABS_MAX_RETRIES} tentatives"
        )
    raise ElevenLabsAPIError(
        f"ElevenLabs échec après {settings.ELEVENLABS_MAX_RETRIES} tentatives : {last_error}"
    )


def _parse_response(data: dict, voice_id: str, script: str) -> ElevenLabsResult:
    """Parse la réponse ElevenLabs, sauvegarde le MP3, construit les timestamps."""
    audio_bytes = base64.b64decode(data["audio_base64"])
    audio_path = _save_audio(audio_bytes)

    alignment = data.get("normalized_alignment", {})
    timestamps = _build_word_timestamps(alignment)

    # Durée réelle = fin du dernier mot ; fallback estimé si aucun timestamp
    duration_ms = (
        int(max(t.end_ms for t in timestamps))
        if timestamps
        else len(script) * 60  # ~60ms par caractère, estimation grossière
    )

    return ElevenLabsResult(
        audio_path=audio_path,
        audio_duration_ms=duration_ms,
        timestamps=timestamps,
        voice_id=voice_id,
        character_count=len(script),
    )


def _save_audio(audio_bytes: bytes) -> str:
    """Sauvegarde les octets MP3 sur le disque, retourne le chemin absolu."""
    Path(AUDIO_STORAGE_DIR).mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}.mp3"
    path = os.path.join(AUDIO_STORAGE_DIR, filename)
    with open(path, "wb") as f:
        f.write(audio_bytes)
    return path


def _build_word_timestamps(alignment: dict) -> list[WordTimestamp]:
    """
    Convertit le format caractère par caractère d'ElevenLabs en mots.

    ElevenLabs retourne les timestamps char par char — on regroupe par espaces
    pour obtenir des WordTimestamp avec start_ms/end_ms en millisecondes.
    """
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if not chars:
        return []

    words: list[WordTimestamp] = []
    current_word = ""
    word_start_ms = 0
    word_end_ms = 0  # track last letter's end time

    for char, start_s, end_s in zip(chars, starts, ends):
        if char in (" ", "\n"):
            if current_word:
                words.append(WordTimestamp(
                    word=current_word,
                    start_ms=word_start_ms,
                    end_ms=word_end_ms,  # last letter's end, not space's end
                ))
                current_word = ""
        else:
            if not current_word:
                word_start_ms = int(start_s * 1000)
            word_end_ms = int(end_s * 1000)
            current_word += char

    # Dernier mot sans espace final
    if current_word:
        words.append(WordTimestamp(
            word=current_word,
            start_ms=word_start_ms,
            end_ms=word_end_ms,
        ))

    return words
