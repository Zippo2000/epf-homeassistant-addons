# Bild-Zoom im Lightbox – „Klick zoomt statt neuem Tab“

> **Status:** ✅ **CLOSED** — umgesetzt in **2.5.0** (Code `a7ab467`, Doku `e44e57a` + `bcb66fe`,
> Getaggt `v2.5.0`). Guard-Test ✅, **L0 ✅ 206+8** (Lauf 2026-11-22, 28,5 s), **L1 ✅ 8/8** (27,2 s),
> **L3 ✅** (Produktions-Image: `/health`, `/sleep`, `/download` unverändert, Seite liefert Ein `#lightbox`,
> drei Dashboard-Handler, kein `target="_blank"` — Report §6.10).
> **Browser-Optik steht aus:** FLIP-Timing, Crossfade, `Esc`/Pfeile, Layout unter 768 px — wie bei allen
> UI-Themen manuell (TESTSPEC §3).
> **Betreff:** `epf-eink-addon/templates/settings.html` (CSS + Markup + JS; Backend unverändert)
> **Ziel:** Ein Klick auf ein Bild — **Dashboard und Galerie** — zoomt es schön im Fenster hoch, statt
> einen Browser-Tab zu öffnen.

---

## 1 · Anfrage

Der Nutzer wollte die Galerie und die drei Dashboard-Previews **per Mausklick vergrößern**, „mit einer
schönen Animation“, und ausdrücklich **nicht** in einem neuen Fenster. Vorher: Galerie ankern auf dem
Original mit `target="_blank"` (Browser-Tab), Dashboard ohne Klick-Funktion.

## 2 · Entscheidungen

| Aspekt | Entscheidung |
|--------|-------------|
| Animation | **FLIP**: Bild in Zielgröße rendern, per Transform auf das geklickte Thumbnail zurückziehen, dann auslösen — nur das **Öffnen** ist FLIP |
| Navigation im Overlay | **Crossfade** (kein zweiter FLIP), Pfeile nur bei Gruppe > 1 |
| Gruppen | Dashboard: die drei Previews (`LIGHTBOX_DASHBOARD_IMAGES`); Galerie: die gerenderten Shots |
| Tastatur | `←`/`→`blättern die Gruppe, `Esc` schließt — Lightbox **zuerst**, danach das Confirm-Modal |
| ohne JavaScript | Galerie-`href` bleibt stehen (kein-JS-Fallback → neuer Tab); der JS-Handler ruft `preventDefault()` |
| Design | Bestehende Tokens: `--dur-*`, `--ease-out-soft`, Glas/Overlay; `prefers-reduced-motion`; Responsive unter 768 px |
| Formular | Overlay-Markup bleibt **außerhalb** von `#settingsForm` (Guard „ein Feldname pro Konfigurationsschlüssel“, 2.4.1) |
| CSP / Konstanten | Inline-CSS/JS im einen Self-Contained-Template, keine externen Downloads; `POLL_INTERVALS` und `NOTIFICATION_DURATION` unangetastet |
| Dauer | `LIGHTBOX_DURATION = 400` ms als benannter Wert (Stil wie die bestehenden Konstanten) |

## 3 · Umsetzung (settings.html)

- **CSS:** `.lightbox` (Zielgrößen), Backdrop-Blur, Caption,/close-/prev-/next-Buttons, Keyframes
  `lightboxBackdropIn`, `lightboxCaptionIn`, `lightboxSwap`; Reduced-Motion- und Mobile-Regeln.
- **Markup:** ein `#lightbox`-Overlay, geteilt von beiden Flächen, **außerhalb** des Formulars.
- **JS:** `openLightbox()`, `lightboxClick()`, `showLightboxItem()`, `lightboxNav()`, `closeLightbox()`,
  `lightboxBackdropClick()`, `lightboxGroup()`, `escapeAttr()`, `restartAnimation()`,
  `lightboxReducedMotion()`.
- **Dashboard:** `onclick="openLightbox('dashboard', this)"` an `previewDelivered` / `previewOriginal` /
  `previewProcessed`, `cursor: zoom-in`.
- **Galerie:** `data-caption` + `onclick="lightboxClick(event, 'gallery', this)"`, `href` bleibt als
  Fallback, `cursor: zoom-in`.

## 4 · Verifikation

- **Guard-Test:** `tests/test_functional.py::TestFR026UISettingsImprovements::test_image_click_zooms_in_page_lightbox`
  — Overlay vorhanden, beide Gruppen verdrahtet, kein `target="_blank"` im Render. Er ist der 9. Fall von
  **TC-FR-026** (Anforderung **FR-026**, neuer Klauselzähler **8**); deshalb L0 **206 + 8 = 214**, Funktionsteil **101**.
- **L1:** unverändert grün — die Seite wird nur ausgeliefert, am Backend ist nichts geändert.
- **L3:** Produktions-Image durch die echte `with-contenv`-Startzeile: `GET /health` (verbindet sich mit Immich), `GET /sleep`,
  `GET /download` (`frame.txt`, 2-Hex-Tokens, kein schließendes `};`), und die **ausgelieferte** Seite enthält
  das Overlay — damit ist auch der Jinja-Pfad bedient, den der Guard-Test nicht sieht.
- **Manuell offen:** Animation, Crossfade, Tastatur, Mobile-Layout (siehe Statuszeile).

## 5 · Nebenbefund aus dem Lauf

Die drei **Speichern**-Fälle der Settings-Seite hatten ihre Guards schon (duplizierte Feldnamen, 2.4.1),
aber nicht für das, was der Nutzer 2.4.3b melden wollte: ein **geleertes** Feld überschreibt den gespeicherten
Wert (bestätigen ab jetzt), und ein Workflow-Slot **mit Inhalt aber ohne Namen** wurde still verworfen
(lehnt jetzt ab). Beide Fälle sind benannt im Funktionsteil.
