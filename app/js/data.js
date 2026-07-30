/* ==========================================================================
   Data loading and the model helpers built on top of it.

   Two files come out of the Python pipeline:
     screenings.json  what is playing, when, where (from the scrapers)
     films.json       what each film is (from TMDb)

   They join on `film_id`, which the resolver stamps onto every screening.
   That join key is deliberately computed in Python: the grouping rules are
   fuzzy (so "Odyssea" and "Oddysea" are one film) and have sequel guards, and
   duplicating that logic here would guarantee the two drift apart.
   ========================================================================== */

/* Where the generated JSON lives, relative to /app/index.html. If the app and
   data ever get deployed under different paths, this is the one line to change. */
const DATA_BASE = '../data';

/* TMDb image CDN. Sizes chosen per use: small for list rows, larger for the
   detail page's poster moment. */
const TMDB_IMG = 'https://image.tmdb.org/t/p';
export const POSTER_SMALL = `${TMDB_IMG}/w154`;
export const POSTER_LARGE = `${TMDB_IMG}/w342`;
export const BACKDROP = `${TMDB_IMG}/w780`;

export const state = {
  screenings: [],
  films: new Map(),      // film_id -> film record
  cinemas: [],
  generatedAt: null,
  dates: [],             // every date we have data for, sorted
  premieres: [],         // upcoming films, sorted by release_date ascending
};

/* ---------- loading ---------- */

export async function loadData() {
  const [screeningsRes, filmsRes, premieresRes] = await Promise.all([
    fetch(`${DATA_BASE}/screenings.json`, { cache: 'no-cache' }),
    fetch(`${DATA_BASE}/films.json`, { cache: 'no-cache' }),
    fetch(`${DATA_BASE}/premieres.json`, { cache: 'no-cache' }),
  ]);

  if (!screeningsRes.ok) throw new Error(`screenings.json: ${screeningsRes.status}`);
  if (!filmsRes.ok) throw new Error(`films.json: ${filmsRes.status}`);
  // Premieres are additive, not core — an outage or a missing file there
  // shouldn't take down the whole app the way missing screenings/films does.
  const premieresData = premieresRes.ok ? await premieresRes.json() : { premieres: [] };

  const screeningsData = await screeningsRes.json();
  const filmsData = await filmsRes.json();

  state.screenings = screeningsData.screenings || [];
  state.cinemas = screeningsData.cinemas || [];
  state.generatedAt = screeningsData.generated_at || null;

  state.films = new Map();
  for (const film of filmsData.films || []) state.films.set(film.film_id, film);

  /* Premieres use the same film_id scheme (normalize_title of the TMDb
     title) as films.json, so a film that's both an upcoming premiere and
     already has real screenings would collide on one id — films.json wins,
     since it's verified against a cinema's own page rather than inferred
     from TMDb alone. Folding premieres into the same films Map means
     filmById()/posterUrl()/etc. all work on a premiere for free, with no
     separate "is this a premiere or a real film" branch anywhere else. */
  state.premieres = premieresData.premieres || [];
  for (const film of state.premieres) {
    if (!state.films.has(film.film_id)) state.films.set(film.film_id, film);
  }

  /* The day strip shows today and the days ahead — a day that has fully passed
     drops off. (Past *screenings* on today itself still show, dimmed; only whole
     past days disappear.) If the data somehow contains only past days — e.g. a
     stale offline copy — fall back to showing all of them rather than an empty
     strip. */
  const allDates = [...new Set(state.screenings.map(s => s.date))].sort();
  const today = todayISO();
  const upcoming = allDates.filter(d => d >= today);
  state.dates = upcoming.length ? upcoming : allDates;
  return state;
}

/* ---------- looking things up ---------- */

export function filmFor(screening) {
  return state.films.get(screening.film_id) || null;
}

export function filmById(filmId) {
  return state.films.get(filmId) || null;
}

/* The title to show. Prefer the film's canonical spelling — when a cinema has a
   typo, the resolver already worked out which spelling is the real one. */
export function titleOf(screeningOrFilm) {
  const film = screeningOrFilm.film_id ? state.films.get(screeningOrFilm.film_id) : null;
  return (film && film.title_cz) || screeningOrFilm.title_cz || '';
}

export function screeningsForFilm(filmId) {
  return state.screenings
    .filter(s => s.film_id === filmId)
    .sort((a, b) => dateTimeOf(a) - dateTimeOf(b));
}

/* ---------- time ---------- */

/* Real clock. The prototype used a frozen NOW constant so it could demo
   "now-awareness" against fixed sample data; the real app uses the actual time. */
export function now() {
  return new Date();
}

export function dateTimeOf(screening) {
  return new Date(`${screening.date}T${screening.time}:00`);
}

export function isPast(screening) {
  return dateTimeOf(screening) < now();
}

export function todayISO() {
  const d = now();
  // Local date, not UTC — toISOString() would roll over at 02:00 Prague time.
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/* The soonest screening of a film that hasn't started yet. */
export function nextScreening(filmId) {
  return screeningsForFilm(filmId).find(s => !isPast(s)) || null;
}

/* ---------- cinema helpers ---------- */

const MULTIPLEX = ['Cinema City', 'CineStar', 'Premiere Cinemas'];

export function isMultiplex(cinemaName) {
  return MULTIPLEX.some(m => cinemaName.includes(m));
}

export function shortVenue(name) {
  return name.replace('Kino ', '');
}

/* Cinemas that told us they're shut on a given day — distinct from simply
   having nothing programmed. Ponrepo (closed for reconstruction) is the case
   this exists for. */
export function closedCinemasOn(dateISO) {
  return state.cinemas
    .filter(c => (c.closed_dates || []).includes(dateISO) ||
                 (c.empty_dates || []).includes(dateISO) ||
                 (c.closed_until && dateISO < c.closed_until))
    .map(c => c.name);
}

/* ---------- screening attributes ---------- */

/* These read real scraped fields. The prototype had to guess at version from
   the language and the strand note, which mislabelled Czech films — that
   heuristic is gone now that the scrapers record it per screening. */

export function is35mm(screening) {
  return (screening.format || '').includes('35');
}

export function isEnglishFriendly(screening) {
  return screening.english_friendly === true;
}

/* Returns null when a screening is presented the normal way. Cinemas only tag
   the exception (Aero tags "Dabing" and never "Titulky"), so showing nothing is
   the correct, honest rendering — not a missing value. */
export function versionOf(screening) {
  const version = screening.language_version || '';
  if (version === 'dabing') return { cls: 'dab', label: 'dab.' };
  if (version === 'titulky') return { cls: 'dab', label: 'tit.' };
  if (version === 'originál') return { cls: 'dab', label: 'orig.' };
  return null;
}

export function strandOf(screening) {
  return (screening.strand || '').trim() || null;
}

/* ---------- posters ---------- */

/* Poster URL for a film, or '' when we have nothing and the monogram tile
   should stand in. TMDb art is preferred; the cinema's own poster is the
   fallback, which is what keeps films TMDb couldn't identify from rendering
   as blank tiles. */
export function posterUrl(film, size = POSTER_SMALL) {
  if (!film) return '';
  if (film.poster_path) return size + film.poster_path;
  return film.poster_fallback_url || '';
}

export function backdropUrl(film) {
  if (!film) return '';
  if (film.backdrop_path) return BACKDROP + film.backdrop_path;
  return '';
}

/* First letter, for the monogram fallback tile. Skips leading punctuation so
   titles like "(re)fresh" don't render as "(". */
export function initialOf(title) {
  const stripped = (title || '').replace(/^[^A-Za-zÁ-Žá-ž0-9]+/, '');
  return (stripped[0] || title[0] || '?').toUpperCase();
}
