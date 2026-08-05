"""
Tests for run.py's per-cinema fallback — added alongside base.py's retry fix
for the same 2026-08-02 incident (Kino Pilotů vanishing from the whole app
over one connection timeout). base.py's retries absorb the common case; this
covers what happens when a scraper still fails after those.

Never touches the real data/screenings.json: OUTPUT_FILE is patched to a
pytest tmp_path for every test here.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import patch

from scrapers.run import _forward_looking, _previous_screenings_by_cinema, run

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def screening(cinema, iso_date, time="20:00", title="Film"):
    return {"cinema": cinema, "title_cz": title, "date": iso_date, "time": time}


# --------------------------------------------------------------------------
# _forward_looking()
# --------------------------------------------------------------------------

def test_forward_looking_keeps_today_and_later():
    shows = [screening("X", YESTERDAY), screening("X", TODAY), screening("X", TOMORROW)]
    kept = _forward_looking(shows)
    assert kept == [screening("X", TODAY), screening("X", TOMORROW)]


def test_forward_looking_returns_nothing_for_an_entirely_stale_cinema():
    shows = [screening("X", YESTERDAY)]
    assert _forward_looking(shows) == []


# --------------------------------------------------------------------------
# _previous_screenings_by_cinema()
# --------------------------------------------------------------------------

def test_previous_screenings_groups_by_cinema(tmp_path):
    output_file = tmp_path / "screenings.json"
    output_file.write_text(json.dumps({
        "screenings": [screening("A", TODAY), screening("B", TODAY), screening("A", TOMORROW)],
    }), encoding="utf-8")

    with patch("scrapers.run.OUTPUT_FILE", output_file):
        by_cinema = _previous_screenings_by_cinema()

    assert len(by_cinema["A"]) == 2
    assert len(by_cinema["B"]) == 1


def test_previous_screenings_is_empty_when_no_file_exists(tmp_path):
    with patch("scrapers.run.OUTPUT_FILE", tmp_path / "does-not-exist.json"):
        assert _previous_screenings_by_cinema() == {}


def test_previous_screenings_is_empty_when_the_file_is_corrupt(tmp_path):
    output_file = tmp_path / "screenings.json"
    output_file.write_text("{ not valid json", encoding="utf-8")
    with patch("scrapers.run.OUTPUT_FILE", output_file):
        assert _previous_screenings_by_cinema() == {}


# --------------------------------------------------------------------------
# run() end to end
# --------------------------------------------------------------------------

def test_a_failed_scraper_falls_back_to_forward_looking_previous_data(tmp_path):
    output_file = tmp_path / "screenings.json"
    output_file.write_text(json.dumps({
        "screenings": [
            screening("Broken Cinema", YESTERDAY),
            screening("Broken Cinema", TOMORROW, title="Still Showing"),
        ],
    }), encoding="utf-8")

    def broken_scraper():
        raise RuntimeError("connection timed out")

    def working_scraper():
        return {"source_url": "https://ok.example", "screenings": [screening("Working Cinema", TODAY)]}

    fake_scrapers = {"Broken Cinema": broken_scraper, "Working Cinema": working_scraper}

    with patch("scrapers.run.OUTPUT_FILE", output_file), \
         patch.dict("scrapers.run.SCRAPERS", fake_scrapers, clear=True):
        payload = run(dry_run=True)

    # The failure is still recorded — falling back never hides that the live
    # scrape actually failed.
    assert payload["failures"] == [{"cinema": "Broken Cinema", "error": "connection timed out"}]

    # But the cinema itself stays present, using only its still-forward-looking
    # screenings, marked stale so the distinction isn't lost.
    broken_entry = next(c for c in payload["cinemas"] if c["name"] == "Broken Cinema")
    assert broken_entry["stale"] is True

    broken_screenings = [s for s in payload["screenings"] if s["cinema"] == "Broken Cinema"]
    assert len(broken_screenings) == 1
    assert broken_screenings[0]["date"] == TOMORROW

    working_screenings = [s for s in payload["screenings"] if s["cinema"] == "Working Cinema"]
    assert len(working_screenings) == 1


def test_a_failed_scraper_with_no_usable_fallback_just_records_the_failure(tmp_path):
    """A cinema that's been down long enough that even yesterday's data has
    run out behaves exactly like before this fix: recorded as failed,
    contributes nothing — never an invented or stale-beyond-usefulness
    schedule."""
    output_file = tmp_path / "screenings.json"
    output_file.write_text(json.dumps({
        "screenings": [screening("Long Broken", YESTERDAY)],
    }), encoding="utf-8")

    def broken_scraper():
        raise RuntimeError("still down")

    with patch("scrapers.run.OUTPUT_FILE", output_file), \
         patch.dict("scrapers.run.SCRAPERS", {"Long Broken": broken_scraper}, clear=True):
        payload = run(dry_run=True)

    assert payload["failures"] == [{"cinema": "Long Broken", "error": "still down"}]
    assert payload["cinemas"] == []
    assert payload["screenings"] == []


def test_a_cinema_that_scrapes_clean_but_finds_nothing_is_flagged(tmp_path):
    """No exception, but zero screenings across the whole covered window —
    the silent-break case an exception-based failure can't see. Every cinema
    here screens regularly, so this almost always means a selector or API
    shape changed, not a real quiet stretch."""
    def empty_scraper():
        return {"source_url": "https://ok.example", "screenings": []}

    with patch("scrapers.run.OUTPUT_FILE", tmp_path / "does-not-exist.json"), \
         patch.dict("scrapers.run.SCRAPERS", {"Quiet Cinema": empty_scraper}, clear=True):
        payload = run(dry_run=True)

    assert payload["failures"] == [{
        "cinema": "Quiet Cinema",
        "error": "ran without error but found 0 screenings — a selector or API shape may have changed",
    }]
    # Unlike an exception-based failure, the cinema itself still shows up —
    # there's nothing wrong with the entry, just nothing in it.
    assert payload["cinemas"] == [{"name": "Quiet Cinema", "source_url": "https://ok.example"}]


def test_a_real_planned_closure_is_not_flagged(tmp_path):
    """A scraper that reports closed_until (Ponrepo's case) means the zero
    screenings are explained and expected — not a silent break."""
    def closed_scraper():
        return {"source_url": "https://ok.example", "screenings": [], "closed_until": "2026-09-01"}

    with patch("scrapers.run.OUTPUT_FILE", tmp_path / "does-not-exist.json"), \
         patch.dict("scrapers.run.SCRAPERS", {"Closed Cinema": closed_scraper}, clear=True):
        payload = run(dry_run=True)

    assert payload.get("failures") is None


def test_no_fallback_available_on_a_brand_new_first_run(tmp_path):
    """No previous screenings.json at all (a first-ever run) must behave
    identically to today's failure handling — no crash, no fallback to
    reach for."""
    def broken_scraper():
        raise RuntimeError("down")

    with patch("scrapers.run.OUTPUT_FILE", tmp_path / "does-not-exist.json"), \
         patch.dict("scrapers.run.SCRAPERS", {"New Cinema": broken_scraper}, clear=True):
        payload = run(dry_run=True)

    assert payload["failures"] == [{"cinema": "New Cinema", "error": "down"}]
    assert payload["cinemas"] == []
