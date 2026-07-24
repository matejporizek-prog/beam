"""
Scraper for Kino Přítomnost (kinopritomnost.cz).

Same Aerofilms platform as Kino Aero, Bio Oko and Kino Světozor — see
aerofilms.py for the parsing logic and scrapers/kino_aero.py's docstring for
why one parser covers all of them.
"""

from __future__ import annotations

from . import aerofilms

CINEMA_NAME = "Kino Přítomnost"
PROGRAM_URL = "https://www.kinopritomnost.cz/program/"


def scrape(html: str | None = None) -> dict:
    return aerofilms.scrape(CINEMA_NAME, PROGRAM_URL, html=html)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
