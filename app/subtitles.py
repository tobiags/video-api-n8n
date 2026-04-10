"""
subtitles.py — Génération des sous-titres synchronisés pour Creatomate

Responsabilités :
  - Regrouper les timestamps mot-par-mot ElevenLabs en chunks d'affichage
  - Découpage intelligent : coupure à la ponctuation (., !, ?, ,) pour des
    lignes qui respectent le rythme naturel de la voix off
  - Construire les éléments text Creatomate avec timing précis (ms → s)
  - Appliquer le style choisi (TikTok / Classique / Cinéma)

NOTE : elevenlabs.py doit utiliser "alignment" (pas "normalized_alignment")
pour que la ponctuation soit conservée dans les mots (ex: "ans." pas "ans").
"""
from __future__ import annotations

from typing import Any

from app.models import SubtitleStyle, WordTimestamp

# Caractères de ponctuation pouvant être des "mots" seuls en français
# (ex: espace avant ? en français → "?" est un token séparé)
_STANDALONE_SENTENCE_END = {".", "!", "?", "…", "»", "\""}
_STANDALONE_CLAUSE_END   = {",", ";", ":", "—", "–"}

# ── Configurations visuelles par style ──────────────────────────────────────

_STYLE_CONFIGS: dict[SubtitleStyle, dict[str, Any]] = {
    SubtitleStyle.TIKTOK: {
        "words_per_chunk": 3,
        "font_family": "Montserrat",
        "font_weight": "900",
        "font_size": "7 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.6 vmin",
        "y": "72%",
        "width": "80%",
    },
    SubtitleStyle.CLASSIQUE: {
        "words_per_chunk": 5,
        "font_family": "Open Sans",
        "font_weight": "700",
        "font_size": "4.5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.25 vmin",
        "y": "86%",
        "width": "82%",
        "background_color": "rgba(0,0,0,0.6)",
        "background_x_padding": "2.5%",
        "background_y_padding": "1%",
        "background_border_radius": "0.4 vmin",
    },
    SubtitleStyle.CINEMA: {
        "words_per_chunk": 7,
        "font_family": "Georgia",
        "font_weight": "400",
        "font_size": "3.5 vmin",
        "fill_color": "#ffffff",
        "stroke_color": "#000000",
        "stroke_width": "0.15 vmin",
        "y": "88%",
        "width": "78%",
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

    Requiert que elevenlabs.py utilise "alignment" (pas "normalized_alignment")
    afin que la ponctuation soit présente dans les mots.
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

    Gère deux cas :
      - Ponctuation attachée au mot : "ans." → word[-1] == "."
      - Ponctuation séparée (français) : "ans" puis "?" → mot seul
    """
    chunks: list[dict[str, Any]] = []
    current_group: list[WordTimestamp] = []

    for ts in timestamps:
        word = ts.word.strip()
        if not word:
            continue

        # Ponctuation seule (ex: "?" séparé en français) — flush le groupe courant
        is_standalone_punct = (
            word in _STANDALONE_SENTENCE_END or
            word in _STANDALONE_CLAUSE_END
        )
        if is_standalone_punct:
            if current_group:
                # Attache le signe au dernier mot pour l'affichage
                last = current_group[-1]
                current_group[-1] = WordTimestamp(
                    word=last.word + word,
                    start_ms=last.start_ms,
                    end_ms=ts.end_ms,
                )
                is_sentence_end = word in _STANDALONE_SENTENCE_END
                if is_sentence_end or len(current_group) >= 3:
                    _flush(current_group, chunks)
                    current_group = []
            continue

        current_group.append(ts)

        ends_sentence = word[-1] in ".!?…" or word[-1] in _STANDALONE_SENTENCE_END
        ends_clause   = word[-1] in ",;:—–" or word[-1] in _STANDALONE_CLAUSE_END

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
    # Filtre les tokens purement vides
    words = [w.word for w in group if w.word.strip()]
    if not words:
        return
    chunks.append({
        "text":       " ".join(words),
        "start_s":    group[0].start_ms  / 1000.0,
        "duration_s": (group[-1].end_ms - group[0].start_ms) / 1000.0,
    })
