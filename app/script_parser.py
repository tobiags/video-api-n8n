"""
script_parser.py — Détection et parsing des scripts pré-découpés (format PLAN/🎙/🎬)

Quand le client fournit un script pré-découpé avec ses propres prompts Kling,
ce module bypasse Claude et retourne directement un ScriptAnalysis.

Spec : docs/superpowers/specs/2026-03-12-preformatted-script-parser-design.md
"""
import re
import logging

from app.errors import ScriptParserError
from app.models import SceneType, ScriptAnalysis, ScriptSection, VideoFormat

logger = logging.getLogger(__name__)

# Regex pour détecter un bloc PLAN complet (header + 🎙 + 🎬)
# Accepte hyphen (-), en-dash (–), em-dash (—) pour les timestamps et le séparateur
_PLAN_BLOCK_RE = re.compile(
    r"PLAN\s+\d+\s*\(\d+\s*[–\-]\s*\d+s\)\s*[—–\-]+\s*\S+",
    re.IGNORECASE,
)


def detect_preformatted(script: str) -> bool:
    """Retourne True si au moins 2 blocs PLAN avec 🎙 + 🎬 sont trouvés.

    Le seuil de 2 blocs évite les faux positifs sur un script qui contiendrait
    le mot 'PLAN' une seule fois par hasard.
    """
    # Cherche les blocs qui ont les 3 composants : PLAN header + 🎙 + 🎬
    blocks = _PLAN_BLOCK_RE.findall(script)
    if len(blocks) < 2:
        return False
    # Vérifier que 🎙 et 🎬 apparaissent aussi
    mic_count = script.count("🎙")
    cam_count = script.count("🎬")
    return mic_count >= 2 and cam_count >= 2
