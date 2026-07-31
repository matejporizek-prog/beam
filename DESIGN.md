---
name: Beam
description: A calm, near-black screening-room interface for deciding what's worth seeing in Prague this week
colors:
  bg: "#0C0E11"
  sprocket: "#04060A"
  card: "#191D23"
  card-edge: "#2C333C"
  line: "#252A31"
  text: "#ECEFF3"
  text-secondary: "#9BA5B0"
  text-tertiary: "#828A94"
  champagne: "#E7C98A"
  champagne-dim: "#8A7645"
  poster-mark: "#B89660"
typography:
  display:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "25px"
    fontWeight: 600
    lineHeight: 1.08
    letterSpacing: "normal"
  headline:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "21px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
  title:
    fontFamily: "Spectral, Georgia, serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: "normal"
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "IBM Plex Mono, monospace"
    fontSize: "10.5px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "0.14em"
rounded:
  sm: "5px"
  md: "9px"
  lg: "13px"
  pill: "20px"
  full: "50%"
spacing:
  xs: "4px"
  sm: "8px"
  md: "13px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.champagne}"
    textColor: "{colors.bg}"
    typography: "{typography.body}"
    rounded: "{rounded.md}"
    padding: "14px"
  icon-button:
    backgroundColor: "{colors.card}"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.full}"
    size: "42px"
  icon-button-active:
    backgroundColor: "{colors.card}"
    textColor: "{colors.champagne}"
    rounded: "{rounded.full}"
    size: "42px"
  chip-format:
    backgroundColor: "{colors.champagne}"
    textColor: "{colors.bg}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "2px 6px"
  chip-version:
    backgroundColor: "transparent"
    textColor: "{colors.champagne}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    padding: "2px 6px"
  pill-filter:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "7px 15px"
  pill-filter-selected:
    backgroundColor: "rgba(231,201,138,0.08)"
    textColor: "{colors.champagne}"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    padding: "7px 15px"
---

# Design System: Beam

## Overview

**Creative North Star: "The Projection Booth"**

Beam reads as the room behind the screen, not the screen itself: the technical, precise space where the show actually gets run. Near-black surroundings, one warm instrument light (the champagne accent), and information laid out the way a booth operator would want it — legible timestamps in a monospace face, an editorial serif for the film titles that actually matter, everything else quiet. The 35mm sprocket motif on the bottom nav and the accent stripe on every poster tile aren't decoration bolted on after the fact; they're the one place the app admits it's about physical film.

The palette is almost entirely achromatic — background, cards, borders and three text tones are all cool near-black-to-gray — with exactly one warm color in the entire system. That scarcity is deliberate: champagne shows up only where something needs to register as *live, selected, or active*, never as base decoration. A confirmed rejection along the way: the prototype's original chip system gave every tag (format and language-version alike) the same filled-champagne treatment, which meant "35mm" and "dabing" differed only by reading the label text — fixed by making a FORMAT a filled chip and a LANGUAGE VERSION an outlined one, so meaning lives in the shape, not just the word.

At rest, everything in Beam is flat — no card ever floats on its own shadow. The system reserves depth for the rare moment something is genuinely leaving the page's plane: a poster edge lifting out of a hero image, a toast hovering over the bottom nav, a map popup over the map itself. Depth is earned, not applied by default.

**Key Characteristics:**
- One accent color (champagne) on an otherwise achromatic, near-black palette — its rarity is the signal
- Flat by default; soft shadows exist only for elements that are genuinely floating above other content
- Serif (Spectral) carries anything that's a title a human chose to make; mono (IBM Plex Mono) carries anything mechanical — times, counts, uppercase eyebrow labels
- A physical-film signature (sprocket perforations, a poster-edge film-stock stripe) used sparingly, not as a repeating background texture
- Meaning lives in shape, not just color or text: filled vs. outlined chips, a lone dot vs. a full row of them, a circle vs. a pill

## Colors

Almost the whole interface is a five-step near-black-to-white neutral scale; champagne is the only saturated color in the system, and it never appears as a base fill — only as a state.

### Primary
- **Champagne** (`#E7C98A`): the one live/active/selected signal in the whole app — the active day, a saved heart, an "on" toggle, a filled format chip, the primary action button's fill, map markers and popup accents. If something is champagne, it means "this is the one that's active, selected, or true right now."
- **Champagne Dim** (`#8A7645`): champagne's own quiet twin, used for borders and outlines on selected-but-not-filled states (an active day's border, an outlined language-version chip, a selected filter pill's edge) — never as a fill on its own.

### Neutral
- **Void** (`#0C0E11`): the base background — cool, near-black, never pure black.
- **Sprocket Black** (`#04060A`): deeper than Void, reserved for the 35mm perforation holes on the bottom nav, where they need to read against a background that's already dark.
- **Card** (`#191D23`): every raised-but-flat surface — day-strip buttons, filter chips' resting state, the filter sheet, poster placeholders, the map container.
- **Card Edge** (`#2C333C`): the border on Card surfaces — poster tiles, the sheet's top edge, icon-button rings.
- **Line** (`#252A31`): hairline dividers between list rows — the day strip, program rows, the filter sheet's section breaks.
- **Text** (`#ECEFF3`): primary reading text — titles, body copy, active labels. Never pure white.
- **Text Secondary** (`#9BA5B0`): supporting text that still needs to read clearly — sub-labels, secondary metadata, unselected pill text.
- **Text Tertiary** (`#828A94`): the quietest tier — day-of-week labels, timestamps on past screenings, placeholder and disabled text. Lightened from an earlier `#69707A` (2026-07-31): that value measured 3.9:1 on Void and 3.4:1 on Card, both below the 4.5:1 AA minimum, on a token used almost everywhere as real text.

### Named Rules
**The One Voice Rule.** Champagne is the only color in the entire system that means something is happening — active, saved, on, selected. It never appears as passive decoration; if you're using it, you're marking state.

**The Shape-Over-Color Rule.** Where two things could be confused by color alone (a format vs. a language version, a selected vs. unselected pill), the fix is a shape or fill difference — filled vs. outlined — not a second color.

## Typography

**Display Font:** Spectral (with Georgia, serif fallback)
**Body Font:** Archivo (with system-ui, sans-serif fallback)
**Label/Mono Font:** IBM Plex Mono (with monospace fallback)

**Character:** Spectral is the only font that gets to carry a human decision — a film's title, a section heading, a day number. Archivo is neutral, quiet workhorse prose. IBM Plex Mono is reserved for anything mechanical or systemic: clock times, counts, uppercase eyebrow labels — its presence is the visual signal that "this is data, not a choice."

### Hierarchy
- **Display** (600, 25px, line-height 1.08): the detail overlay's film title — the single most important piece of text on any screen.
- **Headline** (600, 21–22px): sheet and empty-state titles ("Filtr", "Nic tu není").
- **Title** (600, 18px / 500, 15–16px): dense list-row film titles (Program, search results, watchlist rows).
- **Body** (400, 14–15px): synopsis text, filter row labels, form inputs.
- **Label** (400–500, 9.5–11px, letter-spacing 0.08–0.16em, uppercase): day-of-week, section eyebrows, chip text, timestamps, the day strip's numerals' unit label.

### Named Rules
**The Mechanical-Face Rule.** Any text that's measured rather than chosen — a time, a count, a percentage, a machine-generated label — is IBM Plex Mono, usually uppercase and letter-spaced. The moment content is a human's editorial choice (a title, a synopsis), it switches to Spectral or Archivo.

## Layout

Single-column, mobile-first, capped at a 430px content width even on desktop — the app never becomes a wider desktop layout, it just centers the same phone-shaped column. A consistent 20px horizontal gutter runs through every screen; dense list rows use 13px vertical padding with a single hairline (`--line`) between them rather than card borders around each row — the list reads as one continuous ledger, not a stack of separate cards. Bottom nav height is fixed (68px) and reserved as scroll padding so content never sits under it. Overlays (the film detail view, the filter sheet, search) replace the document's scroll entirely rather than nesting an inner scroll container — a deliberate structural fix for iOS Safari's scroll-freeze bug on nested `position: fixed` + `overflow-y: auto` panels; every full-screen overlay in this app scrolls the page itself.

## Elevation & Depth

Flat by default — list rows, chips, pills, and cards carry no shadow at rest; separation comes entirely from the `--line` hairline and background-tone contrast (Card vs. Void). Shadows are reserved for the handful of elements that are literally floating above other content: a poster lifting out of the detail hero, a toast hovering over the bottom nav, a map marker's popup sitting over the map. All three share the same soft, wide, dark shadow recipe.

### Shadow Vocabulary
- **Floating disc** (`box-shadow: 0 10px 28px -12px rgba(0,0,0,.9)`): the detail overlay's poster, lifting off the hero image behind it.
- **Floating panel** (`box-shadow: 0 12px 30px -14px rgba(0,0,0,.95)`): the toast and the map's Leaflet popup — anything transiently overlaid on top of the current screen.

### Named Rules
**The Floating-Only Rule.** A shadow appears exactly when an element is visually leaving the page's own plane — sitting on top of something else, not just next to it. Everything else stays flat, distinguished by hairlines and tone alone.

## Shapes

Corners are always rounded — nothing in the app is a hard rectangle — but the radius stays modest and functional rather than a soft/bubbly signature: 5px on the smallest chip/poster-thumbnail scale, 9px on day-strip and input-scale controls, 13px on card-scale containers (the map, score cards, empty-state marks), up to 20px only on the filter sheet's top corners and full pill shapes for filter tags. Icon-scale actions (search, close, save, nav) are always full circles, never rounded squares. The one recurring physical motif is the 35mm film reference: a thin repeating-perforation stripe along a poster tile's left edge, and a full sprocket-hole rail along the top and bottom of the bottom nav — both quiet enough to read as texture, not as loud branding.

## Components

### Buttons
- **Shape:** rounded rectangle, 9–12px radius depending on scale; icon-only actions are always full circles (`border-radius: 50%`).
- **Primary:** filled Champagne background, Void text, 600-weight Archivo — used for the single most committal action on a screen (apply filters, buy tickets).
- **Icon buttons:** a flat Card-colored disc with a Card Edge ring at rest; on press or when representing an "on" state, the icon and border shift to Champagne / Champagne Dim with no fill change.
- **Secondary text buttons** (clear filters, "Celý měsíc"): no background at all, Text Tertiary or Champagne label depending on whether the action is destructive/neutral or affirmative.

### Chips
- **Format chip** (`.chip.fmt`): filled Champagne background, Void text — a physical fact about the presentation (35mm, 70mm).
- **Language-version chip** (`.chip.dab`): transparent background, Champagne text, Champagne Dim outline — a characteristic of the screening, not a hard fact about the film print. This filled-vs-outlined split is the system's clearest instance of the Shape-Over-Color Rule.
- **Neutral chip** (`.chip.eng`): transparent, Text Secondary, plain Line-colored outline — informational only, carries no "this is active" meaning at all.

### Filter Pills
- **Style:** fully rounded (20px), transparent background, Line-colored border, Text Secondary label at rest.
- **Selected:** Champagne text and border, a faint `rgba(231,201,138,.08)` Champagne-tinted fill — a wash, not a hard fill, so several selected pills next to each other stay legible rather than turning into solid blocks.

### List Rows
- **Style:** no card background or border of their own — full-bleed rows separated only by a `--line` hairline, 13px vertical padding, 12px internal gap between poster/time/title/action.
- **State:** a past or filtered-out row drops to 40–45% opacity rather than being hidden, so the day's full shape stays visible even when most of it is over.
- **Press:** a barely-there `rgba(255,255,255,.02)` tint on `:active` — deliberately subtle; touch feedback here is closer to a soft acknowledgment than a visible highlight.

### Toggle (Switch)
- **Style:** a pill track (Line color, off) with a circular knob (Text Secondary, off). On, the track shifts to Champagne Dim and the knob to Champagne, sliding to the far side — the same on/off shape language as any native OS switch, restated in Beam's own palette.
- **Disabled:** the whole control drops to 35% opacity with no pointer events — legible as "cannot be used right now" rather than inviting a tap that silently fails.

### Navigation (bottom nav)
- **Style:** a near-black film-base strip with rounded-rectangle sprocket perforations tiled along the top and bottom edges — a literal 35mm film-strip reference, not a metaphorical one.
- **Default / Active:** icon and label sit in Text Tertiary at rest; the active destination is marked purely by both turning Champagne — no background pill or box behind the active item, since the perforation rails already carry the "this is a strip of frames" visual, and a boxed active state would compete with it.

### Poster Tile (signature)
- A monogram-letter placeholder (Poster Mark on a dark diagonal gradient) shows immediately; the real TMDb or cinema poster crossfades in over it once loaded, so there's never an empty box.
- **Poster Mark** (`#B89660`) is a dedicated color for this one initial-letter text, not Champagne Dim — Champagne Dim measured 3.0:1 against this tile's own gradient, below AA, but every other use of Champagne Dim is a border or fill (day-strip borders, chip outlines, the switch track) where the 3:1 non-text threshold applies, not 4.5:1. Lightening the shared token to fix this one text use would have over-corrected everything else it touches; Poster Mark clears AA on both ends of the gradient (4.7:1 / 6.1:1) without moving any of Champagne Dim's other uses at all.
- A thin repeating-perforation stripe runs down the tile's left edge at low opacity — the same sprocket motif as the nav, scaled down to a texture rather than a statement.

## Do's and Don'ts

### Do:
- **Do** keep Champagne rare. If more than roughly one element per screen is champagne-colored, something that isn't actually "active" is being marked as if it were.
- **Do** default every new surface to flat, and only add the Floating Panel/Disc shadow when the element is truly overlapping something else, not just sitting near it.
- **Do** use IBM Plex Mono for anything measured or generated (times, counts, dates) and Spectral/Archivo for anything a person wrote or chose.
- **Do** distinguish similar-meaning tags by shape (filled vs. outlined) before reaching for a second color.

### Don't:
- **Don't** give a format fact (35mm, 70mm) and a presentation characteristic (dubbed, subtitled) the same filled-chip treatment — that's the exact ambiguity this system already fixed once.
- **Don't** add a card background or border around list rows. Rows are a continuous ledger separated by hairlines, not a stack of boxed cards.
- **Don't** introduce a second saturated color. The system's whole legibility trick is that champagne is the only color that ever means "this one."
- **Don't** build a new full-screen view as a `position: fixed` panel with its own inner `overflow-y: auto` scroll — every overlay in this app deliberately scrolls the document itself, a structural fix for a real iOS Safari bug, not a style preference.
