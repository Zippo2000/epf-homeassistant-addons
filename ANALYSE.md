# EPF Home Assistant Add-ons – Vollständige Projektanalyse

> **Repo:** [`Zippo2000/epf-homeassistant-addons`](https://github.com/Zippo2000/epf-homeassistant-addons) ·
> **Add-on:** `epf-eink-addon` (v2.0.0) · **Lizenz:** MIT ·
> **Status laut Changelog:** Multi-Source (Immich / ComfyUI via HA / ComfyUI Direct), ASPICE-dokumentiert
> **Relation:** HA-Ableger des standalone-Servers [`Zippo2000/EPF`](https://github.com/Zippo2000/EPF) (der wiederum
> auf jwchen119s FireBeetle-Rahmen-Projekt fußt). Die **Firmware** lebt **nicht** hier, sondern in `Zippo2000/EPF/Arduino`.

---

## 0. Inhaltsverzeichnis

1. [Zweck & Idee](#1-zweck--idee)
2. [Gesamtsystem-Architektur](#2-gesamtsystem-architektur)
3. [Repo-Struktur im Detail](#3-repo-struktur-im-detail)
4. [Home-Assistant-Deployment & Launch](#4-home-assistant-deployment--launch)
5. [`app.py` im Detail](#5-apppy-im-detail)
6. [`providers.py` im Detail (das Herzstück v2)](#6-providerspy-im-detail-das-herzstück-v2)
7. [Cython-Modul `cpy.pyx`](#7-cython-modul-cpyx)
8. [Web-UI `templates/settings.html`](#8-web-ui-templatessettingshtml)
9. [Ende-zu-Ende-Workflows](#9-ende-zu-ende-workflows)
10. [HTTP-Vertrag (Endpoint-Katalog)](#10-http-vertrag-endpoint-katalog)
11. [Konfiguration (zweikanalig)](#11-konfiguration-zweikanalig)
12. [Test- & Dokumentations-System](#12-test--dokumentations-system)
13. [Abgrenzung gegenüber `Zippo2000/EPF`](#13-abgrenzung-gegenüber-zippoo2000epf)
14. [Bemerkungen, Schwachstellen & offene Punkte](#14-bemerkungen-schwachstellen--offene-punkte)
15. [Fazit & Empfehlungen](#15-fazit--empfehlungen)

---

## 1. Zweck & Idee

**EPF** ist ein **akkugestützter E-Paper-Fotorahmen**. Das *Gehirn* ist ein **Flask-Server**, der im
Repo als **Home-Assistant-Add-on** (`epf-eink-addon`) ausgeliefert wird. Anders als beim
standalone-`EPF`, das als freies Docker-Container läuft, lebt dieser Server **in der Supervision des
HA-Supervisors**, bekommt seine **Options als Env-Variablen** (via `bashio`) und seine **Web-UI
eingebettet** (via **Ingress**).

Der zentrale Designgedanke bleibt identisch zum Ursprung — **Trennung von Berechnung und Anzeige**:

* **Schwere Arbeit** (Bilder holen, skalieren/rotieren, Farb-/Kontrast-Korrektur, **Dithering**,
  Packen in Panel-Bytes) läuft **komplett serverseitig** (x86/ARM, Docker) — das Dithering in
  **Cython**.
* Der **ESP32** (FireBeetle ESP32-E + Waveshare 7,3″ Spectra-6, 800×480, **6 Farben**) ist 99 % im
  **Deep-Sleep** (~µA), wacht per RTC/Taster auf, ruft ein fertiges Bild + die Schlafdauer ab,
  schreibt ins Panel und schläft wieder. **Keine Bildbearbeitung am Gerät, keine Credentials.**

**Der v2-Schub (2026-04):** Das Bild hat jetzt **drei mögliche Quellen** hinter einer
**Provider-Abstraction** — statt nur Immich:

1. **Immich** (Bibliothek; Album, `random`/`newest`, Original-Download),
2. **ComfyUI via Home Assistant** (`ai_task.generate_image`-Service, Prompt-Templates, **tagesweises
   Generations-Limit**),
3. **ComfyUI Direct** (direkte ComfyUI-API, eigene Workflow-JSON, *Expert Mode*).

Dazu: **`/health`** (quellen-unabhängig), **Prepare/Deliver-Entkopplung** (Foto vorher vorbereiten,
später liefern), **Preview-Galerie**, **Dark Mode**, **CSP-Härtung** und ein **ASPICE-Doku- &
Test-Paket** (31 FR + 10 NFR + 5 IFR + 4 SEC + 3 PER; ~104 vollständig gemoockte Pytest-Fälle).

**Ergebnis:** Frame-Refresh im Sekundenbereich, minimale Geräte-Leistung, und — neu — die Möglichkeit,
den Rahmen mit **KI-generierten Bildern** zu betreiben, die sich per Prompt-Vorlage an
Uhrzeit/Jahreszeit/„Wetter“ anpassen lassen und durch ein Tageslimit vor GPU-Überlastung geschützt sind.

---

## 2. Gesamtsystem-Architektur

```
┌──────────────────────────────── HOME ASSISTANT (Supervisor) ────────────────────────────────┐
│  ┌────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │  epf-eink-addon  (supervised Container, gunicorn :5000, Ingress + Raw-Port)            │ │
│  │                                                                                            │ │
│  │    ┌───────────────┐    ┌───────────────────┐    ┌──────────────────────────────┐      │ │
│  │    │  ImageProvider  ├──►│  Bild-Pipeline     │──►│  Web-UI / (Ingress)            │      │ │
│  │    │  ├ Immich       │   │  scale+rotate(C)   │   │  Health · Batterie · Foto-Status │      │ │
│  │    │  ├ ComfyUI-HA   │   │  enhance(C)+dither │   │  Prepare/Cleanup/Galerie         │      │ │
│  │    │  └ ComfyUI-Direkt│  │  pack 2×4bit→Hex   │   └──────────────────────────────┘      │ │
│  │    └────────┬────────┘   └───────────────────┘                                          │ │
│  │             │ (x-api-key)      (Bearer Token)        (Direct /prompt+/history)             │ │
└────────────────┼──────────────────────────┼────────────────────────────────┼────────────────┘
                 ▼                            ▼                                ▼
          Immich-Server                Home Assistant (ai_task)           ComfyUI-Server
                 │                        (GPU/Stable-Diffusion)           (Stable Diffusion)
                 │
                 │   LAN HTTP (vertrautes Netz, unauthentifiziert)
                 ▼
   ESP32-Rahmen (sibling Repo):  RTC/Taster-Weck → /download → Panel → /sleep → Deep-Sleep
```

**Rollen** (Detail in [`ARCHITECTURE.md`](ARCHITECTURE.md)):

* **Immich** — Bildarchiv; der `ImmichProvider` ist sein Client.
* **Home Assistant** — (a) Supervisor (Options→Env, Ingress, gunicorn-Aufruf) und (b) KI-Gateway
  (`ai_task.generate_image`) für den *ComfyUI-HA*-Pfad.
* **ComfyUI (direkt)** — optionales, direktes SD-Backend im Expertenmodus.
* **Add-on-Server (dieses Repo)** — das Gehirn; **eine** aktive Provider-Instanz; besitzt
  Schlafplanung, Batterie, Health, Galerie, Konfig.
* **ESP32** — dünner HTTP-Client + Panel-Treiber (Firmware im Schwester-Repo).

---

## 3. Repo-Struktur im Detail

| Pfad | Typ | Zweck |
|------|-----|-------|
| `repository.yaml` | YAML | **MAKt das Repo zu einem HA-Add-on-Store** (`name`/`url`/`maintainer`). Pflicht für das Add-on-Store-Install. |
| `LICENSE` | — | MIT. |
| `.gitignore` | Git | Ignoriert `.env`, `config/`, `photos/`, `tracking.txt`, `test-results.xml`, … **aber** *whitelistet* (`!`) das Add-on-Manifest `config.yaml` **und** (redundant) `cpy.so`. Siehe §14.5/14.11. |
| `docs/architecture_document.md` | MD | **ASPICE SYS.3/SWE.2**: Komponenten `C-001…C-018`, Design-Entscheidungen `D-001…`, Interfaces, Datenfluss, Deployment. |
| `docs/requirements_specification_aspice.md` | MD | **ASPICE SWE.1/SYS.2** (EPF-REQ-001): 31 FR, 10 NFR, 5 IFR, 4 SEC, 3 PER (mit Traceability). |
| `docs/test_specification_aspice.md` | MD | **ASPICE SWE.4/5** (EPF-TST-001): je Requirement ein Testfall, Traceability-Matrix. |
| `docs/test_report_aspice.md` | MD | **ASPICE SWE.6** (EPF-RPT-001): letzter Volllauf (⚠ v1.1.0/93 Tests — **veraltet**, s. §14.6). |
| `epf-eink-addon/config.yaml` | YAML | **ADD-ON-MANIFEST**: `name`, `version: 2.0.0`, `slug`, `arch[]`, `ports` (5000), `ingress: true`, `ingress_port`, `panel_icon`, `webui`, `options{}`, `schema{}`. Definiert die **HA-Config-UI**. |
| `epf-eink-addon/build.yaml` | YAML | **Basis-Images pro Arch** (`ghcr.io/home-assistant/<arch>-base-debian:bookworm`). Die Python-basierten Varianten sind auskommentiert. |
| `epf-eink-addon/Dockerfile` | Docker | **Prod-Image**: py3.11 + Pillow-Hebel-libs + `libraw`, **kompiliert `cpy.so`** (`setup.py build_ext`), COPY `app.py`/`providers.py`/`templates/`, COPY `run.sh`, **HEALTHCHECK→`/health`**, `EXPOSE 5000`, LABELs `io.hass.*`. |
| `epf-eink-addon/Dockerfile.test` | Docker | **Test-Image**: dito + `fonts-dejavu-core` + `tests/`; `run.test.sh` als `CMD`. |
| `epf-eink-addon/app.py` (≈1036 Z.) | Python | Flask-App (modular, Blueprint): Config-Handling + Watcher, Provider-Lebenszyklus, Bildpipeline, **Batterie**, `/sleep`, `/health`, `/prepare-photo`, Previews/Galerie, **NTP-Thread**. |
| `epf-eink-addon/providers.py` (≈724 Z.) | Python | **Herzstück v2**: `ImageProvider` (ABC) + `ImmichProvider`/`ComfyUIHAProvider`/`ComfyUIDirectProvider` + `create_provider()` (Factory) + `GenerationTracker` + `resolve_prompt_variables()`. |
| `epf-eink-addon/cpy.pyx` (≈235 Z.) | Cython | `load_scaled`, `convert_image` (Floyd–Steinberg), `convert_image_atkinson`; 6-Farben-Palette; `nogil`-Helpers. |
| `epf-eink-addon/cpy.so` (1,2 MB) | ELF | **Commit-Erbe** vom Basisprojekt; wird **vom Docker-Build NICHT benutzt** (dort neu kompiliert). Siehe §14.5. |
| `epf-eink-addon/setup.py` | Python | `cythonize("cpy.pyx")` (numpy-Include, `language_level=3`) → für den Build. |
| `epf-eink-addon/requirements.txt` | — | Gepinnt: Flask 3.0.3, Werkzeug 3.0.4, Pillow 10.4, pillow-heif 0.18, numpy 1.24, **Cython 3.0.10**, rawpy 0.21, requests 2.32, PyYAML 6.0, watchdog 6.0, ntplib, **gunicorn 23**, python-dotenv, **pytest 7.4.3 + responses 0.24.1**. |
| `epf-eink-addon/run.sh` | bashio | `#!/usr/bin/with-contenv bashio`: liest alle `options` via `bashio::config`, **exportiert sie als Env**, **validiert `IMMICH_API_KEY`+`IMMICH_URL`** (sonst fatal), setzt `INGRESS_PATH`, **startet gunicorn 2×2 auf :5000**. |
| `epf-eink-addon/run.test.sh` | bash | `pytest tests/ -v --junitxml=…` im Test-Image. |
| `epf-eink-addon/templates/settings.html` (≈1209 Z.) | HTML/JS | Die Web-UI (Jinja + Inline-CSS/JS). |
| `epf-eink-addon/tests/*` | Python | 4 Dateien (conftest + 3) → ~104 gemoockte Fälle, strukturiert nach ASPICE-IDs. |

---

## 4. Home-Assistant-Deployment & Launch

Der Unterschied zum standalone-EPF ist hier am größten:

* **Supervision:** Das Add-on läuft als **HA-supervised Docker-Container**. `build.yaml` wählt pro
  Zielarch die passende `*-base-debian:bookworm`-Basis (armhf/armv7/aarch64/amd64/i386).
  `config.yaml` trage `startup: application`, `boot: auto`, `ports: 5000/tcp:5000`, `ingress: true`.
* **`bashio` als Config-Brücke:** `run.sh` ist ein `with-contenv bashio`-Skript. Es ruft für jede
  Option `bashio::config '<name>' [<default>]` auf und **exportiert sie als Umgebungsvariable**
  (`image_source`→`IMAGE_SOURCE`, `immich_api_key`→`IMMICH_API_KEY`, `album_name`→`ALBUM_NAME`,
  `ha_api_token`→`HA_API_TOKEN`, `comfyui_entity_id`→`COMFYUI_ENTITY_ID`, …). Diese Env-Varianlen
  säen `DEFAULT_CONFIG` in `app.py` beim Import. **Secrets kommen ausschließlich so rein.**
* **Ingress:** `config.yaml` deklariert `ingress: true`, `ingress_port: 5000`, `panel_icon:
  mdi:image-frame`, `webui: http://[HOST]:[PORT:5000]`. `run.sh` setzt `INGRESS_PATH=/api/hassio_ingress`.
  `app.py` installiert `werkzeug` **`ProxyFix(x_for=1, x_proto=1, x_host=1, x_prefix=1)`**, damit UI
  & Links hinter dem HA-Reverse-Proxy (inkl. HTTPS) korrekt funktionieren. → Das UI ist **zweimal**
  erreichbar: als **HA-Panel** (Ingress) *und* über den **rohen Port 5000**.
* **gunicorn statt Dev-Server:** `run.sh` beendet mit `exec gunicorn --bind 0.0.0.0:5000 --workers 2
  --threads 2 --timeout 120 app:app`. Der `if __name__=='__main__'`-Zweig in `app.py` (Flask `app.run`)
  ist nur noch für manuelle/Debug-Läufe da. **2 Workers × 2 Threads** ⇒ bis zu 4 parallele Requests
  (der standalone-EPF lief single-threaded — das ist ein echter Gewin).
* **HEALTHCHECK:** Der Docker-`HEALTHCHECK` (30 s / 10 s / 60 s-Start / 3 Versuche) probt
  `GET /health`, der **aktiven Provider** anpingt → `503`, wenn die Quelle nicht erreichbar ist.
  (Trade-off s. §14.12: ein down-gelaufenes Immich markiert den *Container* unhealthy.)
* **`config.yaml` = Manifest, NICHT die Laufzeit-Config:** Der Name kollisioniert bewusst. Das
  *Manifest* (`epf-eink-addon/config.yaml`) definiert `options`/`schema`; die *Laufzeit*-Config ist
  `config/config.yaml` (Bind-Mount, von der Web-UI geschrieben). `.gitignore` whitelistet das
  Manifest (`!epf-eink-addon/config.yaml`) und ignoriert ein nacktes `config.yaml` — beides bewusst.

---

## 5. `app.py` im Detail

### 5.1 Imports & Cython-Verfügbarkeit
* `from __future__ import annotations` + extensive Typ-Hinweise (NFR-009).
* Der **Cython-Import ist defensive**: `import cpy` in `try/except ImportError`. Es werden
  `load_scaled`, sowie `convert_image` (Floyd) und `convert_image_atkinson` als wrapper mit
  Verfügbarkeits-Flags (`FLOYD_AVAILABLE`, `ATKINSON_AVAILABLE`, `CYTHON_AVAILABLE`) exponiert.
  `scale_img_in_memory` **wirft `RuntimeError`**, wenn Cython fehlt (kein stummer Fallback).

### 5.2 Konfiguration (Zweiquellen)
* **`DEFAULT_CONFIG`** = `{'image_source': …, 'immich': {…}, 'comfyui': {…}}`, wo **jeder Wert aus
  `os.getenv(...)`** mit sinnvollem Fallback gesäte wird (`IMMICH_URL`, `ALBUM_NAME`, `ROTATION_ANGLE`,
  `COLOR_ENHANCE`(Default **1,8**), `CONTRAST`, `DITHERING_STRENGTH`, `DISPLAY_MODE`, `IMAGE_ORDER`,
  `DITHERING_METHOD`, `SLEEP_*`, `WAKEUP_INTERVAL`(Default **1440**), ComfyUI-Felder…).
* **Module-Globalen** spiegeln die aktiven Werte (`url`, `album_name`, `rotation_angle`, …,
  `dithering_method`, `image_source`) — das ist der „mutable config“-Zustand.
* **`config/config.yaml`** (Pfad via `CONFIG_PATH`, Default `config/config.yaml`) = **Laufzeit**-Quelle.
  `ConfigFileHandler` (watchdog) **legt die Datei an** (mit Defaults), **lädt sie beim Start** und
  **hot-reloaded sie bei Änderung** → `update_app_config(new)` setzt alle Globalen + **`reset_provider()`**.
* **`update_app_config`** ist der einzige Pfad, der Globalen + Provider synchron hält.

### 5.3 Provider-Lebenszyklus
* `active_provider` (singleton-artig); `get_active_provider()` erzeugt bei `None` den Provider per
  `create_provider(current_config, photo_dir)`; `reset_provider()` **erzeugt ihn neu** (wird bei jedem
  Config-Wechsel gerufen). → Ein **Provider-Wechsel** (Immich→ComfyUI) ist also ein **Config-Wechsel +
  (impliziter) Rebuild**, nicht ein Laufzeit-Flip.

### 5.4 Batterie
* `last_battery_voltage` / `last_battery_update` werden bei jedem `/download`-Request aus dem
  `batteryCap`-Header gespeißt (mV). `calculate_battery_percentage()` interpoliert **stücklinear** über
  die Tabelle `BATTERY_LEVELS` (4200 mV→100 % … 3400 mV→0 %). **Kein 1-h-Timeout mehr** (gegenüber dem
  Basis-EPF): der letzte Stand bleibt, bekommt aber ein **Zeitstempel** (v1.0.3).

### 5.5 Palette & Hex-Format
* `palette` = 6 RGB-Tupel (schwarz/weiß/helles gelb `(255,243,56)`/dunkelrot `(191,0,0)`/
  blau-violett `(100,64,255)`/grün `(67,138,28)`) — **Waveshare-E6-Annäherung**.
* `depalette_image(pixels, pal)`: vektorisierte **euklidische** Abstandsmatrix (NeP-50-Hebel beachten),
  `argmin`, dann **`indices[indices>3] += 1`** (Slots 4,5→5,6; Slot 4 = Waveshare-`RED` wird dabei **nie
  ausgegeben** — bewusste Erbe-Quirk aus dem Basisprojekt, s. §14).
* `convert_to_hex_format`: `np.array` → Indizes → **pro Byte 2×4-Bit** packen (linke Pixel im oberen
  Nibble) → **2-stellige Hex-Zahlen, kommagetrennt, Zeilenumbruch alle 16, kein abschließendes `};`**
  (im Basis-EPF vorhanden → hier weggelassen, um den Firmware-`0x00`-Artefakt zu vermeiden). Ausgabe-
  Dateiname: **`frame.txt`** (war `.c`).

### 5.6 Bildpipeline (`scale_img_in_memory`)
1. EXIF-Datum lesen (Tag 36867 / Fallback 306);
2. `ImageOps.exif_transpose` (korrekte Orientierung);
3. **`load_scaled` (Cython)** → exakt 800×480 (`fit`=Letterbox weiß, `fill`=Center-Crop);
4. `ImageEnhance.Color(·).enhance(img_enhanced)` + `ImageEnhance.Contrast(·).enhance(img_contrast)`;
5. **Dithering (Cython)** je nach `dithering_method` (`atkinson` Default, sonst `floyd-steinberg`;
   Fallback-Logik + `RuntimeError` wenn gar keins da);
6. **Datum-Overlay** (v2 **aktiv**): untere-rechte Ecke, schwarzer Balken, weißer Text, Font
   `DejaVuSans-Bold` (⚠ fehlt im Prod-Image → `load_default`, s. §14.7), **nach** dem Dithering;
7. **Preview** `latest_preview.jpg` (quality 85) speichern.

### 5.7 Previews & Prepare/Deliver
* `save_three_previews(orig)`: `latest_original.jpg` (Thumbnail ≤800×480, q95), `latest_processed.jpg`
  (das pipeline-Output, q95), `latest.bmp` (BMP fürs ESP32). 
* **`/prepare-photo` (POST)**: `provider.fetch_image()` → `save_three_previews` → `latest.status`
  **`new`**. Das Bild ist damit **„bereit zur Lieferung“, aber noch nicht an das Gerät gesandt**.
* **`/download`**: wenn `latest.status == "new"` → `latest.bmp` lesen, `convert_to_hex_format`,
  Status→`"delivered"` liefern (günstig: kein erneutes Fetch). Andernfalls **on-the-fly**
  (fetch+pipeline+Previews, Status `delivered`). In beiden Fällen `copy2(processed→delivered)` fürs
  UI. **Das ist die v2-„Prepare/Deliver“-Entkopplung** (Design-Entscheidung D-003).
* **`/cleanup-previews`**: `cleanup_old_previews()` — **doppelte Eviction**: (a) älter als 7 Tage;
  (b) > 50 Dateien pro Muster → älteste weg; schützt aktuelle Previews. (v1.0.4)

### 5.8 Routes (Kurzform — vgl. §10)
`/` (UI+Save), `/health`, `/download`, `/prepare-photo`, `/preview-*` (5), `/api/battery-status`,
`/api/generation-status`, `/sleep`, `/cleanup-previews`, `/api/gallery-previews`, `/preview-file/<f>`.

### 5.9 Schlaf & NTP
* **`/sleep`**: `calculate_next_interval_time` (Round-up aufs `wakeup_interval`-Raster, 24h-Wrap),
  **Schlafzeitfenster** (`sleep_start…sleep_end`, Mitternacht-Überspannung korrigiert) → falls das
  nächste Wake in’s Fenster fällt → auf `sleep_end`; falls < 10 min → übernächster Slot. → ms +
  `current_time`/`next_wakeup`.
* **NTP-Thread**: Daemon-Thread, schläft bis **täglich 04:00**, `ntplib`→`pool.ntp.org`, Retry 1 h.
  **Graceful Shutdown** via `_ntp_stop_event` (v1.0.4): `stop_ntp_sync()` + `join` im `finally`.
  (Wie im Basis-EPF: **liest nur**, setzt die Systemuhr **nicht** — Doku-Behauptung „korrigiert die
  Uhr“ trifft faktisch nicht zu; die Host-Uhr/Zoné muss stimmen.)

---

## 6. `providers.py` im Detail (das Herzstück v2)

Ein gemeinsames **ABC `ImageProvider`** mit 4 abstrakten Methoden:
`fetch_image() -> (PILImage, source_id)`, `health_check() -> bool`, `get_source_name()`,
`get_config_summary()`. Drei konkrete Implementationen + **Factory** + zwei Hilfs-Komponenten.

### 6.1 `ImmichProvider`
* **Auflösung:** `GET /api/albums` → Match auf `item['albumName']` → `id`.
* **Assets:** `GET /api/albums/{id}` → `album_data['assets']`. **⚠ Legacy-Endpunkt** (Basis-EPF
  nutzt seit v3 das paginierte `POST /api/search/metadata`).
* **Selection:** `newest` → absteigend nach `exifInfo.dateTimeOriginal` (Fallback `1970…`),
  nur *unseen*; leer → **Tracking-Reset** + Vollmenge. `random` → `random.choice` der *unseen*.
* **Tracking:** eigenes `tracking.txt` (Album-Name Zeile 1 + IDs), `os.chmod 0o666` (HA-Write-Access).
* **Download + Decode:** `/api/assets/{id}/original` (stream) → RAW/DNG/… per `rawpy.postprocess`,
  HEIC per `pillow_heif`, sonst PIL.
* **Health:** `GET /api/server/ping`.

### 6.2 `ComfyUIHAProvider`
* Auth: `Authorization: Bearer <HA_API_TOKEN>`; Header/`entity_id` aus Env (`COMFYUI_ENTITY_ID`).
* **Rate-Limit:** `tracker.get_count_today() >= max_generations_per_day` → `RuntimeError`.
* **Prompt:** `resolve_prompt_variables(self.prompt)` (s. §6.5) → `instructions`.
* **Call:** `POST {ha_url}/api/services/ai_task/generate_image?return_response=true`
  Body `{"task_name":"Image","instructions":…,"entity_id":…}`, **Timeout 180 s**.
* **Extraktion** (defensiv, mehrere Shapes): `service_response.url` (relativ → `ha_url`-Prefix) →
  Download; `service_response.media_source_id` → expliziter Fehler „direct URL not available“;
  `image_data` (Base64/`data:` URI); Top-Level-`url`; `images[0]`.
* **Health:** `GET {ha_url}/api/` (200/404 OK).

### 6.3 `ComfyUIDirectProvider`
* **Workflow:** eigene `workflow_json` parsen und **Prompt/Seed/Width/Height in** `CLIPTextEncode`/
  `KSampler`-Inputs injizieren; **Default** = SD-1.5-`KSampler`-Graph (`CheckpointLoaderSimple`,
  `EmptyLatentImage`, 2×`CLIPTextEncode`, `VAEDecode`, `SaveImage`, 20 Steps, cfg 8, euler).
* **Call:** `POST {url}/prompt` `{"prompt":…,"client_id":"epf_<ts>"}` → `prompt_id`;
  **Poll** `GET /history/{prompt_id}` alle 2 s (≤300 s) bis `outputs.*.images[0].filename`;
  `GET /view?filename=&type=output` → Bild.
* **Health:** `GET /system_stats`.

### 6.4 Factory `create_provider(config, photo_dir)`
* `image_source == 'immich'` → `ImmichProvider`; `comfyui_ha` → `ComfyUIHAProvider`;
  `comfyui_direct` → `ComfyUIDirectProvider`; sonst `ValueError`. Secrets (`IMMICH_API_KEY`,
  `HA_API_TOKEN`, `COMFYUI_ENTITY_ID`) werden **hier** aus Env geholt.

### 6.5 `resolve_prompt_variables` (v2-Neuigkeit FR-030)
* **Template-Variablen** → kontextbewusst aufgelöst: `{time_of_day}` (stündliches Map, z. B. 17 h→
  `golden hour`), `{weather}` (**zufällig** aus sunny/cloudy/misty/…), `{season}` (Monat→Jahreszeit),
  `{day_of_week}`, `{month}` (ISO-Names), `{random_element}` (zufällig aus Time-of-Day-Liste).
  Alle bekannten Variablen + generische `PROMPT_VARIABLES` werden ersetzt; unbekannter Text bleibt.

### 6.6 `GenerationTracker` (v2-Neuigkeit)
* Persistiert `generations.json` (Liste von `{timestamp, prompt[≤200], seed, source}`);
  `get_count_today()`, `get_last_generation()`, `reset_daily_count()`. **Dient dem Tages-Limit**
  beider ComfyUI-Pfade und dem `/api/generation-status`.

---

## 7. Cython-Modul `cpy.pyx`

* Flags: `language_level=3`, `boundscheck/wraparound/nonecheck=False`, `cimport numpy`, `nogil`-Helpers.
  Konstanten `EPD_W=800`, `EPD_H=480`.
* **`load_scaled(image, angle, display_mode)`**: RGB → `rotate(angle, expand=True)`;
  `fill` → Cover + **Center-Crop** auf 800×480; `fit` → **Contain** (Letterbox) auf weißem 800×480.
* **`convert_image`** (Floyd–Steinberg, *aktiv wählbar*): 6-Farben-`epd_colors` (normalisiert),
  nearest-color (quadratische Distanz) + Fehlerdiffusion 7/16, 3/16, 5/16, 1/16 × `dithering_strength`.
* **`convert_image_atkinson`** (*Default*): gleiche Palette; nearest-color + **Atkinson** zu **6
  Nachbarn** (recht, 2×recht, links-unten, unten, rechts-unten, 2 Zeilen unten) je **1/8**,
  gesamt × `dithering_strength * 0.75`.
* Ergebnis ist immer **`np.ndarray (480,800,3)`** mit exakt den 6 Palette-Farben (keine Zwischenstufen);
  `preview_path` ist No-Op.
* **Palette-Dualität** (wichtig): `cpy.pyx` dithert gegen **reine** Farben
  (`[0,0,0],[1,1,1],[1,0.953,0.220],[0.749,0,0],[0.392,0.251,1],[0.263,0.541,0.110]`),
  `app.py::depalette_image` mappt das Ergebnis aber gegen die **annähernden** Waveshare-`palette`-
  RGBs → **zwei logisch verschiedene Paletten in zwei Phasen** (Basis-EPF-Charakter, deterministisch
  aber fragil — s. §14.9).

---

## 8. Web-UI `templates/settings.html`

Eine **einzige, selbstdenkende Seite** (Inline-`<style>`/`<script>`, Jinja-Server-Render):

* **Header:** Titel, **Bildquellen-Indikator** (Label mit Quellenname, z. B. `Immich online`/
  `Immich unreachable`, + grüner/roter Dot; `./health` per **GET** — das JSON-Feld `source` wird
  im UI ausgegeben, 60 s; seit 2.0.3, vgl. `plans/findings.md`), **Batterie**
  (%, V, Zeitstempel; `./api/battery-status`, 30 s), **Theme-Toggle** (Dark/Light, in `localStorage`).
* **Photo-Panel:** Vorschau des aktuellen Frames, **Status-Badge** („Ready to deliver“/„Already
  delivered“, `./preview-status`, 10 s), Buttons **Prepare New Photo** (`POST /prepare-photo`),
  **Cleanup Previews** (`POST /cleanup-previews`), **Gallery** (Modal).
* **Gallery-Modal:** `GET /api/gallery-previews` → Raster aus `latest_{original,processed,delivered}_*.jpg`;
  Klick öffnet original in neuem Tab.
* **Config (einklappbar):** Karten je nach `image_source` (`immich` / `comfyui_ha` / `comfyui_direct`),
  Sliders (color-enhance **max 3,0** — mit Schema abgestimmt, contrast, strength), Rotation, Display-Mode,
  Bildreihenfolge, Dithering-Methode, Schlaffenster (h/min), Wake-Intervall.
* **Submit:** **Fetch-POST** an `/` (kein Reload) → Success-/Error-Toast; **Reset-to-Default** setzt
  *Client-seitig* alle Felder (Immich/`http://localhost`/`eink`/ComfyUI-Empty/…) + „Click Save to apply“.
* **Sicherheit:** **CSP** (`default-src 'self'`, inline styles/scripts erlaubt), **Referrer-Policy**
  `strict-origin-when-cross-origin`, `safeGet()`-Helper gegen Null-DOM-Access, **named Constants**
  `POLL_INTERVALS = {HEALTH:60000, PHOTO_STATUS:10000, BATTERY:30000}` + `NOTIFICATION_DURATION`.
* **Bedingtes Polling:** Intervalle starten erst **nach dem ersten erfolgreichen Laden** (kein Lese-
  Spam, wenn gar kein Bild da ist).

> **UI ≠ Secret-Editor:** Das Formular enthält **bewusst kein** Feld für API-Keys/HA-Token — die
> Secrets sind reine **Add-on-Options** (Env). Die UI pflegt nur Nicht-Secrets.

---

## 9. Ende-zu-Ende-Workflows

### 9.1 Immich-Refresh (Standard, passiv)
```
[Deep-Sleep, µA] ─RTC/Taster→
  GET /sleep → in-Fenster? ja: hibernate(ms) | nein: weiter
  GET /download (Header batteryCap:mV)
     status=="new"?  → latest.bmp → hex, Status→"delivered"
     sonst:          ImmichProvider.fetch() (album→assets→select→original→decode)
                     → save_three_previews (orig/proc/BMP) → Status "delivered" → hex
  → Panel schreiben → TurnOnDisplay → hibernate(/sleep.ms)
```

### 9.2 Manueller Prepare (aktiver „next photo now“)
```
UI: "Prepare New Photo" → POST /prepare-photo
   → fetch+pipeline+3 Previews → Status "new"  (Bild sichtbar im UI)
ESP32 wacht später → GET /download → findet "new" → liefert, "delivered"
```
→ **Decouple:** Das Bild kann *vor* dem Device-Weck vorbereitet und *nach* geliefet werden
(z. B. manuell per Touch), ohne erneutes Fetch — und bleibt als Preview/Galerie-Eintrag liegen.

### 9.3 ComfyUI-Generierung (KI)
```
fetch_image() (ComfyUIHAProvider/Direct):
   count_today >= cap? → RuntimeError ("Daily generation limit reached")
   prompt = resolve_prompt_variables(prompt)
   seed = fixed oder random
   [HA]  POST ai_task.generate_image?return_response → service_response.url → download
   [Direkt] POST /prompt → poll /history → /view
   → decode → GenerationTracker.log()
→ weiter wie 9.1 (Pipeline + Previews + Hex)
```

### 9.4 Config-Wechsel (Hot-Reload)
```
UI POST /  →  config.yaml schreiben  +  update_app_config(new)   [sofort]
           └  ConfigFileHandler.on_modified  →  load_config()  →  update_app_config(new)
update_app_config: setze Globalen → reset_provider() (neuer ImageProvider) → Log
```
Beide Wege (UI-POST **und** Datei-Änderung) münden in `update_app_config`; **kein Restart** nötig.

---

## 10. HTTP-Vertrag (Endpoint-Katalog)

| Method | Pfad | Body / Response | Anmerkung |
|--------|------|-----------------|-----------|
| GET | `/` | rendert `settings.html` (Config + Batterie) | UI (Ingress + roher Port) |
| POST | `/` | Form-Fields → `config.yaml` + `update_app_config` → **302** | **validiert Rotation ∈ {0,90,180,270}** (sonst 400) |
| GET/HEAD | `/health` | `200/503` + `{status,timestamp,source,source_status}` | pingt **aktiven** Provider; Docker-Healthziel |
| GET | `/download` | **`text/plain`** (`frame.txt`), 2×4bit/Byte, Hex, 16/Zeile, **ohne** `};` | Header `batteryCap`; Pre/Deliver + On-the-fly |
| POST | `/prepare-photo` | `{success, message, source_id, source}` / 500 `{error,success:false}` | setzt Status `new` |
| GET | `/preview-photo` / `-original` / `-processed` / `-delivered` | JPEG / 404 | jeweilige Preview |
| GET | `/preview-status` | `{exists,status,timestamp,formatted_time}` | für Badge |
| GET | `/api/battery-status` | `{voltage, voltage_v, percentage, last_update, formatted_timestamp, age_seconds}` | |
| GET | `/api/generation-status` | `{source,count_today,max_per_day,last_generation}` (ComfyUI) bzw. Nullwerte (Immich) | |
| GET | `/api/gallery-previews` | `{files:[{name,url,modified,timestamp}]}` (newest first) | |
| GET | `/preview-file/<f>` | JPEG / 404 | `os.path.basename` gegen Directory-Traversal |
| POST | `/cleanup-previews` | `{success, files_removed, message}` / 500 | 7-Tage / 50-Count-Eviction |
| GET | `/sleep` | `{sleep_duration(ms), current_time, next_wakeup}` | **Zoné = Container-Uhr** (TZ-Option beachten) |

**Auth-Modell:** Die `x-api-key`/`Bearer`-Header werden **nur** serverseitig (Add-on→Immich/HA)
gesetzt. Der **ESP32 bringt keine Credentials** mit → **vertrautes LAN**-Modell (wie Basis-EPF).
Die Endpunkte selbst sind **unauthentifiziert** (über Ingress zumindest HA-session-geschützt, über
den rohen Port 5000 offen) — s. §14.11.

**Wire-Format (ESP32):** 800×480 → 192 000 Bytes → ~576 KB Text. Firmware parst Token-weise
(`strtol(…,16)`), 1 Byte pro `SendData`; **`};`-Trailer wurde gegenüber dem Basis-EPF entfernt**
(verhindert das_EXTRA_-`0x00`). Beide Firmware-Parser (mit/ohne `};`) funktionieren.

---

## 11. Konfiguration (zweikanalig)

### 11.1 Kanäle
| Kanal | Träger | Inhalte | Hot-Reload? |
|-------|--------|---------|-------------|
| **A. Add-on-Optionen → Env** | `config.yaml`-Manifest + `bashio::config` in `run.sh` | **Secrets** (`IMMICH_API_KEY`, `HA_API_TOKEN`, `COMFYUI_ENTITY_ID`) **+** Defaults (URLs, Prompt, Dimensions, Wake-Interval, …) | **nein** — nur beim (Re-)Start |
| **B. Laufzeit-YAML** | `config/config.yaml` (Bind-Mount) | **Photo/Display-Einstellungen** (Album, Rotation, Enhance, Contrast, Dither-Method, Display-Mode, Order, Sleep-Fenster) | **ja** (watchdog → `update_app_config` + Provider-Rebuild) |

**Regel:** *Secrets & Quell-Wahl ⇒ Add-on-Option ändern + (Re)Start.* · *Foto-Look ⇒ Web-UI (live).*

### 11.2 Optionen-Referenz (Auszug; vollständige Liste in `epf-eink-addon/README.md`)
| Option | Env | Schema (Validierung) | Default |
|--------|-----|----------------------|---------|
| `image_source` | `IMAGE_SOURCE` | `list(immich\|comfyui_ha\|comfyui_direct)` | `immich` |
| `immich_api_key` | `IMMICH_API_KEY` | `str` (**required** via `run.sh`) | — |
| `immich_url` | `IMMICH_URL` | `str` (**required** via `run.sh`) | — |
| `album_name` | `ALBUM_NAME` | `str` | `eink` |
| `ha_url` / `ha_api_token` | `HA_URL` / `HA_API_TOKEN` | `str?` / `str` | — / — |
| `comfyui_prompt` / `_negative_prompt` | `COMFYUI_PROMPT`/… | `str?` | Templates erlaubt |
| `comfyui_width`/`_height` | … | `int(256,2048)?` | 800 / 480 |
| `comfyui_seed` | `COMFYUI_SEED` | `int(0,999999999)?` | `-1` (random) |
| `comfyui_max_generations` | `COMFYUI_MAX_GENERATIONS` | `int(1,200)?` | 50 |
| `comfyui_entity_id` | `COMFYUI_ENTITY_ID` | `str?` | — |
| `comfyui_direct_url` / `comfyui_workflow_json` | … | `str?` | — |
| `rotation_angle` | `ROTATION_ANGLE` | `list(0\|90\|180\|270)` | 270 |
| `color_enhance` | `COLOR_ENHANCE` | `float(0,3)` | 1.8 |
| `contrast` | `CONTRAST` | `float(0,2)` | 0.9 |
| `dithering_strength` | `DITHERING_STRENGTH` | `float(0,1)` | 1.0 |
| `display_mode` | `DISPLAY_MODE` | `list(fit\|fill)` | fill |
| `image_order` | `IMAGE_ORDER` | `list(random\|newest)` | random |
| `dithering_method` | `DITHERING_METHOD` | `list(atkinson\|floyd-steinberg)` | atkinson |
| `wakeup_interval` | `WAKEUP_INTERVAL` | `int(30,1440)` | 1440 |
| `sleep_start_*`/`sleep_end_*` | … | `int(0,23)` / `int(0,59)` | 23:00 / 06:00 |
| `log_level` | `LOG_LEVEL` | `list(debug\|info\|warning\|error)` | info |

---

## 12. Test- & Dokumentations-System

* **Framework:** **pytest** (7.4.3) **komplett gemoockt** (kein Netz/Immich/ComfyUI nötig):
  `responses` (Immich-/HA-HTTP), `unittest.mock` (NTP, watchdog-Observer), `tmp_path` (Datei-System).
* **Test-Image:** `Dockerfile.test` (Debian bookworm + `fonts-dejavu-core` + `tests/`), `CMD =
  run.test.sh` → `pytest tests/ -v --junitxml=…`. (→ **Doku: `TESTSPEC.md`**.)
* **`conftest.py`**: Kern-Fixture **`app_module`** (Env-setzen, NTP/watchdog patchen, **frischer
  Import** via `del sys.modules['app']`, `photo_dir`/`config_path`/`tracking_file` nach `tmp_path`,
  Batterie-Zustand + Tracking-Reset) und **`client_with_mocks`** (Flask-TestClient + Immich-Mocks:
  ping/albums/album-assets/original). **`app_module` importiert den echten `app.py`** — d. h. die
  Suite testet die **echte** Pipeline (inkl. Cython), nur die externen Abhängigkeiten sind gemoockt.
* **Struktur (nach ASPICE-IDs):**
  * `test_functional.py` → **FR-001…FR-015** (Album/Assets/Selection/Download/Convert/Scale/Dither/
    Overlay/Preview/**Delivery**/Prepare/Preview-Serving).
  * `test_nonfunctional.py` → **NFR** (Health, Logging, Response-Time, Memory, Theme, Typing) + **IFR**
    (Immich-Header, ESP32-Interface, Ingress/ProxyFix, Port 5000) + **SEC** + **PER**.
  * `test_providers.py` → **Prompt-Variablen, `GenerationTracker`**, je Provider (Health/Name/Summary/
    Fetch/Rate-Limit/Error), **Factory**, Multi-Source-Integration.
* **ASPICE-Doku** (`docs/`): Requirements (EPF-REQ-001), Architektur (EPF-ARC-001), Test-Spec
  (EPF-TST-001), **Test-Report** (EPF-RPT-001). **⚠ Der Report steht auf v1.1.0/93 Tests
  (v1.0.4-Baseline) und ist damit *älter* als der v2.0.0-Code/Spec — s. §14.6.**

---

## 13. Abgrenzung gegenüber `Zippo2000/EPF`

| Aspekt | Standalone `EPF` | **dieses Add-on** | Bewertung |
|--------|------------------|-------------------|-----------|
| Auslieferung | `docker compose`, `python:3.9-slim` | **HA-supervised**, Debian bookworm/py3.11, 5 Archs | + (native HA-Integration, Multiarch) |
| Server | Flask-Dev (single-threaded) | **gunicorn 2×2**, 120 s | + (parallel, robuster) |
| Cython | **committed** `cpy.so` (nicht neu gebaut) | **im Build kompiliert** (`setup.py build_ext`) | + (reproduzierbar, arch-korrekt) |
| Config | **nur** `config.yaml` (Web-UI) | **Zweikanalig** (Env-Options + Laufzeit-YAML) | ± (mehr Kanäle; Secrets sauber getrennt) |
| Quellen | Immich | **Immich + ComfyUI×2** | + (großer Mehrwert) |
| Immich-Endpoint | **v3** `POST /api/search/metadata` (paginiert) | **Legacy** `GET /api/albums/{id}` | **− (Regression!** — v3-kompatibler Standalone ist hier *hinter*; s. §14.3) |
| Prepare/Deliver | — | **neu** (`/prepare-photo` + Status-State-Machine) | + (besseres UX) |
| UI | Basic Settings-Form | **Full-UI** (Health, Batterie, Gallery, Dark Mode, CSP) | + |
| Health/API | — | `/health`, `/api/*`, Docker-HEALTHCHECK | + |
| Doku/Test | README/ARCH/ANALYSE/TESTSPEC + kleine pytest | **ASPICE-Deliverables** (4 Doku) + **~104 Pytest** | + (strenger; aber Report veraltet) |
| Firmware | im Repo (`Arduino/`) | **nicht** im Repo | neutral (saubere Trennung) |

**Kernaussage:** Das Add-on **baut auf** dem EPF auf (Pipeline, Dithering, Batterie, Sleep,
Frame-Format) und **ersetzt** den Deploy-/Config-/Source-Stack durch HA-native Mechanismen.
Es **gewinnt** massiv an Reichweite (3 Quellen, KI-Generierung, UI) — und **zahlt zwei Regressions-
Kosten**: der **Legacy-Immich-Endpunkt** und die **Immix-Pflicht in `run.sh`** (s. §14).

---

## 14. Bemerkungen, Schwachstellen & offene Punkte

> „Kritisch“ = beeinflusst Funktion/Robustheit; „kosmetisch“ = Doku/Konsistenz.

### 14.1 „7-Farben“-Fehler durchzieht die Doku (kosmetisch, aber irreführend)
Der Waveshare 7,3″ **Spectra-6 (E630S)** ist ein **6-Farben**-Panel; `palette` (6 Tupel), `epd_colors`
(6 Zeilen) und alle Tests arbeiten mit **6 Farben** (schwarz/weiß/gelb/rot/blau/grün). Trotzdem steht
**„7-color“** in `README.md`, in `requirements_specification_aspice.md` (Intro) und in
`architecture_document.md` (Goals G-002, Constraints C-003) — ein **Copy-Paste-Erbe vom
Upstream-Projekt**. Ironie: Dieselben Doku widersprechen sich *intern* (andere Stellen derselben
Datei sagen „6-color“). **→ auf „6“ vereinheitlichen.**
> **Status (14.1): ✅ behoben** — alle 6 "7-color"-Stellen auf "6-color" gesetzt (epf-`README` L9/L174; `requirements_spec` L18/L24; `architecture_document` L32/L42); "7.3 inch"/"7.3inch" (Diagonale) bewusst erhalten; intern jetzt konsistent. Fix: Commit `196429e`.

### 14.2 Zwei `config.yaml`-Bedeutungen (konzeptionell, gut gedocht)
> **Status (14.2): keine Maßnahme nötig** — Manifest-`epf-eink-addon/config.yaml` (Add-on-Schema, getrackt) vs. Laufzeit-`config/config.yaml` ist in `README`/`ANALYSE`/`AGENTS` + `.gitignore` bereits erklärt.
`epf-eink-addon/config.yaml` = **Add-on-Manifest** (tracked) vs. Laufzeit-`config/config.yaml`
(ignored, Bind-Mount). `.gitignore` trennt das bewusst via `!`-Whitelist. Klar, aber der
**Namensgleichklang** ist eine wiederkehrende Falle; in allen Doku explizit benennen (done: §11).

### 14.3 `ImmichProvider` = **Legacy**-Endpunkt (potenziell kritisch, **Regression vs. Standalone**)
Die Standalone-EPF wurde **bewusst** auf das **v3-paginierte** `POST /api/search/metadata` umgestellt
(`get /api/albums/{id}` liefert in neueren Immich-Versionen *keine* Assets mehr). Dieses Add-on nutzt
jedoch **`GET /api/albums/{id}`**. Konsequenz: (a) auf älteren Immich-Instanzen OK, (b) auf **neueren**
(wo die legacy-Route verkleinert/retired ist) **leere/fehlende Assets** → 500 → Frame liefert kein Bild.
**Empfehlung:** `ImmichProvider` auf das v3-`search/metadata`-Schema portieren (paginieren, `withExif`),
wie der Standalone-EPF es bereits tut — das wäre der *konsistente* Zustand.
> **Status (14.3): ✅ behoben** — `ImmichProvider` portiert auf das v3-`POST /api/search/metadata` (paginiert, `withExif`); Mocks (`conftest`) + Tests `FR-001`/`FR-002` angepasst (FR-001-Matcher korrigiert); Suite **140/140 grün** im Docker-Testimage. Fix: Commit `5825da7` (Branch `fix/analyse-14`).

### 14.4 `run.sh` erzwingt `IMMICH_API_KEY` **und** `IMMICH_URL` (kritisch für reine ComfyUI-Nutzer)
`run.sh` ruft `bashio::log.fatal … ; exit 1`, wenn **irgendwelche** der beiden Werte leer sind —
**unabhängig vom `image_source`**. Ein **ComfyUI-only**-Setup (kein Immich) kann daher **nicht starten**,
solange man nicht Dummy-Werte eingibt. **Empfehlung:** Gate **conditional** auf `image_source == immich`
machen; ggf. nur die *für die gewählte Quelle relevanten* Felder validieren.
> **Status (14.4): ✅ behoben** — Gate in `run.sh` ist jetzt **source-conditional** (`image_source=immich`); reine ComfyUI-Setups starten ohne Immich-Werte. Verifiziert: `bash -n` + Gate-Simulation. Fix: Commit `f6b3756`.

### 14.5 `cpy.so` (1,2 MB, amd64) ist **redundant im Repo** (kosmetisch/hygienisch)
> **Status (14.5): ✅ behoben** — prebuilt `cpy.so` **und** beide `!epf-eink-addon/cpy.so`-Negations entfernt; der Build kompiliert `cpy.pyx` selbst (`*.so` bleibt ignoriert). Fix: Commit `98bd659`.
Der Docker-Build **COPYt nur `cpy.pyx` + `setup.py`** und **kompiliert selbst** — die commit-ete `cpy.so`
wird **niemals** ins Image kopiert. `.gitignore` whitelistet sie trotzdem (`!epf-eink-addon/cpy.so`)
(zweimal, sogar dupliziert) als **Erbe vom Basisprojekt**. → **Entfernen** (oder `!`-Zeile löschen) —
sie suggeriert falsche Relevanz; der Build ist self-contained.

### 14.6 `test_report_aspice.md` ist **veraltet** (kosmetisch, aber Vertrauens-Problem)
> **Status (14.6): ✅ behoben** — Report auf **v2.0.0 / 140 Tests** neu geschrieben (früher 1.1.0/93, intern inkonsistent: 93 nominal vs 78 ausgeführt). Jetzt: 140/140 (functional 77, non-functional 27, provider-unit 36), v3-konforme Immich-Mocks, FR-027/028 erfasst. Fix: Commit `5e35e92`.
Report = **v1.1.0 / 93 Tests / „100 %“ / 14,75 s** — eine **v1.0.4**-Baseline. Code & Specs stehen aber
auf **v2.0.0** (31 FR, + ganzer Provider-Test-Modul). Die Report-Zahlen sind damit **keine Aussage über
den aktuellen Stand**. → Beim nächsten Lauf `EPF-RPT-001` auf v2.x hochziehen und die Count aktualisieren
(laut `run.test.sh` trivial möglich).

### 14.7 Datum-Overlay braucht **DejaVu**, das **Prod-**`Dockerfile` **installiert nicht** (kosmetisch)
> **Status (14.7): ✅ behoben** — `fonts-dejavu-core` zur apt-Liste des **Prod-**`Dockerfile` hinzugefügt (war nur im Test-Image); `DejaVuSans-Bold.ttf` im bookworm-Image verifiziert → Datum-Overlay rendert mit der beabsichtigten Schrift statt `load_default()`. Fix: Commit `c535e67`.
`scale_img_in_memory` versucht `ImageFont.truetype('.../DejaVuSans-Bold.ttf')`; nur **`Dockerfile.test`**
bündelt `fonts-dejavu-core`. Im **prod** Image fällt das auf `ImageFont.load_default()` (winzige
Bitmap-Schrift) zurück → Overlay bleibt, ist aber nicht die beabsichtigte Schrift. → Either `fonts-dejavu-core`
in `Dockerfile` nachziehen, oder den Fallback als *intended* dokumentieren.

### 14.8 Sleep-/Wake-Zeit = **Container-Uhr** (Zone + Drift) (wie Basis-EPF, bewusst)
> **Status (14.8): ✅ entschieden (Doku)** — bewusst wie Basis-EPF: die **Host-/System-Uhr muss stimmen**; der NTP-Thread *liest* nur, setzt die Uhr nicht. *Optional:* `TZ` als Add-on-Option durchreichen, damit Schlaf-/Wake-Fenster lokal sind.
`/sleep` nutzt `datetime.now()` in der **Container-Zoné** (Default **UTC**) — ohne `TZ`-Option driftet
das Fensters um die Offset. NTP-Thread **liest nur** `pool.ntp.org`, **setzt die Uhr nicht**. → **TZ** als
Add-on-Option anbieten (bzw. Doku: „Systemuhr des Hosts muss stimmen“), s. Standalone-Analyse.

### 14.9 **Zwei Paletten in zwei Phasen** (Dithering vs. De-Palette) (offen, s. Basis-EPF)
> **Status (14.9): 🔶 explizit OFFEN** — die endgültige **Farb-Slot-Zuordnung** (2 Paletten/2 Phasen; `indices[indices>3]+=1`) lässt sich nur **gegen eine Waveshare-Referenzkarte / per Foto** abschließend prüfen. Bis dahin **bewusst offengelegt** (nicht verheimlicht) — siehe auch Basis-EPF.
`cpy.pyx` dithert gegen **reine** RGBs; `app.py::depalette_image` mappt gegen die **annähernden**
Waveshare-RGBs — plus `indices[indices>3] += 1` (Slot 4 = Waveshare-`RED` wird nie ausgegeben).
Deterministisch, aber **fragil**; die **effektive Farbzuordnung zum Panel** sollte einmal
fotoğrafisch gegen eine Waveshare-Referenz verifiziert (wie in der Basis-ANALYSE empfohlen).

### 14.10 Health koppelt **Container-Status an externe Quelle** (Design-Entscheidung, Trade-off)
> **Status (14.10): ✅ entschieden (Trade-off behalten)** — die Kopplung bleibt, weil sie die **Abhängigkeit sichtbar** macht (down-Quelle ⇒ 503). *Optional:* Health = „App up“, Quellen-Status nur im UI anzeigen (kein 503).
Docker-`HEALTHCHECK` → `GET /health` → pingt den **aktiven Provider** (z. B. Immich). Ist Immich down,
ist der **Container „unhealthy“** — auch wenn die App selbst einwandfrei läuft. Das ist **bewusst**
(zeigt die Abhängigkeit), kann aber Supervisor-Aktionen/Alerting **falsch** triggern. → Alternative:
Health auf „App ist up” (Process-Check) reduzieren und die *Quellen*-Erreichbarkeit nur als
**Separaten-Status** im UI anzeigen.

### 14.11 **Kein Auth** auf `/` (POST), `/prepare-photo`, `/cleanup-previews`, `/download` (kritisch außer-LAN)
> **Status (14.11): ✅ entschieden (bekannte Grenze)** — Endpunkte bleiben unauthentifiziert; **rohen Port 5000 nur im LAN/VLAN** exponieren; **Ingress** liefert den Session-Schutz für die UI. Token-/Rate-Limit nur **optional**, falls >LAN. Siehe §4 (Security).
Alle Endpunkte sind **anonym** ansprechbar (Ingress bietet bei UI-Zugriff *Session*-Schutz, **roher Port 5000
nicht**). Jeder im Netz könnte Einstellungen ändern oder `/download` in einem Loop feuern. Das **vertraute-
LAN**-Modell (wie Basis-EPF, `SEC-001…` decken nur *Leakage*, nicht *Zugriff*) ist akzeptabel **im Home-LAN**,
**nicht** für „Cloud/Internet“. `SEC-001` (Key nicht in Responses) + `SEC-003` (Rotation-Validierung) sind gut
abgedeckt; **Endpoint-Auth/Rate-Limit** fehlt. → Bei Exponierung: minimales Bearer- oder Token-Schutz + Rate-Limit.

### 14.12 **Single `active_provider`-Global** unter gunicorn **2×2** (robust, aber zu beachten)
> **Status (14.12): ✅ entschieden (bekannte Einschränkung)** — relevant **nur** bei **mehreren Frames gegen einer Instanz** (State/`active_provider` pro Worker/Thread). *Optional:* leichtes Locking/`fcntl` auf `tracking.txt`/`generations.json`. Kein Pflicht-Code.
Der Provider wird pro Worker-Process lazy erzeugt (`get_active_provider`) und bei Config-Wechsel pro
Worker neu gebaut — da gunicorn **forkt**, teilen **verschiedene Worker eigene** `active_provider`/
Tracking-Datei-Zustände. `tracking.txt`/`generations.json` haben **keine Dateisperre** → zwei
simultanen `/download` können dieselbe „unseen“-Menge sehen (**doppeltes Foto**) bzw. das ComfyUI-
Limiter **zählen parallel** (mild). Im typischen Betrieb (1 Frame, sequentiell) unkritisch; für
**mehrere Frames** gegen dieselbe Instanz relevant (wie in Basis-EPF §10.5.2).

### 14.13 Kleinkram
> **Status (14.13): ✅ behoben** — `.gitignore`-Duplikate (`test-results.xml`; `Dockerfile.test`+`run.test.sh`) zusammengefasst; unused `python-dotenv` aus `requirements.txt` entfernt ( nirgends importiert). Fix: Commit `6a778dc`.
* `run.sh`/`run.test.sh` **doppelt** in `.gitignore` aufgeführt (cosmetic).
* `requirements.txt` pinnen `python-dotenv`, das **nirgends** importiert wird (dead dep).
* `app.py` importiert `rawpy`/`glob` o. ä. mehrfach; `setup.py`-`define_macros` (Numpy-ABI) — alles
  harmlos, aber bei Refactor mitdenken.
* **`PROXY`/`X-Forwarded`**: `ProxyFix(x_for=1, …)` ist korrekt für eine HA-Schicht; bei **mehr** als
  einem Proxy davor (z. B. zusätzlicher Reverse-Proxy) müsste `x_for` erhöht werden — Doku-Hinweis.

### 14.14 UI-Track: Footer-Version/-Build-Datum & Health-Indikator (geschlossen in 2.0.3)
Neben dem §14-Katalog lief ein separater **UI-Findings-Track** (Dokumentation:
[`plans/findings.md`](plans/findings.md); der §14-Remediation-Track selbst liegt in
[`plans/findings-14.md`](plans/findings-14.md)):

* **Footer:** `BUILD_VERSION`/`BUILD_TIMESTAMP` waren **manuell gepflegte** Konstanten in `app.py` —
  die Version war gebumpt, das Datum hatte stehen bleiben (altes `2026-04-03`). **Behoben in 2.0.3:**
  beide Werte werden jetzt *im Image abgeleitet* — Version: (Priorität) `ADDON_VERSION`-Build-Arg →
  **Manifest** `config.yaml`, Feld `version:` (Single Source of Truth) → `dev`; Build-Datum:
  `BUILD_TIMESTAMP`-Env → **`.build_stamp`** (vom `Dockerfile` beim Image-Build geschrieben, UTC,
  `SOURCE_DATE_EPOCH`-kompatibel) → `unknown`. Eine handgepflegte Versionsziffer existiert in
  `app.py` nicht mehr; das Release-Verfahren ist in `README.md` („Building & Releasing“) verankert.
* **Header:** Das alte „Connected“-Label sagte nicht, *womit* verbunden. **Behoben in 2.0.3:**
  die UI feuert **GET** an `/health` (statt HEAD) und rendert den Namen der konfigurierten
  Bildquelle aus dem JSON-Body (z. B. `Immich online` / `Immich unreachable` + Tooltip); der
  HEAD-Modus des Endpoints bleibt für Clients erhalten (s. §14.10).
* **Sprache:** Alle nutzerorientierten Strings des Add-ons sind seither **Englisch**
  (Regel verankert in `AGENTS.md`, „Docs & language split").

> **Status (14.14): ✅ geschlossen (2.0.3)** — ausstehend sind nur die *Feld-Smokes* auf der
> echten HA-Instanz (Header × 2 Quellen, Footer), dokumentiert in `plans/findings.md` (L3).

---

## 15. Fazit & Empfehlungen

**Stehung:** Das Add-on ist ein **reifes, gut strukturierter HA-Ableger** des EPF. Die **Provider-
Abstraction** (ABC + 3 Quellen + Factory + Tracker) ist die v2-Point und **sauber umgesetzt** — neue
Quellen sind mit einer Subklasse + einem Factory-Zweig hinzubar, ohne `app.py` zu verunreinigen.
Der **HA-Deploy-Stack** (bashio-Options→Env, Ingress + ProxyFix, gunicorn 2×2, Docker-HEALTHCHECK,
5 Archs, **Cython im Build** statt committed ELF) ist **besser gelöst als beim Standalone-EPF** und
entfernt dessen größte Build-Schwäche (platte `cpy.so`-Binaries). Die **Prepare/Deliver-Entkopplung**,
die **Galerie**, **Health/Batterie-Telemetrie** und die **Dark-Mode-UI** sind echte UX-Gewinne, und
das **ASPICE-Doku- + ~104-Test-Paket** ist disziplinär deutlich über dem Basisprojekt.

**Wo es hakt** (Priorität):
1. **§14.4 (kritisch):** `run.sh` Gate **source-conditional** machen — reine ComfyUI-Setups heute
   nicht startbar ohne Dummy-Immich-Werte.
2. **§14.3 (kritisch/Regression):** `ImmichProvider` auf das **v3 `search/metadata`** portieren
   (konsistent zum Standalone-EPF; vermeidet Breakage auf neueren Immich).
3. **§14.11 (wenn exponiert):** minimales Auth/Rate-Limit auf die POST-/Download-Endpoints.
4. **§14.5/§14.6 (Hygiene):** redundantes `cpy.so` + `!`-Zeile entfernen; **Test-Report auf v2.x**
   neu laufen lassen.
5. **§14.1/§14.7 (Doku):** „7→6-Farben“ vereinheitlichen; `fonts-dejavu-core` ins Prod-Image.
6. **§14.9 (offen):** endgültige **Farb-Slot-Zuordnung** photographisch verifizieren (Basis-EPF-Thema).

**Netto:** Als HA-Add-on **funktional vollständig, robuster gebaut als der Standalone-Vorgänger**, mit
klaren, kleinen Nachbesserungs-Punkten — vor allem das **Immix-Pflicht-Gate** und die **Immix-Endpoint-
RegRESSION** sind die einzigen, die reale Setups betreffen.
