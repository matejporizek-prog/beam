/* ==========================================================================
   Boot splash — the projector lamp striking before Program appears.

   A narrow, down-facing beam built from the same ray recipe as the ambient
   .beam in app.js (renderRaySprite's warm/cool gradients), but NOT the same
   geometry: that fan spreads 170° as a decorative wash across the top of the
   screen, which is right for chrome sitting behind scrollable content but
   reads as a sunburst once aimed straight down as a literal projector throw.
   This one is its own narrower cone (82°), with much dimmer individual rays —
   packed into a narrow cone, rays at the ambient beam's brightness composite
   straight past white, and a clipped core cannot flicker; the whole point of
   the shimmer below is invisible once saturated.

   Each ray flickers on the app's own irregular clock — a period between 3.4
   and 7.2 seconds and a random phase, so no two rays ever brighten together
   — deepened and sped up so it reads inside a two-second boot instead of
   registering as slow ambient motion. The mark's own opacity is not a fade on
   a separate clock: it is mostly a smooth rise (the tuned "follows light"
   value is low, 20%), with a trace of the same shimmer's texture carried
   into how it settles, so it never looks like two unrelated animations
   layered on top of each other.
   ========================================================================== */

const DPR = Math.min(window.devicePixelRatio || 1, 2);
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
/* Same diagnostic flag app.js reads for .beam/.grain — honoured here too so
   ?nobeam/?nofx isolates every decorative fixed layer, not all but one. */
const NO_FX = (() => {
  const p = new URLSearchParams(location.search);
  return p.has('nobeam') || p.has('nofx');
})();
const DEG = Math.PI / 180, TAU = Math.PI * 2;
const clamp01 = x => Math.min(1, Math.max(0, x));
const smooth = (a, b, x) => { const t = clamp01((x - a) / (b - a)); return t * t * (3 - 2 * t); };

/* Tuned interactively against a live preview and fixed here — see the
   session that arrived at these: flicker depth, speed, beam length, cone
   spread, brightness, and how much the mark's opacity tracks the shimmer
   versus just fading in on its own. */
const DEPTH = 0.68, RATE = 2.1, LEN_SCALE = 1.90, SPREAD = 82, GAIN = 2.00, FOLLOW = 0.20;

const LAMP_IN = 0.42;
const EMERGE_IN = 0.34, EMERGE_OUT = 1.70;
/* How long the splash stays up at minimum, regardless of how fast data
   loads. Below this the mark's own rise (finishes at EMERGE_OUT) would be cut
   off mid-arrival on a warm cache — every subsequent open, forever, since
   this runs on every boot, not just the first. Trades a small guaranteed
   delay for the brand moment actually landing rather than flashing past. */
const MIN_DISPLAY_MS = 1750;
const FADE_MS = 500;

/* Does this browser's 2D canvas actually apply a blur filter? Verbatim copy of
   app.js's own check — older iOS Safari has no working
   CanvasRenderingContext2D.filter, and without this a ray sprite comes out a
   hard-edged rectangle: the flat "cartoon" look the ambient .beam hit before
   this check existed there. */
function canvasBlurWorks() {
  try {
    const ctx = document.createElement('canvas').getContext('2d');
    if (typeof ctx.filter !== 'string') return false;
    ctx.filter = 'blur(2px)';
    return ctx.filter === 'blur(2px)';
  } catch {
    return false;
  }
}

function raySprite(w, len, blur, warm, blurWorks) {
  const pad = Math.ceil(blur * 3) + 2;
  const sw = w + pad * 2, sh = len + pad * 2;
  const c = document.createElement('canvas');
  c.width = Math.ceil(sw * DPR); c.height = Math.ceil(sh * DPR);
  const x = c.getContext('2d');
  x.scale(DPR, DPR);
  if (blurWorks) x.filter = 'blur(' + blur + 'px)';
  const g = x.createLinearGradient(0, pad, 0, pad + len);
  /* Same two recipes as renderRaySprite() in app.js. */
  if (warm) {
    g.addColorStop(0.00, 'rgba(255,238,214,0.34)');
    g.addColorStop(0.34, 'rgba(252,224,188,0.15)');
    g.addColorStop(0.64, 'rgba(246,208,168,0.06)');
  } else {
    g.addColorStop(0.00, 'rgba(214,236,255,0.40)');
    g.addColorStop(0.34, 'rgba(190,220,252,0.18)');
    g.addColorStop(0.64, 'rgba(176,208,246,0.07)');
  }
  g.addColorStop(0.92, 'rgba(255,255,255,0)');
  x.fillStyle = g;
  x.fillRect(pad, pad, w, len);

  /* Same fallback as renderRaySprite() in app.js: no live blur, so taper the
     edges into the bitmap itself via an alpha mask instead. */
  if (!blurWorks) {
    x.globalCompositeOperation = 'destination-in';
    const edge = x.createLinearGradient(pad, 0, pad + w, 0);
    edge.addColorStop(0, 'rgba(0,0,0,0)');
    edge.addColorStop(0.5, 'rgba(0,0,0,1)');
    edge.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = edge;
    x.fillRect(pad, pad, w, len);
    x.globalCompositeOperation = 'source-over';
  }

  return { canvas: c, w: sw, h: sh, pad: pad };
}

/* A soft filled cone, baked once — the missing piece that made the ray fan
   read as a set of separate drawn streaks instead of one hazy volume of
   light with rays for texture. Same shape and role as .beam-haze/.beam-core
   in beam.css (a border-triangle wedge, heavily blurred, very low flat
   opacity), scaled to this fan's own width and length instead of ported at
   fixed pixel values, since this beam is narrower and longer than the
   ambient one it's borrowed from. */
function wedgeSprite(halfW, len, blur, color, blurWorks) {
  const pad = Math.ceil(blur * 3) + 2;
  const sw = halfW * 2 + pad * 2, sh = len + pad * 2;
  const c = document.createElement('canvas');
  c.width = Math.ceil(sw * DPR); c.height = Math.ceil(sh * DPR);
  const x = c.getContext('2d');
  x.scale(DPR, DPR);
  if (blurWorks) x.filter = 'blur(' + blur + 'px)';
  x.fillStyle = color;
  x.beginPath();
  x.moveTo(pad + halfW, pad);
  x.lineTo(pad, pad + len);
  x.lineTo(pad + halfW * 2, pad + len);
  x.closePath();
  x.fill();
  return { canvas: c, w: sw, h: sh, pad: pad };
}

function buildFan(W) {
  const s0 = W / 430;   // same reference width the ambient beam authors its fan at
  const blurWorks = canvasBlurWorks();
  let seed = 7;
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  const N = 30, rays = [];
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    const warm = rnd() < 0.4;
    const w = (rnd() < 0.3 ? (2 + rnd() * 3) : (5 + rnd() * 10)) * s0;
    const len = (760 + Math.round(rnd() * 120)) * s0;
    const blur = w > 6 * s0 ? 3.2 : 1.4;
    const centre = 1 - Math.abs(t - 0.5) * 0.7;
    // Much dimmer than the ambient beam's 0.30–0.85 peak — see the header note.
    const peak = 0.11 + 0.22 * rnd() * Math.max(centre, 0.3);
    rays.push({
      sprite: raySprite(w, len, blur, warm, blurWorks),
      t, jit: (rnd() - 0.5) * 3, peak,
      period: 3.4 + rnd() * 3.8, phase: rnd() * TAU,
    });
  }
  const haze = wedgeSprite(150 * s0, 520 * s0 * LEN_SCALE, 30, 'rgba(176,204,238,0.04)', blurWorks);
  const core = wedgeSprite(10 * s0, 460 * s0 * LEN_SCALE, 9, 'rgba(228,242,255,0.07)', blurWorks);
  return { rays, haze, core };
}

/* .beam-haze/.beam-core breathe on their own slow 6s clock in beam.css,
   independent of the rays' own fast shimmer — ported verbatim (same period,
   same .82–1 range) rather than tied to the per-ray flicker used elsewhere in
   this file, since it's the steady fill the rays flicker on top of. */
function breathe(t) {
  return 0.91 - 0.09 * Math.cos(t * (TAU / 6));
}

/* The app's own shimmer, verbatim in shape:
       0.45 + 0.55 * (sin(t·2π/period + phase) + 1) / 2
   depth pulls the 0.45 floor down to exaggerate the swing; rate scales the
   frequency, since the app's multi-second clocks are ambient motion, far too
   slow to register inside a two-second boot. */
function shimmerOf(r, t) {
  const lo = 0.45 - 0.41 * DEPTH;
  const s01 = (Math.sin(t * (TAU / (r.period / RATE)) + r.phase) + 1) / 2;
  return Math.pow(lo + (1 - lo) * s01, 1 + 1.0 * DEPTH);
}

/* What the mark is actually standing in — only the rays near the middle of
   the fan reach it, so averaging those (not the whole fan) is both truer and
   livelier: across all thirty rays the independent phases cancel out and the
   mean barely moves, which is exactly why the beam looks alive while never
   appearing to blink. */
function lightOnMark(rays, t) {
  let sum = 0, n = 0;
  for (const r of rays) {
    if (Math.abs(r.t - 0.5) > 0.22) continue;
    sum += shimmerOf(r, t); n++;
  }
  return n ? sum / n : 0.5;
}

function drawLamp(ctx, ox, oy, r, gain) {
  const g = ctx.createRadialGradient(ox, oy, 0, ox, oy, r);
  g.addColorStop(0.00, 'rgba(255,252,244,' + 0.92 * gain + ')');
  g.addColorStop(0.32, 'rgba(230,242,255,' + 0.46 * gain + ')');
  g.addColorStop(1.00, 'rgba(184,212,255,0)');
  ctx.save();
  ctx.globalCompositeOperation = 'lighter';
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(ox, oy, r, 0, TAU); ctx.fill();
  ctx.restore();
}

export function initSplash() {
  const root = document.getElementById('boot-splash');
  if (!root) return { hide: async () => {} };

  const canvas = document.getElementById('boot-canvas');
  const mark = document.getElementById('boot-mark');
  const status = document.getElementById('boot-status');
  const ctx = canvas.getContext('2d');

  let W = 0, H = 0, rays = [], haze = null, core = null;
  /* The light reaching the mark only ever occupies a narrow band — never near
     0 or 1, since averaging even a dozen independent clocks pulls hard toward
     the mean. Mapped raw against 0–1 the mark's coupling to it would be
     invisible, so the band is measured from the actual settings rather than
     guessed (a guessed one looked fine until DEPTH or RATE changed and the
     real range moved out from under it). */
  let LO = 0.38, HI = 0.61;

  function size() {
    const r = canvas.getBoundingClientRect();
    W = r.width; H = r.height;
    canvas.width = Math.round(r.width * DPR);
    canvas.height = Math.round(r.height * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    const fan = buildFan(r.width);
    rays = fan.rays; haze = fan.haze; core = fan.core;
    recomputeBand();
  }

  function recomputeBand() {
    const span = Math.max(4, (7.2 / RATE) * 1.2);   // one full beat of the slowest ray
    const vals = [];
    for (let t = 0; t < span; t += span / 160) vals.push(lightOnMark(rays, t));
    vals.sort((a, b) => a - b);
    const q = p => vals[Math.floor(p * (vals.length - 1))];
    LO = q(0.05); HI = q(0.95);
    if (HI - LO < 0.02) HI = LO + 0.02;
  }

  function render(t) {
    const ox = W / 2, oy = -H * 0.005;
    const lamp = smooth(0, LAMP_IN, t);

    ctx.clearRect(0, 0, W, H);
    ctx.save();
    ctx.globalCompositeOperation = 'lighter';

    /* Fill first, texture on top — same order beam.css stacks its layers in
       (haze, then core, then the rays). Without this the rays were the whole
       picture: a set of individually-soft but separate streaks, which is
       what read as drawn/illustrated rather than one hazy volume of light. */
    const fill = lamp * breathe(t);
    if (haze) {
      ctx.globalAlpha = fill;
      ctx.drawImage(haze.canvas, ox - haze.w / 2, oy - haze.pad, haze.w, haze.h);
    }
    if (core) {
      ctx.globalAlpha = fill;
      ctx.drawImage(core.canvas, ox - core.w / 2, oy - core.pad, core.w, core.h);
    }

    for (const r of rays) {
      const a = r.peak * lamp * shimmerOf(r, t) * GAIN;
      if (a <= 0.0012) continue;
      ctx.globalAlpha = Math.min(1, a);
      ctx.save();
      ctx.translate(ox, oy);
      ctx.rotate((-SPREAD / 2 + r.t * SPREAD + r.jit) * DEG);
      const sp = r.sprite;
      ctx.drawImage(sp.canvas, -sp.w / 2, -sp.pad, sp.w, sp.h * LEN_SCALE);
      ctx.restore();
    }
    ctx.restore();

    const onMark = lightOnMark(rays, t);
    const norm = clamp01((onMark - LO) / (HI - LO));
    // Radius matched to .beam's own mobile aperture glow (150px at its 430px
    // reference width) — the previous 0.20 read as a small, drawn-looking dot
    // rather than a soft source the haze/core fill visibly comes from.
    drawLamp(ctx, ox, oy, W * 0.35, lamp * (0.30 + 0.70 * norm) * Math.min(1.4, GAIN));

    /* Two jobs, kept separate: `gate` decides whether the mark has arrived yet
       (a threshold starting above anything the shimmer can reach, falling
       through its range — so at FOLLOW near 1 only the bright peaks would
       clear it first, in glimpses; at this tuned-down FOLLOW=0.20 the plain
       fade dominates and gate mostly just softens its edges). `breathe` is
       what it does once there — still riding the shimmer, across a band that
       keeps it readable instead of dropping toward nothing. */
    const emerge = smooth(EMERGE_IN, EMERGE_OUT, t);
    const thr = 1.02 - 1.30 * emerge;
    const gate = clamp01((norm - thr) / 0.26);
    const markGlow = 0.55 + 0.45 * norm;
    const shimmerVis = gate * markGlow;
    const steadyVis = emerge;
    const vis = (1 - FOLLOW) * steadyVis + FOLLOW * shimmerVis;

    mark.style.setProperty('--lit', (lamp * vis).toFixed(3));
    status.style.setProperty('--st', t > 1.8 ? 1 : 0);
  }

  const start = performance.now();
  let raf = null;

  if (REDUCED || NO_FX) {
    /* No shimmer loop: draw once, settled, and let the mark simply be there —
       matching how .beam/.grain are held static under the same conditions
       elsewhere in the app. */
    size();
    render(3.0);
    mark.style.setProperty('--lit', '1');
    status.style.setProperty('--st', '1');
  } else {
    size();
    addEventListener('resize', size);
    const loop = now => {
      render((now - start) / 1000);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
  }

  let hidden = false;

  /* immediate: true skips the minimum-display wait — used on the error/empty
     paths, where holding the splash up for the brand moment makes no sense
     when what's about to show instead is a failure message, not the app. */
  async function hide({ immediate = false } = {}) {
    if (hidden) return;
    hidden = true;

    if (!immediate && !REDUCED && !NO_FX) {
      const elapsed = performance.now() - start;
      const remaining = MIN_DISPLAY_MS - elapsed;
      if (remaining > 0) await new Promise(r => setTimeout(r, remaining));
    }

    if (raf) cancelAnimationFrame(raf);
    root.classList.add('hide');
    await new Promise(r => setTimeout(r, immediate ? 0 : FADE_MS));
    root.remove();   // free the canvas and its ray sprites once it's gone
  }

  return { hide };
}
