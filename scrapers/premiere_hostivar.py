"""
Scraper for Premiere Cinemas Praha Hostivař (premierecinemas.cz).

Prague's only Premiere Cinemas location, in the VIVO! Hostivař shopping
centre — unlike Cinema City, this is a plain server-rendered PHP site with
no JS framework at all, closer in spirit to Aerofilms than to Cinema City's
JSON API.

The whole week's schedule sits in one page load: a day-tab strip
("Pátek 31. 7.", "Sobota 1. 8.", ...) where each tab is a <div id="tab-N">
panel already containing that day's full <table class="ind_table-program">
— no per-day fetch needed. An eighth tab ("Předprodej" / presale, with no
date in its label) links out to future advance-sale listings rather than a
specific day's showtimes, and is skipped.

Each film is one table row: a title cell (nested icon spans for badges like
"4K"/"Premiéra" that we don't need — the plain title text always comes
first in the cell, so `next(stripped_strings)` gets it without them), an
access-rating cell (age rating; not part of Beam's schema, skipped), a
version cell ("cz"/"tit"/"orig"), then one cell per hour-of-day column. An
empty cell means nothing screens in that slot; a filled one holds the
showing's exact time as text, sometimes linked to /vstupenky/{id}/ (a
future, bookable showing) and sometimes a plain <span> (already past or not
yet bookable) — either way the visible text is the real time.

english_friendly is inferred from the version code alone ("tit"/"orig", not
"cz"): there's no separate original-language field the way Cinema City's API
provides one, but this cinema's catalog is overwhelmingly English-language
Hollywood releases, so "not dubbed to Czech" is a reasonable proxy here —
flagged as an approximation rather than a certainty.
"""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup

from .base import (
    Screening,
    clean_text,
    empty_dates_in_range,
    fetch,
    infer_years_for_months,
)

CINEMA_NAME = "Premiere Cinemas Praha Hostivař"
PROGRAM_URL = "https://www.premierecinemas.cz/"

# "cz" = dubbed to Czech, "tit" = Czech subtitles over the original audio,
# "orig" = original audio, no Czech help at all.
VERSION_CODE_MAP = {
    "cz": "dabing",
    "tit": "titulky",
    "orig": "originál",
}

DAY_LABEL_RE = re.compile(r"(\d{1,2})\.\s*(\d{1,2})\.")


def scrape(cinema: str = CINEMA_NAME, program_url: str = PROGRAM_URL, html: str | None = None) -> dict:
    if html is None:
        html = fetch(program_url)

    soup = BeautifulSoup(html, "lxml")

    tab_dates = _day_tab_dates(soup)

    screenings: list[Screening] = []
    covered_dates: list[str] = []

    for tab_id, day_date in tab_dates.items():
        panel = soup.find("div", id=tab_id)
        if not panel:
            continue
        covered_dates.append(day_date)

        table = panel.find("table", class_="ind_table-program")
        if not table:
            continue

        for row in table.find_all("tr"):
            if "ind_table-program-th" in (row.get("class") or []):
                continue  # the header row
            for screening in _screenings_from_row(row, cinema, day_date):
                screenings.append(screening)

    covered_dates.sort()
    screenings.sort(key=lambda s: (s.date, s.time, s.title_cz))

    return {
        "cinema": cinema,
        "source_url": program_url,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, {s.date for s in screenings}),
        "screenings": [s.to_dict() for s in screenings],
    }


def _day_tab_dates(soup: BeautifulSoup) -> dict[str, str]:
    """
    Map each real day tab ("tab-1", "tab-2", ...) to its calendar date.

    Labels look like "Pátek 31. 7." — real day and month, but no year, so
    infer_years_for_months() (shared with Kino Pilotů/Edison, which have the
    same day-header shape) works out the year from the sequence. The eighth
    tab ("Předprodej") carries no day.month pattern and is naturally
    excluded rather than needing a special case.
    """
    tab_ids: list[str] = []
    days: list[int] = []
    months: list[int] = []

    for anchor in soup.select("ul.ps-tabs a[href^='#tab-']"):
        label = clean_text(anchor.get_text(" "))
        match = DAY_LABEL_RE.search(label)
        if not match:
            continue
        tab_ids.append(anchor["href"].lstrip("#"))
        days.append(int(match.group(1)))
        months.append(int(match.group(2)))

    years = infer_years_for_months(months)
    return {
        tab_id: f"{year}-{month:02d}-{day:02d}"
        for tab_id, day, month, year in zip(tab_ids, days, months, years)
        if year is not None
    }


def _screenings_from_row(row, cinema: str, day_date: str) -> list[Screening]:
    movie_cell = row.find("td", class_="ind_table-program-movie")
    if not movie_cell:
        return []
    link = movie_cell.find("a")
    if not link:
        return []
    # The plain title text always comes first, before any nested badge spans
    # ("4K", "Premiéra") that share the same <a> — stripped_strings walks
    # descendants in document order, so the first one is the title itself.
    title = next(link.stripped_strings, "")
    if not title:
        return []

    version_cell = row.find("td", class_="ind_table-program-version")
    version_code = clean_text(version_cell.get_text()) if version_cell else ""
    language_version = VERSION_CODE_MAP.get(version_code, "")
    english_friendly = version_code in ("tit", "orig")

    results = []
    for cell in row.find_all("td", class_="ind_table-program-time"):
        text = clean_text(cell.get_text())
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
        if not match:
            continue
        time = f"{int(match.group(1)):02d}:{match.group(2)}"

        booking_link = cell.find("a")
        booking_url = (
            f"https://www.premierecinemas.cz{booking_link['href']}"
            if booking_link and booking_link.get("href")
            else ""
        )

        results.append(Screening(
            cinema=cinema,
            title_cz=title,
            date=day_date,
            time=time,
            language_version=language_version,
            note=language_version,
            english_friendly=english_friendly,
            booking_url=booking_url,
        ))
    return results


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
