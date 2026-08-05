/* ==========================================================================
   The four screens, the detail overlay and search.

   Every renderer returns or writes HTML built from the joined data. Layout,
   class names and density all follow the prototype exactly — this file is the
   prototype's render functions with real data behind them.
   ========================================================================== */

import {
  state, filmFor, filmById, titleOf, screeningsForFilm, nextScreening,
  isPast, todayISO, shortVenue, is35mm, versionOf, strandOf, isEnglishFriendly,
  closedCinemasOn, posterUrl, backdropUrl, POSTER_LARGE, initialOf, isMultiplex, multiplexChainOf,
} from './data.js?v=59';

import {
  DOW, esc, fold, dateOf, shortDate, longDay, whenLabel, yearIfDifferent,
  posterTile, chip, runtimeLabel, densityDots,
} from './format.js?v=59';

import { store } from './store.js?v=59';
import { isPushSupported } from './push.js?v=59';
import { initCinemaMap } from './map.js?v=59';

/* One save affordance, used everywhere a film can be added to Chci vidět —
   Program rows, Premiéry, the watchlist itself. A filled champagne heart when
   saved, an outline when not, matching the detail overlay's heart. (Premiéry
   used a +/✓ button before, which is the inconsistency this removes.)

   This button sits as a sibling inside a row that itself now carries
   role="button" (added 2026-07-31, for keyboard/screen-reader access to
   opening a film's detail — see the film/vrow/row/sr-item templates below),
   which technically nests one interactive control inside another — an ARIA
   authoring smell in the strict sense. Not restructuring the DOM/CSS to avoid
   it: this is the same well-tolerated "row with a trailing icon action"
   pattern most list UIs with a favorite/star affordance use (Gmail's star,
   a tweet's like button), real interactive elements are still independently
   reachable in the accessibility tree regardless of the ancestor's role, and
   a full template/layout restructure across five call sites isn't worth it
   for a pattern this common and this low-risk in practice. */
/* FIX (impeccable critique, P3): the ♡/♥ glyph swap and .on class change
   were visual-only — aria-label stayed the static "Chci vidět" in both
   states, so a screen-reader user activating this control had no way to
   tell whether it was about to save or remove the film. aria-pressed plus
   a label naming the actual next action (not just the feature's name) match
   syncSaveButtons() below, which keeps both in sync on every later toggle. */
function heartButton(id, title, saved) {
  const label = saved ? 'Odebrat z Chci vidět' : 'Chci vidět';
  return `<button class="save-heart ${saved ? 'on' : ''}" data-save="${esc(id)}" data-title="${esc(title)}" aria-label="${label}" aria-pressed="${saved}">${saved ? '♥' : '♡'}</button>`;
}

/* ---------- filtering ---------- */

export function passesFilters(screening, filters) {
  if (!filters.mplex && screening.cinema && isMultiplex(screening.cinema)) return false;
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

  if (filters.creators.size || filters.genres.size) {
    const film = filmFor(screening);

    if (filters.creators.size) {
      // A film can have several directors and writers; any one of them
      // matching a selected name is enough — OR within the facet, same as
      // every other multi-select filter here, not "match every selection".
      const people = [...((film && film.director) || []), ...((film && film.screenwriter) || [])];
      if (!people.some(name => filters.creators.has(name))) return false;
    }

    if (filters.genres.size) {
      const genres = (film && film.genres) || [];
      if (!genres.some(genre => filters.genres.has(genre))) return false;
    }
  }
  return true;
}

function isCzechLanguage(screening) {
  return (screening.language || '').toLowerCase().startsWith('češt');
}

/* isMultiplex lives in data.js next to the other cinema helpers — this file
   used to carry its own copy with the chain list hardcoded a second time,
   which meant adding a chain in one place and silently not the other. */

export function activeFilterCount(filters) {
  return (filters.mplex ? 1 : 0) + (filters.enOnly ? 1 : 0) + filters.version.size + filters.format.size +
    filters.creators.size + filters.genres.size;
}

/* screeningsForFilm()/nextScreening() in data.js return a film's full,
   unfiltered schedule — correct for data.js to stay filter-agnostic, since
   `filters` is session state that belongs with the screens that render it,
   not with the data layer. But that split had a real bug hiding in it: three
   call sites below (the watchlist row, the detail overlay, and search's next-
   screening subtitle) read straight from those unfiltered functions, so a
   film's "next screening" or "playing this week" list quietly ignored every
   Filtr setting — including the multiplex toggle. A multiplex-heavy film
   would show hundreds of Cinema City/Premiere Cinemas showtimes here even
   with multiplexes switched off in Program, the exact opposite of what the
   toggle promises. These two wrappers are the fix: filter through the same
   passesFilters() Program already uses, right where `filters` is actually in
   scope. */
function filteredScreeningsForFilm(filmId, filters) {
  return screeningsForFilm(filmId).filter(s => passesFilters(s, filters));
}

function filteredNextScreening(filmId, filters) {
  return filteredScreeningsForFilm(filmId, filters).find(s => !isPast(s)) || null;
}

/* ---------- day strip ---------- */

/* FIX (impeccable critique): state.dates (data.js) is every distinct date
   that has *any* screening, today onward, entirely unbounded — in practice
   that's 40+ chips tapering off into single opera/ballet-relay dates months
   out. Three weeks covers what this strip is actually for (picking tonight,
   tomorrow, this weekend); anything past that is a rare lookup, not
   something worth 6+ screen-widths of horizontal swiping to reach. It's
   still reachable — see the trailing "+N" chip below and renderDateJump(). */
const PROGRAM_STRIP_DAYS = 21;

export function renderDays(el, activeDay, filters, onPick) {
  el.innerHTML = '';
  const today = todayISO();
  const visible = state.dates.slice(0, PROGRAM_STRIP_DAYS);
  const beyond = state.dates.length - visible.length;

  for (const date of visible) {
    const d = dateOf(date);
    const button = document.createElement('button');
    button.className = 'day' + (date === activeDay ? ' active' : '') + (date === today ? ' today' : '');
    /* FIX (impeccable critique, P2): champagne marking the active day is,
       by design, the app's only visual "this one" signal — which means it
       was also its only signal, full stop, for anyone not reading it
       visually. aria-current is the standard way a date-picker-like control
       announces which value is currently selected. */
    if (date === activeDay) button.setAttribute('aria-current', 'date');
    const count = state.screenings.filter(s => s.date === date && passesFilters(s, filters)).length;
    const year = yearIfDifferent(date);
    button.innerHTML =
      `<span class="dow">${DOW[d.getDay()]}</span>` +
      `<span class="dnum">${shortDate(date)}</span>` +
      (year ? `<span class="dyear">${year}</span>` : '') +
      densityDots(count);
    button.onclick = () => onPick(date);
    el.appendChild(button);
  }

  if (beyond > 0) {
    const more = document.createElement('button');
    // Active here means "the selected day isn't one of the visible chips at
    // all" — the one case where this strip would otherwise show no active
    // state anywhere, leaving no sign of where 'today's selection actually is.
    const activeBeyond = activeDay && !visible.includes(activeDay);
    more.className = 'day day-more' + (activeBeyond ? ' active' : '');
    if (activeBeyond) more.setAttribute('aria-current', 'date');
    more.setAttribute('data-open-date-jump', '');
    more.setAttribute('aria-label', 'Vybrat další den');
    more.innerHTML = `<span class="dow">DALŠÍ</span><span class="dnum">+${beyond}</span>`;
    el.appendChild(more);
  }
}

/* ---------- Program ---------- */

export function renderProgram(el, activeDay, group, filters) {
  const todays = state.screenings.filter(s => s.date === activeDay && passesFilters(s, filters));
  const closed = closedCinemasOn(activeDay);
  /* FIX (impeccable critique, minor): closedCinemasOn() was already
     date-correct, but the copy always said "dnes" ("today") regardless of
     which day was actually selected — true on today, wrong on every other
     day the strip (or the date-jump sheet) lets you view. */
  const isToday = activeDay === todayISO();
  const when = isToday ? 'dnes' : `${shortDate(activeDay)}${yearIfDifferent(activeDay)}`;
  const closedNote = closed.length
    ? `<div class="closed-note">${esc(closed.map(shortVenue).join(', '))} ${when} ${closed.length > 1 ? 'nehrají' : 'nehraje'}.</div>`
    : '';

  if (!todays.length) {
    const anyThatDay = state.screenings.some(s => s.date === activeDay);
    /* FIX (impeccable critique, minor): this used to just tell you to go
       find Filtr yourself. A direct data-clear-filters button (delegated in
       app.js, same as every other dynamically-rendered control here) skips
       that trip for the common case — you're not here to fine-tune the
       filter, you just want to see something. */
    el.innerHTML = closedNote + (anyThatDay
      ? emptyState('filter', 'Nic neodpovídá filtru', 'Zkus upravit nebo vymazat filtr v panelu Filtr.',
          '<button class="es-action" data-clear-filters>Vymazat filtr</button>')
      : emptyState('program', 'Žádné projekce', 'Pro tento den nemáme žádný program.'));
    return;
  }

  el.innerHTML = closedNote + (group === 'film'
    ? renderFilmMode(todays)
    : renderCinemaMode(todays));
}

/* FIX (impeccable critique, P1): at the hour this app exists for — most of
   an evening — Program used to render every film that screened at all
   today, dimmed to 45% once its last showing passed. On a normal Friday
   night that's dozens of dead rows outweighing the one still-catchable
   film, and the critique measured that dimmed text failing WCAG AA (the
   rows stayed interactive, so the "inactive control" exemption doesn't
   apply either). Films/venues with nothing left today now collapse behind
   one native <details> disclosure at the bottom — same shape already
   shipped for multiplex chains in the detail overlay — rather than being
   deleted or merely dimmed. Once a user deliberately opens it, there's no
   reason to dim the contents further: the disclosure itself is the
   "secondary" signal, so what's inside renders at full, legible opacity,
   which is what actually resolves the contrast finding rather than hunting
   for a "good enough" dim level. */
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

  const upcoming = rows.filter(r => !r.allPast);
  const past = rows.filter(r => r.allPast);

  return upcoming.map(filmRowMarkup).join('') +
    todayDoneNotice(upcoming.length, past.length) +
    pastGroupMarkup(past, filmRowMarkup, filmCount);
}

function filmRowMarkup({ filmId, shows }, stagger = true) {
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

  return `<article class="film${stagger ? ' stagger' : ''}" data-film="${esc(filmId)}" role="button" tabindex="0" aria-label="${esc(title)}">
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
      <div class="showstrip">${showstripMarkup(shows)}</div>
    </div>
    ${heartButton(filmId, title, store.isSaved(filmId))}
  </article>`;
}

/* Shared by both Program modes — a collapsed "N filmů/kin already done for
   today" disclosure. Closed by default, real <details>/<summary> so it's
   keyboard- and screen-reader-operable with no extra JS, exactly the
   pattern already shipped for multiplex chains in the detail overlay. */
function pastGroupMarkup(items, markupFn, countLabel) {
  if (!items.length) return '';
  /* stagger=false: .stagger's entrance animation (rise .46s ... both) never
     gets to run on content born inside a closed <details> — that content is
     display:none at render time, so the animation can't start, and
     fill-mode `both` leaves it stuck at the *from* keyframe (opacity: 0)
     forever once the disclosure opens instead of playing through to
     opacity: 1. Found live: the group opened, but everything inside stayed
     invisible. These rows are revealed by the user's own tap, not a fresh
     screen becoming active, so skipping the stagger here is also just the
     more correct behavior, not only the fix for the bug. */
  return `<details class="past-group">
    <summary>
      <span class="past-group-label">Dnes již proběhlo</span>
      <span class="past-group-count">${countLabel(items.length)}</span>
    </summary>
    <div class="past-group-body">${items.map(item => markupFn(item, false)).join('')}</div>
  </details>`;
}

function filmCount(n) {
  if (n === 1) return '1 film';
  if (n >= 2 && n <= 4) return `${n} filmy`;
  return `${n} filmů`;
}

/* Shown only when today had programming and every bit of it has already
   played — distinct from "no data for today at all" (handled separately in
   renderProgram()). A direct, honest answer to the moment the app is
   actually opened in the evening, rather than just a wall of dimmed rows:
   points at the next day that actually has something on, which may not be
   literally tomorrow (a quiet Monday can be empty). */
function todayDoneNotice(upcomingCount, pastCount) {
  if (upcomingCount > 0 || !pastCount) return '';
  const next = state.dates.find(d => d > todayISO());
  const jump = next
    ? `<button class="today-done-jump" data-jump-day="${esc(next)}">Program na ${esc(shortDate(next))} →</button>`
    : '';
  return `<div class="today-done stagger"><span>Dnes už nic dalšího nehraje.</span>${jump}</div>`;
}

/* Program row preview cap, found by the 2026-07-31 design critique: with
   multiplexes on, a popular title's showstrip could run 50-70+ chips
   (Cinema City alone has six Prague locations). This is a glanceable
   preview, not the place to enumerate every showing — that's what the
   detail overlay is for, which the row already opens on tap, so "+N
   dalších" needs no click handler of its own.

   Past screenings are dropped from the preview entirely when the film has
   any upcoming ones — a dimmed "14:00 proběhlo" chip earns its place in the
   detail overlay's fuller day-by-day list, but adds nothing to a compact
   "when can I still catch this" preview. If every screening for the day
   has already passed, those are shown instead (still capped), since that's
   all there is to preview. */
const SHOWSTRIP_LIMIT = 5;

function showstripMarkup(shows) {
  const upcoming = shows.filter(s => !isPast(s));
  const relevant = upcoming.length ? upcoming : shows;
  const visible = relevant.slice(0, SHOWSTRIP_LIMIT);
  const hiddenCount = relevant.length - visible.length;
  return visible.map(slotMarkup).join('') +
    (hiddenCount > 0 ? `<span class="slot more">+${hiddenCount} dalších</span>` : '');
}

function slotMarkup(screening) {
  const version = versionOf(screening);
  return `<span class="slot ${isPast(screening) ? 'past' : ''}">` +
    `<span class="st">${esc(screening.time)}</span>` +
    `<span class="sv">${esc(shortVenue(screening.cinema))}</span>` +
    (is35mm(screening) ? '<span class="sfmt">35mm</span>' : '') +
    (version ? `<span class="sdab">${esc(version.label)}</span>` : '') +
    /* FIX (impeccable critique, minor): the one signal missing from a slot
       that .vrow already shows — see the .seng CSS note. */
    (isEnglishFriendly(screening) ? '<span class="seng">ENG</span>' : '') +
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

  const groups = venues.map(venue => {
    const shows = byVenue.get(venue).sort((a, b) => a.time.localeCompare(b.time));
    return { venue, shows, allPast: shows.every(isPast) };
  });

  const upcoming = groups.filter(g => !g.allPast);
  const past = groups.filter(g => g.allPast);

  return upcoming.map(venueGroupMarkup).join('') +
    todayDoneNotice(upcoming.length, past.length) +
    /* alreadySeparated=true: every group in `past` is, by definition, a venue
       with nothing upcoming at all today — venueGroupMarkup's own
       upcoming/past split would find zero upcoming and wrap 100% of its
       rows in a second, inner "Dnes již proběhlo" disclosure, forcing a
       second tap to see what the first tap was already supposed to reveal.
       Found live, 2026-08-03. Skip the re-split here; the outer disclosure
       is already the one deliberate step this content needs. */
    pastGroupMarkup(past, (group, stagger) => venueGroupMarkup(group, stagger, true), venueCount);
}

/* FIX (found live, 2026-08-02): the top-level "whole venue already done"
   collapse only fired when *every* screening at a venue today had passed —
   a venue with even one film left standing (like Pilotů showing three
   already-past screenings and one at 21:15) rendered all of them flat and
   merely dimmed, the exact clutter this whole pass was meant to remove.
   Film mode already drops past showtimes from a still-live film's preview
   (see showstripMarkup()); this is the same idea one level up, for a
   still-live venue's past screenings.

   alreadySeparated: true when the caller already knows every show in this
   group is past (rendering inside the top-level past-venues disclosure
   above) — skips the internal split/inner-disclosure entirely and just
   lists every screening directly, since wrapping an already-opt-in
   disclosure's content in a second one adds a tap, not clarity. */
function venueGroupMarkup({ venue, shows }, stagger = true, alreadySeparated = false) {
  if (alreadySeparated) {
    return `<section class="vgroup${stagger ? ' stagger' : ''}" data-venue="${esc(venue)}">
      <div class="vgroup-head"><h2>${esc(shortVenue(venue))}</h2></div>
      ${shows.map(vrowMarkup).join('')}
    </section>`;
  }

  const upcoming = shows.filter(s => !isPast(s));
  const past = shows.filter(isPast);
  return `<section class="vgroup${stagger ? ' stagger' : ''}" data-venue="${esc(venue)}">
    <div class="vgroup-head"><h2>${esc(shortVenue(venue))}</h2></div>
    ${upcoming.map(vrowMarkup).join('')}
    ${pastGroupMarkup(past, vrowMarkup, screeningCount)}
  </section>`;
}

function vrowMarkup(s) {
  const film = filmFor(s);
  const version = versionOf(s);
  const strand = strandOf(s);
  return `<div class="vrow" data-film="${esc(s.film_id)}" role="button" tabindex="0" aria-label="${esc(titleOf(s))}">
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
         <span class="sec-head lead">${esc(longDay(selectedDay))}</span>
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
    return `<article class="film stagger" data-film="${esc(p.film_id)}" role="button" tabindex="0" aria-label="${esc(p.title_cz)}">
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

/* ---------- date-jump sheet ---------- */

/* How Program's day strip reaches a date beyond its own PROGRAM_STRIP_DAYS
   window (renderDays() above) — a month calendar of every date state.dates
   actually has data for, opened from the strip's trailing "+N" chip.
   Deliberately its own small grid-builder rather than sharing
   renderPremieres()'s: that one is wired to premieres/release dates and a
   day-select-then-filter-the-list-below interaction; this one only ever
   needs to pick a day and jump Program straight to it, so reusing it would
   mean threading a second interaction mode through code that has no other
   need for one. It reuses that section's MONTHS/DOW_MON/firstWeekdayMon/
   daysInMonth helpers and the .prem-grid/.prem-day CSS — same look, since
   it's the same kind of control, just not the same code path. */
export function renderDateJump(el, activeMonth) {
  const dates = state.dates;
  if (!dates.length) { el.innerHTML = ''; return; }

  const months = [...new Set(dates.map(d => d.slice(0, 7)))];
  const currentMonth = todayISO().slice(0, 7);
  const month = (activeMonth && months.includes(activeMonth))
    ? activeMonth
    : (months.includes(currentMonth) ? currentMonth : months[0]);

  const [year, monthNum] = month.split('-').map(Number);
  const monthIndex = monthNum - 1;
  const inMonth = new Set(dates.filter(d => d.startsWith(month)));

  const todayISOStr = todayISO();
  const todayDay = todayISOStr.startsWith(month) ? Number(todayISOStr.slice(8, 10)) : null;

  const monthIdx = months.indexOf(month);
  const prevMonth = monthIdx > 0 ? months[monthIdx - 1] : '';
  const nextMonth = monthIdx < months.length - 1 ? months[monthIdx + 1] : '';

  let cells = '';
  const pad = firstWeekdayMon(year, monthIndex);
  for (let i = 0; i < pad; i++) cells += '<div class="prem-day empty"></div>';
  for (let day = 1; day <= daysInMonth(year, monthIndex); day++) {
    const iso = `${month}-${String(day).padStart(2, '0')}`;
    const has = inMonth.has(iso);
    const classes = ['prem-day'];
    if (has) classes.push('has');
    if (day === todayDay) classes.push('today');
    // Only a date with actual screenings is a tap target, same rule as the
    // premieres grid — tapping an empty day would just close the sheet on
    // nothing.
    cells += has
      ? `<button class="${classes.join(' ')}" data-jump-month-day="${iso}"><span class="prem-daynum">${day}</span><span class="prem-dot"></span></button>`
      : `<div class="${classes.join(' ')}"><span class="prem-daynum">${day}</span></div>`;
  }

  el.innerHTML = `
    <div class="prem-nav-row">
      <button class="prem-nav" data-jump-month="${esc(prevMonth)}" ${prevMonth ? '' : 'disabled'} aria-label="Předchozí měsíc">‹</button>
      <h2 class="prem-month-label">${esc(MONTHS[monthIndex])} ${year}</h2>
      <button class="prem-nav" data-jump-month="${esc(nextMonth)}" ${nextMonth ? '' : 'disabled'} aria-label="Další měsíc">›</button>
    </div>
    <div class="prem-grid">
      ${DOW_MON.map(d => `<div class="prem-dow">${d}</div>`).join('')}
      ${cells}
    </div>`;
}

/* ---------- Chci vidět ---------- */

/* The notification toggle lives here rather than on its own settings screen
   because this is the list it's about: "tell me when something on here gets a
   screening". Sitting above the very films it watches, it needs no explaining
   — which is why it moved off the old Profil tab when that became Mapa.

   Only rendered when there's actually something saved: with an empty list
   there is nothing to be notified about, and a lone settings switch above an
   empty state is clutter. It appears the moment the first film is saved,
   which is exactly when it starts meaning anything. */
function notifyRow() {
  const supported = isPushSupported();
  const enabled = store.notifyEnabled();
  return `
    <div class="filter-group notify-group">
      <div class="filter-row compact" id="row-notify" role="switch" tabindex="0" aria-checked="${enabled}">
        <div>
          <div class="fr-title">Upozornit na nové termíny</div>
          <div class="fr-sub">${supported
            ? 'Dáme ti vědět, až některý z těchto filmů dostane první termín.'
            : 'Tento prohlížeč push upozornění nepodporuje.'}</div>
        </div>
        <span class="switch ${enabled ? 'on' : ''}${supported ? '' : ' disabled'}" id="sw-notify" aria-hidden="true"><span class="knob"></span></span>
      </div>
    </div>`;
}

export function renderWatchlist(el, filters) {
  const saved = store.watchlist();

  if (!saved.length) {
    el.innerHTML = emptyState('want', 'Chci vidět',
      'Ťukni na srdíčko u filmu a přidej ho sem. Uvidíš rovnou, kdy nejbližší projekce hraje.');
    return;
  }

  const rows = saved.map(filmId => watchlistFilmRow(filmId, filters)).join('');

  el.innerHTML = notifyRow() +
    `<div class="sec-head lead stagger">${saved.length} ${plural(saved.length)}</div>` + rows;
}

function watchlistFilmRow(filmId, filters) {
  const film = filmById(filmId);
  const all = filteredScreeningsForFilm(filmId, filters);
  /* A watchlisted film may not be in this week's data at all — either it has
     stopped screening or it was never in the program. Keep the stored title so
     the row never renders blank. */
  const title = (film && film.title_cz) || store.titleFor(filmId) || filmId;
  const next = filteredNextScreening(filmId, filters);

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

  return `<div class="row stagger" data-film="${esc(filmId)}" role="button" tabindex="0" aria-label="${esc(title)}">
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

/* ---------- Mapa ---------- */

/* The Mapa tab. Was "Profil" until 2026-07-30, when it was renamed to what it
   actually is: the map is the whole screen now, not a 320px box sharing space
   with unrelated settings.

   Two things left with the rename. The notification toggle moved to Chci
   vidět, where it explains itself — it's a setting about that exact list (see
   renderWatchlist). And the old "your film diary / watch history appears here
   once we add tracking" placeholder is gone: watch-history tracking is
   explicitly shelved, and a screen shouldn't advertise a feature that isn't
   coming. What's left is the map plus the data-freshness line, which is
   genuinely useful and has nowhere better to live. */
export function renderMap(el) {
  const generated = state.generatedAt
    ? new Date(state.generatedAt).toLocaleString('cs-CZ', { dateStyle: 'long', timeStyle: 'short' })
    : '—';

  el.innerHTML =
    `<div class="map-screen"><div class="map-container" id="cinema-map"></div></div>` +
    `<p class="attribution">
      Program aktualizován ${esc(generated)}<br>
      ${state.screenings.length} projekcí · ${state.films.size} filmů
    </p>` +
    /* FIX (going public): no dedicated settings/about screen exists to hang
       this off since Profil split into Mapa + the notify toggle in Chci
       vidět (see the module comment above) — same "small trust-relevant
       info, nowhere better to live" reasoning as the freshness line above
       it, so it gets its own line in the same quiet, small-print style
       rather than a new section. */
    `<p class="attribution">
      Beam neukládá nic na server kromě volitelných push upozornění (anonymní, bez účtu a e-mailu) — seznam Chci vidět a filtry zůstávají jen v tomto zařízení.
    </p>`;

  /* Not awaited: renderMap() stays synchronous like every other render
     function here, and the map fills in a moment later once Leaflet has
     built it and data/cinemas.json has loaded — same fire-and-forget pattern
     already used for syncWatchedFilms(). */
  initCinemaMap();
}

/* ---------- detail overlay ---------- */

/* One screening row inside the detail overlay's day-by-day list — shared by
   both the plain arthouse rows and the rows nested inside a collapsed
   multiplex chain group, so there is exactly one place that knows how to
   render a screening's time/venue/format/booking-link line. */
function ovSrowMarkup(s) {
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
}

function venueCount(n) {
  if (n === 1) return '1 kino';
  if (n >= 2 && n <= 4) return `${n} kina`;
  return `${n} kin`;
}

function screeningCount(n) {
  if (n === 1) return '1 projekce';
  if (n >= 2 && n <= 4) return `${n} projekce`;
  return `${n} projekcí`;
}

export function fillDetail(filmId, filters) {
  const film = filmById(filmId);
  /* Only today and later. screeningsForFilm() returns full history for a
     film, so without this filter a film that played last week keeps showing
     those stale, grayed-out rows here forever — not "past today", genuinely
     gone days. Comparing ISO date strings against todayISO() means this is
     computed fresh from the real clock every time the overlay opens, so it
     rolls over on its own at midnight with no separate "refresh" needed.

     filteredScreeningsForFilm(), not the raw screeningsForFilm() — this list
     used to ignore every Filtr setting, so a multiplex-heavy film's detail
     page showed hundreds of Cinema City/Premiere Cinemas showtimes even with
     multiplexes switched off in Program. */
  const shows = filteredScreeningsForFilm(filmId, filters).filter(s => s.date >= todayISO());
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
  saveBtn.setAttribute('aria-label', saved ? 'Odebrat z Chci vidět' : 'Uložit');
  saveBtn.setAttribute('aria-pressed', saved);

  /* this week's screenings, grouped by day, with real booking links */
  const byDay = new Map();
  for (const s of shows) {
    if (!byDay.has(s.date)) byDay.set(s.date, []);
    byDay.get(s.date).push(s);
  }

  /* Arthouse cinemas stay individual rows, exactly as before — a handful of
     screenings across the whole week is the normal case there. Multiplex
     chains are grouped and collapsed per chain (found by the 2026-07-31
     critique: a popular title can carry 600+ Cinema City/Premiere Cinemas
     rows across six-plus locations, dwarfing the actual arthouse programming
     it shares the day with). Collapsed by default behind a native <details>
     — no custom expand/collapse JS needed, and it stays keyboard/screen-
     reader operable for free — but every individual screening (and its real
     booking link) is still one tap away, never actually removed. */
  document.getElementById('ov-screenings').innerHTML = [...byDay.entries()].map(([date, list]) => {
    const individual = list.filter(s => !multiplexChainOf(s.cinema));

    const byChain = new Map();
    for (const s of list) {
      const chain = multiplexChainOf(s.cinema);
      if (!chain) continue;
      if (!byChain.has(chain)) byChain.set(chain, []);
      byChain.get(chain).push(s);
    }
    const chainGroups = [...byChain.entries()].map(([chain, screenings]) => {
      const venues = new Set(screenings.map(s => s.cinema)).size;
      return `<details class="ov-chain">
        <summary>
          <span class="ov-chain-name">${esc(chain)}</span>
          <span class="ov-chain-count">${venueCount(venues)} · ${screeningCount(screenings.length)}</span>
        </summary>
        <div class="ov-scard">${screenings.map(ovSrowMarkup).join('')}</div>
      </details>`;
    }).join('');

    return `<div class="ov-day">${esc(longDay(date))}</div>
      ${individual.length ? `<div class="ov-scard">${individual.map(ovSrowMarkup).join('')}</div>` : ''}
      ${chainGroups}`;
  }).join('') || '<p style="color:var(--text-3);font-size:13px">Tento týden nehraje.</p>';

  return filmId;
}

/* ---------- search ---------- */

export function runSearch(query, resultsEl, filters) {
  /* fold(), not toLowerCase(): both sides of the comparison get their
     diacritics stripped, so "svetozor" finds "Světozor". Typing Czech
     accents on a phone means a long-press per letter, so searching without
     them is the normal case — before this, "svetozor"/"pilotu"/"pritomnost"
     each returned zero results while the accented spelling returned dozens. */
  const q = fold(query.trim());

  if (!q) {
    resultsEl.innerHTML = '<p class="search-hint">Zadej název filmu, kino, režiséra nebo herce.</p>';
    return;
  }

  /* Searches everything we now know about a film, not just its Czech title —
     the English title, director and cast all became searchable with TMDb data.

     matchedCinema records whether *this specific screening's own* cinema is
     what actually matched — not just that the film plays somewhere matching
     q, which the haystack join alone can't distinguish (a title/director/cast
     hit and a cinema hit look identical once folded into one string). FIX
     (impeccable critique, minor): the subtitle below used to always show the
     film's globally-next screening regardless of *why* it matched — search
     "Aero" and get a result subtitled with Bio Oko, if that happened to be
     playing sooner. */
  const hits = new Map();
  for (const s of state.screenings) {
    if (hits.has(s.film_id)) continue;
    const film = filmFor(s);
    const haystack = fold([
      titleOf(s), s.cinema, s.language, s.strand,
      film && film.title_en, film && film.original_title,
      film && (film.director || []).join(' '),
      film && (film.cast || []).join(' '),
    ].filter(Boolean).join(' '));

    if (haystack.includes(q)) {
      hits.set(s.film_id, { screening: s, matchedCinema: fold(s.cinema).includes(q) });
    }
  }

  if (!hits.size) {
    resultsEl.innerHTML = `<p class="search-hint">Nic nenalezeno pro „${esc(query)}".</p>`;
    return;
  }

  resultsEl.innerHTML = [...hits.entries()].map(([filmId, hit]) => {
    const film = filmById(filmId);
    // A cinema-name match gets that cinema's own next screening when it has
    // one still upcoming; anything else (title, director, cast...) keeps
    // showing the film's next screening anywhere, same as before.
    const next = (hit.matchedCinema &&
        filteredScreeningsForFilm(filmId, filters).find(s => !isPast(s) && s.cinema === hit.screening.cinema))
      || filteredNextScreening(filmId, filters);
    const title = (film && film.title_cz) || hit.screening.title_cz;
    /* FIX (impeccable critique, P1): "tento týden nehraje" used to fire
       whenever the FILTERED next screening came up empty — which happens
       just as easily because a real screening exists but got excluded by an
       active Filtr setting as because the film genuinely isn't playing.
       Verified live: with "Drama" + "titulky" active, searching a real,
       currently-screening Action/Adventure film said it "doesn't play this
       week" — false, it plays, just not under that filter. nextScreening()
       (data.js, unfiltered) tells the two cases apart, so the copy can name
       the actual cause instead of asserting something untrue. */
    const unfilteredNext = !next && nextScreening(filmId);
    const sub = next
      ? `${whenLabel(next)} · ${shortVenue(next.cinema)}`
      : unfilteredNext
        ? 'nehraje s aktivním filtrem'
        : 'tento týden nehraje';
    const clearLink = unfilteredNext ? '<button class="sr-clear" data-clear-filters>Vymazat filtr</button>' : '';
    return `<div class="sr-item" data-film="${esc(filmId)}" role="button" tabindex="0" aria-label="${esc(title)}">
      ${posterTile(film, title, 'sr-poster')}
      <div class="sr-body">
        <div class="sr-title">${esc(title)}</div>
        <div class="sr-sub">${esc(sub)}${clearLink}</div>
      </div>
    </div>`;
  }).join('');
}

/* ---------- shared empty state ---------- */

const EMPTY_ICONS = {
  filter: '<path d="M3 5h18M6 12h12M10 19h4" stroke-linecap="round"/>',
  program: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M8 4v16"/>',
  want: '<path d="M6 4h12a1 1 0 011 1v15l-7-4-7 4V5a1 1 0 011-1z"/>',
};

/* actionHTML: optional markup for a button below the sub-text — only the
   filter-mismatch empty state (below) actually uses this; every other call
   site leaves it '' and gets exactly the plain two-line state it always
   had. */
function emptyState(icon, title, sub, actionHTML = '') {
  return `<div class="empty-state stagger">
    <div class="es-mark">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">${EMPTY_ICONS[icon] || ''}</svg>
    </div>
    <p class="es-title">${esc(title)}</p>
    <p class="es-sub">${esc(sub)}</p>
    ${actionHTML}
  </div>`;
}
