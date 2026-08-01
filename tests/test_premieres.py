"""
Tests for resolve/premieres.py's pure filtering logic.

The rest of the module (fetching from TMDb, building film records) hits the
live API and is exercised by hand — same split as tests/test_resolve.py,
which tests films.py's matching/grouping logic offline against fake TMDb
payloads rather than making real requests.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from resolve.premieres import dedupe_and_filter, merge_duplicate_premieres

TODAY = "2026-07-30"


def movie(id, release_date):
    return {"id": id, "release_date": release_date, "title": f"Movie {id}"}


def premiere(tmdb_id, title_cz, release_date, director=None, synopsis_language="cs"):
    return {
        "tmdb_id": tmdb_id,
        "title_cz": title_cz,
        "release_date": release_date,
        "director": director or [],
        "synopsis_language": synopsis_language,
    }


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


# --------------------------------------------------------------------------
# merge_duplicate_premieres()
# --------------------------------------------------------------------------

def test_merges_two_tmdb_records_for_the_same_film():
    """The exact live case: TMDb registered a Czech-dub entry and a separate
    international-title entry for one film, same director and release date."""
    cz = premiere(1670546, "Tajemství křišťálové planety", "2026-08-13",
                   director=["Arsen Anton Ostojić"], synopsis_language="cs")
    en = premiere(1477654, "The Crystal Planet", "2026-08-13",
                   director=["Arsen Anton Ostojić"], synopsis_language="en")
    result = merge_duplicate_premieres([cz, en])
    assert len(result) == 1
    assert result[0]["tmdb_id"] == 1670546  # the Czech-language one wins


def test_merge_prefers_the_czech_entry_regardless_of_order():
    en = premiere(1477654, "The Crystal Planet", "2026-08-13",
                   director=["Arsen Anton Ostojić"], synopsis_language="en")
    cz = premiere(1670546, "Tajemství křišťálové planety", "2026-08-13",
                   director=["Arsen Anton Ostojić"], synopsis_language="cs")
    result = merge_duplicate_premieres([en, cz])
    assert len(result) == 1
    assert result[0]["tmdb_id"] == 1670546


def test_keeps_first_when_neither_duplicate_is_czech():
    a = premiere(1, "Film A", "2026-08-13", director=["Same Director"], synopsis_language="en")
    b = premiere(2, "Film B", "2026-08-13", director=["Same Director"], synopsis_language="en")
    result = merge_duplicate_premieres([a, b])
    assert len(result) == 1
    assert result[0]["tmdb_id"] == 1


def test_never_merges_films_without_a_director_credit():
    """Several small titles routinely lack director credits on TMDb --
    grouping on an empty director tuple would false-merge every one of them
    that happens to share a release date, which isn't a rare case."""
    a = premiere(1, "Film A", "2026-08-13", director=[])
    b = premiere(2, "Film B", "2026-08-13", director=[])
    result = merge_duplicate_premieres([a, b])
    assert {p["tmdb_id"] for p in result} == {1, 2}


def test_does_not_merge_different_directors_on_the_same_date():
    a = premiere(1, "Film A", "2026-08-13", director=["Director One"])
    b = premiere(2, "Film B", "2026-08-13", director=["Director Two"])
    result = merge_duplicate_premieres([a, b])
    assert {p["tmdb_id"] for p in result} == {1, 2}


def test_does_not_merge_the_same_director_on_different_dates():
    a = premiere(1, "Film A", "2026-08-13", director=["Same Director"])
    b = premiere(2, "Film B", "2026-09-01", director=["Same Director"])
    result = merge_duplicate_premieres([a, b])
    assert {p["tmdb_id"] for p in result} == {1, 2}


def test_matches_a_multi_director_credit_regardless_of_listed_order():
    a = premiere(1, "Film A", "2026-08-13", director=["Alice", "Bob"], synopsis_language="cs")
    b = premiere(2, "Film B", "2026-08-13", director=["Bob", "Alice"], synopsis_language="en")
    result = merge_duplicate_premieres([a, b])
    assert len(result) == 1
    assert result[0]["tmdb_id"] == 1
