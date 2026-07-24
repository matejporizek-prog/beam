"""
Scraper for Kino Kavalírka (kinokavalirka.cz).

Its own platform — an accordion, each `.accordion-item` one screening. The
richest per-screening data of any cinema in this project: full synopsis,
country/year/runtime/director all in one line, an explicit English-friendly
explanation ("ENGLISH FRIENDLY (language: English, subtitles: Czech)"), a
real ticket-purchase link, and — for some films — a direct link to the film's
IMDb page. That IMDb link is genuinely the strongest signal any cinema here
gives (TMDb supports an exact lookup by IMDb id, unlike every other hint in
this project which still needs fuzzy title matching); it's captured on the
Screening record (`imdb_url`) but not yet consumed anywhere in resolve/ —
using it is a resolver change, worth doing as its own focused piece rather
than folded into "add a cinema".

The metadata line — "Velká Británie / USA, 2022, 96 min, r. Charlotte Wells,
v originálním znění s českými titulky" — isn't its own element; it's part of
one big paragraph of prose that also contains the synopsis, an age rating,
and a box-office note, all joined by literal `<br>` line breaks. `_parse_meta()`
regexes it out rather than relying on any DOM structure, since none exists
for it specifically. Not every screening has one — a themed "Film & Drink"
pairing's whole paragraph is about the drink menu instead, so the regex
simply not matching is the normal, expected outcome for those, not a bug.

That "Film & Drink:" family is this cinema's own version of the same problem
Kino Pilotů had: the venue bakes a themed-event label into the title text
itself ("Film & Drink: Pulp Fiction", "Divadlo v kině: Romeo a Julie",
"předpremiéra: Kino Punti a kapybary"). Left alone, "Film & Drink: Pulp
Fiction" would score far worse against "Pulp Fiction" than the clean title
does. Same fix as Kino Pilotů: a small set of known, explicit prefix patterns
recognised and split into a tag — never a bare "split on any colon", since a
prefix that generic would also eat a real title's own colon.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base import (
    Screening,
    classify_tags,
    clean_text,
    empty_dates_in_range,
    fetch,
    infer_years_for_months,
)

CINEMA_NAME = "Kino Kavalírka"
PROGRAM_URL = "https://www.kinokavalirka.cz/cs/uvod"

DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.")

# Known, explicit event-label prefixes — see module docstring for why a
# general "any colon" rule is unsafe here (a real title can legitimately
# contain one, e.g. an actual film titled with a subtitle).
KNOWN_TITLE_PREFIXES = [
    re.compile(r"^film\s*&\s*\w+:\s*", re.IGNORECASE),   # "Film & Drink:", "Film & Brunch:", ...
    re.compile(r"^divadlo\s+v\s+kině:\s*", re.IGNORECASE),
    re.compile(r"^galerie\s+v\s+kině:\s*", re.IGNORECASE),
    re.compile(r"^předpremiéra:\s*", re.IGNORECASE),
]

# "Velká Británie / USA, 2022, 96 min, r. Charlotte Wells, ..." — countries
# (slash-joined), year, runtime ("min" or "minut"), director. Everything after
# the director's name is further free text (subtitle/language info) and isn't
# captured here.
META_RE = re.compile(
    r"(?P<countries>[^,]+),\s*(?P<year>\d{4}),\s*(?P<runtime>\d+)\s*min\w*,\s*r\.\s*(?P<director>[^,]+),"
)


def scrape(html: str | None = None) -> dict:
    """
    Scrape Kino Kavalírka's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")
    items = soup.select(".accordion-item.page__program-item")

    months = [_extract_month(item) for item in items]
    years = infer_years_for_months(months)

    screenings: list[Screening] = []
    for item, month, year in zip(items, months, years):
        screening = _parse_item(item, month, year)
        if screening:
            screenings.append(screening)

    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))
    covered_dates = sorted({s.date for s in screenings})

    return {
        "cinema": CINEMA_NAME,
        "source_url": PROGRAM_URL,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, {s.date for s in screenings}),
        "screenings": [s.to_dict() for s in screenings],
    }


def _extract_month(item) -> int | None:
    term = item.select_one(".page__program-term")
    if not term:
        return None
    match = DATE_RE.search(clean_text(term.get_text()))
    return int(match.group(2)) if match else None


def _split_title(raw_title: str) -> tuple[str, list[str]]:
    """"Film & Drink: Pulp Fiction" -> ("Pulp Fiction", ["Film & Drink"])."""
    for pattern in KNOWN_TITLE_PREFIXES:
        match = pattern.match(raw_title)
        if match:
            prefix_label = raw_title[:match.end()].rstrip(": ").strip()
            return raw_title[match.end():].strip(), [prefix_label]
    return raw_title, []


def _parse_item(item, month: int | None, year: int | None) -> Screening | None:
    if not month or not year:
        return None

    term = item.select_one(".page__program-term")
    day_match = DATE_RE.search(clean_text(term.get_text())) if term else None
    if not day_match:
        return None
    date_str = f"{year:04d}-{month:02d}-{int(day_match.group(1)):02d}"

    hours = item.select_one(".page__program-hours")
    time_match = re.search(r"(\d{1,2}):(\d{2})", hours.get_text()) if hours else None
    if not time_match:
        return None
    time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    name_el = item.select_one(".page__program-name")
    raw_title = clean_text(name_el.get_text()) if name_el else ""
    if not raw_title:
        return None
    title, prefix_tags = _split_title(raw_title)

    chip_tags = [clean_text(t.get_text()) for t in item.select(".page__program-tag")]
    classified = classify_tags(chip_tags + prefix_tags)

    text_div = item.select_one(".text")
    full_text = clean_text(text_div.get_text(" ")) if text_div else ""
    meta = META_RE.search(full_text)
    director = clean_text(meta.group("director")) if meta else ""
    runtime = int(meta.group("runtime")) if meta else None

    # The explicit english-friendly explanation, e.g.
    # "ENGLISH FRIENDLY (language: English, subtitles: Czech)". More specific
    # than the chip tag alone (which only ever says "English Friendly" with no
    # detail), but the chip is what actually drives the boolean signal; this
    # is read only so the explanation text itself isn't silently discarded —
    # a screening description already told us whether it's English-friendly.
    english_friendly = classified["english_friendly"] or "english friendly" in full_text.lower()

    ticket_link = item.select_one("a.btn[href*='/koupit/']")
    booking_url = PROGRAM_URL
    if ticket_link and ticket_link.get("href"):
        href = ticket_link["href"]
        booking_url = href if href.startswith("http") else f"https://www.kinokavalirka.cz{href}"

    imdb_link = item.select_one("a[href*='imdb.com']")
    imdb_url = imdb_link["href"] if imdb_link and imdb_link.get("href") else ""

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=date_str,
        time=time_str,
        language="",
        format=classified["format"],
        note=classified["strand"] or classified["format"] or "",
        english_friendly=english_friendly,
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall="",
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director=director,
        runtime_min=runtime,
        source_id="",
        imdb_url=imdb_url,
    )


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
