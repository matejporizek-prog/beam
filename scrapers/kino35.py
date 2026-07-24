"""
Scraper for Kino 35 (kino35.ifp.cz) — the cinema of the French Institute in
Prague (Institut français de Prague).

A sixth distinct platform shape: a single flat `<table class="prog-list">`
where date headers (`<tr class="header">`) and screening rows (plain `<tr>`)
alternate directly, with no per-day wrapper container — so a screening's date
comes from whichever header row most recently preceded it, tracked while
walking the table in document order.

Confirmed the whole calendar is on the page in one request: no "next month"
arrows or AJAX the way Kino Atlas needs. The venue is between seasons in this
fixture (a stated summer recess, screenings resuming September), so the
static page load only holds three dates spanning August–October — that's the
complete list, not a truncated one.

The recess itself rides in the table as a fake row: `"4.7. - 16.8. KINO MÁ
PRÁZDNINY"` with an empty `td.time`. An empty time means it isn't a real
screening — just a notice — so it's filtered out rather than parsed.

Per-screening detail comes from small icons with a `title` attribute rather
than free-text tags:
    .ico-favorite  title="Speciální večer" (no visible text — a flag)
    .ico-sound     title="Jazyk audia: ..."    text "CS", "IT", ... — spoken language
    .ico-sub       title="Jazyk titulků: ..."  text "FR, EN", ... — subtitle languages
"Speciální večer" is fed through the shared classify_tags() like any other
cinema's raw tag list, landing in `strand` (it isn't a format/dabing/titulky
match). `english_friendly` is true when "EN" appears among the subtitle
codes or as the spoken language — some screenings (the Alice Guy shorts
programme, presumably silent) carry only a subtitle icon and no sound icon
at all, so subtitles alone must be enough to count.

A real, screening-specific ticket link (koupitvstupenku.cz) on every actual
screening.
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
    language_name,
)

CINEMA_NAME = "Kino 35"
PROGRAM_URL = "https://kino35.ifp.cz/program/"

HEADER_DATE_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.")
TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")


def scrape(html: str | None = None) -> dict:
    """
    Scrape Kino 35's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")
    rows = soup.select("table.prog-list > tr")

    # Walk the flat table once, pairing each screening row with whichever
    # header most recently preceded it.
    entries: list[tuple[int | None, int | None, object]] = []
    current_day: int | None = None
    current_month: int | None = None
    for row in rows:
        if "header" in (row.get("class") or []):
            match = HEADER_DATE_RE.search(clean_text(row.get_text()))
            current_day = int(match.group(1)) if match else None
            current_month = int(match.group(2)) if match else None
            continue
        entries.append((current_day, current_month, row))

    years = infer_years_for_months([month for _, month, _ in entries])

    screenings: list[Screening] = []
    for (day, month, row), year in zip(entries, years):
        screening = _build_screening(row, day, month, year)
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


def _build_screening(row, day: int | None, month: int | None, year: int | None) -> Screening | None:
    if not day or not month or not year:
        return None

    time_el = row.select_one("td.time")
    time_match = TIME_RE.search(time_el.get_text()) if time_el else None
    if not time_match:
        # No time means this is the "KINO MÁ PRÁZDNINY" recess notice, not a
        # real screening — see module docstring.
        return None
    time_str = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"

    name_link = row.select_one("td.name a")
    title = clean_text(name_link.get_text()) if name_link else ""
    if not title:
        return None

    date_str = f"{year:04d}-{month:02d}-{day:02d}"

    raw_tags: list[str] = []
    sound_code = ""
    sub_codes: list[str] = []
    for ico in row.select("td.icons .ico"):
        classes = ico.get("class") or []
        text = clean_text(ico.get_text())
        if "ico-sound" in classes:
            sound_code = text
        elif "ico-sub" in classes:
            sub_codes = [code.strip() for code in text.split(",") if code.strip()]
        elif "ico-favorite" in classes:
            flag = clean_text(ico.get("title", ""))
            if flag:
                raw_tags.append(flag)

    classified = classify_tags(raw_tags)
    english_friendly = sound_code.upper() == "EN" or "EN" in (c.upper() for c in sub_codes)

    ticket_link = row.select_one("td.tickets a")
    booking_url = (
        ticket_link["href"] if ticket_link and ticket_link.get("href") else PROGRAM_URL
    )

    return Screening(
        cinema=CINEMA_NAME,
        title_cz=title,
        date=date_str,
        time=time_str,
        language=language_name(sound_code),
        format="",
        note=classified["strand"] or classified["format"] or "",
        english_friendly=english_friendly,
        language_version=classified["language_version"],
        strand=classified["strand"],
        hall="",
        tags=classified["tags"],
        booking_url=booking_url,
        poster_url="",
        director="",
        runtime_min=None,
        source_id="",
    )


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
