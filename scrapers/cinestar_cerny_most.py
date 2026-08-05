"""
Scraper for CineStar Praha Černý Most (Centrum Černý Most).

See cinestar.py for how the platform is scraped — this module is just that
cinema's name and CineStar's own location slug.

The slug is "praha9" despite the cinema being named Černý Most (which
straddles the Praha 9/14 border) — confirmed live by navigating to it, not
guessed from the district name; CineStar's own "cernymost"-style slug
doesn't exist (404s).
"""

from __future__ import annotations

from . import cinestar

CINEMA_NAME = "CineStar Černý Most"
SLUG = "praha9"


def scrape(html=None, catalog=None) -> dict:
    return cinestar.scrape(CINEMA_NAME, SLUG, html=html, catalog=catalog)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
