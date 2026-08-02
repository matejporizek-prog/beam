/* ==========================================================================
   The cinema map — the whole Mapa tab.

   Leaflet (loaded as a classic global script in index.html — see the note
   there) is the one external library this app uses besides fonts; everything
   else in Beam is hand-written. Cinema locations are hand-curated reference
   data (data/cinemas.json — addresses essentially never change, so there's
   no scrape pipeline for this, unlike screenings/films/premieres) rather than
   anything derived from the scraped program.

   Tiles are CARTO's free "dark matter" basemap, not the default OpenStreetMap
   light tiles — a bright white rectangle would be a jarring, out-of-place
   block in an otherwise near-black app; this is a basemap style built
   specifically to sit inside dark UIs like this one.
   ========================================================================== */

import { esc } from './format.js?v=50';

let cinemasCache = null;
let mapInstance = null;

async function loadCinemas() {
  if (cinemasCache) return cinemasCache;
  const response = await fetch('../data/cinemas.json', { cache: 'no-cache' });
  const data = await response.json();
  cinemasCache = data.cinemas || [];
  return cinemasCache;
}

/* Called every time the Mapa tab renders. renderMap() rebuilds #cinema-map's
   whole DOM subtree from scratch on each visit to the tab, which would leak
   the previous Leaflet instance (its own event listeners, its own detached
   DOM) if not explicitly torn down first — .remove() is Leaflet's own
   cleanup, not enough on its own without also dropping our reference to it. */
export async function initCinemaMap() {
  const container = document.getElementById('cinema-map');
  if (!container) return;

  if (mapInstance) {
    mapInstance.remove();
    mapInstance = null;
  }

  const cinemas = await loadCinemas();
  if (!cinemas.length) return;

  const map = L.map(container, { zoomControl: true });
  mapInstance = map;

  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> ' +
      '&copy; <a href="https://carto.com/attributions" target="_blank" rel="noopener noreferrer">CARTO</a>',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);

  /* FIX (impeccable critique, P2): Leaflet's own default marker is a stock
     blue pin loaded from a separate PNG on its CDN — a second saturated
     colour on the one screen that otherwise keeps champagne as the sole
     accent, plus a cross-origin image this app's cache/offline story never
     covers. An inline SVG divIcon needs no extra request and matches
     DESIGN.md's own line naming "map markers" a champagne use, same as the
     "you are here" dot below already is. */
  const cinemaPinIcon = L.divIcon({
    className: 'cinema-pin',
    html: `<svg width="26" height="34" viewBox="0 0 26 34" xmlns="http://www.w3.org/2000/svg">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.75 13 21 13 21s13-11.25 13-21C26 5.8 20.2 0 13 0z" fill="#E7C98A"/>
      <circle cx="13" cy="13" r="5" fill="#0C0E11"/>
    </svg>`,
    iconSize: [26, 34], iconAnchor: [13, 34], popupAnchor: [0, -30],
  });

  const markers = cinemas.map(cinema => {
    const marker = L.marker([cinema.lat, cinema.lng], { icon: cinemaPinIcon }).addTo(map);
    /* Directions use the cinema's coordinates, not its address string — we
       already have exact lat/lng for the marker itself, and Google's own
       geocoding of a Czech street address is one more thing that can drift
       or fail (diacritics, abbreviation differences) where a coordinate
       can't. `api=1` is Google's documented cross-platform directions URL:
       opens the Maps app on a phone that has one installed, falls back to
       maps.google.com in any browser otherwise — no separate mobile/desktop
       branching needed. */
    const directionsUrl =
      `https://www.google.com/maps/dir/?api=1&destination=${cinema.lat},${cinema.lng}`;

    marker.bindPopup(
      `<div class="map-popup">
         <strong>${esc(cinema.name)}</strong>
         <div class="map-popup-addr">${esc(cinema.address)}</div>
         <div class="map-popup-actions">
           <button class="map-popup-btn" data-jump-cinema="${esc(cinema.name)}">Program dnes</button>
           <a class="map-popup-btn secondary" href="${esc(directionsUrl)}" target="_blank" rel="noopener noreferrer">Trasa</a>
         </div>
       </div>`
    );
    return marker;
  });

  map.fitBounds(L.featureGroup(markers).getBounds(), { padding: [24, 24] });

  /* Best-effort: a denied or unavailable permission just means the map shows
     every cinema and nothing more, not an error state — asking "where am I"
     is additive to "where are the cinemas", never a precondition for it. */
  if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
      position => {
        // The map may have been torn down (tab switched away) by the time a
        // slow geolocation prompt resolves — nothing left to draw on.
        if (mapInstance !== map) return;

        const { latitude, longitude } = position.coords;
        /* Deliberately not champagne, unlike the cinema pins above — champagne
           means "this is the one that's active/selected/true" everywhere else
           in the app, but here every cinema pin already claims that meaning,
           and "my own location" is a different kind of fact (where I am, not
           what I might select). A cool blue with a light ring is the
           near-universal "you are here" convention (Google/Apple Maps), so it
           reads instantly without needing its own legend, and it contrasts
           against both the champagne pins and the dark basemap. */
        const you = L.circleMarker([latitude, longitude], {
          radius: 8, weight: 2, color: '#ECEFF3', fillColor: '#4A9EFF', fillOpacity: 0.9,
        }).addTo(map).bindPopup('Tvoje poloha');

        map.fitBounds(L.featureGroup([...markers, you]).getBounds(), { padding: [24, 24] });
      },
      () => { /* denied, unavailable, or timed out — leave the cinemas-only view as-is */ },
      { timeout: 8000 }
    );
  }
}
