# AGENTS.md

Guidance for **AI coding agents** (and human newcomers) working in this repo.
Read this before touching `epf-eink-addon/`. Where it conflicts with an explicit
instruction in chat, the chat wins; the nearest `AGENTS.md` in the tree wins over this one.

> **Relation to the sibling project:** this repo is the **Home Assistant Add-on** version of the
> standalone [`Zippo2000/EPF`](https://github.com/Zippo2000/EPF) server. Same core idea (Flask
> server that turns a source image into a 6-colour e-paper frame and drives an ESP32), but
> repackaged to run **inside Home Assistant** and extended with **multi-source image support**
> (Immich · ComfyUI-via-HA · ComfyUI-direct). If you know `Zippo2000/EPF`, the deltas are in
> §"How this differs from standalone EPF".

---

## What this project is

A **Home Assistant add-on store repository** containing a single add-on, **`epf-eink-addon`**:

- **The server (this repo)** — a Flask app, packaged as a **HA supervised add-on**. On each
  device request it pulls an image from one of three **sources** (see the Provider layer below),
  scales/crops/rotates it, **dithers it toward the 6-colour Waveshare Spectra-6 (E630S) palette**
  (Cython, `cpy.pyx`), packs the pixels, and serves the frame to the ESP32 over HTTP. It also
  answers a "how long should I sleep?" call, exposes a **health check**, **battery**, **generation
  status**, a **preview gallery**, and a web **settings** page that can be embedded in HA via
  **ingress**.
- **The frame** — the same **ESP32 + Waveshare 7.3″ Spectra-6** hardware from the standalone EPF
  project. Its firmware lives in that *other* repo (`Zippo2000/EPF/Arduino`), **not here**. This
  repo contains **no firmware**. The ESP32 merely needs to be pointed at the add-on's URL.

The exact wire contracts are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md); the full
technical analysis (incl. weaknesses) in [`ANALYSE.md`](ANALYSE.md); the test model in
[`TESTSPEC.md`](TESTSPEC.md).

## Repository layout

```
repository.yaml               # marks this as a HA ADD-ON STORE (name/url/maintainer) — required for the add-on store
LICENSE                       # MIT
.gitignore                    # note: whitelists (!) epf-eink-addon/cpy.so and the add-on manifest; ignores the runtime config/ + photos/
docs/                         # formal ASPICE deliverables (German/English): 
                                #   requirements_specification_aspice.md  (EPF-REQ-001: 31 FR + 10 NFR + 5 IFR + 4 SEC + 3 PER)
                                #   architecture_document.md              (EPF-ARC-001: components C-001..C-018, design decisions D-001..)
                                #   test_specification_aspice.md          (EPF-TST-001: test cases, one per requirement)
                                #   test_report_aspice.md                 (EPF-RPT-001: last full run — see version-skew note in §Gotchas)

epf-eink-addon/               # THE ADD-ON (everything you will normally edit lives here)
  config.yaml                 # ADD-ON MANIFEST: name, version, arch list, ports, ingress, panel_icon, options{} + schema{}
  build.yaml                  # base images per arch (HA debian-based python base images)
  Dockerfile                  # production image: installs py3.11 + Pillow/rawpy deps, COMPILES cpy.so, gunicorn entrypoint, HEALTHCHECK->/health
  Dockerfile.test             # test image: same base + fonts-dejavu-core + tests/ , CMD runs pytest (run.test.sh)
  app.py                      # Flask app: routes, config handling, image pipeline driver, battery, sleep, NTP thread (module-level, procedural)
  providers.py                # ImageProvider ABC + ImmichProvider / ComfyUIHAProvider / ComfyUIDirectProvider + create_provider() factory + GenerationTracker + resolve_prompt_variables()
  cpy.pyx  (compiled to cpy.so at build time by setup.py; the committed .so is vestigial — see §Gotchas)
  setup.py                    # cythonize("cpy.pyx", numpy include, language_level=3)
  requirements.txt            # Flask 3.0.3, Pillow 10.4, numpy 1.24, rawpy 0.21, pillow-heif, gunicorn 23, watchdog, ntplib, pytest, responses (pinned)
  run.sh                      # `#!/usr/bin/with-contenv bashio`: reads add-on options via bashio::config -> exports env -> starts gunicorn (2x2) on :5000
  run.test.sh                 # runs `python3 -m pytest tests/ -v --junitxml=...` inside the test image
  templates/settings.html     # the web UI (Jinja + inline JS): health/battery/photo-status panels, source cards, ComfyUI prompt cards, gallery, dark mode
  tests/
    conftest.py               # fixtures: app_module (fresh import w/ env+NTP+watchdog mocked), client_with_mocks (Flask client + `responses` Immich mocks)
    test_functional.py        # FR-001..015 (album/asset/select/download/convert/scale/dither/overlay/preview/delivery/prepare/serve)
    test_nonfunctional.py     # NFR (health, logging, timing, memory, theme, typing) + IFR (immich hdr, esp32, ingress, port) + SEC + PER
    test_providers.py         # Prompt variables, GenerationTracker, each Provider, factory, multi-source integration
  README.md                   # the ADD-ON's user-facing README (shown in HA); keep in sync with config.yaml options
```

---

## How this differs from standalone EPF (the mental model that matters)

| Aspect | Standalone `Zippo2000/EPF` | **This add-on** |
|--------|-----------------------------|------------------|
| Packaging | `docker compose`, `python:3.9-slim`, **committed** `cpy.so` | **HA supervised add-on**; Debian **bookworm / Python 3.11**; **`cpy.so` compiled at image build** (`setup.py build_ext`); multi-arch armhf/armv7/aarch64/amd64/i386 |
| Server | Flask **dev** server | **gunicorn** (`2 workers × 2 threads`, 120 s timeout) |
| Config channel | **only** `config.yaml` (via `/setting`); env used for tests | **DUAL**: (a) **HA add-on options** → env (`bashio`) → seed `DEFAULT_CONFIG`; **secrets only via env**; (b) **`config/config.yaml`** written by web UI = runtime source of truth, hot-reloaded via watchdog. See §Config. |
| Image source(s) | Immich only | **3**: Immich · ComfyUI via HA service · ComfyUI direct API — behind a **`providers.py`** factory |
| Immich endpoint | **v3** `POST /api/search/metadata` (paged) | **legacy** `GET /api/albums/{id}` (see §Gotchas — this is a *regression* vs the base) |
| New features | — | `/health` (source-agnostic), `/api/generation-status`, **prepare/deliver decoupling** (`/prepare-photo` + status file), **preview gallery**, **dark mode**, CSP/referrer hardening, per-day ComfyUI generation cap + tracking |

> If a change to the *standalone* EPF doesn't obviously apply here, this table is why.

---

## Prerequisites

- **Docker** (any flavour; the build only needs to match the target arch).
- To **use** the add-on for real: a **Home Assistant** installation with the add-on store, plus
  a reachable **Immich** server and/or **Home Assistant** with the `ai_task` integration and/or a
  **ComfyUI** server — depending on the chosen `image_source`.
- For **tests**: nothing external — the suite is fully mocked (see §Testing).

## Commands

> All paths are relative to the **repo root**; the add-on lives in `epf-eink-addon/`.

**Build the production image**
```bash
cd epf-eink-addon
docker build -f Dockerfile -t epf-eink:local .        # amd64 by default (BUILD_FROM arg)
# other arches: pass the matching base, e.g.
docker build --build-arg BUILD_FROM=ghcr.io/home-assistant/aarch64-base-debian:bookworm -f Dockerfile -t epf-eink:aarch64 .
```
The build **compiles `cpy.so`** in-container; there is nothing to prebuild on the host.

**Install / run for real (recommended)**
```bash
# In Home Assistant: Add-ons → Add-on Store → (this repo, once added) → install "E-Paper Photo Frame (EPF)"
# then Configure: pick image_source, fill the matching *_url / *api_key / prompt, Start.
```
The UI is exposed **through HA ingress** (`panel_icon: mdi:image-frame`) and also on the raw
`5000/tcp` port. The ESP32 (from the sibling repo) is pointed at the add-on's base URL.

**Run the offline test suite**
```bash
docker build -f epf-eink-addon/Dockerfile.test -t epf-eink-tests:local epf-eink-addon
docker run --rm epf-eink-tests:local /run.sh          # runs run.test.sh -> pytest + junitxml
```
Or, in your own Python 3.11 env with the pinned deps (`responses`, `rawpy`, `Cython`, …):
```bash
cd epf-eink-addon && python -m pytest tests/ -v
```
The suite is self-contained (mocked Immich/HA, `tmp_path` filesystem, patched NTP/watchdog) —
**no network, no Immich, no ComfyUI needed**.

**Edit + recompile the Cython** — only if you touched `cpy.pyx`:
```bash
cd epf-eink-addon && python setup.py build_ext --inplace
```
(The Docker build already does this. A local rebuild is only needed if you import the module on
the host; the host binary is **not** what ships.)

---

## Configuration — two channels (do not confuse them)

This is the biggest footgun in the project:

1. **Add-on options → env vars (deploy/secrets).** HA passes every `options:` key in
   `config.yaml` to the container. `run.sh` reads each with `bashio::config` and **re-exports it
   as an env var** (`image_source`→`IMAGE_SOURCE`, `immich_api_key`→`IMMICH_API_KEY`,
   `album_name`→`ALBUM_NAME`, `ha_api_token`→`HA_API_TOKEN`, `comfyui_entity_id`→
   `COMFYUI_ENTITY_ID`, …). `app.py` reads these into `DEFAULT_CONFIG` at import time. **Secrets
   (API keys, HA token) come *only* from here** — never bake them into the YAML.
2. **Runtime config YAML (display/photo behaviour).** `CONFIG_PATH` (default `config/config.yaml`,
   a bind-mount) holds the effective settings and is (re)written by the **web UI** (`POST /`).
   A **watchdog** (`ConfigFileHandler`) hot-reloads it on change and calls `update_app_config()`,
   which also **rebuilds the active provider**. This is the live source of truth the UI edits.

**Rules of thumb**
- Changing *which album / rotation / dither / sleep window* → edit in the **web UI** (or the
  mounted YAML); it hot-reloads. No restart.
- Changing a *secret* or *adding a new source* → change the **add-on option** (HA UI) and restart
  the add-on (options are read at container start, not hot-reloaded).
- The two files with `config.yaml` in the name are **different things**: the **add-on manifest**
  (`epf-eink-addon/config.yaml` — tracked, defines `options`/`schema`) vs the **runtime YAML**
  (`config/config.yaml` — git-ignored, created at runtime). Don't "refactor" one into the other.

---

## Testing

Plain **pytest**, fully **mocked** (see `TESTSPEC.md` for the ASPICE cross-reference). Layout
mirrors the requirement catalog in `docs/requirements_specification_aspice.md`:

- `tests/conftest.py` — the `app_module` fixture (fresh import with env + NTP + watchdog patched,
  filesystem redirected to `tmp_path`) and `client_with_mocks` (Flask test-client with
  `responses`-mocked Immich: ping/albums/album-assets/asset-original).
- `tests/test_functional.py` — **FR-001…FR-015** (album/asset/selection/download/convert/
  scale+dither/overlay/preview/**delivery**/prepare/serve).
- `tests/test_nonfunctional.py` — **NFR** (health, logging, response-time, memory, theme,
  typing) + **IFR** (Immich header, ESP32 interface, ingress ProxyFix, port) + **SEC** + **PER**.
- `tests/test_providers.py` — prompt-variable resolution, `GenerationTracker`, each Provider, the
  `create_provider` factory, and multi-source integration.

The `Dockerfile.test` image bundles `fonts-dejavu-core` (for the date-overlay path) and
`tests/`, and its `CMD` is `run.test.sh` (pytest with `--junitxml`). **The report
(`docs/test_report_aspice.md`) currently lags the code — see §Gotchas before trusting its
pass counts.**

---

## Code style & conventions

- **Python 3.11** (bookworm), **procedural** `app.py` (module-level functions + a Blueprint, not a
  big class). Keep it that way. English for comments/docstrings in the server code.
- **`providers.py` is the abstraction boundary.** New image source ⇒ new `ImageProvider` subclass +
  a branch in `create_provider()`. Do **not** bolt a fourth source's HTTP logic into `app.py`.
- **Per-pixel work stays in Cython** (`cpy.pyx`). Do not move the dither loops into Python in
  `app.py`.
- **The web UI is a single self-contained `templates/settings.html`** (inline `<style>` +
  `<script>`). It polls `/health` (60 s), `/api/battery-status` (30 s), `/preview-status` (10 s).
  Keep the **CSP** meta tag and the named `POLL_INTERVALS`/`NOTIFICATION_DURATION` constants intact.
- **Docs split:** code-facing docs (`README.md`, `AGENTS.md`, `ARCHITECTURE.md`) are **English**;
  the analytical docs (`ANALYSE.md`, `TESTSPEC.md`) are **German** — match the neighbour.

---

## Security & secrets

- **Secrets only in env (add-on options):** `IMMICH_API_KEY`, `HA_API_TOKEN`,
  `COMfyUI_ENTITY_ID`. The runtime YAML must **never** contain them (the UI form deliberately
  omits a key field — it reads from env). `.gitignore` already keeps `.env`, `config/`,
  `photos/`, `tracking.txt`, `test-results.xml` out.
- **The HTTP surface is unauthenticated** beyond HA ingress: `POST /` (settings), `POST
  /prepare-photo`, `POST /cleanup-previews`, `GET /download` all accept anonymous callers. Treat
  the add-on as **LAN/trusted-network only** (the ESP32 presents no credentials, same model as the
  base EPF). If you expose port 5000 beyond the LAN, that is a real exposure — `SEC-001…004` in
  the requirements doc cover the *leakage* guarantees, not endpoint auth.
- **TLS to Immich/HA/ComfyUI** is whatever the target serves; the add-on does its own
  client-side trust (no pinned certs). The `ProxyFix` middleware (`x_proto=1`) is what makes
  HTTPS-through-ingress behave; keep it.

---

## Gotchas (the non-obvious stuff)

- **`cpy.so` in the repo is vestigial.** The Docker build **recompiles** it from `cpy.pyx`
  (`COPY cpy.pyx setup.py` + `python setup.py build_ext --inplace`); the committed `cpy.so`
  (1.2 MB, amd64) is *never copied into the image*. `.gitignore` *re-includes* it
  (`!epf-eink-addon/cpy.so`) as a leftover from the base project — it's dead weight, not a build
  input. Don't hand-edit the `.so`; edit `cpy.pyx` and let the build rebuild it.
- **`ImmichProvider` uses the *legacy* endpoint** `GET /api/albums/{id}` to list assets — the
  very endpoint the standalone EPF **moved away from** in favour of the v3 paged
  `POST /api/search/metadata`. If a target Immich version drops the legacy route, this breaks.
  Keep an eye on it (see ANALYSE §Bemerkungen).
- **`run.sh` hard-requires `IMMICH_API_KEY` and `IMMICH_URL`** (it `bashio::log.fatal`s +
  `exit 1` if either is empty) **even when `image_source` is a ComfyUI mode.** So a
  ComfyUI-only setup can't start without at least a *dummy* Immich value. The startup gate should
  be made source-conditional before this bites in the field.
- **Doc says "7-colour", code is 6-colour.** The Waveshare 7.3″ Spectra-6 (E630S) panel and the
  `palette`/`epd_colors` arrays are **6 colours** (black/white/yellow/red/blue/green). Several
  docs (`README.md`, `requirements_specification_aspice.md` intro, `architecture_document.md`
  goals/constraints) still say "7-colour" — a copy-paste regression from the upstream project.
  Unify on 6.
- **`test_report_aspice.md` is stale (v1.1.0, "93 tests / 100 %")** whereas the code & specs are
  at **v2.0.0** (31 FRs, plus the provider test module). Treat the report's numbers as a
  *previous* run; re-run `run.test.sh` for the current truth.
- **Date overlay needs DejaVu, but the *prod* `Dockerfile` doesn't install it** (only
  `Dockerfile.test` does). At runtime `ImageFont.truetype('.../DejaVuSans-Bold.ttf')` falls back
  to `load_default()` (tiny bitmap font). The overlay still renders — just not with the intended
  font. Cosmetic.
- **Two different `config.yaml` names** (manifest vs runtime) and a **`photos/` vs `IMMICH_PHOTO_DEST`**
  dir that holds `tracking.txt`, `generations.json`, the `latest_*.jpg` previews, and `latest.bmp`
  + `latest.status`. These live in the add-on's bind-mount; recreate the container without the
  mount and settings/history/reset.
- **`/download` returns `frame.txt`** (renamed from the base project's `.c`) as `text/plain`,
  2 hex-digit tokens (two 4-bit colour indices per byte), newline every 16, **no closing `};`**
  (the base EPF had one; removing it avoids the firmware's extra `0x00`). The firmware in the
  sibling repo parses token-by-token until EOF, so both forms work.

---

## Further reading

- [`README.md`](README.md) — what the store/add-on is, install, option reference (English)
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — the source→provider→pipeline→ESP32 data flow + the
  HA (bashio/ingress/gunicorn) deployment contract + the invariants to keep in sync (English)
- [`ANALYSE.md`](ANALYSE.md) — full German technical analysis incl. weaknesses & recommendations
- [`TESTSPEC.md`](TESTSPEC.md) — test model, tiers, how to run, cross-ref to the ASPICE spec (German)
- Formal ASPICE deliverables: [`docs/`](docs/) — `requirements_specification_aspice.md` (EPF-REQ-001),
  `architecture_document.md` (EPF-ARC-001), `test_specification_aspice.md` (EPF-TST-001),
  `test_report_aspice.md` (EPF-RPT-001).
- Sibling firmware + full original: [`Zippo2000/EPF`](https://github.com/Zippo2000/EPF)
  (`Arduino/epd7in3e.ino` is the frame that talks to this server).
