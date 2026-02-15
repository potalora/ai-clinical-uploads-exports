# Theme Redesign: "Forest Floor"

## Summary

Full visual theme redesign from "Nostromo Earth Terminal" (heavy CRT sci-fi) to "Forest Floor" — a warm, grounded health dashboard using deep greens, warm browns, and cream tones. Flow and functionality stay the same. The only sci-fi nod: monospace font for clinical data readouts.

## Design Direction

**Tone**: Warm, approachable, organic. Like opening a well-made leather journal in a cabin.

**Sci-fi retention**: ~5-10%. Monospace font for data (lab values, dates, codes) only. Everything else is natural and grounded.

**Light/Dark mode**: Both are first-class experiences with a toggle. No default preference.

---

## Color Palette

### Light Mode

| Role | Hex | Description |
|------|-----|-------------|
| Background (deep) | `#f7f4ef` | Warm cream |
| Surface | `#efe9df` | Parchment |
| Card | `#ffffff` | Clean white |
| Card hover | `#faf6f0` | Warm white |
| Primary text | `#2a2f26` | Forest dark |
| Dim text | `#5c6358` | Bark gray |
| Muted text | `#6b7265` | Sage gray |
| Primary accent | `#4a7c59` | Deep moss green |
| Accent dim | `#3d6649` | Darker moss |
| Secondary accent | `#b8860b` | Dark goldenrod |
| Destructive | `#b54834` | Muted terracotta |
| Borders | `#d4cdc0` | Warm stone |
| Border active | `#b8b0a0` | Darker stone |

### Dark Mode

| Role | Hex | Description |
|------|-----|-------------|
| Background (deep) | `#1c2118` | Deep forest floor |
| Surface | `#262f22` | Mossy bark |
| Card | `#2f3a2a` | Forest shadow |
| Card hover | `#384432` | Lighter forest |
| Primary text | `#e4dfd4` | Warm light |
| Dim text | `#a0a896` | Light lichen |
| Muted text | `#8a9182` | Lichen |
| Primary accent | `#6aa67a` | Bright moss |
| Accent dim | `#558a62` | Mid moss |
| Secondary accent | `#d4a843` | Warm gold |
| Destructive | `#d06040` | Warm terracotta |
| Borders | `#3a4436` | Forest edge |
| Border active | `#4a5a42` | Lighter forest edge |

### Record Type Colors

All 14 record types keep distinct colors but shift to the forest palette:
- Conditions: goldenrod/ochre
- Observations: moss green
- Medications: warm terracotta/coral
- Encounters: teal (muted)
- Immunizations: gold
- Procedures: slate blue (muted)
- Documents: warm gray
- Allergies: terracotta red
- Imaging: muted plum
- Others: variations within the earth palette

---

## Typography

No font changes — the current choices are strong:

| Role | Font | Usage |
|------|------|-------|
| Headings | Playfair Display | Warm, editorial serif |
| Body | IBM Plex Sans | Clean, readable sans-serif |
| Data/Mono | IBM Plex Mono | Lab values, dates, codes — the subtle sci-fi nod |

**Key change**: Remove uppercase + tracking-wider from buttons, tabs, and badges. Use sentence-case throughout.

---

## Effects: Remove vs. Replace

### Remove entirely
- CRT scanline overlay (`crt-scanlines` class)
- Vignette overlay (`crt-vignette` class)
- Phosphor glow text-shadows (`crt-glow`, `crt-glow-strong`)
- Pulse-glow animation on buttons
- Subtle-flicker animation
- Blinking cursor animation + `blink-cursor::after`
- Loading-dots animation (replace with a simple spinner or fade)
- F-key shortcut labels in nav bar
- `retro-focus-glow`, `retro-hover-glow`, `retro-underline-glow`

### Replace with
- **Shadows**: Soft warm box-shadows for depth (paper/card feel)
- **Hover states**: Gentle background-color shifts, subtle border darkening
- **Focus states**: Standard ring with primary accent color
- **Transitions**: Smooth `transition-colors duration-200 ease-out` everywhere
- **Page entrance**: Keep `fade-in-up` — it's pleasant and not sci-fi
- **Staggered children**: Keep `retro-stagger` with `fade-in-up` — subtle and nice
- **Loading**: Simple pulsing dot or fade animation

---

## Component Changes

### CRTOverlay → Remove
Delete the component. No global overlay needed.

### GlowText → Simplify to "DisplayText"
Remove glow effect. Keep the polymorphic heading component but with Playfair Display and normal text rendering. No text-shadow.

### RetroCard → Soften
- Remove glowing border-top accent
- Add soft warm box-shadow (`0 1px 3px rgba(0,0,0,0.08)`)
- Rounded corners (`rounded-lg`)
- Gentle hover: slightly elevated shadow

### RetroButton → Naturalize
- Remove pulse-glow animation
- Remove uppercase + tracking-wider
- Rounded corners (`rounded-md`)
- Primary: moss green background, white text
- Ghost: transparent with border, hover background shift
- Destructive: terracotta background
- Hover: slight brightness/background shift, no glow

### RetroNav → Clean up
- Remove F-key labels
- Keep theme toggle (sun/moon)
- Keep logout button
- Simpler active-tab indicator: bottom border in primary accent, no glow
- Sentence-case labels

### RetroTabs → Simplify
- Remove separator characters (`|`)
- Remove glow on active tab
- Active: primary accent color + bottom border with smooth transition
- Inactive: muted text, hover to dim text
- Sentence-case

### RetroBadge → Soften
- Softer rounded corners (`rounded-md`)
- Sentence-case labels (or keep short codes like "COND" since they're data)
- Colors from new record-type palette

### RetroInput → Standard warmth
- Remove glow on focus
- Standard focus ring with primary accent
- Warm background tint

### RetroTable → Clean
- Remove amber header styling
- Subtle alternating row backgrounds
- Clean borders in warm stone color
- Hover: gentle background shift

### RetroLoadingState → Simplify
- Remove blinking cursor block character
- Simple pulsing animation or three-dot fade
- Keep centered layout

### StatusReadout → Simplify
- Remove `|` separators
- Clean label/value pairs with natural spacing
- No glow

### TerminalLog → Simplify to "ActivityLog"
- Keep timestamp + record type tag + text structure
- Remove terminal aesthetic
- Use record-type badge colors
- Clean list layout

### RecordDetailSheet → Minimal changes
- Inherit new colors/shadows from theme
- No specific redesign needed

---

## CSS Custom Properties Structure

Same architecture (`:root` + `.dark` with CSS custom properties). Variable names stay the same (`--retro-*`) to minimize component code changes — only the values change. This means we primarily edit `globals.css` color values and effect classes, not every component file.

Wait — actually, rename `--retro-*` to `--theme-*` since the retro branding no longer fits. This is a search-and-replace across all component files but prevents confusion going forward.

**Decision**: Rename `--retro-*` → `--theme-*` across all files.

---

## Scope of File Changes

| Area | Files | Change type |
|------|-------|-------------|
| `globals.css` | 1 | Major: new colors, remove CRT effects, new utility classes |
| `components/retro/` | 13 | Moderate: restyle each, rename some, remove CRTOverlay |
| `lib/constants.ts` | 1 | Minor: update record-type color variable names |
| `app/layout.tsx` | 1 | Minor: update default theme if needed |
| `Providers.tsx` | 1 | Minor: change `defaultTheme` from "dark" to "system" |
| Page files | ~10 | Minor: remove references to CRT classes, update component imports |

---

## What stays the same

- All page routes and navigation flow
- All API calls and data fetching logic
- React Query / Zustand state management
- Component props interfaces (where possible)
- Font choices (Playfair Display, IBM Plex Sans, IBM Plex Mono)
- next-themes integration for light/dark toggle
- shadcn/ui base components
- 12-tab admin console structure
- Record detail sheet functionality
