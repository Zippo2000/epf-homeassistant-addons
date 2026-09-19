# Preview-Galerie mit Historie – „Archiv- statt Single-Slot"

> **Status:** Plan / nicht begonnen
> **Betreff:** `epf-eink-addon/app.py` (Prepare/Deliver-Pipeline, `cleanup_old_previews()`,
> `/api/gallery-previews`) + `epf-eink-addon/templates/settings.html` (Gallery-Tab)
> **Ziel:** Die Preview-Galerie soll eine echte **Geschichte** ansammeln (z. B. die letzten 50
> Bilder über 7 Tage) statt nur den *aktuellen* Einzelstand — **ohne** das bestehende
> Prepare→Deliver-Protokoll / den ESP32-Handshake anzufassen.

---

## 0 · Zusammenfassung der Entscheidungen

| Aspekt | Entscheidung |
|--------|-------------|
| Ansatz | **Additives Archiv** daneben: Der *Live-Slot* (`latest.bmp` / `latest.status` / `latest_{original,processed,delivered}.jpg`) bleibt **komplett wie heute** (fixe Namen) — ESP32 + `/download`-Handshake berühren wir **nicht**. Zusätzlich kopiert jede `Prepare`/`Deliver` die Previews in ein **Archiv-Verzeichnis** mit **korrelationsbezogenen Namen**. |
| Korrelationsschlüssel | **`source_id`** der Quelle (Immich-Asset-ID / ComfyUI-ID) — wird bereits von `provider.fetch_image()` geliefert und von `/prepare-photo` zurückgegeben. Fallback: Zeitstempel + kurzer `uuid4`-Suffix. |
| Archiv-Layout | Unter-Ordner `photos/gallery/` mit `original_<id>.jpg`, `processed_<id>.jpg`, (optional) `delivered_<id>.jpg`. Ein `id` = ein „Schuss" = ein Paar Original+Processed. |
| Galerie-Reader | `/api/gallery-previews` listet `gallery/*_*.jpg`, gruppiert per UI nach `id` (Paare), sortiert absteigend, begrenzt auf die Konfig. |
| Aufräumen | **Existierende** `cleanup_old_previews()` wiederverwenden, nur `target_dir = gallery/` + Archiv-Pattern; Max-Zahl (50) + Max-Alter (7 Tage) bleiben Parameter. |
| Persistenz/Disziplin | Neues **`gallery/`**-Verz. lives in dem selben Bind-Mount wie `latest.*` (d. h. in `photos/`). Nothing to hand-migrate; leerer Zustand = leerer Ordner. |
| Konfiguration | Defaults via `os.getenv` (kein Manifest-Zwang). *Optional* (Phase M2): echte Add-on-Optionen `gallery_max_count` / `gallery_retention_days`. |
| Release | Neues **Minor** `2.2.0` (Feature, nicht Patch) + CHANGELOG-Eintrag. |
| Test | Neues `tests/test_gallery_history.py` + Erweiterung des funktionellen `/prepare-photo`/`/download`-Regressionstests. Gate: L0 grün (DoD), L3-Smoke, L4 Feld. |

---

## 1 · Kontext & Ist-Zustand (warum man *nicht* einfach umbenennen darf)

Die Pipeline arbeitet heute auf einem **Single-Slot**-Modell mit fixen Namen in `photos/`:

| Datei | Wird erzeugt von | Verwendet für |
|-------|------------------|---------------|
| `latest.bmp` | `save_three_previews()` | **Payload** fürs ESP32 (`/download` → hex) |
| `latest.status` | `prepare_photo()` („new") / `download` („delivered") | **Zustandsmaschine** der Prepare→Deliver-Entkopplung |
| `latest_original.jpg` | `save_three_previews()` | Preview „Original" (≤ 800×480) |
| `latest_processed.jpg` | `save_three_previews()` | Preview „E-Paper-Rendering" (Skalierung/Dithering/Rotation) |
| `latest_delivered.jpg` | `/download` (Copy bei Lieferung) | Nachweis, was tatsächlich auf dem Rahmen gezeigt wurde |

**Das kritische Invariant:** Der **ESP32-Handshake** (`/download`) sucht *explizit* `latest.bmp`
und `latest.status` und kopiert `latest_processed.jpg → latest_delivered.jpg`. Diese **fixen
Namen sind Teil des Wire-Protokolls**. Sie dürfen nicht zu `…_<ts>.jpg` umgestellt werden —
das würde den ESP32-Dialog brechen und einen „aktuell vs. veraltet"-Zustand erzeugen.

Folge: Die Galerie (heute 2.1.2) listet ausgerechnet diese fixen „aktuell"-Dateien → sie zeigt
nur den letzten Stand, nie eine Historie. Das ist das zu lösende Problem.

**Datfluss heute:**

```
[ESP32] ── GET /sleep ──┐
                        ▼
             ┌─────────────────────┐
   (1) POST /prepare-photo ─► provider.fetch_image() → (image, source_id)
             │                    save_three_previews(image)     ← fixte latest_*.jpg + latest.bmp
             │                    latest.status = "new"
             │
   (2) GET  /download  ─► liest latest.bmp + latest.status
             │              if status == "new": send BMP(hex); latest_processed.jpg→latest_delivered.jpg; status="delivered"
             ▼
          [ESP32 rendert]
```

---

## 2 · Ziel & Nicht-Ziele

**Ziel**
- Die Galerie zeigt **mehrere** vorbereitete Bilder als **Paare** (Original + E-Paper-Rendering),
  korreliert über ihre Quellen-ID, absteigend nach Zeit, begrenzt (Count/Alter).
- Volle Rücksicherheit: der Prepare→Deliver-Dialog mit dem ESP32 bleibt **bit-compatibel**.

**Nicht-Ziele (bewusst ausgeschlossen, können ggf. Folge-Features werden)**
- Kein Umbau des Live-Slots (Abschnitt 1).
- Kein eigenes „Delete/Select" im UI in Phase M1 (M3 optional).
- Keine Uploads von *externen* Bildern in die Galerie (nur was die Pipeline vorbereitet).
- Keine Änderung der Cython-Pipeline (`cpy.pyx`) oder des dither/render-Kerns.

---

## 3 · Konzept – Live-Slot bleibt, Archiv kommt dazu

Prinzip: **jede** erfolgreiche `Prepare` (und, optional, jede `Deliver`) legt zusätzlich
Archiv-Kopien mit korrelationsbezogenen Namen an. Die Galerie liest *nur* das Archiv.
Der Live-Slot dient weiterhin ausschließlich dem ESP32-Handshake.

```
   ┌────────────── photos/  (Bind-Mount, unverändertes Layout) ──────────────┐
   │                                                                          │
   │   latest.bmp          latest.status        tracking.txt   generations.json
   │   latest_original.jpg latest_processed.jpg  latest_delivered.jpg        ← LIVE-SLOT (fix, ESP32)
   │                                                                          │
   │   gallery/                                                             ← NEU (nur Galerie)
   │      original_<id>.jpg    processed_<id>.jpg    delivered_<id>.jpg     (≤ 50 Paare, ≤ 7 Tage)
   └──────────────────────────────────────────────────────────────────────────┘
```

```
 (1) POST /prepare-photo
      image, source_id = provider.fetch_image()
      shot_id = _shot_id(source_id)                    # sanitized id OR ts_uuid
      save_three_previews(image)                       # wie heute (Live-Slot)
      _archive_previews(shot_id)                      # NEU: copy latest_original.jpg→gallery/original_<id>.jpg
                                                     #      + copy latest_processed.jpg→gallery/processed_<id>.jpg
      latest.status = "new"
 (2) GET /download  (ESP32)
      ... unchanged: serves latest.bmp, sets status="delivered" ...
      _archive_delivered(shot_id)                    # optional M2: copy latest_delivered.jpg→gallery/delivered_<id>.jpg
 (3) GET /api/gallery-previews
      lists gallery/{original,processed,delivered}_*.jpg → grouped by id → UI
 (4) POST /cleanup-previews / startup
      cleanup_old_previews(directory=gallery, patterns=GALLERY_PATTERNS,
                           max_count=CFG, max_age=CFG)   # wiederverwendet
```

**Warum „Kopie ins Archiv" und kein „umbennen des Live-Slots"?**
- Der Live-Slot muss *immer exakt eine* „aktuell" -Datei je Typ tragen (so erwartet sie `/download`).
- Kopieren ist **atomar & idempotent** (gleicher `id` → gleicher Zielname → einfach überschreiben).
- Das Archiv ist reine *Lesedatenbank* für die Galerie → keinerlei Rückkopplung ins Wire-Protokoll.

---

## 4 · Datei-Layout (Vorher → Nachher)

**Vorher (2.1.2):** Galerie-Reader listet aus `photos/` die fixen `latest_{original,processed,delivered}.jpg`
(→ maximal 1 „Schuss", wird bei jedem Prepare überschrieben).

**Nachher (2.2.0):** Galerie-Reader listet `photos/gallery/` (`*_<id>.jpg`), gruppiert nach `id`.

Beispielinhalt nach 3 Prepsares (ids aus `source_id` bzw. Fallback):

```
gallery/
  original_ab12.jpg        processed_ab12.jpg        (2026-09-19 22:59)
  original_cd34.jpg        processed_cd34.jpg        (2026-09-19 21:10)
  original_20260919_2259_a1b2c3.jpg   processed_20260919_2259_a1b2c3.jpg   (Fallback, ohne source_id)
  delivered_ab12.jpg                                             (nur nach erfolgreicher Deliver)
```

Jedes `id`-Triplett stellt ein **paariges „Foto"** in der Galerie dar.

---

## 5 · Korrelations-ID (shot id) — Ableitung & Sanitisierung

```
def _shot_id(source_id: Optional[str]) -> str:
    if source_id:
        s = re.sub(r'[^A-Za-z0-9._-]', '_', str(source_id)).strip('_')
        if s:
            return s[:64]                       # Länge begrenzen, Datei-System-sicher
    return 'ts_' + datetime.utcnow().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]
```

- **Primär:** `source_id` der Quelle (Immich-Asset-ID, ComfyUI-ID). Vorteil: **idempotent** —
  dasselbe Asset erneut zu prepären überschreibt dessen Archiv-Eintrag (keine Duplikate),
  „newest"-Rotation erzeugt dagegen echte Fortschritte.
- **Fallback:** Zeitstempel + `uuid4`-Suffix → vermeidet Kollision bei sehr schnellen Wiederhol-Prepares
  ohne ID (wichtig unter `gunicorn --workers 2 --threads 2`).
- **Atomarer Write:** Archiv-Kopien immer via `shutil.copy2(src, tmp)` + `os.replace(tmp, dst)` →
  kein torn/Partial-File, selbst bei parallelen Workern (unterschiedliche Ziele sind kollisionsfrei).

---

## 6 · Änderungen im Code (konkret, pro Funktion)

Alle Änderungen in **`app.py`** (außer UI in `settings.html`); keine Änderung an `cpy.pyx`,
`providers.py` oder den ESP32-Routen.

### 6.1 Neue Module-Konstanten (neben `PREVIEW_PATTERNS`)
```
GALLERY_DIR           : str  = os.path.join(photo_dir, 'gallery')     # os.makedirs(exist_ok=True)
GALLERY_PATTERNS      : List[str] = ['original_*.jpg', 'processed_*.jpg', 'delivered_*.jpg']
GALLERY_MAX_COUNT     : int  = int(os.getenv('GALLERY_MAX_COUNT', '50'))         # Paare
GALLERY_MAX_AGE_SECONDS: int = 7 * 24 * 3600 * int(os.getenv('GALLERY_RETENTION_DAYS', '1')) // 1  # → 7 Tage
```
(Exakter Wert: `GALLERY_MAX_AGE_SECONDS = 86400 * int(os.getenv('GALLERY_RETENTION_DAYS','7'))`.)

### 6.2 Neue Helfer `_archive_previews(source_id)` (neben `save_three_previews`)
```
def _archive_previews(source_id: Optional[str]) -> None:
    shot = _shot_id(source_id)
    _copy_into_gallery('latest_original.jpg',   f'original_{shot}.jpg')
    _copy_into_gallery('latest_processed.jpg',   f'processed_{shot}.jpg')
# _copy_into_gallery relativ zu photo_dir → GALLERY_DIR, atomar (tmp + os.replace)
```
Hook: in **`prepare_photo()`** direkt **nach** `save_three_previews(image)`:
`_archive_previews(source_id)`. (Die Funktion kennt `source_id` bereits.)

### 6.3 (optional, Phase M2) `_archive_delivered(source_id)`
Im Deliver-Zweig von **`/download`** (wo heute `copy2(processed, delivered)` steht): zusätzlich
`latest_delivered.jpg → gallery/delivered_<shot>.jpg`. Nur sofern wir die „auf dem Rahmen gezeigt"-
Semantik in der Galerie anzeigen wollen.

### 6.4 Reader `/api/gallery-previews` umstellen
- Liest **`GALLERY_DIR`** (nicht mehr `photo_dir`), Pattern `GALLERY_PATTERNS`.
- Extrahiert pro Datei `id` (Zwischenpräfix) und `kind` (`original|processed|delivered`).
- Antwort (flach, UI gruppiert):
```
{ "files": [
    { "id": "ab12", "kind": "original",  "url": "/preview-file/original_ab12.jpg",
      "name": "original_ab12.jpg", "modified": "2026-09-19 22:59:01" },
    { "id": "ab12", "kind": "processed", "url": "/preview-file/processed_ab12.jpg", ... },
    ...
  ],
  "count": <n> }
```
- Sortierung absteigend nach `modified`, hart begrenzt auf `GALLERY_MAX_COUNT` **Paare**
  (gruppenweise begrenzen, nicht einzelnes Files, damit Paare zusammen bleiben).
- `/preview-file/<filename>` bleibt wie heute (`photo_dir`-relativ) → auf `GALLERY_DIR` ausweiten
  (`os.path.join(photo_dir, 'gallery', basename)`), weiterhin nur `basename` (Path-Traversal-sicher).

### 6.5 Aufräumen: `cleanup_old_previews()` wiederverwenden
Berechtnigt durch den existierenden `directory`-Parameter (aktuell ~Zeile 258). Wir brauchen
**keine** neue Prune-Logik, sondern einen zweiten Aufruf:
```
cleanup_old_previews(directory=GALLERY_DIR, patterns=GALLERY_PATTERNS,
                     max_count=GALLERY_MAX_COUNT, max_age_seconds=GALLERY_MAX_AGE_SECONDS)
```
(d. h. `cleanup_old_previews` bekommt einen optionalen `patterns`-Parameter; Standard bleibt
`PREVIEW_PATTERNS`, um die heutige Semantik zu wahren.) Aufruf: (a) passiv zu Beginn jedes
`/prepare-photo` (selbst-aufräumend), (b) im bestehenden `POST /cleanup-previews`, (c) optional
beim Start. **Niemals** auf dem Live-Slot anwenden (sonst löschen wir das aktuelle `latest.bmp`).

### 6.6 UI (`templates/settings.html`) — Gallery-Tab
- `loadGallery()` rendert jetzt **paare**: je `id` eine Karte mit 2 (bzw. 3) Thumbnails
  (Original | E-Paper-Rendering [| Delivered]) + der `modified`-Zeitzeile.
  Gruppierung: `Map<id, items[]>` client-side aus `files[]`.
- Empty-State: von *„No old previews found"* → *„No previews yet — press “Prepare New Photo“"*.
- IDs/CSP bleiben stabil (neue IDs nur für die neuen Wrapper-Elemente, wie beim UI-Redesign).
- Kein JS-Komplexitäts-Sprung: weiterhin Vanilla-JS, `fetch('./api/gallery-previews')` (relativ → ingress-tauglich).

### 6.7 (optional, Phase M2) konfigurierbare Grenzen
Neue **Add-on-Optionen** in `config.yaml` (`options:` + `schema:`) und `run.sh`
(`bashio::config`): `gallery_max_count` (int, default 50) und `gallery_retention_days`
(int, default 7) → in Env (`GALLERY_MAX_COUNT` / `GALLERY_RETENTION_DAYS`) → `DEFAULT_CONFIG`.
*Phase M1* kommt bewusst **ohne** neue Optionen aus (nur `os.getenv`-Defaults), damit die
Manifest/Schema-Drift klein bleibt (siehe AGENTS: „schema & run.sh halten im Gleichklang").

---

## 7 · Alternativen & warum verworfen

| Alt. | Idee | Warum nein |
|------|------|-----------|
| **A** | Live-Slot komplett auf `…_<ts>.jpg` umbenennen + „aktuell"-Zeiger (Symbolics / JSON-Pointer) | Brechert das ESP32-`/download`-Protokoll (sucht feste `latest.bmp`/`latest.status`), erzeugt Migration & Race auf dem *kritischen* Pfad. Hoher Aufwand, wenig Nutzen. |
| **B** | Status-Quo (nur aktuelle Dateien) | Ist exakt das zu lösende Problem (keine Historie). |
| **C** *(gewählt)* | Live-Slot fix belassen + additives `gallery/`-Archiv | Niedrigstes Risiko: ESP32-Bereich unberührt; Galerie = reine Lesedatenbank; idempotent & atomar. |

---

## 8 · Konfiguration & Defaults (zusammengefasst)

| Schlüssel | Default | Bedeutung | Phase |
|-----------|---------|-----------|-------|
| `GALLERY_MAX_COUNT` | `50` | max. Paare (original+processed) im Archiv | M1 (Env), M2 (Option) |
| `GALLERY_RETENTION_DAYS` | `7` | max. Alter eines Archiv-Eintrags | M1 (Env), M2 (Option) |
| `gallery/` (Verz.) | auto | Zielverzeichnis, liegt im `photos/`-Bind-Mount | M1 |

Wirklich „knöpfen" lässt sich das erst in M2 via Add-on-Optionen; bis dahin gelten die Env-Defaults
(HA-User ändert ggf. über die Add-on-Options, sobald M2 gelandet ist).

---

## 9 · Edge-Cases & Risiken

- **Konkurrenz (gunicorn 2×2):** Archiv-Targets sind pro `id` **distincte Dateien** → keine
  Schreib-/Lesekonflikte zwischen Workern. Gleiche `id` parallel (doppeltes Prepear desselben Assets)
  → atomar via `tmp + os.replace`; letztes Schreiben gewinnt, Inhalt identisch. **Risiko: niedrig.**
- **Disk-Bound:** max. `2×50` JPGs (≤ 800×480, q95 ≈ 50–150 KB) → Größenordnung < 20 MB;
  durch Count-*und* Age-Pruning beidseitig gedeckt. **Risiko: niedrig.**
- **Orphaning alter `latest_*.jpg`:** Die heutigen fixen Dateien bleiben *im Live-Slot* (werden vom
  ESP32 weiter gebraucht); das alte Verhalten „Galerie = letzte fixen Dateien" entfällt stillschweigend
  (Reader wechselt auf `gallery/`). Kein Datenverlust.
- **Immich-/ComfyUI-IDs als Filenames:** durch Sanitisierung (Abschnitt 5) + Längen-Cap +
  `uuid4`-Fallback garantiert OS-safe. **Risiko: gering.**
- **HEIC/RAW/…:** bereits *vor* `save_three_previews` in die Pillow-Bilder konvertiert
  (`register_heif_opener()` etc.) → die Archiv-Kopien sind immer JPEG; keine Encoding-Edge-Cases.
- **Ingress/ProxyFix:** Galerie-URLs bleiben **relativ** (`/preview-file/…`) → wie heute ingress-tauglich.
- **ESP32-Regressionsschutz:** der einzige „shared" Zustandsübergang bleibt `latest.*`; da wir ihn
  **nicht** anfassen, gilt: **kein** neues Risiko fürs Wire-Protokoll (wird im Testplan abgedeckt, s. 10).

---

## 10 · Testplan (Mapping auf die etablierten Ebenen)

Neu: **`tests/test_gallery_history.py`** (selbstlaufend, mocked, `tmp_path` wie die übrigen Suites).
Erweiterungen: `tests/test_functional.py` (Prepare/Deliver-Regression), `tests/test_nonfunctional.py`
(keine CSP-/Typing-Breakage durch die neuen Galerie-Elemente).

**L0 – Offline (Gate, DoD „100 %")**
- `test_archive_creates_pair`: `prepare_photo()` → `gallery/original_<id>.jpg` + `processed_<id>.jpg`
  existieren, beide ≈ identisch groß zu `latest_*.jpg`; `latest.status == 'new'` **unverändert**.
- `test_shot_id_sanitization`: `source_id` mit Pfad-/Sonderzeichen → nur `[A-Za-z0-9._-]`, ≤ 64, kein Crash.
- `test_shot_id_fallback_unique`: ohne `source_id` → zwei schnelle Aufrufe → **verschiedene** Fallback-ids.
- `test_reader_groups_and_caps`: 60 synthetische Paare → Reader liefert ≤ `GALLERY_MAX_COUNT`
  **Paare**, korrekt sortiert, `id`-Gruppierung stimmt; `delivered_` (falls vorhanden) gruppenzusammen.
- `test_cleanup_prunes_age_and_count`: alte + überzählige Archiv-Dateien werden entfernt; **Live-Slot bleibt**.
- **Regression** (kritisch): `test_download_protocol_unchanged`: `GET /download` liefert weiterhin
  `latest.bmp`-hex bei `status=new`, erzeugt `latest_delivered.jpg`, setzt `status=delivered` —
  **byte-stabil** gegenüber Pre-Feature (verhindert versehentliches Brechen des ESP32-Handshakes).

**L3 – Produktions-Image-Smoke**
- `docker build -f Dockerfile` → Boot → `POST /prepare-photo` (Fake-Source) → `gallery/` enthält
  2 Dateien → `GET /api/gallery-previews` listet das Paar → `/health` 200.

**L4 – Feld**
- Mehrere Tage echter Betrieb mit Immich: Galerie wächst, Cap/Retention trennen; ESP32 erhält weiterhin
  fehlerfrei Frames (Wire-Check via `latest.status`-Übergänge); kein sichtbarer Disk-Climb.

**Definition of Done (Feature)**
1. L0 grün (einschl. des neuen Files) und ESP32-Regressionstest stabil;
2. L3-Smoke zeigt ein archiviertes Paar + ordnungsgemäße Pruning;
3. L4-Feld: Galerie zeigt ≥ 3 Paare über ≥ 1 Tag; ESP32-Dialog intakt;
4. Changelog `2.2.0` geschrieben, `config.yaml`-Version angehoben (AGENTS „Release by bumping version").

---

## 11 · Rollout & Versionierung

- **Version:** Feature → **`2.2.0`** (Minor, nicht Patch). `epf-eink-addon/config.yaml` → `version: "2.2.0"`.
- **CHANGELOG:** neuer Eintrag `## [2.2.0]` (Added: „Preview-Galerie mit Historie …").
- **Kein** Breaking Change nach außen: ESP32-Konfig, Add-on-Options-Schema (in M1), Wire-Format bleiben.
- Migration: **keine** — leerer `gallery/`-Ordner ist der Nullzustand; alte `latest_*.jpg` unverändert.
- Rollback: `gallery/` ignorieren + Reader auf `photo_dir`-fixed-Namen zurück (Revert des Reader-Diffs) →
  Live-Slot war nie betroffen, daher trivial reversibel.

---

## 12 · Meilensteine (Phasen)

| Phase | Scope | Deploy-/Testbar eigenständig? |
|-------|-------|-------------------------------|
| **M1** (Kern) | `_shot_id` + `_archive_previews()` (orig+proc) · Hook in `prepare_photo` · Reader → `gallery/` (gruppiert) · `cleanup_old_previews(directory=gallery)` · UI paariert rendert · `test_gallery_history.py` (inkl. ESP32-Regression) · `2.2.0` | **Ja** – delivers the value (History + safe) |
| **M2** (optional) | `_archive_delivered()` im `/download`-Zweig · Add-on-Optionen `gallery_max_count`/`gallery_retention_days` (config.yaml + `run.sh` + `DEFAULT_CONFIG`) | Ja (nice-to-have) |
| **M3** (polish) | UI: „Galerie leeren" (neuer `/cleanup-previews`-Button), Lazy-Load-Thumbs, Hover-Lightbox; ggf. Paginierung | Ja (kosmetisch) |

> Empfehlung: **M1** ist das komplette, lohnende Feature. M2/M3 sind Ergänzungen, die separat
> gecuttet werden können, ohne M1 zu blockieren.

---

## 13 · Offene Fragen (vor M1-Start kurz entscheiden)

1. **Paar vs. Triplet als Standard:** M1 zeigt *Original + Processed*; „Delivered" als 3. Thumbnail
   nur in M2? (Empfehlung: ja, M1 = Paar.)
2. **Sortierung primär nach Zeit oder nach `id`?** (Empfehlung: Zeit/`modified`, `id` nur zum Gruppieren.)
3. **Soll die Galerie auch den letzten ESP32-Lieferzeitpunkt** zeigen? (würde die `delivered_`-Semantik brauchen → M2.)
4. **Cap-Einheit:** „Paare" (empfohlen, hält Paare zusammen) vs. einzelne Dateien bei der Pruning?

---

## 14 · Querverweise

- Wire-Vertrag & Invarianten: [`ARCHITECTURE.md`](../ARCHITECTURE.md) (§ Prepare/Deliver-Entkopplung).
- Testmodel/Ebenen: [`TESTSPEC.md`](../TESTSPEC.md) + `docs/test_specification_aspice.md`.
- UI-Design-Basis (Galerie-Tab, IDs, CSP): [`plans/ui-modernisierung.md`](ui-modernisierung.md).
- Vorlauf-Patches (dieser Feature vorgelagert): `2.1.1` (Script-Syntaxfix) / `2.1.2` (Reader→fix names).
- Anforderungen/ARC: `docs/requirements_specification_aspice.md`, `docs/architecture_document.md`
  (hier ggf. neue FR/I für „Historie" aufnehmen, falls gewünscht).
