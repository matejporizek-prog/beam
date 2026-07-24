"""
Tests for the Kino 35 scraper (kino35.ifp.cz — French Institute cinema).

A sixth distinct platform shape: a flat <table class="prog-list"> where date
headers and screening rows alternate directly, with per-screening detail
carried on icon `title` attributes instead of free-text tags. See
kino35.py's module docstring for the summer-recess notice row, the
english_friendly-from-subtitles-alone case, and why no pagination is needed.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import kino35

FIXTURE = Path(__file__).parent / "fixtures" / "kino35-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return kino35.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title_contains):
    return [s for s in screenings if title_contains.lower() in s["title_cz"].lower()]


def test_finds_screenings(screenings):
    # 4 real showtimes; the "KINO MÁ PRÁZDNINY" recess notice row is excluded.
    assert len(screenings) == 4


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino 35" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_covers_august_to_october(result):
    assert result["covered_dates"][0] == "2026-09-01"
    assert result["covered_dates"][-1] == "2026-10-20"


# --------------------------------------------------------------------------
# The summer-recess notice row must not become a fake screening
# --------------------------------------------------------------------------

def test_recess_notice_row_is_not_a_screening(screenings):
    assert find(screenings, "PRÁZDNINY") == []


# --------------------------------------------------------------------------
# Year inference across an ascending month sequence with no year printed
# --------------------------------------------------------------------------

def test_all_screenings_land_in_the_current_year(screenings):
    assert all(s["date"].startswith("2026-") for s in screenings)


# --------------------------------------------------------------------------
# Sound / subtitle icons
# --------------------------------------------------------------------------

def test_spoken_language_comes_from_the_sound_icon(screenings):
    puccini = find(screenings, "BOH")
    assert puccini
    assert puccini[0]["language"] == "italština"


def test_a_silent_or_undubbed_screening_has_no_spoken_language(screenings):
    alice_guy = find(screenings, "Alice Guy")
    assert alice_guy
    assert alice_guy[0]["language"] == ""


def test_english_friendly_from_subtitles_alone(screenings):
    """
    The Alice Guy shorts programme has no sound icon at all, only French +
    English subtitles — english_friendly must be recognised from the
    subtitle codes, not just a spoken-language match.
    """
    alice_guy = find(screenings, "Alice Guy")
    assert alice_guy
    assert alice_guy[0]["english_friendly"] is True


def test_a_non_english_screening_is_not_english_friendly(screenings):
    vagabundi = find(screenings, "Vagabundi")
    assert vagabundi
    assert all(s["english_friendly"] is False for s in vagabundi)


# --------------------------------------------------------------------------
# The "Speciální večer" flag icon becomes a strand tag
# --------------------------------------------------------------------------

def test_special_evening_flag_becomes_a_strand(screenings):
    assert all(s["strand"] == "Speciální večer" for s in screenings)


# --------------------------------------------------------------------------
# Real per-screening ticket links
# --------------------------------------------------------------------------

def test_every_screening_has_a_real_ticket_link(screenings):
    assert all("koupitvstupenku.cz" in s["booking_url"] for s in screenings)


def test_ticket_links_are_distinct_per_screening(screenings):
    urls = {s["booking_url"] for s in screenings}
    assert len(urls) == len(screenings)


# --------------------------------------------------------------------------
# Same film, two showtimes on the same day
# --------------------------------------------------------------------------

def test_repeated_screening_appears_twice(screenings):
    vagabundi = find(screenings, "Vagabundi")
    assert len(vagabundi) == 2
    assert {s["time"] for s in vagabundi} == {"17:00", "19:00"}
