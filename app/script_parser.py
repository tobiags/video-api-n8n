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


# ── Full parser regex ────────────────────────────────────────────────────────
# Captures: plan_num, start, end, label, voice_text, kling_prompt
_PLAN_FULL_RE = re.compile(
    r"PLAN\s+(\d+)\s*\((\d+)\s*[–\-]\s*(\d+)s\)\s*[—–\-]+\s*(.+?)\s*\n"
    r"\s*🎙\s*[\"«](.+?)[\"»]\s*\n"
    r"\s*🎬\s*(.+?)(?=\nPLAN\s|\Z)",
    re.DOTALL | re.IGNORECASE,
)

# ── Stop words for keyword extraction ────────────────────────────────────────
_STOP_WORDS = frozenset({
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "is", "are", "was",
    "were", "be", "been", "being", "with", "and", "or", "but", "not", "by",
    "from", "as", "into", "through", "his", "her", "its", "their", "our",
    "your", "my", "this", "that", "these", "those", "up", "out", "off",
    "over", "under", "between", "he", "she", "it", "they", "we", "you",
    "who", "which", "what", "where", "when", "how", "all", "each", "every",
    "both", "few", "more", "most", "other", "some", "such", "no", "nor",
    "than", "too", "very", "just", "also",
})

_CINEMA_WORDS = frozenset({
    "cinematic", "dramatic", "vertical", "horizontal", "format", "shallow",
    "depth", "field", "slow", "motion", "close", "medium", "wide", "shot",
    "angle", "tones", "lighting", "light", "mood", "atmosphere", "aesthetic",
    "style", "feel", "look", "warm", "cold", "cool", "soft", "harsh",
    "natural", "artificial", "backlight", "desaturated", "blurred",
    "bokeh", "perspective", "dynamic", "static", "pan", "zoom",
})

# ── Scene type mapping ───────────────────────────────────────────────────────
_SCENE_TYPE_MAP: dict[str, SceneType] = {
    "HOOK": SceneType.EMOTION,
    "AVANT": SceneType.EMOTION,
    "DOULEUR": SceneType.EMOTION,
    "FRUSTRATION": SceneType.EMOTION,
    "DÉCOUVERTE": SceneType.AMBIENT,
    "DECOUVERTE": SceneType.AMBIENT,
    "MÉCANISME": SceneType.AMBIENT,
    "MECANISME": SceneType.AMBIENT,
    "TRANSFORMATION": SceneType.TESTIMONIAL,
    "RÉSULTAT": SceneType.TESTIMONIAL,
    "RESULTAT": SceneType.TESTIMONIAL,
    "SOCIAL PROOF": SceneType.TESTIMONIAL,
    "CTA": SceneType.CTA,
}


def _extract_keywords(broll_prompt: str, max_keywords: int = 3) -> list[str]:
    """Extrait jusqu'à 3 mots-clés anglais significatifs du prompt Kling."""
    # Tokenize: split on whitespace + punctuation, lowercase, split hyphens
    tokens = re.findall(r"[a-zA-Z]+", broll_prompt.lower())
    # Filter stop words and cinema jargon
    significant = [
        t for t in tokens
        if t not in _STOP_WORDS and t not in _CINEMA_WORDS and len(t) > 2
    ]
    return significant[:max_keywords]


def _map_scene_type(label: str) -> SceneType:
    """Mappe le label du plan vers un SceneType. Fallback: AMBIENT."""
    normalized = label.strip().upper()
    return _SCENE_TYPE_MAP.get(normalized, SceneType.AMBIENT)


def parse_preformatted(script: str, format_: VideoFormat) -> ScriptAnalysis:
    """Parse le script pré-découpé en ScriptAnalysis (synchrone, pas d'I/O).

    Le caller ne doit PAS l'awaiter — c'est une fonction synchrone pure CPU.
    total_duration est calculé comme sum(section.duration), dérivé des timestamps.

    Raises:
        ScriptParserError: si le format est malformé.
    """
    matches = list(_PLAN_FULL_RE.finditer(script))

    if len(matches) < 2:
        raise ScriptParserError(
            f"Script pré-découpé invalide : {len(matches)} plan(s) trouvé(s), minimum 2 requis"
        )

    sections: list[ScriptSection] = []

    for m in matches:
        plan_num = int(m.group(1))
        start = int(m.group(2))
        end = int(m.group(3))
        label = m.group(4).strip()
        voice_text = m.group(5).strip()
        kling_prompt = m.group(6).strip()

        # Validate timestamps
        if end <= start:
            raise ScriptParserError(
                f"Plan {plan_num} : timestamps invalides (end {end}s <= start {start}s)"
            )

        # Validate non-empty content
        if not voice_text:
            raise ScriptParserError(f"Plan {plan_num} : texte voix off vide après 🎙")
        if not kling_prompt or len(kling_prompt) < 10:
            raise ScriptParserError(f"Plan {plan_num} : prompt Kling vide après 🎬")

        sections.append(
            ScriptSection(
                id=plan_num,
                text=voice_text,
                start=start,
                end=end,
                duration=end - start,
                broll_prompt=kling_prompt,
                keywords=_extract_keywords(kling_prompt),
                scene_type=_map_scene_type(label),
            )
        )

    # Sort by plan number to ensure order
    sections.sort(key=lambda s: s.id)

    # Validate contiguous timestamps
    for i in range(1, len(sections)):
        prev = sections[i - 1]
        curr = sections[i]
        if curr.start < prev.end:
            raise ScriptParserError(
                f"Plans {prev.id}-{curr.id} : timestamps se chevauchent "
                f"(plan {prev.id} finit à {prev.end}s, plan {curr.id} commence à {curr.start}s)"
            )
        if curr.start > prev.end:
            gap = curr.start - prev.end
            raise ScriptParserError(
                f"Plans {prev.id}-{curr.id} : timestamps non-contigus (gap de {gap}s)"
            )

    total_duration = sum(s.duration for s in sections)

    logger.info(
        "Script pré-découpé parsé : %d plans, durée totale %ds",
        len(sections), total_duration,
    )

    return ScriptAnalysis(
        total_duration=total_duration,
        sections=sections,
        source="parser",
    )
