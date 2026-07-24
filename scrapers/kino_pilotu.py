"""
Scraper for Kino Pilotů (kinopilotu.cz).

A different platform from the Aerofilms cinemas — worth checking before writing
any code, and it was: no JSON-LD, no `program__` markup, no `data-projection`
ids. Instead the whole program lives on the homepage as a Swiper.js carousel:
one "day" slide per date, paired index-for-index with an "event" slide holding
that day's `<li>` screenings. Confirmed the pairing holds (day[i]'s date lines
up with event[i]'s films) before relying on it.

    <div class="swiper-slide day"><span><strong>Pátek</strong> 24. července</span></div>
    ...
    <div class="swiper-slide event">
      <li>
        <span class="program__content-wrap">
          <em>17:15</em>
          <strong><a href="/detail/112576"><span class="underline">Odyssea</span></a></strong>
        </span>
        <span class="program__sub">...</span>   (only ever seen holding a
        <span class="program__sub">...</span>    capacity notice, never a
                                                    real language/format tag)
      </li>
      ...
    </div>

The whole ~3-week window is pre-rendered in one page load — no per-day fetches
needed, unlike Aerofilms (which needs one request but paginates days inline
too, so this is actually simpler: a single GET covers everything).

What's deliberately NOT scraped here
-------------------------------------
There's no structured data for language, format, director, runtime or poster
on this page. A per-screening detail page (`/detail/<id>`) does exist and
carries a poster (`og:image`) and even a trailer embed — but fetching one extra
page per unique film just for a poster we'll usually get from TMDb anyway isn't
worth the added requests and failure surface. This follows the architecture
note in the planning doc directly: scrape schedule only, let TMDb resolution
carry the metadata. `director`, `runtime_min`, `poster_url`, `hall` and
`language` all stay empty for this cinema; nothing downstream requires them
(TMDb fills poster/runtime/director, and an empty `language` just means the
cinema-mode row shows one less detail, same graceful-degrade pattern used
everywhere else in this codebase).

The one tag ever seen in `program__sub` is a capacity notice ("Omezená
kapacita - doporučujeme rezervaci" — limited capacity, reservation
recommended), not a real strand/format/language signal. It still goes through
`classify_tags()` like any other cinema's tags — an unrecognised tag becomes a
strand, which is the correct, safe default and costs nothing if the site never
adds a real tag at all.

A genuinely new problem this site raised: Python's `apparent_encoding` guesser
misread this page's bytes as `iso8859_10` even though the site correctly
declares `charset=UTF-8` in its own headers — corrupting every accented
character on first fetch. Fixed at the source, in `base.fetch()`, to trust a
declared charset over a guess; see the comment there.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import (
    Screening,
    classify_tags,
    clean_text,
    empty_dates_in_range,
    fetch,
    infer_years_for_months,
)

CINEMA_NAME = "Kino Pilotů"
PROGRAM_URL = "https://kinopilotu.cz/"

# Czech month names in the genitive case, as this site writes dates:
# "24. července" (24 July), "01. srpna" (1 August). Day-of-week text
# ("Pátek", "Sobota", ...) appears alongside but isn't needed — the numeric
# day + month name alone is enough to build an ISO date.
CZECH_MONTHS_GENITIVE = {
    "ledna": 1, "února": 2, "března": 3, "dubna": 4,
    "května": 5, "června": 6, "července": 7, "srpna": 8,
    "září": 9, "října": 10, "listopadu": 11, "prosince": 12,
}

DATE_RE = re.compile(r"(\d{1,2})\.\s*(\w+)")
DETAIL_ID_RE = re.compile(r"/detail/(\d+)")

# This site bakes its programming strand directly into the title text as a
# colon-prefixed label ("Céčko: Leviticus", "Kino Seniorů: Michael") — unlike
# the Aerofilms cinemas, which expose it as a separate chip. Left alone, this
# would badly hurt TMDb matching in Milestone 2 ("Céčko: Leviticus" barely
# resembles "Leviticus"). A colon is NOT safe to strip on generally — real film
# titles legitimately contain one ("Blade Runner: 2049") — so only these
# specific, observed strand labels are recognised and split off; anything else
# stays part of the title, matching this codebase's preference for explicit
# known lists over a fragile heuristic (see NON_LANGUAGE_CODES in base.py for
# the same reasoning). The anniversary label is a pattern, not a fixed string,
# since "10 Let Kina Pilotů" becomes "11 Let..." next year.
KNOWN_TITLE_PREFIXES = [
    re.compile(r"^\d+\s+let\s+kina\s+pilotů$", re.IGNORECASE),
    re.compile(r"^céčko$", re.IGNORECASE),
    re.compile(r"^kino senior[uů]$", re.IGNORECASE),
    re.compile(r"^filmový\s+klub$", re.IGNORECASE),
]

# The suffix case is safer to generalise: unlike a colon, nothing in this
# cinema's real titles ever contains " / " or " + " — every observed instance
# is an event annotation ("/ Český dabing", "/ debata s...", "+ DEBATA S
# REŽISÉREM"), so splitting on the first one and classifying it as a tag is
# safe. "Český dabing" in particular is worth doing properly: classify_tags()
# already recognises it (via VERSION_TAGS) as a real language_version signal,
# not just a strand — feeding it through the same pipeline the Aerofilms
# cinemas use gets that for free.
TITLE_SUFFIX_RE = re.compile(r"\s+[/+]\s+")


def scrape(html: str | None = None) -> dict:
    """
    Scrape Kino Pilotů's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")

    day_slides = soup.select(".swiper-slide.day")
    event_slides = soup.select("#swiper-events .swiper-slide.event")
    day_dates = _dates_from_slides(day_slides)

    covered_dates: list[str] = []
    screenings: list[Screening] = []

    # The two carousels are parallel: day_slides[i]'s date is event_slides[i]'s
    # screenings. Confirmed against the live site before relying on it — if a
    # future redesign breaks that pairing, zip() just produces fewer matched
    # pairs rather than silently misassigning dates, and the day/event count
    # mismatch would be an obvious signal in a test failure.
    for day_date, event_slide in zip(day_dates, event_slides):
        if not day_date:
            continue
        covered_dates.append(day_date)

        for row in event_slide.find_all("li"):
            screening = _parse_row(row, day_date)
            if screening:
                screenings.append(screening)

    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))

    return {
        "cinema": CINEMA_NAME,
        "source_url": PROGRAM_URL,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, {s.date for s in screenings}),
        "screenings": [s.to_dict() for s in screenings],
    }


# --------------------------------------------------------------------------
# Day parsing
# --------------------------------------------------------------------------

def _dates_from_slides(day_slides) -> list[str | None]:
    """
    Turn every day slide's text ("Pátek 24. července") into an ISO date.

    No year is ever printed, so it's inferred via infer_years_for_months() in
    base.py — shared with Edison Filmhub, which has the exact same
    no-year-printed problem in a different date format. Deliberately built in
    two passes (extract day+month here, infer years as a separate pure
    function) rather than stateful per-call parsing — module-level mutable
    state would leak between scrape() calls in the same process, which is
    exactly how this scraper gets invoked (run.py calls every cinema in one
    process; so does a single pytest session).
    """
    days: list[int | None] = []
    months: list[int | None] = []

    for day_slide in day_slides:
        text = day_slide.get_text(" ", strip=True)
        match = DATE_RE.search(text)
        if not match:
            days.append(None)
            months.append(None)
            continue

        days.append(int(match.group(1)))
        months.append(CZECH_MONTHS_GENITIVE.get(match.group(2).lower()))

    years = infer_years_for_months(months)
    return [
        f"{year:04d}-{month:02d}-{day:02d}" if (year and month and day) else None
        for day, month, year in zip(days, months, years)
    ]


# --------------------------------------------------------------------------
# Row parsing
# --------------------------------------------------------------------------

def _split_title(raw_title: str) -> tuple[str, list[str]]:
    """
    Pull a strand prefix and/or an event-annotation suffix out of a raw title.

    "Céčko: Leviticus" -> ("Leviticus", ["Céčko"])
    "Šepot lesa / Český dabing" -> ("Šepot lesa", ["Český dabing"])

    Returns the cleaned title plus any fragments found, to be classified as
    tags exactly like an Aerofilms cinema's chips — so "Český dabing" still
    ends up as a real language_version, not just inert strand text.
    """
    title = raw_title
    tags: list[str] = []

    if ":" in title:
        prefix, _, rest = title.partition(":")
        if any(pattern.match(prefix.strip()) for pattern in KNOWN_TITLE_PREFIXES):
            tags.append(prefix.strip())
            title = rest.strip()

    match = TITLE_SUFFIX_RE.search(title)
    if match:
        tags.append(title[match.end():].strip())
        title = title[:match.start()].strip()

    return title, tags


def _parse_row(row, day_date: str) -> Screening | None:
    """Build one Screening from one <li> screening entry."""

    time_el = row.find("em")
    time_text = clean_text(time_el.get_text()) if time_el else ""
    match = re.search(r"(\d{1,2})[:.](\d{2})", time_text)
    if not match:
        return None
    time_str = f"{int(match.group(1)):02d}:{match.group(2)}"

    link = row.find("a", href=DETAIL_ID_RE)
    title_el = link.find("span", class_="underline") if link else None
    raw_title = clean_text(title_el.get_text()) if title_el else (
        clean_text(row.find("strong").get_text()) if row.find("strong") else ""
    )
    if not raw_title:
        return None

    title, title_tags = _split_title(raw_title)

    raw_tags = list(title_tags)
    raw_tags += [tag.get_text() for tag in row.find_all("span", class_="program__sub")]
    kids_el = row.find("span", class_="program__kids")
    if kids_el and clean_text(kids_el.get_text()):
        raw_tags.append(kids_el.get_text())
    classified = classify_tags(raw_tags)

    source_id = ""
    booking_url = PROGRAM_URL
    if link and link.get("href"):
        id_match = DETAIL_ID_RE.search(link["href"])
        if id_match:
            source_id = id_match.group(1)
        booking_url = urljoin(PROGRAM_URL, link["href"])

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=day_date,
        time=time_str,
        # No structured language/director/runtime/poster on this site — see
        # the module docstring for why that's a deliberate choice, not a gap.
        language="",
        format=classified["format"],
        note=classified["strand"] or classified["format"] or _friendly_note(classified),
        english_friendly=classified["english_friendly"],
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall="",
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director="",
        runtime_min=None,
        source_id=source_id,
    )


def _friendly_note(classified: dict) -> str:
    if classified["english_friendly"]:
        return "english friendly"
    if classified["language_version"]:
        return classified["language_version"]
    return ""


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
