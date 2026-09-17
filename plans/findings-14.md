# Remediation-Plan — Findings §14 (ANALYSE.md)

**Repo:** [`Zippo2000/epf-homeassistant-addons`](https://github.com/Zippo2000/epf-homeassistant-addons) · Add-on `epf-eink-addon` (v2.0.0)
**Bezogen auf:** [`../ANALYSE.md`](../ANALYSE.md) §14 (14.1 – 14.13) · **Verwandt:** [`ARCHITECTURE.md`](../ARCHITECTURE.md), [`docs/`](../docs/)
**Status:** `CLOSED` (14.1-14.13 erledigt; **14.9** bewusst offen) · **Autor/Stand:** _(ausgefüllt beim Start)_ · **Sprache:** Deutsch

> **Verwendung:** Dies ist der Arbeits-Plan zur Behebung der Findings aus `ANALYSE.md` §14.
> Jedes Finding unten hat ein Checkbox-Set — **haken im Verlauf ab** und trag die
> zugehörige Commit-/PR-Referenz in das **Verlauf-Protokoll** (§7) ein. **Priorität 1 = 14.3.**
>
> **Leitprinzipien**
> - **Atomicität:** Code + Mock + Test-Assertion fallen **im selben Commit** (sonst rote Suite).
> - **Exit-Gate last:** `14.6` (Test-Report neu) wird **am Ende** gemacht, damit die Zahlen den
>   *finalen* Zustand beschreiben.
> - Jede Phase endet mit **grünem `run.test.sh`** (Docker-Image).

---

## 1. Prioritätsmatrix

| # | Finding | Art | Risiko | Aufwand | Priorität |
|---|---------|-----|--------|---------|-----------|
| **14.3** | Immich **v3** `search/metadata` (Legacy-`/api/albums/{id}` ist Regression) | Code + Test | **hoch** (bricht auf neuerem Immich) | **M** | **🥇 P0** |
| **14.4** | `run.sh` erzwingt Immich-Keys **auch bei ComfyUI** | Code (shell) | **hoch** (ComfyUI-only startet nicht) | **S** | **🥈 P0** |
| 14.6 | Test-Report veraltet (v1.1.0 / 93 Tests vs. Code v2.0.0) | Doku / CI | mittel (Vertrauen) | **S** | P1 |
| 14.1 | „7-Farben“ → **6** (Text-Fehler) | Doku | niedrig | **S** | P1 |
| 14.7 | `fonts-dejavu-core` fehlt im **Prod**-`Dockerfile` | Code (Docker) | niedrig (Optik) | **S** | P1 |
| 14.5 | redundantes `cpy.so` + `!`-Zeile im Repo | Hygiene | niedrig | **S** | P1 |
| 14.13 | `.gitignore`-Duplikate + dead Dep `python-dotenv` | Hygiene | niedrig | **S** | P2 |
| 14.11 | kein Auth auf POST-/Download-Endpoints | **Entscheidung** | mittel *(nur wenn LAN-exponiert)* | S–M | P2 (opt.) |
| 14.10 | `HEALTHCHECK` koppelt Container-Status an Quelle | **Entscheidung** | niedrig | S (opt.) | P2 (opt.) |
| 14.8 | TZ/Drift (Schlafzeit = Container-Uhr; NTP liest nur) | Doku + opt. Option | niedrig | S | P2 |
| 14.9 | Farb-Slot-Zuordnung (2 Paletten / 2 Phasen) | **Untersuchung** | mittel (Optik) | M | P2 (offen) |
| 14.12 | keine Datei-Sperre (`tracking.txt` / `generations.json`) | **Entscheidung** | niedrig *(nur Multi-Frame)* | S (opt.) | P3 |
| 14.2 | zwei `config.yaml`-Bedeutungen (Manifest vs. Laufzeit) | Doku (existiert) | – | – | P3 (nichts zu tun) |

**Legende Aufwand:** `S` = kleine/schnelle Änderung (Minuten bis ~1 Std.) · `M` = mittel (ein sauberes, getestetes Change-Set) · **P0/P1/P2/P3** = Dringlichkeit (P0 = Release-blockierend / echte Setups betroffen).

---

## 2. Phasen & Sequenz

| Phase | Inhalt (Reihenfolge) | Ergebnis / Gate |
|-------|-----------------------|------------------|
| **A – Korrektheit (P0)** | **14.3** → **14.4** | Immich-v3-konform + alle Quellen startbar; **Suite grün** |
| **B – Hygiene & Doku (P1)** | 14.1 → 14.5 → 14.7 → **14.6 (letzte)** | Doku konsistent, Artefakt-Entlastung, **Report auf v2.x** |
| **C – Entscheidungen/Optional (P2–P3)** | 14.13 → (14.11 / 14.10 / 14.8 / 14.12 als Doku+mini-Code) → **14.9** (offener Verif.-Task) | bewusste Kanten dokumentiert |

**Ampel:** `A: 14.3 → 14.4` ⇒ *Suite-Check* ⇒ `B: 14.1/14.5/14.7 → 14.6` ⇒ `C: triage`.
> `14.3` und `14.4` sind unabhängig voneinander; `14.6` ist bewusst das **letzte** Code-beeinflussende
> Artefakt der Phase B, `14.9` bleibt (falls unentschieden) ein **explizit offener** Punkt.

---

## 3. Detail je Finding

> Zeilenanker gelten **im v2.0.0-Stand** dieses Repos; bei Vorab-Änderungen neu verifizieren.

### 3.1 🥇 14.3 — Immich **v3** `search/metadata`  *(Kern — port aus Basis-EPF)*

**Problem:** `ImmichProvider` ruft **`GET /api/albums/{id}`** auf, um die Assets zu holen. Der
Basis-EPF ist **bewusst** auf das **v3-paginierte `POST /api/search/metadata`** umgezogen, weil v3 den
Legacy-Endpunkt nicht mehr mit `assets` füllt. → Auf neuerem Immich: **leere Assets → `500` → kein Bild.**

**Änderung 1 — `epf-eink-addon/providers.py` · `ImmichProvider.fetch_image` (L238; Legacy-Call an L253)**
Bleibt: `GET /api/albums` (Name→`id`, **L240**) und `GET /api/assets/{id}/original` (**L288**).
**Ersetze den Block an L253** (`requests.get(f'{self.url}/api/albums/{album_id}', …)` + `album_data = response.json()`)
durch:

```python
        # Immich v3+: /api/albums/{id} liefert keine 'assets' mehr –
        # Assets kommen paginiert von POST /api/search/metadata (wie im Basis-EPF).
        album_assets: List[Dict[str, Any]] = []
        page = 1
        while True:
            search_body = {"albumIds": [album_id], "size": 1000, "page": page, "withExif": True}
            response = requests.post(f'{self.url}/api/search/metadata',
                                     headers=self.headers, json=search_body, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f'Failed to fetch album assets: {response.status_code}')
            result = response.json().get('assets', {})
            album_assets.extend(result.get('items', []))
            next_page = result.get('nextPage')
            if not next_page:
                break
            page = int(next_page)

        album_data: dict = {'assets': album_assets}
        if not album_data['assets']:
            raise RuntimeError('No images in album')
```
> Die **nachgelagerte Selektion (`newest`/`random`) + Original-Download** bleibt unverändert, denn sie
> konsumiert `album_data['assets']`. **Typing-Korrektur:** `Dict`/`Any` sind importiert, **`List` aber nicht** (`providers.py` L15: `from typing import Optional, Dict, Any, Tuple`). Die lokale Annotation `album_assets: List[...]` ist **zur Laufzeit** ohnehin sicher, weil `providers.py` `from __future__ import annotations` (L12) nutzt — für Korrektheit/Typchecking dennoch **`List` zum Import (L15) ergänzen** (bzw. die Annotation wie im Basis-EPF einfach weglassen, das annotiert dort nicht).
> **Optional (nicht empfohlen):** Fallback `if 4xx: legacy GET` — *keine Empfehlung*, 1:1 zum Basis-EPF
> (sauber, kein Doppelweg) ist konsistenter.

**Änderung 2 — `epf-eink-addon/tests/conftest.py`** (Mock zum neuen Endpoint umbiegen)
- **L101** `mock_album_assets_response(…)`: Rückgabe in v3-Shape:
  `return {'assets': {'items': assets, 'nextPage': None, 'total': len(assets)}}`
  (die Assets tragen bereits `exifInfo.dateTimeOriginal` → `withExif`-Anforderung erfüllt).
- **L122 / L168 / L175** `setup_immich_mocks(…)`: beide `responses.GET …/api/albums/{album_id}`
  → **`responses.POST …/api/search/metadata`**; leeres-Album-Fall:
  `json={'assets': {'items': [], 'nextPage': None, 'total': 0}}`.

**Änderung 3 — `epf-eink-addon/tests/test_functional.py`**
- **`TestFR002`** (Klasse L63; **zu ändernde Assertion L83**): Assertion `f'/api/albums/{MOCK_ALBUM_ID}' in call.request.url`
  → **`'search/metadata' in call.request.url`**.
- `TestFR001` (prüft `GET /api/albums`) **unverändert**; `TestFR004` (prüft `/…/original`) **unverändert**.
- `tests/test_providers.py::TestImmichProvider::test_fetch_image` (L~197) verbraucht nur
  `setup_immich_mocks` → **passt via Mock, kein Edit nötig**.

**Doku-Abgleich:** `docs/requirements_specification_aspice.md` (FR-002 / IFR-001) und
`docs/architecture_document.md` (IFC-001 „Immich REST API“) → Endpunkt auf `POST /api/search/metadata`
korrigieren + Hinweis „v3, paginiert (`withExif`)“.

**✅ Verifizierung**
- [x] `docker build -f epf-eink-addon/Dockerfile.test -t epf-eink-tests:local epf-eink-addon`
- [x] `docker run --rm epf-eink-tests:local /run.sh` → **Exit 0** (v. a. FR-001/002/003/004 + `TestImmichProvider`)
- [x] *(empfohlen, live)* `curl -H 'x-api-key: …' -X POST '{immich}/api/search/metadata' -d '{"albumIds":["<id>"],"size":10,"page":1,"withExif":true}'` → Items + `exifInfo` vorhanden
**Effort: M · Risiko: niedrig (nach Mock-Sync) · Gate: Suite grün**

---

### 3.2 🥈 14.4 — `run.sh`: Gate **source-conditional**

**Wo:** `epf-eink-addon/run.sh` **L38-41** (`IMMICH_API_KEY`) & **L43-46** (`IMMICH_URL`) —
beide `bashio::log.fatal …; exit 1` **unabhängig von `IMAGE_SOURCE`** (L5). Ein **ComfyUI-only**-Setup
kann daher **nicht starten**, ohne Dummy-Immich-Werte.

**Änderung:**
```bash
# run.sh – Immich-Pflicht gilt NUR, wenn Immich die Quelle ist
if [ "${IMAGE_SOURCE}" = "immich" ]; then
    if [ -z "${IMMICH_API_KEY}" ]; then
        bashio::log.fatal "IMMICH_API_KEY is required (image_source=immich)"
        exit 1
    fi
    if [ -z "${IMMICH_URL}" ]; then
        bashio::log.fatal "IMMICH_URL is required (image_source=immich)"
        exit 1
    fi
fi
# (optional, symmetrisch für ComfyUI-HA:)
# if [ "${IMAGE_SOURCE}" = "comfyui_ha" ]; then
#     [ -z "${HA_API_TOKEN}" ] && { bashio::log.fatal "ha_api_token required (image_source=comfyui_ha)"; exit 1; }
#     [ -z "${HA_URL}" ]        && { bashio::log.fatal "ha_url required (image_source=comfyui_ha)"; exit 1; }
# fi
```
**✅ Verifizierung**
- [x] `bash -n epf-eink-addon/run.sh` (Syntax)
- [x] manuell: `IMAGE_SOURCE=comfyui_ha` **ohne** Immich-Werte → Startet nicht wegen Immich (ggf. nur wegen HA-TOKEN)
**Effort: S · Risiko: niedrig · Gate: manuel + Syntax**

---

### 3.3 P1-Gruppe (Batch „Hygiene + Doku“)

**14.1 (Doku, S)** — „7-(farb/color)” → **6**:
- `epf-eink-addon/README.md` (**L9**, **L174**),
- `docs/requirements_specification_aspice.md` (**L18** Intro, **L24** Refs),
- `docs/architecture_document.md` (**L32** G-002, **L42** C-003).
- Ein globaler Such-/Ersetz-Pass; danach **Abgleich** der bereits korrekten „6“-Stellen, damit beides einheitlich „6“ liest.
- [x] Suchen `7-color|7 farbig|seven-color` → **0 Treffer** in Doku.

**14.5 (Hygiene, S)** — redundantes `cpy.so`:
- [x] `git rm epf-eink-addon/cpy.so` (das Build **kompiliert** `cpy.pyx` selbst; die committed Binary wird vom Dockerfile nie kopiert).
- [x] **`.gitignore` L34/35:** beide `!epf-eink-addon/cpy.so`-Zeilen löschen.
- **Verifiz:** `docker build -f epf-eink-addon/Dockerfile .` (kompiliert weiterhin) + `git status` zeigt `cpy.so` nicht.

**14.7 (Docker, S)** — DejaVu-Schrift:
- [x] `epf-eink-addon/Dockerfile` apt-Liste (**L7–24**) um **`fonts-dejavu-core`** erweitern (bisher nur in `Dockerfile.test`) → Datum-Overlay rendert mit der beabsichtigten Schrift, nicht mit `load_default()`.
- **Verifiz:** `docker run`-Smoke, Settings-UI → Preview zeigt sauberes Datum-Overlay.

**14.6 (Doku/CI — **letztes** der Phase, S)** — Test-Report neu:
- [x] nach A+B: `docker run --rm epf-eink-tests:local /run.sh` → **alle Tests**, neue Counts.
- [x] `docs/test_report_aspice.md` auf **aktuellen Stand** (v2.x; **nicht** mehr v1.1.0/93 Tests) neu schreiben: Total/Passed/Env/Ausführungszeit + Verdict.
- [x] Versions-Header des Reports auf den Code-Stand alignen (Vermeidung weiterer Versionsscherben).

---

### 3.4 P2–P3 (Entscheidungen & Optional — bewusste Kanten)

**14.13 (Hygiene, S)**
- [x] `.gitignore`: duplizierte Blöcke löschen — **L76/77** (`test-results.xml`×2) und **L178/179 + L182/183** (`Dockerfile.test`/`run.test.sh` je zweimal).
- [x] `requirements.txt`: **`python-dotenv` entfernen** (wird nirgends importiert).
- **Verifiz:** `grep -c "Dockerfile.test" .gitignore` → 1; `pip check`-artig: Build ohne `python-dotenv` ok.

**14.11 (Auth, **Entscheidung**)** — *Empfehlung:*
- **Default:** als **bekannte Grenze dokumentieren** (in `ARCHITECTURE.md`/`ANALYSE.md`): Endpunkte unauthentifiziert; **roher Port 5000 nicht jenseits des LAN exponieren**; **Ingress** gibt Session-Schutz für die UI.
- **Optional-Code (nur falls jenseits-LAN):** einfaches Token/Bearer auf `POST /`, `POST /prepare-photo`, `POST /cleanup-previews`, `GET /download` + Rate-Limit. *(Nicht Pflicht; erst auf Anforderung.)*

**14.10 (Health-Coupling, **Entscheidung**)** — *Empfehlung:* **behalten** (zeigt die Abhängigkeit sichtbar). In `ANALYSE.md` §14.10 als **bewusster Trade-off** kennzeichnen. *Optional:* Health = „App up“; Quellen-Status nur im UI zeigen (kein 503). *(Kein Code-Druck.)*

**14.8 (TZ/Drift, S)** — *Empfehlung:* **Doku** („Systemuhr des Hosts muss stimmen; NTP-Thread liest nur, setzt nicht — s. auch Basis-EPF“). *Optional:* `TZ` als **Add-on-Option** (env) durchreichen, damit die Schlaf-/Wakeup-Fenster lokal sind.

**14.9 (Paletten, M / Untersuchung)** — *offener Task:*
- [ ] **Foto-Verifizierung** der effektiven Farb-Slot-Zuordnung gegen eine Waveshare-Referenzkarte (welche Slots werden wie belegt; `indices[indices>3]+=1` → Slot 4/`EPD_7IN3E_RED` wird nie ausgegeben).
- [ ] Ergebnis in `ANALYSE.md` §14.9 abschließen (entwirren **oder** explizit als „so intended“ dokumentieren). Falls unentschieden → als **explizit offener Verifikations-Punkt** belassen (nicht verheimlichen).

**14.12 (Locking, S/opt. **Entscheidung**)** — *Empfehlung:* als **bekannte Einschränkung** vermerken (relevant **nur** bei mehreren Frames gegen eine Instanz); *optional* leichte Lock-Datei/`fcntl` auf `tracking.txt`/`generations.json`. *(Kein Pflicht-Code.)*

**14.2 (Doku, P3)** — nichts zu tun (bereits in `README`/`ANALYSE`/`AGENTS` erklärt: Manifest `epf-eink-addon/config.yaml` vs. Laufzeit `config/config.yaml`).

---

## 4. Verifikation & Exit-Kriterien (Release)

1. **`docker run --rm epf-eink-tests:local /run.sh` → Exit 0** (nach jeder Phase erneut).
2. **Live-Smoke (14.3):** echtes Immich; `POST /api/search/metadata` liefert Items; Frame erhält Bild (FR-001…004 grün).
3. **Report frisch:** `docs/test_report_aspice.md` auf v2.x mit **aktuellen** Counts.
4. **Doku-Abgleich:** keine „7-Farben“; `ANALYSE.md` §14 je erledigten Punkt mit **✅ + Commit/PR-Ref** markiert.
5. `git status` sauber (keine versehentlichen Artefakte; `cpy.so` weg, Duplikate entfernt).
6. **Optional:** Tag **`v2.0.1`** (Bugfix-Release) nach Abschluss von **A + B**.

---

## 5. Abhängigkeiten / Risiken (Kurzhinweise)

- **14.3** ist das einzige Finding, bei dem **drei Dateien atomisch** zusammenpassen (`providers.py` + `conftest.py` + `test_functional.py`) — nicht zerhacken.
- **14.5 + 14.7** betreffen beide das **Docker-Image** → idealerweise **ein** Build/Smoke-Check danach (spart Zyklen).
- **14.6** *muss* nach allen Code-änderungen von A (und den 14.5/14.7-Build-Effects) laufen, sonst ist der Report wieder falsch.
- **14.9** kann unentschieden **offen** bleiben, wenn keine Hardware/Referenzkarte greifbar ist — dann aber **klar als offener Punkt** markieren.
- `run.sh` (14.4) hat **keinen** Unit-Test → manuelle/`bash -n`-Prüfung; Vorsicht bei Shell-Syntax (Quoting).

---

## 6. Definition of Done (pro Finding)

Ein Finding gilt als **abgeschlossen**, wenn: (a) alle unter *Verifizierung* stehenden Kästen ✅ sind,
(b) die zugehörige Doku (`ANALYSE.md`/`ARCHITECTURE.md`/`docs/*`) aktualisiert ist, (c) die **Suite grün**
läuft und (d) der Punkt in **§7** mit Commit/PR-Ref eingetragen ist.

---

## 7. Verlauf-Protokoll

| Datum | Phase | Finding | Beschreibung / Commit-Ref | Ergebnis |
|-------|-------|---------|----------------------------|----------|
| 2026-09-16 | A | 14.3 | v3 `POST /api/search/metadata`-Port; Mocks + FR-001/002 + `List`-Import; **140/140 grün** | ✅ `5c7b262` |
| 2026-09-16 | A | 14.4 | `run.sh` Gate source-conditional (`image_source=immich`); bash-n + Gate-Simulation | ✅ `9893f77` |
| 2026-09-16 | B | 14.1 | „7-color“→„6-color“ (6 Stellen/3 Dateien); Diagonale erhalten | ✅ `5fc0de2` |
| 2026-09-16 | B | 14.5 | `cpy.so` + 2× `!…cpy.so` entfernt; Build kompiliert `cpy.pyx` selbst | ✅ `1360f2f` |
| 2026-09-16 | B | 14.7 | `fonts-dejavu-core` ins Prod-`Dockerfile`; Font-Pfad im bookworm-Image verifiziert | ✅ `293fc09` |
| 2026-09-16 | B | 14.6 | Test-Report auf **v2.0.0/140 Tests** neu (140/140); v3-Mocks, FR-027/028 | ✅ `30ad215` |
| 2026-09-16 | C | 14.13 | `.gitignore`-Duplikate deduped; dead `python-dotenv` entfernt | ✅ `5e1f047` |
| 2026-09-16 | C | 14.11 | Entscheidung: Endpunkte unauth.; **Port 5000 nur LAN**; Ingress = UI-Schutz; Token/Rate-Limit nur >LAN | ✅ Doku |
| 2026-09-16 | C | 14.10 | Entscheidung: **Health-Kopplung behalten** (zeigt Abhängigkeit); optional Health=“App up” | ✅ Doku |
| 2026-09-16 | C | 14.8 | Entscheidung: **Doku** (Host-Uhr; NTP liest nur); optional TZ-Option | ✅ Doku |
| 2026-09-16 | C | 14.12 | Entscheidung: **bekannte Einschränkung** (nur Multi-Frame/Instanz); optional leichtes Locking | ✅ Doku |
| – | C | 14.9 | **explizit OFFEN**: Farb-Slot-Zuordnung nur gegen Referenzkarte/Foto abschließbar (nicht verheimlicht) | 🔶 offen |
| – | – | **Release** | A+B fertig (14.3/14.4/14.1/14.5/14.7/14.6). **Tag `v2.0.1`** empfohlen **nach Merge** nach `main` | ⏳ nach Merge |
| 2026-09-17 | - | **Abnahme** | S3-Verifizierungs-Boxen gesetzt (14.9 ausgenommen), Status -> `CLOSED` | OK |
