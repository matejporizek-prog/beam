/* ==========================================================================
   Push notifications: "tell me when a film I've saved actually gets a
   screening."

   This is the one feature in Beam with a real server behind it — everything
   else is static files. The server side is worker/index.js (a Cloudflare
   Worker, not part of this app bundle) plus a KV namespace holding each
   subscription and which film_ids it's watching; a weekly cron there checks
   for matches and sends the actual push. This module only does the
   browser-side half: asking permission, subscribing, and keeping the
   server's list of watched films in sync with the real watchlist.

   Scope, per Matěj: no per-film opt-in — one master toggle (Profil), and
   once it's on, everything in Chci vidět that doesn't have a screening yet
   is watched automatically.
   ========================================================================== */

import { state } from './data.js?v=25';
import { store } from './store.js?v=25';

/* Public half of the VAPID keypair used to sign push messages server-side.
   Not secret — every subscribing browser needs it, same as a site's own TLS
   certificate is public. The private half lives only as a Cloudflare Worker
   secret (see README.md's "Push notifications" section), never in this
   repo. */
const VAPID_PUBLIC_KEY = 'BNqX_cCkQevtNlR5_nvEI41OV-dBJJCmYKLVbQTRqiWiy6dHiAwDjNoXxPQu2YWC14JapK5hDDuAcZhVNGTozUU';

/* pushManager.subscribe() wants applicationServerKey as a Uint8Array, not
   the base64url string it's naturally stored/transmitted as. */
function urlBase64ToUint8Array(base64url) {
  const padding = '='.repeat((4 - (base64url.length % 4)) % 4);
  const base64 = (base64url + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
}

export function isPushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

async function getSubscription() {
  if (!isPushSupported()) return null;
  const registration = await navigator.serviceWorker.ready;
  return registration.pushManager.getSubscription();
}

export async function isSubscribed() {
  return !!(await getSubscription());
}

/* Every watchlisted film that has no screening yet — the exact set the
   server should watch on this subscriber's behalf. Recomputed fresh each
   sync rather than cached: a film graduating from "watched" to "actually
   screening" naturally drops off the list next time this runs. */
function unscreenedWatchlist() {
  const screeningFilmIds = new Set(state.screenings.map(s => s.film_id));
  return store.watchlist().filter(id => !screeningFilmIds.has(id));
}

/* Tell the server which films this subscription is watching for. Called
   right after subscribing, and again whenever the watchlist changes while
   notifications are on — the server only acts on what it's been told, so a
   stale list here means a real screening goes unnotified. */
export async function syncWatchedFilms() {
  if (!store.notifyEnabled()) return;
  const subscription = await getSubscription();
  if (!subscription) return;

  try {
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ subscription: subscription.toJSON(), filmIds: unscreenedWatchlist() }),
    });
  } catch {
    /* Offline or the Worker's briefly down — the next watchlist change or
       app open retries. Losing one sync isn't worth surfacing as an error
       for a background housekeeping call. */
  }
}

/* Returns true on success. Requesting permission and subscribing are both
   real, user-visible browser prompts/states, so the caller (the Profil
   toggle) needs to know whether it actually worked to reflect that back. */
export async function enableNotifications() {
  if (!isPushSupported()) return false;

  const permission = await Notification.requestPermission();
  if (permission !== 'granted') return false;

  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
    });

    store.setNotifyEnabled(true);
    await fetch('/api/push/subscribe', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ subscription: subscription.toJSON(), filmIds: unscreenedWatchlist() }),
    });
    return true;
  } catch {
    /* subscribe() itself can reject — a browser/OS quirk, or (harmlessly, in
       local dev) no real push service reachable. Permission was already
       granted at this point, but nothing is actually subscribed, so the
       toggle must not claim success. */
    return false;
  }
}

export async function disableNotifications() {
  store.setNotifyEnabled(false);
  const subscription = await getSubscription();
  if (!subscription) return;

  try {
    await fetch('/api/push/unsubscribe', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ subscription: subscription.toJSON() }),
    });
  } catch {
    /* The server-side record is harmless if this doesn't land — it'll stop
       mattering the moment the local unsubscribe below removes the only
       thing that could ever deliver to it. */
  }
  await subscription.unsubscribe();
}
