"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Approche hybride DaVinci Resolve + CapCut :

  1. SEGMENTATION (style DaVinci Resolve) :
     - Découpage en phrases aux pauses naturelles (gap ≥ PAUSE_THRESHOLD_MS)
     - Chaque phrase découpée en lignes de max MAX_CHARS_PER_LINE caractères
     - Respecte les limites Netflix (42 chars/ligne) et les pratiques pro

  2. AFFICHAGE (style CapCut karaoke) :
     - Chaque mot déclenche un update : la ligne s'affiche en s'accumulant
     - Le texte visible = tous les mots de la ligne courante jusqu'au mot actif
     - Couleur lime (#CBFF4D) pour TikTok — blanc pour Classique/Cinéma
     - Police ultra-grasse, sans fond, positionnée au tiers inférieur

  Résultat : mots qui apparaissent progressivement, respectant les pauses
  naturelles de la parole et les limites de lisibilité par ligne.
"""
from __future__ import annotations

from typing import Any

from app.models import SubtitleStyle, WordTimestamp

# ── Constantes DaVinci Resolve ────────────────────────────────────────────────
PAUSE_THRESHOLD_MS: int = 400    # gap ≥ 400 ms entre deux mots = nouvelle phrase
MAX_CHARS_PER_LINE: int = 38     # limite lisibilité (Netflix = 42, on reste prudent)

# ── Configurations visuelles par style ──────────────────────────────────────

_STYLE_CONFIGS: dict[SubtitleStyle, dict[str, Any]] = {
    SubtitleStyle.TIKTOK: {
        "font_family": "Montserrat",
        "font_weight": "900",
        "font_size": "7.5 vmin",
        "fill_color": "#ffffff",           # Blanc pur
        "stroke_color": "#000000",
        "stroke_width": "0.6 vmin",
        "y": "75%",
        "width": "85%",
    },
    SubtitleStyle.CLASSIQUE: {
        "font_family": "Montserrat",
        "font_weight": "700",
        "font_size": "5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.35 vmin",
        "y": "80%",
        "width": "85%",
        "background_color": "rgba(0,0,0,0.55)",
        "background_x_padding": "2%",
        "background_y_padding": "1%",
        "background_border_radius": "0.5 vmin",
    },
    SubtitleStyle.CINEMA: {
        "font_family": "Montserrat",
        "font_weight": "300",
        "font_size": "3.5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.2 vmin",
        "y": "88%",
        "width": "80%",
    },
}


# ── Helpers DaVinci Resolve ───────────────────────────────────────────────────

def _split_into_phrases(
    timestamps: list[WordTimestamp],
    pause_ms: int = PAUSE_THRESHOLD_MS,
) -> list[list[WordTimestamp]]:
    """
    Découpe la liste de mots en phrases aux pauses naturelles.

    Une pause = gap entre la fin d'un mot et le début du suivant ≥ pause_ms.
    DaVinci Resolve utilise cette logique pour créer des blocs de sous-titres
    distincts plutôt qu'un flux continu.
    """
    if not timestamps:
        return []

    phrases: list[list[WordTimestamp]] = []
    current: list[WordTimestamp] = [timestamps[0]]

    for i in range(1, len(timestamps)):
        gap = timestamps[i].start_ms - timestamps[i - 1].end_ms
        if gap >= pause_ms:
            phrases.append(current)
            current = [timestamps[i]]
        else:
            current.append(timestamps[i])

    if current:
        phrases.append(current)

    return phrases


def _split_phrase_into_lines(
    words: list[WordTimestamp],
    max_chars: int = MAX_CHARS_PER_LINE,
) -> list[list[WordTimestamp]]:
    """
    Découpe une phrase en lignes respectant la limite de caractères.

    Limite Netflix = 42 chars/ligne. On utilise max_chars (défaut 38) pour
    garder une marge confortable et éviter les lignes trop longues en mobile.
    """
    lines: list[list[WordTimestamp]] = []
    current_line: list[WordTimestamp] = []
    current_chars = 0

    for word in words:
        word_len = len(word.word)
        separator = 1 if current_line else 0  # espace avant le mot

        if current_line and current_chars + separator + word_len > max_chars:
            # Ligne pleine → on la sauvegarde et on recommence
            lines.append(current_line)
            current_line = [word]
            current_chars = word_len
        else:
            current_line.append(word)
            current_chars += separator + word_len

    if current_line:
        lines.append(current_line)

    return lines


# ── Fonction principale ───────────────────────────────────────────────────────

def build_subtitle_elements(
    timestamps: list[WordTimestamp],
    style: SubtitleStyle,
    audio_speed: float = 1.0,
    track: int = 6,
) -> list[dict[str, Any]]:
    """
    Construit les éléments text Creatomate.

    Pipeline :
      1. Segmentation DaVinci Resolve : phrases (pauses) → lignes (chars)
      2. Affichage CapCut karaoke : chaque mot accumule la ligne courante
         → N mots dans la ligne = N éléments texte successifs

    Conversion timestamps : ms ElevenLabs → secondes vidéo (/audio_speed).

    Args:
        timestamps:  Liste de WordTimestamp triés par start_ms
        style:       Style visuel (tiktok / classique / cinema)
        audio_speed: Multiplicateur de vitesse audio Creatomate
        track:       Piste Creatomate (défaut 6)

    Returns:
        Liste d'éléments dict prêts pour le payload Creatomate
    """
    if not timestamps:
        return []

    cfg = _STYLE_CONFIGS[style]
    elements: list[dict[str, Any]] = []
    total = len(timestamps)

    # ── Étape 1 : segmentation ─────────────────────────────────────────────
    phrases = _split_into_phrases(timestamps)

    for phrase in phrases:
        lines = _split_phrase_into_lines(phrase)

        # ── Étape 2 : affichage karaoke par ligne ──────────────────────────
        for line in lines:
            for word_idx, word in enumerate(line):
                # Texte affiché = tous les mots de la ligne jusqu'au mot courant
                visible_words = line[: word_idx + 1]
                text = " ".join(w.word for w in visible_words)

                # Timing vidéo
                time_s = round(word.start_ms / 1000.0 / audio_speed, 3)

                # Durée = jusqu'au début du mot suivant global
                global_idx = timestamps.index(word)
                if global_idx + 1 < total:
                    next_start_s = timestamps[global_idx + 1].start_ms / 1000.0 / audio_speed
                    duration_s = max(round(next_start_s - time_s, 3), 0.05)
                else:
                    end_s = word.end_ms / 1000.0 / audio_speed
                    duration_s = max(round(end_s - time_s + 0.25, 3), 0.1)

                el: dict[str, Any] = {
                    "type": "text",
                    "track": track,
                    "time": time_s,
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
