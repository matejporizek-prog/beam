"""
Tests for the Kino Lucerna scraper.

Same Aerofilms platform as Kino Aero, Bio Oko, Kino Světozor and Kino
Přítomnost (see aerofilms.py) — the parsing mechanics are covered by
test_kino_aero.py. These tests focus on what's specific to this cinema: its
program lives on the homepage rather than at /program/.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import lucerna

FIXTURE = Path(__file__).parent / "fixtures" / "lucerna-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return lucerna.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def test_finds_screenings(screenings):
    assert len(screenings) == 48


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Lucerna" for s in screenings)


def test_cinema_name_has_correct_diacritics(screenings):
    assert screenings[0]["cinema"] == "Kino Lucerna"


def test_booking_urls_point_at_kinolucerna(screenings):
    for s in screenings:
        assert s["booking_url"].startswith("https://www.kinolucerna.cz/")


def test_shares_films_with_the_other_aerofilms_cinemas(screenings):
    titles = {s["title_cz"] for s in screenings}
    assert "Pozvání" in titles or "Odyssea" in titles


def test_director_and_runtime_are_present(screenings):
    """Same JSON-LD richness as every other Aerofilms cinema."""
    with_director = [s for s in screenings if s["director"]]
    assert len(with_director) == len(screenings)
