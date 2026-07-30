/* ==========================================================================
   The four screens, the detail overlay and search.

   Every renderer returns or writes HTML built from the joined data. Layout,
   class names and density all follow the prototype exactly — this file is the
   prototype's render functions with real data behind them.
   ========================================================================== */

import {
  state, filmFor, filmById, titleOf, screeningsForFilm, nextScreening,
  isPast, todayISO, shortVenue, is35mm, versionOf, strandOf, isEnglishFriendly,
  closedCinemasOn, posterUrl, backdropUrl, POSTER_LARGE, initialOf,
} from './data.js?v=16';

import {
  DOW, esc, dateOf, shortDate, longDay, whenLabel,
  posterTile, chip, runtimeLabel, densityDots,
} from './format.js?v=16';

import { store } from './store.js?v=16';

/* One save affordance, used everywhere a film can be added to Chci vidět —
   Program rows, Premiéry, the watchlist itself. A filled champagne heart when
   saved, an outline when not, matching the detail overlay's heart. (Premiéry
   used a +/✓ button before, which is the inconsistency this removes.) */
function heartButton(id, title, saved) {
  return `<button class="save-heart ${saved ? 'on' : ''}" data-save="${esc(id)}" data-title="${esc(title)}" aria-label="Chci vidět">${saved ? '♥' : '♡'}</button>`;
}

/* ---------- filtering ---------- */

export function passesFilters(screening, filters) {
  if (!filters.mplex && screening.cinema && isMultiplexName(screening.cinema)) return false;
  if (filters.enOnly && !isEnglishFriendly(screening)) return false;

  if (filters.format.size) {
    const format = is35mm(screening) ? '35mm' : 'dcp';
    if (!filters.format.has(format)) return false;
  }

  if (filters.version.size) {
    /* Real per-screening data now, not the prototype's heuristic. An untagged
       screening is the cinema's default presentation: for a foreign-language
       film that means subtitles, and for a Czech-language film it means the
       original. That distinction is what the old guess got wrong. */
    const version = screening.language_version || '';
    let key;
    if (version === 'dabing') key = 'dabovano';
    else if (version === 'titulky') key = 'titulky';
    else if (version === 'originál') key = 'ov';
    else key = isCzechLanguage(screening) ? 'ov' : 'titulky';
    if (!filters.version.has(key)) return false;
  }
  return true;
}

function isCzechLanguage(screening) {
  return (screening.language || '').toLowerCase().startsWith('češt');
}

function isMultiplexName(name) {
  return ['Cinema City', 'CineStar', 'Premiere Cinemas'].some(m => name.includes(m));
}

export function activeFilterCount(filters) {
  return (filters.mplex ? 1 : 0) + (filters.enOnly ? 1 : 0) + filters.version.size + filters.format.size;
}

/* ---------- day strip ---------- */

export function renderDays(el, activeDay, filters, onPick) {
  el.innerHTML = '';
  const today = todayISO();

  for (const date of state.dates) {
    const d = dateOf(date);
    const button = document.createElement('button');
    button.className = 'day' + (date === activeDay ? ' active' : '') + (date === today ? ' today' : '');
    const count = state.screenings.filter(s => s.date === date && passesFilters(s, filters)).length;
    button.innerHTML =
      `<span class="dow">${DOW[d.getDay()]}</span>` +
      `<span class="dnum">${shortDate(date)}</span>` +
      densityDots(count);
    button.onclick = () => onPick(date);
    el.appendChild(button);
  }
}

/* ---------- Program ---------- */

export function renderProgram(el, activeDay, group, filters) {
  const todays = state.screenings.filter(s => s.date === activeDay && passesFilters(s, filters));
  const closed = closedCinemasOn(activeDay);
  const closedNote = closed.length
    ? `<div class="closed-note">${esc(closed.map(shortVenue).join(', '))} ${closed.length > 1 ? 'dnes nehrají' : 'dnes nehraje'}.</div>`
    : '';

  if (!todays.length) {
    const anyThatDay = state.screenings.some(s => s.date === activeDay);
    el.innerHTML = closedNote + (anyThatDay
      ? emptyState('filter', 'Nic neodpovídá filtru', 'Zkus upravit nebo vymazat filtr v panelu Filtr.')
      : emptyState('program', 'Žádné projekce', 'Pro tento den nemáme žádný program.'));
    return;
  }

  el.innerHTML = closedNote + (group === 'film'
    ? renderFilmMode(todays)
    : renderCinemaMode(todays));
}

function renderFilmMode(todays) {
  /* Group by film_id, not by title string — that is what makes typo variants
     of the same film collapse into one row. */
  const byFilm = new Map();
  for (const s of todays) {
    if (!byFilm.has(s.film_id)) byFilm.set(s.film_id, []);
    byFilm.get(s.film_id).push(s);
  }

  const rows = [...byFilm.entries()].map(([filmId, shows]) => {
    shows.sort((a, b) => a.time.localeCompare(b.time));
    const upcoming = shows.filter(s => !isPast(s));
    const allPast = upcoming.length === 0;
    return { filmId, shows, allPast, sortKey: allPast ? '99:99' : upcoming[0].time };
  }).sort((a, b) =>
    a.allPast !== b.allPast ? (a.allPast ? 1 : -1) : a.sortKey.localeCompare(b.sortKey)
  );

  return rows.map(({ filmId, shows, allPast }) => {
    const film = filmById(filmId);
    const title = titleOf(shows[0]);
    const meta = [];

    /* Genres from TMDb read better than the raw language list, so they lead
       when we have them; language is the fallback for unresolved films. */
    if (film && film.genres && film.genres.length) meta.push(esc(film.genres.slice(0, 2).join(', ')));
    else {
      const langs = [...new Set(shows.map(s => s.language).filter(Boolean))].join(', ');
      if (langs) meta.push(esc(langs));
    }
    const strands = [...new Set(shows.map(strandOf).filter(Boolean))];

    return `<article class="film stagger ${allPast ? 'dim' : ''}" data-film="${esc(filmId)}">
      ${posterTile(film, title)}
      <div class="film-body">
        <div class="film-head">
          <h2 class="film-title">${esc(title)}</h2>
          <span class="runtime">${runtimeLabel(film)}</span>
        </div>
        <div class="film-meta">
          ${meta.map(m => `<span>${m}</span>`).join('')}
          ${strands.map(s => `<span class="strand">${esc(s)}</span>`).join('')}
        </div>
        <div class="showstrip">${shows.map(slotMarkup).join('')}</div>
      </div>
      ${heartButton(filmId, title, store.isSaved(filmId))}
    </article>`;
  }).join('');
}

function slotMarkup(screening) {
  const version = versionOf(screening);
  return `<span class="slot ${isPast(screening) ? 'past' : ''}">` +
    `<span class="st">${esc(screening.time)}</span>` +
    `<span class="sv">${esc(shortVenue(screening.cinema))}</span>` +
    (is35mm(screening) ? '<span class="sfmt">35mm</span>' : '') +
    (version ? `<span class="sdab">${esc(version.label)}</span>` : '') +
    '</span>';
}

function renderCinemaMode(todays) {
  const order = state.cinemas.map(c => c.name);
  const byVenue = new Map();
  for (const s of todays) {
    if (!byVenue.has(s.cinema)) byVenue.set(s.cinema, []);
    byVenue.get(s.cinema).push(s);
  }
  /* Any cinema not listed in cinemas[] still gets shown, appended after the
     known ones, so a new scraper's output can never silently vanish. */
  const venues = [...new Set([...order.filter(v => byVenue.has(v)), ...byVenue.keys()])];

  return venues.map(venue => {
    const shows = byVenue.get(venue).sort((a, b) => a.time.localeCompare(b.time));
    const allPast = shows.every(isPast);

    return `<section class="vgroup stagger ${allPast ? 'dim' : ''}">
      <div class="vgroup-head"><h2>${esc(shortVenue(venue))}</h2></div>
      ${shows.map(s => {
        const film = filmFor(s);
        const version = versionOf(s);
        const strand = strandOf(s);
        return `<div class="vrow ${isPast(s) ? 'past' : ''}" data-film="${esc(s.film_id)}">
          <span class="time">${esc(s.time)}</span>
          ${posterTile(film, titleOf(s), 'poster-sm')}
          <div class="vtitle">
            <div class="t-line">
              <span class="t">${esc(titleOf(s))}</span>
              <span class="vruntime">${runtimeLabel(film)}</span>
            </div>
            <div class="m">
              <span>${esc(s.language || '')}${strand ? ' · ' + esc(strand) : ''}</span>
              ${chip(version)}
              ${is35mm(s) ? '<span class="chip fmt">35mm</span>' : ''}
              ${isEnglishFriendly(s) ? '<span class="chip eng">ENG</span>' : ''}
            </div>
          </div>
          ${heartButton(s.film_id, titleOf(s), store.isSaved(s.film_id))}
        </div>`;
      }).join('')}
    </section>`;
  }).join('');
}

/* ---------- Premiéry ---------- */

const MONTHS = ['Leden', 'Únor', 'Březen', 'Duben', 'Květen', 'Červen',
                'Červenec', 'Srpen', 'Září', 'Říjen', 'Listopad', 'Prosinec'];

/* Monday-first, matching what a Czech reader expects from an actual calendar
   grid. format.js's DOW starts on Sunday (JS's own getDay() convention),
   which is right for the horizontal day strip but wrong here. */
const DOW_MON = ['PO', 'ÚT', 'ST', 'ČT', 'PÁ', 'SO', 'NE'];

const monthKey = iso => iso.slice(0, 7); // '2026-08-13' -> '2026-08'

// Monday-first weekday index of a month's 1st: 0 = Monday ... 6 = Sunday.
function firstWeekdayMon(year, monthIndex) {
  return (new Date(year, monthIndex, 1).getDay() + 6) % 7;
}

function daysInMonth(year, monthIndex) {
  return new Date(year, monthIndex + 1, 0).getDate();
}

/* activeMonth is a 'YYYY-MM' string and activeDay an ISO date or null, both
   owned by app.js the same way activeDay in Program is — this function only
   resolves a *default* month when none is set yet, it never mutates app.js's
   state itself. Month nav and day selection are both delegated clicks (see
   app.js) — [data-prem-month] and [data-prem-day] — matching how every other
   re-rendered button in this file works: there's no persistent element to
   attach a plain onclick to once a render replaces it. */
export function renderPremieres(el, activeMonth, activeDay) {
  const premieres = state.premieres;

  if (!premieres.length) {
    el.innerHTML = emptyState('program', 'Zatím žádné premiéry',
      'Jakmile budou známy nové termíny, objeví se tady.');
    return;
  }

  const months = [...new Set(premieres.map(p => monthKey(p.release_date)))].sort();
  const currentMonth = monthKey(todayISO());
  const month = (activeMonth && months.includes(activeMonth))
    ? activeMonth
    : (months.includes(currentMonth) ? currentMonth : months[0]);

  const [year, monthNum] = month.split('-').map(Number);
  const monthIndex = monthNum - 1;
  const inMonth = premieres.filter(p => monthKey(p.release_date) === month);
  const dayNumbers = new Set(inMonth.map(p => Number(p.release_date.slice(8, 10))));

  const todayISOStr = todayISO();
  const todayDay = todayISOStr.startsWith(month) ? Number(todayISOStr.slice(8, 10)) : null;

  // A selected day only makes sense within the month it belongs to — one
  // carried over from a different month (e.g. app.js's state not yet reset
  // on a month-nav tap) is treated as no selection rather than filtering
  // everything out.
  const selectedDay = activeDay && monthKey(activeDay) === month ? activeDay : null;

  const monthIdx = months.indexOf(month);
  const prevMonth = monthIdx > 0 ? months[monthIdx - 1] : '';
  const nextMonth = monthIdx < months.length - 1 ? months[monthIdx + 1] : '';

  let cells = '';
  const pad = firstWeekdayMon(year, monthIndex);
  for (let i = 0; i < pad; i++) cells += '<div class="prem-day empty"></div>';
  for (let day = 1; day <= daysInMonth(year, monthIndex); day++) {
    const has = dayNumbers.has(day);
    const iso = `${month}-${String(day).padStart(2, '0')}`;
    const classes = ['prem-day'];
    if (has) classes.push('has');
    if (day === todayDay) classes.push('today');
    if (iso === selectedDay) classes.push('selected');
    // Only a day that actually has a premiere is a tap target — tapping an
    // empty day would just clear the selection for no visible reason.
    cells += has
      ? `<button class="${classes.join(' ')}" data-prem-day="${iso}">` +
        `<span class="prem-daynum">${day}</span><span class="prem-dot"></span></button>`
      : `<div class="${classes.join(' ')}"><span class="prem-daynum">${day}</span></div>`;
  }

  const grid = `
    <div class="prem-nav-row">
      <button class="prem-nav" data-prem-month="${esc(prevMonth)}" ${prevMonth ? '' : 'disabled'} aria-label="Předchozí měsíc">‹</button>
      <h2 class="prem-month-label">${esc(MONTHS[monthIndex])} ${year}</h2>
      <button class="prem-nav" data-prem-month="${esc(nextMonth)}" ${nextMonth ? '' : 'disabled'} aria-label="Další měsíc">›</button>
    </div>
    <div class="prem-grid">
      ${DOW_MON.map(d => `<div class="prem-dow">${d}</div>`).join('')}
      ${cells}
    </div>`;

  const shown = selectedDay ? inMonth.filter(p => p.release_date === selectedDay) : inMonth;

  // Tapping a marked day filters the list to just that day; this heading is
  // the only way back to the whole month short of tapping the day again.
  const listHead = selectedDay
    ? `<div class="prem-list-head">
         <span class="sec-head">${esc(longDay(selectedDay))}</span>
         <button class="prem-clear" data-prem-day="${selectedDay}">Celý měsíc</button>
       </div>`
    : '';

  /* Real films now — TMDb-resolved and merged into state.films by data.js —
     so unlike the old placeholder these are genuinely clickable: data-film
     opens the same detail overlay every other film uses, poster and all,
     even though there's nothing in "Tento týden hrají" yet. */
  const list = shown.map(p => {
    const meta = [];
    if (p.genres && p.genres.length) meta.push(esc(p.genres.slice(0, 2).join(', ')));
    return `<article class="film stagger" data-film="${esc(p.film_id)}">
      ${posterTile(p, p.title_cz)}
      <div class="film-body">
        <div class="film-head">
          <h2 class="film-title">${esc(p.title_cz)}</h2>
          <span class="runtime">${runtimeLabel(p)}</span>
        </div>
        <div class="film-meta">
          ${meta.map(m => `<span>${m}</span>`).join('')}
          <span class="strand">premiéra ${shortDate(p.release_date)}</span>
        </div>
      </div>
      ${heartButton(p.film_id, p.title_cz, store.isSaved(p.film_id))}
    </article>`;
  }).join('');

  el.innerHTML = grid + listHead + `<div class="prem-list">${list}</div>` +
    `<p class="attribution">Termíny premiér poskytuje TMDb — distributor je ještě může posunout.</p>`;
}

/* ---------- Chci vidět ---------- */

export function renderWatchlist(el) {
  const saved = store.watchlist();

  if (!saved.length) {
    el.innerHTML = emptyState('want', 'Chci vidět',
      'Ťukni na srdíčko u filmu a přidej ho sem. Uvidíš rovnou, kdy nejbližší projekce hraje.');
    return;
  }

  const rows = saved.map(watchlistFilmRow).join('');

  el.innerHTML =
    `<div class="sec-head stagger">${saved.length} ${plural(saved.length)}</div>` + rows;
}

function watchlistFilmRow(filmId) {
  const film = filmById(filmId);
  const all = screeningsForFilm(filmId);
  /* A watchlisted film may not be in this week's data at all — either it has
     stopped screening or it was never in the program. Keep the stored title so
     the row never renders blank. */
  const title = (film && film.title_cz) || store.titleFor(filmId) || filmId;
  const next = nextScreening(filmId);

  const meta = [];
  if (film && film.genres && film.genres.length) meta.push(esc(film.genres.slice(0, 2).join(', ')));
  else {
    const langs = [...new Set(all.map(s => s.language).filter(Boolean))].join(', ');
    if (langs) meta.push(esc(langs));
  }

  const strip = next
    ? `<div class="showstrip"><span class="slot">
         <span class="st">${esc(whenLabel(next))}</span>
         <span class="sv">${esc(shortVenue(next.cinema))}</span>
         ${is35mm(next) ? '<span class="sfmt">35mm</span>' : ''}
       </span></div>`
    : `<div class="showstrip"><span class="slot none">tento týden nehraje</span></div>`;

  return `<div class="row stagger" data-film="${esc(filmId)}">
    ${posterTile(film, title)}
    <div class="film-body">
      <div class="film-head">
        <h2 class="film-title">${esc(title)}</h2>
        <span class="runtime">${runtimeLabel(film)}</span>
      </div>
      <div class="film-meta">${meta.map(m => `<span>${m}</span>`).join('')}</div>
      ${strip}
    </div>
    ${heartButton(filmId, title, true)}
  </div>`;
}

function plural(n) {
  if (n === 1) return 'uložený film';
  if (n >= 2 && n <= 4) return 'uložené filmy';
  return 'uložených filmů';
}

/* ---------- Profil ---------- */

export function renderProfile(el) {
  const generated = state.generatedAt
    ? new Date(state.generatedAt).toLocaleString('cs-CZ', { dateStyle: 'long', timeStyle: 'short' })
    : '—';

  el.innerHTML = emptyState('profile', 'Profil',
    'Tvůj filmový deník, oblíbená kina a historie zhlédnutých filmů se objeví tady, až přidáme sledování.') +
    `<p class="attribution">
      Program aktualizován ${esc(generated)}<br>
      ${state.screenings.length} projekcí · ${state.films.size} filmů
    </p>`;
}

/* ---------- detail overlay ---------- */

export function fillDetail(filmId) {
  const film = filmById(filmId);
  /* Only today and later. screeningsForFilm() returns full history for a
     film, so without this filter a film that played last week keeps showing
     those stale, grayed-out rows here forever — not "past today", genuinely
     gone days. Comparing ISO date strings against todayISO() means this is
     computed fresh from the real clock every time the overlay opens, so it
     rolls over on its own at midnight with no separate "refresh" needed. */
  const shows = screeningsForFilm(filmId).filter(s => s.date >= todayISO());
  const title = (film && film.title_cz) || (shows[0] && shows[0].title_cz) || store.titleFor(filmId) || filmId;

  /* hero */
  const back = document.getElementById('ov-back');
  const backdrop = backdropUrl(film);
  if (backdrop) {
    back.style.setProperty('--backdrop', `url("${backdrop}")`);
    back.classList.add('has-image');
  } else {
    back.classList.remove('has-image');
    back.style.removeProperty('--backdrop');
  }

  const posterEl = document.getElementById('ov-poster');
  const posterSrc = posterUrl(film, POSTER_LARGE);
  posterEl.innerHTML = esc(initialOf(title)) +
    (posterSrc ? `<img src="${esc(posterSrc)}" alt="" onload="this.classList.add('loaded')" onerror="this.remove()">` : '');

  document.getElementById('ov-title').textContent = title;
  /* CZ/EN rule from the planning doc: Czech title leads; the English title is
     an italic subtitle here on the detail page only, never in lists. */
  const en = film && film.title_en && film.title_en !== title ? film.title_en : '';
  document.getElementById('ov-en').textContent = en;

  /* facts line */
  const facts = [];
  if (film && film.year) facts.push(`<span>${film.year}</span>`);
  if (film && film.runtime_min) facts.push(`<span>${film.runtime_min}′</span>`);
  if (film && film.age_rating) facts.push(`<span class="rating">${esc(film.age_rating)}</span>`);
  document.getElementById('ov-facts').innerHTML = facts.join('<span class="dot">·</span>');

  document.getElementById('ov-genres').innerHTML =
    ((film && film.genres) || []).map(g => `<span class="ov-genre">${esc(g)}</span>`).join('');

  /* trailer — only offered when we actually have one */
  const trailer = document.getElementById('ov-trailer');
  const key = film && film.trailer_youtube_key;
  if (key) {
    trailer.style.display = '';
    trailer.dataset.trailer = key;
    trailer.style.backgroundImage =
      `linear-gradient(rgba(10,12,16,.35), rgba(10,12,16,.55)), url("https://i.ytimg.com/vi/${key}/hqdefault.jpg")`;
    document.getElementById('ov-tlabel').textContent = 'Přehrát trailer';
  } else {
    trailer.style.display = 'none';
    trailer.dataset.trailer = '';
  }

  /* synopsis */
  const synopsis = (film && film.synopsis) || '';
  document.getElementById('ov-synopsis').textContent =
    synopsis || 'Anotaci k tomuto filmu zatím nemáme.';
  /* Say plainly when the text is English rather than passing it off as Czech. */
  const langNote = document.getElementById('ov-synopsis-lang');
  langNote.textContent = (film && film.synopsis_language === 'en') ? 'anotace v angličtině' : '';

  /* credits */
  const credits = [
    ['Režie', film && film.director],
    ['Scénář', film && film.screenwriter],
    ['Hrají', film && film.cast],
  ];
  document.getElementById('ov-credits').innerHTML = credits
    .map(([role, people]) => {
      const value = Array.isArray(people) && people.length ? people.join(', ') : '—';
      return `<div class="ov-credit"><span class="role">${role}</span><span class="val">${esc(value)}</span></div>`;
    }).join('');

  /* ČSFD — a real link now. Hidden when we have nothing to point at. */
  const csfd = document.getElementById('ov-csfd');
  if (film && film.csfd_url) {
    csfd.style.display = '';
    csfd.href = film.csfd_url;
  } else {
    csfd.style.display = 'none';
  }

  /* save state */
  const saveBtn = document.getElementById('ov-save');
  const saved = store.watchlist().includes(filmId);
  saveBtn.classList.toggle('saved', saved);
  saveBtn.textContent = saved ? '♥' : '♡';

  /* this week's screenings, grouped by day, with real booking links */
  const byDay = new Map();
  for (const s of shows) {
    if (!byDay.has(s.date)) byDay.set(s.date, []);
    byDay.get(s.date).push(s);
  }

  document.getElementById('ov-screenings').innerHTML = [...byDay.entries()].map(([date, list]) => {
    return `<div class="ov-day">${esc(longDay(date))}</div>
      <div class="ov-scard">${list.map(s => {
        const past = isPast(s);
        const version = versionOf(s);
        const extras = [
          is35mm(s) ? '35mm' : '',
          version ? version.label : '',
          isEnglishFriendly(s) ? 'ENG' : '',
        ].filter(Boolean).join(' · ');
        const buy = past
          ? '<span class="buy past">proběhlo</span>'
          : `<a class="buy" href="${esc(s.booking_url || '#')}" target="_blank" rel="noopener noreferrer">Vstupenky ↗</a>`;
        return `<div class="ov-srow ${past ? 'past' : ''}">
          <span class="time">${esc(s.time)}</span>
          <span class="cin">${esc(shortVenue(s.cinema))}${extras ? ' · ' + esc(extras) : ''}</span>
          ${buy}
        </div>`;
      }).join('')}</div>`;
  }).join('') || '<p style="color:var(--text-3);font-size:13px">Tento týden nehraje.</p>';

  return filmId;
}

/* ---------- search ---------- */

export function runSearch(query, resultsEl) {
  const q = query.trim().toLowerCase();

  if (!q) {
    resultsEl.innerHTML = '<p class="search-hint">Zadej název filmu, kino, režiséra nebo herce.</p>';
    return;
  }

  /* Searches everything we now know about a film, not just its Czech title —
     the English title, director and cast all became searchable with TMDb data. */
  const hits = new Map();
  for (const s of state.screenings) {
    if (hits.has(s.film_id)) continue;
    const film = filmFor(s);
    const haystack = [
      titleOf(s), s.cinema, s.language, s.strand,
      film && film.title_en, film && film.original_title,
      film && (film.director || []).join(' '),
      film && (film.cast || []).join(' '),
    ].filter(Boolean).join(' ').toLowerCase();

    if (haystack.includes(q)) hits.set(s.film_id, s);
  }

  if (!hits.size) {
    resultsEl.innerHTML = `<p class="search-hint">Nic nenalezeno pro „${esc(query)}".</p>`;
    return;
  }

  resultsEl.innerHTML = [...hits.keys()].map(filmId => {
    const film = filmById(filmId);
    const next = nextScreening(filmId);
    const title = (film && film.title_cz) || hits.get(filmId).title_cz;
    const sub = next
      ? `${whenLabel(next)} · ${shortVenue(next.cinema)}`
      : 'tento týden nehraje';
    return `<div class="sr-item" data-film="${esc(filmId)}">
      ${posterTile(film, title, 'sr-poster')}
      <div class="sr-body">
        <div class="sr-title">${esc(title)}</div>
        <div class="sr-sub">${esc(sub)}</div>
      </div>
    </div>`;
  }).join('');
}

/* ---------- shared empty state ---------- */

const EMPTY_ICONS = {
  filter: '<path d="M3 5h18M6 12h12M10 19h4" stroke-linecap="round"/>',
  program: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v16"/>',
  want: '<path d="M6 4h12a1 1 0 011 1v15l-7-4-7 4V5a1 1 0 011-1z"/>',
  profile: '<circle cx="12" cy="8.5" r="3.7"/><path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6"/>',
};

function emptyState(icon, title, sub) {
  return `<div class="empty-state stagger">
    <div class="es-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">${EMPTY_ICONS[icon] || ''}</svg>
    </div>
    <p class="es-title">${esc(title)}</p>
    <p class="es-sub">${esc(sub)}</p>
  </div>`;
}
