"""
Shared building blocks for every cinema scraper.

Each cinema gets its own module (kino_aero.py, bio_oko.py, ...) that knows how to
read that one website. Everything those modules have in common — what a screening
looks like, how we clean up text, how we turn cinema tags into structured fields —
lives here so the per-cinema modules stay small and readable.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
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


def fetch(url: str) -> str:
    """Download a page and return its HTML."""
    response = requests.get(
        url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT
    )
    response.raise_for_status()
    # The Czech cinema sites are UTF-8 but don't always say so in the headers.
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


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
        else:
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
}


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
        name = LANGUAGE_NAMES.get(part.lower(), part)
        if name not in names:  # "en, en-US" shouldn't produce a duplicate
            names.append(name)
    return ", ".join(names)
