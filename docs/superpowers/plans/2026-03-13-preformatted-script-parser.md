# Preformatted Script Parser Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `script_parser.py` module that detects and parses pre-formatted scripts (PLAN/🎙/🎬 format) into `ScriptAnalysis`, bypassing Claude API when the client provides their own Kling prompts.

**Architecture:** New `script_parser.py` module with `detect_preformatted()` and `parse_preformatted()` functions. Routing added in `main.py` before the Claude call (line 536). Output is the same `ScriptAnalysis` model used by the rest of the pipeline — zero changes downstream.

**Tech Stack:** Python 3.14, Pydantic v2, regex, pytest (asyncio_mode=auto)

**Spec:** `docs/superpowers/specs/2026-03-12-preformatted-script-parser-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `app/script_parser.py` | Detect and parse pre-formatted scripts into `ScriptAnalysis` |
| Modify | `app/errors.py:165` | Add `ScriptParserError(VideoGenException)` |
| Modify | `app/models.py:136-152` | Add `source` field to `ScriptAnalysis` |
| Modify | `app/main.py:57,530-548` | Import script_parser, add routing before Claude call |
| Create | `tests/test_script_parser.py` | 16 tests covering detection, parsing, edge cases, routing |

---

## Chunk 1: Foundation (errors + models + detect)

### Task 1: Add ScriptParserError to errors.py

**Files:**
- Modify: `app/errors.py:162-165` (after `LibraryError`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_script_parser.py`:

```python
"""Tests for app.script_parser — pre-formatted script detection and parsing."""
import pytest

from app.errors import ScriptParserError, VideoGenException


def test_script_parser_error_inherits_videogen():
    """ScriptParserError must inherit from VideoGenException."""
    err = ScriptParserError("Plan 1 : marqueur 🎙 manquant")
    assert isinstance(err, VideoGenException)
    assert err.error_code == "SCRIPT_PARSER_ERROR"
    assert err.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_script_parser_error_inherits_videogen -v`
Expected: FAIL with `ImportError: cannot import name 'ScriptParserError'`

- [ ] **Step 3: Write minimal implementation**

Add to `app/errors.py` after `LibraryError` (after line 165):

```python
class ScriptParserError(VideoGenException):
    """Erreur de parsing d'un script pré-découpé (format PLAN/🎙/🎬 invalide)."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "SCRIPT_PARSER_ERROR"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_script_parser_error_inherits_videogen -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/errors.py tests/test_script_parser.py
git commit -m "feat: add ScriptParserError to errors.py"
```

---

### Task 2: Add source field to ScriptAnalysis

**Files:**
- Modify: `app/models.py:7,136-152`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_script_parser.py`:

```python
from app.models import ScriptAnalysis, ScriptSection, SceneType


def test_script_analysis_source_defaults_to_claude():
    """ScriptAnalysis.source defaults to 'claude' for backward compatibility."""
    analysis = ScriptAnalysis(
        total_duration=5,
        sections=[
            ScriptSection(
                id=1, text="Test", start=0, end=5, duration=5,
                broll_prompt="A man walking in a park at sunset, cinematic",
                keywords=["man", "park"], scene_type=SceneType.AMBIENT,
            )
        ],
    )
    assert analysis.source == "claude"


def test_script_analysis_source_parser():
    """ScriptAnalysis.source can be set to 'parser'."""
    analysis = ScriptAnalysis(
        total_duration=5,
        source="parser",
        sections=[
            ScriptSection(
                id=1, text="Test", start=0, end=5, duration=5,
                broll_prompt="A man walking in a park at sunset, cinematic",
                keywords=["man", "park"], scene_type=SceneType.AMBIENT,
            )
        ],
    )
    assert analysis.source == "parser"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_script_analysis_source_defaults_to_claude tests/test_script_parser.py::test_script_analysis_source_parser -v`
Expected: FAIL with `unexpected keyword argument 'source'`

- [ ] **Step 3: Write minimal implementation**

In `app/models.py`:

1. Add `Literal` to the typing import on line 7:
```python
from typing import Any, Literal
```

2. Add the `source` field to `ScriptAnalysis` class (after line 142, before the validator):
```python
    source: Literal["claude", "parser"] = Field(
        "claude", description="Origine de l'analyse : Claude API ou parser pré-découpé"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Run existing tests to check no regression**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_config.py -v`
Expected: 15 PASSED

- [ ] **Step 6: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/models.py tests/test_script_parser.py
git commit -m "feat: add source field to ScriptAnalysis for traceability"
```

---

### Task 3: Implement detect_preformatted()

**Files:**
- Create: `app/script_parser.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_script_parser.py`:

```python
from app.script_parser import detect_preformatted


THEO_SCRIPT_3_PLANS = """PLAN 1 (0-5s) — HOOK
🎙 "Un documentaire gratuit a changé la vie de cet homme."
🎬 Close-up portrait of a rugged French man in his 40s with stubble, arms crossed, looking directly at camera with a confident slight smile, dark moody background with warm red backlight, cinematic dramatic lighting, 9:16 vertical format
PLAN 2 (5-10s) — DOULEUR
🎙 "Avant, il était technicien dans le Nord. Il partait à 6h, rentrait à 19h."
🎬 A tired man in a dark blue work jacket walking alone through a grey industrial parking lot early in the morning, cold foggy atmosphere, streetlights glowing, slow motion, cinematic desaturated tones, 9:16 vertical format
PLAN 3 (10-15s) — FRUSTRATION
🎙 "Comme beaucoup de Français, il avait l'impression que sa vie lui échappait."
🎬 A man sitting alone in a crowded commuter train, staring through the window with a blank tired expression, other passengers blurred around him, grey rainy weather outside, melancholic cinematic mood, shallow depth of field, 9:16 vertical format"""


NORMAL_SCRIPT = """Vous en avez marre de perdre du temps chaque matin dans les transports ?
Découvrez la méthode qui a changé la vie de 2800 personnes.
Un documentaire gratuit de 47 minutes vous attend."""


def test_detect_preformatted_valid():
    """Script with 3+ PLAN blocks → True."""
    assert detect_preformatted(THEO_SCRIPT_3_PLANS) is True


def test_detect_preformatted_normal_script():
    """Normal raw script without PLAN markers → False."""
    assert detect_preformatted(NORMAL_SCRIPT) is False


def test_detect_preformatted_partial():
    """Only 1 PLAN block (need >= 2) → False."""
    single = """PLAN 1 (0-5s) — HOOK
🎙 "Test."
🎬 A man walking in a park"""
    assert detect_preformatted(single) is False


def test_detect_preformatted_dash_variants():
    """Works with en-dash and hyphen instead of em-dash."""
    script_endash = """PLAN 1 (0–5s) – HOOK
🎙 "Line one."
🎬 A man walking
PLAN 2 (5–10s) – CTA
🎙 "Line two."
🎬 A woman smiling"""
    assert detect_preformatted(script_endash) is True

    script_hyphen = """PLAN 1 (0-5s) - HOOK
🎙 "Line one."
🎬 A man walking
PLAN 2 (5-10s) - CTA
🎙 "Line two."
🎬 A woman smiling"""
    assert detect_preformatted(script_hyphen) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_detect_preformatted_valid tests/test_script_parser.py::test_detect_preformatted_normal_script tests/test_script_parser.py::test_detect_preformatted_partial tests/test_script_parser.py::test_detect_preformatted_dash_variants -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.script_parser'`

- [ ] **Step 3: Write minimal implementation**

Create `app/script_parser.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py -v`
Expected: 7 PASSED

- [ ] **Step 5: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/script_parser.py tests/test_script_parser.py
git commit -m "feat: add detect_preformatted() for PLAN/🎙/🎬 format detection"
```

---

## Chunk 2: parse_preformatted() core + keywords + scene_type

### Task 4: Implement parse_preformatted() — core parsing

**Files:**
- Modify: `app/script_parser.py`
- Modify: `tests/test_script_parser.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_script_parser.py`:

```python
from app.script_parser import detect_preformatted, parse_preformatted
from app.models import VideoFormat


FULL_THEO_SCRIPT = """PLAN 1 (0-5s) — HOOK
🎙 "Un documentaire gratuit a changé la vie de cet homme."
🎬 Close-up portrait of a rugged French man in his 40s with stubble, arms crossed, looking directly at camera with a confident slight smile, dark moody background with warm red backlight, cinematic dramatic lighting, 9:16 vertical format
PLAN 2 (5-10s) — DOULEUR
🎙 "Avant, il était technicien dans le Nord. Il partait à 6h, rentrait à 19h."
🎬 A tired man in a dark blue work jacket walking alone through a grey industrial parking lot early in the morning, cold foggy atmosphere, streetlights glowing, slow motion, cinematic desaturated tones, 9:16 vertical format
PLAN 3 (10-15s) — FRUSTRATION
🎙 "Comme beaucoup de Français, il avait l'impression que sa vie lui échappait."
🎬 A man sitting alone in a crowded commuter train, staring through the window with a blank tired expression, other passengers blurred around him, grey rainy weather outside, melancholic cinematic mood, shallow depth of field, 9:16 vertical format
PLAN 4 (15-20s) — DÉCOUVERTE
🎙 "Un soir, il tombe sur un documentaire de 47 minutes. Il découvre un métier dont personne ne parle."
🎬 A man sitting on a couch in a dark living room at night, face illuminated by the glow of a laptop screen, leaning forward with an intrigued focused expression, intimate documentary atmosphere, warm screen light contrasting dark room, 9:16 vertical format
PLAN 5 (20-25s) — MÉCANISME
🎙 "Ce métier, c'est celui qui écrit les mots derrière chaque pub, chaque mail, chaque page de vente que vous voyez défiler."
🎬 Cinematic montage-style shot of a smartphone screen rapidly scrolling through social media ads and marketing content, dynamic motion, glowing screen, fingers swiping, close-up perspective, modern urban aesthetic, 9:16 vertical format
PLAN 6 (25-30s) — TRANSFORMATION
🎙 "6 mois plus tard, il avait ses premiers clients. Il travaillait depuis chez lui. 4 heures par jour."
🎬 A calm man in casual clothes typing on a laptop at a clean minimalist desk by a window, soft morning sunlight streaming in, coffee mug beside him, peaceful focused atmosphere, warm natural tones, cinematic shallow depth of field, 9:16 vertical format
PLAN 7 (30-35s) — RÉSULTAT
🎙 "Aujourd'hui il gagne plus de 4 500 euros par mois. Sans patron. Sans bureau."
🎬 A man walking slowly through a quiet sunny residential street in northern France, relaxed confident posture, hands in pockets, golden hour sunlight, trees lining the sidewalk, peaceful lifestyle atmosphere, cinematic warm tones, 9:16 vertical format
PLAN 8 (35-40s) — SOCIAL PROOF
🎙 "Il fait partie des 2 800 personnes qui ont suivi cette méthode. La première en France."
🎬 Slow cinematic zoom out revealing a large modern auditorium filled with people watching a big screen presentation, warm professional lighting, motivated crowd atmosphere, epic documentary feel, 9:16 vertical format
PLAN 9 (40-45s) — CTA
🎙 "Le documentaire est gratuit. 47 minutes. Le lien est juste en dessous."
🎬 Close-up of a man pressing play on a laptop screen in a cozy dark room, the play button glowing, cinematic shallow depth of field, warm intimate mood, the light from the screen growing brighter, 9:16 vertical format"""


def test_parse_preformatted_full():
    """Parse Théo's 9-plan script and verify all sections."""
    result = parse_preformatted(FULL_THEO_SCRIPT, VideoFormat.VERTICAL)

    assert result.source == "parser"
    assert result.total_duration == 45
    assert len(result.sections) == 9

    # Check first section
    s1 = result.sections[0]
    assert s1.id == 1
    assert s1.text == "Un documentaire gratuit a changé la vie de cet homme."
    assert s1.start == 0
    assert s1.end == 5
    assert s1.duration == 5
    assert "rugged French man" in s1.broll_prompt

    # Check last section
    s9 = result.sections[8]
    assert s9.id == 9
    assert s9.text == "Le documentaire est gratuit. 47 minutes. Le lien est juste en dessous."
    assert s9.start == 40
    assert s9.end == 45


def test_parse_preformatted_validation():
    """Parsed ScriptAnalysis passes Pydantic validators (total_duration == sum)."""
    result = parse_preformatted(FULL_THEO_SCRIPT, VideoFormat.VERTICAL)
    computed = sum(s.duration for s in result.sections)
    assert computed == result.total_duration
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_parse_preformatted_full tests/test_script_parser.py::test_parse_preformatted_validation -v`
Expected: FAIL with `ImportError: cannot import name 'parse_preformatted'`

- [ ] **Step 3: Write implementation**

Add to `app/script_parser.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py -v`
Expected: 9 PASSED

- [ ] **Step 5: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/script_parser.py tests/test_script_parser.py
git commit -m "feat: implement parse_preformatted() with keyword extraction and scene mapping"
```

---

### Task 5: Test keywords extraction

**Files:**
- Modify: `tests/test_script_parser.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_script_parser.py`:

```python
def test_parse_preformatted_keywords():
    """Keywords are extracted from broll_prompt in English, max 3."""
    result = parse_preformatted(FULL_THEO_SCRIPT, VideoFormat.VERTICAL)

    for section in result.sections:
        assert isinstance(section.keywords, list)
        assert len(section.keywords) <= 3
        assert len(section.keywords) >= 1  # at least 1 keyword from rich prompts
        for kw in section.keywords:
            assert kw.isascii(), f"Keyword '{kw}' should be ASCII/English"
            assert kw == kw.lower(), f"Keyword '{kw}' should be lowercase"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_parse_preformatted_keywords -v`
Expected: PASS (implementation already done in Task 4)

- [ ] **Step 3: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add tests/test_script_parser.py
git commit -m "test: add keyword extraction verification"
```

---

### Task 6: Test scene_type mapping

**Files:**
- Modify: `tests/test_script_parser.py`

- [ ] **Step 1: Write the test**

Add to `tests/test_script_parser.py`:

```python
def test_parse_preformatted_scene_types():
    """Scene types are correctly mapped from labels."""
    result = parse_preformatted(FULL_THEO_SCRIPT, VideoFormat.VERTICAL)

    # HOOK → emotion
    assert result.sections[0].scene_type == SceneType.EMOTION
    # DOULEUR → emotion
    assert result.sections[1].scene_type == SceneType.EMOTION
    # FRUSTRATION → emotion
    assert result.sections[2].scene_type == SceneType.EMOTION
    # DÉCOUVERTE → ambient
    assert result.sections[3].scene_type == SceneType.AMBIENT
    # MÉCANISME → ambient
    assert result.sections[4].scene_type == SceneType.AMBIENT
    # TRANSFORMATION → testimonial
    assert result.sections[5].scene_type == SceneType.TESTIMONIAL
    # RÉSULTAT → testimonial
    assert result.sections[6].scene_type == SceneType.TESTIMONIAL
    # SOCIAL PROOF → testimonial
    assert result.sections[7].scene_type == SceneType.TESTIMONIAL
    # CTA → cta
    assert result.sections[8].scene_type == SceneType.CTA
```

- [ ] **Step 2: Run test to verify it passes**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_parse_preformatted_scene_types -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add tests/test_script_parser.py
git commit -m "test: add scene_type mapping verification"
```

---

## Chunk 3: Error handling + edge cases

### Task 7: Test malformed scripts

**Files:**
- Modify: `tests/test_script_parser.py`

- [ ] **Step 1: Write error case tests**

Add to `tests/test_script_parser.py`:

```python
def test_parse_malformed_missing_voice():
    """Plan without 🎙 marker → ScriptParserError."""
    bad_script = """PLAN 1 (0-5s) — HOOK
🎬 A man walking in a park
PLAN 2 (5-10s) — CTA
🎙 "Line two."
🎬 A woman smiling"""
    with pytest.raises(ScriptParserError):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_malformed_missing_prompt():
    """Plan without 🎬 marker → ScriptParserError."""
    bad_script = """PLAN 1 (0-5s) — HOOK
🎙 "Line one."
PLAN 2 (5-10s) — CTA
🎙 "Line two."
🎬 A woman smiling"""
    with pytest.raises(ScriptParserError):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_malformed_timestamps():
    """Reversed timestamps (end <= start) → ScriptParserError."""
    bad_script = """PLAN 1 (10-5s) — HOOK
🎙 "Line one."
🎬 A man walking in a park at sunset, cinematic mood
PLAN 2 (5-10s) — CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    with pytest.raises(ScriptParserError, match="timestamps invalides"):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_empty_prompt_after_marker():
    """🎬 followed by whitespace only → ScriptParserError."""
    bad_script = """PLAN 1 (0-5s) — HOOK
🎙 "Line one."
🎬
PLAN 2 (5-10s) — CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    with pytest.raises(ScriptParserError, match="prompt Kling vide"):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_non_contiguous_timestamps():
    """Gap between plans → ScriptParserError."""
    bad_script = """PLAN 1 (0-5s) — HOOK
🎙 "Line one."
🎬 A man walking in a park at sunset, cinematic mood
PLAN 2 (7-12s) — CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    with pytest.raises(ScriptParserError, match="non-contigus"):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_overlapping_timestamps():
    """Overlapping timestamps → ScriptParserError."""
    bad_script = """PLAN 1 (0-6s) — HOOK
🎙 "Line one."
🎬 A man walking in a park at sunset, cinematic mood
PLAN 2 (4-10s) — CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    with pytest.raises(ScriptParserError, match="chevauchent"):
        parse_preformatted(bad_script, VideoFormat.VERTICAL)


def test_parse_dash_variants():
    """Parser accepts hyphen, en-dash, and em-dash."""
    # En-dash for timestamps, regular dash for separator
    script = """PLAN 1 (0–5s) - HOOK
🎙 "Line one."
🎬 A man walking in a park at sunset, cinematic mood
PLAN 2 (5–10s) - CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    result = parse_preformatted(script, VideoFormat.VERTICAL)
    assert len(result.sections) == 2
    assert result.total_duration == 10
```

- [ ] **Step 2: Run all tests**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py -v`
Expected: All PASSED (16+ tests)

- [ ] **Step 3: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add tests/test_script_parser.py
git commit -m "test: add error handling and edge case tests for script parser"
```

---

## Chunk 4: Pipeline routing + integration

### Task 8: Add routing in main.py

**Files:**
- Modify: `app/main.py:57,530-548`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_script_parser.py`:

```python
from unittest.mock import AsyncMock, patch
from app.config import get_settings


@pytest.mark.asyncio
async def test_pipeline_routing_preformatted():
    """Pipeline skips Claude when script is pre-formatted."""
    from app.main import run_pipeline, create_app
    from app.models import VideoGenerationRequest, SheetsRow, VideoJob
    from uuid import uuid4

    app = create_app()

    # Create a job with Théo's pre-formatted script
    job_id = uuid4()
    request = VideoGenerationRequest(
        job_id=job_id,
        sheets_row=SheetsRow(
            row_id="row_1",
            script=FULL_THEO_SCRIPT,
            format="vertical",
            strategy="A",
            duration=45,
            voice_id="tMyQcCxfGDdIt7wJ2RQw",
        ),
    )
    job = VideoJob(job_id=job_id, row_id="row_1", request=request)

    async with app.router.lifespan_context(app):
        app.state.jobs[job_id] = job
        settings = get_settings()

        with patch("app.main.analyze_script", new_callable=AsyncMock) as mock_claude, \
             patch("app.main.generate_voiceover", new_callable=AsyncMock) as mock_el, \
             patch("app.main.generate_clips", new_callable=AsyncMock) as mock_clips, \
             patch("app.main.assemble_video", new_callable=AsyncMock) as mock_creat:

            # Mock downstream to avoid real API calls
            from app.models import ElevenLabsResult, CreatomateRenderResult
            mock_el.return_value = ElevenLabsResult(
                audio_path="/tmp/test.mp3", audio_duration_ms=45000,
                voice_id="test", character_count=100,
            )
            mock_clips.return_value = []
            mock_creat.return_value = CreatomateRenderResult(
                render_id="r1", video_url="https://example.com/video.mp4",
                duration_seconds=45.0, format="vertical",
            )

            await run_pipeline(job_id=job_id, app=app, settings=settings)

            # Claude should NOT have been called
            mock_claude.assert_not_called()
            # ElevenLabs SHOULD have been called
            mock_el.assert_called_once()
            # Job should have script_analysis from parser
            assert job.script_analysis is not None
            assert job.script_analysis.source == "parser"


@pytest.mark.asyncio
async def test_pipeline_routing_normal():
    """Pipeline calls Claude for normal scripts."""
    from app.main import run_pipeline, create_app
    from app.models import VideoGenerationRequest, SheetsRow, VideoJob, ScriptAnalysis, ScriptSection
    from uuid import uuid4

    app = create_app()

    job_id = uuid4()
    request = VideoGenerationRequest(
        job_id=job_id,
        sheets_row=SheetsRow(
            row_id="row_2",
            script=NORMAL_SCRIPT * 3,  # repeat to meet min_length=50
            format="vertical",
            strategy="A",
            duration=60,
            voice_id="test-voice",
        ),
    )
    job = VideoJob(job_id=job_id, row_id="row_2", request=request)

    async with app.router.lifespan_context(app):
        app.state.jobs[job_id] = job
        settings = get_settings()

        mock_analysis = ScriptAnalysis(
            total_duration=10,
            sections=[
                ScriptSection(
                    id=1, text="Test", start=0, end=5, duration=5,
                    broll_prompt="A person walking in sunlight, cinematic mood",
                    keywords=["person"], scene_type="ambient",
                ),
                ScriptSection(
                    id=2, text="Test two", start=5, end=10, duration=5,
                    broll_prompt="A cityscape at night with neon lights glowing",
                    keywords=["cityscape"], scene_type="ambient",
                ),
            ],
        )

        with patch("app.main.analyze_script", new_callable=AsyncMock, return_value=mock_analysis) as mock_claude, \
             patch("app.main.generate_voiceover", new_callable=AsyncMock) as mock_el, \
             patch("app.main.generate_clips", new_callable=AsyncMock) as mock_clips, \
             patch("app.main.assemble_video", new_callable=AsyncMock) as mock_creat:

            from app.models import ElevenLabsResult, CreatomateRenderResult
            mock_el.return_value = ElevenLabsResult(
                audio_path="/tmp/test.mp3", audio_duration_ms=10000,
                voice_id="test", character_count=50,
            )
            mock_clips.return_value = []
            mock_creat.return_value = CreatomateRenderResult(
                render_id="r2", video_url="https://example.com/video2.mp4",
                duration_seconds=10.0, format="vertical",
            )

            await run_pipeline(job_id=job_id, app=app, settings=settings)

            # Claude SHOULD have been called (normal script)
            mock_claude.assert_called_once()
            assert job.script_analysis is not None
            assert job.script_analysis.source == "claude"
```

- [ ] **Step 2: Run integration tests to verify they fail**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py::test_pipeline_routing_preformatted -v`
Expected: FAIL because main.py doesn't yet call `detect_preformatted`

- [ ] **Step 3: Modify main.py — add import and routing**

In `app/main.py`:

1. Add import after line 61 (`from app.creatomate import assemble_video`):
```python
from app.script_parser import detect_preformatted, parse_preformatted
```

2. Replace lines 530-548 (Étape 1: Claude) with:
```python
            # ── Étape 1 : Analyse script (Claude ou Parser) ───────────────────────
            if detect_preformatted(row.script):
                # Script pré-découpé : bypass Claude, parsing direct
                logger.info("Job %s | Script pré-découpé détecté, bypass Claude", job_id)
                script_analysis = parse_preformatted(row.script, row.format)
                _update_job_progress(
                    job, JobStatus.RUNNING_ELEVENLABS,
                    "Script pré-découpé parsé (bypass Claude)", 15,
                    f"{script_analysis.section_count} plans détectés",
                )
            else:
                # Script normal : analyse Claude complète
                _update_job_progress(
                    job, JobStatus.RUNNING_CLAUDE,
                    "Analyse du script avec Claude", 10,
                    f"Découpage en sections de ~{settings.KLING_DURATION}s",
                )
                script_analysis = await analyze_script(
                    script=row.script,
                    format_=row.format,
                    duration=row.duration,
                    aspect_ratio=row.aspect_ratio,
                    http_client=http_client,
                    settings=settings,
                )
            job.script_analysis = script_analysis
            logger.info(
                "Job %s | Analyse OK [%s] : %d sections, durée totale %ds",
                job_id, script_analysis.source,
                script_analysis.section_count, script_analysis.total_duration,
            )
```

- [ ] **Step 4: Run all tests**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest tests/test_script_parser.py -v`
Expected: All PASSED

- [ ] **Step 5: Run full test suite to check no regression**

Run: `cd C:\Users\tobid\Downloads\CLAUDE\video-api && python -m pytest -v`
Expected: All PASSED, 0 warnings

- [ ] **Step 6: Commit**

```bash
cd C:\Users\tobid\Downloads\CLAUDE\video-api
git add app/main.py tests/test_script_parser.py
git commit -m "feat: add preformatted script routing in pipeline — bypass Claude when PLAN/🎙/🎬 format detected"
```

---

## Post-implementation

After all tasks pass:

1. Run full test suite: `python -m pytest -v`
2. Deploy to VPS: rebuild Docker container on Coolify
3. Test with Théo's actual script via Google Sheets
