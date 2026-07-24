"""
Tests for the Kino MAT scraper.

A fourth distinct platform among the cinemas in this project — no JSON-LD,
not the Aerofilms markup, not a Swiper carousel, not Edison's line-based
table. Format is exposed as a pictogram image's alt/title text rather than a
text chip, and the page carries an unusually long window (a recurring
classic-film series scheduled almost a year out), which is what surfaced a
real month-name collision bug. See mat.py's module docstring for the full
story.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import mat

FIXTURE = Path(__file__).parent / "fixtures" / "mat-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return mat.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title):
    return [s for s in screenings if s["title_cz"] == title]


def test_finds_screenings(screenings):
    assert len(screenings) == 42


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino MAT" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_shares_films_with_other_cinemas(screenings):
    titles = {s["title_cz"] for s in screenings}
    assert "Odyssea" in titles


# --------------------------------------------------------------------------
# The real bug: "červenec" (July) starts with "červen" (June)
# --------------------------------------------------------------------------

def test_july_is_not_misread_as_june(result):
    """
    The fixture was captured on 24 July 2026, and the first row is today.
    "červenec" (July) contains "červen" (June) as a literal prefix, and the
    date text has no separator to anchor a word boundary on ("24červenec") —
    checking June's name before July's silently misread every July screening
    as June on the first pass. This is the regression pin.
    """
    assert result["covered_dates"][0] == "2026-07-24"


def test_month_extraction_prefers_the_longer_name():
    from scrapers.mat import _extract_month

    class FakeDateEl:
        def __init__(self, text):
            self._text = text
        def get_text(self):
            return self._text

    class FakeRow:
        def __init__(self, text):
            self._el = FakeDateEl(text)
        def select_one(self, _sel):
            return self._el

    assert _extract_month(FakeRow("dnes24červenec")) == 7
    assert _extract_month(FakeRow("neděle02srpen")) == 8
    assert _extract_month(FakeRow("pátek01červen")) == 6  # June itself still resolves correctly


# --------------------------------------------------------------------------
# The long, multi-month window
# --------------------------------------------------------------------------

def test_covers_a_window_almost_a_year_long(result):
    """A recurring classic-film series, scheduled far in advance — genuinely
    different from every other cinema's few-week window."""
    assert result["covered_dates"][0] == "2026-07-24"
    assert result["covered_dates"][-1] == "2027-06-23"


# --------------------------------------------------------------------------
# Pictogram-based format tags
# --------------------------------------------------------------------------

def test_35mm_pictogram_becomes_a_real_format(screenings):
    """
    The format signal is an <img alt="35mm film"> pictogram, not a text chip
    — a fourth distinct tag mechanism among the cinemas scraped so far. Only
    this specific picto maps to FORMAT_TAGS' "35mm" key (its alt text is
    "35mm film", not an exact match); everything else (e.g. "Dolby Surround
    7.1") is passed through as a tag and lands in strand rather than being
    lost.
    """
    formatted = [s for s in screenings if s["format"] == "35 mm"]
    assert formatted


def test_unrecognised_pictograms_are_not_lost(screenings):
    assert any("Dolby" in s["strand"] for s in screenings)


# --------------------------------------------------------------------------
# Real ticket links, when present
# --------------------------------------------------------------------------

def test_some_screenings_have_a_real_ticket_link(screenings):
    entradio = [s for s in screenings if "entradio.cz" in s["booking_url"]]
    assert entradio
    assert len(entradio) < len(screenings), "not every screening has one — some fall back"
