# Beam — scrapers

Prague arthouse cinema programs, scraped into one normalized JSON file that the
PWA reads. See `beam-build-brief.md` for the build order and
`prague-cinema-app-brainstorm.md` for the full planning context.

**Milestones 1–3 are done**: the Kino Aero scraper, TMDb + ČSFD resolution, and
the PWA running on real data. Milestones 4 (remaining scrapers) and 5 (GitHub
Actions + Cloudflare Pages) are ahead.

## Running it

Python 3.12 is installed at
`%LOCALAPPDATA%\Programs\Python\Python312\python.exe` but is **not on your PATH**,
so commands need the full path. From the project folder:

```powershell
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"

& $py -m pip install -r requirements.txt   # once
& $py -m pytest tests -v                   # run the tests
& $py -m scrapers.run                      # scrape -> data/screenings.json
& $py -m scrapers.run --dry-run            # summary only, writes nothing

& $py -m resolve.films                     # resolve new titles -> data/films.json
& $py -m resolve.films --retry             # also retry titles that failed before
& $py -m resolve.films --force             # re-resolve everything from scratch
```

`resolve.films` needs a TMDb key. Copy `.env.example` to `.env` and paste it in;
`.env` is gitignored so it never reaches the public repo.

### Looking at the app

The PWA uses ES modules and `fetch`, so it needs a web server — opening
`index.html` off the disk will not work. From the project folder:

```powershell
& $py devserver.py
```

then open **http://localhost:8788/app/**. Resize the browser narrow, or use the
device toolbar, to see it as intended — the layout is capped at 430px.

`devserver.py` is a plain static server with one addition: it sends
`Cache-Control: no-store`. Python's built-in `http.server` doesn't, which makes
browsers heuristically cache the ES modules — so edits silently don't appear
until a hard refresh. The dev server avoids that whole class of confusion.

The module imports also carry a `?v=` version query (in `index.html` and the
`js/` files). Bump it when shipping changed JS so returning visitors fetch the
new code rather than a cached copy; Milestone 5 can automate it at deploy.

If you'd rather type plain `python`, add
`C:\Users\matej\AppData\Local\Programs\Python\Python312` to your PATH in
*Settings → System → About → Advanced system settings → Environment Variables*.

## Layout

```
scrapers/
  base.py        shared: the Screening record, text cleanup, tag classification
  kino_aero.py   the Kino Aero scraper
  run.py         runs every scraper, writes data/screenings.json
resolve/
  tmdb.py        TMDb client + the title matcher
  csfd.py        ČSFD links
  films.py       screenings.json -> films.json
  overrides.json hand-written answers for films the matcher can't get
app/
  index.html     the PWA shell
  css/beam.css   the design system, ported from the prototype
  js/data.js     loading, joining, model helpers
  js/format.js   Czech dates, shared markup primitives
  js/screens.js  the four screens, detail overlay, search
  js/store.js    localStorage (watchlist, filters)
  js/app.js      bootstrap, navigation, events, the beam
  sw.js          offline caching
data/
  screenings.json   generated — do not edit by hand
  films.json        generated — do not edit by hand
tests/
  test_kino_aero.py     tests run against a saved page, not the live site
  test_resolve.py       matching logic, tested offline against fake TMDb payloads
  fixtures/             that saved page
```

Adding a cinema in Milestone 4 means writing one new module next to
`kino_aero.py` exposing a `scrape()` function, then adding it to `SCRAPERS` in
`run.py`. Nothing else changes.

## What one screening looks like

```json
{
  "cinema": "Kino Aero",
  "title_cz": "Odyssea",
  "date": "2026-07-21",
  "time": "20:00",
  "language": "angličtina",
  "format": "35 mm",
  "note": "35 mm",

  "english_friendly": true,
  "language_version": "",
  "strand": "",
  "hall": "Kinosál",
  "tags": ["ENG", "35 mm"],
  "booking_url": "https://kinoaero.cz/?projection=51863",
  "poster_url": "https://kinoaero.cz/uploads/images/movies/...jpg",
  "director": "Christopher Nolan",
  "runtime_min": 172,
  "source_id": "51863"
}
```

The first seven fields are exactly the shape of `sample-screenings-clean.json`,
so the prototype and existing fixtures keep working. The rest is extra, and each
piece pays for something specific later:

| Field | Why it's here |
|---|---|
| `english_friendly` | A first-class accessibility signal per the data model — belongs on the card, not behind a filter. |
| `language_version` | Fixes the flagged version-filter bug: real per-screening data instead of a heuristic that mislabels Czech films. |
| `strand` | "Malé oči", "Bio Senior", "Legendy" — kept separate from format so chips can differ by shape, not just text. |
| `booking_url` | The "Vstupenky ↗" button in Milestone 3, deep-linked to the exact screening. |
| `poster_url` | A real poster for every film immediately, and a fallback when TMDb can't match a title. |
| `director`, `runtime_min` | Free here, and a cross-check for TMDb matching in Milestone 2. |
| `source_id` | Aero's own id — stable identity for a screening across scrapes. |

## Two things about Kino Aero specifically

**The page carries structured data.** Every screening has a schema.org `Event`
block embedded next to it, giving an exact timezone-aware start time plus
director, runtime, language and poster. That's the primary source; the visible
HTML is only read for the cinema's own tags, which the structured data omits.
Practically, it means we never have to interpret the Czech day headers
"Dnes"/"Zítra", and the parser is much harder to break with a redesign.

**Aero only tags the exception.** Dubbed screenings get a "Dabing" chip;
subtitled ones get nothing — there is no "Titulky" tag anywhere on the site. So
an empty `language_version` means "presented the usual way", not "we failed to
find it". That happens to match the prototype's rule of showing a version chip
only when it deviates from the norm.

## Two gotchas worth remembering

**Scrape in the morning.** The program page only lists screenings that haven't
started yet. Scraping at 22:00 makes today look like it had one screening all
day. The Milestone 5 cron should run early, before the first matinee.

**Windows certificates.** Python doesn't trust the same certificate authorities
Windows does, and `kinoaero.cz` fails TLS verification without help. The
`truststore` package in `requirements.txt` fixes this and `base.py` activates it
automatically. It's an optional import, so CI on Linux is unaffected.

## How film matching works

Cinemas advertise Czech distribution titles; TMDb knows films under many titles.
Bridging the two is the whole of Milestone 2, and it can't be exact-string
matching — the sample data alone has "Odyssea" and "Oddysea" for one film.

The matcher scores candidates rather than comparing strings, and then *verifies*
them. Milestone 1 already collects each screening's director and runtime from
the cinema's own page, and those make excellent independent checks: two films
can share a title, but a title *and* a director *and* a runtime all agreeing is
about as sure as this gets without a person looking.

1. Strip event branding — `Nebezpečné známosti | NT Live` → `Nebezpečné známosti`.
2. Search TMDb in Czech, falling back to a plain search.
3. Score every candidate on its best-matching title, localised or original.
4. Fetch details for the top few and check director and runtime.
5. **Contradicting evidence vetoes the match**, however perfect the title.
6. Still unsure? Flag it — never guess. A wrong poster is worse than none.

### What the first real run taught us

The first run resolved all 18 films and looked like a total success. Cross-checking
each match against the director and runtime the cinema itself published found
**two were wrong**, which is why that check is worth running rather than trusting
a green tick:

- **"Mouchy"** matched a 4-minute Czech short from 1951, exactly titled. The film
  actually screening is a 99-minute Mexican feature.
- **"Nebezpečné známosti | NT Live"** matched the 1988 Dangerous Liaisons. Aero is
  screening Marianne Elliott's 180-minute theatre broadcast.

Both had *perfect* title scores. The bug was treating a mismatched director or
runtime as a small penalty — a 1.00 title could always outvote it. Now a
contradiction vetoes the match outright, and only an explicit confirmation on the
other axis can overrule it (a restoration or director's cut genuinely runs long,
so a confirmed director beats a runtime gap).

A related trap: TMDb returns directors in their own script — Wong Kar-wai as
王家衛, Antonio Lukič as Антоніо Лукіч. Character similarity reads those as
flat contradictions, which was penalising four *correct* matches. Names in
different scripts are now treated as no evidence rather than as disagreement.

Both failures are pinned by tests in `tests/test_resolve.py`.

### When TMDb simply doesn't have the film

Two of the eighteen needed help, and for opposite reasons:

- **Mouchy** is Eimbcke's *Moscas* (2026). TMDb has no Czech title for it at all,
  so no title search could ever find it. Fixed with a `tmdb_id` in
  `overrides.json` — this is exactly the case that file exists for.
- **Nebezpečné známosti | NT Live** genuinely isn't on TMDb; National Theatre Live
  broadcasts aren't catalogued there. It stays unresolved on purpose.

Unresolved films are not dropped. They keep their Czech title, their ČSFD search
link, and `poster_fallback_url` — the cinema's own poster art, which Aero
publishes for every screening. **The app should prefer TMDb's `poster_path` and
fall back to that URL, so no film ever renders as a blank tile**, matching the
store-readiness checklist's top item.

Anything unresolved lands in `films.json` with `resolved: false` and a reason,
so the screening still shows with its Czech title instead of disappearing. Put
the right `tmdb_id` in `resolve/overrides.json` and re-run with `--retry`.

**Grouping is fuzzy too, with guards.** Screenings collapse into films by fuzzy
title, so "Odyssea" and "Oddysea" cost one lookup instead of two — but plain
similarity would also merge "Toy Story 4" and "Toy Story 5", which score 0.91.
So differing digits block a merge outright, and the most common spelling wins as
the canonical title, since a typo is nearly always the rarer variant.

Every film is resolved **once, ever**. Re-runs skip anything already in
`films.json`. The current Aero program is 21 screenings → 18 unique films → about
54 API calls on a first run, and effectively zero after that.

## About the ČSFD link

The plan was to resolve each film's real ČSFD page URL at ingest. That is no
longer possible: csfd.cz now sits behind **Anubis**, a proof-of-work bot
challenge, and every automated request gets the challenge page instead of
results. Getting past it would mean defeating bot detection, which we don't do.

So `csfd_url` is a **search link** — `csfd.cz/hledat/?q=<title> <year>`. It's an
ordinary link a person clicks; their browser answers the challenge the way any
visitor's does. No automated access, nothing to maintain, and it can't rot the
way a stored film id could. The cost is landing on results rather than the film
page — usually one extra click. For films where that isn't good enough, put an
exact URL in `overrides.json` and it wins.

## The app (Milestone 3)

Built to the prototype's spec — same palette, type, density, components and
motion. The two files sit side by side if you want to compare: open
`app-shell-cool.html` directly in a browser for the prototype, and
`localhost:8788/app/` for the real thing.

**Everything that was placeholder is now real**: posters and backdrops, synopsis,
cast and credits, runtime, genres, age rating, trailers, ČSFD links, and the
Vstupenky buttons — which deep-link to the exact screening, not just the
cinema's homepage. "Now" is the real clock instead of the prototype's frozen
constant, and the watchlist, saved premieres and filters all persist across
reloads via localStorage.

### Backlog items fixed while building

- **Version filter** now uses real per-screening data instead of the heuristic
  that mislabelled Czech films.
- **Chip semantics** — a format is a filled champagne chip, a language version
  is outlined. Meaning lives in shape, not just in the text.
- **Bottom nav as a film strip** — reworked from round dots to a real 35mm
  look: rounded rectangular perforations tiled along the top and bottom edges,
  with the four destinations sitting in the frames between them (matching a
  reference strip Matěj supplied). The active frame lights champagne.
- **Unified "next screening" pill** — `dnes 17:00` today, `ÚT 22.7. 17:00`
  otherwise, everywhere it appears.
- **Inline trailer** in a modal rather than bouncing out to YouTube.
- **Toast component** replacing the "V přípravě…" button-text swap.
- **Removed prototype artifacts** — the self-annotating footer, and the dead
  `en-sub` / `vcount` / `beam-dot` / `TAGS` CSS and JS.
- **Scroll-linked shrinking header** and a springier filter sheet.

### Two things worth knowing

**The beam is drawn to a canvas, and still flickers.** The prototype used ~40
absolutely positioned divs, each blurred, each with `mix-blend-mode: screen`,
each animating its own opacity. That is now one canvas: each ray is blurred into
a sprite once, and the animation loop only varies each sprite's opacity per
frame — so the irregular per-ray flicker the motif depends on is preserved,
while a frame is 40 cheap `drawImage` calls instead of 40 live blur+blend
layers. One frame is also painted synchronously at build time, so the fan
appears immediately even in a background tab where the animation loop is
throttled. The loop pauses while the tab is hidden.

**Intensity and dust are one preset.** `BEAM_PRESETS` in `app.js` (ported from
the prototype's config) maps a preset name to a beam intensity and a dust-mote
count; `setBeamPreset('sixty')` at boot applies the locked 60% default. The
intensity is a single CSS variable (`--beam-intensity`) multiplying the whole
beam's opacity. The dust is `buildMotes()` — ~18 seeded, cone-constrained DOM
particles (≈30% warm-toned) drifting down inside the cone, a separate cheap
layer from the canvas rays. The rays stay on the canvas; only the motes and the
per-ray opacity flicker animate.

**No service worker on localhost.** It caches the app shell, which during
development means edits silently don't appear — a genuinely confusing failure.
It registers only on a real domain. The shell is cached
stale-while-revalidate rather than cache-first, so a deploy reaches users on
their next load without anyone having to remember to bump a version number.

## Data attribution

Screening data is read from each cinema's own public program page. Film metadata
(Milestone 2) comes from TMDb, which requires attribution and their logo in the
app — not yet added, since that lands with the PWA in Milestone 3.
