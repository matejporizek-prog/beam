"""
Shared scraper for Cinema City's Prague multiplexes.

Cinema City (part of the Cineworld group) runs on Vista Cinema Group's
booking platform, which — unlike every arthouse cinema scraped so far —
exposes a genuine public JSON API rather than server-rendered HTML. It's the
same endpoint cinemacity.cz's own front-end JavaScript calls:

    GET /cz/data-api-service/v1/quickbook/{circuit}/film-events
        /in-cinema/{cinemaId}/at-date/{date}?attr=&lang=cs_CZ

"10101" is Vista's circuit code for the Czech Republic market (every
Cineworld-group market has its own — this was found, not guessed, by
checking the site's own asset URLs, e.g. /mrest/logos/v1/10101/logo.svg).
{cinemaId} is Cinema City's own internal id for one physical location,
found embedded in cinemacity.cz's /whatson page HTML (search that page's
source for "externalCode" to find every Prague location's id, address and
coordinates in one place — that's where the six ids below came from).

One call returns that single cinema's full schedule for one date: `films`
(title, runtime, poster — keyed by id) and `events` (the actual showtimes,
each carrying a filmId to join against). No HTML parsing at all, which
makes this the most reliable of Beam's cinema data sources so far.

DAYS_AHEAD matches what the API actually publishes — confirmed by probing
several offsets live: today through +5 days return a full ~44-45
events/day per cinema, and +6 and beyond thins to a handful of long-running
outliers, not a real schedule. The daily cron keeps this window fresh the
same way it already does for every other cinema (see scrape.yml).

Each per-cinema module (cinema_city_flora.py, cinema_city_chodov.py, ...) is
a three-line wrapper naming its own cinema id — the same pattern
aerofilms.py's Aerofilms cinemas already use for one shared platform.
"""

from __future__ import annotations

from datetime import date as date_cls, datetime, timedelta

from .base import Screening, empty_dates_in_range, fetch_json, language_name

API_BASE = "https://www.cinemacity.cz/cz/data-api-service/v1/quickbook/10101/film-events/in-cinema"

DAYS_AHEAD = 6  # today + 5 more days — see module docstring

# Vista's presentation-format attribute codes that affect the app's own
# format filter (is35mm() in data.js just checks for "35" anywhere in the
# string) — everything else Vista sends ("dolby-atmos", "vip", genre codes,
# age ratings, ...) is display-only or not meaningful here, and is left out
# rather than mapped, the same as how classify_tags() treats an unrecognised
# tag elsewhere.
FORMAT_ATTRS = {
    "70-mm": "70 mm",
    "3d": "3D",
}

# Presentation extras worth a "strand" chip even though a multiplex has no
# curated programming strands the way an arthouse cinema does — this is the
# app's only other visible tag, and "why pick this specific showing" is a
# reasonable use for it. Priority order: the first one found wins, so a
# screening flagged both 4DX and Dolby Atmos shows the more distinctive of
# the two rather than stacking both.
STRAND_ATTRS = [
    ("4dx", "4DX"),
    ("dolby-atmos", "Dolby Atmos"),
    ("vip", "VIP"),
    ("laser-barco", "Laser"),
]


def scrape(cinema: str, cinema_id: str, payloads: dict[str, dict] | None = None) -> dict:
    """
    Scrape one Cinema City location's next few days of showtimes.

    Unlike every other cinema module, this calls a JSON API once per date
    rather than fetching a single page. Pass `payloads` (date -> parsed JSON
    body) to test against saved responses; leave it out to fetch the live
    site for today through DAYS_AHEAD.
    """
    screenings: list[Screening] = []
    covered_dates: list[str] = []

    # In tests, `payloads` supplies its own fixed dates directly — computing
    # them from date.today() instead would make the fixture quietly stop
    # matching the moment "today" drifts past the dates it was captured for,
    # defeating the whole point of a saved fixture.
    if payloads is not None:
        dates = sorted(payloads.keys())
    else:
        today = date_cls.today()
        dates = [(today + timedelta(days=offset)).isoformat() for offset in range(DAYS_AHEAD)]

    for iso in dates:
        if payloads is not None:
            payload = payloads.get(iso)
            if payload is None:
                continue
        else:
            try:
                payload = fetch_json(f"{API_BASE}/{cinema_id}/at-date/{iso}?attr=&lang=cs_CZ")
            except Exception:
                # A single bad date (site hiccup, a cinema temporarily
                # missing from the feed) shouldn't cost us the rest of the
                # week for this cinema — the other days are still good.
                continue

        covered_dates.append(iso)
        body = payload.get("body") or {}
        films_by_id = {film["id"]: film for film in body.get("films", [])}
        for event in body.get("events", []):
            screening = _screening_from_event(event, films_by_id, cinema)
            if screening:
                screenings.append(screening)

    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))

    return {
        "cinema": cinema,
        "source_url": f"https://www.cinemacity.cz/cz/cinema/{cinema_id}",
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, {s.date for s in screenings}),
        "screenings": [s.to_dict() for s in screenings],
    }


def _screening_from_event(event: dict, films_by_id: dict, cinema: str) -> Screening | None:
    film = films_by_id.get(event.get("filmId"))
    if not film or not film.get("name"):
        return None

    when = event.get("eventDateTime", "")
    if "T" not in when:
        return None
    screening_date, time_part = when.split("T", 1)
    screening_time = time_part[:5]  # "09:00:00" -> "09:00"

    attrs = set(event.get("attributeIds", []))
    language_version, english_friendly, language = _language_info(event.get("languages") or {})

    format_ = ""
    for code, label in FORMAT_ATTRS.items():
        if code in attrs:
            format_ = label
            break

    strand = ""
    for code, label in STRAND_ATTRS:
        if code in attrs:
            strand = label
            break

    note = strand or format_ or (language_version if language_version else ("english friendly" if english_friendly else ""))

    return Screening(
        cinema=cinema,
        title_cz=film["name"],
        date=screening_date,
        time=screening_time,
        language=language,
        format=format_,
        note=note,
        english_friendly=english_friendly,
        language_version=language_version,
        strand=strand,
        hall=event.get("auditoriumTinyName", "") or event.get("auditorium", ""),
        tags=sorted(attrs),
        booking_url=event.get("bookingRouterLaunchLink", ""),
        poster_url=film.get("posterLink", ""),
        runtime_min=film.get("length"),
        source_id=str(event.get("id", "")),
    )


def _language_info(languages: dict) -> tuple[str, bool, str]:
    """
    Map Vista's {original, dubbed, voiceover, subtitles} language-code arrays
    onto (language_version, english_friendly, language) — the same
    distinction base.classify_tags() draws from cinema-printed chips
    elsewhere. Here we have real structured data instead, so there's no chip
    text to guess at.
    """
    original = languages.get("original") or []
    dubbed = languages.get("dubbed") or []
    subtitles = languages.get("subtitles") or []

    if "cs" in dubbed:
        version = "dabing"
    elif subtitles and "cs" not in original:
        version = "titulky"
    elif original and "cs" not in original:
        version = "originál"
    else:
        version = ""  # Czech-original film — presented the normal way

    english_friendly = "en" in original and "cs" not in dubbed
    language = language_name(", ".join(original))
    return version, english_friendly, language
