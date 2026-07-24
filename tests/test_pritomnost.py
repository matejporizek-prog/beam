"""
Tests for the Kino Přítomnost scraper.

Same Aerofilms platform as Kino Aero, Bio Oko and Kino Světozor (see
aerofilms.py) — the parsing mechanics are covered by test_kino_aero.py. These
tests focus on what's specific to this cinema.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import pritomnost

FIXTURE = Path(__file__).parent / "fixtures" / "pritomnost-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return pritomnost.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def test_finds_screenings(screenings):
    assert len(screenings) == 17


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Přítomnost" for s in screenings)


def test_cinema_name_has_correct_diacritics(screenings):
    """Regression check for encoding: 'Přítomnost', not mojibake."""
    assert screenings[0]["cinema"] == "Kino Přítomnost"


def test_booking_urls_point_at_kinopritomnost(screenings):
    """Each cinema's booking links must point at its own domain, not another Aerofilms cinema's."""
    for s in screenings:
        assert s["booking_url"].startswith("https://www.kinopritomnost.cz/")


def test_shares_films_with_the_other_aerofilms_cinemas(screenings):
    """Sanity check this is genuinely the same distribution window."""
    titles = {s["title_cz"] for s in screenings}
    assert "Odyssea" in titles
    assert "Pozvání" in titles


def test_real_strand_vocabulary_is_captured(screenings):
    strands = {s["strand"] for s in screenings if s["strand"]}
    assert "Předpremiéra" in strands
    assert "Divadlo v kině" in strands


def test_hall_has_correct_diacritics(screenings):
    assert any(s["hall"] == "Kinosál" for s in screenings)


def test_theatre_broadcast_is_scraped_like_any_other_screening(screenings):
    """
    'Audience | NT Live' — a National Theatre Live broadcast, same pattern as
    Aero's 'Nebezpečné známosti | NT Live'. The scraper doesn't need to treat
    this specially; the resolver already knows these usually aren't on TMDb.
    """
    assert any("NT Live" in s["title_cz"] for s in screenings)
