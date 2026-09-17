# Testspezifikation & -Modell – EPF E-Ink Add-on

**Projekt:** `epf-homeassistant-addons` / Add-on `epf-eink-addon` · **Stand:** v2.0.0
**Sprache:** Deutsch (analytisch) · **Verwandt:** [`ANALYSE.md`](ANALYSE.md),
[`docs/test_specification_aspice.md`](docs/test_specification_aspice.md) (EPF-TST-001, formale ASPICE-
Spezifikation), [`docs/test_report_aspice.md`](docs/test_report_aspice.md) (EPF-RPT-001).

> **Abgrenzung:** Die *formale* ASPICE-Test-Spezifikation mit je-einem-Testfall-pro-Requirement liegt in
> `docs/test_specification_aspice.md`. Dieses Dokument ist das **kurze Modell**: *wie* die Suite
> aufgebaut & gelaufen ist, *wo* welche Anforderungen abgedeckt sind, und *was* man beim Lesen wissen
> muss (v. a. die Versionsscherbe im Report).

---

## 1. Testphilosophie

Die Suite ist **komplett offline & deterministisch**: kein Netzwerk, kein echtes Immich, kein HA, kein
ComfyUI. Das ist möglich, weil drei Dinge gemockt/umbaut werden, während **die echte Anwendung**
(`app.py`, `providers.py`, `cpy.so`) **unberührt** getestet wird:

| Was | Wie |
|-----|-----|
| **Immich-/HA-HTTP** | Bibliothek **`responses`** (interceptiert `requests`; `ping`/`albums`/`albums/{id}`/`assets/{id}/original`) |
| **NTP** | `ntplib.NTPClient` via `unittest.mock.patch` (kein echtes `pool.ntp.org`) |
| **File-Watching** | `watchdog.observers.Observer` → `MagicMock` (kein echter Observer-Thread) |
| **File-System** | pytest **`tmp_path`** → `photo_dir`/`config_path`/`tracking_file` in ein Temp-Dir umgeleitet |
| **Modul-Isolation** | jedes Test-Setup **löscht `sys.modules['app']`** und importiert **frisch** (State-Reset pro Test) |

**Kern-Gewinn:** Die **echte** Pipeline (Cython-Dithering, Scaling, Hex-Packing, Provider-Logik,
Flask-Routes) wird ausgeführt — nur die *externen Abhängigkeiten* sind Simulationen. Dadurch testen
z. B. die Floyd-/Atkinson-Cases die **echte** `cpy.so`-Bitauflösung, nicht ein Stub.

---

## 2. Laufumgebung & wie man es startet

**Primär: Docker-Test-Image** (deterministische Arch/Versionen, Cython wird *im Build* kompiliert):
```bash
# vom Repo-Root
docker build -f epf-eink-addon/Dockerfile.test -t epf-eink-tests:local epf-eink-addon
docker run --rm epf-eink-tests:local /run.sh          # → run.test.sh → pytest + junitxml
```
`Dockerfile.test` = Prod-Basis **plus** `fonts-dejavu-core` (für den Date-Overlay-Pfad) **plus**
`tests/`; seine `CMD` ist `run.test.sh` (`python3 -m pytest tests/ -v --junitxml=/app/test-results.xml`).
Der Exit-Code von `pytest` wird weitergegeben (Grün/Rot im CI).

**Alternativ: lokal** (Python 3.11, Dependencies aus `requirements.txt`, v. a. `responses`, `rawpy`,
`Cython`/`numpy`/`Pillow`):
```bash
cd epf-eink-addon
python setup.py build_ext --inplace        # cpy.so für lokalen Import
python -m pytest tests/ -v
```
> `tests/conftest.py` + `tests/` müssen importierbar sein (wurde so gelegt, dass `python -m pytest
> tests/` aus `epf-eink-addon/` funktioniert; `from conftest import …` und `from tests.conftest import …`
> werden beide unterstützt).

---

## 3. Test-Module & Abdeckung (Requirement → Test-Klasse)

Vier Dateien; jede Test-Klasse trägt die ASPICE-IDs im Namen.

### `tests/conftest.py` (Fixtures/Helpers — selbst nicht „getestet”)
* **`app_module`** — DER Setup-Fixuture: setzt alle Env-Defaults, patcht `NTPClient` + `Observer`,
  leert `sys.modules['app']`, `import app`, überschreibt `photo_dir`/`config_path`/`tracking_file`
  → `tmp_path`, setzt `last_battery_* = 0`, löscht `tracking.txt`, **yieldet das Modu**.
* **`client_with_mocks`** — `flask_client` (Test-Client, `TESTING=True`) **plus** `responses`-Mocks
  (Immich ping/albums/album-assets/original). Der meistverwendete Fixture für **Endpoint**-Tests.
* **`app_with_immich_mocks`** — wie oben, ohne Client (für Modul-level-Checks).
* Hilfs-Generatoren: `create_test_image` (Gradient, optional **EXIF `DateTimeOriginal`**),
  `mock_album_assets_response`, `setup_immich_mocks`, `write_test_config`.

### `tests/test_functional.py` → **FR-001 … FR-015**
| Klasse | Requirement | Prüft (Kernel) |
|--------|-------------|----------------|
| `TestFR001AlbumRetrieval` | FR-001 | `/api/albums` + `x-api-key` → Album-`id` |
| `TestFR002AlbumAssetRetrieval` | FR-002 | `assets` für konfiguriertes Album |
| `TestFR003ImageSelection` | FR-003 | `random`→unseen, `newest`→neu, **Reset** nach „alle gezeigt“ |
| `TestFR004ImageDownload` | FR-004 | Original-Download |
| `TestFR005FormatConversion` | FR-005 | JPEG direkt; RAW/HEIC-Functions existieren |
| `TestFR006ScalingRotation` | FR-006 | `load_scaled` → 800×480; Rotation 90/180/270; `fill`=Crop, `fit`=Letterbox |
| `TestFR007ColorEnhancement` | FR-007 | neutral=unchanged; `enhance=0`→Grayscale |
| `TestFR008FloydSteinberg` | FR-008/009 | Shape (480,800,3), **6-Farben-Palette**, **Atkinson** analog |
| `TestFR010DateOverlay` | FR-010 | Overlay **mit** EXIF-Datum; **keine** ohne |
| `TestFR011PreviewGeneration` | FR-011 | 3 Previews; original resized; BMP valide |
| `TestFR012HexFormat` | FR-012 | `convert_to_hex_format` → `BytesIO`; korrekter Inhalt |
| `TestFR013ImageDelivery` | FR-013 | prepared delivered; **on-the-fly** delivery; `batteryCap`-Recording |
| `TestFR014PreparePhoto` | FR-014 | `POST /prepare-photo` → success + Status `new` |
| `TestFR015PreviewServing` | FR-015 | `/preview-photo`/`/preview-original`/… 200 |

### `tests/test_nonfunctional.py` → **NFR + IFR + SEC + PER**
| Klasse | ID | Prüft |
|--------|----|-------|
| `TestNFR003HealthCheck` | NFR-003 | `/health`-Endpoint existiert (200/503) |
| `TestNFR004Logging` | NFR-004 | Log-Format; `LOG_LEVEL` konfigurierbar |
| `TestNFR006ResponseTime` | NFR-006 | Bildverarbeitung < 120 s |
| `TestNFR007MemoryFootprint` | NFR-007 | NumPy-Array-Größe; Speicher nach Verarbeitung frei |
| `TestNFR008ThemeSupport` | NFR-008 | UI hat Theme-CSS + Toggle + `localStorage` |
| `TestNFR009TypeAnnotations` | NFR-009 | `from __future__ import annotations`; Typen auf Funks/Globalen |
| `TestIFR001ImmichAPI` | IFR-001 | `x-api-key`-Header gesetzt; Timeouts konfiguriert |
| `TestIFR002ESP32Interface` | IFR-002 | `/download` liefert `text/plain`; akzeptiert `batteryCap` |
| `TestIFR003HAIngress` | IFR-003 | **ProxyFix**-Middleware konfiguriert |
| `TestIFR005NetworkPort` | IFR-005 | App auf Port 5000 |
| `TestSEC001APIKeyProtection` | SEC-001 | API-Key **nicht** in Responses; kommt aus Env |
| `TestSEC003InputValidation` | SEC-003 | ungültige Rotation abgelehnt (400); valide akzeptiert |
| `TestPER001ProcessingThroughput` | PER-001 | Floyd-/Atkinson-Durchsatz (Timing-Grenze) |
| `TestPER002ConcurrentRequests` | PER-002 | Flask verarbeitung sequentieller Requests |
| `TestPER003ConfigReloadLatency` | PER-003 | Config-Reload < 2 s |

### `tests/test_providers.py` → **Provider-Abstraktion** (FR-027…FR-031)
| Klasse | Prüft |
|--------|-------|
| `TestPromptVariables` | `resolve_prompt_variables`: `{time_of_day}`, `{weather}`, `{season}`, mehrere, keine, `{random_element}` variiert |
| `TestGenerationTracker` | Anfangs-0, `log`, mehrere, `last_generation`, **Persistenz** (File), **Daily-Reset** |
| `TestImmichProvider` | Health (ok/fail), Name, `config_summary`, `fetch_image` |
| `TestComfyUIHAProvider` | Health (ok/fail), Name, `fetch_image` success, **Rate-Limiting**, HA-Service-Error, summary |
| `TestComfyUIDirectProvider` | Health (ok/fail), Name, **Default-Workflow**, random-seed |
| `TestProviderFactory` | `create_immich`/`comfyui_ha`/`comfyui_direct`; **unknown → ValueError** |
| `TestMultiSourceIntegration` | `/health` zeigt Quelle; `/api/generation-status` (Immich = Nullwerte); Settings zeigt `image_source` |

> **Coverage-Grob:** ~**104** Testmethoden (funktionell + non-funktional + Provider) über die
> 53 Requirements; die meisten FR/IFR/SEC/PER haben **mind. einen** automatisierten Fall. Was **nicht**
> automatisiert ist, steht in der ASPICE-Spezifikation als *manuell* (z. B. echte HA-/ComfyUI-Integration,
> ARM-Performance, EPD-Wear) und gehört in das Feld-Handbuch, nicht in `pytest`.

---

## 4. Bekannte Grenzen der Suite (honest read)

1. **Versionsscherbe im Report (wichtig):** `docs/test_report_aspice.md` = **v1.1.0 / 93 Tests / 100 % /
   14,75 s** und basiert auf der **v1.0.4-Baseline**. Code & Specs sind **v2.0.0** (31 FR, voller
   Provider-Modul). Die Report-Zahlen beschreiben therefore **nicht** den aktuellen Stand — vor einem
   Release `run.test.sh` neu fahren und den Report aktualisieren (s. [`ANALYSE.md`](ANALYSE.md) §14.6).
2. **Echte Netzwerk-Backends sind nicht abgedeckt** (by design): Ein echter Immich-/HA-/ComfyUI-Lauf
   (z. B. gegen eine Live-Immich mit *v3-API*) ist ein separates Manuell-/Integrationstier. Genau *dort*
   würde die **legacy-Immich-Endpoint-Frage** (ANALYSE §14.3) sichtbar — die Offline-Suite kann sie
   prinzipiell **nicht** falsifizieren (der Mock liefert, was ihm beigebracht wurde).
3. **Multi-Process/Concurrency** (gunicorn 2×2, mehrere Frames → eine Instanz) ist **nicht** simuliert
   (keine Dateisperren in `tracking.txt`/`generations.json`, ANALYSE §14.12).
4. **Cython-Import**: Wenn `cpy.so` im lokalen Build fehlt/scheitert, fallen die dithering-Tests aus —
   im **Docker-Image** wird es aber zuverlässig gebaut (daher dort als „Referenzlauf“ bevorzugen).

---

## 5. Definition of Done (Test-Pflicht vor Release)

Ein Release gilt als **testabgeschlossen**, wenn:
1. `docker run --rm epf-eink-tests:local /run.sh` → **Exit 0** (alle automatisierten Fälle grün);
2. **alle P0/`SEC`/`IFR`**-Cases grün (v. a. `SEC-001`, `IFR-001/002/003/005`, `NFR-003`);
3. `--junitxml` zeigt **keine** ungehandelten Tracebacks in Endpoint-Responses (korrespondiert zu
   `ANALYSE` §10 / `docs` N-Guard);
4. **Report** (`EPF-RPT-001`) ist auf den **aktuellen Code-Stand** (v2.x) neu generiert;
5. Doku-Fehler (7→6-Farben, §14.1) sind behoben oder zumindest gekennzeichnet.

---

## 6. Kurzer Hand-`curl`-Check (optional, gegen lokal laufende Instanz)

```bash
B=http://localhost:5000
curl -s  -D - -o /dev/null -H "batteryCap: 3950" $B/download | grep -E "HTTP|Content-|frame.txt"
curl -s  $B/health
curl -s  $B/api/battery-status
curl -s  $B/api/generation-status
curl -s  $B/preview-status
curl -s  -X POST $B/prepare-photo
curl -s  $B/sleep
curl -s  -X POST $B/cleanup-previews
```

> (Im Ingress-Kontext: gleiche Pfade unter `http://<ha>/api/hassio_ingress/<addon>/…`, authentifiziert
> über die HA-Session.)
