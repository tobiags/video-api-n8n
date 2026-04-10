"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Approche :
  - 1 section du script = 1 sous-titre affiché pendant toute la durée du plan
  - Le texte complet de la section est affiché d'un bloc (pas de découpage mot par mot)
  - La durée du sous-titre correspond exactement à la durée du clip de la section
"""
from __future__ import annotations
from typing import Any
from app.models import ScriptSection, SubtitleStyle

# ── Configurations visuelles par style ──────────────────────────────────────

_STYLE_CONFIGS: dict[SubtitleStyle, dict[str, Any]] = {
    SubtitleStyle.TIKTOK: {
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
    sections: list[ScriptSection],
    section_durations: dict[int, float],
    style: SubtitleStyle,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate : 1 élément par section du script.

    Chaque sous-titre affiche le texte COMPLET de la section pendant toute
    la durée du plan (section_durations[section.id]).
    Les sections sont triées par id pour recalculer les temps de départ cumulatifs.
    """
    if not sections or not section_durations:
        return []

    cfg = _STYLE_CONFIGS[style]
    elements: list[dict[str, Any]] = []

    # Calcul des temps de départ cumulatifs dans l'ordre des sections
    current_time = 0.0
    for section in sorted(sections, key=lambda s: s.id):
        duration = section_durations.get(section.id)
        if duration is None or duration < 0.05:
            if duration:
                current_time += duration
            continue

        text = section.text.strip()
        if not text:
            current_time += duration
            continue

        el: dict[str, Any] = {
            "type": "text",
            "track": track,
            "time": round(current_time, 3),
            "duration": round(duration, 3),
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
        current_time += duration

    return elements
