"""
Tests for the Kino Světozor scraper.

Same Aerofilms platform as Kino Aero and Bio Oko (see aerofilms.py) — the
parsing mechanics are covered by test_kino_aero.py. These tests focus on what's
specific to this cinema.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import svetozor

FIXTURE = Path(__file__).parent / "fixtures" / "svetozor-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return svetozor.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def test_finds_screenings(screenings):
    assert len(screenings) == 41


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Světozor" for s in screenings)


def test_cinema_name_has_correct_diacritics(screenings):
    """Regression check for encoding: 'Světozor', not mojibake."""
    assert screenings[0]["cinema"] == "Kino Světozor"


def test_booking_urls_point_at_kinosvetozor(screenings):
    """Each cinema's booking links must point at its own domain, not Aero's."""
    for s in screenings:
        assert s["booking_url"].startswith("https://www.kinosvetozor.cz/")


def test_shares_a_film_with_aero_and_bio_oko(screenings):
    """
    Sanity check that this is genuinely the same distribution window: Odyssea
    (the 35mm test case from Aero) is also playing here.
    """
    assert any(s["title_cz"] == "Odyssea" for s in screenings)


def test_real_strand_vocabulary_is_captured(screenings):
    strands = {s["strand"] for s in screenings if s["strand"]}
    assert "Bio Senior" in strands
    assert "Výstavy na plátně" in strands


def test_hall_names_have_correct_diacritics(screenings):
    halls = {s["hall"] for s in screenings if s["hall"]}
    assert "Malý sál" in halls
