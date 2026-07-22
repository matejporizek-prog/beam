"""
ČSFD links.

Why this module is three lines of logic instead of a scraper
------------------------------------------------------------
The original plan was to resolve a film's real ČSFD page URL once at ingest, by
searching csfd.cz and storing the result. That is no longer possible: csfd.cz
now sits behind Anubis, a proof-of-work bot challenge. Every automated request
gets the challenge page instead of results, and getting past it would mean
defeating bot detection — which we're not going to do.

So we build a search URL instead. It is an ordinary link that a person clicks,
their browser answers the challenge the way any visitor's would, and they land
on ČSFD's results for that film. No automated access, nothing to maintain, and
the link cannot rot the way a stored film id could.

The trade-off is honest: the user lands on a results page rather than straight
on the film. For anything with a distinctive title that's a single extra click.
`overrides.json` exists for films where that isn't good enough — put an exact
ČSFD URL there and it wins.
"""

from __future__ import annotations

from urllib.parse import quote_plus

SEARCH_BASE = "https://www.csfd.cz/hledat/?q="


def search_url(title: str, year: int | None = None) -> str:
    """
    Build a ČSFD search link for a film.

    The year is included when we know it — ČSFD's search handles it well and it
    separates remakes from originals, which is exactly where a bare title search
    is least useful.
    """
    if not title:
        return ""
    query = f"{title} {year}" if year else title
    return SEARCH_BASE + quote_plus(query)
