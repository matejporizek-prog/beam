"""
Scraper for Divadlo Za plotem (divadlo.bohnice.cz) — the cinema/theatre of
Prague's Bohnice psychiatric hospital, also open to the public.

A WordPress site built with the GenerateBlocks page-builder plugin, not a
purpose-built cinema platform — a fifth distinct shape among the cinemas in
this project. There's no clean "one container per screening" element the way
every other site has; a page builder like this just emits a flat sequence of
generic blocks. What actually makes it parseable is that GenerateBlocks
stamps each block with a semantic (if invalidly repeated) `id`:

    <h2 id="datum">úterý 28. 7.</h2>
    <h2 id="název-filmu">TOY STORY 5: PŘÍBĚH HRAČEK</h2>
    <p>(synopsis)</p>
    <p>USA 2025 – přístupný – 102 min.</p>
    <div id="vstupenka"><a href="https://www.webticket.cz/akce/81616">KOUPIT VSTUPENKU</a></div>
    <span id="kino">kino junior</span>
    <span id="čas">14:00</span>
    <span id="cena">170 / 150</span>
    <span id="zvuk">CZ DAB</span>

`id="datum"` etc. repeats once per screening (checked: exactly 6 of each for
6 screenings, never more or fewer) — genuinely invalid HTML, since ids must
be unique, but reliable to select by anyway with `find_all(id=...)` and zip
together in document order. Low volume (a handful of screenings at a time),
but a real ticket-purchase link (webticket.cz) on every single one, plus
country/age-rating/runtime bundled into one small prose line.

This venue's own titles are all ALL CAPS ("TOY STORY 5: PŘÍBĚH HRAČEK") — its
own headline styling, not touched here. Checked rather than assumed: the
resolver's existing "most common spelling wins" canonicalisation
(unique_titles() in resolve/films.py) already fixes this for free whenever
the same film also plays at another cinema with normal casing — Toy Story 5
and Spider-Man both do, in this fixture. Only a title unique to this venue
would still display ALL CAPS in the app; a narrower, lower-priority residual
case than speculative Czech title-casing logic would be worth building.

`.page__program-tag`-style clean tags don't exist here; the closest thing is
`id="zvuk"` ("sound"), whose only observed values are "CZ" (original) and "CZ
DAB" (dubbed). "DAB" is a third, even-shorter abbreviation for dabing beyond
the ones already generalised in classify_tags() ("Dabing", "Český dabing",
"CZ DABING") — but "dab" alone is too short and common a substring to add to
that *global* rule safely (unlike "dabing", which essentially never appears
by coincidence). So it's matched only as an exact whole token, locally, in
this cinema's own module — the same "site-specific quirk stays in that
site's file" pattern already used for Kino Pilotů's title prefixes and MAT's
pictogram-based formats.
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

CINEMA_NAME = "Divadlo Za plotem"
PROGRAM_URL = "https://divadlo.bohnice.cz/"

DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.")
META_RE = re.compile(
    r"(?P<country>[^\d]+?)\s*(?P<year>\d{4})\s*.\s*(?P<agerating>[^.]+?)\s*.\s*(?P<runtime>\d+)\s*min",
    re.UNICODE,
)


def scrape(html: str | None = None) -> dict:
    """
    Scrape Divadlo Za plotem's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")

    dates = soup.find_all(id="datum")
    titles = soup.find_all(id="název-filmu")  # "název-filmu"
    tickets = soup.find_all(id="vstupenka")
    halls = soup.find_all(id="kino")
    times = soup.find_all(id="čas")  # "čas"
    sounds = soup.find_all(id="zvuk")
    metas = soup.select("p.has-text-align-left.wp-block-paragraph")

    months = [_extract_month(d) for d in dates]
    years = infer_years_for_months(months)

    screenings: list[Screening] = []
    rows = zip(dates, titles, tickets, halls, times, sounds, months, years)
    for i, (date_el, title_el, ticket_el, hall_el, time_el, sound_el, month, year) in enumerate(rows):
        meta_el = metas[i] if i < len(metas) else None
        screening = _build_screening(
            date_el, title_el, ticket_el, hall_el, time_el, sound_el, meta_el, month, year
        )
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


def _extract_month(date_el) -> int | None:
    match = DATE_RE.search(clean_text(date_el.get_text())) if date_el else None
    return int(match.group(2)) if match else None


def _build_screening(date_el, title_el, ticket_el, hall_el, time_el, sound_el, meta_el, month, year) -> Screening | None:
    if not month or not year:
        return None

    day_match = DATE_RE.search(clean_text(date_el.get_text()))
    if not day_match:
        return None
    date_str = f"{year:04d}-{month:02d}-{int(day_match.group(1)):02d}"

    time_match = re.search(r"(\d{1,2}):(\d{2})", time_el.get_text()) if time_el else None
    if not time_match:
        return None
    time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    title = clean_text(title_el.get_text()) if title_el else ""
    if not title:
        return None

    hall = clean_text(hall_el.get_text()) if hall_el else ""

    sound_text = clean_text(sound_el.get_text()) if sound_el else ""
    # Only an exact whole-token "DAB" — never a bare substring check, which
    # would risk matching unrelated text. See module docstring.
    is_dubbed = "dab" in [tok.lower() for tok in sound_text.split()]

    runtime = None
    if meta_el:
        meta_match = META_RE.search(clean_text(meta_el.get_text()))
        if meta_match:
            runtime = int(meta_match.group("runtime"))

    classified = classify_tags([])  # no free-text tags on this site beyond "zvuk"
    if is_dubbed:
        classified["language_version"] = "dabing"

    booking_url = PROGRAM_URL
    if ticket_el:
        link = ticket_el.find("a")
        if link and link.get("href"):
            booking_url = link["href"]

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=date_str,
        time=time_str,
        language="",
        format="",
        note=classified["language_version"],
        english_friendly=False,
        language_version=classified["language_version"],
        strand="",
        hall=hall,
        tags=[],
        booking_url=booking_url,
        poster_url="",
        director="",
        runtime_min=runtime,
        source_id="",
    )


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
