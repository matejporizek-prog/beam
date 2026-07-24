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
from datetime import datetime
from pathlib import Path

from . import bio_oko, edison, kino_aero, kino_pilotu, ponrepo, pritomnost, svetozor

# Every cinema module exposes the same scrape() function, so the runner doesn't
# need to know anything about how an individual site is built.
SCRAPERS = {
    "Kino Aero": kino_aero.scrape,
    "Bio Oko": bio_oko.scrape,
    "Kino Světozor": svetozor.scrape,
    "Kino Přítomnost": pritomnost.scrape,
    "Kino Pilotů": kino_pilotu.scrape,
    "Kino Ponrepo": ponrepo.scrape,
    "Edison Filmhub": edison.scrape,
}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "screenings.json"


def run(dry_run: bool = False) -> dict:
    cinemas = []
    all_screenings = []
    failures = []

    for name, scrape_fn in SCRAPERS.items():
        try:
            result = scrape_fn()
        except Exception as error:
            # One broken cinema site must never take down the whole run — the
            # other cinemas' data is still perfectly good.
            failures.append({"cinema": name, "error": str(error)})
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
