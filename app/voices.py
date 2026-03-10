"""
voices.py — Catalogue et vérification des voix ElevenLabs

Responsabilités :
  - Charger la liste des voice_ids approuvés depuis voices_catalog.json
  - Fetcher les métadonnées (nom, genre, accent, preview) depuis l'API ElevenLabs
  - Exposé via GET /voices et GET /voices/{voice_id}
"""
import asyncio
import json
import logging
from pathlib import Path

import httpx
from pydantic import BaseModel

from app.config import Settings

logger = logging.getLogger(__name__)

CATALOG_PATH = Path(__file__).parent / "voices_catalog.json"


class VoiceInfo(BaseModel):
    """Métadonnées d'une voix ElevenLabs, retournées par GET /voices."""
    voice_id: str
    name: str
    gender: str | None = None       # "male" / "female"
    accent: str | None = None       # "american", "british", "french", …
    description: str | None = None  # description libre (ton, style)
    age: str | None = None          # "young" / "middle aged" / "old"
    use_case: str | None = None     # "narration", "conversational", …
    preview_url: str | None = None  # URL MP3 d'aperçu
    available: bool = True          # False si l'API retourne une erreur (ID invalide, etc.)


def load_catalog() -> list[str]:
    """Charge la liste des voice_ids depuis voices_catalog.json."""
    if not CATALOG_PATH.exists():
        logger.warning("voices_catalog.json introuvable : %s", CATALOG_PATH)
        return []
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        return data.get("voices", [])
    except Exception as e:
        logger.error("Erreur lecture voices_catalog.json : %s", e)
        return []


async def fetch_voice_info(
    voice_id: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> VoiceInfo:
    """
    Fetche les métadonnées d'une voix depuis l'API ElevenLabs.

    Retourne un VoiceInfo avec available=False si l'ID est inconnu ou inaccessible.
    """
    try:
        resp = await http_client.get(
            f"{settings.ELEVENLABS_BASE_URL}/voices/{voice_id}",
            headers={"xi-api-key": settings.elevenlabs_api_key},
            timeout=10.0,
        )
        if not resp.is_success:
            logger.warning("ElevenLabs GET /voices/%s → HTTP %d", voice_id, resp.status_code)
            return VoiceInfo(
                voice_id=voice_id,
                name=f"Voix inaccessible ({voice_id[:8]}…)",
                available=False,
            )
        data = resp.json()
        labels: dict = data.get("labels", {})
        return VoiceInfo(
            voice_id=voice_id,
            name=data.get("name", ""),
            gender=labels.get("gender"),
            accent=labels.get("accent"),
            description=labels.get("description"),
            age=labels.get("age"),
            use_case=labels.get("use case"),  # ElevenLabs utilise "use case" avec espace
            preview_url=data.get("preview_url"),
            available=True,
        )
    except Exception as e:
        logger.error("Erreur fetch voice %s : %s", voice_id, e)
        return VoiceInfo(
            voice_id=voice_id,
            name=f"Erreur ({voice_id[:8]}…)",
            available=False,
        )


async def list_catalog_voices(
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> list[VoiceInfo]:
    """
    Retourne les métadonnées de toutes les voix listées dans voices_catalog.json.
    Les appels ElevenLabs sont faits en parallèle.
    """
    voice_ids = load_catalog()
    if not voice_ids:
        return []
    tasks = [fetch_voice_info(vid, http_client, settings) for vid in voice_ids]
    results = await asyncio.gather(*tasks)
    # Trier : voix disponibles en premier, puis par genre (female avant male), puis par nom
    return sorted(
        results,
        key=lambda v: (not v.available, v.gender or "zzz", v.name.lower()),
    )
