"""
Shared scraper for the Aerofilms cinemas: Kino Aero, Bio Oko and Kino Světozor.

All three are run by the same operator and — conveniently — built on the same
website platform, so one parser handles all of them. Each per-cinema module
(kino_aero.py, bio_oko.py, svetozor.py) is a three-line wrapper that calls
scrape() here with its own name and program URL.

How the page is built, and why we parse it the way we do
--------------------------------------------------------
The program page is server-rendered (no JavaScript needed) and embeds a
schema.org "Event" block as JSON-LD next to every single screening. That block
is the primary source, because it gives the things that are painful to scrape
from visible text:

    - the exact start time as a timezone-aware ISO timestamp, so we never have
      to interpret the Czech day headers "Dnes" / "Zítra"
    - the film's language, director, runtime and poster
    - a stable per-screening URL to use as the "Vstupenky" link

What JSON-LD does *not* contain is the cinema's own tags — "35 mm",
"English Friendly", "Malé oči", "Dabing". Those only exist as visible chips, so
we read them from the HTML and classify them in base.classify_tags().

So each screening is assembled from two halves of the same row:
    JSON-LD   -> what the film is and when it starts
    HTML tags -> how this particular screening is presented

Timing note for the scheduled job
---------------------------------
The page only lists screenings that haven't started yet — scrape it at 22:00 and
today will look like it had one screening all day. The weekly cron therefore
runs early in the morning, before the first matinee, or each run would quietly
lose that day's earlier shows.

One nice detail: these cinemas only tag the *exception*. Dubbed screenings carry
a "Dabing" chip; subtitled ones carry nothing. There is no "Titulky" tag. That
matches the app's rule of showing a version chip only when it deviates from the
norm, so an empty `language_version` means "presented the usual way", not "we
failed to find it".
"""

from __future__ import annotations

import json
import re
from datetime import date as date_cls, datetime, timedelta
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

from .base import (
    Screening,
    classify_tags,
    clean_text,
    fetch,
    language_name,
    parse_iso_duration,
)

# The day anchor looks like: id="program-day-21-07-2026"
DAY_ID_RE = re.compile(r"program-day-(\d{2})-(\d{2})-(\d{4})")


def scrape(cinema: str, program_url: str, html: str | None = None) -> dict:
    """
    Scrape one Aerofilms cinema's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to fetch
    the live site. Returns a dict with the cinema, its screenings, and which
    dates the page actually covered.
    """
    if html is None:
        html = fetch(program_url)

    soup = BeautifulSoup(html, "lxml")

    screenings: list[Screening] = []
    covered_dates: list[str] = []

    # Each ".program" block is one day: a date anchor plus that day's rows.
    for day_block in soup.find_all("div", class_="program"):
        day_date = _parse_day_date(day_block)
        if day_date:
            covered_dates.append(day_date)

        for row in day_block.find_all("div", class_="program__info-row"):
            screening = _parse_row(row, cinema, program_url, fallback_date=day_date)
            if screening:
                screenings.append(screening)

    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))

    return {
        "cinema": cinema,
        "source_url": program_url,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        # Days the page listed but which held no screenings at all. This is how a
        # quiet day stays distinguishable from a day we simply never looked at —
        # and it is the same signal a closed cinema (Ponrepo) will produce.
        "empty_dates": _empty_dates(covered_dates, screenings),
        "screenings": [s.to_dict() for s in screenings],
    }


# --------------------------------------------------------------------------
# Row parsing
# --------------------------------------------------------------------------

def _parse_row(row, cinema: str, program_url: str, fallback_date: str | None) -> Screening | None:
    """Build one Screening from one .program__info-row element."""

    data = _extract_json_ld(row)

    # --- title ---
    title = clean_text(data.get("name", "")) if data else ""
    if not title:
        name_el = row.find("div", class_="program__movie-name")
        title = clean_text(name_el.get_text()) if name_el else ""
    if not title:
        # No title means this isn't really a screening row; skip rather than
        # emit a broken record.
        return None

    # --- date and time ---
    screening_date, screening_time = _extract_datetime(row, data, fallback_date)
    if not screening_date or not screening_time:
        return None

    # --- tags (the half JSON-LD doesn't have) ---
    raw_tags = [tag.get_text() for tag in row.find_all("span", class_="program__tag")]
    classified = classify_tags(raw_tags)

    return Screening(
        cinema=cinema,
        title_cz=title,
        date=screening_date,
        time=screening_time,
        language=language_name(data.get("inLanguage", "")) if data else "",
        format=classified["format"],
        # `note` keeps the sample file's human-readable label. The strand is the
        # most useful thing to put there; if there's no strand we fall back to
        # whatever the screening is actually flagged as.
        note=classified["strand"] or classified["format"] or _friendly_note(classified),
        english_friendly=classified["english_friendly"],
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall=_extract_hall(row),
        tags=classified["tags"],
        booking_url=_extract_booking_url(row, data, program_url),
        poster_url=data.get("image", "") if data else "",
        director=clean_text(data.get("director", "")) if data else "",
        runtime_min=parse_iso_duration(data.get("duration", "")) if data else None,
        source_id=_extract_source_id(row),
    )


def _extract_json_ld(row) -> dict:
    """Read the schema.org Event block attached to this screening."""
    script = row.find("script", attrs={"type": "application/ld+json"})
    if not script or not script.string:
        return {}
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        # A malformed block shouldn't lose us the whole screening — the HTML
        # fallbacks below can still produce a usable record.
        return {}
    return data if isinstance(data, dict) else {}


def _extract_datetime(row, data: dict, fallback_date: str | None):
    """
    Get (date, time) for a screening.

    Prefer JSON-LD's `startDate` — it is unambiguous and already timezone-aware.
    Fall back to the visible time plus the date from the day header.
    """
    start = data.get("startDate") if data else None
    if start:
        try:
            parsed = datetime.fromisoformat(start)
            return parsed.strftime("%Y-%m-%d"), parsed.strftime("%H:%M")
        except ValueError:
            pass  # fall through to the HTML fallback

    hour_el = row.find("div", class_="program__hour")
    hour = clean_text(hour_el.get_text()) if hour_el else ""
    match = re.search(r"(\d{1,2})[:.](\d{2})", hour)
    if not match or not fallback_date:
        return None, None
    return fallback_date, f"{int(match.group(1)):02d}:{match.group(2)}"


def _extract_hall(row) -> str:
    """
    Pull the hall name out of the venue block.

    The markup is "<span>Aero</span><br>Kinosál" — the span is the venue, the
    loose text after it is the hall. We only want the hall.
    """
    place = row.find("div", class_="program__place program__place--desktop")
    if place is None:
        place = row.find("div", class_="program__place--desktop")
    if place is None:
        return ""
    venue = place.find("span")
    venue_text = clean_text(venue.get_text()) if venue else ""
    full_text = clean_text(place.get_text(" "))
    if venue_text and full_text.startswith(venue_text):
        return clean_text(full_text[len(venue_text):])
    return full_text


def _extract_booking_url(row, data: dict, program_url: str) -> str:
    """
    The link the app's "Vstupenky" button should open.

    The visible ticket button is a POST form to a ticketing system, which we
    can't turn into a plain link. But the JSON-LD offer carries a normal URL that
    opens this exact screening on the cinema's own site — good enough to hand the
    user off to the right place, which is all the app promises to do.
    """
    offers = data.get("offers") if data else None
    if isinstance(offers, dict) and offers.get("url"):
        return offers["url"]
    if isinstance(offers, list) and offers and isinstance(offers[0], dict):
        return offers[0].get("url", "")

    # Fall back to a per-screening link on the cinema's own domain, derived from
    # its program URL so this stays correct for every Aerofilms cinema.
    projection_id = _extract_source_id(row)
    if projection_id:
        parts = urlsplit(program_url)
        return f"{parts.scheme}://{parts.netloc}/?projection={projection_id}"
    return program_url


def _extract_source_id(row) -> str:
    """The cinema's own id for this screening, carried on elements as data-projection."""
    element = row.find(attrs={"data-projection": True})
    return element["data-projection"] if element else ""


def _friendly_note(classified: dict) -> str:
    """Last-resort human label when a screening has no strand and no format."""
    if classified["english_friendly"]:
        return "english friendly"
    if classified["language_version"]:
        return classified["language_version"]
    return ""


# --------------------------------------------------------------------------
# Day handling
# --------------------------------------------------------------------------

def _parse_day_date(day_block) -> str | None:
    """Turn the day anchor id 'program-day-21-07-2026' into '2026-07-21'."""
    anchor = day_block.find("a", class_="program__day")
    if not anchor or not anchor.get("id"):
        return None
    match = DAY_ID_RE.search(anchor["id"])
    if not match:
        return None
    day, month, year = match.groups()
    return f"{year}-{month}-{day}"


def _empty_dates(covered_dates: list[str], screenings: list[Screening]) -> list[str]:
    """
    Which of the covered days ended up with no screenings.

    Includes any gap days inside the covered range, so a day the site skips
    entirely still shows up as "nothing on" rather than vanishing.
    """
    if not covered_dates:
        return []

    with_screenings = {s.date for s in screenings}
    known = sorted(set(covered_dates))
    start = date_cls.fromisoformat(known[0])
    end = date_cls.fromisoformat(known[-1])

    empty = []
    current = start
    while current <= end:
        iso = current.isoformat()
        if iso not in with_screenings:
            empty.append(iso)
        current += timedelta(days=1)
    return empty
