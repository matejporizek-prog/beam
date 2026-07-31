/* ==========================================================================
   Bootstrap, navigation and all event wiring.

   The prototype used inline onclick="" attributes throughout. Those are gone:
   handlers are delegated from a few roots here, which is what lets titles and
   strand names come straight from scraped pages without any quote-escaping
   games in the markup.
   ========================================================================== */

/* The ?v= must match index.html. See the note there. */
import { loadData, state, todayISO, titleOf, filmById, creatorNames, genreNames } from './data.js?v=31';
import { store } from './store.js?v=31';
import {
  renderDays, renderProgram, renderPremieres, renderWatchlist, renderMap,
  fillDetail, runSearch, activeFilterCount,
} from './screens.js?v=31';
import { esc } from './format.js?v=31';
import { isPushSupported, isSubscribed, enableNotifications, disableNotifications, syncWatchedFilms } from './push.js?v=31';

/* ---------- app state ---------- */

let activeDay = null;
let progGroup = 'film';
let filters = store.loadFilters();
let detailFilmId = null;
/* Whether Žánr's full pill list is expanded — see renderGenrePills() below.
   Reset every time the sheet opens (openFilter() below), same as
   #creator-input's own value: the sheet always opens in a clean state. */
let genresExpanded = false;
/* 'YYYY-MM', resolved lazily. Same lifetime as activeDay above: null until
   renderPremieres() (screens.js) picks a default the first time the tab
   opens — this month if it has a premiere, otherwise the soonest month that
   does — and from then on it only changes when the month-nav arrows are
   tapped, same as every other piece of session state here. */
let activePremMonth = null;
/* ISO date or null. Set by tapping a marked day in the premieres grid, to
   filter that screen's list down to just that day; cleared by tapping the
   same day again, the "Celý měsíc" link, or a month-nav tap (a selection
   from a different month showing through would be confusing). */
let activePremDay = null;

const $ = id => document.getElementById(id);

/* Diagnostic flag: open the app with ?nobeam (or ?nofx) to strip every
   decorative fixed layer (beam, dust, grain) and every scroll-time effect. It's
   an isolation test for scroll performance — if scrolling is smooth with this
   on and janky without it, the decoration is the cause; if it's janky either
   way, the cause is elsewhere (content, layout, images). */
const NO_FX = (() => {
  const p = new URLSearchParams(location.search);
  return p.has('nobeam') || p.has('nofx');
})();

/* ---------- boot ---------- */

async function boot() {
  store.migrate();

  /* We restore scroll ourselves when the detail view closes (see closeDetail).
     Left on 'auto', the browser also restores a position for the history entry
     as it pops — landing on whatever it recorded rather than where the user
     actually was, and undoing our restore a frame later. */
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

  if (NO_FX) {
    document.documentElement.classList.add('no-fx');   // CSS hides .beam and .grain
  } else {
    buildBeam();
    watchBeamResize();
    setBeamPreset('sixty');   // intensity + dust density; locked default
  }

  try {
    await loadData();
  } catch (error) {
    $('prog-list').innerHTML =
      `<div class="boot">Data se nepodařilo načíst.<br><br>
       <span style="color:var(--text-3)">${error.message}</span><br><br>
       Zkus stránku načíst znovu.</div>`;
    return;
  }

  if (!state.dates.length) {
    $('prog-list').innerHTML = '<div class="boot">Zatím nemáme žádný program.</div>';
    return;
  }

  /* Open on today when today has data, otherwise the next day that does —
     landing on an empty past day would be a poor first impression. */
  const today = todayISO();
  activeDay = state.dates.includes(today)
    ? today
    : (state.dates.find(d => d >= today) || state.dates[0]);

  wireEvents();
  syncFilterUI();
  renderProg();
  registerServiceWorker();
  reconcileNotifyState();
}

/* store.notifyEnabled() is just the user's last known preference; the real
   truth is the browser's own subscription state, which can drift out from
   under it (permission revoked in the browser's own settings, the
   subscription expired). Checked once per app open and corrected silently —
   Chci vidět reads store.notifyEnabled() fresh each time it renders, so this
   only needs to fix the stored flag, not force an immediate re-render. Not
   awaited from boot(): it depends on the service worker being ready, which
   can take a moment, and nothing else here needs to wait on it. */
async function reconcileNotifyState() {
  if (!isPushSupported()) return;
  if (store.notifyEnabled() && !(await isSubscribed())) store.setNotifyEnabled(false);
}

/* ---------- rendering ---------- */

function renderProg() {
  renderDays($('days'), activeDay, filters, day => { activeDay = day; renderProg(); });
  $('seg-film').className = 'seg' + (progGroup === 'film' ? ' active' : '');
  $('seg-cinema').className = 'seg' + (progGroup === 'cinema' ? ' active' : '');
  renderProgram($('prog-list'), activeDay, progGroup, filters);
}

function renderPrem() {
  renderPremieres($('s-prem'), activePremMonth, activePremDay);
}

const SCREENS = { program: 's-program', prem: 's-prem', want: 's-want', map: 's-map' };

function go(name) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.s === name));
  const target = $(SCREENS[name]);
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  void target.offsetWidth;  // force reflow so the stagger animation replays
  target.classList.add('active');

  if (name === 'prem') renderPrem();
  if (name === 'want') renderWatchlist(target, filters);
  if (name === 'map') renderMap(target);

  window.scrollTo({ top: 0, behavior: 'instant' });
}

/* ---------- events ---------- */

function wireEvents() {
  /* nav */
  document.querySelectorAll('.nav-item').forEach(item => {
    item.onclick = () => go(item.dataset.s);
  });

  /* group toggle */
  $('seg-film').onclick = () => { progGroup = 'film'; renderProg(); };
  $('seg-cinema').onclick = () => { progGroup = 'cinema'; renderProg(); };

  document.body.addEventListener('click', event => {
    /* Premiéry's month-nav arrows. Delegated like every other control in this
       screen's markup — renderPremieres() replaces the buttons on every
       render, so a plain .onclick bound once at boot wouldn't survive past
       the first render. A disabled edge button has an empty data-prem-month
       and the disabled attribute already stops the click, but the emptiness
       check guards against acting on it regardless. */
    const monthNav = event.target.closest('[data-prem-month]');
    if (monthNav) {
      const month = monthNav.dataset.premMonth;
      if (month) {
        activePremMonth = month;
        activePremDay = null;   // a day picked in a different month wouldn't apply here
        renderPrem();
      }
      return;
    }

    /* A marked day in the premieres grid, or the "Celý měsíc" link back out
       of one — both carry the same data-prem-day attribute (the link's value
       is whichever day is currently selected), so tapping either toggles: a
       fresh day selects it, tapping the already-selected day (or its own
       clear link) clears back to the whole month. */
    const premDay = event.target.closest('[data-prem-day]');
    if (premDay) {
      const day = premDay.dataset.premDay;
      activePremDay = activePremDay === day ? null : day;
      renderPrem();
      return;
    }

    /* A creator chip (already selected — tap removes it) or a search result
       (not yet selected — tap adds it). Both are the exact same toggle, just
       rendered differently by syncFilterUI() depending on which set a name
       is currently in, so one handler covers both. */
    const creatorPill = event.target.closest('[data-creator]');
    if (creatorPill) {
      togglePill(filters.creators, creatorPill.dataset.creator);
      return;
    }

    /* Genre pills — same toggle as everything above, same reason for
       delegating it: renderGenrePills() rebuilds these on every
       syncFilterUI() call, so a plain .onclick bound once wouldn't stick. */
    const genrePill = event.target.closest('[data-genre]');
    if (genrePill) {
      togglePill(filters.genres, genrePill.dataset.genre);
      return;
    }

    if (event.target.closest('#fp-genre-toggle')) {
      genresExpanded = !genresExpanded;
      renderGenrePills();
      return;
    }

    /* "Program dnes" inside a map pin's popup (map.js — a Leaflet popup is
       just DOM content like anything else, so this delegated handler on
       document.body catches clicks inside it with no special wiring). Jumps
       to Program grouped by cinema and scrolls that venue's section into
       view — it may not exist if that cinema has nothing on today's active
       day, which is a normal, silent no-op rather than an error.

       The button is labelled "dnes", so it must actually land on today —
       activeDay is session state that a previous visit to Program may have
       left on some other day (e.g. tomorrow), and without resetting it here
       this would silently reopen Program on that stale day instead. */
    const jumpCinema = event.target.closest('[data-jump-cinema]');
    if (jumpCinema) {
      progGroup = 'cinema';
      activeDay = todayISO();
      go('program');
      renderProg();
      const section = document.querySelector(`[data-venue="${cssEscape(jumpCinema.dataset.jumpCinema)}"]`);
      if (section) setTimeout(() => section.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50);
      return;
    }

    /* A save heart, wherever it appears — Program (both modes), Premiéry, the
       watchlist. Handled before the row's own click so it never also opens the
       detail overlay. */
    const heart = event.target.closest('[data-save]');
    if (heart) {
      event.stopPropagation();
      const id = heart.dataset.save;
      const on = store.toggleWatch(id, heart.dataset.title || '');
      syncSaveButtons(id, on);
      toast(on ? 'Přidáno do Chci vidět' : 'Odebráno z Chci vidět');

      /* Removing the last-tapped item straight out of the open watchlist would
         leave a stale row, so re-render it. */
      if ($('s-want').classList.contains('active')) renderWatchlist($('s-want'), filters);
      /* No-ops silently when notifications are off (see syncWatchedFilms) —
         only worth the round trip when the server actually has a list to
         update. */
      syncWatchedFilms();
      return;
    }

    /* The notify toggle, which lives on Chci vidět. Delegated for the same
       reason as everything above: renderWatchlist() rebuilds it on every
       render. */
    const notifyRow = event.target.closest('#row-notify');
    if (notifyRow) {
      toggleNotify();
      return;
    }

    /* Any element carrying data-film opens that film's detail overlay. */
    const filmEl = event.target.closest('[data-film]');
    if (filmEl && !event.target.closest('.buy')) {
      /* A result tapped inside the search overlay needs the search closed first
         — the search overlay sits above the detail overlay, so otherwise the
         detail opens hidden behind it and nothing appears to happen. */
      const fromSearch = !!event.target.closest('#search-ov');
      openDetail(filmEl.dataset.film, fromSearch);
    }
  });

  /* search */
  $('hdr-search').onclick = openSearch;
  $('search-back').onclick = () => closeSearch();
  $('search-input').oninput = () => runSearch($('search-input').value, $('search-results'), filters);

  /* filter sheet */
  $('filtr-btn').onclick = openFilter;
  $('filter-scrim').onclick = () => closeFilter();
  $('sheet-apply').onclick = () => { closeFilter(); renderProg(); };
  $('sheet-clear').onclick = () => {
    filters = { mplex: false, version: new Set(), format: new Set(), enOnly: false, creators: new Set(), genres: new Set() };
    store.saveFilters(filters);
    syncFilterUI();
  };
  $('row-mplex').onclick = () => { filters.mplex = !filters.mplex; store.saveFilters(filters); syncFilterUI(); };
  $('row-en').onclick = () => { filters.enOnly = !filters.enOnly; store.saveFilters(filters); syncFilterUI(); };
  $('creator-input').oninput = () => renderCreatorResults();

  document.querySelectorAll('#fp-version .fpill').forEach(pill => {
    pill.onclick = () => togglePill(filters.version, pill.dataset.v);
  });
  document.querySelectorAll('#fp-format .fpill').forEach(pill => {
    pill.onclick = () => togglePill(filters.format, pill.dataset.v);
  });

  /* detail overlay */
  $('ov-close').onclick = () => closeDetail();
  $('ov-save').onclick = toggleSave;
  $('ov-trailer').onclick = () => {
    const key = $('ov-trailer').dataset.trailer;
    if (key) openTrailer(key);
  };
  $('trailer-close').onclick = closeTrailer;
  $('trailer-modal').onclick = event => {
    if (event.target === $('trailer-modal')) closeTrailer();
  };

  /* Back button / swipe-back closes whatever is open instead of leaving. */
  window.addEventListener('popstate', () => {
    if ($('trailer-modal').classList.contains('open')) return closeTrailer(true);
    if ($('overlay').classList.contains('open')) return closeDetail(true);
    if ($('search-ov').classList.contains('open')) return closeSearch(true);
    if ($('filter-sheet').classList.contains('open')) return closeFilter(true);
  });

  /* Scroll-linked header shrink. Skipped under ?nobeam so the isolation test
     leaves nothing at all running on scroll. */
  if (!NO_FX) {
    let ticking = false;
    window.addEventListener('scroll', () => {
      if (ticking) return;
      /* The detail view and the Filtr panel both scroll the document too, and
         the header is hidden while either is open — so this would be
         per-frame work for a class nobody can see, on the exact screens we're
         trying to keep smooth. */
      const root = document.documentElement.classList;
      if (root.contains('detail-open') || root.contains('sheet-open')) return;
      ticking = true;
      requestAnimationFrame(() => {
        document.querySelector('header').classList.toggle('compact', window.scrollY > 24);
        ticking = false;
      });
    }, { passive: true });
  }
}

function togglePill(set, value) {
  set.has(value) ? set.delete(value) : set.add(value);
  store.saveFilters(filters);
  syncFilterUI();
}

function syncFilterUI() {
  $('sw-mplex').className = 'switch' + (filters.mplex ? ' on' : '');
  $('sw-en').className = 'switch' + (filters.enOnly ? ' on' : '');
  document.querySelectorAll('#fp-version .fpill').forEach(p => p.classList.toggle('on', filters.version.has(p.dataset.v)));
  document.querySelectorAll('#fp-format .fpill').forEach(p => p.classList.toggle('on', filters.format.has(p.dataset.v)));
  renderGenrePills();
  renderCreatorChips();
  renderCreatorResults();

  const count = activeFilterCount(filters);
  const badge = $('filtr-count');
  badge.textContent = count || '';
  badge.classList.toggle('show', count > 0);
  $('filtr-btn').classList.toggle('on', count > 0);
}

/* Every genre currently screening, as toggle pills — unlike creators this is
   a small, bounded set (TMDb's whole taxonomy is under 20 names), so it's
   rendered like Verze/Format rather than a search field: every option shown
   as a pill, tap to toggle on/off in place, not typed into a search box.
   Still computed from genreNames() rather than hardcoded, so a genre with
   nothing screening never shows an empty-result pill and a real one is never
   missing.

   But ~18 pills at once is still a wall — a real cognitive-load finding from
   the 2026-07-31 design critique, sitting right next to Tvůrci's own
   type-ahead field which already solves the same problem correctly. A search
   box isn't the right fix for genre specifically, though: unlike creator
   names (100+, unknown to the user in advance), genres are a short, closed,
   already-familiar vocabulary someone wants to scan and tap, not type — so
   the fix here is showing only the first GENRE_VISIBLE_LIMIT (genreNames()
   orders these by how many films actually carry them this week, most useful
   first) with a "show more" reveal for the rest. Whatever's already selected
   always stays visible even collapsed, so toggling one off is never a
   scroll-and-hunt. */
const GENRE_VISIBLE_LIMIT = 6;

function renderGenrePills() {
  const all = genreNames();
  const visible = genresExpanded
    ? all
    : all.filter((genre, i) => i < GENRE_VISIBLE_LIMIT || filters.genres.has(genre));
  const hiddenCount = all.length - visible.length;

  $('fp-genre').innerHTML = visible.map(genre =>
    `<button class="fpill ${filters.genres.has(genre) ? 'on' : ''}" data-genre="${esc(genre)}">${esc(genre)}</button>`
  ).join('');

  const toggle = $('fp-genre-toggle');
  toggle.classList.toggle('show', genresExpanded || hiddenCount > 0);
  toggle.textContent = genresExpanded ? 'Zobrazit méně' : `Zobrazit vše (+${hiddenCount})`;
}

/* Selected director/screenwriter names — rendered the same way a selected
   version/format pill is (.fpill.on), since selecting one means the same
   thing: this is filtering right now. The "×" is decorative; the whole chip
   is the tap target, and tapping it removes it (see the delegated
   [data-creator] handler above). */
function renderCreatorChips() {
  $('creator-chips').innerHTML = [...filters.creators].map(name =>
    `<button class="fpill on" data-creator="${esc(name)}">${esc(name)} <span class="x">✕</span></button>`
  ).join('');
}

/* Live matches for whatever's typed in #creator-input, excluding names
   already selected (those show as chips instead). Empty until there's a
   query — with 100+ names some weeks, showing all of them unasked would
   defeat the point of a search field. Capped well short of that count so a
   broad query doesn't turn into its own wall of pills. */
const CREATOR_RESULT_LIMIT = 8;

function renderCreatorResults() {
  const query = $('creator-input').value.trim().toLowerCase();
  const results = $('creator-results');
  if (!query) { results.innerHTML = ''; return; }

  const matches = creatorNames()
    .filter(name => !filters.creators.has(name) && name.toLowerCase().includes(query))
    .slice(0, CREATOR_RESULT_LIMIT);

  results.innerHTML = matches.map(name =>
    `<button class="fpill" data-creator="${esc(name)}">${esc(name)}</button>`
  ).join('');
}

/* ---------- overlays ---------- */

/* Where the program list was scrolled to when Filtr was opened. The panel
   scrolls the document itself now (see .sheet in the CSS for the full story),
   so opening it replaces the page's scroll — this is what puts you back where
   you were. Exactly the same mechanism as scrollBeforeDetail below; the two
   are kept separate because the panels can't be open at once but their
   history entries are independent. */
let scrollBeforeFilter = 0;

function openFilter() {
  $('creator-input').value = '';
  genresExpanded = false;
  syncFilterUI();
  scrollBeforeFilter = window.scrollY;
  document.documentElement.classList.add('sheet-open');
  $('filter-scrim').classList.add('open');
  $('filter-sheet').classList.add('open');
  window.scrollTo(0, 0);
  history.pushState({ sheet: 'filter' }, '');
}

function closeFilter(fromPop) {
  $('filter-scrim').classList.remove('open');
  $('filter-sheet').classList.remove('open');
  document.documentElement.classList.remove('sheet-open');
  /* Reading a layout property forces the browser to apply the line above
     before we scroll. Without it the program list is still display:none, the
     document is only as tall as the panel was, and the target scroll gets
     clamped to that shorter height — you'd land near the top instead of
     where you left off. Same reasoning as closeDetail(). */
  void document.documentElement.scrollHeight;
  window.scrollTo(0, scrollBeforeFilter);
  if (!fromPop) history.back();
}

function openSearch() {
  $('search-ov').classList.add('open');
  setTimeout(() => $('search-input').focus(), 60);
  history.pushState({ sheet: 'search' }, '');
}

function closeSearch(fromPop) {
  $('search-ov').classList.remove('open');
  $('search-input').value = '';
  runSearch('', $('search-results'), filters);
  if (!fromPop) history.back();
}

/* Where the program list was scrolled to when a detail was opened. The detail
   scrolls the document itself now (see .overlay in the CSS for why), so opening
   it replaces the page's scroll — this is what puts you back where you were. */
let scrollBeforeDetail = 0;

function openDetail(filmId, fromSearch) {
  detailFilmId = fillDetail(filmId, filters);
  scrollBeforeDetail = window.scrollY;
  $('overlay').classList.add('open');
  document.documentElement.classList.add('detail-open');
  window.scrollTo(0, 0);

  if (fromSearch) {
    /* Hide the search overlay and take over its history entry, so there's no
       stranded 'search' state and the detail isn't left behind it. */
    $('search-ov').classList.remove('open');
    $('search-input').value = '';
    runSearch('', $('search-results'), filters);
    history.replaceState({ sheet: 'detail' }, '');
  } else {
    history.pushState({ sheet: 'detail' }, '');
  }
}

function closeDetail(fromPop) {
  $('overlay').classList.remove('open');
  document.documentElement.classList.remove('detail-open');
  /* Reading a layout property forces the browser to apply the line above
     before we scroll. Without it the program list is still display:none, the
     document is only as tall as the detail was, and the target scroll gets
     clamped to that shorter height — you'd land near the top instead of where
     you left off. */
  void document.documentElement.scrollHeight;
  window.scrollTo(0, scrollBeforeDetail);
  if (!fromPop) history.back();
}

function toggleSave() {
  if (!detailFilmId) return;
  const film = filmById(detailFilmId);
  const title = (film && film.title_cz) || $('ov-title').textContent;
  const on = store.toggleWatch(detailFilmId, title);
  syncSaveButtons(detailFilmId, on);
  toast(on ? 'Přidáno do Chci vidět' : 'Odebráno z Chci vidět');

  /* Keep Chci vidět in step immediately rather than on the next tab switch. */
  if ($('s-want').classList.contains('active')) renderWatchlist($('s-want'), filters);
  syncWatchedFilms();
}

/* The "Upozornit na nové termíny" toggle on Chci vidět. Both directions are real
   browser-level actions (a permission prompt, a subscription request), not
   an instant local flip, so the toggle's visual state is re-rendered from
   what actually happened rather than assumed optimistically — denying the
   permission prompt must leave it off, not show on-then-snap-back. */
async function toggleNotify() {
  const turningOn = !store.notifyEnabled();
  let success = true;
  if (turningOn) success = await enableNotifications();
  else await disableNotifications();

  if (turningOn && !success) {
    toast('Upozornění se nepodařilo povolit.');
  } else {
    toast(turningOn ? 'Upozornění zapnuta' : 'Upozornění vypnuta');
  }
  /* The toggle lives on Chci vidět now (it's a setting about that list), so
     that's the screen to re-render from the real post-action state. */
  if ($('s-want').classList.contains('active')) renderWatchlist($('s-want'), filters);
}

/* Reflect a save/unsave on every control that points at the same id: the big
   overlay heart and any row hearts currently on screen. Without this, saving
   from the detail page would leave the Program row's heart stale until re-render. */
function syncSaveButtons(id, on) {
  document.querySelectorAll(`.save-heart[data-save="${cssEscape(id)}"]`).forEach(button => {
    button.classList.toggle('on', on);
    button.textContent = on ? '♥' : '♡';
  });
  if (detailFilmId === id) {
    const overlayHeart = $('ov-save');
    overlayHeart.classList.toggle('saved', on);
    overlayHeart.textContent = on ? '♥' : '♡';
  }
}

/* CSS.escape isn't universal on older mobile WebViews; fall back to escaping
   the characters that actually appear in our ids (quotes, backslashes). */
function cssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replace(/["\\]/g, '\\$&');
}

/* ---------- trailer ---------- */

/* Plays inline over the app. The prototype bounced out to YouTube; the brief
   explicitly calls for a modal instead. youtube-nocookie avoids setting
   tracking cookies until the video is actually played. */
function openTrailer(key) {
  $('trailer-frame').src =
    `https://www.youtube-nocookie.com/embed/${encodeURIComponent(key)}?autoplay=1&rel=0`;
  $('trailer-modal').classList.add('open');
  history.pushState({ sheet: 'trailer' }, '');
}

function closeTrailer(fromPop) {
  $('trailer-modal').classList.remove('open');
  $('trailer-frame').src = '';   // stops playback
  if (!fromPop) history.back();
}

/* ---------- toast ---------- */

let toastTimer = null;

function toast(message) {
  const el = $('toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 2000);
}

/* ---------- the projector beam ---------- */

/* The ray fan, on a canvas — but still shimmering.

   The prototype animated 40 separate blurred, screen-blended DOM layers, each
   fading its own opacity in and out. That flicker is the point of the motif, so
   losing it (as the first static-canvas pass did) changed the feel.

   This keeps the flicker but pays for it once: each ray is blurred into its own
   little sprite a single time, and the per-frame loop only redraws those
   sprites at a varying opacity. The expensive part — the blur — never runs
   again; a frame is 40 cheap drawImage calls. Same seeded geometry and warm/
   cool mix as the prototype, so the fan itself looks identical. */

let beamState = null;   // { ctx, rays, originX, width, height, dpr }
let beamRAF = null;

function buildBeam() {
  const canvas = $('beam-canvas');
  if (!canvas || !canvas.getContext) return;

  /* Measure the container, not the canvas. An unstyled canvas reports its
     intrinsic 300x150 default, so reading clientWidth before layout settles
     silently produces a fan that is too narrow. */
  const box = canvas.parentElement.getBoundingClientRect();
  const width = Math.round(box.width) || 430;
  const height = canvas.clientHeight || 640;
  /* Cap the pixel ratio: a 3x buffer costs a lot of fill rate for a soft,
     blurred graphic nobody inspects at pixel level. */
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);

  const ctx = canvas.getContext('2d');

  /* Whether this browser's canvas can actually blur. Older iOS Safari has no
     working CanvasRenderingContext2D.filter, so the rays would come out
     hard-edged — the flat "cartoon" look on mobile. When it can't blur, the ray
     sprites are given soft edges another way (a gradient mask, see
     renderRaySprite). Crucially the softening is always baked into the sprite
     bitmap, never applied as a live CSS filter on the on-screen canvas — a
     filter on that fixed, scroll-overlapping layer badly janks iOS scrolling. */
  const blurWorks = canvasBlurWorks();

  const N = 40, spread = 170;
  let seed = 7;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };

  const rays = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const angle = (-spread / 2 + t * spread + (rnd() - 0.5) * 3) * Math.PI / 180;
    const warm = rnd() < 0.4;
    const w = rnd() < 0.3 ? (3 + rnd() * 4) : (10 + rnd() * 18);
    const len = 580 + Math.round(rnd() * 90);
    const blur = w > 12 ? 4.5 : 1.8;
    const centre = 1 - Math.abs(t - 0.5) * 0.7;
    const peak = 0.35 + 0.65 * rnd() * Math.max(centre, 0.3);
    /* Each ray shimmers on its own clock — different period and phase — so the
       fan flickers irregularly, "haze drifting through", not a unison pulse. */
    const period = 3.4 + rnd() * 3.8;
    const phase = rnd() * Math.PI * 2;

    rays.push({
      sprite: renderRaySprite(w, len, blur, warm, dpr, blurWorks),
      angle, peak, period, phase, pad: Math.ceil(blur * 3) + 2,
    });
  }

  /* On touch devices the beam is a single STATIC layer: drawn once, never
     animated, with the aperture glow baked into this same canvas so the blurred
     DOM glow layers (.beam-haze/.beam-core/.beam-origin) and the animated dust
     can all be switched off (they're hidden in CSS on coarse pointers, and
     buildMotes is skipped). That leaves one cheap, static, un-blended layer —
     which is what stops the beam from janking scroll on iOS. Desktop keeps the
     full animated, blended, dust-filled beam. */
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  beamState = { ctx, rays, originX: width / 2, width, height, dpr, coarse };
  beamAnimated = !coarse && !reduce;

  if (beamRAF) cancelAnimationFrame(beamRAF);

  /* Paint one frame straight away so the fan is visible the instant the canvas
     exists — before, and independent of, the animation loop. Without this a
     tab that loads in the background (where rAF is throttled to zero) would
     show a blank beam until it happened to gain focus. Held steady (not
     mid-shimmer) whenever there won't be an animation loop. */
  drawBeam(performance.now(), !beamAnimated);
  if (beamAnimated) startBeamLoop();
}

/* The animation loop, capped to ~30fps. The shimmer periods are several seconds
   long, so 30fps looks identical to 60 while halving the main-thread cost. It's
   a named start/stop pair so scrolling can pause it (see below) — a rAF loop
   redrawing the canvas is exactly the kind of main-thread work that makes the
   first touch of a scroll feel unresponsive on mobile. */
let beamLastDraw = 0;
let beamAnimated = false;   // false on touch devices / reduced-motion: static beam
const BEAM_FRAME_MS = 33;

function startBeamLoop() {
  if (!beamAnimated) return;   // static beam never runs a loop (mobile/reduced-motion)
  if (beamRAF || !beamState) return;
  if (document.hidden) return;
  const loop = now => {
    if (now - beamLastDraw >= BEAM_FRAME_MS) { drawBeam(now, false); beamLastDraw = now; }
    beamRAF = requestAnimationFrame(loop);
  };
  beamRAF = requestAnimationFrame(loop);
}

function stopBeamLoop() {
  if (beamRAF) { cancelAnimationFrame(beamRAF); beamRAF = null; }
}

/* Does this browser's 2D canvas actually apply a blur filter? */
function canvasBlurWorks() {
  try {
    const ctx = document.createElement('canvas').getContext('2d');
    if (typeof ctx.filter !== 'string') return false;
    ctx.filter = 'blur(2px)';
    return ctx.filter === 'blur(2px)';   // unsupported browsers leave it 'none'
  } catch {
    return false;
  }
}

/* Blur one ray into a standalone sprite canvas, once. */
function renderRaySprite(w, len, blur, warm, dpr, useFilter) {
  const pad = Math.ceil(blur * 3) + 2;
  const sw = Math.ceil(w + pad * 2);
  const sh = Math.ceil(len + pad * 2);

  const sprite = document.createElement('canvas');
  sprite.width = Math.ceil(sw * dpr);
  sprite.height = Math.ceil(sh * dpr);

  const sctx = sprite.getContext('2d');
  sctx.scale(dpr, dpr);
  if (useFilter) sctx.filter = `blur(${blur}px)`;

  const gradient = sctx.createLinearGradient(0, pad, 0, pad + len);
  if (warm) {
    gradient.addColorStop(0.00, 'rgba(255,238,214,0.34)');
    gradient.addColorStop(0.34, 'rgba(252,224,188,0.15)');
    gradient.addColorStop(0.64, 'rgba(246,208,168,0.06)');
  } else {
    gradient.addColorStop(0.00, 'rgba(214,236,255,0.40)');
    gradient.addColorStop(0.34, 'rgba(190,220,252,0.18)');
    gradient.addColorStop(0.64, 'rgba(176,208,246,0.07)');
  }
  gradient.addColorStop(0.92, 'rgba(255,255,255,0)');

  sctx.fillStyle = gradient;
  sctx.fillRect(pad, pad, w, len);

  /* When the canvas can't blur, taper the ray's left and right edges to
     transparent with a horizontal alpha mask. That turns the hard-edged
     rectangle into a soft streak — the same "haze not cartoon" result as a
     blur, but baked into the bitmap here (no live filter, so no scroll cost). */
  if (!useFilter) {
    sctx.globalCompositeOperation = 'destination-in';
    const edge = sctx.createLinearGradient(pad, 0, pad + w, 0);
    edge.addColorStop(0, 'rgba(0,0,0,0)');
    edge.addColorStop(0.5, 'rgba(0,0,0,1)');
    edge.addColorStop(1, 'rgba(0,0,0,0)');
    sctx.fillStyle = edge;
    sctx.fillRect(pad, pad, w, len);
    sctx.globalCompositeOperation = 'source-over';
  }

  return { canvas: sprite, sw, sh, pad };
}

function drawBeam(now, still) {
  if (!beamState) return;
  const { ctx, rays, originX, width, height, dpr, coarse } = beamState;
  const seconds = now / 1000;

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, width, height);
  /* 'lighter' is canvas's additive blend — the closest match to the CSS
     mix-blend-mode: screen the DOM version relied on. */
  ctx.globalCompositeOperation = 'lighter';

  /* On touch devices the blurred DOM glow layers are hidden, so bake the bright
     aperture + soft cone glow straight into this canvas — keeps the beam
     feeling luminous without a single extra layer or filter. */
  if (coarse) {
    ctx.globalAlpha = 1;
    const glow = ctx.createRadialGradient(originX, 6, 0, originX, 6, 150);
    glow.addColorStop(0.00, 'rgba(224,240,255,0.55)');
    glow.addColorStop(0.35, 'rgba(190,220,252,0.14)');
    glow.addColorStop(1.00, 'rgba(190,220,252,0)');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, width, 230);
  }

  for (const ray of rays) {
    /* Matches the prototype's shimmer keyframes: opacity swings between
       peak*0.45 and peak. Held mid-bright when motion is reduced. */
    const shimmer = still
      ? 0.72
      : 0.45 + 0.55 * (Math.sin(seconds * (2 * Math.PI / ray.period) + ray.phase) + 1) / 2;
    ctx.globalAlpha = ray.peak * shimmer;

    ctx.save();
    ctx.translate(originX, 0);
    ctx.rotate(ray.angle);
    ctx.drawImage(ray.sprite.canvas, -ray.sprite.sw / 2, -ray.sprite.pad, ray.sprite.sw, ray.sprite.sh);
    ctx.restore();
  }
  ctx.globalAlpha = 1;
}

/* Redraw on resize/rotation, debounced — the fan is geometry-dependent. */
let beamResizeTimer = null;
function watchBeamResize() {
  window.addEventListener('resize', () => {
    clearTimeout(beamResizeTimer);
    beamResizeTimer = setTimeout(buildBeam, 200);
  });

  /* Stop the loop while the tab is hidden; no point animating a beam nobody can
     see, and it keeps the battery honest. */
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopBeamLoop();
    else startBeamLoop();
  });

  /* Pause the beam the instant a scroll gesture begins, and for a moment after
     it settles. During the gesture the main thread is left entirely free, so
     the scroll starts on the first touch instead of feeling frozen. The beam
     resumes shimmering once scrolling stops. */
  let beamResumeTimer = null;
  const pauseBeamForScroll = () => {
    /* The static beam (mobile / reduced-motion) has no loop to pause — bail
       before churning a timer on every touchmove of every scroll gesture. */
    if (!beamAnimated) return;
    stopBeamLoop();
    clearTimeout(beamResumeTimer);
    beamResumeTimer = setTimeout(startBeamLoop, 300);
  };
  window.addEventListener('scroll', pauseBeamForScroll, { passive: true });
  window.addEventListener('touchstart', pauseBeamForScroll, { passive: true });
  window.addEventListener('touchmove', pauseBeamForScroll, { passive: true });
}

/* ---------- beam presets + dust ----------
   Ported from the prototype's BEAM_CONFIG. One knob — the preset — sets both the
   beam's overall intensity (a CSS variable multiplying its opacity) and the
   number of dust motes, so a quieter beam also has quieter dust. Matěj locked
   the 60% preset after comparing intensities side by side. */
const BEAM_PRESETS = {
  full:    { intensity: 1.00, motes: 26 },
  medium:  { intensity: 0.70, motes: 20 },
  sixty:   { intensity: 0.60, motes: 18 },   // ← locked default
  low:     { intensity: 0.45, motes: 14 },
  minimal: { intensity: 0.25, motes: 8 },
};

function setBeamPreset(name) {
  const preset = BEAM_PRESETS[name];
  if (!preset) return;
  document.documentElement.style.setProperty('--beam-intensity', preset.intensity);
  /* No dust on touch devices: 18 continuously-animating elements on a fixed
     layer over the scroll are part of what made scrolling sticky. The static
     canvas beam carries the look there instead. */
  const coarse = window.matchMedia('(pointer: coarse)').matches;
  buildMotes(coarse ? 0 : preset.motes);
}

/* Dust drifting down inside the cone. Each mote is randomised in size, position
   (constrained to the cone, which widens with depth), fall distance, sway and
   speed, with ~30% warm-toned to match the warm rays. Seeded, so the field
   looks the same on every load. */
function buildMotes(count) {
  const field = $('motefield');
  if (!field) return;
  field.innerHTML = '';

  let seed = 42;
  const rnd = () => { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; };
  const H = 480, maxHalf = 190;   // field height, cone half-width at the bottom

  const fragment = document.createDocumentFragment();
  for (let i = 0; i < count; i++) {
    const mote = document.createElement('div');
    mote.className = 'mote' + (rnd() < 0.3 ? ' warm' : '');

    const t = 0.08 + rnd() * 0.84;          // depth down the cone (0 = top)
    const half = 14 + t * maxHalf;          // cone widens with depth
    const x = 215 + (rnd() * 2 - 1) * half;  // field is 430 wide, centred at 215
    const y = t * H;
    const size = 1 + rnd() * 2.5;

    mote.style.left = x.toFixed(0) + 'px';
    mote.style.top = y.toFixed(0) + 'px';
    mote.style.width = mote.style.height = size.toFixed(1) + 'px';
    mote.style.setProperty('--mo', (0.25 + rnd() * 0.5).toFixed(2));      // peak opacity
    mote.style.setProperty('--md', (60 + rnd() * 110).toFixed(0) + 'px'); // fall distance
    mote.style.setProperty('--mx', ((rnd() * 2 - 1) * 24).toFixed(0) + 'px'); // sway
    mote.style.animationDuration = (7 + rnd() * 9).toFixed(1) + 's';
    mote.style.animationDelay = (-rnd() * 14).toFixed(1) + 's';           // desync loops
    fragment.appendChild(mote);
  }
  field.appendChild(fragment);
}

/* ---------- service worker ---------- */

function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  /* Only meaningful over http(s); opening index.html straight off disk skips it. */
  if (location.protocol === 'file:') return;

  /* Never register on localhost. A service worker caching the shell during
     development means edits silently don't appear, which costs far more time
     than offline support is worth on a machine that is serving the files. */
  const isLocal = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  if (isLocal) {
    /* Clear out any worker registered by an earlier visit. */
    navigator.serviceWorker.getRegistrations()
      .then(list => list.forEach(r => r.unregister()))
      .catch(() => {});
    return;
  }
  navigator.serviceWorker.register('./sw.js').catch(() => {
    /* Offline support is a bonus, not a requirement — never block the app. */
  });
}

boot();
