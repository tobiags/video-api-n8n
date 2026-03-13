"""Tests for app.script_parser — pre-formatted script detection and parsing."""
import pytest

from app.errors import ScriptParserError, VideoGenException
from app.models import ScriptAnalysis, ScriptSection, SceneType


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
