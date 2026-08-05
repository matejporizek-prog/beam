"""
Scraper for CineStar Praha Anděl (OC Nový Smíchov).

See cinestar.py for how the platform is scraped — this module is just that
cinema's name and CineStar's own location slug.
"""

from __future__ import annotations

from . import cinestar

CINEMA_NAME = "CineStar Anděl"
SLUG = "praha5"


def scrape(html=None, catalog=None) -> dict:
    return cinestar.scrape(CINEMA_NAME, SLUG, html=html, catalog=catalog)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
