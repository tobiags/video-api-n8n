"""Tests for app.script_parser — pre-formatted script detection and parsing."""
import pytest

from app.errors import ScriptParserError, VideoGenException
from app.models import ScriptAnalysis, ScriptSection, SceneType, VideoFormat
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
