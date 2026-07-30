# Beam — scrapers

Prague arthouse cinema programs, scraped into one normalized JSON file that the
PWA reads. See `beam-build-brief.md` for the build order and
`prague-cinema-app-brainstorm.md` for the full planning context.

**All five Phase 1 milestones are done**, live at
[beam.matej-porizek.workers.dev](https://beam.matej-porizek.workers.dev): Kino
Aero, Bio Oko, Kino Světozor and Kino Přítomnost (all four turned out to be on
the same Aerofilms platform, see below), Kino Pilotů and Edison Filmhub (each
its own platform, see below), and Kino Ponrepo (closed for reconstruction until
31.8 — scraped and wired in now, correctly reporting zero screenings, exactly
the edge case the planning doc calls out by name).

**Phase 2 ("more cinemas") has added six more**: Kino Lucerna (a fifth
Aerofilms cinema), Kino Atlas, Kino MAT, Kino Kavalírka, Divadlo Za plotem and
Kino 35 — see "Phase 2" below for each. Modřanský Biograf is deliberately
deferred: its program is Next.js React Server Components streaming data, not
server-rendered HTML, a fundamentally different parsing problem from every
cinema scraped so far. **Kampus Hybernská was checked and ruled out**: it's a
general cultural center whose program is overwhelmingly DJ nights, lectures,
exhibitions and workshops — only 8 of 45 current events were film screenings,
all under one seasonal summer strand. Doesn't fit the curated-arthouse premise
the other 13 cinemas do; see `prague-cinema-app-brainstorm.md`'s scope list
for the full reasoning.

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

& $py -m resolve.premieres                 # refresh upcoming premieres -> data/premieres.json
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
  aerofilms.py   shared parser for the Aerofilms-platform cinemas
  kino_aero.py   Kino Aero — three lines: name, URL, calls aerofilms.scrape()
  bio_oko.py     Bio Oko — same pattern
  svetozor.py    Kino Světozor — same pattern
  pritomnost.py  Kino Přítomnost — same pattern
  kino_pilotu.py Kino Pilotů — its own platform (a Swiper.js carousel, no JSON-LD)
  edison.py      Edison Filmhub — its own platform (rich language/event markup, no JSON-LD)
  ponrepo.py     Kino Ponrepo — closed until 31.8; reports the closure honestly
  lucerna.py     Kino Lucerna — a fifth Aerofilms cinema, calls aerofilms.scrape()
  atlas.py       Kino Atlas — its own platform, AJAX-paginated program
  mat.py         Kino MAT — its own platform, pictogram-based formats
  kavalirka.py   Kino Kavalírka — its own platform, richest per-screening data yet
  zaplotem.py    Divadlo Za plotem — a WordPress/GenerateBlocks page, no clean container
  kino35.py      Kino 35 — its own platform, icon-based language/flag markup
  run.py         runs every scraper, writes data/screenings.json
resolve/
  tmdb.py        TMDb client + the title matcher
  csfd.py        ČSFD links
  films.py       screenings.json -> films.json
  premieres.py   TMDb discover (region=CZ) -> data/premieres.json
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
  premieres.json    generated — do not edit by hand
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

## Milestone 4 so far: one parser, four cinemas

Kino Aero, Bio Oko, Kino Světozor and Kino Přítomnost are all run by the same
operator (Aerofilms) — and, conveniently, all four sites are built on the
identical platform: same `program__*` BEM markup, same JSON-LD `Event` blocks,
same `data-projection` ids, same `checkTagInput` tag mechanism. (Přítomnost
was a tip from Matěj, checked before writing any code — same result.)

So the actual parsing logic lives in `scrapers/aerofilms.py` (a generalised
version of the original Aero-only parser, parameterised by cinema name and
program URL), and `kino_aero.py` / `bio_oko.py` / `svetozor.py` / `pritomnost.py`
are each a three-line wrapper. One bug fix or site-structure change now fixes
all four at once — and if the platform ever changes, all four tests fail
together, which is the signal to look here first.

One real fix this surfaced: Bio Oko's JSON-LD writes `inLanguage: "orig"` for
some original-version screenings — not a real language code. `language_name()`
in `scrapers/base.py` now drops known non-language tokens (`orig`, `ov`, `und`,
…) instead of showing literal "orig" as a language.

**Milestone 2's matcher held up at 3x the scale.** Resolving all three cinemas'
films together (95 screenings → 40 unique films) needed four manual overrides,
and each was a genuinely different kind of gap — worth knowing about since
they'll recur as more cinemas are added:

- **No Czech title on TMDb at all** — *Mé 20. století* (Ildikó Enyedi's *My
  Twentieth Century*) and *Ztracená listina* (*The Lost Letter*) are both
  literal Czech translations of the title, not the distribution title TMDb
  actually indexes. Found by searching the director's filmography instead of
  the title.
- **The title search never surfaces the right candidate at all** — Bio Oko's
  *Mumbo Jumbo* is really the Danish *When Mumbo Jumbo Grew Giant*; TMDb's own
  title search doesn't return it for that query no matter how the matcher's
  thresholds are tuned. Same fix: search by director instead.
- **A translated title that happens to also exist as a different real title**
  — *Hořké svátky* ("bitter holidays") is Almodóvar's *Bitter Christmas*.
- **Programming events, not single films** — the two "double feature" listings
  (Almodóvar, Ildikó Enyedi) correctly stay unresolved forever; there's no
  single TMDb film to match. They still render fine — Czech title, the
  cinema's own poster, a ČSFD search link — so nothing about the app degrades.

A full director/runtime audit of all 36 resolved films against what each
cinema actually scraped came back with **zero suspicious matches** — the
veto-on-contradiction logic from Milestone 2 is doing its job at this scale
too, not just on the original 18-film test case.

**Adding Přítomnost surfaced two more real things:**

- **A second NT Live theatre broadcast** (Přítomnost's "Audience | NT Live")
  hit the exact same veto as Aero's — title matched, director and runtime both
  contradicted, correctly rejected. Good confirmation the veto logic
  generalises rather than having been tuned to that one case.
- **TMDb returns `runtime: 0`** for films it doesn't have a runtime for yet
  (an unreleased film, still "In Production" upstream) — not `null`, literally
  `0`. `build_film_record` now normalises that to `None`; a real film is never
  zero minutes long, and showing "0′" in the app would have been worse than
  showing nothing.

## Kino Pilotů: a different platform, and a real bug in `base.fetch()`

Not Aerofilms — checked before writing anything, same as always. The whole
~3-week program is a Swiper.js carousel on the homepage (paired "day" and
"event" slides, confirmed the index pairing holds before relying on it), no
JSON-LD at all. Deliberately schedule-only: no director/runtime/poster is
scraped from this site, matching the architecture note to let TMDb carry
metadata — a per-screening detail page does exist with a poster and trailer,
but fetching one per unique film just for a bonus poster wasn't worth the
added requests.

**A real, general bug this site surfaced:** `apparent_encoding` (the
content-sniffing guesser) misread this page's bytes as `iso8859_10`, mangling
every accented character — even though the site correctly declares
`charset=UTF-8` in its own headers. `base.fetch()` used to unconditionally
prefer the guess over the declared charset, backwards from what should happen.
Fixed to trust a declared charset and only guess when none exists. The
Aerofilms cinemas never exposed this because their pages happened to guess
correctly too — luck, not correctness; the fix costs them nothing.

**Kino Pilotů bakes its programming strand into the title text itself**
("Céčko: Leviticus", "Kino Seniorů: Michael", "10 Let Kina Pilotů: Aftersun")
rather than exposing it as a separate chip like the Aerofilms cinemas do. Left
alone, this would have wrecked TMDb matching — "Céčko: Leviticus" barely
resembles "Leviticus". `_split_title()` recognises a small, explicit list of
known strand-label prefixes and splits them into `strand` instead — explicit
rather than "split on any colon", because real titles legitimately contain one
too (*Zootropolis: Město zvířat 2*, *Toy Story 5: Příběh hraček*). The suffix
case is safer to generalise: nothing here ever uses " / " or " + " as part of a
real title, so `"Šepot lesa / Český dabing"` splits cleanly, and — nicely —
`classify_tags()` already recognises "Český dabing" as a real
`language_version`, not just inert strand text, entirely for free.

**This also caught a systemic matcher bug, not specific to this cinema.**
`strip_event_branding()` used to treat a plain hyphen (and em/en dashes) as an
event-branding separator alongside "|", to catch cases like "...| NT Live". But
a dash-joined title/subtitle is an ordinary convention in real titles — Kino
Pilotů's *Dalajláma - Oceán moudrosti* proved it, silently truncated to just
"Dalajláma" before the search ever ran. Only "|" is actually safe to split on
unconditionally; it's the one separator ever observed in real event branding
and essentially never appears in an official title. Fixed, with a regression
test pinning both the fix and the original "| NT Live" case it must still
catch.

**Three titles needed overrides with a caveat worth knowing:** Kino Pilotů
gives no director or runtime at all, so unlike every other override in this
project, these three had no independent signal to verify against — just a
single unambiguous TMDb candidate and a precise semantic translation match
(*Co nám zbylo z lásky* → *The Love That Remains*, *Mrzutá rybka* → *The
Pout-Pout Fish*, *Šepot lesa* → *Whispering Forest*, a Białowieża Forest
documentary). Lower confidence than the others in this file, flagged as such
in each entry's comment.

**A print crash silently destroyed a correct result — fixed at the source.**
Resolving "Sirāt" (a real 2025 Cannes title) worked fine internally, the
correct record was already written to the cache — and then the *success*
print statement for its own title crashed on Windows' console codepage (which
can't represent 'ā'), and the surrounding `except Exception` caught that print
crash and overwrote the good result with a bogus "error" entry. Console text is
only for a human to skim; a crash there must never corrupt real data.
`sys.stdout.reconfigure(errors="replace")` at both CLI entrypoints fixes the
class of bug, not just this one title.

## Edison Filmhub: a third platform, and the richest data source yet

Not Aerofilms, not the Kino Pilotů carousel — a third distinct platform,
checked structurally before writing anything, same as every cinema here. No
JSON-LD, but a genuinely rich, cleanly server-rendered program table: real
per-screening language and subtitle notation ("JPN, Tit. CZ, EN" — Japanese,
Czech *and* English subtitles), a two-level tag structure (a broad category
like "Festivaly" plus, often, a specific named series like "Heatwave Horror"),
free-text notes (a Q&A guest's name, "+ úvod" for an introduction), and —
uniquely among all 7 cinemas — a genuine ticket-purchase link on a few
screenings, straight to a GoOut checkout page.

**`.desc`'s language notation is more structured signal than any Aerofilms
chip.** `_parse_desc()` turns "EN, Tit. CZ" into real `language`,
`english_friendly` and `language_version` fields — and `english_friendly` is
set from *either* the spoken language or the subtitle language being English,
matching the planning doc's own definition of the signal ("followable via
English audio *or* English subtitles").

**Two real title-cleaning bugs, found the same way as always: fetch, check,
then decide.**

- *"Toy Story 5: Příběh hraček (CZ DABING)"* is the exact same film already
  known from other cinemas as plain *"Toy Story 5: Příběh hraček"* — the
  suffix would have cost a duplicate, worse-scoring search and thrown away a
  real dubbing signal. `_strip_dabing_suffix()` recognises a parenthetical that
  actually mentions dabing and turns it into a tag; a same-fixture example,
  *"Posedlost (2026)"*, proves it's not just "strip any parenthetical" — that
  one is left alone by this specific rule.
- *"Posedlost (2026)"* turned out **not** to be harmless after all: TMDb's own
  search API returns **zero results** for the literal query with the year
  attached — not a fuzzy-scoring nuisance, a hard failure before the matcher
  ever sees a candidate — while "Posedlost" alone is already correctly
  resolved from other cinemas. `_strip_year_suffix()` removes a bare trailing
  `(YYYY)` unconditionally; unlike the dabing case there's no signal worth
  keeping, and a bare year is never part of a film's actual official title the
  way a subtitle-in-parentheses occasionally is.

**One more classify_tags() generalisation, prompted by "CZ DABING".** The
exact-match `VERSION_TAGS` dict caught bare "Dabing" and "Český dabing", but
not this cinema's own abbreviation. Rather than grow that dict with every new
combination as it's found, `classify_tags()` now recognises "dabing"/"titulky"
as a *substring* of any tag — covering whatever prefix or abbreviation the next
cinema invents too, not just this one.

**Both fixes were needed to avoid literal duplicates**, not just missed
matches: fixing a title-cleaning rule changes the computed cache key for that
title (`normalize_title(strip_...(title))`), which leaves the *old* key
orphaned in `films.json` as a permanently-wrong "unresolved" ghost — exactly
what happened to both "Dalajláma" (Milestone 4, Kino Pilotů) and "Posedlost"
here. The orphan is inert (no screening's `film_id` points at it anymore) but
worth cleaning up; a stray one now costs a few minutes of confusion later.

## Kino Ponrepo: built now, deliberately without a screening parser

Closed for reconstruction until 31.8 — the planning doc calls this out by name
as the test case for "a cinema temporarily has zero screenings." Checked
structurally before writing anything, same discipline as every other cinema:
every day link on the real program page carries a `--disabled` class, and there
is no hidden per-day content section anywhere on the page (no AJAX endpoint, no
React/Vue root — confirmed, not assumed). That's a genuinely verified "nothing
scheduled", not a page that needs JavaScript to show real content.

So the scraper reads the one thing that verifiably exists — the calendar's own
day links, whose `href="#2026-07-01"` already carries a full ISO date, no
Czech month-name parsing needed — and reports every one of them empty. It
deliberately does **not** contain speculative screening-extraction logic: there
is nothing to verify a parser against yet, and every other scraper in this
project was built by checking real structure first. Writing one now would
invert that and risk silently producing garbage the day the site changes.

Instead there's a tripwire: `_check_for_unexpected_content()` warns if a day
link is ever found *not* disabled, or if a matching `id="<date>"` content
section ever appears — either means the cinema has reopened and this file
needs the real screening parser, buildable and verifiable against real data at
last. Both trigger conditions are covered by tests that simulate the change,
confirming the tripwire actually fires rather than silently doing nothing.

`closed_until` flows through `run.py` into `screenings.json`'s cinema list the
same way `empty_dates` already did, and the app's `closedCinemasOn()` (built
back in Milestone 3, never yet exercised against a real closure) picks it up
with no changes needed — verified live: the Program screen now shows "Ponrepo
dnes nehraje."

## Phase 2: six more cinemas

With all 7 Phase 1 cinemas live, Phase 2 picked up "more cinemas" from the
planning doc's list. Same discipline as every cinema above: fetch the real
site, inspect its actual markup, and only then write a parser — never guess
at structure. Six distinct sites, five genuinely new platform shapes.

**Kino Lucerna** is a sixth Aerofilms cinema (a tip from Matěj, checked before
writing any code, same result as Přítomnost) — a three-line wrapper around
`aerofilms.scrape()`, with one quirk: the program lives on the homepage
itself, not `/program/`, which redirects there.

**Kino Atlas** is the first site here with AJAX pagination: only "today"
loads with the page; everything else comes from `GET
ajax_get_program.php?date=...&...`, an endpoint found by reading the page's
own inline JS and confirmed directly with `requests`. `data-next-cnt="0"` is
the real "no more data" signal — verified empirically by walking a live page
to exhaustion, not assumed from the first response. It also has the best
ticket-link coverage of any cinema: a real GoOut link on every single
screening.

**Kino MAT** is a fourth distinct platform, and surfaced a real bug: Czech
"červenec" (July) contains "červen" (June) as a literal prefix, so naive
substring month-matching misread every July screening as June. Fixed by
trying longer month names first. Format comes from a pictogram's `alt` text
(`<img alt="35mm film">`) rather than a text tag.

**Kino Kavalírka** has the richest per-screening data of any cinema in this
project — director/country/runtime bundled in one prose paragraph, and a
direct IMDb link for some films (`imdb_url`, captured on `Screening` but not
yet consumed by the resolver — TMDb supports an exact lookup by IMDb id, a
strong candidate for a focused follow-up). It also has its own version of
Kino Pilotů's title-branding problem ("Film & Drink: Pulp Fiction", "Divadlo v
kině: Romeo a Julie") and surfaced a real, general bug: a screening can carry
the *same* strand text twice at once (once from the title prefix, once from a
separate tag chip) — fixed generically in the shared `classify_tags()` with a
dedup guard, not just patched locally.

**Divadlo Za plotem** (the cinema at Prague's Bohnice psychiatric hospital,
also open to the public) is a WordPress/GenerateBlocks page-builder site — a
fifth distinct shape, with no clean "one container per screening" element at
all. What makes it parseable is that GenerateBlocks stamps each block with a
semantic (if invalidly repeated) `id` — `id="datum"`, `id="název-filmu"`,
`id="čas"`, ... — reliable to `find_all(id=...)` and zip together in document
order even though repeating an `id` is invalid HTML. Its own titles are ALL
CAPS; checked, not assumed, that the resolver's existing majority-spelling
canonicalisation already fixes this for free whenever the same film also
plays elsewhere (Toy Story 5 and Spider-Man both do, in this fixture).

**Kino 35** (the French Institute's cinema) rounds out this batch: a flat
`<table class="prog-list">` where date headers and screening rows alternate
directly, with per-screening detail (spoken language, subtitle languages, a
"Speciální večer" special-evening flag) carried on icon `title` attributes
rather than any free-text tag. The whole calendar loads in one request — no
pagination needed, confirmed by checking for one rather than assuming there
wasn't. The venue's stated summer recess ("KINO MÁ PRÁZDNINY") rides in the
same table as a notice row with no time; an empty time is exactly how it's
told apart from a real screening.

**One shared addition Kino Pilotů, Edison and now MAT/Kavalírka/Za
plotem/Kino 35 all needed:** working out a year for a date whose site never
prints one. Kino Pilotů's original per-scraper logic for this was pulled out
into `infer_years_for_months()` in `base.py` — the list of months only ever
runs forward, so a month that's lower than the one before it means the
calendar crossed a year boundary; everything else just carries the current
year forward.

A live end-to-end run across all 13 cinemas (581 screenings) plus a full
TMDb resolution pass, followed by a director/runtime cross-check of every
resolved film against what its cinema actually scraped, came back with no
wrong-film matches — the handful of runtime differences found (a few minutes,
on films like *Saving Private Ryan* and *Little Thief*) are consistent with
different release cuts, not mismatches.

## Two things about the Aerofilms cinemas specifically

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
constant, and the watchlist and filters all persist across reloads via
localStorage. (Premiéry was the last placeholder-data screen; see below —
it's real now too, and its saves live in the same unified watchlist as
everything else, not a separate mechanism.)

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

## Premieres calendar (Phase 2)

The planning doc left the premieres data source as an open "TBD": TMDb
upcoming-releases, or Czech distributor dates. Tested both realistic TMDb
options before writing anything real against either:

- **`/movie/upcoming?region=CZ`** — TMDb's purpose-built endpoint, but too
  thin: about a dozen results, one page.
- **`/discover/movie?region=CZ&with_release_type=2|3`** (limited + wide
  theatrical) — far more results, and cross-checking a sample against known
  upcoming titles confirmed the dates really are Czech theatrical dates, not
  some other country's, for genuinely new films.
- **ČSFD** — the ideal, actually Czech-curated source — is still blocked by
  the same Anubis bot-detection wall documented under "About the ČSFD link"
  below. Not available.

**One real gotcha, found by testing rather than assumed.** An old title with
an unrelated Czech *rerelease* entry (an anniversary theatrical run) can
still slip through the date-window filter: TMDb matches the filter against a
`release_dates` entry it doesn't surface back, and the `release_date` field
it *does* return is the film's original primary release — for *Avengers:
Endgame* that's 2019, years before the window supposedly filtered to. A
defensive floor (drop anything whose displayed date is before today) throws
this out along with any other case where the filter and the displayed date
disagree — `resolve/premieres.py`'s `dedupe_and_filter()`, unit-tested
against exactly this case in `tests/test_premieres.py`.

**Deliberately no popularity floor.** TMDb's discover results include a long
tail of very obscure, near-zero-popularity titles alongside the ones anyone
would recognise. Matěj's call: keep all of them — an arthouse premieres list
should surface the small, easy-to-miss title, which is exactly what a
popularity cutoff would hide first.

**Premieres share the exact film_id scheme films.json uses**
(`normalize_title` of the TMDb title, computed the same way in both files).
That one decision removed an entire parallel concept: the old placeholder
Premiéry stored a saved premiere under a synthetic `prem:<title>` watchlist
id (there was no real film behind it to key on), with its own render path
(`watchlistPremiereRow`, non-clickable, "no detail page to open") and its own
`store.togglePremiere()`/`savedPremieres()`. None of that exists anymore.
`data.js` merges `premieres.json`'s records straight into the same `films`
Map films.json populates (films.json wins on a collision, since it's
cinema-verified rather than TMDb-inferred), so a premiere is just a film that
happens to have no screenings yet — `filmById()`, `posterUrl()`, the detail
overlay, the watchlist row, all work on it completely for free. Saving a
premiere now really does carry straight over into a normal watchlisted film
the moment it starts screening, which the old synthetic-id scheme could
never do. (The `prem:` prefix survives only inside `store.js`'s `migrate()`,
for one already-superseded legacy storage key; nothing new is ever saved
under it, and an old entry degrades harmlessly — correct remembered title,
generic tile, "tento týden nehraje" — rather than crashing.)

**The month grid has no prototype reference.** `app-shell-cool.html` only
ever mocked Premiéry as a flat, month-grouped list; "month grid, not just a
list" was a Phase 2 wishlist line in the planning doc, not a design. Built to
match the rest of the system instead of inventing a new visual language: a
Monday-first 7-column grid (`renderPremieres()` in `screens.js`) with a small
dot — the day strip's own density dot, at calendar scale — marking any day
that has a premiere, so the month's shape reads before a single title does.
Below the grid, that month's premieres render as ordinary clickable film
cards, poster and all, opening the same detail overlay as any other film.

Month navigation is a click delegated to `[data-prem-month]` (screens.js
returns an HTML string like every other renderer here, so a plain `.onclick`
bound once at boot wouldn't survive a re-render replacing the buttons — same
reasoning as the existing `data-save`/`data-film` delegation). `app.js` owns
`activePremMonth`, resolved lazily the same way `activeDay` is: null until
the tab is first opened, defaulting to the current month if it has a
premiere or the soonest month that does, and from then on changed only by an
explicit nav tap.

**The grid days are tappable too** (added after Matěj tried to tap one and
nothing happened — a fair catch, a calendar that doesn't let you pick a date
isn't really a calendar). A day with a premiere is a real `<button>`
(everything else stays a plain non-interactive `<div>`); tapping it filters
the list below to just that day, with a heading and a "Celý měsíc" link back
out. The link and the day button share one `data-prem-day` attribute and one
delegated handler — tapping either the selected day again or its own clear
link toggles the same thing off. `app.js`'s `activePremDay` clears whenever
the month changes, since a day picked in a different month wouldn't apply to
the one now showing.

Refreshed weekly in the same GitHub Actions run as everything else
(`resolve.premieres`, after `resolve.films`).

## Extended filters: director and screenwriter

The Filtr sheet's other facets (Verze, Formát) are two or three fixed
options, shown as a static pill row. Director/screenwriter isn't that shape
at all — the current program alone has 100+ distinct names — so it's a
search-to-select field instead: type into "Tvůrci", matching names (from
films actually screening right now, not TMDb's whole universe, so a result
never leads to an empty list) appear as tappable suggestions, and a tap adds
a removable chip. No new data needed — `films.json` records already carry
`director`/`screenwriter` arrays from TMDb credits; `data.js`'s
`creatorNames()` just collects the distinct set across everything in
`state.screenings` right now.

Matching is OR-within-the-facet like every other filter here: a film with
several directors or writers passes if *any* selected name is among them,
same relationship version/format already have to their own multi-select
sets. `filters.creators` persists via `store.js` the same way, and folds
into the shared active-filter count and "Vymazat" reset alongside everything
else — it's an addition to the existing filter object, not a parallel
mechanism.

Dropped **production company** from the planning doc's original three-field
list: TMDb has the data, but it's a far less natural way for anyone to think
about "what do I want to see" than a director or writer, and adding a third
near-identical search field for it wasn't worth the UI weight for the value.

## Data attribution

Screening data is read from each cinema's own public program page. Film metadata
(Milestone 2) comes from TMDb, which requires attribution and their logo in the
app — not yet added, since that lands with the PWA in Milestone 3.
