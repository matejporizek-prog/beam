"""
Tests for TMDb matching and film-record building.

These never touch the network. The matching logic is the part that can quietly
go wrong — a wrong poster on the wrong film — so it's tested against fabricated
TMDb payloads shaped exactly like the real API's, using the real titles from
Kino Aero's current program.

Run with:   python -m pytest tests -v
"""

from __future__ import annotations

import pytest

from resolve import csfd
from resolve.films import (
    _age_rating,
    _cast,
    _people,
    _trailer_key,
    build_film_record,
    is_same_film,
    unique_titles,
)
from resolve.tmdb import (
    combined_score,
    comparable_names,
    director_agreement,
    match_film,
    runtime_agreement,
    score_candidate,
    strip_event_branding,
    title_similarity,
)


# --------------------------------------------------------------------------
# Title cleanup and similarity
# --------------------------------------------------------------------------

def test_strips_event_branding_from_titles():
    """A real title from Aero's program: the "| NT Live" would break any match."""
    assert strip_event_branding("Nebezpečné známosti | NT Live") == "Nebezpečné známosti"
    assert strip_event_branding("EOS: Frida Kahlo") == "EOS: Frida Kahlo"  # colon is part of it
    assert strip_event_branding("Odyssea") == "Odyssea"


def test_stripping_never_returns_an_empty_title():
    """A title that is *only* branding must stay intact rather than vanish."""
    assert strip_event_branding("| NT Live") == "| NT Live"


def test_the_known_typo_still_matches():
    """
    The reason fuzzy matching exists at all: the sample data contains both
    "Odyssea" and "Oddysea" for the same film.
    """
    assert title_similarity("Odyssea", "Oddysea") > 0.85
    assert title_similarity("Odyssea", "Odyssea") == 1.0


def test_diacritics_and_case_are_ignored():
    assert title_similarity("PŘÍSAHÁM, ŽE ZA TO NEMŮŽU", "Přísahám že za to nemůžu") == 1.0


def test_genuinely_different_titles_score_low():
    assert title_similarity("Odyssea", "Mimoni a monstra") < 0.4
    assert title_similarity("Pramen", "Mouchy") < 0.5


def test_score_candidate_checks_both_localised_and_original_titles():
    candidate = {"title": "Odyssea", "original_title": "The Odyssey"}
    assert score_candidate("Odyssea", candidate) == 1.0
    # The English original must also be findable.
    assert score_candidate("The Odyssey", candidate) == 1.0


# --------------------------------------------------------------------------
# Verification signals
# --------------------------------------------------------------------------

def test_runtime_agreement_tolerates_normal_drift():
    assert runtime_agreement(172, 172) == 1.0
    assert runtime_agreement(172, 174) == 1.0   # cinemas round
    assert runtime_agreement(172, 180) == 0.3   # adverts, plausible
    assert runtime_agreement(172, 95) == -1.0   # not the same film
    assert runtime_agreement(None, 172) == 0.0  # no evidence either way


def test_director_agreement():
    credits = {"crew": [{"job": "Director", "name": "Christopher Nolan"}]}
    assert director_agreement("Christopher Nolan", credits) == 1.0
    assert director_agreement("Wong Kar-wai", credits) == -1.0
    assert director_agreement("", credits) == 0.0
    assert director_agreement("Christopher Nolan", {}) == 0.0


def test_director_agreement_survives_transliterated_names():
    """
    Aero writes Japanese names Czech-style ("Hirojuki Morita"); TMDb uses the
    English romanisation. These must not read as a contradiction.
    """
    credits = {"crew": [{"job": "Director", "name": "Hiroyuki Morita"}]}
    assert director_agreement("Hirojuki Morita", credits) >= 0.0


def test_director_names_in_another_script_are_not_a_contradiction():
    """
    Found on the first real run. TMDb returns Wong Kar-wai as 王家衛 and Antonio
    Lukič as Антоніо Лукіч. Comparing across scripts scores ~0, which read as
    "definitely a different director" and penalised four correct matches.
    """
    assert director_agreement("Wong Kar-wai", {"crew": [
        {"job": "Director", "name": "王家衛"}]}) == 0.0
    assert director_agreement("Antonio Lukič", {"crew": [
        {"job": "Director", "name": "Антоніо Лукіч"}]}) == 0.0
    # Same-script contradictions must still be caught.
    assert director_agreement("Fernando Eimbcke", {"crew": [
        {"job": "Director", "name": "Jaroslav Možíš"}]}) == -1.0


def test_co_directors_listed_by_the_cinema_still_match():
    """
    Aero writes "Maïlys Vallade, Liane-Cho Han"; TMDb lists them separately.
    A substring match must rescue this from looking like a mismatch.
    """
    credits = {"crew": [{"job": "Director", "name": "Maïlys Vallade"}]}
    assert director_agreement("Maïlys Vallade, Liane-Cho Han", credits) == 1.0


def test_title_dominates_the_combined_score():
    """
    A matching director must never rescue a badly-wrong title, and a mismatched
    director must not sink an exact one below the accept threshold.
    """
    strong_title_bad_director = combined_score(1.0, -1.0, 0.0)
    weak_title_good_director = combined_score(0.5, 1.0, 1.0)
    assert strong_title_bad_director > weak_title_good_director
    assert weak_title_good_director < 0.75  # still rejected


# --------------------------------------------------------------------------
# The matcher end to end, against a stub TMDb
# --------------------------------------------------------------------------

class FakeClient:
    """Stands in for TMDbClient so matching can be tested without the network."""

    def __init__(self, results, details):
        self._results = results
        self._details = details
        self.detail_calls = 0

    def search_movie(self, query, language=None):
        return self._results

    def movie_details(self, tmdb_id, language=None):
        self.detail_calls += 1
        return self._details[tmdb_id]


def test_exact_title_alone_is_not_enough_to_accept():
    """
    The "Mouchy" failure from the first real run. TMDb has a 4-minute Czech
    short from 1951 titled exactly "Mouchy"; Aero is screening a 99-minute
    Mexican feature by Fernando Eimbcke. The title matches perfectly, so the
    old shortcut accepted it without ever checking the runtime.
    """
    client = FakeClient(
        results=[{"id": 1, "title": "Mouchy", "original_title": "Mouchy", "popularity": 1.0}],
        details={1: {
            "runtime": 4,
            "credits": {"crew": [{"job": "Director", "name": "Jaroslav Možíš"}]},
        }},
    )
    result = match_film(client, "Mouchy", director="Fernando Eimbcke", runtime_min=99)

    assert not result.resolved
    assert client.detail_calls == 1, "an exact title must still be verified"


def test_both_checks_contradicting_is_decisive():
    """
    The "Nebezpečné známosti | NT Live" failure. The title matches Dangerous
    Liaisons exactly, but Aero's screening is Marianne Elliott's 180-minute
    theatre broadcast, not Stephen Frears' 115-minute film. Under the old
    weights this still scored 0.85 and was accepted.
    """
    client = FakeClient(
        results=[{"id": 859, "title": "Nebezpečné známosti",
                  "original_title": "Dangerous Liaisons", "popularity": 20.0}],
        details={859: {
            "runtime": 115,
            "credits": {"crew": [{"job": "Director", "name": "Stephen Frears"}]},
        }},
    )
    result = match_film(client, "Nebezpečné známosti | NT Live",
                        director="Marianne Elliott", runtime_min=180)

    assert not result.resolved
    assert "contradict" in result.reason


def test_a_lone_runtime_contradiction_also_vetoes():
    """
    The second NT Live failure. After rejecting the 1988 film, the matcher fell
    through to the 2012 Chinese remake — whose director is Korean-scripted, so
    that check abstains and only the runtime objected (180 vs 110). A gap that
    large is proof of a different work on its own.
    """
    client = FakeClient(
        results=[{"id": 4, "title": "Nebezpečné známosti",
                  "original_title": "Dangerous Liaisons", "popularity": 8.0}],
        details={4: {
            "runtime": 110,
            "credits": {"crew": [{"job": "Director", "name": "허진호"}]},
        }},
    )
    result = match_film(client, "Nebezpečné známosti | NT Live",
                        director="Marianne Elliott", runtime_min=180)
    assert not result.resolved
    assert "runtime" in result.reason


def test_a_confirmed_director_can_overrule_a_runtime_gap():
    """
    Vetoes must not be absolute. Restorations and director's cuts genuinely run
    long, so an explicitly confirmed director outweighs a runtime disagreement.
    """
    client = FakeClient(
        results=[{"id": 5, "title": "Modrý samet", "original_title": "Blue Velvet", "popularity": 9.0}],
        details={5: {
            "runtime": 120,
            "credits": {"crew": [{"job": "Director", "name": "David Lynch"}]},
        }},
    )
    result = match_film(client, "Modrý samet", director="David Lynch", runtime_min=155)
    assert result.resolved


def test_a_good_match_is_still_accepted():
    """The fixes must not make the matcher refuse correct matches."""
    client = FakeClient(
        results=[{"id": 2, "title": "Odyssea", "original_title": "The Odyssey", "popularity": 50.0}],
        details={2: {
            "runtime": 172,
            "credits": {"crew": [{"job": "Director", "name": "Christopher Nolan"}]},
        }},
    )
    result = match_film(client, "Odyssea", director="Christopher Nolan", runtime_min=172)

    assert result.resolved
    assert result.tmdb_id == 2


def test_a_correct_match_survives_a_foreign_script_director():
    """Padlí andělé: TMDb says 王家衛, Aero says Wong Kar-Wai. Must still resolve."""
    client = FakeClient(
        results=[{"id": 3, "title": "Padlí andělé", "original_title": "墮落天使", "popularity": 10.0}],
        details={3: {
            "runtime": 97,
            "credits": {"crew": [{"job": "Director", "name": "王家衛"}]},
        }},
    )
    result = match_film(client, "Padlí andělé", director="Wong Kar-Wai", runtime_min=99)
    assert result.resolved


def test_unresolved_when_tmdb_knows_nothing():
    client = FakeClient(results=[], details={})
    result = match_film(client, "Film Který Neexistuje")
    assert not result.resolved
    assert "no results" in result.reason


# --------------------------------------------------------------------------
# Pulling fields out of TMDb responses
# --------------------------------------------------------------------------

def test_prefers_an_official_czech_trailer():
    details = {"videos": {"results": [
        {"site": "YouTube", "key": "teaser1", "type": "Teaser", "iso_639_1": "cs", "official": True},
        {"site": "YouTube", "key": "en_tr", "type": "Trailer", "iso_639_1": "en", "official": True},
        {"site": "YouTube", "key": "cs_tr", "type": "Trailer", "iso_639_1": "cs", "official": True},
    ]}}
    assert _trailer_key(details) == "cs_tr"


def test_falls_back_to_an_english_trailer():
    details = {"videos": {"results": [
        {"site": "YouTube", "key": "en_tr", "type": "Trailer", "iso_639_1": "en", "official": True},
    ]}}
    assert _trailer_key(details) == "en_tr"


def test_ignores_non_youtube_videos():
    """The app plays trailers inline in a YouTube embed; a Vimeo key would break it."""
    details = {"videos": {"results": [
        {"site": "Vimeo", "key": "vimeo1", "type": "Trailer", "iso_639_1": "cs"},
    ]}}
    assert _trailer_key(details) == ""


def test_no_trailer_is_an_empty_string_not_a_crash():
    assert _trailer_key({}) == ""
    assert _trailer_key({"videos": {"results": []}}) == ""


def test_prefers_the_czech_age_rating():
    details = {"release_dates": {"results": [
        {"iso_3166_1": "US", "release_dates": [{"certification": "R"}]},
        {"iso_3166_1": "CZ", "release_dates": [{"certification": "15"}]},
    ]}}
    assert _age_rating(details) == "15"


def test_marks_a_us_rating_as_a_fallback():
    """A US rating is a hint, not a Czech certification, and must say so."""
    details = {"release_dates": {"results": [
        {"iso_3166_1": "US", "release_dates": [{"certification": "PG-13"}]},
    ]}}
    assert _age_rating(details) == "PG-13 (US)"


def test_age_rating_skips_blank_certifications():
    details = {"release_dates": {"results": [
        {"iso_3166_1": "CZ", "release_dates": [{"certification": ""}, {"certification": "12"}]},
    ]}}
    assert _age_rating(details) == "12"


def test_people_extraction_deduplicates_and_keeps_order():
    credits = {"crew": [
        {"job": "Director", "name": "Wong Kar-wai"},
        {"job": "Screenplay", "name": "Wong Kar-wai"},
        {"job": "Writer", "name": "Jeff Lau"},
        {"job": "Editor", "name": "Someone Else"},
    ]}
    assert _people(credits, "Director") == ["Wong Kar-wai"]
    assert _people(credits, "Screenplay", "Writer") == ["Wong Kar-wai", "Jeff Lau"]


def test_cast_is_capped_for_the_detail_page():
    credits = {"cast": [{"name": f"Actor {i}"} for i in range(20)]}
    assert len(_cast(credits)) == 8


# --------------------------------------------------------------------------
# The assembled film record
# --------------------------------------------------------------------------

@pytest.fixture
def odyssea_cs():
    return {
        "original_title": "The Odyssey",
        "overview": "Odysseus se vrací domů.",
        "runtime": 172,
        "release_date": "2026-07-17",
        "genres": [{"name": "Dobrodružný"}, {"name": "Drama"}],
        "poster_path": "/poster.jpg",
        "backdrop_path": "/backdrop.jpg",
        "production_companies": [{"name": "Universal Pictures"}],
        "videos": {"results": [
            {"site": "YouTube", "key": "abc123", "type": "Trailer", "iso_639_1": "en", "official": True}
        ]},
        "release_dates": {"results": [
            {"iso_3166_1": "CZ", "release_dates": [{"certification": "12"}]}
        ]},
    }


@pytest.fixture
def odyssea_en():
    """Credits live on the English response — that is where Latin-script names are."""
    return {
        "title": "The Odyssey",
        "overview": "Odysseus journeys home.",
        "release_date": "2026-07-17",
        "credits": {
            "crew": [
                {"job": "Director", "name": "Christopher Nolan"},
                {"job": "Screenplay", "name": "Christopher Nolan"},
            ],
            "cast": [{"name": "Matt Damon"}, {"name": "Anne Hathaway"}, {"name": "Tom Holland"}],
        },
    }


def test_credits_come_from_the_english_response(odyssea_cs, odyssea_en):
    """
    Found while testing search: TMDb localises crew names, so a Czech request
    returns 王家衛 instead of "Wong Kar-Wai". That is wrong in the UI and makes
    the film unfindable for anyone typing the director's name.
    """
    odyssea_cs["credits"] = {"crew": [{"job": "Director", "name": "克里斯多福·諾蘭"}], "cast": []}
    record = build_film_record("Odyssea", odyssea_cs, odyssea_en, 1, "x", 1.0)
    assert record["director"] == ["Christopher Nolan"]
    assert "Matt Damon" in record["cast"]


def test_build_film_record(odyssea_cs, odyssea_en):
    record = build_film_record("Odyssea", odyssea_cs, odyssea_en, 12345, "title match", 0.98)

    assert record["film_id"] == "odyssea"
    assert record["title_cz"] == "Odyssea"
    assert record["title_en"] == "The Odyssey"
    assert record["original_title"] == "The Odyssey"
    assert record["year"] == 2026
    assert record["runtime_min"] == 172
    assert record["genres"] == ["Dobrodružný", "Drama"]
    assert record["director"] == ["Christopher Nolan"]
    assert record["cast"] == ["Matt Damon", "Anne Hathaway", "Tom Holland"]
    assert record["poster_path"] == "/poster.jpg"
    assert record["trailer_youtube_key"] == "abc123"
    assert record["age_rating"] == "12"
    assert record["tmdb_id"] == 12345
    assert record["resolved"] is True


def test_czech_synopsis_wins_when_available(odyssea_cs, odyssea_en):
    record = build_film_record("Odyssea", odyssea_cs, odyssea_en, 12345, "x", 1.0)
    assert record["synopsis"] == "Odysseus se vrací domů."
    assert record["synopsis_language"] == "cs"


def test_falls_back_to_the_english_synopsis(odyssea_cs, odyssea_en):
    """
    Arthouse titles frequently have no Czech text on TMDb. English beats an
    empty box, but the app needs to know which language it got.
    """
    odyssea_cs["overview"] = ""
    record = build_film_record("Odyssea", odyssea_cs, odyssea_en, 12345, "x", 1.0)
    assert record["synopsis"] == "Odysseus journeys home."
    assert record["synopsis_language"] == "en"


def test_record_always_carries_a_csfd_link(odyssea_cs, odyssea_en):
    record = build_film_record("Odyssea", odyssea_cs, odyssea_en, 12345, "x", 1.0)
    assert record["csfd_url"].startswith("https://www.csfd.cz/hledat/?q=")
    assert "2026" in record["csfd_url"]


# --------------------------------------------------------------------------
# Collapsing screenings into films
# --------------------------------------------------------------------------

def test_typo_variants_collapse_into_one_film():
    """
    The payoff for normalising: "Odyssea" and "Oddysea" must become a single
    film costing a single TMDb lookup, not two.
    """
    screenings = [
        {"title_cz": "Odyssea", "director": "Christopher Nolan", "runtime_min": 172},
        {"title_cz": "Oddysea", "director": "Christopher Nolan", "runtime_min": 172},
    ]
    films = unique_titles(screenings)
    assert len(films) == 1


def test_sequels_are_never_merged():
    """
    The trap fuzzy grouping walks into: "toy story 4" and "toy story 5" score
    about 0.91 similarity — above the threshold that catches real typos. Merging
    them would put one film's poster and synopsis on the other.
    """
    assert not is_same_film("toy story 4", "toy story 5")
    assert not is_same_film("john wick 3", "john wick 4")

    screenings = [
        {"title_cz": "Toy Story 4", "director": "", "runtime_min": None},
        {"title_cz": "Toy Story 5: Příběh hraček", "director": "", "runtime_min": None},
    ]
    assert len(unique_titles(screenings)) == 2


def test_typos_are_merged():
    assert is_same_film("odyssea", "oddysea")


def test_short_similar_titles_are_not_merged():
    """Different films with similar names must stay apart."""
    assert not is_same_film("pramen", "prameny sveta")
    assert not is_same_film("mouchy", "duchy")


def test_the_most_common_spelling_becomes_canonical():
    """
    A typo is nearly always the rarer variant, so the majority spelling is what
    we show and what we search TMDb with.
    """
    screenings = (
        [{"title_cz": "Odyssea", "director": "", "runtime_min": None}] * 3
        + [{"title_cz": "Oddysea", "director": "", "runtime_min": None}]
    )
    films = unique_titles(screenings)
    assert len(films) == 1
    assert list(films.values())[0]["title_cz"] == "Odyssea"


def test_event_branding_collapses_too():
    screenings = [
        {"title_cz": "Nebezpečné známosti | NT Live", "director": "", "runtime_min": None},
        {"title_cz": "Nebezpečné známosti", "director": "", "runtime_min": None},
    ]
    assert len(unique_titles(screenings)) == 1


def test_hints_are_filled_in_from_later_screenings():
    """The first screening of a film may lack a runtime; a later one can supply it."""
    screenings = [
        {"title_cz": "Pramen", "director": "", "runtime_min": None},
        {"title_cz": "Pramen", "director": "Jan Novák", "runtime_min": 101},
    ]
    films = unique_titles(screenings)
    assert films["pramen"]["runtime_min"] == 101


def test_titles_that_are_only_punctuation_are_ignored():
    assert unique_titles([{"title_cz": "  "}, {"title_cz": "!!!"}]) == {}


# --------------------------------------------------------------------------
# ČSFD links
# --------------------------------------------------------------------------

def test_csfd_search_url_is_properly_encoded():
    url = csfd.search_url("Přísahám, že za to nemůžu", 2026)
    assert url.startswith("https://www.csfd.cz/hledat/?q=")
    assert " " not in url          # spaces must be encoded
    assert "Přísahám" not in url   # accents must be encoded too


def test_csfd_url_includes_the_year_when_known():
    assert "2026" in csfd.search_url("Odyssea", 2026)
    assert "2026" not in csfd.search_url("Odyssea")


def test_csfd_url_is_empty_for_an_empty_title():
    assert csfd.search_url("") == ""
