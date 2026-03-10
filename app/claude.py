"""
claude.py — Module d'analyse script + génération prompts B-roll (PRD §4.1)

Responsabilités :
  - Découper le script en N sections de ~5 secondes
  - Générer un prompt B-roll Kling-compatible pour chaque section
  - Valider la structure JSON (somme durées == total_duration)
  - Relancer avec contexte d'erreur si JSON invalide (PRD §5.1)
"""
import json
import logging
import re

import anthropic
import httpx
from pydantic import ValidationError

from app.config import Settings
from app.errors import ClaudeAPIError, ClaudeInvalidJSONError
from app.models import ScriptAnalysis, VideoFormat

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Tu es un expert en publicité vidéo. Ton rôle est de découper un script
publicitaire en sections temporelles et de générer un prompt B-roll Kling pour chaque section.

RÈGLES STRICTES :
1. Chaque section dure exactement {clip_duration} secondes
2. La somme de toutes les durées doit être exactement égale à {total_duration} secondes
3. Chaque broll_prompt doit inclure le ratio {aspect_ratio}, le style visuel, l'action et le cadrage
4. Retourne UNIQUEMENT un objet JSON valide, sans markdown, sans commentaires
5. Les keywords DOIVENT être en ANGLAIS et décrire précisément la SCÈNE VISUELLE pour une recherche
   stock vidéo Pexels. Sois spécifique et cohérent avec le sujet exact du script.
   ✓ CORRECT   : ["luxury apartment interior tour", "couple signing lease contract", "real estate agent showing home"]
   ✗ INTERDIT  : ["appartement", "gens", "immobilier", "product", "person", "happy", "lifestyle"]

SCHÉMA JSON REQUIS :
{{
  "total_duration": <int>,
  "sections": [
    {{
      "id": <int>,
      "text": "<texte narré>",
      "start": <int secondes>,
      "end": <int secondes>,
      "duration": <int secondes>,
      "broll_prompt": "<prompt Kling complet avec ratio {aspect_ratio}>",
      "keywords": ["<english specific visual scene 1>", "<english specific visual scene 2>", "<english specific visual scene 3>"],
      "scene_type": "<emotion|product|testimonial|cta|ambient|tutorial>"
    }}
  ]
}}"""

_USER_PROMPT = """Script à découper ({total_duration} secondes, format {aspect_ratio}) :

{script}"""

_RETRY_PROMPT = """Ton JSON précédent était invalide. Erreur : {error}

Reprends l'analyse et retourne UNIQUEMENT un JSON valide respectant strictement le schéma.
La somme des durées DOIT être exactement {total_duration} secondes."""


async def analyze_script(
    script: str,
    format_: VideoFormat,
    duration: int,
    aspect_ratio: str,
    http_client: httpx.AsyncClient,
    settings: Settings,
) -> ScriptAnalysis:
    """
    Appelle Claude pour découper le script en sections temporelles
    avec un prompt B-roll par section.

    Retourne un ScriptAnalysis validé (somme durées == duration).
    Retry jusqu'à CLAUDE_MAX_RETRIES fois si JSON invalide (PRD §5.1).

    Args:
        script:       Script publicitaire brut
        format_:      VideoFormat.VERTICAL (9:16) ou HORIZONTAL (16:9)
        duration:     Durée cible en secondes (90/120/180)
        aspect_ratio: "9:16" ou "16:9" (injecté dans les prompts B-roll)
        http_client:  Client HTTP partagé (httpx.AsyncClient)
        settings:     Configuration application

    Returns:
        ScriptAnalysis avec sections validées

    Raises:
        ClaudeAPIError:         Erreur API Anthropic
        ClaudeInvalidJSONError: JSON invalide après N tentatives
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key, http_client=http_client)
    messages = [
        {
            "role": "user",
            "content": _USER_PROMPT.format(
                total_duration=duration,
                aspect_ratio=aspect_ratio,
                script=script,
            ),
        }
    ]
    system = _SYSTEM_PROMPT.format(
        clip_duration=settings.KLING_DURATION,
        total_duration=duration,
        aspect_ratio=aspect_ratio,
    )
    last_error: Exception | None = None
    raw: str = ""

    for attempt in range(settings.CLAUDE_MAX_RETRIES):
        try:
            response = await client.messages.create(
                model=settings.CLAUDE_MODEL,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                system=system,
                messages=messages,
            )
            raw = response.content[0].text.strip()

            # Clean up optional markdown ```json ... ``` block (M-1)
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
            if match:
                raw = match.group(1)

            data = json.loads(raw)
            analysis = ScriptAnalysis(**data)
            logger.info(
                "Claude OK — %d sections, durée %ds (tentative %d)",
                analysis.section_count,
                analysis.total_duration,
                attempt + 1,
            )
            return analysis

        except anthropic.APIError as e:
            # I-1: non-retryable API errors (HTTP 401, 500, rate-limit, …)
            raise ClaudeAPIError(f"Erreur API Anthropic : {e}") from e

        except (json.JSONDecodeError, ValidationError, Exception) as e:
            last_error = e
            logger.warning(
                "Claude tentative %d/%d échouée : %s",
                attempt + 1,
                settings.CLAUDE_MAX_RETRIES,
                e,
            )
            if attempt < settings.CLAUDE_MAX_RETRIES - 1:
                messages.append({"role": "assistant", "content": raw})  # M-2
                messages.append(
                    {
                        "role": "user",
                        "content": _RETRY_PROMPT.format(
                            error=str(e),
                            total_duration=duration,
                        ),
                    }
                )

    raise ClaudeInvalidJSONError(
        f"Claude a retourné un JSON invalide après {settings.CLAUDE_MAX_RETRIES} tentatives. "
        f"Dernière erreur : {last_error}"
    )
