# Datum: Schalter für den Datumsstempel (v2.4.2)

**Status:** umgesetzt (2.4.2, 2026-11-17) · **Sprache:** Deutsch (Arbeitsdokument)
**Auftrag (Nutzer):** „Nur wenn der Schalter auf enabled steht, soll das Datum gesetzt werden. Bitte einen
Schalter auf der Settings-Seite einbauen, mit dem man das ein- und ausschalten kann. Setze ihn in den
globalen Bereich (unabhängig von Immich, HA, ComfyUI).“

## Entscheidungen

1. **Feldtyp: Select (Enabled / Disabled)** — kein optischer Toggle. Das Settings-Formular ist *ein*
   `<form>`; seit 2.4.1 gilt „ein Feldname pro Config-Key“. Eine Checkbox schickt im Nicht-JS-POST nichts,
   wenn sie aus ist — und die Regel „Feld fehlt = gespeicherter Wert behalten“ (die Legacy-POSTs, Skripte
   und die bestehenden Tests brauchen) würde das Ausschalten ohne JS unmöglich machen. Ein Select schickt
   immer. Ein Toggle *im Toggle-Outfit* (Optik, Wert per JS/Hidden-Field) ist machbar, aber Entscheidung
   beim Nutzer.
2. **Default: enabled** — das Verhalten aller früheren Versionen; bestehende Installationen ändern nichts.
3. **YAML-Key auf Top-Level** (`date_overlay`), nicht in einem Quellen-Abschnitt — darum geht es ja:
   der Schalter gehört zu keiner Quelle. Angezeigt wird er in der Display-Settings-Karte (das ist die
   quellunabhängige Karte).
4. **Semantik:** Der Schalter entscheidet, ob die Pipeline zeichnen *darf*. Ohne EXIF-Datum im Bild wird
   nichts gezeichnet — ComfyUI-Generationen und rawpy-konvertierte RAW/DNG bleiben ohne Stempel, beide
   Stellungen. Seit diesem Pass im Hilfetext des Feldes nachlesbar.
5. **„Feld fehlt = behalten“:** POSTs ohne Feld dürfen den gespeicherten Wert nicht kippen (neuer Test).

## Umsetzung (Code)

- `app.py`: `_env_bool()` (Seed aus der Umgebung; Unlesbares fällt hörbar auf den Default zurück),
  `DEFAULT_CONFIG['date_overlay']`, Modulglobale `date_overlay` + Aktualisierung in
  `update_app_config()` (Hot-Reload-Pfad), `form_bool()` (Feld fehlt → behalten),
  `scale_img_in_memory()` zeichnet nur noch, wenn der Schalter an ist — die Logzeile
  `Date overlay: …` bleibt der Beweis.
- `config.yaml`: Option `date_overlay: true` + Schema `bool?` (Version 2.4.2). `run.sh`:
  `export DATE_OVERLAY=…` (üblicher Seed-Kanal).
- `templates/settings.html`: Select + Hilfetext im Display-Settings-Block (Englisch, weil user-facing).

## Tests & Beweislage

- **L0:** 199 Fälle, 8 Skips (22,1 s). Vier neue Fälle in `TestFR010DateOverlay` — u. a. das
  **An/Aus-Differenzial auf demselben Input**: nur das Differenzial beweist etwas, weil das Testbild ein
  Verlauf ist, der beim Dithern mehrere Palettenfarben bekommt (weiße Pixel im Eck zählen also nicht).
- **L1 (Live-Tier):** 8/8 grün (26,9 s), unverändert.
- **L3, Produktions-Image, echtes Immich-Foto:** ON → Pipeline loggt `Date overlay: <EXIF-Datum des Fotos>`, im
  ausgelieferten Preview sitzt das schwarze Rechteck; OFF → kein Log, kein Stempel. POST ohne Feld behält
  den Wert, `/download`-Contract unverändert. Details im Report (§6.6).

## Harness-Notizen (für künftige Standalone-Smoke-Läufe)

- **Build-Kontext:** `Dockerfile` kopiert das ganze Add-on-Verzeichnis — ein lokales `config/` und
  `photos/` werden ins Image **eingebrannt**, wenn sie im Build-Kontext liegen (in HA verdeckt der
  Bind-Mount sie).
- **Standalone-Start:** `/init` (s6) muss PID 1 bleiben, gunicorn durch das **echte** `with-contenv`
  starten (`/package/admin/s6-overlay-*/command/with-contenv` — der `/usr/bin/with-contenv`-Symlink im
  Base-Image ist dangling). Wer `--entrypoint bash` überschreibt, verliert die Container-Umgebung, und
  die App startet still mit leerer URL/leerem Secret. Git-Bash mangelt Argumente mit führendem `/` →
  `MSYS_NO_PATHCONV=1`.
- **`--env-file`** will strikte `KEY=VALUE`-Zeilen: CRLF in der `.env` wandert als CR in den Wert; der
  Shell-`source` des L1-Harness streicht ihn.
- **Provider-Zyklus:** beide Ordnungen (`random`, `newest`) überspringen bereits gezeigte Fotos (Tracking) —
  `newest` pinnt ein Foto also **nicht** über mehrere Läufe. Die Pixel-Differenz *zwischen* Läufen ist
  deshalb nur ein Indiz; die Logzeile ist der Beweis.

## Offen

- Optischer Toggle für alle Ja/Nein-Felder (Entscheidung beim Nutzer).
- FR-010 für EXIF-lose Quellen erweitern: (a) Datei-MTime als Fallback, (b) ComfyUI-Metadaten
  (Prompt/Seed/Erstellzeit), (c) sichtbare Option — Entscheidung steht aus.
