"""
Tests for the Kino Atlas scraper.

The genuinely new problem this cinema poses: only today's screenings are in
the plain page load; everything else comes from a paginated AJAX endpoint
found by reading the page's own JS and verified directly with `requests`
before writing any parsing code. See atlas.py's module docstring for the full
story, including why the .buy link's own timestamp (present on every row) is
used instead of the outer .line div's data-program-date (only present on
today's highlight rows).

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import atlas

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def result():
    homepage = FIXTURES.joinpath("atlas-homepage-2026-07-24.html").read_text(encoding="utf-8")
    batches = [
        FIXTURES.joinpath("atlas-ajax-batch1-2026-07-24.html").read_text(encoding="utf-8"),
        FIXTURES.joinpath("atlas-ajax-batch2-2026-07-24.html").read_text(encoding="utf-8"),
    ]
    return atlas.scrape(homepage_html=homepage, ajax_batches=batches)


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title):
    return [s for s in screenings if s["title_cz"] == title]


# --------------------------------------------------------------------------
# Overall shape
# --------------------------------------------------------------------------

def test_finds_screenings_across_the_homepage_and_both_ajax_batches(screenings):
    """100 = today's highlight rows (some already past by fetch time) plus two
    AJAX batches walked to exhaustion (data-next-cnt reached 0)."""
    assert len(screenings) == 100


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Atlas" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_covers_more_than_a_week_without_gaps(result):
    """Two AJAX batches walked to genuine exhaustion (data-next-cnt="0"),
    not just a single arbitrary page."""
    assert result["covered_dates"][0] == "2026-07-24"
    assert result["covered_dates"][-1] == "2026-08-02"
    assert result["empty_dates"] == []


# --------------------------------------------------------------------------
# The real find: a genuine ticket link on every single screening
# --------------------------------------------------------------------------

def test_every_screening_has_a_real_goout_ticket_link(screenings):
    """Unlike every other cinema in this project (a real link only sometimes,
    or never), Atlas's own markup gives a direct GoOut purchase URL on every
    row — both in the highlight section and every AJAX batch."""
    assert all("goout.net" in s["booking_url"] for s in screenings)


# --------------------------------------------------------------------------
# Director info: only present on today's highlight rows
# --------------------------------------------------------------------------

def test_director_is_present_only_for_todays_highlighted_screenings(screenings):
    """
    The .subtitle div ("Director / Country / Year") only appears in the
    homepage's special "today" section — AJAX-paginated future days use a
    simpler template with no director at all. Both are correctly handled by
    the same row-parser; the field is just genuinely absent for later days.
    """
    with_director = [s for s in screenings if s["director"]]
    assert with_director
    assert all(s["date"] == "2026-07-24" for s in with_director)


def test_a_known_directors_name_is_extracted_cleanly(screenings):
    matches = find(screenings, "Pramen")
    todays = [s for s in matches if s["date"] == "2026-07-24"]
    assert todays
    assert todays[0]["director"] == "Ivan Ostrochovský"


# --------------------------------------------------------------------------
# The three tag classes
# --------------------------------------------------------------------------

def test_language_tag_is_read_directly_as_english_friendly(screenings):
    """
    `tag language` is unambiguous — its title attribute is literally "English
    friendly" — so it's read directly rather than routed through
    classify_tags()'s generic "ENG"-string guessing.
    """
    assert any(s["english_friendly"] for s in screenings)


def test_cyklus_tag_is_a_real_themed_series(screenings):
    strands = {s["strand"] for s in screenings if s["strand"]}
    assert any("Atlas" in strand for strand in strands)


def test_no_runtime_is_ever_reported(screenings):
    """Confirmed while investigating: this site never publishes a runtime
    anywhere. TMDb resolution covers it, same philosophy as Kino Pilotů."""
    assert all(s["runtime_min"] is None for s in screenings)


# --------------------------------------------------------------------------
# Pagination internals
# --------------------------------------------------------------------------

def test_source_id_is_extracted_from_the_line_element_id(screenings):
    assert all(s["source_id"] for s in screenings)
    assert all(s["source_id"].isdigit() for s in screenings)
