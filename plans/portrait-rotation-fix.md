# Bugfix: Portrait-Vorschau – Rotationsrichtung

> **Status:** 🔶 IN ARBEIT – Fix in `1fcc2b4`, Version wird auf **2.6.5** hochgezählt (HA braucht eine neue Manifest-Version, sonst wird kein Update angeboten). Die letzten Screenshots bestätigen das Problem und das Ziel; die endgültige Abnahme auf einem laufenden 2.6.5-Container steht noch aus.
> **Hindernis:** Aktuelles Modell (`club3090-active`) hat keine Vision – Screenshots müssen analysiert werden.

---

## Problem

Im Webinterface (Settings → Dashboard, Portrait-Modus) erscheinen die
`processed`/`delivered`-Vorschau und die Galerie-`.is-wall`-Items **in der falschen
Rotationsrichtung**. Das Bild liegt seitlich, statt aufrecht (wie an der Wand).

### Reproduktion
- Frame hängt **portrait** an der Wand
- Settings: `frame_orientation = portrait`
- Dashboard → "NEXT / PROCESSED" und "CURRENT / DELIVERED" zeigen das Bild seitlich
- Galerie → `PROCESSED`-Items ebenfalls seitlich

### Erwartetes Verhalten
Das Bild soll **aufrecht** erscheinen – exakt wie der Betrachter es an der Wand sieht
(vgl. `ui-shots/IMG_8996.heic` / `frame_photo.jpg`: Gebäude mit Dach oben, Bäume nach oben).

---

## Analyse

Die Pipeline (Cython) rotiert das Quellbild **90° CW** für den Portrait-Mode
(`app.py` line 506: `rotation = (rotation_angle + 90) % 360`).
Das 800×480-Datei-Ergebnis enthält den Inhalt bereits für die portrait-hängende Wand
vorrotiert.

**Physikalisch:** Das Panel wird 90° **CW** gedreht (hängt portrait).
Die Firmware rotiert den Content **CW** vor dem Schreiben.
**Netto-Effekt für den Betrachter:** Das Bild erscheint aufrecht.

**CSS-Simulation:** Um im Browser dieselbe Sicht zu erzeugen, muss die 800×480-Datei
im Browser **90° CCW** (`rotate(-90deg)`) gedreht werden – NACH dem CW der Firmware
„rückdrehen" = CCW im Browser.

**Bug:** Der Code hatte `rotate(90deg)` (CW) → doppelt CW → Bild liegt 180° falsch.
**Fix:** `rotate(-90deg)` (CCW).

---

## Geleistete Fixes (Commit-Reihenfolge)

| Commit | Was |
|--------|-----|
| `cda964e` | Portrait-Default + `object-fit: cover` Crop (falscher Ansatz) |
| `21d7b39` | Revert auf `rotate(90deg)` (CW) – nach User-Analyse des Frame-Fotos |
| `1fcc2b4` | **Korrekte Richtung: `rotate(-90deg)` (CCW)** |

---

## Betrachtung der Screenshots vom 28.11.2026

Die beiden jüngsten Screenshots liefern die nötige visuelle Rückmeldung:

### `ui-shots/Screenshot 2026-11-28 094329.png` — Dashboard (Portrait)
- Die beiden rahmenförmigen Vorschauboxen („Current photo“ und „Next photo — processed“) zeigen das Bild **um 90° im Uhrzeigersinn gedreht** (Dach/Häuser liegen auf der Seite).
- Das zentrale Original-Thumbnail zeigt die **korrekte, aufrechte Quelle**.
- Das belegt den Zustand **vor** `1fcc2b4`: der CSS-Code enthielt noch `rotate(90deg)`, d.h. die Vorschau war nicht das, was der Betrachter an der Wand sieht.

### `ui-shots/Screenshot 2026-11-28 094406.png` — Echtes Frame-Foto (Portrait)
- Dieser Screenshot ist **kein Galerie-Screenshot**, sondern ein Foto des physischen E-Paper-Frames.
- Das Bild erscheint **aufrecht** (Dach/Haus oben, Bäume seitlich).
- Das bestätigt: Pipeline + Firmware erzeugen bereits das korrekte Wand-Ergebnis; die Web-Vorschau muss nur noch dieselbe Orientierung darstellen.

### Schlussfolgerung
Da `1fcc2b4` nun `rotate(-90deg)` verwendet, sollte ein neuer Dashboard-Screenshot unter 2.6.4 ebenfalls das aufrechte Bild zeigen — konsistent mit dem echten Frame.

---

## Offene Fragen

1. **Sitzt die Rotation jetzt?** → Teilweise beantwortet: Das echte Frame-Foto (094406) zeigt ein aufrechtes Bild, also ist das Hardware/Pipeline-Ergebnis korrekt. Der Dashboard-Screenshot 094329 stammt noch vom Zustand vor `1fcc2b4` (`rotate(90deg)`). **Noch offen:** Neuer Dashboard-Screenshot auf einem laufenden 2.6.4-Container, um zu prüfen, ob `rotate(-90deg)` das Frame-Foto exakt abbildet.
2. **Galerie:** `.is-wall`-Items verwenden dieselbe CSS-Regel (`rotate(-90deg)`). Theoretisch konsistent; visuell noch nicht dokumentiert.
3. **Landscape-Modus** bleibt unangetastet (5:3 Box, keine Rotation) – weiterhin korrekt.

---

## Wie man weitermacht

> **Wichtig:** Der Screenshot `094329.png` zeigt noch den Zustand vor `1fcc2b4` (`rotate(90deg)`). Nach dem Neustart mit der neuen Version **2.6.5** muss ein **neuer** Dashboard-Screenshot im Portrait-Modus erstellt und mit `094406.png` (echtes Frame) verglichen werden.

```bash
# Container mit neuestem Code starten:
cd epf-eink-addon
docker stop epf-ui 2>/dev/null; docker rm epf-ui 2>/dev/null
docker build -f Dockerfile.test -t epf-eink-tests:fix .
docker run -d --name epf-ui -p 5000:5000 --env-file .env epf-eink-tests:fix \
    bash -c "cd /app && python3 app.py"

# Photo vorbereiten (echte Immich):
curl -s -X POST http://localhost:5000/prepare-photo

# Browser: http://localhost:5000
# Oder: Playwright-Screenshot:
cd ../ui-shots && node -e "
const { chromium } = require('playwright');
(async () => {
    const b = await chromium.launch({ headless: true });
    const p = await b.newPage({ viewport: { width: 1440, height: 900 } });
    await p.goto('http://localhost:5000/', { waitUntil: 'networkidle' });
    await p.waitForTimeout(2500);
    await p.screenshot({ path: 'verify-portrait.png' });
    console.log('✓ verify-portrait.png');
    await b.close();
})().catch(e => { console.error(e); process.exit(1); });
"
```

### Vergleichs-Material (lokal, git-ignored)
- `ui-shots/frame_photo.jpg` – echtes Foto des Frames (portrait, Referenz für aufrechtes Bild)
- `ui-shots/Screenshot 2026-11-28 093657.png` – Dashboard (Landscape, korrekt)
- `ui-shots/Screenshot 2026-11-28 094329.png` – Dashboard (Portrait, **falsch**, Zustand vor `1fcc2b4`)
- `ui-shots/Screenshot 2026-11-28 094406.png` – Foto des physischen Frames (Portrait, **Zielvorgabe**)

### CSS-Stand (Commit `1fcc2b4`)
```css
/* Portrait: 800×480 → rotate(-90deg) in 3:5 Box */
body[data-orientation="portrait"] .preview-img-container.portrait-box {
    aspect-ratio: 3/5; position: relative; overflow: hidden;
}
body[data-orientation="portrait"] .preview-img-container.portrait-box img {
    position: absolute; top: 50%; left: 50%;
    width: 166.67%; height: auto;
    transform: translate(-50%, -50%) rotate(-90deg);
}
/* Galerie: gleicher Effekt für .is-wall */
body[data-orientation="portrait"] .gallery-item a.is-wall img {
    position: absolute; top: 50%; left: 50%;
    width: 166.67%; height: auto;
    transform: translate(-50%, -50%) rotate(-90deg);
}
```

### Versionsstand
- `config.yaml`: `version: "2.6.5"`
- `CHANGELOG.md`: Einträge 2.6.0 → 2.6.5
- Latest commit: `1fcc2b4` (plus Version-Bump zu 2.6.5)
