"""
Build data/films.json from data/screenings.json.

Reads every unique film title the scrapers found, resolves it against TMDb once,
and writes a film record the app can render. Titles already present in
films.json are never re-resolved — the whole point of the cache is that a film
costs API calls exactly once, ever.

Usage, from the project folder:

    python -m resolve.films              # resolve anything new
    python -m resolve.films --retry      # also retry previously-failed titles
    python -m resolve.films --force      # re-resolve everything from scratch
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from scrapers.base import normalize_title

from . import csfd
from .tmdb import (
    CZECH,
    ENGLISH,
    MissingAPIKey,
    TMDbClient,
    match_film,
    strip_event_branding,
    title_similarity,
)

ROOT = Path(__file__).resolve().parent.parent
SCREENINGS_FILE = ROOT / "data" / "screenings.json"
FILMS_FILE = ROOT / "data" / "films.json"
OVERRIDES_FILE = Path(__file__).resolve().parent / "overrides.json"

# How many cast members the detail page shows under "Hrají".
CAST_LIMIT = 8


# --------------------------------------------------------------------------
# Pulling the fields we want out of TMDb's response
# --------------------------------------------------------------------------

def _people(credits: dict, *jobs: str) -> list[str]:
    """Crew names for the given jobs, in TMDb's own order, without duplicates."""
    names = []
    for member in credits.get("crew", []):
        if member.get("job") in jobs:
            name = member.get("name", "")
            if name and name not in names:
                names.append(name)
    return names


def _cast(credits: dict) -> list[str]:
    return [
        member.get("name", "")
        for member in credits.get("cast", [])[:CAST_LIMIT]
        if member.get("name")
    ]


def _trailer_key(details: dict) -> str:
    """
    Pick the best YouTube trailer key.

    Preference order: an official Czech trailer, then any Czech one, then an
    official English one, then anything that's a trailer, then a teaser. The app
    plays this inline, so it must be a YouTube video id and nothing else.
    """
    videos = [
        video
        for video in details.get("videos", {}).get("results", [])
        if video.get("site") == "YouTube" and video.get("key")
    ]
    if not videos:
        return ""

    def rank(video: dict) -> tuple:
        is_trailer = video.get("type") == "Trailer"
        is_czech = video.get("iso_639_1") == "cs"
        is_official = bool(video.get("official"))
        # Sorted descending, so True sorts before False.
        return (is_trailer, is_czech, is_official)

    return max(videos, key=rank)["key"]


def _age_rating(details: dict) -> str:
    """Czech certification if TMDb has one, otherwise the US rating as a hint."""
    results = details.get("release_dates", {}).get("results", [])
    by_country = {entry.get("iso_3166_1"): entry for entry in results}

    for country in ("CZ", "US"):
        entry = by_country.get(country)
        if not entry:
            continue
        for release in entry.get("release_dates", []):
            certification = (release.get("certification") or "").strip()
            if certification:
                return certification if country == "CZ" else f"{certification} (US)"
    return ""


def build_film_record(
    title_cz: str,
    details_cs: dict,
    details_en: dict,
    tmdb_id: int,
    match_reason: str,
    match_score: float,
    poster_fallback: str = "",
) -> dict:
    """Assemble the record the app reads. Field names follow the planning doc's data model."""
    # Credits come from the English response so crew and cast names are in the
    # Latin alphabet. A Czech request returns 王家衛 rather than "Wong Kar-Wai",
    # which is both wrong for the UI and unsearchable by anyone typing "wong".
    credits = details_en.get("credits") or details_cs.get("credits", {})
    release_date = details_cs.get("release_date") or details_en.get("release_date") or ""
    year = int(release_date[:4]) if release_date[:4].isdigit() else None

    # Czech synopsis when TMDb has one; English is a far better fallback than
    # an empty box, and arthouse titles often only have the English text.
    synopsis = (details_cs.get("overview") or "").strip()
    synopsis_language = "cs"
    if not synopsis:
        synopsis = (details_en.get("overview") or "").strip()
        synopsis_language = "en" if synopsis else ""

    title_en = (details_en.get("title") or "").strip()

    return {
        "film_id": normalize_title(strip_event_branding(title_cz)),
        "title_cz": title_cz,
        "title_en": title_en,
        "original_title": (details_cs.get("original_title") or "").strip(),
        "year": year,
        "synopsis": synopsis,
        "synopsis_language": synopsis_language,
        # TMDb genuinely returns 0 for films it hasn't got a runtime for yet
        # (typically an unreleased film, still "In Production"). 0 minutes isn't
        # a real runtime for any film, so treat it the same as missing rather
        # than showing "0'" — or having every consumer re-derive that rule.
        "runtime_min": details_cs.get("runtime") or None,
        "genres": [g.get("name", "") for g in details_cs.get("genres", []) if g.get("name")],
        "director": _people(credits, "Director"),
        "screenwriter": _people(credits, "Screenplay", "Writer", "Story"),
        "cast": _cast(credits),
        "production_company": [
            c.get("name", "") for c in details_cs.get("production_companies", []) if c.get("name")
        ],
        "poster_path": details_cs.get("poster_path") or "",
        # The cinema's own poster. The app should prefer TMDb's poster_path and
        # fall back to this, so no film ever renders as a blank tile.
        "poster_fallback_url": poster_fallback,
        "backdrop_path": details_cs.get("backdrop_path") or "",
        "trailer_youtube_key": _trailer_key(details_cs),
        "age_rating": _age_rating(details_cs),
        "tmdb_id": tmdb_id,
        "csfd_url": csfd.search_url(title_cz, year),
        "resolved": True,
        "match_reason": match_reason,
        "match_score": round(match_score, 3),
    }


def unresolved_record(
    title_cz: str, reason: str, score: float, poster_fallback: str = ""
) -> dict:
    """
    A film we couldn't match confidently.

    We still write a record, with `resolved: false` and whatever we know. That
    way the app can show the screening with its Czech title rather than dropping
    it, and the title is visible in films.json for a manual override.
    """
    return {
        "film_id": normalize_title(strip_event_branding(title_cz)),
        "title_cz": title_cz,
        "title_en": "",
        "original_title": "",
        "year": None,
        "synopsis": "",
        "synopsis_language": "",
        "runtime_min": None,
        "genres": [],
        "director": [],
        "screenwriter": [],
        "cast": [],
        "production_company": [],
        "poster_path": "",
        # Even with no TMDb match, the cinema's own poster means this film still
        # renders properly in the app instead of as a placeholder tile.
        "poster_fallback_url": poster_fallback,
        "backdrop_path": "",
        "trailer_youtube_key": "",
        "age_rating": "",
        "tmdb_id": None,
        "csfd_url": csfd.search_url(title_cz),
        "resolved": False,
        "match_reason": reason,
        "match_score": round(score, 3),
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

# How similar two normalized titles must be before we treat them as the same
# film. Tuned to the real case this exists for: "odyssea" vs "oddysea" scores
# about 0.86, so the threshold has to sit below that.
SAME_FILM_THRESHOLD = 0.85
# ...but a loose threshold alone would merge sequels, so the guards below matter
# at least as much as the number.
MAX_LENGTH_DIFFERENCE = 2


def _digits(text: str) -> list[str]:
    """Every run of digits in a title: 'toy story 5' -> ['5']."""
    return re.findall(r"\d+", text)


def is_same_film(key_a: str, key_b: str) -> bool:
    """
    Decide whether two normalized titles are the same film misspelled, rather
    than two different films that look alike.

    Fuzzy similarity alone is not enough. "toy story 4" and "toy story 5" score
    0.91 — comfortably above any threshold that still catches a real typo — and
    merging them would show one film's poster and synopsis for the other. So a
    difference in numbering is treated as decisive: sequels differ by exactly the
    digits, and typos essentially never invent or drop them.
    """
    if key_a == key_b:
        return True
    # Sequels, episodes, years: different numbers mean different films, full stop.
    if _digits(key_a) != _digits(key_b):
        return False
    # A typo shifts a couple of characters; it doesn't change a title's length
    # substantially. This blocks "pramen" from absorbing a longer relative.
    if abs(len(key_a) - len(key_b)) > MAX_LENGTH_DIFFERENCE:
        return False
    return title_similarity(key_a, key_b) >= SAME_FILM_THRESHOLD


def unique_titles(screenings: list[dict]) -> dict[str, dict]:
    """
    Collapse screenings down to one entry per film.

    Grouping is fuzzy, not exact: the real data already contains "Odyssea" and
    "Oddysea" for the same film, and each spelling would otherwise cost its own
    TMDb lookup and show up as a separate film in the app.

    When spellings disagree, the one appearing on the most screenings wins as
    the canonical title — a typo is almost always the rarer variant.
    """
    films: dict[str, dict] = {}

    for screening in screenings:
        title = screening.get("title_cz", "").strip()
        if not title:
            continue
        key = normalize_title(strip_event_branding(title))
        if not key:
            continue

        # Does this belong with a film we've already seen?
        match = next((existing for existing in films if is_same_film(existing, key)), None)

        if match is None:
            films[key] = {
                "title_cz": title,
                "director": screening.get("director", ""),
                "runtime_min": screening.get("runtime_min"),
                # The cinema's own poster, kept as a fallback for films TMDb
                # can't identify. Aero publishes one for every screening.
                "poster_url": screening.get("poster_url", ""),
                "_spellings": {title: 1},
            }
            continue

        entry = films[match]
        entry["_spellings"][title] = entry["_spellings"].get(title, 0) + 1
        # Fill in hints a previous screening didn't have.
        if not entry.get("director"):
            entry["director"] = screening.get("director", "")
        if not entry.get("runtime_min"):
            entry["runtime_min"] = screening.get("runtime_min")
        if not entry.get("poster_url"):
            entry["poster_url"] = screening.get("poster_url", "")

    # Settle on the most common spelling as the title we show and search with.
    for entry in films.values():
        spellings = entry.pop("_spellings")
        entry["title_cz"] = max(spellings.items(), key=lambda pair: pair[1])[0]

    return films


def assign_film_ids(screenings: list[dict], film_keys) -> int:
    """
    Stamp every screening with the film_id it belongs to.

    The app needs to join screenings to films, and the grouping rules (fuzzy
    matching, sequel guards, canonical spellings) live here in Python. Rather
    than reimplement all of that in JavaScript — where it would inevitably drift
    out of step — we write the answer into the data and let the app do a plain
    dictionary lookup.
    """
    stamped = 0
    for screening in screenings:
        title = screening.get("title_cz", "").strip()
        if not title:
            continue
        key = normalize_title(strip_event_branding(title))
        if key not in film_keys:
            key = next((k for k in film_keys if is_same_film(k, key)), key)
        screening["film_id"] = key
        stamped += 1
    return stamped


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_all(retry_failed: bool = False, force: bool = False) -> dict:
    screenings_data = load_json(SCREENINGS_FILE, None)
    if screenings_data is None:
        raise SystemExit(
            f"{SCREENINGS_FILE} not found — run `python -m scrapers.run` first."
        )

    wanted = unique_titles(screenings_data.get("screenings", []))
    # Keys starting with "_" are documentation inside overrides.json, not entries.
    overrides = {
        key: value
        for key, value in load_json(OVERRIDES_FILE, {}).items()
        if not key.startswith("_") and isinstance(value, dict)
    }

    existing_data = load_json(FILMS_FILE, {"films": []})
    cache = {film["film_id"]: film for film in existing_data.get("films", [])}

    client = TMDbClient()

    resolved_count = 0
    failed = []

    for key, hints in sorted(wanted.items()):
        cached = cache.get(key)
        if cached and not force:
            if cached.get("resolved") or not retry_failed:
                continue  # already done, or a known failure we're not retrying

        title = hints["title_cz"]
        override = overrides.get(key, {})

        if override.get("skip"):
            print(f"  - {title}: skipped by override")
            continue

        try:
            if override.get("tmdb_id"):
                # A human has told us the answer; trust it and skip matching.
                tmdb_id = int(override["tmdb_id"])
                details_en = client.movie_details(tmdb_id, language=ENGLISH)
                reason, score = "manual override", 1.0
            else:
                result = match_film(
                    client, title, hints.get("director", ""), hints.get("runtime_min")
                )
                if not result.resolved:
                    print(f"  ? {title}: UNRESOLVED — {result.reason}")
                    unresolved = unresolved_record(
                        title, result.reason, result.score, hints.get("poster_url", "")
                    )
                    unresolved["film_id"] = key
                    cache[key] = unresolved
                    failed.append(title)
                    continue
                tmdb_id = result.tmdb_id
                # The matcher already fetched the English details to verify the
                # director, so reuse them rather than paying for them twice.
                details_en = result.details or client.movie_details(tmdb_id, language=ENGLISH)
                reason, score = result.reason, result.score

            # Czech for the things we want localised: title, synopsis, genres.
            # Credits deliberately come from the English response instead —
            # see the note in tmdb.match_film.
            details_cs = client.movie_details(tmdb_id, language=CZECH)

            record = build_film_record(
                title, details_cs, details_en, tmdb_id, reason, score,
                poster_fallback=hints.get("poster_url", ""),
            )
            # Pin the record to the grouping key. Fuzzy grouping means the
            # canonical title can be a different spelling than the one that
            # created the group, and if film_id drifted from the key we look up,
            # the cache would miss forever and re-resolve the film every run.
            record["film_id"] = key
            if override.get("csfd_url"):
                record["csfd_url"] = override["csfd_url"]

            cache[key] = record
            resolved_count += 1
            print(f"  + {title} -> {record['title_en'] or record['original_title']} ({record['year']})")

        except Exception as error:
            # One bad film must not lose the whole run's work.
            print(f"  ! {title}: ERROR — {error}")
            errored = unresolved_record(
                title, f"error: {error}", 0.0, hints.get("poster_url", "")
            )
            errored["film_id"] = key
            cache[key] = errored
            failed.append(title)

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "attribution": "This product uses the TMDb API but is not endorsed or certified by TMDb.",
        "films": [cache[key] for key in sorted(cache)],
    }

    FILMS_FILE.parent.mkdir(parents=True, exist_ok=True)
    FILMS_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Write the film_id back onto every screening so the app can join the two
    # files without re-deriving any of the grouping logic.
    stamped = assign_film_ids(screenings_data.get("screenings", []), set(cache))
    SCREENINGS_FILE.write_text(
        json.dumps(screenings_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Stamped film_id onto {stamped} screenings")

    total = len(payload["films"])
    unresolved = [f["title_cz"] for f in payload["films"] if not f.get("resolved")]
    print(f"\n{resolved_count} newly resolved, {total} films total, {client.call_count} API calls.")
    if unresolved:
        print(f"{len(unresolved)} unresolved: {', '.join(unresolved)}")
        print(f"Add a tmdb_id for these in {OVERRIDES_FILE.name} and run again.")
    print(f"Wrote {FILMS_FILE}")
    return payload


if __name__ == "__main__":
    import sys

    # A Windows console is often locked to a legacy codepage (cp1250 etc.) that
    # can't represent every character a TMDb title might contain — a Latvian,
    # Vietnamese or otherwise non-Czech film's title, say. That must never
    # crash the run: this is print()-ing a progress message, not writing the
    # actual data. It genuinely destroyed a correct result once — "Sirāt"
    # resolved successfully, cache[key] was set to the right record, and then
    # the success print for its own title crashed on 'ā'; the broad except
    # below caught that crash and overwrote the correct record with a bogus
    # "error" entry. Console text is only for a human to skim; replacing one
    # unprintable character with '?' is harmless, silently losing a real
    # resolution is not.
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Resolve film metadata against TMDb.")
    parser.add_argument("--retry", action="store_true", help="retry previously-failed titles")
    parser.add_argument("--force", action="store_true", help="re-resolve every title from scratch")
    args = parser.parse_args()

    try:
        resolve_all(retry_failed=args.retry, force=args.force)
    except MissingAPIKey as error:
        raise SystemExit(str(error))
