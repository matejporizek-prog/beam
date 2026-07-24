"""
Scraper for Bio Oko (biooko.net).

Same Aerofilms platform as Kino Aero — see aerofilms.py for the parsing logic
and scrapers/kino_aero.py's docstring for why one parser covers all the
Aerofilms cinemas.
"""

from __future__ import annotations

from . import aerofilms

CINEMA_NAME = "Bio Oko"
PROGRAM_URL = "https://www.biooko.net/program/"


def scrape(html: str | None = None) -> dict:
    return aerofilms.scrape(CINEMA_NAME, PROGRAM_URL, html=html)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
