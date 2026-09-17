# Findings — Settings-UI (Footer / Header)

**Repo:** `Zippo2000/epf-homeassistant-addons` · Add-on `epf-eink-addon` · **Stand:** v2.0.2
**Status:** `ALMOST CLOSED` — Phasen A ✅ (`05c0f23` + `9328979`), B ✅ (`9fce0e9`), C ✅ (Doku + Report 2.0.3) — verbleibt: **L3-Feld-Smokes** bei echter HA (Header ×2 Quellen, Footer) · **Sprache:** Deutsch · **Bezogen auf:** [`findings-14.md`](findings-14.md) (separater §14-Track, dort `CLOSED`)

> **Lesetipp:** Dieses File enthält **zwei** offene UI-Findings. Beide wurden gegen den
> aktuellen Code (v2.0.2) verifiziert. Jeder Abschnitt: *Beobachtung → Ursache → Plan →
> Test-Impact → Verifizierung*. Der Ausführungsplan mit Phasen/Gate/DoD steht in **§3–§5**.

---

## 1. Footer: Version & Build-Datum werden nicht gemeinsam gepflegt

### 1.1 Beobachtung (präzisiert)

Der Footer der Settings-Seite zeigt heute: **`v2.0.1 | Built: 2026-04-03 21:30:00 CET`**
(beim Finding-Stand; inzwischen ist die Version weitergezogen, s. u.).

**Rendering-Kette (verifiziert):**
- `epf-eink-addon/app.py` **L15–16** — zwei **hartkodierte** Module-Konstanten:
  ```python
  BUILD_TIMESTAMP = "2026-04-03 21:30:00 CET"   # L15
  BUILD_VERSION   = "2.0.2"                     # L16
  ```
- `app.py` **L550** — zusätzlich im Startup-Log: `logger.info(f"Build Version: {BUILD_VERSION} - {BUILD_TIMESTAMP}")`
- `app.py` **L628–629** — Übergabe an das Template: `render_template('settings.html', …, addon_version=BUILD_VERSION, build_timestamp=BUILD_TIMESTAMP)`
- `templates/settings.html` **L824**: `<div class="footer-version">v{{ addon_version }} | Built: {{ build_timestamp }}</div>`

**Fehlverhalten (reproduziert):** Seit Erstellung des Findings wurde `BUILD_VERSION` **zweimal**
bumped (2.0.1 → 2.0.2, inkl. Manifest `config.yaml` `version: "2.0.2"`), das Datum ist aber
weiterhin `2026-04-03 21:30:00 CET` — während u. a. der §14-Remediation-Track
(`findings-14.md`, Stand 2026-09-16/17) lief. Es existiert **kein Mechanismus**, der
Version und Datum koppelt; beide sind manuell gepflegte Strings.

> **Verwechslungsgefahr (nicht anfassen):** `Dockerfile` LABEL `io.hass.version="1.0.0"`
> ist die **minimal unterstützte HA-Version**, *nicht* die Add-on-Version — hat mit diesem
> Finding nichts zu tun.

### 1.2 Ursache

`BUILD_VERSION`/`BUILD_TIMESTAMP` sind **manuell zu pflegende Konstanten** in `app.py`.
Beim Version-Bump (Pflichtstelle: Manifest `config.yaml`) muss jemand *zudem* diese Konstante
und — wie das Finding verlangt — *zusätzlich* das Datum ändern. Genau dieser Schritt
(Datum) fällt in der Praxis durch → Footer lügt (statisches Datum, frische Version).

### 1.3 Plan (Schritt-für-Schritt)

**Leitidee:** Beide Footer-Werte **ableiten statt pflegen**. Implementierte Prioritätenkette
(**2026-09-17 verschärft**, `9fce0e9` — statt reiner Build-Args, weil das HA-Add-on-Buildsystem
keine custom `--build-arg` zuverlässig durchreicht; *in-image* funktioniert bei **jedem** Builder):
**(1)** Build-Arg/ENV-Override (`ADDON_VERSION` / `BUILD_TIMESTAMP`) → **(2)** Add-on-Manifest
`config.yaml` (in das Image neben `app.py` kopiert — **Single Source of Truth** der Version) →
**(3)** `.build_stamp`-Datei, die der `Dockerfile` beim Image-Build schreibt (UTC,
`SOURCE_DATE_EPOCH`-kompatibel) → **(4)** ehrlicher Fallback `dev`/`unknown`.

| # | Schritt | Wo | Was |
|---|--------|----|-----|
| P1-1 | **Version aus dem Manifest** | `Dockerfile` + `app.py` | (a) `Dockerfile`: `ARG ADDON_VERSION` + `ENV ADDON_VERSION=${ADDON_VERSION}` (optionaler Override) **und** `COPY config.yaml /app/` neben `app.py`. (b) `app.py`: `_resolve_build_version()` liest ENV → dann `version:`-Zeile des Manifests (kleiner Regex-Parser, kein `yaml` nötig wegen Import-Reihenfolge) → Fallback `"dev"`. `BUILD_VERSION: str = …` bleibt ein Zuweisungs-Literal (NFR-Source-Scan). Damit wird **ein** Bump im Manifest automatisch im Footer wirksam; `app.py` trägt keine Versionszahl mehr. |
| P1-2 | **Datum = Build-Zeit (UTC)** | `Dockerfile` + `app.py` | (a) `Dockerfile`: `RUN date -u '+%Y-%m-%d %H:%M:%S UTC' > .build_stamp` (WORKDIR `/app`), honoriert `SOURCE_DATE_EPOCH` für reproduzierbare Builds; `ARG ADDON_VERSION`/`ENV` wie P1-1. (b) `app.py`: `_resolve_build_timestamp()` liest ENV → dann `.build_stamp` → Fallback `"unknown"`. (Der Ursprungs-Plan mit `--build-arg BUILD_TIMESTAMP=$(date …)` ist obsolet: der ARG-Mechanismus ist bei HA-Builds nicht verlässlich — deshalb Datei im Image.) |
| P1-3 | **Fallback-Semantik** | `app.py` | Ohne Build-Args (lokaler Dev-Run, Tests): `dev` / `unknown` — **ehrlich** statt stehengelassenes Datum. Der Label-Text im Template **bleibt** `Built:` (semantisch korrekt: Zeit des Image-Builds). |
| P1-4 | **Tests nachziehen** | `tests/conftest.py` + `tests/test_functional.py` | (a) `app_module`-Fixture-Env-Block: `'ADDON_VERSION': '9.9.9-test'`, `'BUILD_TIMESTAMP': '2026-01-01 00:00:00 UTC'` ergänzen (deterministisch, keine echten Werte). (b) Neuer Test in `TestFR017*`/neue Kleinklasse: `GET /` → HTML enthält `v9.9.9-test` und `Built: 2026-01-01 00:00:00 UTC` (prägt genau den neuen Vertrag: „Footer zeigt ENV-Werte“). (c) Bestands-Test `test_nonfunctional.py::test_global_variables_have_types` (assertet Literal `'BUILD_TIMESTAMP =' in source`) **bleibt grün**, weil der Zuweisungs-Name erhalten bleibt — nur der RHS ändert sich. |
| P1-5 | **Doku** | `README.md` (Bau-Abschnitt), optional `AGENTS.md` | Build-Abschnitt um die zwei `--build-arg`-Flags + `SOURCE_DATE_EPOCH`-Hinweis ergänzen; Satz: „Version wird **ausschließlich** aus `config.yaml` injiziert.“ |

**Alternative (bewusst abgewählt):** `Built:` → `Started:` (App-Startzeit). Verworfen: der Wert
würde dann zwar nie „stehen bleiben“, aber die Frage *„wann wurde das Image gebaut?“* wäre
beantwortet **mit einer Lüge** (Startzeit ≠ Buildzeit).

### 1.4 Test-/Konflikt-Impact

- **`test_nonfunctional.py` L509** (`'BUILD_TIMESTAMP: str' or 'BUILD_TIMESTAMP ='`) — bleibt grün
  bei beibehaltenem Namen (§1.3 P1-2b).
- **Kein** anderer Test assertet die konkreten Footer-Werte (verifiziert: nur `test_functional.py`
  L1201 prüft das *Element* `healthText`, L824-Template ist nicht gematcht).
- `run.sh`/gunicorn: ENV wird unverändert in die Worker geerbt → kein Einrichtungsaufwand.

### 1.5 Verifizierung (Gate)

- [x] **Test-Suite:** `docker run --rm epf-eink-tests:local /run.sh` → **141 passed / 5 skipped** (inkl. neuem `TestFR017BFooterBuildInfo`), 2026-09-17.
- [x] **Produktions-Image ohne Args** (`epf-eink:local`): `import app` → `2.0.2 | 2026-09-17 20:08:49 UTC` — Version aus dem Manifest, Datum = echter Build-Zeitpunkt (`.build_stamp`); Startup-Log identisch.
- [x] **Produktions-Image mit Override** (`--build-arg ADDON_VERSION=9.9.9-override`): Override schlägt Manifest (`9.9.9-override`).
- [ ] **Manuell (L3):** Settings-UI in echter HA → Footer zeigt **Manifest-Version** + **heutiges** UTC-Build-Datum. *(steht aus — Add-on nach dem 2.0.2-Commit/Push neu bauen; zusammen mit den Finding-2-Smokes)*

---

## 2. Header „Connected“: Bedeutung unklar + vorhandene Info wird verworfen

### 2.1 Beobachtung (präzisiert)

Rechts oben in der Settings-Seite steht neben Akku-Datum und Theme-Button ein Indikator
(`settings.html` **L498–501**):

```html
<div class="health-status" id="healthStatus">
    <span class="health-dot"></span>
    <span id="healthText">Checking...</span>
</div>
```

**Was „Connected“ heißt (verifiziert):**
1. **UI-Logik** (`settings.html` `checkHealth()` **L899–918**, alle **60 s** via
   `setInterval(checkHealth, POLL_INTERVALS.HEALTH)`, `POLL_INTERVALS.HEALTH = 60000` L854):
   `fetch('./health', { method: 'HEAD' })` → `response.ok ? 'Connected' : 'Disconnected'`
   (+ Klassen `healthy`/`degraded` am Dot).
2. **Backend** (`app.py` `/health` **L632–649**): prüft **nicht** das Add-on selbst (das wäre
   tautologisch — der Browser hat die Seite gerade geladen) und **nicht** den ESP32.
   Es ruft `get_active_provider().health_check()` auf, d. h. **die konfigurierte Bildquelle**
   (`image_source`) gemäß `providers.py`:
   | Quelle | `health_check()` (Provider) | Probe |
   |--------|------------------------------|-------|
   | `Immich` | `GET {immich_url}/api/server/ping` (5 s) | 200 ⇒ ok |
   | `ComfyUI (HA)` | `GET {ha_url}/api/` (5 s) | 200/404 ⇒ ok |
   | `ComfyUI (Direct)` | `GET {url}/system_stats` (5 s) | 200 ⇒ ok |
   Response-JSON: `{'status','timestamp','source','source_status'}` mit **`source`** =
   z. B. `"Immich"` und **`source_status`** = `connected`/`unreachable`.

**Diagnose — zwei Mängel:**
- **(a) Semantik:** „Connected“ ohne Objekt. Niemand kann sagen, *womit* verbunden — es liest
  sich wie System-/Netz-/ESP32-Status. Tatsächlich = *„deine konfigurierte **Bildquelle** ist
  erreichbar“*. Ist Immich z. B. down, steht bloß „Disconnected“ — der eigentliche Wert
  (welcher Server?) bleibt unsichtbar.
- **(b) Verschwendeter Kanal:** Der `/health`-Body liefert bereits den Quellen-Namen
  (`source`) — **aber** das UI ruft **HEAD** (kein Body!) und hardcodet beide Labels. Die Info
  existiert, wird im Request-Design weggeworfen.

### 2.2 Plan (Schritt-für-Schritt)

| # | Schritt | Wo | Was |
|---|--------|----|-----|
| P2-1 | **HEAD → GET** | `settings.html` `checkHealth()` | `fetch('./health', { method: 'GET' }).then(r => r.json())` (Route unterstützt beide Methoden; `test_health_head` bleibt bestehen — HEAD-Unterstützung wird **nicht** entfernt, nur die UI nutzt GET). |
| P2-2 | **Quelle in den Label** | `settings.html` | Aus dem JSON rendern: gesund → `Immich online` / `ComfyUI (HA) online` / `ComfyUI (Direct) online`; krank → derselbe Name + `unreachable` (Dot rot, wie heute via `.degraded`). `source` fehlend/leer (Defensiv) → Fallback zu generischem `Connected`/`Disconnected` wie heute. |
| P2-3 | **Tooltip + Initialtext** | `settings.html` | `title` am `#healthStatus`: *„Erreichbarkeit der konfigurierten Bildquelle ({source})“*; serverseitig gerenderten Init-Platzhalter „Checking...“ → **„Bildquelle: …“** (klärt semantisch noch vor dem ersten Poll). *(Umgesetzt 2026-09-17 auf Englisch nach neuer Sprach-Regel: „Image source: …“ / Tooltip „Reachability of the configured image source (…)“ — s. `9328979`.)* |
| P2-4 | *(optional, P2)* **Zeitstempel** | `settings.html` | `data.timestamp` (ISO) in Kurzform im Tooltip anzeigen („zuletzt geprüft HH:MM:SS“) — nur wenn Aufwand klein bleibt; sonst weglassen. |
| P2-5 | **Test-Vertrag** | `tests/test_functional.py` (`TestFR017*`) | Bestands-Assertions (`status`, `source_status`) bleiben; **eine** Assertion ergänzen: `data['source'] == 'Immich'` im Healthy-Case (prägt den Feld-Vertrag, auf den die UI ab P2-2 verlässt). Kein HTML-Dom-Test nötig (kein Browser in pytest) — UI-Verhalten via L3-Smoke prüfen. |

### 2.3 Test-/Konflikt-Impact

- `test_functional.py` L1201 (`'healthText' in html`) — **unbetroffen** (IDs/L1201-Checks bleiben).
- `test_health_head` (L835 ff.) — **unbetroffen** (Endpoint behält HEAD).
- CSS-Klassen `.healthy`/`.degraded` bleiben der Mechanik-Grundlage; nur `textContent` ändert sich
  → kein Styling-Risiko.

### 2.4 Verifizierung (Gate)

- [x] `run.test.sh` → Exit 0 (inkl. neuer `source`-Assertion) — **140 passed, 5 skipped** (2026-09-17, Image `epf-eink-tests:local`).
- [ ] **L3-Smoke (manuell):** Settings-UI mit `image_source=immich` → Indikator zeigt „Immich online“ (bzw. „Immich unreachable“ bei gestopptem Immich); Tooltip korrekt. *(steht noch aus — braucht echte HA-Instanz)*
- [ ] **L3-Smoke (2. Quelle):** `image_source=comfyui_ha` (oder Direct) → Label wechselt entsprechend → beweist Quell-agnostik. *(steht noch aus — braucht echte HA-Instanz)*

---

## 3. Ausführungsplan (Phasen, Reihenfolge, Gates)

**Reihenfolge:** `A` (Finding 2 — klein, UI-only, sofort spürbarer Nutzen) → `B`
(Finding 1 — Build-System, breiterer Blast-Radius) → `C` (Doku + Abschluss).
Die Findings sind **voneinander unabhängig** (unterschiedliche Dateien außer README/DoD).

| Phase | Inhalt | Files | Gate |
|-------|--------|-------|------|
| **A** | Finding 2: P2-1 … P2-3 (P2-4/P2-5 optional hieran geklebt) | `templates/settings.html`, `tests/test_functional.py` | Suite grün + L3-Smoke (beide Quellen) |
| **B** | Finding 1: P1-1 … P1-4 | `Dockerfile`, `app.py`, `tests/conftest.py`, `tests/test_functional.py` | Suite grün + Image-Smoke mit/ohne Build-Args (§1.5) |
| **C** | P1-5 (README/AGENTS-Abgleich), ggf. P2-4, `ANALYSE.md`-Rückverweis, **Tag** (siehe §5) | `README.md`, evtl. `AGENTS.md`/`ANALYSE.md` | Doku-Konsistenz-Check, `git status` clean |

**Sequenz-Regeln:**
- **Atomarität** (wie in `findings-14.md`): Code + Mock + Assertion **im selben Commit** pro
  Phase — sonst rote Suite.
- Phase B **nach** A, damit `BUILD_TIMESTAMP`/`-VERSION`-Semantik nicht zweimal gleichzeitig im
  Review steht; zusätzlich: *keine* weitere Manuell-Bump von `app.py`-Version zwischen B
  (Manifest allein).

## 4. Definition of Done (gesamt)

Ein Finding ist **done**, wenn: (a) alle §-Verifizierungs-Boxen (1.5 bzw. 2.4) ✅,
(b) Suite `run.test.sh` **Exit 0**, (c) L3-Smoke des jeweiligen Items dokumentiert,
(d) Eintrag in **§5** mit Commit-Ref, (e) bei Finding 1 zusätzlich: **niemand** findet in
`app.py` noch eine Versionsziffer.

## 5. Verlauf-Protokoll

| Datum | Phase | Finding/Schritt | Beschreibung / Commit-Ref | Ergebnis |
|-------|-------|-----------------|----------------------------|----------|
| – | – | – | *(bei Arbeit aufnehmen hier eintragen; Pattern wie `findings-14.md` §7)* | – |
| 2026-09-17 | A | 2 | HEAD→GET, `{source} online/unreachable`, Tooltip, `source`-Assertion; **140/140 grün** | ✅ `05c0f23` |
| 2026-09-17 | A | 2+Rule | Language unified to **English** across `epf-eink-addon/` (UI strings + Dockerfile comments); rule anchored in `AGENTS.md` (“everything inside `epf-eink-addon/` is English”) | ✅ `9328979` |
| – | B | 1 | In-image-Derivation: Version ← Manifest (oder ARG-Override), Datum ← `.build_stamp`; **141/141 grün**; Prod-Smoke: `2.0.2 | 2026-09-17 20:08:49 UTC` + Override-Test | ✅ `9fce0e9` |
| 2026-09-17 | C | 1+2 | `AGENTS.md`-Gotchas nach §14 aufgebereinigt + Footer-Mechanismus-Entry; README „Building & Releasing“; `ANALYSE.md` §8-Header; `test_report_aspice.md` auf **141/146** (2.0.3); CHANGELOG 2.0.3; **Tag v2.0.2** (`614ab9c`) + v2.0.3; **Push nach origin/main** (damit die L3-Feld-Smokes lauffähig sind) | ✅ `614ab9c` + C-Commit |
| – | L3 | 1+2 | Feld-Smokes in echter HA: Header „Immich online/unreachable“ (+ 2. Quelle), Footer Manifest-Version + Build-Datum | ☐ *(nach 2.0.3-Update in HA)* |
