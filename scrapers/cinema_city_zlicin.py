"""
Scraper for Cinema City Zličín (Prague 5, Metropole Zličín).

See cinema_city.py for how the platform is scraped and why one shared
parser covers all six Prague locations — this module is just that cinema's
name and Vista location id.
"""

from __future__ import annotations

from . import cinema_city

CINEMA_NAME = "Cinema City Zličín"
CINEMA_ID = "1051"


def scrape(payloads=None) -> dict:
    return cinema_city.scrape(CINEMA_NAME, CINEMA_ID, payloads=payloads)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
