"""
Tests for resolve/premieres.py's pure filtering logic.

The rest of the module (fetching from TMDb, building film records) hits the
live API and is exercised by hand — same split as tests/test_resolve.py,
which tests films.py's matching/grouping logic offline against fake TMDb
payloads rather than making real requests.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from resolve.premieres import dedupe_and_filter

TODAY = "2026-07-30"


def movie(id, release_date):
    return {"id": id, "release_date": release_date, "title": f"Movie {id}"}


def test_keeps_movies_dated_today_or_later():
    raw = [movie(1, "2026-07-30"), movie(2, "2026-08-15"), movie(3, "2026-12-01")]
    result = dedupe_and_filter(raw, TODAY)
    assert {m["id"] for m in result} == {1, 2, 3}


def test_drops_movies_dated_before_today():
    """
    The exact case found in testing: an old title (Avengers: Endgame, 2019)
    slipped through TMDb's own date filter because of a rerelease entry it
    doesn't surface — the field it *does* display is the original release,
    which is what this defensive floor catches.
    """
    raw = [movie(1, "2019-04-25"), movie(2, "2026-08-15")]
    result = dedupe_and_filter(raw, TODAY)
    assert [m["id"] for m in result] == [2]


def test_drops_entries_with_no_release_date():
    raw = [movie(1, ""), movie(2, "2026-08-15")]
    result = dedupe_and_filter(raw, TODAY)
    assert [m["id"] for m in result] == [2]


def test_drops_entries_with_no_id():
    raw = [{"release_date": "2026-08-15"}, movie(2, "2026-08-15")]
    result = dedupe_and_filter(raw, TODAY)
    assert [m["id"] for m in result] == [2]


def test_dedupes_by_id_keeping_first_occurrence():
    """A rerun combining cached results with a fresh page should never double
    up a film just because it appears on more than one discover page."""
    raw = [movie(1, "2026-08-01"), movie(1, "2026-08-01"), movie(2, "2026-09-01")]
    result = dedupe_and_filter(raw, TODAY)
    assert [m["id"] for m in result] == [1, 2]
