"""
Tests for the Cinema City scraper (cinema_city.py + cinema_city_flora.py).

These run against two saved days of the real quickbook API response for
Cinema City Flora (captured 31 July 2026: at-date/2026-08-01 and
at-date/2026-08-02), passed in via `payloads` rather than fetched live —
same offline-and-stable idea as every HTML-fixture test elsewhere in this
suite, just keyed by date instead of being one page.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapers import cinema_city, cinema_city_flora

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


PAYLOADS = {
    "2026-08-01": _load("cinema-city-flora-2026-08-01.json"),
    "2026-08-02": _load("cinema-city-flora-2026-08-02.json"),
}


@pytest.fixture(scope="module")
def result():
    return cinema_city.scrape("Cinema City Flora", "1052", payloads=PAYLOADS)


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

def test_finds_every_event_across_both_days(screenings):
    # 45 events each day in the saved fixtures.
    assert len(screenings) == 90


def test_covers_exactly_the_dates_passed_in(result):
    assert result["covered_dates"] == ["2026-08-01", "2026-08-02"]


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["cinema"] == "Cinema City Flora"
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_output_matches_the_sample_data_shape(screenings):
    core = {"cinema", "title_cz", "date", "time", "language", "format", "note"}
    assert core.issubset(set(screenings[0].keys()))


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------
# One screening, end to end — the IMAX 70mm Odyssea showing
# --------------------------------------------------------------------------

def test_odyssea_imax_screening_parses_completely(screenings):
    s = find(screenings, "Odyssea", date="2026-08-01", time="09:00")

    assert s["format"] == "70 mm"           # from the "70-mm" attribute
    assert s["hall"] == "IMAX"              # from auditoriumTinyName
    assert s["language"] == "angličtina"    # original: ["en"]
    assert s["language_version"] == "titulky"  # subtitles: ["cs"], not dubbed
    assert s["english_friendly"] is True
    assert s["runtime_min"] == 180  # Cinema City's own listed runtime for this print
    assert s["source_id"] == "212838"
    assert s["booking_url"].startswith("https://www.cinemacity.cz/cz/booking-router/launch/")
    assert s["poster_url"].startswith("https://www.cinemacity.cz/")


def test_dubbed_screening_is_not_english_friendly(screenings):
    s = find(screenings, "Odyssea", date="2026-08-01", time="19:10")
    assert s["language_version"] == "dabing"
    assert s["english_friendly"] is False


# --------------------------------------------------------------------------
# Tag classification
# --------------------------------------------------------------------------

def test_format_never_leaks_genre_or_age_rating_noise(screenings):
    for s in screenings:
        assert s["format"] in ("", "35 mm", "70 mm", "3D")


def test_raw_attribute_codes_are_kept_in_tags(screenings):
    """Genre/age-rating codes aren't classified into anything, but must
    still survive in `tags` — nothing scraped is silently dropped."""
    s = find(screenings, "Odyssea", date="2026-08-01", time="09:00")
    assert "history" in s["tags"]
    assert "15-plus" in s["tags"]


# --------------------------------------------------------------------------
# The three-line wrapper
# --------------------------------------------------------------------------

def test_flora_wrapper_calls_through_with_its_own_name_and_id():
    result = cinema_city_flora.scrape(payloads=PAYLOADS)
    assert result["cinema"] == "Cinema City Flora"
    assert result["source_url"] == "https://www.cinemacity.cz/cz/cinema/1052"
    assert len(result["screenings"]) == 90


# --------------------------------------------------------------------------
# Helper units
# --------------------------------------------------------------------------

def test_language_info_maps_dubbed_titulky_and_original():
    dabing, dabing_eng, dabing_lang = cinema_city._language_info(
        {"original": ["en"], "dubbed": ["cs"], "subtitles": []}
    )
    assert (dabing, dabing_eng) == ("dabing", False)

    titulky, titulky_eng, titulky_lang = cinema_city._language_info(
        {"original": ["en"], "dubbed": [], "subtitles": ["cs"]}
    )
    assert (titulky, titulky_eng) == ("titulky", True)
    assert titulky_lang == "angličtina"

    czech_original, czech_eng, _ = cinema_city._language_info(
        {"original": ["cs"], "dubbed": [], "subtitles": []}
    )
    assert (czech_original, czech_eng) == ("", False)


def test_a_missing_date_is_skipped_not_fatal():
    """A date absent from `payloads` (a bad fetch, in production) must not
    take down the rest of the cinema's week."""
    partial = {"2026-08-01": PAYLOADS["2026-08-01"]}
    result = cinema_city.scrape("Cinema City Flora", "1052", payloads=partial)
    assert result["covered_dates"] == ["2026-08-01"]
    assert len(result["screenings"]) == 45
