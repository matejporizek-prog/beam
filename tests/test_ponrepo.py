"""
Tests for the Kino Ponrepo scraper.

Ponrepo is closed for reconstruction, reopening 31.8.2026 — this is the
"cinema temporarily has zero screenings" test case the planning doc calls out
by name. Confirmed structurally before writing anything: every day link on
the real program page carries a `--disabled` class, and there is no hidden
per-day content section anywhere on the page. See ponrepo.py's module
docstring for the full story, including why it deliberately does NOT contain
speculative screening-extraction logic.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

from scrapers import ponrepo

FIXTURE = Path(__file__).parent / "fixtures" / "ponrepo-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return ponrepo.scrape(html=FIXTURE.read_text(encoding="utf-8"))


def test_reports_the_cinema_correctly(result):
    assert result["cinema"] == "Kino Ponrepo"


def test_no_screenings_found(result):
    """
    The expected, correct state right now — not a scraper failure. Ponrepo is
    closed; a scraper reporting real screenings today would be the bug.
    """
    assert result["screenings"] == []


def test_reports_the_known_reopening_date(result):
    assert result["closed_until"] == "2026-08-31"


def test_covers_the_whole_visible_month(result):
    """
    The calendar's day links carry a real ISO date in their href
    ("#2026-07-01") — no Czech-month-name parsing needed, unlike Kino Pilotů.
    """
    assert result["covered_dates"][0] == "2026-07-01"
    assert result["covered_dates"][-1] == "2026-07-31"
    assert len(result["covered_dates"]) == 31


def test_every_covered_day_is_reported_empty(result):
    """
    Every day the calendar shows is empty right now — this is what lets the
    app distinguish "we checked and there's nothing" from "we never looked",
    the same signal every other cinema's quiet day produces.
    """
    assert result["covered_dates"] == result["empty_dates"]


def test_scraping_twice_gives_identical_results():
    """No hidden per-call state (the same class of bug the Kino Pilotů scraper
    was fixed for) — scrape() must be safely callable more than once.
    scraped_at is excluded: it's a real wall-clock timestamp and legitimately
    differs between calls, even a second apart."""
    html = FIXTURE.read_text(encoding="utf-8")
    first = {k: v for k, v in ponrepo.scrape(html=html).items() if k != "scraped_at"}
    second = {k: v for k, v in ponrepo.scrape(html=html).items() if k != "scraped_at"}
    assert first == second


# --------------------------------------------------------------------------
# The tripwire: does it actually fire when the site's state changes?
# --------------------------------------------------------------------------

def test_warns_if_a_day_becomes_enabled():
    """
    The whole point of building this scraper now, before real listings exist,
    is that someone has to notice when the cinema reopens and real
    screening-extraction logic needs writing. Simulate that by clearing the
    disabled class on one day link and confirming the warning actually fires —
    a silent no-op here would defeat the entire mechanism.
    """
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace("calendar-slider__link--disabled", "calendar-slider__link", 1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ponrepo.scrape(html=html)

    assert any("reopened" in str(w.message) for w in caught)


def test_warns_if_a_day_content_section_appears():
    """The other tripwire signal: a matching id="<date>" section appearing."""
    html = FIXTURE.read_text(encoding="utf-8")
    html = html.replace("<body>", '<body><div id="2026-07-24">something</div>', 1)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ponrepo.scrape(html=html)

    assert any("reopened" in str(w.message) for w in caught)


def test_no_warning_in_the_normal_closed_state(result):
    """The tripwire must stay silent for the real, currently-closed page."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        ponrepo.scrape(html=FIXTURE.read_text(encoding="utf-8"))
    assert len(caught) == 0
