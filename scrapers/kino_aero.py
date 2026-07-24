"""
Scraper for Kino Aero (kinoaero.cz).

Kino Aero, Bio Oko and Kino Světozor are all run by the same operator
(Aerofilms) on the same website platform, so the actual parsing logic lives in
one shared place: aerofilms.py. This module is just that cinema's name and URL.
See aerofilms.py for how the page is structured and why it's parsed this way.
"""

from __future__ import annotations

from . import aerofilms

CINEMA_NAME = "Kino Aero"
PROGRAM_URL = "https://kinoaero.cz/program"


def scrape(html: str | None = None) -> dict:
    return aerofilms.scrape(CINEMA_NAME, PROGRAM_URL, html=html)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
