"""
Tests for the Kino Pilotů scraper.

A different platform from the Aerofilms cinemas (see aerofilms.py) — no
JSON-LD, no `program__` markup. The whole ~3-week program is a Swiper.js
carousel of paired "day" and "event" slides, entirely pre-rendered in one page
load. See kino_pilotu.py's module docstring for the full story, including two
real things this cinema's site surfaced: a genuine encoding bug in
`base.fetch()`, and title text with the programming strand baked into it
("Céčko: Leviticus") rather than exposed as a separate tag.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scrapers import kino_pilotu
from scrapers.kino_pilotu import _dates_from_slides, _split_title

FIXTURE = Path(__file__).parent / "fixtures" / "kino-pilotu-program-2026-07-24.html"


@pytest.fixture(scope="module")
def result():
    return kino_pilotu.scrape(html=FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def screenings(result):
    return result["screenings"]


def find(screenings, title):
    return [s for s in screenings if s["title_cz"] == title]


# --------------------------------------------------------------------------
# Overall shape
# --------------------------------------------------------------------------

def test_finds_screenings(screenings):
    assert len(screenings) == 183


def test_every_screening_is_tagged_with_this_cinema(screenings):
    assert all(s["cinema"] == "Kino Pilotů" for s in screenings)


def test_every_screening_has_the_core_fields(screenings):
    for s in screenings:
        assert s["title_cz"], "title must never be empty"
        assert len(s["date"]) == 10 and s["date"].count("-") == 2
        assert len(s["time"]) == 5 and s["time"][2] == ":"


def test_screenings_are_sorted_by_date_then_time(screenings):
    keys = [(s["date"], s["time"]) for s in screenings]
    assert keys == sorted(keys)


def test_shares_films_with_the_aerofilms_cinemas(screenings):
    """Sanity check this is genuinely the same distribution window."""
    titles = {s["title_cz"] for s in screenings}
    assert "Odyssea" in titles
    assert "Pozvání" in titles


# --------------------------------------------------------------------------
# The genuinely new problem: date inference with no year, and gaps
# --------------------------------------------------------------------------

def test_covers_a_three_week_window(result):
    assert result["covered_dates"][0] == "2026-07-24"
    assert result["covered_dates"][-1] == "2026-08-12"
    assert len(result["covered_dates"]) == 16


def test_days_the_site_skips_entirely_are_reported_as_empty(result):
    """
    The site's own day list jumps straight from 5. srpna to 10. srpna — those
    four missing days must still show up as "nothing on" rather than vanishing,
    the same signal a closed cinema like Ponrepo produces.
    """
    assert result["empty_dates"] == [
        "2026-08-06", "2026-08-07", "2026-08-08", "2026-08-09",
    ]


def test_year_rolls_forward_across_a_december_boundary():
    """
    No year is ever printed on this site ("24. července"), so it has to be
    inferred from month order. A genuinely different kind of date problem than
    the Aerofilms cinemas, which always carry a full date in their day-anchor
    id — this site has nothing but a day number and a Czech month name.
    """
    class FakeSlide:
        def __init__(self, text):
            self._text = text
        def get_text(self, *_args, **_kwargs):
            return self._text

    slides = [FakeSlide(t) for t in ("Úterý 29. prosince", "Středa 30. prosince", "Čtvrtek 1. ledna")]
    dates = _dates_from_slides(slides)
    assert dates[0].endswith("-12-29")
    assert dates[1].endswith("-12-30")
    year_before = int(dates[0].split("-")[0])
    year_after = int(dates[2].split("-")[0])
    assert year_after == year_before + 1
    assert dates[2].endswith("-01-01")


def test_date_inference_does_not_leak_between_scrape_calls():
    """
    The year-rollover logic used to live in module-level mutable state, which
    would corrupt results the second time scrape() ran in the same process —
    exactly how this scraper is actually invoked (run.py calls every cinema in
    one process; so does a single pytest session). Calling scrape() twice here
    must produce identical results both times.
    """
    html = FIXTURE.read_text(encoding="utf-8")
    first = kino_pilotu.scrape(html=html)
    second = kino_pilotu.scrape(html=html)
    assert first["covered_dates"] == second["covered_dates"]
    assert [s["date"] for s in first["screenings"]] == [s["date"] for s in second["screenings"]]


# --------------------------------------------------------------------------
# The other genuinely new problem: strand baked into the title text
# --------------------------------------------------------------------------

def test_strand_prefix_is_split_off_the_title(screenings):
    """
    This cinema writes "Céčko: Leviticus" as one title string, unlike the
    Aerofilms cinemas which expose the strand as a separate chip. Left in the
    title, TMDb matching for "Céčko: Leviticus" would score far worse against
    "Leviticus" than the clean title does.
    """
    assert find(screenings, "Céčko: Leviticus") == []
    matches = find(screenings, "Leviticus")
    assert matches
    assert "Céčko" in matches[0]["strand"]


def test_anniversary_strand_prefix_is_recognised(screenings):
    assert find(screenings, "10 Let Kina Pilotů: Aftersun") == []
    matches = find(screenings, "Aftersun")
    assert matches
    assert "10 Let Kina Pilotů" in matches[0]["strand"]


def test_kino_senioru_strand_maps_the_same_way_as_bio_senior_elsewhere(screenings):
    matches = find(screenings, "Michael")
    senior_screening = next(s for s in matches if "Kino Seniorů" in s["strand"])
    assert senior_screening is not None


def test_colon_in_a_real_title_is_never_touched(screenings):
    """
    The exact same character (":") that separates a strand prefix is also
    part of several real titles here. Splitting on any colon would wrongly
    truncate these; only the small set of known strand labels may trigger it.
    """
    real_titles_with_colons = [
        "Zootropolis: Město zvířat 2",
        "Toy Story 5: Příběh hraček",
        "Spider-Man: Zbrusu nový den",
    ]
    for title in real_titles_with_colons:
        assert find(screenings, title), f"{title!r} should be untouched"


def test_a_real_dash_in_a_title_survives_suffix_stripping(screenings):
    """
    "Dalajláma - Oceán moudrosti" has a legitimate dash as part of its own
    title, and separately appears with a " + DEBATA S REŽISÉREM" suffix on some
    screenings. The suffix split must not eat the title's own dash.
    """
    matches = find(screenings, "Dalajláma - Oceán moudrosti")
    assert matches
    assert find(screenings, "Dalajláma - Oceán moudrosti + DEBATA S REŽISÉREM") == []


def test_czech_dubbing_suffix_becomes_a_real_language_version(screenings):
    """
    "Šepot lesa / Český dabing" isn't just inert strand text — classify_tags()
    already recognises "Český dabing" as a dabing signal via VERSION_TAGS, so
    running the split fragment through the same pipeline the Aerofilms cinemas
    use gets a real language_version for free, with no special-casing here.
    """
    matches = find(screenings, "Šepot lesa")
    assert matches
    assert all(s["language_version"] == "dabing" for s in matches)


def test_event_annotation_suffixes_land_in_strand_not_lost(screenings):
    matches = find(screenings, "Chica Checa")
    assert matches
    assert "debata" in matches[0]["strand"].lower()


# --------------------------------------------------------------------------
# _split_title unit tests
# --------------------------------------------------------------------------

def test_split_title_strand_prefix():
    title, tags = _split_title("Céčko: Leviticus")
    assert title == "Leviticus"
    assert tags == ["Céčko"]


def test_split_title_suffix():
    title, tags = _split_title("Šepot lesa / Český dabing")
    assert title == "Šepot lesa"
    assert tags == ["Český dabing"]


def test_split_title_both_prefix_and_suffix():
    title, tags = _split_title("Céčko: Slepice / Omezená kapacita")
    assert title == "Slepice"
    assert tags == ["Céčko", "Omezená kapacita"]


def test_split_title_unrecognised_prefix_is_left_alone():
    """A colon that isn't one of the known strand labels must not be touched."""
    title, tags = _split_title("Blade Runner: 2049")
    assert title == "Blade Runner: 2049"
    assert tags == []


def test_split_title_plain_title_is_unchanged():
    title, tags = _split_title("Odyssea")
    assert title == "Odyssea"
    assert tags == []
