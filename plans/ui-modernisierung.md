# UI-Modernisierung – „Apple-Grade" Evolutionsstufe

> **Status:** Plan / nicht begonnen
> **Betreff:** `epf-eink-addon/templates/settings.html` (aktuell ~1 220 Zeilen, Einseiter)
> **Ziel:** Komplett neues visuelles Erscheinungsbild – ruhig, präzise, Apple-Website-inspiriert –
> umgesetzt als **inkrementelle Phasen**, jeweils eigenständig deploy- & test-bar.

---

## 0 · Zusammenfassung der Entscheidungen

| Aspekt | Entscheidung |
|--------|-------------|
| Ansatz | **Vollständiger Rewrite** des Stils & der Layout-Struktur (DOM-IDs bleiben stabil für Tests) |
| Design-Sprache | Apple Web: Weißraum, Monochrom + 1 Akzent, 20 px Radien, Frosted Glass, Light-Type, subtile Schatten, sanfte Animationen |
| Navigation | **3 Tabs**: *Dashboard* · *Configuration* · *Gallery* (Tab (a) aus der Anfrage) |
| Responsiv | Desktop-first; Mobile (< 768 px) erhält gestapelten Flow, Touch-targets ≥ 44 px |
| Farbe | Neutrales Grau/Weiß-Basis; **dynamischer Akzent** = dominante Farbe des aktuell geladenen Fotos (client-side Canvas-Extraktion) |
| Dark Mode | Manueller Toggle (wie bisher), respektiert `localStorage`; kein Auto-OVERRIDE |
| Runtime | i7 8700 → keine Performance-Sorgen; aber **kein Build-Step**: reines CSS + Vanilla-JS inline im HTML (CSP-safe) |
| Icons | **Inline SVG** (Lucide-Style, 20 px, 1.5 px Stroke) – konsistent, skalierbar, kein Emoji-Mix |
| Fonts | System-Stack (`-apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif`) – **keine externen Font-Downloads** (CSP + Latenz) |
| Testbarkeit | Alle existierenden Element-**IDs** werden beibehalten; neue Wrapper-Elemente erhalten neue, dokumentierte IDs; `conftest.py`-Mocks und `responses`-Pfade müssen unangetastet funktionieren |

---

## 1 · Design-Token (Grundlage aller Phasen)

### 1.1 Farbsystem

```
--surface-0      : #ffffff  (Light) / #1c1c1e  (Dark)   – Seite-Hintergrund
--surface-1      : #f5f5f7  (Light) / #2c2c2e  (Dark)   – Karten, Panels
--surface-2      : #e8e8ed  (Light) / #3a3a3c  (Dark)   – Inputs, Chips
--border-subtle  : rgba(0,0,0,.06) / rgba(255,255,255,.08)
--text-primary   : #1d1d1f  / #f5f5f7
--text-secondary : #6e6e73  / #a1a1a6
--text-tertiary  : #86868b  / #636366

--accent         : DYNAMIC (default #007AFF → Apple-Blue)
--accent-soft    : color-mix(in srgb, var(--accent) 15%, transparent)
--accent-glow    : color-mix(in srgb, var(--accent) 30%, transparent)
```

**Dynamischer Akzent:** Beim Laden/Bilden eines Previews extrahiert der Client die dominante
Farbe (kleiner Canvas, K-Means-lite mit 4 Clustern) und setzt `--accent` + abgeleitete Variablen.
Fallback = `#007AFF`. Der Akzent färbt: Header-Gradient, Primary-Buttons, Slider-Thumb, Health-Dot,
aktivem Tab-Unterbalk – **nicht** den Body-Hintergrund (bleibt neutral).

### 1.2 Typografie-Skala

| Token | Größe | Weight | Einsatz |
|-------|-------|--------|---------|
| `--fs-display` | clamp(2.0 rem, 4vw, 2.75 rem) | 300 | Page-H1 (Hero) |
| `--fs-h2` | 1.375 rem | 500 | Card-Titel, Tab-Label |
| `--fs-body` | 1.0 rem | 400 | Fließtext |
| `--fs-small` | 0.875 rem | 400 | Labels, Hints |
| `--fs-caption` | 0.75 rem | 400 | Timestamps, Footer |

Line-height: 1.6 (body), 1.2 (headings). Letter-spacing: `-0.01em` (display), `0` (rest).

### 1.3 Spacing & Radius

```
--space-xs : 0.25rem   --space-sm : 0.5rem   --space-md : 1rem
--space-lg : 1.5rem    --space-xl : 2.5rem   --space-2xl: 4rem

--radius-sm : 10px    --radius-md : 16px    --radius-lg : 20px    --radius-xl : 24px
--radius-full: 9999px
```

### 1.4 Schatten & Glass

```
--shadow-1 : 0 1px 3px rgba(0,0,0,.04)         /* barely-there */
--shadow-2 : 0 4px 12px rgba(0,0,0,.06)        /* cards */
--glass-bg   : rgba(255,255,255,.72);         /* light frosted */
--glass-bg-d : rgba(28,28,30,.72);            /* dark frosted  */
--glass-blur : 20px;
--glass-border: 1px solid rgba(255,255,255,.18); /* subtle edge */
```

### 1.5 Motion

```
--ease-out-soft : cubic-bezier(.25,.8,.25,1);
--ease-spring   : cubic-bezier(.34,1.56,.64,1);   /* micro-bounce */
--dur-fast  : 150ms;
--dur-med   : 250ms;
--dur-slow  : 400ms;
```

All animations use `transform` + `opacity` only (GPU-composited, no layout thrash).

---

## 2 · Phasen-Plan

### Phase 1 – Design-Foundation & Tokens *(~1 Tag)*

**Ziel:** Alle design tokens (Abschnitt 1) als `:root` / `[data-theme="dark"]` CSS Custom Properties
im `<style>`-Block definieren. **Kein** sichtbares Layout-Change noch.

Aufgaben:
- [ ] `:root` + `[data-theme="dark"]` Token-Blöcke schreiben (Farbe, Type, Space, Radius, Shadow, Glass, Motion)
- [ ] Base-Styles: `body`, `*`, headings, links auf Tokens umstellen
- [ ] Frosted-glass utility: `.glass { background: var(--glass-bg); backdrop-filter: blur(var(--glass-blur)); border: var(--glass-border); }`
- [ ] Icon-Set: 12–15 Inline-SVGs (camera, gear, moon, sun, battery, power, image, gallery, chevron, check, x, alert, refresh) als HTML-Template-Block oberhalb des `<style>` (oder direkt in den Slots)
- [ ] **Check:** Bestehende Tests (`pytest tests/`) grün (nur Styles geändert, keine ID-Changes)

**Abnahmekriterium:** Seite sieht noch wie vorher, aber alle Farben/Radien/Shadows kommen aus Tokens;
Dark-Mode funktioniert per Toggle.

---

### Phase 2 – Layout-Überbau & Navigation *(~1–2 Tage)*

**Ziel:** Von der flachen Card-Liste zur **3-Tab-Architektur** mit Frosted-Glass-Header.

Neues DOM-Skelett (IDs aus alter Datei bleiben):

```
<header class="glass">                     ← sticky, frosted
  <nav class="tab-bar">
    <button data-tab="dashboard" class="tab active">Dashboard</button>
    <button data-tab="configuration" class="tab">Configuration</button>
    <button data-tab="gallery" class="tab">Gallery</button>
  </nav>
  <div class="header-status">
    <span class="chip health-chip" id="healthStatus">…</span>
    <span class="chip battery-chip" id="batteryChip">…</span>
    <button class="icon-btn" id="themeToggle">…</button>
  </div>
</header>

<main class="page">
  <section id="tab-dashboard" class="tab-panel active">
    <!-- Hero: current photo (groß, 16:10), delivered-at, battery -->
    <!-- Quick Actions: Prepare / Cleanup / Gallery -->
    <!-- Next Photo: original + processed side-by-side -->
  </section>

  <section id="tab-configuration" class="tab-panel">
    <!-- Source Selection (pill / segmented control) -->
    <!-- Source-specific panels (Immich / ComfyUI-HA / ComfyUI-Direct) -->
    <!-- Display Settings (sliders, selects) -->
    <!-- Power Management -->
    <!-- Footer: Save + Reset -->
  </section>

  <section id="tab-gallery" class="tab-panel">
    <!-- Grid of preview thumbnails -->
  </section>
</main>

<footer class="page-footer">…</footer>
```

Aufgaben:
- [ ] Header mit `position: sticky`, `backdrop-filter: blur(20px)`, `border-bottom: var(--glass-border)`
- [ ] Tab-Bar: horizontaler Row, aktive Tabs erhalten `--accent` Unterbalk (2 px) + voll-Alpha Text; inaktive `--text-tertiary`
- [ ] Tab-Panels: `display: none` / `.active { display: block; animation: fadeIn var(--dur-med) var(--ease-out-soft) }`
- [ ] **Dashboard-Hero:** aktuelles Foto groß (max-width 640 px, 16:10), darunter "Delivered at …", Battery/Health-Chips kompakt daneben
- [ ] **Next Photo:** zwei gleich große Panels (Original | Processed), aspect-ratio 5:3
- [ ] **Quick-Actions:** drei Buttons in einer Reihe (Prepare = primary/filled, Cleanup = secondary/outlined, Gallery = ghost)
- [ ] **Configuration-Tab:** Sub-Karten (Source, Display, Power) als `--surface-1` Cards mit `--radius-lg`, großzügige interne `--space-xl`
- [ ] **Source-Selection:** Horizontaler **Segmented Control** (iOS-Style: pill mit animierter Slide-Background) statt `<select>`
- [ ] **Gallery-Tab:** Responsive grid (`grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))`), Click → full-size overlay
- [ ] Mobile (< 768 px): Tabs werden horizontal scrollable; Cards stapeln sich vertikal; Touch-targets ≥ 44 px
- [ ] **Check:** Alle IDs aus `conftest.py` + `test_*.py` weiterhin vorhanden & erreichbar

**Abnahmekriterium:** Funktionales Äquivalent der alten Seite, 3 Tabs, Frosted-Header,
Mobile-Layout funktioniert (DevTools 375 px).

---

### Phase 3 – Komponenten-Restyle *(~1–2 Tage)*

**Ziel:** Alle Eingabe-Elemente auf das Apple-Grid bringen.

- [ ] **Inputs** (`text`, `select`, `textarea`): `--surface-2` bg, `--radius-md`, 1 px `--border-subtle`,
      Focus: `box-shadow: 0 0 0 3px var(--accent-glow)` + `border-color: var(--accent)`;
      Padding `--space-sm --space-md`; Font `--fs-body`
- [ ] **Sliders** (range): Track 4 px `--surface-2`, Thumb 20 px circle `--accent`,
      Value-Bubble als kleine Pill (`--radius-full`, `--accent` bg, weißes Text)
- [ ] **Buttons:**
      - Primary: `--accent` bg, weißes Text, `--radius-md`, `padding: 0.75rem 1.5rem`,
        Hover: `brightness(1.1)`, Active: `scale(.98)`
      - Secondary (Outlined): transparent bg, 1.5 px `--accent` border, `--accent` text
      - Ghost: transparent, `--text-secondary` text, Hover: `--surface-1` bg
- [ ] **Chips** (Health, Battery): `--radius-full`, `padding: 0.3rem 0.75rem`, `--surface-1` bg,
      0.75 rem Text, Colored Dot 6 px inline
- [ ] **Modals** (Confirm, Gallery-Overlay): `--glass-bg` bg, `backdrop-filter: blur(30px)`,
      `--radius-xl`, `--shadow-2`, Content max-width 440 px
- [ ] **Notifications** (Toast): `--glass-bg`, `--radius-md`, bottom-right,
      slide-up + fade animation, `--dur-med`
- [ ] **Cards:** `--surface-1` bg, `--radius-lg`, `--shadow-1`, `border: 1px solid --border-subtle`;
      Hover: `--shadow-2` (subtler als heute)
- [ ] **Error-Banner:** `--accent`-tinted left border 3 px, `--surface-1` bg, `--radius-md`
- [ ] **Footer:** `--text-tertiary`, `--fs-caption`, generous top-margin, keine harte Border-Trennung
- [ ] **Check:** Pytest grün; Dark-Mode auf jedem Element verifiziert

**Abnahmekriterium:** Visuell konsistent, jedes Element folgt Token-System;
screenshot-Parität Light/Dark.

---

### Phase 4 – Dynamische Akzentfarbe *(~1 Tag)*

**Ziel:** UI passt ihre Akzentfarbe an das aktuell geladene Foto an.

Mechanik (100 % client-side, kein zusätzlicher Request):

```js
function extractAccentFromImage(imgEl) {
  // 1. Draw to 64×36 offscreen canvas (fast, low-res)
  // 2. Get ImageData (~2304 pixels)
  // 3. Simple k-means with k=4 on RGB
  // 4. Pick the most saturated cluster center (avoid pure gray/white)
  // 5. Clamp: ensure contrast ratio ≥ 4.5:1 against --surface-0 for text-on-accent
  // 6. Set CSS vars:
  //      --accent         : <hex>
  //      --accent-soft    : color-mix(...)
  //      --accent-glow    : color-mix(...)
}
```

- [ ] Offscreen-Canvas-Helper (64×36, `drawImage` vom `<img id="previewDelivered">`)
- [ ] K-Means (4 Clusters, 10 Iterationen – trivial auf 2 304 Punkten, < 5 ms)
- [ ] Kontrast-Clamp: wenn Cluster-Farbe zu hell/dunkel, fälle zurück auf Default `#007AFF`
- [ ] Trigger: nach jedem erfolgreichen `updatePhotoStatus()` (also beim Poll, nur wenn `data.exists` true und Bild neu)
- [ ] Smooth Transition: `body { transition: --accent 600ms var(--ease-out-soft) }` (via `@property` registration für `--accent` als `<color>`)
- [ ] Fallback: kein Bild / CORS / Canvas-Error → Default-Akzent bleibt
- [ ] **Check:** Pytest grün; manueller Test: 3 unterschiedliche Photos → 3 sichtbare Akzent-Shifts

**Abnahmekriterium:** Akzentfarbe wandelt sich sanft mit dem Foto; kein Flash,
kein Layout-Shift; Dark Mode respektiert (kontrastgeprüft).

---

### Phase 5 – Micro-Interactions & Polish *(~0.5–1 Tag)*

**Ziel:** Das "Leben" in die UI bringen – subtil, nie übergriffig.

- [ ] **Tab-Switch:** aktiviertes Panel `fadeIn + translateY(8px) → 0` über `--dur-med`
- [ ] **Button Hover:** `transform: translateY(-1px)` + `--shadow-2`; Active: `scale(.98)`
- [ ] **Card Hover:** `--shadow-1 → --shadow-2` (150 ms)
- [ ] **Slider Thumb:** `scale(1.15)` bei `:active`
- [ ] **Gallery Grid Items:** `opacity: 0 → 1, scale(.97) → 1` staggered (30 ms delay/item, max 8 sichtbar)
- [ ] **Toast:** `translateY(16px) → 0` + fade, `--dur-med`
- [ ] **Modal open:** `scale(.95) → 1` + backdrop `opacity 0 → 1`, `--dur-med`
- [ ] **Health-Dot:** pulsierendes Glow (CSS keyframe, 2 s loop, nur bei "degraded")
- [ ] **Scroll-reveal:** Dashboard-Hero-Elements bei initial load: sequentiell `opacity + translateY`,
      50 ms stagger, nur einmal (IntersectionObserver oder einfach CSS animation-delay)
- [ ] **Respect `prefers-reduced-motion`:** alle Animationen auf `duration: 0.01ms` setzen
- [ ] **Check:** Pytest grün; `performance.now()`-Messung: LCP < 500 ms auf i7

**Abnahmekriterium:** Seite "fühlt sich" flüssig und premium; keine Animation > 400 ms;
`prefers-reduced-motion` greift.

---

### Phase 6 – QA, Regression & Release *(~0.5 Tag)*

- [ ] **Vollständiger pytest-Run** (Dockerfile.test): alle 140+ Tests grün
- [ ] **Manueller Smoke** (L3): `docker build -f Dockerfile` → `curl /health`, `curl /`,
      visuell in Chrome + Firefox + Safari (Light + Dark)
- [ ] **Responsive-Test:** 375 px (iPhone), 768 px (iPad), 1440 px (Desktop)
- [ ] **CSP-Verifikation:** keine externen Requests (DevTools → Network → nur `self`)
- [ ] **Darker-Mode-Persistenz:** Reload → Theme bleibt
- [ ] **Dynamische Farbe:** 3 verschiedene Photos laden → 3 verschiedene Akzente;
      "weisses Bild" → Fallback-Akzent
- [ ] **Version-Bump:** `config.yaml` `version: 2.1.0` (minor: neues UI)
- [ ] **Docs:** `README.md` (Add-on) kurz um "UI" erwähnen; `AGENTS.md` §"Code style"
      um neue Design-Token-Regel ergänzen; ASPICE-Report aktualisieren wenn Test-Anzahl sich ändert
- [ ] **Commit:** `feat(ui): redesign to Apple-grade visual language (v2.1.0)`

**Abnahmekriterium (Definition of Done):**
- L0 (pytest) ✅ · L3 (production smoke) ✅ · Visuell abgenommen in Light + Dark + Mobile
- Kein Funktionalitäts-Regression (alle Endpoints, alle Formfelder, alle Polling-Intervalle intakt)

---

## 3 · Risken & Mitigation

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|--------------------|------------|
| Tests brechen durch ID-/Struktur-Changes | Mittel | Alle IDs aus `conftest.py` + `test_*.py` inventarisieren **vor** Phase 2; nur umschließen, nie entfernen |
| `backdrop-filter` performant auf älteren GPUs? | Gering (i7 8700 + integrated Grafikk) | Fallback: `background: var(--surface-1)` ohne Blur, wenn `@supports not (backdrop-filter: blur(1px))` |
| Dynamische Farbe wirkt "schmutzig" auf bestimmten Photos | Mittel | Kontrast-Clamp + Sättigungs-Clamp (min 20 %, max 80 %); bei Graubild → Fallback |
| CSP blockiert Canvas-Operation? | Sehr gering | `img-src 'self' data:` erlaubt bereits; Canvas readback ist same-origin |
| Single-HTML-File wird > 2 000 Zeilen schwer wartbar | Gering | Token-System + klare Sektionskommentare halten es navigierbar; Split erst ab > 3 000 Zeilen in CSS-File |

---

## 4 · Abhängigkeiten / Voraussetzungen

- **Keine** neuen Dependencies (kein npm, kein PostCSS, kein Tailwind) – alles inline CSS + Vanilla JS.
- **Keine** externen Fonts (CSP + Latenz).
- **Keine** Backend-Änderungen erforderlich – die API-Verträge (`/health`, `/api/battery-status`,
  `/preview-status`, `/api/gallery-previews`, `POST /`, `POST /prepare-photo`, `POST /cleanup-previews`)
  bleiben identisch.
- Einzige "neue" Client-Logik: Canvas-basierte Farbboxtraktion (Phase 4).

---

## 5 · File-Touch-Matrix

| Phase | Dateien | Art der Änderung |
|-------|---------|-----------------|
| 1 | `settings.html` – `<style>` Block | Tokens-Definition, Base-Styles |
| 2 | `settings.html` – `<body>` + `<script>` | Neue DOM-Struktur (Tabs), JS für Tab-Switching |
| 3 | `settings.html` – `<style>` Block | Komponent-Styles |
| 4 | `settings.html` – `<script>` Block | Canvas-Extraktion, `@property`-Registrierung |
| 5 | `settings.html` – `<style>` + `<script>` | Animation-Keyframes, micro-interaction-Handlers |
| 6 | `config.yaml` (version), `AGENTS.md`, `README.md`, `docs/test_report_aspice.md` | Meta/Release |

> **Eine einzige Quelle der Wahrheit:** alles lebt weiterhin in `templates/settings.html`.
> Kein neues File, außer optional `static/icons.svg` (wenn Inline-SVGs zu redundant werden –
> erst in Phase 5 entscheiden).

---

## 6 · Zeit- & Aufwands-Schätzung

| Phase | Aufwand (Solo) | Kumulativ |
|-------|:-:|:-:|
| 1 – Tokens | 0.5–1 Tag | 1 Tag |
| 2 – Layout & Tabs | 1–2 Tage | 3 Tage |
| 3 – Komponenten | 1–2 Tage | 5 Tage |
| 4 – Dynamische Farbe | 0.5–1 Tag | 6 Tage |
| 5 – Micro-Interactions | 0.5–1 Tag | 7 Tage |
| 6 – QA & Release | 0.5 Tag | **~7–8 Tage** |

Realistisch: **eine fokussierte Arbeitswoche** (mit Puffer für Dark-Mode-Edge-Cases und
Mobile-Tüftelei).

---

## 7 · Offene Fragen / Follow-ups (optional, nicht blockierend)

- Soll der **Gallery-Tab** später auch einen Lightbox-Viewer mit Vor/Zurück-Pfeilen bekommen?
  (Aktuell: Click → `window.open` in neuem Tab. Könnte in 2. Iteration.)
- **i18n:** Aktuell Englisch. Bei zukünftiger DE-LOkalisierung sollte die UI-Strings
  in ein externes Dictionary ausgelagert werden – bewusst hier *nicht* gemacht.
- **Accessibility:** ARIA-Labels für Tabs (`role="tablist"`, `aria-selected`), `focus-visible` Styles –
  in Phase 3 mit einbauen.

---

*Plan erstellt: 2025-*
*Nächster Schritt: Phase 1 (Token-Definition) – kann sofort losgehen.*
