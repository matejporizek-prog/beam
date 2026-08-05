"""
Tests for the CineStar scraper (cinestar.py + cinestar_andel.py).

Run against one saved day-of capture of the real CineStar Praha Anděl
program page and its matching GraphQL catalog response (captured 5 August
2026: tests/fixtures/cinestar-praha5.html and
cinestar-praha5-catalog.json), passed in via `html`/`catalog` rather than
fetched live — same offline-and-stable idea as every other fixture-based
scraper test in this suite.

Run them with:   python -m pytest tests -v
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapers import cinestar, cinestar_andel, devalue

FIXTURES = Path(__file__).parent / "fixtures"

HTML = (FIXTURES / "cinestar-praha5.html").read_text(encoding="utf-8")
CATALOG = json.loads((FIXTURES / "cinestar-praha5-catalog.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result():
    return cinestar.scrape("CineStar Anděl", "praha5", html=HTML, catalog=CATALOG)


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title, date=None, time=None):
    for s in screenings:
        if s["title_cz"] != title:
            continue
        if date and s["date"] != date:
            continue
        if time and s["time"] != time:
            continue
        return s
    raise AssertionError(f"no screening found for {title!r} {date or ''} {time or ''}")


# --------------------------------------------------------------------------
# Overall shape
# --------------------------------------------------------------------------

def test_finds_every_screening_in_the_fixture(screenings):
    assert len(screenings) == 517


def test_covers_a_contiguous_near_term_run_not_the_scattered_advance_dates(result):
    # The fixture's payload also carries scattered one-off advance-sale
    # dates months out (Cirque du Soleil, opera broadcasts) — only the real
    # day-by-day published run should count as "covered".
    assert result["covered_dates"][0] == "2026-08-05"
    assert result["covered_dates"][-1] == "2026-08-16"
    assert len(result["covered_dates"]) == 12
    # Consecutive, no gaps.
    from datetime import date as date_cls
    days = [date_cls.fromisoformat(d) for d in result["covered_dates"]]
    assert all((b - a).days == 1 for a, b in zip(days, days[1:]))


def test_no_empty_days_in_the_covered_range(result):
    assert result["empty_dates"] == []


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["cinema"] == "CineStar Anděl"
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_output_matches_the_sample_data_shape(screenings):
    core = {"cinema", "title_cz", "date", "time", "language", "format", "note"}
    assert core.issubset(set(screenings[0].keys()))


def test_screenings_are_sorted_by_date_then_time_then_title(screenings):
    keys = [(s["date"], s["time"], s["title_cz"]) for s in screenings]
    assert keys == sorted(keys)


# --------------------------------------------------------------------------
# Title cleanup — CineStar's own catalog bakes the variant into the title
# --------------------------------------------------------------------------

def test_version_suffix_is_stripped_from_the_title(screenings):
    s = find(screenings, "Mimoni a monstra", date="2026-08-05")
    assert s["language_version"] == "dabing"
    # The raw catalog title for this entry is "Mimoni a monstra DABING" —
    # confirm the clean title is what actually reached the screening, not
    # a coincidental separate untagged entry.
    assert "DABING" not in s["title_cz"]


def test_genuinely_all_caps_titles_are_not_mangled(screenings):
    # "Cirque du Soleil: KOOZA" and "GHOST: 2 BIG TO RIG" are real titles in
    # this catalog, not CineStar's suffix convention — a blanket
    # "strip trailing uppercase word" heuristic would wrongly eat "KOOZA".
    s = find(screenings, "Cirque du Soleil: KOOZA")
    assert s["title_cz"] == "Cirque du Soleil: KOOZA"


def test_multi_token_suffix_is_fully_stripped(screenings):
    # Raw catalog title: "Mandalorian a Grogu DABING MINI KINO".
    s = find(screenings, "Mandalorian a Grogu")
    assert s["language_version"] == "dabing"


def test_location_specific_tier_codes_are_stripped():
    # GC (Anděl's Gold Class) is covered by the fixture above; TDL (Theatre
    # Deluxe) and BC are Černý Most-only codes with no fixture of their
    # own — covered directly rather than left to a live-only check.
    assert cinestar._clean_title("Spider-Man: Zbrusu nový den DABING TDL") == "Spider-Man: Zbrusu nový den"
    assert cinestar._clean_title("Odyssea TITULKY BC") == "Odyssea"


def test_same_film_in_different_variants_collapses_to_one_clean_title(screenings):
    titles = {s["title_cz"] for s in screenings if "Odyssea" in s["title_cz"]}
    # Catalog has 4 separate variant entries (DABING / DABING GC / TITULKY /
    # TITULKY GC) for this one film; cleaned, they must all read as "Odyssea".
    assert titles == {"Odyssea"}


# --------------------------------------------------------------------------
# One screening, end to end
# --------------------------------------------------------------------------

def test_3d_dubbed_screening_parses_completely(screenings):
    s = find(screenings, "Spider-Man: Zbrusu nový den", date="2026-08-05", time="12:20")
    assert s["format"] == "3D"
    assert s["language_version"] == "dabing"
    assert s["runtime_min"] == 140
    assert s["source_id"] == "1743644"
    assert "3D" in s["tags"] and "Dabing" in s["tags"]


def test_gold_class_screening_gets_the_strand(screenings):
    s = find(screenings, "Spider-Man: Zbrusu nový den", date="2026-08-05", time="15:30")
    assert s["strand"] == "Gold Class"
    assert s["note"] == "Gold Class"


def test_original_language_screening_is_detected(screenings):
    s = find(screenings, "Cirque du Soleil: KOOZA")
    assert s["language_version"] == "originál"


def test_czech_original_film_has_no_language_version(screenings):
    # "Bardotky" is a Czech production shown as-is — neither dubbed,
    # subtitled, nor flagged "Originální znění" (that tag is for a foreign
    # film shown untouched, not a domestic one).
    s = find(screenings, "Bardotky")
    assert s["language_version"] == ""


def test_utc_screening_times_convert_to_prague_local_time(screenings):
    # Directly cross-checked against the fixture's own raw Start timestamp
    # for this EventId: "2026-08-05T08:00:00+00:00" UTC == 10:00 in Prague
    # (CEST, UTC+2, in August).
    s = next(x for x in screenings if x["source_id"] == "1743491")
    assert s["date"] == "2026-08-05"
    assert s["time"] == "10:00"


# --------------------------------------------------------------------------
# The three-line wrapper
# --------------------------------------------------------------------------

def test_andel_wrapper_calls_through_with_its_own_name_and_slug():
    result = cinestar_andel.scrape(html=HTML, catalog=CATALOG)
    assert result["cinema"] == "CineStar Anděl"
    assert result["source_url"] == "https://www.cinestar.cz/cz/praha5/program"
    assert len(result["screenings"]) == 517


# --------------------------------------------------------------------------
# The devalue deserializer, in isolation
# --------------------------------------------------------------------------

def test_devalue_unflatten_resolves_plain_values_and_references():
    # index 0 (root) -> object {"a": 1, "b": 2}; index 1 -> "hello"; index 2 -> 42
    values = [{"a": 1, "b": 2}, "hello", 42]
    assert devalue.unflatten(values) == {"a": "hello", "b": 42}


def test_devalue_unflatten_resolves_plain_arrays_of_references():
    values = [[1, 2], "x", "y"]
    assert devalue.unflatten(values) == ["x", "y"]


def test_devalue_unflatten_unwraps_reactivity_wrappers_as_identity():
    for tag in ("Ref", "Reactive", "ShallowReactive", "ShallowRef"):
        values = [[tag, 1], "wrapped value"]
        assert devalue.unflatten(values) == "wrapped value"


def test_devalue_unflatten_resolves_a_set_as_its_member_list():
    values = [["Set", 1], [2, 3], "a", "b"]
    assert devalue.unflatten(values) == ["a", "b"]


def test_devalue_unflatten_handles_a_bare_empty_set():
    # Nuxt's own "once" effect-tracking set shows up this way in a real
    # payload — no second element at all.
    values = [["Set"]]
    assert devalue.unflatten(values) == []


def test_devalue_unflatten_surfaces_an_unrecognized_tag_instead_of_crashing():
    values = [["TotallyMadeUpTag", 1], "whatever"]
    result = devalue.unflatten(values)
    assert result["__unhandled_devalue_tag__"] == "TotallyMadeUpTag"


# --------------------------------------------------------------------------
# The scheduled-events lookup doesn't depend on Nuxt's opaque cache key
# --------------------------------------------------------------------------

def test_scheduled_events_are_found_by_shape_not_by_the_cache_key_name():
    # A real payload keys this under an opaque auto-generated hash
    # ("IUEqG1BzJc" in the live site as of this fixture's capture) that
    # isn't guaranteed stable across a CineStar redeploy — confirm the
    # lookup works by field presence, using a deliberately different key.
    root = {"data": {"someOtherHashKeyEntirely": {"scheduledEventsEntries": ["ok"]}}}
    assert cinestar._find_scheduled_events(root) == ["ok"]


def test_missing_scheduled_events_raises_a_clear_error():
    with pytest.raises(ValueError, match="scheduledEventsEntries"):
        cinestar._find_scheduled_events({"data": {"x": {}}})
