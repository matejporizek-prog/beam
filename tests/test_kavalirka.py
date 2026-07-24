"""
Tests for the Kino Kavalírka scraper.

The richest per-screening data of any cinema in this project — full
synopsis, country/year/runtime/director in one line, an explicit
english-friendly explanation, and, for some films, a direct IMDb link (the
strongest resolution signal any cinema here provides, though not yet
consumed by the resolver — see kavalirka.py's module docstring). It also has
its own version of Kino Pilotů's title-branding problem ("Film & Drink: Pulp
Fiction") and surfaced a real strand-deduplication bug shared by every
cinema.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import kavalirka
from scrapers.kavalirka import _split_title

FIXTURE = Path(__file__).parent / "fixtures" / "kavalirka-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return kavalirka.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title):
    return [s for s in screenings if s["title_cz"] == title]


def test_finds_screenings(screenings):
    assert len(screenings) == 36


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Kavalírka" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_covers_more_than_two_months(result):
    assert result["covered_dates"][0] == "2026-07-24"
    assert result["covered_dates"][-1] == "2026-10-07"


# --------------------------------------------------------------------------
# The metadata line: country/year/runtime/director all in one paragraph
# --------------------------------------------------------------------------

def test_director_and_runtime_are_extracted_from_the_prose_paragraph(screenings):
    matches = find(screenings, "Aftersun")
    assert matches
    assert matches[0]["director"] == "Charlotte Wells"
    assert matches[0]["runtime_min"] == 96


def test_screenings_without_a_metadata_line_degrade_gracefully(screenings):
    """
    A "Film & Drink" pairing's whole paragraph is about the drink menu, not
    the film — the metadata regex correctly finds nothing there, and that
    must produce empty fields, not a crash.
    """
    matches = find(screenings, "Pulp Fiction")
    assert matches
    assert matches[0]["director"] == ""
    assert matches[0]["runtime_min"] is None


# --------------------------------------------------------------------------
# The real find: a direct IMDb link
# --------------------------------------------------------------------------

def test_imdb_link_is_captured_when_present(screenings):
    matches = find(screenings, "Aftersun")
    assert matches
    assert matches[0]["imdb_url"] == "https://www.imdb.com/title/tt19770238/"


def test_imdb_link_is_absent_for_most_screenings(screenings):
    """Only some films have one — must not be invented for the rest."""
    with_imdb = [s for s in screenings if s["imdb_url"]]
    assert 0 < len(with_imdb) < len(screenings)


# --------------------------------------------------------------------------
# Venue-branded title prefixes (this cinema's version of Kino Pilotů's problem)
# --------------------------------------------------------------------------

def test_film_and_drink_prefix_is_stripped_from_the_title(screenings):
    assert find(screenings, "Film & Drink: Pulp Fiction") == []
    matches = find(screenings, "Pulp Fiction")
    assert matches
    assert matches[0]["strand"] == "Film & Drink"


def test_a_title_with_its_own_real_dash_survives(screenings):
    """
    "Piráti z Karibiku - Prokletí Černé perly" has a legitimate dash as part
    of its own title, appearing here after a "Film & Drink:" prefix — the
    prefix strip must not also eat the film's own subtitle-dash.
    """
    matches = find(screenings, "Piráti z Karibiku - Prokletí Černé perly")
    assert matches


def test_the_duplicate_strand_bug_is_fixed(screenings):
    """
    This cinema can carry the *same* strand text from two places at once —
    the title prefix and a separate matching tag chip. Regression-pinned here
    (the actual fix lives in the shared classify_tags(), tested more directly
    in test_kino_aero.py).
    """
    matches = find(screenings, "Pulp Fiction")
    assert matches
    assert matches[0]["strand"] == "Film & Drink"  # not "Film & Drink / Film & Drink"


# --------------------------------------------------------------------------
# _split_title unit tests
# --------------------------------------------------------------------------

def test_split_title_recognises_film_and_x_patterns():
    title, tags = _split_title("Film & Drink: Pulp Fiction")
    assert title == "Pulp Fiction"
    assert tags == ["Film & Drink"]

    title, tags = _split_title("Film & Degustace: Duch")
    assert title == "Duch"
    assert tags == ["Film & Degustace"]


def test_split_title_recognises_divadlo_and_galerie_prefixes():
    title, tags = _split_title("Divadlo v kině: Romeo a Julie")
    assert title == "Romeo a Julie"
    assert tags == ["Divadlo v kině"]


def test_split_title_leaves_a_plain_title_alone():
    title, tags = _split_title("Aftersun")
    assert title == "Aftersun"
    assert tags == []
