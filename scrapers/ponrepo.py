"""
Scraper for Kino Ponrepo (nfa.cz), the National Film Archive's cinema.

Ponrepo is closed for reconstruction, reopening 31.8.2026 — this scraper was
written and wired into the pipeline *now*, expecting zero screenings until
then, exactly as the planning doc calls for. It's the intended test case for
"a cinema temporarily has nothing on" rather than a bug.

What the page actually shows right now
---------------------------------------
The program page (nfa.cz/cs/kino-ponrepo/program/program) renders a day-picker
calendar for the current month — a real one, not a placeholder: each day is a

    <a class="calendar-slider__link ... calendar-slider__link--disabled"
       href="#2026-07-01">
      <span class="calendar-slider__day">St</span> 1/7
    </a>

The `href` already carries a full ISO date, so there's no Czech-month-name
parsing needed here at all (contrast Kino Pilotů, which has neither this nor
JSON-LD). What was checked and confirmed before writing anything further:
every single day link in the current month carries `--disabled`, and there is
no matching `id="2026-07-01"` section anywhere on the page holding that day's
screenings. That's a structurally verified "nothing scheduled", not a page
that needs JavaScript to render real content — no AJAX endpoint, no React/Vue
root, only two unrelated <script src> tags (analytics).

Why this scraper doesn't try to parse real screenings yet
-----------------------------------------------------------
There is currently nothing to verify a parser against. Every other scraper in
this codebase was built by fetching the live site and checking its structure
before writing extraction logic — writing speculative parsing for markup that
doesn't exist yet would invert that discipline and risk silently producing
garbage the day the cinema reopens. So this scraper does the honest thing:
read the real, already-confirmed calendar (which days exist, which are
disabled), and report every day as empty. `_check_for_unexpected_content()`
is the tripwire for revisiting this file — if a day is ever found NOT
disabled, or an `id="<date>"` section turns up, that's the signal the site has
changed and real per-screening parsing needs to be written (and can finally be
verified against real data), the same way every other scraper here was.
"""

from __future__ import annotations

import re
import warnings
from datetime import datetime

from bs4 import BeautifulSoup

from .base import empty_dates_in_range, fetch

CINEMA_NAME = "Kino Ponrepo"
PROGRAM_URL = "https://nfa.cz/cs/kino-ponrepo/program/program"

# Known from the planning doc, not discoverable from the site itself (it gives
# no "closed for reconstruction" text anywhere) — the app uses this to show an
# honest closure notice rather than an unexplained empty program.
CLOSED_UNTIL = "2026-08-31"

DAY_LINK_SELECTOR = "a.calendar-slider__link"
ISO_DATE_RE = re.compile(r"#(\d{4}-\d{2}-\d{2})")


def scrape(html: str | None = None) -> dict:
    """
    Scrape Kino Ponrepo's program.

    Pass `html` to parse a saved page (used by the tests); leave it out to
    fetch the live site.
    """
    if html is None:
        html = fetch(PROGRAM_URL)

    soup = BeautifulSoup(html, "lxml")
    day_links = soup.select(DAY_LINK_SELECTOR)

    covered_dates: list[str] = []
    for link in day_links:
        match = ISO_DATE_RE.search(link.get("href", ""))
        if match:
            covered_dates.append(match.group(1))
    covered_dates.sort()

    _check_for_unexpected_content(soup, day_links, covered_dates)

    # No screening-extraction logic exists yet — see the module docstring for
    # why that's deliberate. Every covered day is therefore empty.
    screenings: list[dict] = []

    return {
        "cinema": CINEMA_NAME,
        "source_url": PROGRAM_URL,
        "scraped_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "closed_until": CLOSED_UNTIL,
        "covered_dates": covered_dates,
        "empty_dates": empty_dates_in_range(covered_dates, set()),
        "screenings": screenings,
    }


def _check_for_unexpected_content(soup, day_links, covered_dates: list[str]) -> None:
    """
    The tripwire for "the site changed, this file needs real work now".

    Warns (doesn't fail the whole scrape run) if either signal that currently
    reads as "closed" ever stops being true: a day link without the disabled
    class, or an anchor target that actually exists. Either means the cinema
    has started publishing real screenings and this scraper needs the same
    verify-then-parse treatment every other cinema got.
    """
    enabled = [
        link for link in day_links
        if "calendar-slider__link--disabled" not in (link.get("class") or [])
    ]
    if enabled:
        warnings.warn(
            f"Kino Ponrepo: {len(enabled)} day(s) are no longer marked disabled — "
            "the cinema may have reopened. scrapers/ponrepo.py needs real "
            "screening-extraction logic now; see its module docstring.",
            stacklevel=2,
        )

    for date in covered_dates:
        if soup.find(id=date):
            warnings.warn(
                f"Kino Ponrepo: found a content section for {date} — "
                "the cinema may have reopened. scrapers/ponrepo.py needs real "
                "screening-extraction logic now; see its module docstring.",
                stacklevel=2,
            )
            break  # one is enough to raise the flag


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
