"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Approche mot-par-mot :
  - Utilise les timestamps ElevenLabs (un timestamp par mot)
  - Les mots sont groupés en chunks de N mots selon le style
  - Chaque chunk apparaît exactement au bon moment (synchronisé avec la parole)
  - Texte blanc, centré, positionné en bas de la vidéo
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
        "font_size": "6 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.5 vmin",
        "y": "85%",
        "width": "80%",
    },
    SubtitleStyle.CLASSIQUE: {
        "words_per_chunk": 5,
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
        "words_per_chunk": 6,
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
    audio_speed: float = 1.0,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate synchronisés mot par mot.

    Les timestamps ElevenLabs (en ms depuis le début de l'audio) sont
    convertis en temps vidéo en divisant par audio_speed.
    Les mots sont regroupés en chunks de N mots selon le style.
    Chaque chunk apparaît quand le premier mot est prononcé et disparaît
    quand le chunk suivant commence.

    Args:
        timestamps:  Liste de WordTimestamp (start_ms, end_ms, word)
        style:       Style visuel (tiktok / classique / cinema)
        audio_speed: Multiplicateur de vitesse audio (Creatomate speed)
        track:       Numéro de piste Creatomate (défaut 6)

    Returns:
        Liste d'éléments dict prêts à être ajoutés au payload Creatomate
    """
    if not timestamps:
        return []

    cfg = _STYLE_CONFIGS[style]
    words_per_chunk: int = cfg.get("words_per_chunk", 3)
    elements: list[dict[str, Any]] = []

    # Grouper les mots en chunks de N
    chunks = [
        timestamps[i : i + words_per_chunk]
        for i in range(0, len(timestamps), words_per_chunk)
    ]

    for idx, chunk in enumerate(chunks):
        # Temps de départ : premier mot du chunk (ms → secondes vidéo)
        start_s = chunk[0].start_ms / 1000.0 / audio_speed

        # Durée : jusqu'au début du chunk suivant, ou fin du dernier mot + 0.3s
        if idx + 1 < len(chunks):
            end_s = chunks[idx + 1][0].start_ms / 1000.0 / audio_speed
        else:
            end_s = chunk[-1].end_ms / 1000.0 / audio_speed + 0.3

        duration_s = max(round(end_s - start_s, 3), 0.1)
        text = " ".join(w.word for w in chunk)

        el: dict[str, Any] = {
            "type": "text",
            "track": track,
            "time": round(start_s, 3),
            "duration": duration_s,
            "text": text,
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
