"""
Build data/premieres.json — upcoming Czech theatrical premieres from TMDb.

Where the planning doc left this "TBD" between TMDb upcoming-releases and
Czech distributor dates: TMDb's own /movie/upcoming endpoint (region=CZ)
turned out too thin (about a dozen results, one page). /discover/movie with
region=CZ and with_release_type=2|3 (limited + wide theatrical) returns far
more, and cross-checking against known upcoming titles confirms most of it is
genuinely accurate for new films — TMDb applies the region when a date filter
and region are both present, so a brand-new film's release_date field really
is its Czech date, not some other country's.

The one real gotcha, found by testing rather than assumed: an old title with
an unrelated CZ *rerelease* entry (an anniversary theatrical run, say) can
still slip through the date filter, because TMDb matches the filter against
a release_dates entry it doesn't actually surface — the release_date field
returned is the film's original primary release, which can be years in the
past. A defensive filter (drop anything whose displayed release_date is
before today) throws these out along with any other date-filter oddity,
which is a trade worth making: an arthouse premieres list should show small,
easy-to-miss titles rather than only the popular ones, so nothing here
filters on popularity — see the module's own scope discussion with Matěj.

Usage, from the project folder:

    python -m resolve.premieres              # refresh the list
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from scrapers.base import normalize_title

from .films import build_film_record
from .tmdb import CZECH, ENGLISH, MissingAPIKey, TMDbClient, strip_event_branding

ROOT = Path(__file__).resolve().parent.parent
PREMIERES_FILE = ROOT / "data" / "premieres.json"

# How far ahead to look. Long enough to be worth calling a "calendar", short
# enough that the list stays a genuine near-term preview rather than drifting
# into distributor dates nobody has confirmed yet.
WINDOW_DAYS = 150

# Theatrical release types only (TMDb: 1 premiere, 2 limited theatrical,
# 3 wide theatrical, 4 digital, 5 physical, 6 TV) — a premieres calendar is
# about cinema releases, not a streaming or disc date.
RELEASE_TYPES = "2|3"


def _fetch_candidates(client: TMDbClient, today: date) -> list[dict]:
    """
    Every TMDb result whose displayed release_date falls in the window ahead —
    before the defensive date filter, which the caller applies. Paginates the
    full result set; a few months of Czech theatrical releases fits in a
    handful of pages.
    """
    window_end = (today + timedelta(days=WINDOW_DAYS)).isoformat()
    candidates = []
    page = 1
    while True:
        data = client.get(
            "/discover/movie",
            language=CZECH,
            region="CZ",
            with_release_type=RELEASE_TYPES,
            sort_by="primary_release_date.asc",
            **{
                "release_date.gte": today.isoformat(),
                "release_date.lte": window_end,
            },
            page=page,
        )
        results = data.get("results", [])
        candidates.extend(results)
        total_pages = data.get("total_pages", 1)
        if page >= total_pages or not results:
            break
        page += 1
    return candidates


def dedupe_and_filter(raw: list[dict], today_iso: str) -> list[dict]:
    """
    Dedupe TMDb's discover results by id, then apply the defensive floor: only
    a release_date that is genuinely today or later survives.

    This is what throws out the old-title-with-a-rerelease-entry anomaly (see
    the module docstring) along with any other case where TMDb's date filter
    and the date it actually displays disagree — a plain string comparison is
    enough since every date here is already ISO 8601.
    """
    seen_ids: set[int] = set()
    filtered = []
    for movie in raw:
        tmdb_id = movie.get("id")
        release_date = movie.get("release_date") or ""
        if not tmdb_id or tmdb_id in seen_ids:
            continue
        if release_date < today_iso:
            continue
        seen_ids.add(tmdb_id)
        filtered.append(movie)
    return filtered


def resolve_premieres() -> dict:
    today = date.today()
    client = TMDbClient()

    raw = _fetch_candidates(client, today)
    filtered = dedupe_and_filter(raw, today.isoformat())

    existing = json.loads(PREMIERES_FILE.read_text(encoding="utf-8")) if PREMIERES_FILE.exists() else {}
    cache = {p["tmdb_id"]: p for p in existing.get("premieres", []) if p.get("tmdb_id")}

    premieres = []
    new_count = 0
    for movie in filtered:
        tmdb_id = movie["id"]
        release_date = movie["release_date"]
        cached = cache.get(tmdb_id)
        if cached:
            # Title metadata rarely changes; the date can shift if a distributor
            # reschedules, so that field is always refreshed from the live call.
            cached["release_date"] = release_date
            premieres.append(cached)
            continue

        details_cs = client.movie_details(tmdb_id, language=CZECH)
        details_en = client.movie_details(tmdb_id, language=ENGLISH)
        # TMDb is the source of truth here, unlike films.py where the cinema's
        # own scraped title is ground truth and TMDb is what we're matching
        # against — so the Czech title comes from TMDb itself, falling back to
        # the original title when there's no Czech localisation yet.
        title_cz = (
            (details_cs.get("title") or "").strip()
            or (details_cs.get("original_title") or "").strip()
            or (details_en.get("title") or "").strip()
        )
        if not title_cz:
            continue

        record = build_film_record(
            title_cz, details_cs, details_en, tmdb_id,
            match_reason="TMDb discover: upcoming CZ theatrical release",
            match_score=1.0,
        )
        record["release_date"] = release_date
        # Same normalize_title(strip_event_branding(...)) scheme films.json
        # uses for film_id. A premiere that later gets real screenings and a
        # films.json entry will land under the exact same id, so a saved
        # premiere carries straight over into a real watchlisted film with no
        # extra plumbing.
        record["film_id"] = normalize_title(strip_event_branding(title_cz))
        premieres.append(record)
        new_count += 1
        print(f"  + {title_cz} -> premiere {release_date}")

    premieres.sort(key=lambda p: (p["release_date"], p["title_cz"]))

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "attribution": "This product uses the TMDb API but is not endorsed or certified by TMDb.",
        "premieres": premieres,
    }

    PREMIERES_FILE.parent.mkdir(parents=True, exist_ok=True)
    PREMIERES_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\n{new_count} new, {len(premieres)} premieres total ({WINDOW_DAYS}-day window), {client.call_count} API calls.")
    print(f"Wrote {PREMIERES_FILE}")
    return payload


if __name__ == "__main__":
    import sys

    # Same reasoning as resolve/films.py and scrapers/run.py: a Windows
    # console's legacy codepage can choke on a progress print(), and that must
    # never be allowed to look like a real failure.
    sys.stdout.reconfigure(errors="replace")

    try:
        resolve_premieres()
    except MissingAPIKey as error:
        raise SystemExit(str(error))
