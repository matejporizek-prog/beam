"""
Scraper for Kino Lucerna (kinolucerna.cz).

Same Aerofilms platform as Kino Aero, Bio Oko, Kino Světozor and Kino
Přítomnost — checked before writing anything (48 JSON-LD Event blocks, the
same program__ markup, the same data-projection ids). Matěj's tip; same
result as Přítomnost's.

One difference from the other Aerofilms cinemas: the program lives directly
on the homepage rather than at /program/ (the site redirects /program/ back
to /), so PROGRAM_URL is the root.

See aerofilms.py for the parsing logic and scrapers/kino_aero.py's docstring
for why one parser covers all the Aerofilms cinemas.
"""

from __future__ import annotations

from . import aerofilms

CINEMA_NAME = "Kino Lucerna"
PROGRAM_URL = "https://www.kinolucerna.cz/"


def scrape(html: str | None = None) -> dict:
    return aerofilms.scrape(CINEMA_NAME, PROGRAM_URL, html=html)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
