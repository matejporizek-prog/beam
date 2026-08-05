"""
Run every cinema scraper and write data/screenings.json.

Usage, from the project folder:

    python -m scrapers.run              # scrape the live sites
    python -m scrapers.run --dry-run    # print a summary, write nothing

As more cinemas get their own modules (Milestone 4), add them to SCRAPERS below.
Nothing else here needs to change.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from . import (
    atlas, bio_oko, cinema_city_chodov, cinema_city_flora, cinema_city_letnany,
    cinema_city_novy_smichov, cinema_city_slovansky_dum, cinema_city_zlicin,
    cinestar_andel, cinestar_cerny_most,
    edison, kavalirka, kino35, kino_aero, kino_pilotu, lucerna, mat, ponrepo,
    premiere_hostivar, pritomnost, svetozor, zaplotem,
)

# Every cinema module exposes the same scrape() function, so the runner doesn't
# need to know anything about how an individual site is built.
SCRAPERS = {
    "Kino Aero": kino_aero.scrape,
    "Bio Oko": bio_oko.scrape,
    "Kino Světozor": svetozor.scrape,
    "Kino Přítomnost": pritomnost.scrape,
    "Kino Lucerna": lucerna.scrape,
    "Kino Pilotů": kino_pilotu.scrape,
    "Kino Ponrepo": ponrepo.scrape,
    "Edison Filmhub": edison.scrape,
    "Kino Atlas": atlas.scrape,
    "Kino MAT": mat.scrape,
    "Kino Kavalírka": kavalirka.scrape,
    "Divadlo Za plotem": zaplotem.scrape,
    "Kino 35": kino35.scrape,
    # Multiplexes — hidden by the app's arthouse-default filter, but scraped
    # the same as everything else. See cinema_city.py and cinestar.py for
    # how each platform is scraped.
    "Cinema City Flora": cinema_city_flora.scrape,
    "Cinema City Chodov": cinema_city_chodov.scrape,
    "Cinema City Letňany": cinema_city_letnany.scrape,
    "Cinema City Nový Smíchov": cinema_city_novy_smichov.scrape,
    "Cinema City Slovanský dům": cinema_city_slovansky_dum.scrape,
    "Cinema City Zličín": cinema_city_zlicin.scrape,
    "Premiere Cinemas Praha Hostivař": premiere_hostivar.scrape,
    "CineStar Anděl": cinestar_andel.scrape,
    "CineStar Černý Most": cinestar_cerny_most.scrape,
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "screenings.json"


def _previous_screenings_by_cinema() -> dict[str, list[dict]]:
    """
    The last successful run's screenings, grouped by cinema — the pool a
    still-failing scraper (base.py already retries transient blips a few
    times before giving up) falls back to, so one bad site doesn't make its
    cinema vanish from the app for the whole day. Empty on the very first
    run, or if the existing file is missing/corrupt — a fallback with
    nothing to fall back to is just the existing "record the failure, move
    on" behavior.
    """
    if not OUTPUT_FILE.exists():
        return {}
    try:
        previous = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    by_cinema: dict[str, list[dict]] = {}
    for screening in previous.get("screenings", []):
        by_cinema.setdefault(screening["cinema"], []).append(screening)
    return by_cinema


def _forward_looking(screenings: list[dict]) -> list[dict]:
    """
    Only the fallback screenings that are still honest to show — a stale
    copy of what a cinema was showing days ago is useless (and confusing)
    padding; a stale copy of what it's *still probably* showing today or
    later is exactly the point of falling back at all. Naturally produces
    nothing once a cinema has been down long enough that even yesterday's
    data has run out, rather than ever inventing a schedule.
    """
    today = date.today().isoformat()
    return [s for s in screenings if s["date"] >= today]


def run(dry_run: bool = False) -> dict:
    previous_by_cinema = _previous_screenings_by_cinema()

    cinemas = []
    all_screenings = []
    failures = []

    for name, scrape_fn in SCRAPERS.items():
        try:
            result = scrape_fn()
        except Exception as error:
            # One broken cinema site must never take down the whole run — the
            # other cinemas' data is still perfectly good. base.py's own
            # retries already absorbed the common case (a brief timeout); if
            # a scraper still failed after those, fall back to whatever of
            # its last successful run is still forward-looking, so the
            # cinema stays present (a day stale) rather than empty. The
            # failure itself is still recorded either way, so a real,
            # longer-lived break in a scraper never goes unnoticed.
            failures.append({"cinema": name, "error": str(error)})

            fallback = _forward_looking(previous_by_cinema.get(name, []))
            if fallback:
                cinemas.append({"name": name, "source_url": "", "stale": True})
                all_screenings.extend(fallback)
                print(f"  ! {name}: FAILED — {error}")
                print(f"    using {len(fallback)} screenings from the last successful run instead")
            else:
                print(f"  ! {name}: FAILED — {error}")
            continue

        cinema_entry = {"name": name, "source_url": result.get("source_url", "")}
        # An arthouse cinema with no screenings is normal (quiet week, or closed
        # for reconstruction like Ponrepo). Record it rather than hiding it.
        if result.get("empty_dates"):
            cinema_entry["empty_dates"] = result["empty_dates"]
        # Ponrepo-specific, but written generically: any scraper can report a
        # known reopening date. The app's closedCinemasOn() already checks for
        # this field to show an honest "closed until X" notice.
        if result.get("closed_until"):
            cinema_entry["closed_until"] = result["closed_until"]

        cinemas.append(cinema_entry)
        all_screenings.extend(result["screenings"])
        print(f"  + {name}: {len(result['screenings'])} screenings")

    all_screenings.sort(key=lambda s: (s["date"], s["time"], s["cinema"]))

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "cinemas": cinemas,
        "screenings": all_screenings,
    }
    if failures:
        payload["failures"] = failures

    if dry_run:
        print(f"\nDry run — {len(all_screenings)} screenings, nothing written.")
        return payload

    # Refuse to replace real data with nothing. If every cinema failed (network
    # down, TLS problem, a site being redesigned), the last good screenings.json
    # is far more useful to the app than an empty one — a stale program still
    # beats a blank screen. Genuinely empty results are only trusted when the
    # scrapers actually succeeded.
    if not all_screenings and failures:
        print(
            f"\nAll {len(failures)} scraper(s) failed — keeping the existing "
            f"{OUTPUT_FILE.name} instead of overwriting it with nothing."
        )
        return payload

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nWrote {len(all_screenings)} screenings to {OUTPUT_FILE}")
    return payload


if __name__ == "__main__":
    import sys

    # See the matching comment in resolve/films.py: a Windows console's legacy
    # codepage can't represent every character a scraped title might contain,
    # and a crash from a progress print() must never take down the run or
    # corrupt an already-correct result.
    sys.stdout.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(description="Scrape Prague arthouse cinema programs.")
    parser.add_argument("--dry-run", action="store_true", help="print a summary, write nothing")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
