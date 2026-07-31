/* ==========================================================================
   Czech formatting helpers and the small shared markup primitives.
   ========================================================================== */

import { todayISO, initialOf, posterUrl } from './data.js?v=32';

export const DOW = ['NE', 'PO', 'ÚT', 'ST', 'ČT', 'PÁ', 'SO'];
export const DOW_LONG = ['NEDĚLE', 'PONDĚLÍ', 'ÚTERÝ', 'STŘEDA', 'ČTVRTEK', 'PÁTEK', 'SOBOTA'];

/* Escapes text before it goes into innerHTML. Film titles, strand names and
   cinema names all come from scraped pages, so they are never trusted. */
export function esc(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/* Lowercase and strip diacritics, so "svetozor" matches "Světozor".

   This is the JS half of what normalize_title() in scrapers/base.py already
   does for the Python side (NFKD-decompose, then drop the combining marks
   that decomposition splits off). The resolver has folded accents since
   Milestone 2; the app's own search never did, which the 2026-07-30 review
   caught: searching "svetozor", "pilotu", "pritomnost" or "kavalirka"
   returned literally zero results while the accented spellings returned
   17/73/7/36. On a phone keyboard Czech diacritics need a long-press per
   letter, so typing without them is the common case, not the edge case.

   Deliberately not the full normalize_title(): that also strips punctuation
   to a single space, which is right for deriving a stable film_id but wrong
   for a substring search (it would stop "Almodóvar" matching inside a longer
   phrase the moment punctuation differed). Folding case and accents is
   exactly the part search needs. */
export function fold(value) {
  return String(value ?? '')
    // NFD splits an accented letter into base letter + combining mark, then
    // \p{M} (the Unicode "Mark" category, needing the /u flag) removes the
    // marks. Written this way rather than as a literal character range so
    // the source stays pure ASCII and can't be corrupted by an editor or
    // encoding round-trip.
    .normalize('NFD')
    .replace(/\p{M}/gu, '')
    .toLowerCase();
}

export function dateOf(iso) {
  return new Date(`${iso}T12:00:00`);
}

/* "22.7." */
export function shortDate(iso) {
  const d = dateOf(iso);
  return `${d.getDate()}.${d.getMonth() + 1}.`;
}

/* "ÚTERÝ 22.7." — the detail overlay's day heading. */
export function longDay(iso) {
  return `${DOW_LONG[dateOf(iso).getDay()]} ${shortDate(iso)}`;
}

/* FIX (audit): the prototype formatted the "next screening" pill differently on
   Program ("20:15 Bio Oko") than on Chci vidět ("ÚT 17:00 Světozor"). One rule
   now, used everywhere the pill appears:
       today      ->  "dnes 17:00"
       otherwise  ->  "ÚT 22.7. 17:00"
   Dropping the weekday for today is the point — "dnes" is what you actually
   want to read, and it makes today's screenings scannable at a glance. */
export function whenLabel(screening) {
  if (screening.date === todayISO()) return `dnes ${screening.time}`;
  const d = dateOf(screening.date);
  return `${DOW[d.getDay()]} ${shortDate(screening.date)} ${screening.time}`;
}

/* ---------- shared markup ---------- */

/* A poster tile. The monogram shows immediately and the real image fades in
   over it, so there is never an empty box while loading. */
export function posterTile(film, title, className = 'poster', size) {
  const url = posterUrl(film, size);
  const monogram = esc(initialOf(title));
  const img = url
    ? `<img src="${esc(url)}" alt="" loading="lazy" onload="this.classList.add('loaded')" onerror="this.remove()">`
    : '';
  return `<div class="${className}">${monogram}${img}</div>`;
}

export function chip(version) {
  return version ? `<span class="chip ${version.cls}">${esc(version.label)}</span>` : '';
}

export function runtimeLabel(film) {
  return film && film.runtime_min ? `${film.runtime_min}′` : '';
}

/* Density dots on the day strip: 1 dot for a quiet day, 3 for a busy one. */
export function densityDots(count) {
  const n = count === 0 ? 0 : count <= 2 ? 1 : count <= 6 ? 2 : 3;
  return `<span class="density">${'<i></i>'.repeat(n)}</span>`;
}
