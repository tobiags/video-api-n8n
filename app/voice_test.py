"""
voice_test.py — Test de vitesse voix off (audio uniquement, 0 crédit Creatomate)

Endpoint :
  POST /test-voice-speed

Génère 4 fichiers audio ElevenLabs aux vitesses 1.0 / 1.2 / 1.5 / 2.0
et retourne leurs URLs publiques. Théo écoute, choisit, puis lance UNE
vidéo complète avec la valeur choisie dans voice_speed.

Pourquoi 0 crédit Creatomate : aucun rendu vidéo, uniquement ElevenLabs.
"""
import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.elevenlabs import generate_voiceover

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice-test"])

# Vitesses de test : 1.0, 1.2 (max ElevenLabs natif), 1.5, 2.0
# Pour 1.5 et 2.0 : ElevenLabs tourne à 1.2, l'audio sera accéléré côté Creatomate
# mais pour ce test on compare juste les voix à 1.0 et 1.2 natif + indication
_TEST_SPEEDS = [1.0, 1.2, 1.5, 2.0]


class VoiceSpeedTestRequest(BaseModel):
    """Payload pour POST /test-voice-speed."""
    script: str = Field(..., min_length=10, description="Texte à synthétiser (extrait ou script complet)")
    voice_id: str = Field(..., description="ID du clone vocal ElevenLabs")


class VoiceSpeedTestResult(BaseModel):
    """Un fichier audio généré pour une vitesse donnée."""
    speed: float
    elevenlabs_speed: float  # Vitesse réelle envoyée à ElevenLabs (max 1.2)
    creatomate_multiplier: float  # Multiplicateur Creatomate supplémentaire (si speed > 1.2)
    audio_url: str
    duration_seconds: float


class VoiceSpeedTestResponse(BaseModel):
    results: list[VoiceSpeedTestResult]
    note: str = (
        "Écoutez les 4 versions et choisissez la meilleure. "
        "Ensuite, ajoutez 'voice_speed': <valeur> dans le payload n8n. "
        "Pour speed=1.5 et 2.0, la voix ElevenLabs est à 1.2 natif — "
        "la différence finale sera obtenue par accélération Creatomate lors du rendu vidéo."
    )


@router.post("/test-voice-speed", response_model=VoiceSpeedTestResponse)
async def test_voice_speed(
    body: VoiceSpeedTestRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
) -> VoiceSpeedTestResponse:
    """
    Génère 4 fichiers audio aux vitesses 1.0 / 1.2 / 1.5 / 2.0.
    Aucun rendu Creatomate = 0 crédit Creatomate consommé.
    """
    http_client = request.app.state.http_client
    api_base = settings.API_BASE_URL.rstrip("/") if settings.API_BASE_URL else ""

    async def _generate_one(speed: float) -> VoiceSpeedTestResult:
        eleven_speed = min(speed, 1.2)
        creatomate_mult = round(speed / eleven_speed, 4) if speed > 1.2 else 1.0

        result = await generate_voiceover(
            script=body.script,
            voice_id=body.voice_id,
            http_client=http_client,
            settings=settings,
            voice_speed=speed,
        )
        audio_filename = Path(result.audio_path).name
        audio_url = (
            f"{api_base}/audio/{audio_filename}"
            if api_base
            else f"file://{result.audio_path}"
        )
        return VoiceSpeedTestResult(
            speed=speed,
            elevenlabs_speed=eleven_speed,
            creatomate_multiplier=creatomate_mult,
            audio_url=audio_url,
            duration_seconds=result.audio_duration_seconds,
        )

    # Génération séquentielle pour éviter le rate-limiting ElevenLabs
    results: list[VoiceSpeedTestResult] = []
    for speed in _TEST_SPEEDS:
        logger.info("Génération audio vitesse %.2f...", speed)
        res = await _generate_one(speed)
        results.append(res)
        logger.info("  → %.1fs audio à speed=%.2f", res.duration_seconds, speed)

    return VoiceSpeedTestResponse(results=results)
