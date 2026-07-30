/* ==========================================================================
   localStorage persistence.

   The prototype kept the watchlist and filters in memory only, so a reload
   wiped them — flagged in the pre-build audit. Everything personal lives here
   now, client-side, matching the planning doc's decision to defer accounts.

   The watchlist stores film_ids, not titles, so a film keeps its place even if
   a cinema changes the spelling it advertises. Titles are cached alongside
   purely so a saved film can still be named after it drops out of the current
   week's data.
   ========================================================================== */

const KEYS = {
  watchlist: 'beam.watchlist',
  titles: 'beam.titles',
  premieres: 'beam.premieres',   // legacy — folded into watchlist by migrate()
  filters: 'beam.filters',
};

/* Premieres and screening films share one watchlist so that "Chci vidět" is a
   single list, the way the prototype had it. This prefix is legacy now: back
   when Premiéry was placeholder data with no real film behind it, a saved
   premiere had nothing to key on but its title, so it went into the
   watchlist under this synthetic id. Now that premieres.json resolves real
   TMDb films, a premiere gets the exact same film_id a real screening of it
   would — computed the same way (normalize_title of the TMDb title) in
   resolve/premieres.py — so a save carries straight over the moment the film
   actually starts screening, with no separate premiere concept needed at
   all. Kept only so migrate() can still place any pre-existing legacy
   `beam.premieres` entry somewhere sane; nothing new is ever saved under it. */
const PREMIERE_PREFIX = 'prem:';
const premiereId = title => PREMIERE_PREFIX + title;

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    /* Private-browsing modes and full quotas both throw here. Losing saved
       state is a nuisance, not a reason to break the whole app. */
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* Ignore — see above. */
  }
}

export const store = {
  /* ---- watchlist (Chci vidět) ---- */

  watchlist() {
    return read(KEYS.watchlist, []);
  },

  isSaved(filmId) {
    return this.watchlist().includes(filmId);
  },

  toggleWatch(filmId, title) {
    const list = this.watchlist();
    const index = list.indexOf(filmId);
    if (index >= 0) list.splice(index, 1);
    else list.push(filmId);
    write(KEYS.watchlist, list);
    if (title) this.rememberTitle(filmId, title);
    return list.includes(filmId);
  },

  /* ---- remembered titles ---- */

  rememberTitle(filmId, title) {
    const titles = read(KEYS.titles, {});
    titles[filmId] = title;
    write(KEYS.titles, titles);
  },

  titleFor(filmId) {
    return read(KEYS.titles, {})[filmId] || '';
  },

  /* ---- legacy premiere migration ---- */

  /* One-time move of any legacy `beam.premieres` entries into the unified
     watchlist, so nothing saved before this change is lost. */
  migrate() {
    const legacy = read(KEYS.premieres, null);
    if (!Array.isArray(legacy) || !legacy.length) return;
    const list = this.watchlist();
    for (const title of legacy) {
      const id = premiereId(title);
      if (!list.includes(id)) {
        list.push(id);
        this.rememberTitle(id, title);
      }
    }
    write(KEYS.watchlist, list);
    try { localStorage.removeItem(KEYS.premieres); } catch { /* ignore */ }
  },

  /* ---- filters ---- */

  /* Sets don't survive JSON, so they're stored as arrays and rehydrated. */
  loadFilters() {
    const saved = read(KEYS.filters, null);
    const filters = { mplex: false, version: new Set(), format: new Set(), enOnly: false, creators: new Set() };
    if (!saved) return filters;
    filters.mplex = !!saved.mplex;
    filters.enOnly = !!saved.enOnly;
    filters.version = new Set(saved.version || []);
    filters.format = new Set(saved.format || []);
    filters.creators = new Set(saved.creators || []);
    return filters;
  },

  saveFilters(filters) {
    write(KEYS.filters, {
      mplex: filters.mplex,
      enOnly: filters.enOnly,
      version: [...filters.version],
      format: [...filters.format],
      creators: [...filters.creators],
    });
  },
};
