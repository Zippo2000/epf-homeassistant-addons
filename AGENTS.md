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

 "## Top-level goal: the add-on must run flawlessly in Home Assistant

**The single highest bar for this project: the add-on must work end to end inside a
real Home Assistant instance â not merely "compile and pass unit tests."** A green
offline suite is necessary but not sufficient; the failure modes that bite in the
field live in the *integration* with real dependencies (Immich / Home Assistant /
ComfyUI) and in *packaging* (gunicorn, ingress, ports, the ESP32 handshake). We
defend that bar with a **layered** assurance model, cheapest-first:

| Layer | What it proves | Where / how |
|-------|----------------|-------------|
| **L0 â offline unit/integration** | the *real* pipeline (Cython dither, scaling, hex pack, provider logic, Flask routes) is correct, deterministically | `Dockerfile.test` default CMD -> `pytest tests/` (~206 tests); no network — and in CI (`.github/workflows/l0.yml`, 2.4.3b) |
| **L1 â LIVE backend** | the *actual* wire contract holds against a **real** Immich (album resolve, v3 paged `search/metadata`, original download) and the add-on `/download` route end to end, plus (2.4.0) a **real** ComfyUI (built-in graph, named-workflow selection, a real exported graph) | `sh epf-eink-addon/run-live-tests.sh` (opt-in `EPF_LIVE_TESTS=1`, reads git-ignored `.env`); the only tier that can falsify a real-API assumption |
| **L2 â HA / ingress / gunicorn** | ProxyFix, ingress path, `/health`, port 5000, multi-worker behaviour | covered in L0 (`test_nonfunctional.py`) + the production-image smoke below |
| **L3 â production-image smoke** | the *shipped* `Dockerfile` (gunicorn, healthcheck, real entrypoint) boots and answers `/health`, `/sleep`, `/download` | build `Dockerfile` + the `curl` checklist in TESTSPEC.md, section 6 |
| **L4 â manual field** | real ESP32, e-paper wear, multi-day stability, real ComfyUI/HA flows | documented in the field handbook; not automatable here (TESTSPEC, section 3) |

**Definition of Done (release gate).** A release is test-complete when:
1. **L0** is green (`Dockerfile.test` run returns exit 0) and all P0/`SEC`/`IFR` cases pass;
2. **L1** has been run against a real Immich and is green (or, if the server was
   unavailable, that is explicitly noted). L1 is the *load-bearing* gate for
   "works in real HA";
3. **L3** production-image smoke answers `/health` and `/download`;
4. the ASPICE report (`docs/test_report_aspice.md`) is regenerated against the *current*
   code (the v1.1.0 numbers in it are stale).

> **Why L1 matters most:** the offline mocks can only return what we teach them. Only a
> live Immich run tells us, for example, whether the image source still matches the
> server's current API. Keep L1 cheap and always skippable so it is *actually* run
> before every release.


## Repository layout" 

```
repository.yaml               # marks this as a HA ADD-ON STORE (name/url/maintainer) — required for the add-on store
LICENSE                       # MIT
.github/workflows/l0.yml      # the L0 tier in CI: build Dockerfile.test, run pytest (L1 auto-skips; no secrets), upload the junit artifact
.gitignore                    # note: whitelists (!) epf-eink-addon/cpy.so and the add-on manifest; ignores the runtime config/ + photos/
docs/                         # formal ASPICE deliverables (German/English): 
                                #   requirements_specification_aspice.md  (EPF-REQ-001: 33 FR + 10 NFR + 5 IFR + 4 SEC + 3 PER)
                                #   architecture_document.md              (EPF-ARC-001: components C-001..C-018, design decisions D-001..)
                                #   test_specification_aspice.md          (EPF-TST-001: test cases, one per requirement)
                                #   test_report_aspice.md                 (EPF-RPT-001: last full run — see version-skew note in §Gotchas)

epf-eink-addon/               # THE ADD-ON (everything you will normally edit lives here)
  config.yaml                 # ADD-ON MANIFEST: name, version, arch list, ports, ingress, panel_icon, options{} + schema{}
  build.yaml                  # base images per arch (HA debian-based python base images)
  Dockerfile                  # production image: installs py3.11 + Pillow/rawpy deps, COMPILES cpy.so, gunicorn entrypoint, HEALTHCHECK->/health
  Dockerfile.test             # test image: same base + fonts-dejavu-core + tests/ , CMD runs pytest (run.test.sh)
  app.py                      # Flask app: routes, config handling, image pipeline driver, battery, sleep, NTP thread (module-level, procedural)
  providers.py                # ImageProvider ABC + ImmichProvider / ComfyUIHAProvider / ComfyUIDirectProvider + create_provider() factory + GenerationTracker + resolve_prompt_variables() + named-workflow selection (2.4.0)
  cpy.pyx  (compiled to cpy.so at build time by setup.py; the committed .so is vestigial — see §Gotchas)
  setup.py                    # cythonize("cpy.pyx", numpy include, language_level=3)
  requirements.txt            # Flask 3.0.3, Pillow 10.4, numpy 1.24, rawpy 0.21, pillow-heif, gunicorn 23, watchdog, ntplib, pytest, responses (pinned)
  run.sh                      # `#!/usr/bin/with-contenv bashio`: reads add-on options via bashio::config -> exports env -> starts gunicorn (2x2) on :5000
  run.test.sh                 # runs `python3 -m pytest tests/ -v --junitxml=...` inside the test image
  templates/settings.html     # the web UI (Jinja + inline JS): health/battery/photo-status panels, source cards, ComfyUI prompt cards, gallery, dark mode, in-page image zoom (lightbox) for dashboard previews and gallery shots
  tests/
    conftest.py               # fixtures: app_module (fresh import w/ env+NTP+watchdog mocked), client_with_mocks (Flask client + `responses` Immich mocks)
    test_functional.py        # FR-001..015 (album/asset/select/download/convert/scale/dither/overlay/preview/delivery/prepare/serve) + the settings vocabulary & save-time guards (2.4.1, 2.4.3b)
    test_nonfunctional.py     # NFR (health, logging, timing, memory, theme, typing) + IFR (immich hdr, esp32, ingress, port) + SEC + PER
    test_providers.py         # Prompt variables, GenerationTracker, each Provider, factory, multi-source integration
    test_gallery_history.py   # FR-032 gallery history: shot ids, pairing, grouped reader, **per-shot** pruning (2.4.3), option round trip
    test_live.py              # L1 live tier (opt-in: EPF_LIVE_TESTS=1 + git-ignored .env) — real Immich + real ComfyUI; auto-skips otherwise
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

> **…or let CI do it:** `.github/workflows/l0.yml` runs exactly those two commands on every push/PR
> that touches the add-on (plus `workflow_dispatch`). It needs no secrets and no network, so the opt-in
> live tier auto-skips there too — L1 and the L3 production-image smoke stay manual, so the CI job is
> the cheap always-on floor, **not** a replacement for the release gates above.
Or, in your own Python 3.11 env with the pinned deps (`responses`, `rawpy`, `Cython`, …):
```bash
cd epf-eink-addon && python -m pytest tests/ -v
```
The suite is self-contained (mocked Immich/HA, `tmp_path` filesystem, patched NTP/watchdog) —
 "**no network, no Immich, no ComfyUI needed**.

**Run the LIVE integration tier (L1 â needs a real Immich)**
```bash
cd epf-eink-addon && cp .env.example .env        # then fill in .env (git-ignored)
sh epf-eink-addon/run-live-tests.sh               # uses .env; builds the test image, then pytest tests/test_live.py
sh epf-eink-addon/run-live-tests.sh <url> [album]   # one-off override (those two values not read from .env)
```
It is **opt-in + auto-skip**: without `EPF_LIVE_TESTS=1` and a `.env`, the live tests skip (never
red), so the offline run is unaffected. Credentials come only from the git-ignored `.env` â
never bake them in.

" 
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
- **One vocabulary (2.3.2):** settings-form field names equal the **add-on option** names, and
  `settings()` reads them canonical-first with the pre-2.3.2 short name as a **legacy alias**
  (`form_field()`). The **runtime-YAML keys are unchanged** (`url`, `album`, `rotation`, `enhanced`,
  `strength`, nested `entity_id`) — do not "clean up" one side without the other, and keep the alias
  (stored configs and old bookmarks post the short names). The page labels each card with its channel
  (`runtime YAML` / `HA option`) and echoes the env-only secrets + `log_level` as read-only status —
  keep that, it is the only place the user can see which channel a value came from.
- A **global (source-independent) setting** - the date-stamp switch `date_overlay` is the example - lives
  at the **top level** of the runtime YAML, is edited on the settings page, and is seeded on first start
  from the matching add-on option through env. A POST that omits such a field must keep the stored value.

- The two files with `config.yaml` in the name are **different things**: the **add-on manifest**
  (`epf-eink-addon/config.yaml` — tracked, defines `options`/`schema`) vs the **runtime YAML**
  (`config/config.yaml` — git-ignored, created at runtime). Don't "refactor" one into the other.

---

## Testing

 Plain **pytest**, fully **mocked** (see `TESTSPEC.md` for the ASPICE cross-reference).
 .  Alongside this fully-offline suite there is an **opt-in live tier** (`tests/test_live.py`,
run via `sh epf-eink-addon/run-live-tests.sh`) that exercises a **real** Immich and, since 2.4.0, a
**real** ComfyUI server; it **auto-skips**
unless `EPF_LIVE_TESTS=1` and a `.env` are present, so it never turns the offline run red. See the
"Top-level goal" section above for how the layers fit together.
  Layout
mirrors the requirement catalog in `docs/requirements_specification_aspice.md`:

- `tests/conftest.py` — the `app_module` fixture (fresh import with env + NTP + watchdog patched,
  filesystem redirected to `tmp_path`) and `client_with_mocks` (Flask test-client with
  `responses`-mocked Immich: ping/albums/album-assets/asset-original).
- `tests/test_functional.py` — **FR-001…FR-033** (album/asset/selection/download/convert/
  scale+dither/overlay/preview/**delivery**/prepare/serve, the settings vocabulary (FR-021, incl. the
  2.4.1 "no rendered field name twice" guard and the shared-ComfyUI-block round trip) and the
  workflow-selection form (FR-033)).
- `tests/test_nonfunctional.py` — **NFR** (health, logging, response-time, memory, theme,
  typing) + **IFR** (Immich header, ESP32 interface, ingress ProxyFix, port) + **SEC** + **PER**.
- `tests/test_providers.py` — prompt-variable resolution, `GenerationTracker`, each Provider, the
  `create_provider` factory, multi-source integration, and the named-workflow selection (2.4.0).

The `Dockerfile.test` image bundles `fonts-dejavu-core` (for the date-overlay path) and
`tests/`, and its `CMD` is `run.test.sh` (pytest with `--junitxml`). **The report
(`docs/test_report_aspice.md`) is re-counted with each release — see §Gotchas for the current numbers
before quoting them.**

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
- **Images zoom in the one lightbox overlay** (`#lightbox`, dashboard previews and gallery thumbs
  both open it): the click FLIP-zooms the image out of the thumbnail it came from, `Esc` closes,
  `←`/`→` navigate the group (the three dashboard previews, or the gallery as rendered). Gallery
  anchors keep their `href` as the no-JS fallback, so the click handler must `preventDefault()`, and
  the overlay markup stays **outside** `#settingsForm` (one field name per config key, 2.4.1).
- **Docs & language split:**
  - **Code-facing docs** (`README.md`, `AGENTS.md`, `ARCHITECTURE.md`) are **English**;
    **analytical docs** (`ANALYSE.md`, `TESTSPEC.md`) and **working docs** (`plans/findings*.md`)
    are **German** — match the neighbour.
  - **Everything inside `epf-eink-addon/` is English** — user-facing text (the
    `templates/settings.html` UI: labels, tooltips, placeholders; the user-facing `README.md`;
    manifest descriptions; log messages) **and** code comments (`app.py`, `providers.py`,
    `Dockerfile`, `run.sh`, `setup.py`). German slipping in there (UI strings, Dockerfile
    comments, …) is a defect — if a string can ever reach a user's browser, it is English.

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

- **A standalone production-image smoke build is not the HA runtime.** `Dockerfile` copies the whole
  add-on directory, so a developer's local `config/config.yaml` and `photos/` get **baked into the
  image** when they exist in the build context (in HA the bind mount shadows them). Start the container
  through its normal s6 init and launch gunicorn via the **real** `with-contenv` path
  (`/package/admin/s6-overlay-*/command/with-contenv`; the `/usr/bin/with-contenv` symlink in this base
  image is dangling) - Docker's container environment reaches the main program only through it, so
  overriding `--entrypoint` (bash) loses the env and the app silently starts with empty secrets/URLs.
  Git-Bash also mangles leading-slash arguments; prefix `MSYS_NO_PATHCONV=1` or keep the path inside a
  quoted `-c` string. And `--env-file` wants strict `KEY=VALUE` lines: a CRLF `.env` puts the CR into
  the value, while the shell `source` the L1 harness uses strips it.

- **Line endings can break the test entrypoint on Windows.** Contributors here build with
  `core.autocrlf=true` and there is no repo-wide `eol` pin, so a Windows checkout materialises
  `.sh` files as **CRLF**; a CRLF shebang then makes a Docker `COPY run.test.sh /run.sh` plus
  `exec` fail with the misleading "no such file or directory" (the *interpreter* named by the
  mangled shebang is what is "missing"). Mitigated three ways: (1) `.gitattributes` forces
  `eol=lf` for `*.sh`/sources on checkout; (2) `Dockerfile.test` normalises the entrypoint
  **in-image** (strips trailing carriage returns) and runs it via an explicit `bash /run.sh`
  rather than a shebang; (3) `run.test.sh` is matched by a `.gitignore` pattern but **is tracked**
  (it is the documented test entrypoint), so the script itself is part of the committed robustness
  together with `.gitattributes` and the Dockerfile.

- **The production image cannot self-start outside Home Assistant.** `run.sh`'s shebang is
  `#!/usr/bin/with-contenv bashio`, and the HA base image has no `bashio` — the plain (non-supervised)
  container dies at `exec: fatal: unable to exec bashio`, and s6 strips the environment of services it
  starts (that is exactly what `with-contenv` exists to restore). For the **L3 smoke**, run the shipped
  image with the same gunicorn line through `with-contenv`, and pass secrets via `--env-file` with a
  **relative** path. Also: never hand Git-Bash an absolute container path (`/run.sh`) as an argument —
  MSYS rewrites it and Docker blames a "missing file".
- **Build context for the production `Dockerfile` is the add-on directory**, not the repo root
  (`cd epf-eink-addon && docker build -f Dockerfile -t epf-eink:local .`) — the `COPY` lines are
  relative to it; from the root it fails on `/run.sh`.

- **The Cython module is compiled at image-build time.** There is no `cpy.so` in the repo:
  both Dockerfiles run `python setup.py build_ext --inplace` (from `cpy.pyx`) during the build.
  Never hand-edit the `.so` — edit `cpy.pyx` and let the Docker build regenerate it.
 - **Immich image source speaks the v3 paged API.** `ImmichProvider` resolves the album via
  `GET /api/albums`, then lists assets with the **paginated `POST /api/search/metadata`**
  (size=1000) and downloads via `GET /api/assets/{id}/original` â the same v3 shape the
  standalone EPF moved to. (This supersedes an older note claiming a *legacy*
  `GET /api/albums/{id}` call; that call is gone.) **Re-prove it against a real server with the
  L1 live test** (`sh epf-eink-addon/run-live-tests.sh`) before a release â it is the only
  check that can catch an Immich-version API drift the offline mocks cannot.
- **`run.sh`'s startup gate is source-conditional** (14.4): the Immich credentials
  (`IMMICH_API_KEY` / `IMMICH_URL`) are fatal only when `image_source=immich`; a ComfyUI-only
  setup starts with no Immich values at all. When adding a new image source, mirror the same
  conditional block in `run.sh` (and keep the `config.yaml` schema in sync).
- **Colour-count regression trap.** The Waveshare 7.3-inch Spectra-6 panel and the
  `palette`/`epd_colors` arrays are **6 colours** (black/white/yellow/red/blue/green). All docs
  were unified to 6 in the 14.1 pass; if "7-colour" resurfaces anywhere, treat it as a regression.
- **The ASPICE test report must track the suite.** `docs/test_report_aspice.md` was re-baselined
  to the multi-source v2 suite in the 14.6 pass and is re-counted with each release (currently the
  **206 offline + 8 live = 214**-case suite, **2.5.0**, re-counted 2026-11-22 — **L0, L1 and the
  L3 production-image smoke all re-ran green on this code base on 2026-11-22** (report §6.10; the L3 run
  deliberately used a cap of 2 and three real preparations so the shipped per-shot pruner executed). If
  a PR adds or removes tests, update the
  report's counts in the same PR — the "100 %" claim silently rots otherwise (that is how 14.6 found
  the v1.1.0 drift). The gallery-history feature got **FR-032 / TC-FR-032** in the 2.3.0 pass, the
  named-workflow feature **FR-033 / TC-FR-033** in the 2.4.0 one, the 2.4.3 pass re-worded
  **FR-032 / TC-FR-032** for the per-shot gallery pruning, and the 2.5.0 in-page image zoom (Dashboard
  previews + Gallery) is written as a clause on **FR-026** — no new requirement ID, it is a control on
  an existing one (see the gallery unit note below).
- **One unit for the gallery cap (2.4.3).** `gallery_max_count` / `gallery_retention_days` count
  **shots** (whole `original` + `processed` pairs): `cleanup_gallery()` prunes through
  `_cleanup_previews_per_shot()`, which groups by shot id and judges a group by its newest member —
  the same measure `/api/gallery-previews` sorts and caps by, so the setting means one thing. The
  **live preview directory** cleanup (`POST /cleanup-previews`, `FR-024`) is deliberately different:
  it prunes **per pattern**, because that directory holds the single live slot, not groups. Do not
  "unify" the two. The lock is the cross-mtime test in `tests/test_gallery_history.py` — forcing the
  pruner back to per-pattern makes exactly that case fail (verified 2026-11-20), so never weaken it
  back to a case that passes under both semantics; the split was first seen in the field, not in the
  suite (report §6.3, closed in §6.7).

- **Fonts for the date overlay.** The prod `Dockerfile` installs `fonts-dejavu-core` (14.7)
  so the date overlay renders with the intended typeface; without it Pillow would silently fall
  back to the tiny bitmap default.
- **The settings form has one field name per config key (2.4.1).** It is a single `<form>`, so a name
  used twice means the browser submits both values and Flask keeps the first, and the second card's
  edit vanishes without an error (that is how a seed change did nothing on a real install). The settings
  the two ComfyUI sources share are rendered once, in the **ComfyUI - Common Settings** card; the guard
  is the test that no rendered field name appears twice. A duplicated *id* is harmless when the two
  elements live in mutually exclusive Jinja branches.
- **The form always sends its controls (2.4.3b).** "A POST that omits the field keeps the stored value"
  is the rule for *missing* fields — it does **not** cover an emptied one: an empty field overwrites,
  which is intended (a prompt must be clearable), so the page now **confirms before saving** a field
  that goes from stored to empty. A **workflow slot with content but no name** is likewise no longer
  dropped in silence — `parse_workflow_slots()` refuses it at save time, because that was the other
  half of the same complaint. Keep both; the functional suite names them.
- **ComfyUI workflow selection is YAML-owned (2.4.0).** The runtime YAML carries
  `comfyui.workflows` (a list of named entries) plus `comfyui.active_workflow`; the settings page
  shows a dropdown and four slots, and `parse_workflow_slots()` rebuilds the whole list from what the
  form posted — which is why a POST carrying **no** `wf_*` field must keep the stored list (there is
  a test for exactly that). The two add-on options only *seed* it. Only **API-format** graphs
  (`{id: {class_type, inputs}}`, what ComfyUI's "Save (Export)" produces) can be stored — ComfyUI's
  default UI save is refused at save time. Entry values win over globals; an unknown
  `active_workflow` falls back to the built-in graph with a warning. Reading a saved workflow *file*
  out of ComfyUI's `userdata` store over the API is still unsolved, so pasting the export is the
  supported path (phase 2 of the plan).
- **Two different `config.yaml` names** (manifest vs runtime) and a **`photos/` vs `IMMICH_PHOTO_DEST`**
  dir that holds `tracking.txt`, `generations.json`, the `latest_*.jpg` previews, and `latest.bmp`
  + `latest.status`. These live in the add-on's bind-mount; recreate the container without the
  mount and settings/history/reset.
- **`/download` returns `frame.txt`** (renamed from the base project's `.c`) as `text/plain`,
  2 hex-digit tokens (two 4-bit colour indices per byte), newline every 16, **no closing `};`**
  (the base EPF had one; removing it avoids the firmware's extra `0x00`). The firmware in the
  sibling repo parses token-by-token until EOF, so both forms work.

- **Footer version & build date are derived, never hand-edited (2.0.3).** `app.py` resolves
  `BUILD_VERSION` from (in priority order) the `ADDON_VERSION` build arg → the `config.yaml`
  manifest's `version:` field → `"dev"`, and `BUILD_TIMESTAMP` from the `BUILD_TIMESTAMP` env →
  the `.build_stamp` file written by the `Dockerfile` at image-build time → `"unknown"`.
  Release by bumping `version:` in `epf-eink-addon/config.yaml` only.

- **HA does not read git tags — the version number is the whole comparison.** The store compares the
  manifest's `version:` against the *installed* version, so a tag is a labelling step, not a release
  trigger. Consequence, hit for real on 2026-11-22: the `2.4.3` CHANGELOG entry is dated 20.11., but
  the 2.4.3b code (settings guards, warning dialog, CI) landed on 22.11. **under the same number** —
  so an install that pulled 2.4.3 in between shows *no pending update* while running without that
  code. The only remedy is **reinstall the add-on in HA** (a restart pulls no code). Cut the tag on
  the commit where the version's content is actually complete, and if code lands after the bump,
  say so in the changelog/plan instead of letting the number quietly cover it.

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
