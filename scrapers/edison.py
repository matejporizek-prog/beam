"""
Scraper for Edison Filmhub (edisonfilmhub.cz).

A third distinct platform (not Aerofilms, not the Kino Pilotů Swiper carousel)
— checked structurally before writing anything, same as every cinema here. No
JSON-LD, but a genuinely rich, cleanly server-rendered program table:

    <div class="line"><div class="den">Pátek 24.7.</div></div>   (day header)
    <div class="line">                                            (one screening)
      <div class="time">19.00</div>
      <div class="name"><a href="/filmy/carodejky">Čarodějky</a></div>
      <div class="event">
        <a href="/akce/festivaly">Festivaly</a><br>
        <a href="/akce/festivaly/heatwave-horror">Heatwave Horror</a>
      </div>
      <div class="desc">EN, Tit. CZ<br>+ úvod Ryan Keating</div>
      <div class="event event_mobile"><a href="/akce/festivaly">Festivaly</a></div>
      <a target="_blank" class="ticket"><div class="btn">200 Kč</div></a>
    </div>

`.event` carries TWO tags per screening — a broad category ("Festivaly") and,
when the screening belongs to one, a specific named series ("Heatwave
Horror"). `.event.event_mobile` duplicates just the category for a narrower
viewport and is deliberately skipped, or every screening would double-count
its own category tag.

The real find: `.desc`'s first line is a compact language notation this site
uses consistently — "EN, Tit. CZ" (English, Czech subtitles), "JPN, Tit. CZ,
EN" (Japanese, Czech AND English subtitles — a real english_friendly signal
from the subtitle language, not just the spoken one), or just "CZ" alone (Czech
original, nothing to add). `_parse_desc()` turns this into real `language`,
`english_friendly` and `language_version` fields — more structured data than
any Aerofilms cinema's `english_friendly` chip alone gives. Anything after the
first line — a Q&A guest's name, "+ úvod" (introduction), a repeated
"Premiéry"/"Předpremiéra" marker, a festival cross-reference — is free text
with no fixed vocabulary, so it's fed through classify_tags() and lands in
`strand` like any other cinema's unrecognised tag.

Some of this site's language codes aren't the ISO ones scrapers/base.py
already knows (`DNK` for Danish instead of `da`, `JPN`/`JAP` for Japanese
instead of `ja`, `FIN` for Finnish instead of `fi`, `SWE`/`HUN`/`ISL` instead of
`sv`/`hu`/`is`). `EDISON_LANGUAGE_ALIASES` translates them to the standard
codes before handing off to the shared `language_name()`, kept local to this
file rather than added to base.py's table — it's this site's own quirky
abbreviation choice, not a general one.

Two structural quirks worth knowing, both handled gracefully rather than
specially:
  - "Double Feature: X" rows (the same kind of event Bio Oko and Kino Pilotů
    also show) have no `.event` block at all, and their `.desc` mixes two
    films' language info together with " / ". Both are read defensively — an
    absent `.event` just means no strand tags, and the messy combined `.desc`
    still yields *some* language text rather than crashing. These titles will
    correctly stay unresolved at the TMDb-matching stage regardless, the same
    as the other cinemas' double-feature events.
  - Most `<a class="ticket">` elements carry no `href` at all (the purchase
    flow is presumably JS-driven); a genuine few link straight to a GoOut
    ticket page. `booking_url` prefers a real ticket href when present,
    falling back to the film's own `/filmy/<slug>` page — actual coverage
    beats every other cinema in this project on the days it's there.

Day headers ("Pátek 24.7.") carry no year, same problem as Kino Pilotů in a
different format — day and month are already plain digits here, so no
Czech-month-name lookup is needed, but the year still has to be inferred via
the shared `infer_years_for_months()` in base.py.
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
    language_name,
)

CINEMA_NAME = "Edison Filmhub"
PROGRAM_URL = "https://edisonfilmhub.cz/program/"

DAY_HEADER_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.")

# This site's own language abbreviations that don't match the ISO codes
# scrapers/base.py's LANGUAGE_NAMES already knows. Kept local: it's Edison's
# quirk, not a general one worth adding to the shared table.
EDISON_LANGUAGE_ALIASES = {
    "dnk": "da", "jpn": "ja", "jap": "ja", "fin": "fi",
    "swe": "sv", "hun": "hu", "isl": "is",
}


def scrape(html: str | None = None) -> dict:
    """
    Scrape Edison Filmhub's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(".program_table .line")

    day_headers = [row.select_one(".den") for row in rows]
    months = [
        int(DAY_HEADER_RE.search(h.get_text(strip=True)).group(2))
        if h and DAY_HEADER_RE.search(h.get_text(strip=True)) else None
        for h in day_headers
    ]
    years = infer_years_for_months(months)

    covered_dates: list[str] = []
    screenings: list[Screening] = []
    current_date: str | None = None

    for row, month, year in zip(rows, months, years):
        den = row.select_one(".den")
        if den:
            match = DAY_HEADER_RE.search(den.get_text(strip=True))
            if match and month and year:
                day = int(match.group(1))
                current_date = f"{year:04d}-{month:02d}-{day:02d}"
                covered_dates.append(current_date)
            else:
                current_date = None
            continue

        if not current_date:
            continue  # a screening row before any day header ever parsed

        screening = _parse_row(row, current_date)
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
# Row parsing
# --------------------------------------------------------------------------

def _parse_row(row, day_date: str) -> Screening | None:
    """Build one Screening from one screening `.line` element."""

    time_el = row.select_one(".time")
    time_text = clean_text(time_el.get_text()) if time_el else ""
    match = re.search(r"(\d{1,2})[.:](\d{2})", time_text)
    if not match:
        return None
    time_str = f"{int(match.group(1)):02d}:{match.group(2)}"

    name_link = row.select_one(".name a")
    raw_title = clean_text(name_link.get_text()) if name_link else ""
    if not raw_title:
        return None
    title, dabing_tag = _strip_dabing_suffix(raw_title)
    title = _strip_year_suffix(title)

    # .event carries up to two tags: a category and an optional named series.
    # .event_mobile duplicates the category for narrow viewports — skipped, or
    # every screening's category would be counted (and shown) twice.
    event_el = row.select_one(".event:not(.event_mobile)")
    event_tags = [
        clean_text(a.get_text()) for a in (event_el.select("a") if event_el else [])
        if clean_text(a.get_text())
    ]

    desc_el = row.select_one(".desc")
    language, english_friendly, language_version, note_tags = _parse_desc(desc_el)

    raw_tags = event_tags + note_tags + dabing_tag
    classified = classify_tags(raw_tags)
    # classify_tags() would only set english_friendly from an "ENG"-style chip,
    # which this site never uses — the real signal is in .desc's language
    # notation, already extracted above.
    is_english_friendly = classified["english_friendly"] or english_friendly

    booking_url = _extract_booking_url(row)

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=day_date,
        time=time_str,
        language=language,
        format=classified["format"],
        note=classified["strand"] or classified["format"] or "",
        english_friendly=is_english_friendly,
        language_version=language_version or classified["language_version"],
        strand=classified["strand"],
        hall="",
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director="",
        runtime_min=None,
        source_id="",
    )


DABING_SUFFIX_RE = re.compile(r"\s*\(([^)]*dabing[^)]*)\)\s*$", re.IGNORECASE)


def _strip_dabing_suffix(raw_title: str) -> tuple[str, list[str]]:
    """
    "Toy Story 5: Příběh hraček (CZ DABING)" -> ("Toy Story 5: Příběh hraček", ["CZ DABING"])

    Found via a real title in this cinema's own listing: this exact film is
    already a known, correctly-resolved match from other cinemas (as plain
    "Toy Story 5: Příběh hraček"), so leaving the suffix in would both cost a
    duplicate, harder-scoring TMDb search AND throw away a real dubbing
    signal. Deliberately narrow — only a parenthetical actually containing
    "dabing" is touched, not every trailing "(...)" (a same-fixture example,
    "Posedlost (2026)", is a harmless year disambiguation and is left alone;
    stripping it would gain nothing and risks being wrong about what a
    "(...)" suffix means in general).
    """
    match = DABING_SUFFIX_RE.search(raw_title)
    if not match:
        return raw_title, []
    return raw_title[:match.start()].strip(), [match.group(1)]


YEAR_SUFFIX_RE = re.compile(r"\s*\((?:19|20)\d{2}\)\s*$")


def _strip_year_suffix(title: str) -> str:
    """
    "Posedlost (2026)" -> "Posedlost"

    Found via a real resolution failure: "Posedlost" is already a known,
    correctly-resolved film from other cinemas, but TMDb's own search API
    returns zero results for the literal query "Posedlost (2026)" — not a
    fuzzy-matching nuisance, a hard failure before the matcher ever gets a
    candidate to score. A bare trailing year is Edison's own disambiguation
    for generic-sounding titles, never part of a film's actual official
    title, so it's safe to strip unconditionally — unlike the dabing suffix,
    there's no real signal here worth keeping as a tag.
    """
    return YEAR_SUFFIX_RE.sub("", title).strip()


def _parse_desc(desc_el) -> tuple[str, bool, str, list[str]]:
    """
    Split `.desc` into (language, english_friendly, language_version, note_tags).

    The first line is this site's compact language notation: "EN, Tit. CZ"
    (English, Czech subtitles), "JPN, Tit. CZ, EN" (Japanese, Czech AND
    English subtitles), or just "CZ" alone. Everything after the first line —
    a Q&A guest, "+ úvod", a repeated strand marker — is free text with no
    fixed vocabulary, returned as note_tags for classify_tags() to bucket.
    """
    if not desc_el:
        return "", False, "", []

    # <br> becomes a literal separator so lines don't run together.
    for br in desc_el.find_all("br"):
        br.replace_with("\n")
    lines = [clean_text(line) for line in desc_el.get_text("\n").split("\n")]
    lines = [line for line in lines if line]

    if not lines:
        return "", False, "", []

    spoken_part, _, subtitle_part = lines[0].partition("Tit.")
    spoken = _split_codes(spoken_part)
    subtitles = _split_codes(subtitle_part)

    all_codes = spoken + subtitles
    english_friendly = "en" in all_codes

    spoken_names = [_edison_language_name(code) for code in spoken]
    language = ", ".join(dict.fromkeys(n for n in spoken_names if n))  # de-dup, keep order

    # "Subtitled foreign film" reads as titulky here; a Czech original with no
    # subtitle note, or an English screening with no subtitle note at all
    # (seen on this site — presumably shown fully OV), correctly stay empty.
    language_version = "titulky" if subtitles and "cz" not in spoken and "cs" not in spoken else ""

    return language, english_friendly, language_version, lines[1:]


def _split_codes(text: str) -> list[str]:
    """'EN, DE' -> ['en', 'de']. Handles the odd '/'-joined double-feature blob too."""
    parts = re.split(r"[,/]", text)
    return [p.strip().lower() for p in parts if p.strip()]


def _edison_language_name(code: str) -> str:
    return language_name(EDISON_LANGUAGE_ALIASES.get(code, code))


def _extract_booking_url(row) -> str:
    """
    Prefer a real ticket link when this screening has one (a genuine few link
    straight to a GoOut purchase page); otherwise fall back to the film's own
    page, then the program page — the same "best available link" pattern
    every cinema here uses when there's no direct per-screening purchase URL.
    """
    ticket = row.select_one("a.ticket")
    if ticket and ticket.get("href"):
        return ticket["href"]

    name_link = row.select_one(".name a")
    if name_link and name_link.get("href"):
        return urljoin(PROGRAM_URL, name_link["href"])

    return PROGRAM_URL


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
