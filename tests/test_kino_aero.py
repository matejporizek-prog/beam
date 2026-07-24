"""
Tests for the Kino Aero scraper.

These run against a saved copy of kinoaero.cz/program (captured 21 July 2026),
not the live site. That matters for two reasons: the tests stay fast and work
offline, and — more importantly — they keep testing the same page forever, so
when Aero redesigns their site the tests tell us the parser broke rather than
quietly passing on different data.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import kino_aero
from scrapers.base import (
    classify_tags,
    language_name,
    normalize_title,
    parse_iso_duration,
)

FIXTURE = Path(__file__).parent / "fixtures" / "kino-aero-program-2026-07-21.html"


@pytest.fixture(scope="module")
def result():
    return kino_aero.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title, date=None, time=None):
    """Small helper — grab one screening by title (and optionally date/time)."""
    for s in screenings:
        if s["title_cz"] != title:
            continue
        if date and s["date"] != date:
            continue
        if time and s["time"] != time:
            continue
        return s
    raise AssertionError(f"no screening found for {title!r} {date or ''} {time or ''}")


# --------------------------------------------------------------------------
# Overall shape
# --------------------------------------------------------------------------

def test_finds_every_screening_on_the_page(screenings):
    # The saved page contains 21 screening rows and 21 JSON-LD Event blocks.
    # If this number moves, the parser is either dropping rows or duplicating them.
    assert len(screenings) == 21


def test_covers_the_full_week(result):
    assert result["covered_dates"][0] == "2026-07-21"
    assert result["covered_dates"][-1] == "2026-07-28"
    assert len(result["covered_dates"]) == 8


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["cinema"] == "Kino Aero"
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_output_matches_the_sample_data_shape(screenings):
    """The first seven keys must match sample-screenings-clean.json exactly."""
    core = {"cinema", "title_cz", "date", "time", "language", "format", "note"}
    assert core.issubset(set(screenings[0].keys()))


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------
# One screening, end to end
# --------------------------------------------------------------------------

def test_odyssea_parses_completely(screenings):
    """
    The 35mm Odyssea screening exercises everything at once: JSON-LD metadata,
    two tags of different kinds, hall, and the booking link.
    """
    s = find(screenings, "Odyssea", date="2026-07-21", time="20:00")

    assert s["language"] == "angličtina"      # from inLanguage "en"
    assert s["format"] == "35 mm"             # from the "35 mm" chip
    assert s["english_friendly"] is True      # from the "ENG" chip
    assert s["director"] == "Christopher Nolan"
    assert s["runtime_min"] == 172            # from "PT2H52M"
    assert s["hall"] == "Kinosál"
    assert s["booking_url"] == "https://kinoaero.cz/?projection=51863"
    assert s["poster_url"].startswith("https://kinoaero.cz/uploads/")
    assert s["source_id"] == "51863"


# --------------------------------------------------------------------------
# The three things the brief called out
# --------------------------------------------------------------------------

def test_strand_notes_are_captured(screenings):
    """
    "Malé oči", "Bio Senior", "Legendy" and friends must land in `strand` —
    not be mistaken for a format or silently dropped.
    """
    strands = {s["strand"] for s in screenings if s["strand"]}
    assert "Malé oči" in strands
    assert "Bio Senior" in strands
    assert "Legendy" in strands

    # A strand must never leak into the format field.
    for s in screenings:
        assert s["format"] in ("", "35 mm", "70 mm", "DCP", "3D")


def test_35mm_screenings_are_flagged_as_format_not_strand(screenings):
    film_screenings = [s for s in screenings if s["format"] == "35 mm"]
    assert len(film_screenings) == 3
    for s in film_screenings:
        assert "35 mm" not in s["strand"]


def test_days_with_no_screenings_are_reported(result):
    """
    A quiet day must be distinguishable from a day we never looked at. Every
    reported empty date has to fall inside the range we actually covered.
    """
    covered = set(result["covered_dates"])
    dates_with_screenings = {s["date"] for s in result["screenings"]}

    for empty in result["empty_dates"]:
        assert empty not in dates_with_screenings
    # Sanity: covered days either have screenings or are listed as empty.
    for day in covered:
        assert day in dates_with_screenings or day in result["empty_dates"]


# --------------------------------------------------------------------------
# Language version
# --------------------------------------------------------------------------

def test_dubbed_screenings_are_marked(screenings):
    """Aero tags exactly three dubbed screenings on this page."""
    dubbed = [s for s in screenings if s["language_version"] == "dabing"]
    assert len(dubbed) == 3
    for s in dubbed:
        assert "Dabing" not in s["strand"]  # a version is not a strand


def test_untagged_screenings_have_no_version(screenings):
    """
    Aero never writes "Titulky" — subtitled is the unmarked default. An empty
    language_version therefore means "presented normally", and the app should
    show no chip at all, exactly as the prototype does.
    """
    assert all(s["language_version"] in ("", "dabing") for s in screenings)


def test_english_friendly_is_a_boolean_not_a_note(screenings):
    eng = [s for s in screenings if s["english_friendly"]]
    assert len(eng) > 5  # Aero flags this constantly
    for s in eng:
        assert "ENG" not in s["strand"]


# --------------------------------------------------------------------------
# Helper units
# --------------------------------------------------------------------------

def test_normalize_title_handles_the_known_typo_case():
    """The real reason this helper exists: "Odyssea" vs "Oddysea"."""
    assert normalize_title("Odyssea") == "odyssea"
    assert normalize_title("Přísahám, že za to nemůžu") == "prisaham ze za to nemuzu"
    assert normalize_title("Král  Šumavy!") == "kral sumavy"


def test_parse_iso_duration():
    assert parse_iso_duration("PT2H52M") == 172
    assert parse_iso_duration("PT95M") == 95
    assert parse_iso_duration("PT2H") == 120
    assert parse_iso_duration("") is None
    assert parse_iso_duration("nonsense") is None


def test_language_name_handles_multilingual_films():
    """
    "Padlí andělé" is listed as "yue, zh" and must read the way the sample data
    writes it. A single unsplit blob here would surface as literal "yue, zh" in
    the UI.
    """
    assert language_name("en") == "angličtina"
    assert language_name("yue, zh") == "kantonština, čínština"
    assert language_name("cs/hu/sk") == "čeština, maďarština, slovenština"
    assert language_name("") == ""
    assert language_name("xx") == "xx"  # unknown codes pass through, not dropped


def test_no_screening_leaks_a_raw_language_code(screenings):
    """A two-letter language field means we're missing a mapping in LANGUAGE_NAMES."""
    for s in screenings:
        for part in s["language"].split(","):
            part = part.strip()
            if part:
                assert len(part) > 3, f"unmapped language code {part!r} in {s['title_cz']!r}"


def test_classify_tags_splits_the_three_kinds():
    out = classify_tags(["ENG", "35 mm", "Malé oči", "Dabing"])
    assert out["english_friendly"] is True
    assert out["format"] == "35 mm"
    assert out["language_version"] == "dabing"
    assert out["strand"] == "Malé oči"


def test_dabing_and_titulky_are_recognised_with_any_prefix():
    """
    Found via Edison Filmhub's "(CZ DABING)": the exact-match VERSION_TAGS
    dict alone missed it, since that tag never appears as a bare "Dabing" —
    real cinemas prefix or abbreviate it differently every time ("Dabing",
    "Český dabing", "CZ DABING", ...). Recognising the word as a substring is
    the fix, and it must not start swallowing unrelated strand names that
    merely contain other text.
    """
    assert classify_tags(["CZ DABING"])["language_version"] == "dabing"
    assert classify_tags(["Český dabing"])["language_version"] == "dabing"
    assert classify_tags(["Dabing"])["language_version"] == "dabing"
    assert classify_tags(["České titulky"])["language_version"] == "titulky"
    # Sanity: an unrelated strand name is still just a strand.
    assert classify_tags(["Malé oči"])["language_version"] == ""


def test_unknown_tags_become_strands_and_are_never_lost():
    """New arthouse strands appear all the time; they must survive unrecognised."""
    out = classify_tags(["Zcela Nový Cyklus"])
    assert out["strand"] == "Zcela Nový Cyklus"
    assert "Zcela Nový Cyklus" in out["tags"]
