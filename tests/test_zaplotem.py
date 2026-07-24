"""
Tests for the Divadlo Za plotem scraper.

A WordPress/GenerateBlocks site — a fifth distinct platform shape among the
cinemas in this project, with no clean per-screening container. What makes it
parseable is a set of semantic (if invalidly repeated) `id` attributes
GenerateBlocks stamps on each block. See zaplotem.py's module docstring for
the full story, including why "CZ DAB" is matched as an exact token locally
rather than widening the shared substring rule, and why the venue's ALL CAPS
titles aren't touched here.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import zaplotem

FIXTURE = Path(__file__).parent / "fixtures" / "zaplotem-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return zaplotem.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title_contains):
    return [s for s in screenings if title_contains.upper() in s["title_cz"].upper()]


def test_finds_screenings(screenings):
    assert len(screenings) == 6


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Divadlo Za plotem" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_covers_two_days(result):
    assert result["covered_dates"] == ["2026-07-28", "2026-07-30"]


# --------------------------------------------------------------------------
# Runtime from the bundled country/agerating/runtime prose line
# --------------------------------------------------------------------------

def test_runtime_is_extracted(screenings):
    toy_story = find(screenings, "TOY STORY 5")
    assert toy_story
    assert toy_story[0]["runtime_min"] == 102


def test_all_screenings_have_a_runtime(screenings):
    """Unlike most cinemas here, this venue publishes runtime for every
    screening — no cinema-wide gap the way Kino Atlas or Kino Pilotů have."""
    assert all(s["runtime_min"] for s in screenings)


# --------------------------------------------------------------------------
# "CZ DAB" — a third, shorter dabing abbreviation, matched locally
# --------------------------------------------------------------------------

def test_cz_dab_is_recognised_as_dabing(screenings):
    toy_story = find(screenings, "TOY STORY 5")
    assert toy_story
    assert toy_story[0]["language_version"] == "dabing"


def test_plain_cz_is_not_mistaken_for_dabing(screenings):
    bardotky = find(screenings, "BARDOTKY")
    assert bardotky
    assert all(s["language_version"] == "" for s in bardotky)


# --------------------------------------------------------------------------
# Real ticket links on every screening
# --------------------------------------------------------------------------

def test_every_screening_has_a_real_webticket_link(screenings):
    assert all("webticket.cz" in s["booking_url"] for s in screenings)


def test_ticket_links_are_distinct_per_screening(screenings):
    """Each screening has its own webticket event id, not a shared program link."""
    urls = {s["booking_url"] for s in screenings}
    assert len(urls) == len(screenings)


# --------------------------------------------------------------------------
# Hall types: this venue has three (kino, kino junior, kino senior)
# --------------------------------------------------------------------------

def test_hall_types_are_captured(screenings):
    halls = {s["hall"] for s in screenings}
    assert "kino" in halls
    assert "kino junior" in halls
    assert "kino senior" in halls


# --------------------------------------------------------------------------
# The ALL CAPS title question
# --------------------------------------------------------------------------

def test_titles_are_scraped_as_is_all_caps_and_all(screenings):
    """
    This venue's own titles really are ALL CAPS — not fixed here. Checked
    separately (see test_resolve.py / the scraper's module docstring) that
    the resolver's existing majority-spelling canonicalisation already
    displays the properly-cased title whenever the same film also plays
    elsewhere, which both of these do.
    """
    toy_story = find(screenings, "toy story 5")
    assert toy_story
    assert toy_story[0]["title_cz"] == toy_story[0]["title_cz"].upper()
