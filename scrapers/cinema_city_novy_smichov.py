"""
Scraper for Cinema City Nový Smíchov (Prague 5, OC Nový Smíchov).

See cinema_city.py for how the platform is scraped and why one shared
parser covers all six Prague locations — this module is just that cinema's
name and Vista location id.
"""

from __future__ import annotations

from . import cinema_city

CINEMA_NAME = "Cinema City Nový Smíchov"
CINEMA_ID = "1031"


def scrape(payloads=None) -> dict:
    return cinema_city.scrape(CINEMA_NAME, CINEMA_ID, payloads=payloads)


if __name__ == "__main__":
    import json
    import sys

    json.dump(scrape(), sys.stdout, ensure_ascii=False, indent=2)
