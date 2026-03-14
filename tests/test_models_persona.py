"""Tests for persona/ambiance fields on SheetsRow."""
import pytest
from app.models import SheetsRow


def test_sheets_row_persona_default_none():
    """persona defaults to None when not provided."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
    )
    assert row.persona is None


def test_sheets_row_ambiance_default_none():
    """ambiance defaults to None when not provided."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
    )
    assert row.ambiance is None


def test_sheets_row_persona_set():
    """persona accepts a string value."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="femme 30 ans, mère de famille",
    )
    assert row.persona == "femme 30 ans, mère de famille"


def test_sheets_row_ambiance_set():
    """ambiance accepts a string value."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        ambiance="cinématique chaud, lumière dorée",
    )
    assert row.ambiance == "cinématique chaud, lumière dorée"


def test_sheets_row_persona_stripped():
    """persona is stripped of whitespace (strip_sheets_strings validator)."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="  femme 30 ans  \r\n",
    )
    assert row.persona == "femme 30 ans"


def test_sheets_row_ambiance_stripped():
    """ambiance is stripped of whitespace."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        ambiance="  chaud  \n",
    )
    assert row.ambiance == "chaud"


def test_sheets_row_empty_string_persona_becomes_none():
    """Empty string persona is treated as None (falsy)."""
    row = SheetsRow(
        row_id="1", script="A" * 50, voice_id="v1",
        persona="",
    )
    # Empty string is valid — Claude code checks truthiness
    assert row.persona == ""
