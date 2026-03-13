"""Tests for app.script_parser — pre-formatted script detection and parsing."""
import pytest

from app.errors import ScriptParserError, VideoGenException
from app.models import ScriptAnalysis, ScriptSection, SceneType, VideoFormat
from app.script_parser import detect_preformatted, parse_preformatted


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


def test_script_parser_error_inherits_videogen():
    """ScriptParserError must inherit from VideoGenException."""
    err = ScriptParserError("Plan 1 : marqueur 🎙 manquant")
    assert isinstance(err, VideoGenException)
    assert err.error_code == "SCRIPT_PARSER_ERROR"
    assert err.status_code == 422


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
    """🎬 followed by whitespace only → ScriptParserError (regex won't match the plan)."""
    bad_script = """PLAN 1 (0-5s) — HOOK
🎙 "Line one."
🎬
PLAN 2 (5-10s) — CTA
🎙 "Line two."
🎬 A woman smiling at camera in bright office"""
    with pytest.raises(ScriptParserError):
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
