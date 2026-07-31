"""
Tests for the Premiere Cinemas Praha Hostivař scraper.

These run against a saved copy of premierecinemas.cz's homepage (captured
31 July 2026), which is also its program page — the whole week's schedule
sits in one page load, one day-tab panel per date. Not fetched live, same
reasoning as every other fixture-based test in this suite.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import premiere_hostivar

FIXTURE = Path(__file__).parent / "fixtures" / "premiere-hostivar-program-2026-07-31.html"


@pytest.fixture(scope="module")
def result():
    return premiere_hostivar.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title, date=None, time=None):
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

def test_covers_all_seven_real_day_tabs(result):
    # Seven weekday tabs with real dates; the eighth ("Předprodej" / presale)
    # has no day.month in its label and must not show up as a made-up date.
    assert result["covered_dates"] == [
        "2026-07-31", "2026-08-01", "2026-08-02", "2026-08-03",
        "2026-08-04", "2026-08-05", "2026-08-06",
    ]


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["cinema"] == "Premiere Cinemas Praha Hostivař"
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_output_matches_the_sample_data_shape(screenings):
    core = {"cinema", "title_cz", "date", "time", "language", "format", "note"}
    assert core.issubset(set(screenings[0].keys()))


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_a_thin_day_is_reported_as_empty_not_silently_dropped(result):
    """This snapshot's Thursday (6.8.) tab has no film rows at all — it must
    still show up as a covered, empty day, not vanish from the range."""
    assert "2026-08-06" in result["empty_dates"]
    assert "2026-08-06" in result["covered_dates"]


# --------------------------------------------------------------------------
# One film, multiple showings across a day — the table-column parsing
# --------------------------------------------------------------------------

def test_odyssea_has_both_dubbed_and_subtitled_showings(screenings):
    """
    One row's several hour-columns must become several distinct screenings,
    each keeping its own time and booking link — not collapsed into one, and
    not all inheriting the same (wrong) version.
    """
    dubbed = find(screenings, "Odyssea", date="2026-07-31", time="15:50")
    assert dubbed["language_version"] == "dabing"
    assert dubbed["english_friendly"] is False
    assert dubbed["booking_url"] == "https://www.premierecinemas.cz/vstupenky/170986/"

    subtitled = find(screenings, "Odyssea", date="2026-07-31", time="19:20")
    assert subtitled["language_version"] == "titulky"
    assert subtitled["english_friendly"] is True
    assert subtitled["booking_url"] == "https://www.premierecinemas.cz/vstupenky/170992/"


def test_a_past_showing_with_no_booking_link_still_parses(screenings):
    """
    An already-past slot renders as a plain <span> instead of a booking
    <a> — the time must still be read correctly, just with an empty
    booking_url rather than a broken or missing screening.
    """
    s = find(screenings, "Odyssea", date="2026-07-31", time="14:00")
    assert s["booking_url"] == ""


def test_title_text_excludes_nested_badge_spans(screenings):
    """
    The movie-title cell nests "4K"/"Premiéra" badge spans inside the same
    <a> as the title — those must never leak into title_cz.
    """
    s = find(screenings, "Odyssea", date="2026-07-31", time="15:50")
    assert s["title_cz"] == "Odyssea"
    assert "4K" not in s["title_cz"]
    assert "Premiéra" not in s["title_cz"]


def test_language_version_is_only_ever_a_known_value(screenings):
    assert {s["language_version"] for s in screenings} <= {"dabing", "titulky", "originál", ""}
