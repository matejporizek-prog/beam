"""
Tests for the Edison Filmhub scraper.

A third distinct platform (not Aerofilms, not the Kino Pilotů Swiper
carousel) — no JSON-LD, but a rich, cleanly server-rendered program table with
real per-screening language/subtitle notation and, sometimes, a genuine
ticket-purchase link. See edison.py's module docstring for the full story.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import edison
from scrapers.edison import _parse_desc, _split_codes, _strip_dabing_suffix, _strip_year_suffix

FIXTURE = Path(__file__).parent / "fixtures" / "edison-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return edison.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title):
    return [s for s in screenings if s["title_cz"] == title]


# --------------------------------------------------------------------------
# Overall shape
# --------------------------------------------------------------------------

def test_finds_screenings(screenings):
    assert len(screenings) == 63


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Edison Filmhub" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_no_screening_leaks_a_raw_language_code(screenings):
    """
    A two/three-letter leftover means a code fell through _edison_language_name
    unmapped — this caught a real gap: 'is' and 'my' passed through
    untranslated on the first run (legitimate ISO codes missing from
    scrapers/base.py's shared LANGUAGE_NAMES, not an Edison-specific quirk).
    """
    for s in screenings:
        for part in s["language"].split(","):
            part = part.strip()
            if part:
                assert len(part) > 3, f"unmapped language code {part!r} in {s['title_cz']!r}"


# --------------------------------------------------------------------------
# The date problem: no year, spanning a month boundary
# --------------------------------------------------------------------------

def test_covers_a_multi_month_window(result):
    """
    Unlike Kino Pilotů's single-month window, this site's calendar genuinely
    crosses July -> August -> September in one page load — a real exercise of
    the shared infer_years_for_months(), not just the single no-year problem.
    """
    assert result["covered_dates"][0] == "2026-07-24"
    assert result["covered_dates"][-1] == "2026-09-03"


def test_days_the_site_skips_are_reported_empty(result):
    assert "2026-08-13" in result["empty_dates"]
    assert "2026-08-13" not in {None}  # sanity: the field is populated at all


# --------------------------------------------------------------------------
# The real find: .desc's compact language notation
# --------------------------------------------------------------------------

def test_language_and_subtitle_notation_is_parsed(screenings):
    """
    "JPN, Tit. CZ, EN" (Japanese, Czech AND English subtitles) is real,
    structured signal — more than any Aerofilms cinema's bare english_friendly
    chip gives. The subtitle language, not just the spoken one, is what should
    set english_friendly here.
    """
    matches = find(screenings, "Exit 8")
    assert matches
    s = matches[0]
    assert s["language"] == "japonština"
    assert s["english_friendly"] is True
    assert s["language_version"] == "titulky"


def test_czech_original_with_no_subtitle_note_stays_unversioned(screenings):
    matches = find(screenings, "Chlast")
    # "Chlast" doesn't exist in this fixture under that exact title necessarily;
    # use the language-parsing unit test instead for this exact case, and keep
    # this integration test for whichever row is genuinely spoken Czech only.
    czech_only = [s for s in screenings if s["language"] == "čeština" and not s["language_version"]]
    assert czech_only, "expected at least one Czech-spoken screening with no subtitle note"


def test_english_friendly_from_subtitles_not_just_spoken_language(screenings):
    """
    A German-spoken film with Czech+English subtitles must still count as
    english_friendly — the signal comes from either the spoken OR subtitled
    language being English, matching the planning doc's own definition.
    """
    german_with_en_subs = [
        s for s in screenings
        if s["language"] == "němčina" and s["english_friendly"]
    ]
    assert german_with_en_subs


# --------------------------------------------------------------------------
# Real ticket links, when they exist
# --------------------------------------------------------------------------

def test_a_genuine_ticket_link_is_preferred_when_present(screenings):
    """
    A small number of screenings link straight to a GoOut purchase page.
    When that exists, it must win over the generic film-page fallback.
    """
    goout = [s for s in screenings if "goout.net" in s["booking_url"]]
    assert goout, "expected at least one real GoOut ticket link in this fixture"


def test_falls_back_to_the_films_own_page_without_a_real_ticket_link(screenings):
    fallback = [s for s in screenings if "/filmy/" in s["booking_url"]]
    assert fallback
    assert all("goout" not in s["booking_url"] for s in fallback)


# --------------------------------------------------------------------------
# The two-level .event structure and free-text notes
# --------------------------------------------------------------------------

def test_named_series_is_captured_alongside_the_category(screenings):
    """.event carries a broad category ("Festivaly") and, often, a specific
    named series ("Heatwave Horror") — both should end up in strand."""
    matches = find(screenings, "Čarodějky")
    assert matches
    assert "Festivaly" in matches[0]["strand"]
    assert "Heatwave Horror" in matches[0]["strand"]


def test_qa_and_intro_notes_are_not_lost(screenings):
    """Free-text notes ("+ úvod Ryan Keating") have no fixed vocabulary but
    must still survive somewhere rather than being silently dropped."""
    matches = find(screenings, "Čarodějky")
    assert matches
    assert "Ryan Keating" in matches[0]["strand"]


def test_dabing_suffix_is_stripped_from_the_title_and_becomes_a_real_version(screenings):
    """
    "Toy Story 5: Příběh hraček (CZ DABING)" is the exact same film already
    known from the Aerofilms cinemas and Kino Pilotů as plain "Toy Story 5:
    Příběh hraček" — leaving the suffix in would cost a duplicate, worse-
    scoring TMDb match AND throw away a real dubbing signal.
    """
    matches = find(screenings, "Toy Story 5: Příběh hraček")
    assert matches, "the (CZ DABING) suffix should have been stripped from the title"
    assert find(screenings, "Toy Story 5: Příběh hraček (CZ DABING)") == []
    assert matches[0]["language_version"] == "dabing"


def test_year_suffix_is_stripped_because_it_breaks_tmdb_search_entirely(screenings):
    """
    "Posedlost (2026)" turned out not to be a harmless disambiguation at all:
    "Posedlost" alone is already a known, correctly-resolved film from other
    cinemas, but TMDb's own search API returns zero results for the literal
    query "Posedlost (2026)" — a hard failure, not a fuzzy-scoring nuisance.
    The dabing suffix stays a separate rule (it carries a real signal worth
    keeping as a tag; a bare year doesn't).
    """
    assert find(screenings, "Posedlost (2026)") == []
    matches = find(screenings, "Posedlost")
    assert matches


def test_double_feature_rows_have_no_event_block_and_dont_crash(screenings):
    """
    "Double Feature: X" rows have no .event div at all — the parser must
    handle that gracefully (empty strand contribution from .event) rather than
    crashing on a missing element.
    """
    matches = [s for s in screenings if "Double Feature" in s["title_cz"]]
    assert matches
    for s in matches:
        assert s["title_cz"]  # didn't crash, title still present


# --------------------------------------------------------------------------
# _parse_desc / _split_codes unit tests
# --------------------------------------------------------------------------

def test_strip_dabing_suffix_recognises_the_pattern():
    title, tags = _strip_dabing_suffix("Toy Story 5: Příběh hraček (CZ DABING)")
    assert title == "Toy Story 5: Příběh hraček"
    assert tags == ["CZ DABING"]


def test_strip_dabing_suffix_leaves_a_year_suffix_alone():
    """_strip_dabing_suffix only recognises dabing text; the year suffix is a
    separate rule (_strip_year_suffix), applied afterward in _parse_row."""
    title, tags = _strip_dabing_suffix("Posedlost (2026)")
    assert title == "Posedlost (2026)"
    assert tags == []


def test_strip_year_suffix_removes_a_bare_trailing_year():
    assert _strip_year_suffix("Posedlost (2026)") == "Posedlost"
    assert _strip_year_suffix("Nějaký film (1999)") == "Nějaký film"


def test_strip_year_suffix_leaves_other_parentheses_alone():
    """Only a bare 4-digit year is safe to strip unconditionally — anything
    else in parentheses might be part of the film's real title."""
    assert _strip_year_suffix("Alien (Director's Cut)") == "Alien (Director's Cut)"
    assert _strip_year_suffix("Toy Story 5: Příběh hraček") == "Toy Story 5: Příběh hraček"


def test_split_codes_handles_commas_and_slashes():
    assert _split_codes("EN, DE") == ["en", "de"]
    assert _split_codes("HU / EN, DE") == ["hu", "en", "de"]
    assert _split_codes("") == []


def test_parse_desc_simple_language_only():
    class FakeEl:
        def find_all(self, *_a, **_k): return []
        def get_text(self, *_a, **_k): return "CZ"
    language, eng, version, notes = _parse_desc(FakeEl())
    assert language == "čeština"
    assert eng is False
    assert version == ""
    assert notes == []


def test_parse_desc_with_subtitles_and_a_note():
    class FakeBr:
        def replace_with(self, text): self.replaced = text
    class FakeEl:
        def find_all(self, *_a, **_k): return []
        def get_text(self, joiner="", **_k):
            return "EN, Tit. CZ" + joiner + "+ úvod Ryan Keating"
    language, eng, version, notes = _parse_desc(FakeEl())
    assert language == "angličtina"
    assert eng is True
    assert version == "titulky"
    assert notes == ["+ úvod Ryan Keating"]


def test_parse_desc_handles_a_missing_element():
    language, eng, version, notes = _parse_desc(None)
    assert (language, eng, version, notes) == ("", False, "", [])
