"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Responsabilités :
  - Regrouper les timestamps mot-par-mot ElevenLabs en chunks d'affichage
  - Découpage intelligent : coupure à la ponctuation (., !, ?, ,) pour des
    lignes qui respectent le rythme naturel de la voix off
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
        "font_size": "9 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.7 vmin",
        "y": "72%",
        "width": "88%",
        "background_color": None,
    },
    SubtitleStyle.CLASSIQUE: {
        "words_per_chunk": 5,
        "font_family": "Open Sans",
        "font_weight": "700",
        "font_size": "5.5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.3 vmin",
        "y": "86%",
        "width": "90%",
        "background_color": "rgba(0,0,0,0.6)",
        "background_x_padding": "3%",
        "background_y_padding": "1.5%",
        "background_border_radius": "0.5 vmin",
    },
    SubtitleStyle.CINEMA: {
        "words_per_chunk": 6,
        "font_family": "Georgia",
        "font_weight": "400",
        "font_size": "4.5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.2 vmin",
        "y": "87%",
        "width": "82%",
        "background_color": None,
    },
}


def build_subtitle_elements(
    timestamps: list[WordTimestamp],
    style: SubtitleStyle,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate pour les sous-titres.

    Découpage intelligent : les coupures sont faites en priorité aux fins de
    phrase (. ! ?) et de clause (, ; :), pour des sous-titres qui suivent
    le rythme naturel de la voix off plutôt qu'un compte fixe de mots.

    Args:
        timestamps: Liste de WordTimestamp depuis ElevenLabs.
        style:      Style visuel (TIKTOK / CLASSIQUE / CINEMA).
        track:      Track Creatomate (défaut : 6).

    Returns:
        Liste de dicts prêts à injecter dans le payload Creatomate.
    """
    if not timestamps:
        return []

    cfg = _STYLE_CONFIGS[style]
    chunks = _group_words_smart(timestamps, cfg["words_per_chunk"])
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


# ── Helpers ──────────────────────────────────────────────────────────────────

def _group_words_smart(
    timestamps: list[WordTimestamp],
    words_per_chunk: int,
) -> list[dict[str, Any]]:
    """
    Regroupe les mots en chunks en respectant la ponctuation naturelle.

    Priorité de coupure :
      1. Fin de phrase (. ! ? …) si ≥ 2 mots → coupure immédiate
      2. Pause logique (, ; : —)  si ≥ 3 mots → coupure immédiate
      3. Limite de taille (words_per_chunk)     → coupure forcée
    """
    chunks: list[dict[str, Any]] = []
    current_group: list[WordTimestamp] = []

    for ts in timestamps:
        current_group.append(ts)
        word = ts.word.strip()

        ends_sentence = bool(word) and word[-1] in ".!?…"
        ends_clause   = bool(word) and word[-1] in ",;:—"

        should_break = (
            len(current_group) >= words_per_chunk
            or (ends_sentence and len(current_group) >= 2)
            or (ends_clause   and len(current_group) >= 3)
        )

        if should_break:
            _flush(current_group, chunks)
            current_group = []

    if current_group:
        _flush(current_group, chunks)

    return chunks


def _flush(group: list[WordTimestamp], chunks: list[dict]) -> None:
    """Convertit un groupe de WordTimestamp en dict de chunk."""
    chunks.append({
        "text":       " ".join(w.word for w in group),
        "start_s":    group[0].start_ms  / 1000.0,
        "duration_s": (group[-1].end_ms - group[0].start_ms) / 1000.0,
    })
