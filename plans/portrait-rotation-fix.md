# Bugfix: Portrait-Vorschau – Rotationsrichtung

> **Status:** 🔶 2.6.6 + 2.6.7 implementiert (Realtests grün). Offen: User muss in der UI **Display → Rotation = 0°** setzen (gespeicherter Legacy-Wert 270° drehte das Bild), danach ein Frame-Foto zur Abnahme.
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

### Schlussfolgerung (vorläufig)
Da `1fcc2b4` nun `rotate(-90deg)` verwendet, sollte ein neuer Dashboard-Screenshot unter 2.6.4/2.6.5 das aufrechte Bild zeigen — konsistent mit dem echten Frame.

---

## Update nach 2.6.5: Screenshots vom 28.11. 10:10

### `ui-shots/Screenshot 2026-11-28 101040.png` — Dashboard (Portrait)
- Das zentrale Original-Thumbnail zeigt einen Fuchs **aufrecht**.
- `Current photo` und `Next photo — processed` zeigen denselben Fuchs **um 90° im Uhrzeigersinn gedreht** (liegt auf der Seite).
- Der Footer zeigt `v2.6.5` — der Fehler ist also **nicht durch `rotate(-90deg)` behoben**.

### `ui-shots/Screenshot 2026-11-28 101119.png` — Echtes Frame-Foto (Portrait)
- Der Fuchs liegt auf dem Display **ebenfalls um 90° im Uhrzeigersinn gedreht**.
- Dashboard und reales Frame sind weiterhin konsistent, aber beide zeigen das falsche Ergebnis.

### Neue Erkenntnis
Das Quellbild ist selbst **hochformatig**. Die Portrait-Orientierung des Frames sollte ein hochformatiges Bild **nicht zusätzlich um 90° drehen** — es müsste aufrecht bleiben. Die bisherige Annahme (`portrait = +90° Pipeline-Drehung`) ist für hochformatige Quellen falsch.

### Entscheidung
Gewählt wird **Option 2** in verfeinerter Form: Die Pipeline prüft Quellbild-Orientierung und Frame-Orientierung. Es wird nur gedreht, wenn beide nicht zusammenpassen (und das Bild nicht quadratisch ist). Die Ausgabe nimmt die physische Orientierung des Frames an (800×480 vs. 480×800). Damit bleibt das Bild so weit wie möglich erhalten und es wird nur so viel abgeschnitten wie nötig.

---

## Requirements (Neufassung)

**REQ-1: Physische Orientierung als Einstellung**
Der Benutzer kann in den Settings einstellen, ob der Frame physisch im Hochformat (`portrait`) oder Querformat (`landscape`) hängt. Der Wert ist ein globaler Top-Level-Key `frame_orientation` im Runtime-YAML und wird aus der Add-on-Option `FRAME_ORIENTATION` geseedet.

**REQ-2: Fixe Auflösung, orientierungsabhängiges Seitenverhältnis**
Die Panel-Auflösung bleibt 800×480 Pixel. Je nach `frame_orientation` liefert die Pipeline:
- `landscape`: ein 800×480 Bild,
- `portrait`: ein 480×800 Bild.
Das Bild füllt das Panel vollständig aus.

**REQ-3: Automatische Drehung nur bei Orientierungskonflikt**
Das Quellbild wird nach EXIF-Auto-Transpose betrachtet. Eine zusätzliche 90°-Drehung wird nur dann angewendet, wenn:
- das Seitenverhältnis des Quellbilds nicht annähernd 1:1 ist, UND
- die Orientierung des Quellbilds nicht zur physischen Frame-Orientierung passt.
Bei Übereinstimmung oder quadratischem Quellbild findet keine zusätzliche Drehung statt.

**REQ-4: Drehrichtung und manuelle Feinjustierung**
Die automatische Drehung wird als +90° auf die gespeicherte `rotation_angle` addiert (PIL-Semantik: 90° gegen den Uhrzeigersinn). Der Benutzer kann weiterhin über `rotation_angle` (0/90/180/270) feinjustieren.

**REQ-5: Minimale Beschneidung**
Nach der eventuellen Drehung wird das Bild mit dem konfigurierten `display_mode` (`fit` oder `fill`) auf die Zielabmessungen skaliert. `fill` beschneidet so wenig wie möglich, um das Zielformat vollständig zu füllen; `fit` zeigt das gesamte Bild mit Letterbox-Balken an.

**REQ-6: Web-Vorschau zeigt physische Wandansicht**
Dashboard- und Galerie-Vorschauen für `processed`/`delivered` verwenden ein Vorschaufenster, dessen Seitenverhältnis der physischen Orientierung entspricht (3:5 für Portrait, 5:3 für Landscape). Es findet keine CSS-Drehung statt; das ausgelieferte Bild wird direkt angezeigt.

**REQ-7: Lightbox zeigt das rohe Frame-Bild**
Die Lightbox zeigt das verarbeitete Bild in seinen tatsächlichen Abmessungen (480×800 oder 800×480), ohne zusätzliche CSS-Drehung.

**REQ-8: Rückwärtskompatibilität**
Die Einstellung `rotation_angle` bleibt erhalten und addiert sich zur automatischen Drehung. `frame_orientation` kann fehlen; der Default ist `landscape`.

---

## Plan

1. **Cython-Modul (`cpy.pyx`)**
   - [x] `load_scaled` akzeptiert `target_width`/`target_height` (Default 800/480).
   - [x] `convert_image` und `convert_image_atkinson` verwenden die Dimensionen des Eingabebilds statt hartcodierter Konstanten.

2. **Backend (`app.py`)**
   - [x] `_target_dimensions(frame_orientation)` → (800,480) oder (480,800).
   - [x] `_source_orientation(width, height)` klassifiziert Quellbild nach EXIF.
   - [x] `_needs_auto_rotation(...)` entscheidet, ob +90° nötig sind.
   - [x] `scale_img_in_memory` wendet Zielabmessungen und automatische Drehung an.
   - [x] Default `frame_orientation` zurück auf `landscape`.

3. **Frontend (`templates/settings.html`)**
   - [x] CSS-`transform: rotate(...)` für Portrait entfernt.
   - [x] Portrait-Boxen behalten `aspect-ratio: 3/5`, Landscape `5/3`.
   - [x] Galerie `.is-wall` analog ohne Rotation.

4. **Tests**
   - [x] TC-FR-034 auf neue Semantik angepasst (Default `landscape`).
   - [x] Neue Fälle mit Marker-Bild: Portrait/Portrait, Landscape/Landscape, Mismatch-Quer/Hoch, quadratische Quelle, additive `rotation_angle`.

5. **Doku & Version**
   - [x] `CHANGELOG.md` Eintrag für 2.6.6.
   - [x] `config.yaml`: Version 2.6.6.
   - [x] Plan aktualisiert.

6. **Build & Push**
   - [ ] Docker-Testimage bauen und pytest laufen lassen.
   - [ ] Commit & Push.
   - [ ] Visuelle Abnahme am echten Frame durch User.

---

## Offene Fragen

1. **Sitzt die Drehrichtung am echten Frame?** → Die Pipeline dreht mismatched Quellen um 90° gegen den Uhrzeigersinn (PIL). Falls das Frame-Foto weiterhin verdreht ist, kann der Nutzer das über `rotation_angle` korrigieren; alternativ drehen wir den Auto-Betrag auf 270°. **User-Foto erforderlich.**
2. **Unterstützt die ESP32-Firmware 480×800?** → Der Code liefert jetzt 480×800 im Portrait-Modus. Falls die Firmware hart auf 800×480 pro Zeile ausgelegt ist, müssen wir entweder im Server wieder auf 800×480 ausgeben oder die Firmware anpassen. **Feldtest erforderlich.**
3. **Galerie:** CSS ohne Rotation umgestellt; visuell noch nicht am Frame geprüft.

---

## Realtests (28.11.2026, nach 2.6.6-Build)

1. **Echt-Immich-Replikation** (Album `eink`, Server 192.168.177.42): echte Quellbilder geholt und durch das echte Cython-Modul `load_scaled` gejagt:
   - Fuchs-Portrait 864×1184, `rotation=0` → **aufrecht** 480×800 ✓
   - derselbe Fuchs, `rotation=270` → **seitlich** (Kopf zeigt rechts) – exakt die Pose aus dem User-Screenshot `152906.png` ✓
2. **Echter End-to-End-Test** (echte `app.py` + echtes Immich + `frame_orientation: portrait`, `rotation: 0`): `POST /prepare-photo` → `latest_processed.jpg` 480×800 **aufrecht** mit Datumsstempel ✓
3. **L0-Suite:** 334 passed, 8 skipped (L1) ✓

**Schlussfolgerung:** Die Pipeline ist korrekt. Der seitliche Homer im Screenshot kommt aus dem **gespeicherten** `rotation_angle=270` (Legacy-Default aus dem Manifest; wurde in 2.6.4/2.6.5 vom Portrait-`+90` zu 360°=0 ausgeglichen, ist jetzt aber wirksam). Fix 2.6.7: Manifest-/Env-/UI-Reset-Default auf **0°**; bestehende Installationen müssen Rotation einmalig in der UI auf 0° setzen (gespeicherte Werte überschreibt kein Save ohne Feld).

---

## Wie man weitermacht

> **Wichtig:** Nach dem Update auf **2.6.6** muss ein **neuer** Dashboard-Screenshot im Portrait-Modus erstellt und mit dem echten Frame-Foto verglichen werden.

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
```

### Vergleichs-Material (lokal, git-ignored)
- `ui-shots/frame_photo.jpg` – echtes Foto des Frames (portrait, Referenz für aufrechtes Bild)
- `ui-shots/Screenshot 2026-11-28 093657.png` – Dashboard (Landscape, korrekt)
- `ui-shots/Screenshot 2026-11-28 094329.png` – Dashboard (Portrait, **falsch**, Zustand vor `1fcc2b4`)
- `ui-shots/Screenshot 2026-11-28 094406.png` – Foto des physischen Frames (Portrait, **Zielvorgabe**, Landschaftsmotiv)
- `ui-shots/Screenshot 2026-11-28 101040.png` – Dashboard (Portrait, **falsch**, Fuchs-Hochformatmotiv unter 2.6.5)
- `ui-shots/Screenshot 2026-11-28 101119.png` – Foto des physischen Frames (Portrait, **falsch**, Fuchs-Hochformatmotiv unter 2.6.5)

### CSS-Stand (2.6.6)
```css
body[data-orientation="portrait"] .preview-img-container.portrait-box { aspect-ratio: 3/5; }
body[data-orientation="portrait"] .preview-img-container.portrait-box img {
    width: 100%; height: 100%; object-fit: contain;
}
body[data-orientation="portrait"] .gallery-item a.is-wall { aspect-ratio: 3/5; }
body[data-orientation="portrait"] .gallery-item a.is-wall img {
    width: 100%; height: 100%; object-fit: cover; aspect-ratio: 3/5; transform: none;
}
body[data-orientation="portrait"] .gallery-item:hover a.is-wall img { transform: scale(1.03); }
```

### Versionsstand
- `config.yaml`: `version: "2.6.7"`
- `CHANGELOG.md`: Einträge 2.6.0 → 2.6.7
- Latest commit: TBD
