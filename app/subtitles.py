"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Approche de segmentation :
  - Détection des pauses naturelles entre mots (gap > PAUSE_THRESHOLD_MS)
    → ne dépend PAS de la ponctuation dans les timestamps ElevenLabs
  - Limite de mots max par chunk (fallback)
  - Les deux conditions combinées → coupures naturelles et professionnelles
"""
from __future__ import annotations
from typing import Any
from app.models import SubtitleStyle, WordTimestamp

# Seuil de pause entre deux mots pour considérer une fin de phrase (ms)
PAUSE_THRESHOLD_MS = 200

# ── Configurations visuelles par style ──────────────────────────────────────

_STYLE_CONFIGS: dict[SubtitleStyle, dict[str, Any]] = {
    SubtitleStyle.TIKTOK: {
        "words_per_chunk": 3,
        "font_family": "Montserrat",
        "font_weight": "900",
        "font_size": "6 vmin",
        "fill_color": "#ffff00",
        "stroke_color": "#000000",
        "stroke_width": "0.5 vmin",
        "y": "85%",
        "width": "80%",
    },
    SubtitleStyle.CLASSIQUE: {
        "words_per_chunk": 6,
        "font_family": "Montserrat",
        "font_weight": "700",
        "font_size": "4 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.3 vmin",
        "y": "90%",
        "width": "85%",
        "background_color": "rgba(0,0,0,0.55)",
        "background_x_padding": "2%",
        "background_y_padding": "1%",
        "background_border_radius": "0.4 vmin",
    },
    SubtitleStyle.CINEMA: {
        "words_per_chunk": 7,
        "font_family": "Montserrat",
        "font_weight": "300",
        "font_size": "3 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.15 vmin",
        "y": "92%",
        "width": "75%",
    },
}


def build_subtitle_elements(
    timestamps: list[WordTimestamp],
    style: SubtitleStyle,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate.

    La segmentation utilise les pauses naturelles entre mots (≥ PAUSE_THRESHOLD_MS)
    plutôt que la ponctuation — plus robuste car indépendant du format ElevenLabs.
    """
    if not timestamps:
        return []

    cfg = _STYLE_CONFIGS[style]
    chunks = _segment_by_pause(timestamps, cfg["words_per_chunk"])
    elements: list[dict[str, Any]] = []

    for chunk in chunks:
        if chunk["duration_s"] < 0.05:
            continue

        el: dict[str, Any] = {
            "type": "text",
            "track": track,
            "time": round(chunk["start_s"], 3),
            "duration": round(chunk["duration_s"], 3),
            "text": chunk["text"],
            "font_family": cfg["font_family"],
            "font_weight": cfg["font_weight"],
            "font_size": cfg["font_size"],
            "fill_color": cfg["fill_color"],
            "x": "50%",
            "y": cfg["y"],
            "width": cfg["width"],
            "x_anchor": "50%",
            "y_anchor": "50%",
            "text_align": "center",
        }

        if cfg.get("stroke_color"):
            el["stroke_color"] = cfg["stroke_color"]
            el["stroke_width"] = cfg["stroke_width"]

        if cfg.get("background_color"):
            el["background_color"] = cfg["background_color"]
            if "background_x_padding" in cfg:
                el["background_x_padding"] = cfg["background_x_padding"]
            if "background_y_padding" in cfg:
                el["background_y_padding"] = cfg["background_y_padding"]
            if "background_border_radius" in cfg:
                el["background_border_radius"] = cfg["background_border_radius"]

        elements.append(el)

    return elements


def _segment_by_pause(
    timestamps: list[WordTimestamp],
    words_per_chunk: int,
) -> list[dict[str, Any]]:
    """
    Segmente les mots en chunks selon deux critères :
      1. Pause naturelle entre mots (gap ≥ PAUSE_THRESHOLD_MS) si ≥ 2 mots
      2. Limite max de mots (words_per_chunk)

    Les pauses naturelles correspondent aux fins de phrases/clauses dans la
    synthèse vocale ElevenLabs — méthode fiable indépendante de la ponctuation.
    """
    chunks: list[dict[str, Any]] = []
    group: list[WordTimestamp] = []

    for i, ts in enumerate(timestamps):
        if not ts.word.strip():
            continue
        group.append(ts)

        # Calcul du gap avec le mot suivant
        is_last = (i == len(timestamps) - 1)
        next_gap_ms = 0
        if not is_last:
            # Cherche le prochain mot non-vide
            for j in range(i + 1, len(timestamps)):
                if timestamps[j].word.strip():
                    next_gap_ms = timestamps[j].start_ms - ts.end_ms
                    break

        has_pause = (not is_last) and (next_gap_ms >= PAUSE_THRESHOLD_MS)

        should_break = (
            is_last
            or len(group) >= words_per_chunk
            or (has_pause and len(group) >= 2)
        )

        if should_break:
            chunks.append({
                "text":       " ".join(w.word for w in group),
                "start_s":    group[0].start_ms / 1000.0,
                "duration_s": (group[-1].end_ms - group[0].start_ms) / 1000.0,
            })
            group = []

    return chunks
