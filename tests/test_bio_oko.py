"""
Tests for the Bio Oko scraper.

Bio Oko runs on the same Aerofilms platform as Kino Aero (see aerofilms.py),
so the parsing mechanics are already covered by test_kino_aero.py. These tests
focus on what's specific to this cinema: its real strand vocabulary, and the
"orig" language-code fix this fixture surfaced.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import bio_oko

FIXTURE = Path(__file__).parent / "fixtures" / "bio-oko-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return bio_oko.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def test_finds_screenings(screenings):
    # Bio Oko's real program on this page: 29 rows across a week.
    assert len(screenings) == 29


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Bio Oko" for s in screenings)


def test_booking_urls_point_at_biooko_net(screenings):
    """Each cinema's booking links must point at its own domain, not Aero's."""
    for s in screenings:
        assert s["booking_url"].startswith("https://www.biooko.net/")


def test_real_strand_vocabulary_is_captured(screenings):
    """Bio Oko runs its own programming strands, distinct from Aero's."""
    strands = {s["strand"] for s in screenings if s["strand"]}
    assert "Baby Bio" in strands
    assert "Bio Senior" in strands
    assert "Malé oči" in strands


def test_orig_is_not_treated_as_a_language(screenings):
    """
    Found on this fixture: Bio Oko's JSON-LD writes inLanguage="orig" for an
    original-version screening with no language specified. "orig" is not a
    language and must not leak into the language field as literal text.
    """
    assert not any(s["language"] == "orig" for s in screenings)
    assert not any("orig" in s["language"].split(", ") for s in screenings)


def test_director_with_diacritics_is_correct(screenings):
    """Regression check for encoding: 'Pedro Almodóvar', not mojibake."""
    almodovar = [s for s in screenings if "Almod" in s["title_cz"]]
    assert almodovar, "expected an Almodóvar screening in this fixture"
    assert almodovar[0]["director"] == "Pedro Almodóvar"


def test_hall_has_correct_diacritics(screenings):
    assert any(s["hall"] == "Kinosál" for s in screenings)


def test_booking_url_domain_is_derived_not_hardcoded():
    """
    The shared aerofilms parser must derive each cinema's booking domain from
    ITS OWN program_url, not from a value copied out of the Aero module. This
    is the one thing that's genuinely new versus a single-cinema scraper: three
    cinemas sharing one parser must never cross-link to each other's domain.
    """
    from scrapers import aerofilms

    html = FIXTURE.read_text(encoding="utf-8")
    result = aerofilms.scrape("Bio Oko", "https://www.biooko.net/program/", html=html)
    for s in result["screenings"]:
        assert "biooko.net" in s["booking_url"]
        assert "kinoaero.cz" not in s["booking_url"]
        assert "kinosvetozor.cz" not in s["booking_url"]
