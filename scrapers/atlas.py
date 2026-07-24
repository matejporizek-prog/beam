"""
Scraper for Kino Atlas (kinoatlaspraha.cz).

A genuinely different shape of problem from every cinema before it: only
*today's* screenings are in the plain HTML page load (a "highlight" section).
Everything after today loads via a paginated AJAX endpoint the page's own JS
calls when you click "Zobrazit další" (show more):

    GET /ajax_get_program.php?date=<last screening's timestamp>&lang=cz&tag=&location=&searchtext=

Found by reading the page's own inline JS, then verified directly with
`requests` before writing any parsing code — it's a plain GET returning an
HTML fragment, no browser/JS execution needed. Passing the *last* screening's
own `data-program-date` as the next `date` param continues where the previous
batch left off; the response's `<div class="variables" data-next-cnt="0" ...>`
is the real "nothing more to fetch" signal (checked by walking it to
exhaustion: the count hits 0 exactly on the last batch that still has data,
never one batch early or late).

Both the highlight section and every AJAX batch use the same inner row
markup — time, hall, title, tags, a real ticket link — so one row-parser
handles both. The two differences:

    - The highlight section's `.line` also carries a `.subtitle` div with
      "Director / Country, Country / Year" — real verification signal, but
      only for today. Every other day has no director at all here.
    - The outer `.line` on a highlight row carries its own `data-program-date`;
      an AJAX batch row doesn't. The `.buy` ticket link's own
      `data-program-date` is present on *both*, so that's what's actually used
      as the timestamp source — one reliable field instead of two
      inconsistent ones.

Real, direct GoOut ticket links on every single screening — the best coverage
of any cinema in this project. No runtime is published anywhere on the site
(checked); TMDb covers it as usual.

Tags come in three CSS classes, found by inspecting real markup rather than
guessing: `tag cyklus` (a themed series — "Atlas hororu", "Atlas klasiky"),
`tag simple` (an event-type label — "CZ/SK film", "Novinka"), and `tag
language` (English-friendly specifically, `title="English friendly"`, shown
as "EN") — a clean, unambiguous signal, so it's read directly rather than
inferred from classify_tags()'s "ENG"-string heuristic.
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
)

CINEMA_NAME = "Kino Atlas"
PROGRAM_URL = "https://www.kinoatlaspraha.cz"
AJAX_URL = "https://www.kinoatlaspraha.cz/ajax_get_program.php"

# Safety cap on pagination rounds — the real stopping signal is
# data-next-cnt="0", this just guards against an unexpected infinite loop if
# the site's markup ever changes underneath us.
MAX_PAGES = 20


def scrape(homepage_html: str | None = None, ajax_batches: list[str] | None = None) -> dict:
    """
    Scrape Kino Atlas's program.

    Pass `homepage_html` (and optionally `ajax_batches`, a list of canned AJAX
    fragment responses) to parse saved pages — used by the tests. Leave both
    out to fetch the live site, which walks the real pagination until the
    site itself reports there's nothing more.
    """
    if homepage_html is None:
        homepage_html = fetch(PROGRAM_URL)

    screenings: list[Screening] = []
    screenings.extend(_parse_rows(BeautifulSoup(homepage_html, "lxml")))

    if ajax_batches is not None:
        for batch_html in ajax_batches:
            screenings.extend(_parse_rows(BeautifulSoup(batch_html, "lxml")))
    else:
        screenings.extend(_fetch_remaining_pages(screenings))

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


def _fetch_remaining_pages(seen_so_far: list[Screening]) -> list[Screening]:
    """Walk the live AJAX pagination forward until the site reports nothing more."""
    if not seen_so_far:
        return []

    cursor = max(f"{s.date} {s.time}:00" for s in seen_so_far)
    collected: list[Screening] = []

    for _ in range(MAX_PAGES):
        html = fetch(f"{AJAX_URL}?date={cursor}&lang=cz&tag=&location=&searchtext=")
        soup = BeautifulSoup(html, "lxml")
        batch = _parse_rows(soup)
        collected.extend(batch)

        next_cnt_match = re.search(r'data-next-cnt="(\d+)"', html)
        if not batch or (next_cnt_match and next_cnt_match.group(1) == "0"):
            break

        cursor = max(f"{s.date} {s.time}:00" for s in batch)

    return collected


# --------------------------------------------------------------------------
# Row parsing — shared by the highlight section and every AJAX batch
# --------------------------------------------------------------------------

TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}")


def _parse_rows(soup: BeautifulSoup) -> list[Screening]:
    return [s for row in soup.select("div.line") if (s := _parse_row(row)) is not None]


def _parse_row(row) -> Screening | None:
    # The .buy ticket link's own timestamp is present on every row in both the
    # highlight section and AJAX batches — more reliable than the outer .line
    # div's data-program-date, which only the highlight section carries.
    buy = row.select_one("a.buy")
    timestamp = buy.get("data-program-date", "") if buy else ""
    match = TIMESTAMP_RE.match(timestamp)
    if not match:
        return None
    date_str, time_str = match.groups()

    title_link = row.select_one(".title a")
    title = clean_text(title_link.get_text()) if title_link else ""
    if not title:
        return None

    hall = clean_text(row.select_one(".location").get_text()) if row.select_one(".location") else ""

    # Three tag classes, each meaning something different — see module
    # docstring. `tag language` is unambiguous (its title is literally
    # "English friendly"), so it's read directly rather than routed through
    # classify_tags()'s text-guessing.
    strand_or_type_tags = [
        clean_text(t.get_text()) for t in row.select(".tags .tag.cyklus, .tags .tag.simple")
    ]
    english_friendly = bool(row.select_one(".tags .tag.language"))
    classified = classify_tags(strand_or_type_tags)

    director = ""
    subtitle = row.select_one(".subtitle")
    if subtitle:
        # "Ivan Ostrochovský / Slovensko, Česko, Maďarsko / 2026" — only
        # present on today's highlight rows; every other day has none.
        director = clean_text(subtitle.get_text()).split("/")[0].strip()

    booking_url = buy["href"] if buy and buy.get("href") else PROGRAM_URL

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=date_str,
        time=time_str,
        language="",  # no structured spoken-language field on this site
        format=classified["format"],
        note=classified["strand"] or classified["format"] or "",
        english_friendly=english_friendly or classified["english_friendly"],
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall=hall,
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director=director,
        runtime_min=None,  # not published anywhere on this site
        source_id=(row.get("id", "") or "").replace("program-id-", ""),
    )


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
