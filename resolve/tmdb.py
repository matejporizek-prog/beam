"""
TMDb client and title matching.

The problem this solves
-----------------------
Cinemas advertise films under their Czech distribution title. TMDb knows films
under many titles. Matching the two is the whole job, and it cannot be an exact
string comparison — the sample data alone contains "Odyssea" and "Oddysea" for
the same film. Titles also carry punctuation, subtitles and event prefixes
("Nebezpečné známosti | NT Live") that no exact match survives.

So we score candidates instead, and — crucially — we verify them. The scraper
already gives us the director and runtime for each screening, straight from the
cinema's own page. Those are excellent independent checks: two different films
can share a title, but a title *and* a director *and* a runtime agreeing is
about as certain as this gets without a human looking.

Anything we can't resolve confidently is flagged, never guessed at. A wrong
poster on the wrong film is far worse than a missing one.
"""

from __future__ import annotations

import os
import time
import unicodedata
from difflib import SequenceMatcher
from typing import Optional

import requests

from scrapers.base import normalize_title

API_BASE = "https://api.themoviedb.org/3"

# Czech first — we're matching Czech distribution titles and want Czech synopses.
CZECH = "cs-CZ"
ENGLISH = "en-US"

# --- how sure we need to be -------------------------------------------------
# Above ACCEPT_SCORE we take the match. Below REJECT_SCORE we give up and flag
# the title for a manual override. In between we spend extra API calls checking
# the director and runtime before deciding.
ACCEPT_SCORE = 0.90
REJECT_SCORE = 0.75
# How far ahead the best candidate must be to win without verification.
CLEAR_LEAD = 0.08
# How many candidates are worth verifying when the top match is ambiguous.
VERIFY_TOP_N = 3

# TMDb allows roughly 40 requests/second. We're nowhere near that, but a small
# pause keeps us obviously well-behaved.
REQUEST_PAUSE = 0.15


class TMDbError(RuntimeError):
    pass


class MissingAPIKey(TMDbError):
    """Raised with instructions rather than a stack trace, since Matěj hits this first."""

    def __init__(self):
        super().__init__(
            "No TMDb credentials found.\n\n"
            "Set one of these environment variables, or put it in a .env file "
            "in the project folder:\n"
            "    TMDB_API_KEY=<your v3 API key>\n"
            "    TMDB_READ_TOKEN=<your v4 read access token>\n\n"
            "Get either from https://www.themoviedb.org/settings/api\n"
            "The .env file is already in .gitignore, so it won't be committed."
        )


def load_dotenv(path: str = ".env") -> None:
    """
    Read a simple KEY=value file into the environment.

    Deliberately tiny rather than a dependency — we need exactly this and
    nothing more, and it keeps the API key out of the codebase.
    """
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class TMDbClient:
    """Thin wrapper over the TMDb REST API, with both auth styles supported."""

    def __init__(self, api_key: str | None = None, read_token: str | None = None):
        load_dotenv()
        self.api_key = api_key or os.environ.get("TMDB_API_KEY", "")
        self.read_token = read_token or os.environ.get("TMDB_READ_TOKEN", "")
        if not self.api_key and not self.read_token:
            raise MissingAPIKey()

        self.session = requests.Session()
        if self.read_token:
            # v4 tokens go in the header; v3 keys go in the query string.
            self.session.headers["Authorization"] = f"Bearer {self.read_token}"
        self.session.headers["accept"] = "application/json"
        self.call_count = 0

    def get(self, path: str, **params) -> dict:
        if self.api_key and not self.read_token:
            params["api_key"] = self.api_key

        response = self.session.get(f"{API_BASE}{path}", params=params, timeout=30)
        self.call_count += 1
        time.sleep(REQUEST_PAUSE)

        if response.status_code == 401:
            raise TMDbError(
                "TMDb rejected the credentials (401). Check the key is correct "
                "and fully activated at https://www.themoviedb.org/settings/api"
            )
        response.raise_for_status()
        return response.json()

    # -- endpoints we actually use ------------------------------------------

    def search_movie(self, query: str, language: str = CZECH) -> list[dict]:
        data = self.get("/search/movie", query=query, language=language, include_adult=False)
        return data.get("results", [])

    def movie_details(self, tmdb_id: int, language: str = CZECH) -> dict:
        return self.get(
            f"/movie/{tmdb_id}",
            language=language,
            append_to_response="credits,videos,release_dates",
            # Trailers are rarely uploaded with a Czech language tag; accept
            # Czech, English and untagged videos so we don't miss them.
            include_video_language="cs,en,null",
        )


# --------------------------------------------------------------------------
# Title scoring
# --------------------------------------------------------------------------

# Cinemas bolt event branding onto titles. Strip it before comparing, or
# "Nebezpečné známosti | NT Live" never matches "Nebezpečné známosti".
# Only "|" — the one separator actually observed in real event branding
# ("Nebezpečné známosti | NT Live", "Audience | NT Live"). Dashes used to be
# in this list too, and it was a real bug: a plain hyphen or em/en dash is a
# common title/subtitle separator in perfectly ordinary film titles, not a
# marker for bolted-on event branding. It silently truncated "Dalajláma -
# Oceán moudrosti" down to just "Dalajláma", throwing the real second half of
# the title away before the search ever ran. "|" essentially never appears in
# an official title, which is what makes it safe to split on unconditionally.
EVENT_SUFFIX_SEPARATORS = ("|",)


def strip_event_branding(title: str) -> str:
    """'Nebezpečné známosti | NT Live' -> 'Nebezpečné známosti'."""
    cleaned = title
    for separator in EVENT_SUFFIX_SEPARATORS:
        if separator in cleaned:
            cleaned = cleaned.split(separator)[0]
    return cleaned.strip() or title.strip()


def title_similarity(a: str, b: str) -> float:
    """0.0-1.0 similarity between two titles, ignoring case, accents and punctuation."""
    left, right = normalize_title(a), normalize_title(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def score_candidate(query: str, candidate: dict) -> float:
    """
    Best similarity between the cinema's title and any title TMDb knows for
    this film — the localised one or the original.
    """
    known_titles = [
        candidate.get("title", ""),
        candidate.get("original_title", ""),
    ]
    return max((title_similarity(query, t) for t in known_titles if t), default=0.0)


def runtime_agreement(scraped: Optional[int], tmdb_runtime: Optional[int]) -> float:
    """
    How well two runtimes agree, as a -1.0..+1.0 nudge.

    Cinemas round and sometimes include adverts, so a few minutes' drift is
    normal and only a large gap is evidence of a wrong match.
    """
    if not scraped or not tmdb_runtime:
        return 0.0
    difference = abs(scraped - tmdb_runtime)
    if difference <= 3:
        return 1.0
    if difference <= 10:
        return 0.3
    if difference >= 30:
        return -1.0
    return 0.0


def _has_latin_letters(text: str) -> bool:
    """True if the text contains Latin letters once accents are stripped."""
    decomposed = unicodedata.normalize("NFKD", text)
    return any("a" <= char.lower() <= "z" for char in decomposed)


def comparable_names(a: str, b: str) -> bool:
    """
    Whether two names are written in scripts we can meaningfully compare.

    TMDb returns a director's name in whatever script its record uses — Wong
    Kar-wai comes back as 王家衛, Antonio Lukič as Антоніо Лукіч. Those are the
    same people the cinema listed, but character-by-character similarity reads
    them as total contradictions. Comparing across scripts produces confident
    nonsense, so we decline to compare at all and let the other evidence decide.
    """
    return _has_latin_letters(a) == _has_latin_letters(b)


def director_agreement(scraped: str, credits: dict) -> float:
    """
    +1.0 if the cinema's director matches TMDb's, -1.0 if they clearly differ,
    0.0 when we have no comparable evidence either way.
    """
    if not scraped or not credits:
        return 0.0
    directors = [
        member.get("name", "")
        for member in credits.get("crew", [])
        if member.get("job") == "Director" and member.get("name")
    ]
    # Only compare names written in the same script as the cinema's.
    directors = [name for name in directors if comparable_names(scraped, name)]
    if not directors:
        return 0.0

    # Films often have co-directors and cinemas list only one, or list several
    # in one string. Any one of them matching is a match.
    best = max(title_similarity(scraped, name) for name in directors)
    if best >= 0.85:
        return 1.0
    # A cinema may write "Maïlys Vallade, Liane-Cho Han" where TMDb has just
    # one of them — check for a name appearing inside the other string too.
    if any(
        normalize_title(name) in normalize_title(scraped)
        or normalize_title(scraped) in normalize_title(name)
        for name in directors
    ):
        return 1.0
    if best <= 0.4:
        return -1.0
    return 0.0


def combined_score(title_score: float, director: float, runtime: float) -> float:
    """
    Fold the evidence into one number.

    Title stays dominant; director and runtime can only nudge it. That ordering
    matters — a matching director on a wrong-titled film is a coincidence, but a
    mismatched director on a right-looking title is a real warning.
    """
    return title_score + (director * 0.10) + (runtime * 0.05)


# --------------------------------------------------------------------------
# The matcher
# --------------------------------------------------------------------------

class MatchResult:
    def __init__(self, tmdb_id: int | None, score: float, reason: str, details: dict | None = None):
        self.tmdb_id = tmdb_id
        self.score = score
        self.reason = reason      # human-readable, ends up in films.json
        self.details = details    # full movie details when we already fetched them

    @property
    def resolved(self) -> bool:
        return self.tmdb_id is not None


def match_film(
    client: TMDbClient,
    title_cz: str,
    director: str = "",
    runtime_min: Optional[int] = None,
) -> MatchResult:
    """
    Find the TMDb film behind a Czech cinema title.

    Searches Czech first, falls back to a plain search, then verifies ambiguous
    candidates against the director and runtime the scraper collected.
    """
    query = strip_event_branding(title_cz)

    candidates = client.search_movie(query, language=CZECH)
    if not candidates:
        candidates = client.search_movie(query, language=ENGLISH)
    if not candidates:
        return MatchResult(None, 0.0, f"TMDb returned no results for {query!r}")

    scored = sorted(
        ((score_candidate(query, c), c) for c in candidates),
        key=lambda pair: (pair[0], pair[1].get("popularity", 0)),
        reverse=True,
    )

    best_score, best = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else 0.0

    have_evidence = bool(director) or bool(runtime_min)

    # Only skip verification when there is nothing to verify against. An exact
    # title match is NOT sufficient on its own: "Mouchy" matches a 4-minute
    # Czech short from 1951 perfectly, while the film actually screening is a
    # 99-minute Mexican feature. Whenever the scraper gave us a director or a
    # runtime, spending one more call to check them is always worth it — the
    # result is cached forever, and a wrong film is permanent.
    if not have_evidence and best_score >= ACCEPT_SCORE and (best_score - runner_up_score) >= CLEAR_LEAD:
        return MatchResult(best["id"], best_score, f"title match, unverified ({best_score:.2f})")

    verified = []
    for score, candidate in scored[:VERIFY_TOP_N]:
        if score < REJECT_SCORE - 0.15:
            continue  # hopeless, not worth a request
        # English, deliberately: TMDb localises crew names, returning 王家衛 for
        # a Czech request and "Wong Kar-Wai" for an English one. Verifying
        # against the Latin form is what makes the director check work at all
        # for non-Western cinema — which, for an arthouse app, is a lot of it.
        details = client.movie_details(candidate["id"], language=ENGLISH)
        director_score = director_agreement(director, details.get("credits", {}))
        runtime_score = runtime_agreement(runtime_min, details.get("runtime"))
        total = combined_score(score, director_score, runtime_score)
        verified.append((total, score, director_score, runtime_score, candidate, details))

    if not verified:
        return MatchResult(None, best_score, f"no candidate scored above {REJECT_SCORE}")

    verified.sort(key=lambda item: item[0], reverse=True)
    total, title_score, director_score, runtime_score, candidate, details = verified[0]

    # Contradicting evidence vetoes a match; it does not merely lower its score.
    #
    # This was the hardest lesson of the first real run. Treating a mismatch as
    # a small penalty means a perfect title can always outvote it, so "Mouchy"
    # matched a 4-minute short and "Nebezpečné známosti | NT Live" matched a
    # feature film 70 minutes shorter than the broadcast Aero is screening. A
    # runtime that far out is not a weak signal — it is proof of a different
    # work. Only an explicit confirmation on the *other* axis can overrule it.
    if director_score < 0 or runtime_score < 0:
        contradictions = []
        if director_score < 0:
            contradictions.append("director")
        if runtime_score < 0:
            contradictions.append("runtime")

        confirmed_elsewhere = (
            (director_score < 0 and runtime_score >= 1.0)
            or (runtime_score < 0 and director_score >= 1.0)
        )
        if not confirmed_elsewhere:
            return MatchResult(
                None,
                total,
                f"title matched {candidate.get('title')!r} but "
                f"{' and '.join(contradictions)} contradict it",
            )

    if total < REJECT_SCORE:
        return MatchResult(
            None,
            total,
            f"best candidate {candidate.get('title')!r} only scored {total:.2f}",
        )

    return MatchResult(
        candidate["id"],
        total,
        f"verified against director/runtime ({total:.2f}, title {title_score:.2f})",
        details,
    )
