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
   single list, the way the prototype had it. A premiere has no film_id (it
   isn't in the scraped data yet), so it goes in under a prefixed synthetic id.
   Keeping them in one list is what makes a saved premiere actually appear in
   Chci vidět — the previous split into two lists is the bug this fixes. */
export const PREMIERE_PREFIX = 'prem:';
export const premiereId = title => PREMIERE_PREFIX + title;
export const isPremiereId = id => id.startsWith(PREMIERE_PREFIX);
export const premiereTitle = id => id.slice(PREMIERE_PREFIX.length);

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

  /* ---- saved premieres (a view over the same watchlist) ---- */

  savedPremieres() {
    return this.watchlist().filter(isPremiereId).map(premiereTitle);
  },

  togglePremiere(title) {
    return this.toggleWatch(premiereId(title), title);
  },

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
    const filters = { mplex: false, version: new Set(), format: new Set(), enOnly: false };
    if (!saved) return filters;
    filters.mplex = !!saved.mplex;
    filters.enOnly = !!saved.enOnly;
    filters.version = new Set(saved.version || []);
    filters.format = new Set(saved.format || []);
    return filters;
  },

  saveFilters(filters) {
    write(KEYS.filters, {
      mplex: filters.mplex,
      enOnly: filters.enOnly,
      version: [...filters.version],
      format: [...filters.format],
    });
  },
};
