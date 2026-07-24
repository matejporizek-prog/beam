"""
Scraper for Kino MAT (mat.cz/kino/).

Its own platform — checked before writing anything, same as every cinema
here (no JSON-LD, no program__ markup, no Swiper carousel — a fourth distinct
shape among the arthouse cinemas in this project). One page load carries an
unusually long window: dates ranging from today out to several months ahead
(a recurring classic-film series, published far in advance), so no
pagination is needed at all, just the same no-year-printed date problem as
Kino Pilotů and Edison Filmhub, solved the same way via the shared
`infer_years_for_months()`.

Per-screening markup:

    <div class='cinema121'>dnes<strong>24</strong>červenec</div>
    <div class='cinema122'>18.30</div>
    <div class='cinema124' data-definitionid='17570'>
      <strong>169 Kč</strong>
      <a href='https://shop.entradio.cz/event/...'>vstupenky</a>   (sometimes)
      <span class='pictospan'><img src='...' alt='35mm film' title='35mm film' /></span>  (sometimes)
    </div>
    <div class='cinema123'>
      <a href='/kino/cz/kino-mat?movie-id=8321_soukromy-zivot'>Soukromý život</a>
      Vie privée
    </div>

The Czech title and, when present, the film's original title are both in
`.cinema123` — the original title is loose text trailing the `<a>` tag, not
its own element. Genuinely useful data (it would help TMDb matching for a
translated title), but wiring a new hint into the resolver's matcher is a
different piece of work than adding a cinema — deliberately not captured here,
the same way a poster or detail-page fetch gets skipped elsewhere when the
payoff doesn't justify a scraper-only change.

Format is exposed as a pictogram image's `alt`/`title` text ("35mm film",
"Dolby Surround 7.1") rather than a text chip — a fourth distinct tag
mechanism among the cinemas scraped so far (JSON-LD chips, title-embedded
prefixes, `.desc` compact notation, and now an image attribute). Only the
35mm case maps to anything classify_tags() already recognises (its own
FORMAT_TAGS key is "35mm", not "35mm film"); anything else is passed through
as a tag and lands in `strand` by classify_tags()'s existing unknown-tag
default, so it's never silently lost even where it's imperfectly labelled.

What's deliberately not scraped: no cycle/strand is exposed inline per
screening on this page (the "Cykly" filter list only links to separately
browsable pages, one per series) — matching this project's running practice
of not scraping data that would need its own extra requests just to be
"complete"; the resolver doesn't need it.
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

CINEMA_NAME = "Kino MAT"
PROGRAM_URL = "https://www.mat.cz/kino/"

# Nominative case this time ("červenec", not Kino Pilotů's genitive
# "července") — this site's own date convention, checked against real markup.
CZECH_MONTHS_NOMINATIVE = {
    "leden": 1, "únor": 2, "březen": 3, "duben": 4,
    "květen": 5, "červen": 6, "červenec": 7, "srpen": 8,
    "září": 9, "říjen": 10, "listopad": 11, "prosinec": 12,
}


def scrape(html: str | None = None) -> dict:
    """
    Scrape Kino MAT's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(".cinema1")

    months = [_extract_month(row) for row in rows]
    years = infer_years_for_months(months)

    screenings: list[Screening] = []
    for row, month, year in zip(rows, months, years):
        screening = _parse_row(row, month, year)
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


# Longest name first: "červenec" (July) contains "červen" (June) as a literal
# prefix, and the digit+month text has no separator to anchor a word boundary
# on ("24červenec") — checking June before July as a plain substring silently
# misread every July screening as June. Sorting the candidates by length
# means the longer, more specific name always wins the match.
_MONTH_CANDIDATES = sorted(CZECH_MONTHS_NOMINATIVE.items(), key=lambda pair: -len(pair[0]))


def _extract_month(row) -> int | None:
    date_el = row.select_one(".cinema121")
    if not date_el:
        return None
    text = clean_text(date_el.get_text()).lower()
    for name, number in _MONTH_CANDIDATES:
        if name in text:
            return number
    return None


def _parse_row(row, month: int | None, year: int | None) -> Screening | None:
    if not month or not year:
        return None

    date_el = row.select_one(".cinema121")
    day_match = re.search(r"(\d{1,2})", date_el.get_text()) if date_el else None
    if not day_match:
        return None
    date_str = f"{year:04d}-{month:02d}-{int(day_match.group(1)):02d}"

    time_el = row.select_one(".cinema122")
    time_match = re.search(r"(\d{1,2})[.:](\d{2})", time_el.get_text()) if time_el else None
    if not time_match:
        return None
    time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    title_el = row.select_one(".cinema123 a")
    title = clean_text(title_el.get_text()) if title_el else ""
    if not title:
        return None

    price_el = row.select_one(".cinema124")
    booking_url = PROGRAM_URL
    raw_tags: list[str] = []
    format_tag = ""
    if price_el:
        ticket_link = price_el.select_one("a")
        if ticket_link and ticket_link.get("href"):
            booking_url = ticket_link["href"]
        for img in price_el.select("img[alt]"):
            picto_text = clean_text(img["alt"])
            if not picto_text:
                continue
            if "35mm" in picto_text.replace(" ", "").lower():
                format_tag = "35 mm"
            else:
                raw_tags.append(picto_text)

    classified = classify_tags(raw_tags)
    if format_tag:
        classified["format"] = format_tag

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=date_str,
        time=time_str,
        language="",
        format=classified["format"],
        note=classified["strand"] or classified["format"] or "",
        english_friendly=classified["english_friendly"],
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall="",
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director="",
        runtime_min=None,
        source_id=(title_el.get("href", "").rsplit("=", 1)[-1] if title_el else ""),
    )


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
