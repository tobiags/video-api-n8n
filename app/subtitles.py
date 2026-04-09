"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Responsabilités :
  - Regrouper les timestamps mot-par-mot ElevenLabs en chunks d'affichage
  - Construire les éléments text Creatomate avec timing précis (ms → s)
  - Appliquer le style choisi (TikTok / Classique / Cinéma)

Les sous-titres s'intègrent sur le Track 6 de la composition Creatomate.
"""
from __future__ import annotations

from typing import Any

from app.models import SubtitleStyle, WordTimestamp


# ── Configurations visuelles par style ──────────────────────────────────────

_STYLE_CONFIGS: dict[SubtitleStyle, dict[str, Any]] = {
    SubtitleStyle.TIKTOK: {
        "words_per_chunk": 3,
        "font_family": "Montserrat",
        "font_weight": "900",
        "font_size": "8 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.6 vmin",
        "y": "70%",
        "width": "88%",
        "background_color": None,
    },
    SubtitleStyle.CLASSIQUE: {
        "words_per_chunk": 5,
        "font_family": "Open Sans",
        "font_weight": "600",
        "font_size": "5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.3 vmin",
        "y": "88%",
        "width": "90%",
        "background_color": "rgba(0,0,0,0.55)",
        "background_x_padding": "3%",
        "background_y_padding": "1.5%",
        "background_border_radius": "0.5 vmin",
    },
    SubtitleStyle.CINEMA: {
        "words_per_chunk": 7,
        "font_family": "Georgia",
        "font_weight": "400",
        "font_size": "4 vmin",
        "fill_color": "#ffffff",
        "stroke_color": None,
        "stroke_width": None,
        "y": "91%",
        "width": "80%",
        "background_color": None,
        "letter_spacing": "5%",
        "font_style": "italic",
    },
}


def build_subtitle_elements(
    timestamps: list[WordTimestamp],
    style: SubtitleStyle,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate pour les sous-titres.

    Args:
        timestamps: Liste de WordTimestamp (mot + start_ms + end_ms) depuis ElevenLabs.
        style:      Style visuel choisi (TIKTOK / CLASSIQUE / CINEMA).
        track:      Numéro de track Creatomate (défaut : 6).

    Returns:
        Liste de dicts prêts à être injectés dans le payload Creatomate.
    """
    if not timestamps:
        return []

    cfg = _STYLE_CONFIGS[style]
    chunks = _group_words(timestamps, cfg["words_per_chunk"])
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

        if cfg.get("letter_spacing"):
            el["letter_spacing"] = cfg["letter_spacing"]

        if cfg.get("font_style"):
            el["font_style"] = cfg["font_style"]

        elements.append(el)

    return elements


def _group_words(
    timestamps: list[WordTimestamp],
    words_per_chunk: int,
) -> list[dict[str, Any]]:
    """Regroupe les timestamps mot par mot en chunks d'affichage."""
    chunks = []
    for i in range(0, len(timestamps), words_per_chunk):
        group = timestamps[i : i + words_per_chunk]
        if not group:
            continue
        chunks.append({
            "text": " ".join(w.word for w in group),
            "start_s": group[0].start_ms / 1000.0,
            "duration_s": (group[-1].end_ms - group[0].start_ms) / 1000.0,
        })
    return chunks
