"""
Shared scraper for CineStar's Prague multiplexes (Anděl, Černý Most).

Previously flagged as not scrapable (see README.md's Phase 3 section) — the
site's program page always looked like it should be readable (the schedule
is embedded server-rendered data, not a client-only fetch), but a plain
request against it kept coming back with the showtimes stripped of which
film each one was for. Revisited 2026-08-05 and it now works cleanly with
nothing more exotic than this project's own USER_AGENT and two plain GETs —
whatever was degrading the response before either wasn't what it looked
like, or CineStar's own protection has changed since. Recorded here rather
than re-guessed: if this ever silently degrades again, it will look like
`scheduledEventsEntries` still being present but every `movies_by_id` lookup
missing (see `_screening_from_event`), which is a real, distinguishable
signal, not a crash.

Two plain GETs, no API key, no session warm-up:

1. `GET /cz/{slug}/program` — a Nuxt 3 SSR page. The schedule
   (`scheduledEventsEntries`: EventId, Start/Finish as UTC timestamps, a
   numeric TitleId, and a flat list of presentation-tag Properties like
   "Dabing"/"Titulky"/"3D"/"GOLD CLASS") lives in the page's own
   `__NUXT_DATA__` script tag — a devalue-flattened state tree, not plain
   JSON (see devalue.py). One fetch per cinema covers roughly two weeks of
   near-term programming in one go, plus scattered far-future advance-sale
   dates the site's own "Předprodej" tab surfaces — see `_covered_dates`
   for why only the near-term run counts as "covered" for gap-detection.

2. `GET craft.cinestar.cz/api?query=...` — a genuine public GraphQL
   endpoint (Craft CMS's own), found by watching the real page's own
   network requests rather than guessed. `ListMainMovies`, given every
   distinct TitleId from step 1, resolves each to its title, runtime, age
   rating and poster in one call — confirmed against the full 52-title set
   from a live schedule, not a small sample.

Not yet captured: a per-screening booking URL (`websale.cinestar.cz`'s
exact link pattern wasn't confirmed live — every bookable-looking time slot
sampled was already sold through or past). `booking_url` is left empty
rather than guessed; the app already degrades a missing one to a dead link
rather than crashing (see `.buy` in screens.js), which is the honest state
until this is revisited. Also not captured: original spoken language per
screening (only Dabing/Titulky, not which language is being dubbed or
subtitled from) — `english_friendly` and `language` are left at their
defaults rather than guessed from a title looking like a Hollywood release.
"""

from __future__ import annotations

import json
from datetime import date as date_cls, datetime, timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .base import Screening, empty_dates_in_range, fetch, fetch_json
from .devalue import unflatten

PROGRAM_URL = "https://www.cinestar.cz/cz/{slug}/program"

CATALOG_URL = "https://craft.cinestar.cz/api"
# Exactly the query the site's own front-end sends for its schedule grid —
# captured from a live page's network requests, not written from scratch.
CATALOG_QUERY = (
    "query ListMainMovies($site: [String], $GroupId: [QueryArgument!], $MovieId: [QueryArgument!]) "
    "{ moviesEntries(site: $site, GroupId: $GroupId, MovieId: $MovieId) { ... on movies_default_Entry "
    "{ slug MovieId TitleArray Accessibility Duration Movie3D MovieDubbing MovieSubtitles PictureUrl "
    "__typename } __typename } }"
)

PRAGUE_TZ = ZoneInfo("Europe/Prague")

# CineStar's own catalog bakes the screening variant straight into the
# title text ("Mimoni a monstra DABING", "Odyssea TITULKY GC") — confirmed
# systematic across both Prague locations' entire live catalogs, not an
# occasional glitch: every dubbed/subtitled/Czech-original entry carries
# one of these as a trailing, space-separated, all-caps token (sometimes
# two, e.g. "DABING MINI KINO"). Properties already carries this same
# information cleanly (see _screening_from_event), so it's dropped from the
# title rather than shown twice and messily. Deliberately a known-token
# allowlist, not "strip any trailing uppercase word" — two real titles in
# that same catalog ("Cirque du Soleil: KOOZA", "GHOST: 2 BIG TO RIG") are
# themselves genuinely all-caps, and a blanket heuristic would have mangled
# both. GC/TDL/BC are auditorium-tier codes (Gold Class, Theatre Deluxe, and
# a third seen only at Černý Most) — confirmed against both locations'
# catalogs, not just Anděl's, since a location-specific code silently
# missing from this set doesn't error, it just leaves a suffix attached.
_TITLE_SUFFIX_TOKENS = {
    "CZ", "DABING", "TITULKY", "OV", "GC", "TDL", "BC", "ATMOS", "3D",
    "MINI", "KINO", "UA", "ZNĚNÍ", "ČSFD",
}


def _clean_title(raw: str) -> str:
    tokens = raw.split()
    while tokens and tokens[-1] in _TITLE_SUFFIX_TOKENS:
        tokens.pop()
    return " ".join(tokens).strip() or raw.strip()


# Presentation-tier chips worth a strand — same "why pick this specific
# showing" reasoning as Cinema City's STRAND_ATTRS, and the same
# first-match-wins priority so a Gold Class + Atmos screening shows the
# more distinctive of the two rather than stacking both. CineStar's own
# Properties list is an unordered bag per screening (format, tier, and
# promo badges like "HIT"/"Premiéra" all mixed together with no structural
# way to tell them apart), so this is curated rather than auto-classified —
# same call Cinema City already made for the same reason. Title-case, not
# the all-caps the site's own CSS renders these as (text-transform:
# uppercase) — confirmed against the real Properties data, not the
# rendered page text, which would have gotten this wrong.
STRAND_NAMES = ["IMAX", "4DX", "Gold Class", "Premium", "Atmos"]


def scrape(cinema: str, slug: str, html: str | None = None, catalog: dict | None = None) -> dict:
    """
    Scrape one CineStar location's schedule.

    Pass `html` (the program page's raw HTML) and `catalog` (the parsed
    GraphQL catalog response) to test against saved fixtures; leave both
    out to fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL.format(slug=slug))

    root = unflatten(_extract_nuxt_payload(html))
    schedule = _find_scheduled_events(root)

    movie_ids = sorted({event["TitleId"] for event in schedule if event.get("TitleId")})
    if catalog is None:
        catalog = _fetch_catalog(movie_ids) if movie_ids else {"data": {"moviesEntries": []}}
    movies_by_id = {
        movie["MovieId"]: movie
        for movie in catalog.get("data", {}).get("moviesEntries", [])
    }

    screenings: list[Screening] = []
    for event in schedule:
        screening = _screening_from_event(event, movies_by_id, cinema)
        if screening:
            screenings.append(screening)
    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))

    covered_dates = _covered_dates(schedule)

    return {
        "cinema": cinema,
        "source_url": PROGRAM_URL.format(slug=slug),
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, {s.date for s in screenings}),
        "screenings": [s.to_dict() for s in screenings],
    }


def _extract_nuxt_payload(html: str) -> list:
    # Matching on the id value itself, not a specific attribute order —
    # the real tag is `<script type="application/json"
    # data-nuxt-data="nuxt-app" data-ssr="true" id="__NUXT_DATA__">`, with
    # id last, not first.
    marker = html.find('id="__NUXT_DATA__"')
    if marker == -1:
        raise ValueError("CineStar page has no __NUXT_DATA__ payload — page structure may have changed")
    tag_end = html.find(">", marker) + 1
    end = html.find("</script>", tag_end)
    return json.loads(html[tag_end:end])


def _find_scheduled_events(root: dict) -> list[dict]:
    """
    Find `scheduledEventsEntries` by field name, not by its containing
    key — that key is one of Nuxt's own auto-generated cache-hash ids
    (`useAsyncData`'s hash of call-site + args), which is not guaranteed
    stable across a CineStar frontend redeploy. Matching by shape rather
    than by that opaque key is what keeps this working across one.
    """
    for value in root.get("data", {}).values():
        if isinstance(value, dict) and "scheduledEventsEntries" in value:
            return value["scheduledEventsEntries"]
    raise ValueError("scheduledEventsEntries not found in CineStar's payload — page structure may have changed")


def _covered_dates(schedule: list[dict]) -> list[str]:
    """
    Only the contiguous near-term run of dates counts as "covered" for
    gap detection — CineStar's payload also carries scattered one-off
    advance-sale dates months out (the site's own "Předprodej" tab), and
    treating the whole span between today and one of those as "covered"
    would make empty_dates_in_range() report months of false gaps.
    """
    dates = {event["Start"][:10] for event in schedule if event.get("Start")}
    if not dates:
        return []
    covered = []
    current = date_cls.fromisoformat(min(dates))
    while current.isoformat() in dates:
        covered.append(current.isoformat())
        current += timedelta(days=1)
    return covered


def _fetch_catalog(movie_ids: list[str]) -> dict:
    variables = json.dumps({"MovieId": movie_ids})
    url = (
        f"{CATALOG_URL}?query={quote(CATALOG_QUERY)}"
        f"&operationName=ListMainMovies&variables={quote(variables)}"
    )
    return fetch_json(url)


def _screening_from_event(event: dict, movies_by_id: dict, cinema: str) -> Screening | None:
    movie = movies_by_id.get(event.get("TitleId"))
    if not movie or not movie.get("TitleArray"):
        return None

    start = event.get("Start", "")
    if "T" not in start:
        return None
    # Start/Finish are UTC timestamps ("...+00:00") regardless of what
    # timezone this scraper runs in (a GitHub Actions runner is UTC) —
    # converting explicitly to Europe/Prague, not relying on system-local,
    # is what keeps the displayed time correct across the CET/CEST switch.
    start_local = datetime.fromisoformat(start).astimezone(PRAGUE_TZ)

    tags = [p["Name"] for p in event.get("Properties", []) if p.get("Name")]
    tag_set = set(tags)
    if "Dabing" in tag_set:
        language_version = "dabing"
    elif "Titulky" in tag_set:
        language_version = "titulky"
    elif "Originální znění" in tag_set:
        language_version = "originál"
    else:
        language_version = ""
    format_ = "3D" if "3D" in tag_set else ""
    strand = next((name for name in STRAND_NAMES if name in tag_set), "")
    note = strand or format_ or language_version

    duration = movie.get("Duration")
    poster = movie.get("PictureUrl") or ""

    return Screening(
        cinema=cinema,
        title_cz=_clean_title(movie["TitleArray"]),
        date=start_local.date().isoformat(),
        time=start_local.strftime("%H:%M"),
        format=format_,
        note=note,
        language_version=language_version,
        strand=strand,
        tags=sorted(tag_set),
        # PictureUrl is sometimes a bare filename ("cinestar2.jpg") rather
        # than a real URL when CineStar has no poster of its own for a
        # title yet — TMDb resolution beats a real poster_url anyway (see
        # Screening's own docstring), so a non-URL value is worth dropping
        # rather than shipping a broken image src.
        poster_url=poster if poster.startswith("http") else "",
        runtime_min=int(duration) if duration and duration.isdigit() else None,
        source_id=str(event.get("EventId", "")),
    )
