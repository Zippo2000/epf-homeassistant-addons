# Plan: Rahmen-Orientierung (Quer/Hoch) — FR-034

> **Status:** ✅ **CLOSED** — **2.6.0** (UI-Umbau + Feature in einem Pass, Template-Rewrite `templates/settings.html`). Abgenommen: L0 212/212 + L1 8/8 (2026-11-27), reale Immich-Ende-zu-Ende (prepare → download → Orientation-Round-Trip, 400-Guard), Browser-Optik vom User abgenommen (2026-11-27). Tag `v2.6.0` auf 06fb965.
> **Auftrag (Nutzer, 2026-11-27):** „Es soll in der Konfiguration eingestellt werden können, ob der Bilderrahmen im Querformat oder im Hochformat aufgehängt ist. Danach sollen sich auch die Bilder im Webinterface orientieren und angezeigt werden."

---

## 1. Auftrag & Kontext

Der Rahmen ist mechanisch quer (Hardware-nativ: das Panel zeigt 800×480) oder hoch auf der
Wand. Bisher konnte nur die freie `rotation` (0/90/180/270) die Ausrichtung ändern — semantisch
unübersichtlich: „Um 90° drehen" sagt nichts über die *Aufhängung* des Rahmens. Die neue
Einstellung benennt, **wie der Rahmen hängt**, und wirkt auf zwei Ebenen:

1. **Pipeline:** Hochformat ⇒ das an den ESP32 ausgelieferte Frame-Inhalt wird um 90° relativ
   zur gespeicherten `rotation` gedreht, damit das Bild an der Wand aufrecht steht.
2. **Web-UI:** Die Vorschauen zeigen sich in der *Wall-Orientierung* — was an der Wand zu sehen
   ist, ist auch das, was die Seite zeigt.

## 2. Design-Entscheidungen

| # | Entscheidung | Begründung |
|---|--------------|------------|
| D1 | **Global** (quellunabhängig), wie `date_overlay` (2.4.2): Top-Level-Key `frame_orientation` im Runtime-YAML, Add-on-Option `frame_orientation` (Schema `list(landscape\|portrait)`, Default `landscape`) nur als **Seed** beim ersten Start (env `FRAME_ORIENTATION`) | Konvention 2.3.2/2.4.2: ein Feldname = der Optionename; globale Einstellungen leben auf Top-Level; Secrets/Quellen bleiben getrennt |
| D2 | **Additiv zur `rotation`** (`effektiv = (rotation + (90 wenn Hoch)) mod 360`), kein Ersetzen | Die Rotation bleibt der Fein-Steller (z. B. 90 vs. 270 je nach Wandseite); Orientierung ist die Semantik. `load_scaled` (Cython) wird nicht angefasst — der Effekt entsteht in `scale_img_in_memory`, wo die Rotation bereits gelesen wird |
| D3 | **Web-Drehung nur für `processed`/`delivered`** Vorschauen (Dashboard: Current + Processed; Galerie: `kind=processed|delivered`); `original` bleibt ungedreht | Original = Quellbild (so wie es aufgenommen/generiert wurde); nur das Frame-Format (800×480) ist die Wand-Sicht. CSS: `body[data-orientation="portrait"]` dreht das Bild 90° in einem 3:5-Box (Breite 277,78 % = (800/480)·(5/3)), kein Crock, kein Letterbox |
| D4 | **Lightbox zeigt das rohe Frame** (800×480, ungefiltert) — auch im Hochformat | Der FLIP-Zoom (2.5.0, getestet) rechnet mit achsenparallelen Rechtecken; eine Rotation des Lightbox-Bilds würde die Transform-Chain mit `img.style.transform` kollidieren. Die Caption sagt bereits, was gezeigt wird („processed for the e-ink frame") |
| D5 | Invalid-Values ⇒ **400** (wie `rotation`) | Konvention der POST-/Validierung |
| D6 | Ein POST **ohne** `frame_orientation`-Feld behält den gespeicherten Wert (Regel „fehlendes Feld = gespeicherter Wert", 2.4.2/2.4.3b) | Das Select sendet immer; Legacy-POSTs dürfen die Einstellung nicht flippen |

## 3. Umfängen (2.6.0 bündelt Feature + UI-Umbau)

Das Feature und der UI-Umbau (§4) ändern dieselbe Datei — ein Version-Zug deckt beides.

**Backend:**
- `app.py`: `DEFAULT_CONFIG['frame_orientation']` (env-Seed), Modul-Global `frame_orientation`,
  `update_app_config` liest den Top-Level-Key (inkl. Startup-Log), POST-Handler persistiert +
  validiert (400), `scale_img_in_memory` wendet den 90°-Offset an.
- `run.sh`: `export FRAME_ORIENTATION=$(bashio::config 'frame_orientation' 'landscape')` + Log.
- `config.yaml` (Manifest): Option + Schema; Version 2.5.0 → 2.6.0.

**UI (`templates/settings.html`, vgl. §4):**
- `Display`-Sektion: Select **Frame Orientation** (Landscape/Portrait) mit Erklärung beider
  Effekte; `body[data-orientation="…"]`-Attribut aus dem gespeicherten Wert (Jinja).
- CSS: Portrait-Boxen für `processed`/`delivered`-Vorschauen (Dashboard + Galerie);
  Galerie-Renderer markiert diese mit `.is-wall` (D3).

**Tests (TC-FR-034, 6 Fälle):** Rendering des Selects (Landscape-Default), Portrait-Persistenz
(Top-Level-Key im YAML), Feld-fehlt ⇒ Wert bleibt, Invalid ⇒ 400, Pipeline-Drehung
(Asymmetrie-Bild: Quadranten-Korrespondenz Landscape vs. Portrait) + Web-Marker
(`data-orientation="portrait"` im gerenderten HTML).

## 4. UI-Umbau (2.6.0) — Referenz: dunkel-blauer Dashboard-Look mit Left-Sidebar

**Vorher:** Apple-Style Light (Dark als Alternative), Header mit Tab-Leiste
(Dashboard/Configuration/Gallery), Karten-Kaskade in einem Tab.
**Nachher:**

- **Dunkel-Navy als Primärlauch** (Referenz-Palette `#060a1e`/`#0d1330`/`#151d44`, Text
  `#e8eaf6`/`#9aa3c7`), Light-Theme bleibt als Alternative (Theme-Toggle + `localStorage` wie
  bisher).
- **Left-Sidebar** (sticky): Logo, Navigation **Dashboard · Image Source · Display · Schedule ·
  Gallery**, unten **Save / Reset** + Version. <768 px: Sidebar wird Sticky-Topbar mit
  horizontaler Navigation, Save/Reset wird Bottom-Bar.
- **Status-Strip** über der aktiven Ansicht: Health-Pill (Quelle online/unreachable),
  Battery-Pill, Generation-Status (ComfyUI) — einheitlich in jeder Ansicht.
- **Einheitliche Karten** (eine Optik für alle Sektionen), Kanal-Badges
  (`runtime YAML` / `HA option`) bleiben; **ein Feldname pro Config-Key** bleibt (2.4.1);
  Bestätigungs-Modals (Reset + Clear-Empty, 2.4.3b) bleiben; **Lightbox** (2.5.0) bleibt,
  Markup bleibt **außerhalb** `#settingsForm`; CSP/Referrer-Metas, `POLL_INTERVALS`,
  `NOTIFICATION_DURATION`, `safeGet`, Theme-Persistenz bleiben.
- Form-Spanne: `<form id="settingsForm">` umschließt die vier Konfig-Arsichten (Source,
  Display, Schedule, Gallery inkl. Archiv-Optionen); Dashboard liegt außerhalb. Save/Reset im
  Sidebar-Block triggern `handleSubmit`/`showResetConfirmation` (kein zweites Form).

**Nicht verändert (bewusst):** alle Form-Feldnamen/IDs, Endpoints, Jinja-Context
(`config`, `runtime_status`, `battery_*`, `addon_version`, `build_timestamp`, `max_workflows`),
die JS-Funktionsnamen und -Verträge (Tests referenzieren sie), Footer
(`v{{ addon_version }} | Built: {{ build_timestamp }}`).

## 5. Abnahme / DoD

- [x] L0 Suite grün (Dockerfile.test) — Zählung: funktional 101 → **107**, offline 206 → **212**,
      kombiniert 214 → **220** (100 %).
- [x] L3-Produktions-Smoke: `/health`, `/` rendert, POST round-trip (2.6.0-Image).
- [ ] L1 (Live Immich/ComfyUI) + Browser-Optik-Abnahme (Chrome/Firefox/Safari, Light+Dark,
      375/768/1440 px) — steht als Feld-Punkt offen (wie die früheren UI-Pässe, s.
      `ui-modernisierung.md` §6).
- [x] Doku: FR-034 + TC-FR-034 im ASPICE-Trio, Report re-baselined, README/ARCHITECTURE/AGENTS
      abgeglichen.
