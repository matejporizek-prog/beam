"""
Shared building blocks for every cinema scraper.

Each cinema gets its own module (kino_aero.py, bio_oko.py, ...) that knows how to
read that one website. Everything those modules have in common — what a screening
looks like, how we clean up text, how we turn cinema tags into structured fields —
lives here so the per-cinema modules stay small and readable.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date as date_cls, timedelta
from typing import Optional

import requests

# Use the operating system's certificate store rather than the CA list Python
# ships with. Without this, kinoaero.cz fails TLS verification on Windows even
# though every browser on the machine trusts it fine. Optional on purpose: if
# truststore isn't installed we fall back to Python's own list, which is what
# CI on Linux uses happily.
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

# Pretend to be a normal browser. We are reading public listing pages exactly the
# way a visitor would; a real User-Agent is politeness, not evasion.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 "
    "(+Beam cinema aggregator; personal, non-commercial)"
)

REQUEST_TIMEOUT = 30

# Found live (2026-08-02): a single 30s connection timeout to kinopilotu.cz
# during one scheduled run was enough to drop that cinema from the app for
# the whole day — a blip a plain retry would very likely have survived,
# not a real multi-hour outage. A couple of short, immediate retries within
# the same run catch that common case for free, with no new infrastructure
# (a separately-scheduled retry run, failure-state tracked between runs,
# ...) — see run.py's fallback-to-yesterday's-data for the rarer case this
# doesn't catch.
RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (5, 15)  # wait before the 2nd attempt, then the 3rd


def _request_with_retry(url: str, headers: dict) -> requests.Response:
    """
    GET a URL, retrying on anything that looks transient.

    A connection error, a timeout, or a 5xx is the server's (or the
    network's) own trouble, not ours — worth a couple of quick retries. A
    4xx means the request itself is wrong (bad URL, blocked, not found), and
    retrying it would just fail the same way three times instead of once, so
    that raises straight through on the first attempt.
    """
    for attempt in range(RETRY_ATTEMPTS):
        try:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response
        except requests.RequestException as error:
            is_client_error = (
                isinstance(error, requests.HTTPError)
                and error.response is not None
                and 400 <= error.response.status_code < 500
            )
            if is_client_error or attempt == RETRY_ATTEMPTS - 1:
                raise
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])


def fetch(url: str) -> str:
    """Download a page and return its HTML."""
    response = _request_with_retry(url, headers={"User-Agent": USER_AGENT})

    # Trust a charset the server actually declared in Content-Type — requests
    # already parses that into response.encoding before we touch anything.
    # Only guess (via apparent_encoding, a content-sniffing heuristic) when
    # nothing was declared, which is what "no charset" looks like: requests
    # falls back to ISO-8859-1 per the old HTTP default for text/*.
    #
    # This used to unconditionally overwrite the declared encoding with the
    # guess, which is backwards — a declared charset is a fact, a sniffing
    # heuristic is a guess, and guesses can be wrong even on a page that is
    # genuinely UTF-8. That's exactly what happened on kinopilotu.cz: it
    # declares UTF-8 correctly, but apparent_encoding misread it as
    # iso8859_10, and every accented character came out corrupted. The
    # Aerofilms cinemas never exposed this because chardet's guess happened
    # to agree with their declared encoding — luck, not correctness.
    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def fetch_json(url: str) -> dict:
    """
    Download a URL and parse it as JSON.

    For the rarer cinema whose site is a genuine public API (Cinema City's
    Vista quickbook endpoint) rather than server-rendered HTML — same
    politeness header as fetch(), just a different body format.
    """
    response = _request_with_retry(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    return response.json()


# --------------------------------------------------------------------------
# The screening record
# --------------------------------------------------------------------------

@dataclass
class Screening:
    """
    One film, at one cinema, at one date and time.

    The first seven fields deliberately match sample-screenings-clean.json so the
    prototype and any existing fixtures keep working unchanged. Everything after
    them is extra detail we can get for free while we're already parsing the page —
    see README.md for why each one earns its place.
    """

    # --- core shape (matches sample-screenings-clean.json) ---
    cinema: str
    title_cz: str
    date: str          # "2026-07-21"
    time: str          # "20:00"
    language: str = ""  # Czech name of the film's language, e.g. "angličtina"
    format: str = ""    # "35 mm" when the cinema flags it, else ""
    note: str = ""      # human-readable label, usually the programming strand

    # --- extra fields (additive; nothing above changes) ---
    english_friendly: bool = False
    language_version: str = ""   # "dabing" | "titulky" | "" (unmarked = original)
    strand: str = ""             # "Malé oči", "Bio senior", "Legendy", ...
    hall: str = ""               # "Kinosál", "Bio Oko", ...
    tags: list[str] = field(default_factory=list)  # every raw tag, unclassified
    booking_url: str = ""        # deep link to this screening's booking page
    poster_url: str = ""         # cinema's own poster; TMDb will usually beat it
    director: str = ""           # from the page's structured data, when present
    runtime_min: Optional[int] = None
    source_id: str = ""          # the cinema's own id for this screening
    # A cinema's own IMDb link for the film (Kino Kavalírka gives one for some
    # screenings). A far stronger signal than title/director/runtime fuzzy
    # matching — TMDb supports an exact lookup by IMDb id — but consuming it
    # is a resolver change, not a scraper one, so it's captured here and not
    # yet wired into anything in resolve/. Worth doing as a focused follow-up.
    imdb_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# Text helpers
# --------------------------------------------------------------------------

def clean_text(value: str) -> str:
    """Collapse whitespace and strip. HTML is full of stray newlines and tabs."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_title(title: str) -> str:
    """
    Reduce a title to a comparable key: lowercase, no diacritics, no punctuation.

    This is what makes "Odyssea" and "Oddysea" (a real typo in the sample data)
    land near each other. It is NOT the fuzzy matcher itself — that comes in
    Milestone 2 — but it is the normalisation every fuzzy match starts from.
    """
    if not title:
        return ""
    decomposed = unicodedata.normalize("NFKD", title.lower())
    without_accents = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def parse_iso_duration(duration: str) -> Optional[int]:
    """Turn an ISO-8601 duration like 'PT2H52M' into minutes (172)."""
    if not duration:
        return None
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration.strip())
    if not match:
        return None
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    total = hours * 60 + minutes
    return total or None


# --------------------------------------------------------------------------
# Tag classification
# --------------------------------------------------------------------------

# Cinemas mix three different kinds of information into one row of tags:
# a format, a language version, and a programming strand. We split them apart so
# the app can style and filter each one properly instead of matching on text.

ENGLISH_FRIENDLY_TAGS = {"english friendly", "eng", "english subtitles", "en subs"}

FORMAT_TAGS = {
    "35 mm": "35 mm",
    "35mm": "35 mm",
    "70 mm": "70 mm",
    "70mm": "70 mm",
    "dcp": "DCP",
    "3d": "3D",
}

VERSION_TAGS = {
    "dabing": "dabing",
    "dabovano": "dabing",
    "cesky dabing": "dabing",
    "titulky": "titulky",
    "ceske titulky": "titulky",
    "original": "originál",
}


def classify_tags(raw_tags: list[str]) -> dict:
    """
    Sort a screening's tags into structured fields.

    Anything we don't recognise is treated as a programming strand ("Malé oči",
    "Legendy", "Mistři animace", ...). That default is deliberate: arthouse
    cinemas invent new strands constantly, and an unknown tag is far more likely
    to be a new strand than a new format. Unrecognised tags are never dropped —
    they stay in `tags` so nothing is silently lost.
    """
    result = {
        "english_friendly": False,
        "format": "",
        "language_version": "",
        "strand": "",
        "tags": [],
    }

    strands: list[str] = []

    for raw in raw_tags:
        tag = clean_text(raw)
        if not tag:
            continue
        result["tags"].append(tag)

        key = normalize_title(tag)

        if key in ENGLISH_FRIENDLY_TAGS:
            result["english_friendly"] = True
        elif key in FORMAT_TAGS:
            result["format"] = FORMAT_TAGS[key]
        elif key in VERSION_TAGS:
            result["language_version"] = VERSION_TAGS[key]
        # Beyond the exact-match dict above: "dabing"/"titulky" keep turning up
        # with a different prefix or abbreviation per cinema — bare "Dabing"
        # (Aerofilms), "Český dabing" (Kino Pilotů), "CZ DABING" (Edison
        # Filmhub). Rather than grow VERSION_TAGS with every new combination as
        # it's found, recognise the word itself wherever it appears in the tag.
        elif "dabing" in key or "dabovano" in key:
            result["language_version"] = "dabing"
        elif "titulky" in key:
            result["language_version"] = "titulky"
        elif tag not in strands:
            # Found via Kino Kavalírka: a screening can carry the same strand
            # twice from two different places on the page at once — its own
            # ".page__program-tag" chip *and* a venue-branded prefix baked
            # into the title ("Film & Drink: Pulp Fiction" alongside a
            # separate "Film & Drink" chip). Deduplicating here is general
            # and harmless for every cinema, not just this one.
            strands.append(tag)

    # A screening normally has at most one strand; join defensively if not.
    result["strand"] = " / ".join(strands)
    return result


# --------------------------------------------------------------------------
# Language codes -> Czech names
# --------------------------------------------------------------------------

# The sample data records languages in Czech ("angličtina"), while structured
# page data uses ISO codes ("en"). Map the ones our cinemas actually screen.
LANGUAGE_NAMES = {
    "cs": "čeština",
    "cz": "čeština",
    "en": "angličtina",
    "de": "němčina",
    "fr": "francouzština",
    "es": "španělština",
    "it": "italština",
    "ja": "japonština",
    "ko": "korejština",
    "zh": "čínština",
    "yue": "kantonština",
    "ru": "ruština",
    "pl": "polština",
    "sk": "slovenština",
    "hu": "maďarština",
    "sl": "slovinština",
    "da": "dánština",
    "sv": "švédština",
    "no": "norština",
    "fi": "finština",
    "pt": "portugalština",
    "nl": "nizozemština",
    "uk": "ukrajinština",
    "ro": "rumunština",
    "tr": "turečtina",
    "fa": "perština",
    "ar": "arabština",
    "he": "hebrejština",
    "hi": "hindština",
    "is": "islandština",
    "my": "barmština",
}

# Tokens that appear in the inLanguage field but aren't actually languages —
# some Aerofilms cinemas write "orig" (original version, language unspecified)
# there. Dropped rather than shown as a bogus "language".
NON_LANGUAGE_CODES = {"orig", "original", "ov", "und", "zxx", "mul"}


def language_name(code: str) -> str:
    """
    Turn a language code into its Czech name: 'en' -> 'angličtina'.

    Films are often multilingual and the page lists those as "yue, zh", so each
    code is translated separately and rejoined — matching how the sample data
    writes it ("kantonština, čínština"). Codes we don't know are passed through
    unchanged rather than dropped, so a missing mapping shows up as odd text we
    can notice and add, instead of silently becoming an empty field.
    """
    if not code:
        return ""

    parts = [part.strip() for part in re.split(r"[,/;]", code) if part.strip()]
    if not parts:
        return ""

    names = []
    for part in parts:
        lower = part.lower()
        if lower in NON_LANGUAGE_CODES:
            continue
        name = LANGUAGE_NAMES.get(lower, part)
        if name not in names:  # "en, en-US" shouldn't produce a duplicate
            names.append(name)
    return ", ".join(names)


# --------------------------------------------------------------------------
# Day gaps
# --------------------------------------------------------------------------

def empty_dates_in_range(covered_dates: list[str], dates_with_screenings: set[str]) -> list[str]:
    """
    Which days inside the covered range ended up with no screenings.

    Shared by every scraper, not just one cinema's parser: any site can have a
    quiet day, and this is how it stays distinguishable from a day we simply
    never looked at — filling in gap days the site's own listing skips
    entirely, not just the days it explicitly marked as empty. It's also the
    signal a closed cinema (Ponrepo, closed until 31.8) produces.
    """
    if not covered_dates:
        return []

    known = sorted(set(covered_dates))
    start = date_cls.fromisoformat(known[0])
    end = date_cls.fromisoformat(known[-1])

    empty = []
    current = start
    while current <= end:
        iso = current.isoformat()
        if iso not in dates_with_screenings:
            empty.append(iso)
        current += timedelta(days=1)
    return empty


def infer_years_for_months(months: list[int | None]) -> list[int | None]:
    """
    Given a document-ordered sequence of month numbers with no year attached,
    work out which year each one belongs to.

    Some cinema sites (Kino Pilotů, Edison Filmhub) print a day header with a
    day-of-week, a day number and a month — "Pátek 24. července", "Pátek
    24.7." — but never a year. The list only ever runs forward in time, so a
    month that's *lower* than the one before it can only mean the calendar
    crossed from December into January; every other case just carries the
    current year forward unchanged.

    A `None` in the input (a header we failed to parse a month out of) passes
    through as `None` and is skipped when looking for the previous real month,
    so one bad header doesn't throw off every date after it.
    """
    year = date_cls.today().year
    last_month: int | None = None
    years: list[int | None] = []

    for month in months:
        if month is None:
            years.append(None)
            continue
        if last_month is not None and month < last_month:
            year += 1
        last_month = month
        years.append(year)

    return years
