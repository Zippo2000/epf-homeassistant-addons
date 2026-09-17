# EPF Home Assistant Add-ons

A **[Home Assistant add-on store](https://www.home-assistant.io/add-ons/)** that hosts
**`epf-eink-addon`** — an **E-Ink photo frame server** that runs *inside* Home Assistant and
feeds a battery-powered **ESP32 + Waveshare 7.3″ Spectra-6 (6-colour, 800×480)** frame.

It is the **Home Assistant version of [`Zippo2000/EPF`](https://github.com/Zippo2000/EPF)**:
the same "server does all the heavy lifting, the frame just wakes up, grabs a frame, sleeps"
design — repackaged as a supervised HA add-on and extended so the *picture* can come from
**three different sources**.

```
 ┌──────────────────────────── HOME ASSISTANT ───────────────────────────┐
 │  ┌───────────────────────────────────────────────────────────────────┐ │
 │  │  epf-eink-addon  (supervised container, gunicorn :5000)           │ │
 │  │                                                                     │ │
 │  │  ┌─────────┐   ┌────────────────┐   ┌─────────────────────────┐  │ │
 │  │  │  /health │   │   /download    │   │  Web UI  /  (ingress)   │  │ │
 │  │  └─────────┘   │  /sleep /api/*  │   │  settings / gallery     │  │ │
 │  │                  └───────┬────────┘   └─────────────────────────┘  │ │
 │  │        image source ──────┼─────────────────────────────────────────│ │
 │  │   ┌────────────┬──────────┴───────────┬───────────────┐             │ │
 │  │   │ Immich     │ ComfyUI via HA       │ ComfyUI       │             │ │
 │  │   │ (photos)   │ (ai_task service)    │ (direct API)  │             │ │
 │  │   └────┬───────┴──────────┬───────────┴──────┬────────┘             │ │
 │  └────────┼───────────────────┼──────────────────┼──────────────────────┘ │
 └───────────┼────────────────────┼──────────────────┼────────────────────────┘
             ▼                    ▼                  ▼
       Immich server       Home Assistant        ComfyUI server
             │                (GPU/AI)               (Stable Diffusion)
             ▼
   ┌──────────────────────────┐     LAN  HTTP   ┌────────────────────────────┐
   │   ESP32 frame (this       │ ───────────────► │  /download  → 6-colour     │
   │   sibling repo's firmware)│ ◄─────────────── │  hex frame  → e-paper      │
   │   wakes on RTC/button     │  /sleep → ms      └────────────────────────────┘
   └──────────────────────────┘
```

**Why the split?** The frame is 99 % of the time in deep sleep (~µA). All image acquisition
and per-pixel processing (scaling, colour/contrast, **Atkinson/Floyd–Steinberg dithering** — in
**Cython**) happens on the cheap x86/ARM server in the container, so a full frame refresh takes
seconds and the device barely sips power.

---

## What makes this different from the standalone EPF

| | Standalone `Zippo2000/EPF` | **This add-on** |
|---|---|---|
| Runs as | raw Docker container | **Home Assistant supervised add-on** (config via HA UI, web UI embedded via **ingress**) |
| Server | Flask dev server | **gunicorn** (2×2) |
| Image source | Immich only | **Immich · ComfyUI via HA · ComfyUI direct** (swappable in the UI) |
| Extras | — | `/health`, **prepare/deliver** decoupling, **preview gallery**, **dark mode**, per-day **AI generation cap** + tracking, CSP hardening |

> **Firmware is NOT in this repo.** The ESP32 firmware lives in the sibling
> [`Zippo2000/EPF/Arduino`](https://github.com/Zippo2000/EPF). Point its "server URL" at this
> add-on and it just works (same `/download` + `/sleep` contract).

---

## Repository layout

```
repository.yaml          # makes this a HA add-on store (name / url / maintainer)
epf-eink-addon/          # the add-on itself
  config.yaml            # add-on MANIFEST (options + schema; drives the HA config UI)
  build.yaml             # per-arch base images
  Dockerfile            # prod image (compiles the Cython dithering module, gunicorn, HEALTHCHECK)
  Dockerfile.test        # test image (runs the pytest suite)
  app.py                 # Flask app (routes, config, pipeline driver, battery, sleep, NTP)
  providers.py           # ImageProvider ABC + 3 sources + factory + GenerationTracker + prompt templates
  cpy.pyx  cpy.so        # Cython dithering (compiled at image build)
  run.sh                 # with-contenv bashio → exports options → starts gunicorn :5000
  run.test.sh            # pytest runner
  templates/settings.html# the web UI
  tests/                 # offline, fully-mocked pytest suite
  README.md              # ← the add-on's own user guide (full option reference)
docs/                    # formal ASPICE deliverables (requirements / architecture / test spec / report)
AGENTS.md · ARCHITECTURE.md · ANALYSE.md · TESTSPEC.md   # agent + deep-dive docs
```

---

## Installation

### 1. Add this repository to Home Assistant
* **GUI:** Settings → Devices & Services → Add-ons → ⋯ (Add-on Store) → **Add repository** →
  `https://github.com/Zippo2000/epf-homeassistant-addons`
* then **install** the **"E-Paper Photo Frame (EPF)"** add-on.

### 2. Configure it
Pick a **`image_source`** and fill in the matching fields (the config UI only shows the relevant
cards):

* **Immich** — `immich_url` (e.g. `http://192.168.1.100:2283`), `immich_api_key`, `album_name`.
* **ComfyUI via HA** — `ha_url`, `ha_api_token` (a long-lived HA token), a `comfyui_prompt`
  (supports `{time_of_day}`, `{weather}`, `{season}`, `{day_of_week}`, `{month}`, `{random_element}`),
  optional negative prompt / dimensions / seed / **daily generation cap**, and a `comfyui_entity_id`
  targeting your `ai_task.generate_image` entity.
* **ComfyUI direct (expert)** — `comfyui_direct_url` and, optionally, a custom `comfyui_workflow_json`
  (prompt/seed/size are injected into it).

> **Secrets are entered as add-on options and kept in the environment — never in the settings
> YAML.** The **web UI** (below) edits the *non-secret* display/photo settings live.

### 3. Point the ESP32 at it
In the frame's setup (captive portal), set the **server URL** to this add-on's address
(e.g. the HA host, or the **ingress** URL if you access the UI through HA). The frame then wakes
on its RTC/button schedule, fetches a frame, shows it, and sleeps.

---

## The web interface

Reachable two ways: **(a)** the **HA panel** (icon `mdi:image-frame`) via ingress, and
**(b)** the raw `:5000` port. It offers:

* **live health** (green/red dot — 60 s poll), **battery** (%/V + timestamp — 30 s poll),
  **current-photo status** (10 s poll);
* **"Prepare new photo"** (fetch + render a frame now, mark it *ready to deliver*), **"Cleanup old
  previews"**, and a **preview gallery**;
* a collapsible **configuration** section with per-source cards, sliders (colour enhance / contrast /
  dither strength), rotation, display mode (fit/fill), image order, dithering method, and the
  sleep window + wake-up interval — all saved without a page reload.

---

## Quick reference — how a refresh happens

1. RTC alarm or button wakes the **ESP32**.
2. If inside the sleep window → it calls **`/sleep`**, gets the **duration in ms**, and hibernates
   (no image). Otherwise it **`GET /download`** (header `batteryCap: <mV>`).
3. The server: if a *prepared-but-undelivered* frame exists → serve it (flip status
   `new → delivered`); else **fetch from the active source** → **scale/rotate** (Cython
   `load_scaled`) → **colour+contrast enhance** → **dither to 6 colours** (Cython Atkinson or
   Floyd–Steinberg) → **pack 2 pixels/byte as hex** → return as `text/plain`.
4. The frame writes the bytes straight to the panel, refreshes, and sleeps for `/sleep`'s value.

The full contract (request/response shapes, retry behaviour, invariants) is in
**[`ARCHITECTURE.md`](ARCHITECTURE.md)**; the weaknesses, the "7-vs-6-colour" doc bug, the
legacy-Immich-endpoint question, and recommendations are in **[`ANALYSE.md`](ANALYSE.md)**;
how to test without any external service is in **[`TESTSPEC.md`](TESTSPEC.md)** and
[`AGENTS.md`](AGENTS.md).

---

## Requirements / docs map

| Doc | Language | What it answers |
|-----|----------|-----------------|
| [`epf-eink-addon/README.md`](epf-eink-addon/README.md) | English | add-on user guide (every option) |
| [`README.md`](README.md) (this file) | English | the store + system overview |
| [`AGENTS.md`](AGENTS.md) | English | how to build/test/**not break** it |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | English | sources→provider→pipeline→ESP32 contract + HA deployment |
| [`ANALYSE.md`](ANALYSE.md) | **German** | full technical analysis + weaknesses |
| [`TESTSPEC.md`](TESTSPEC.md) | **German** | test model, tiers, how to run |
| [`docs/`](docs/) | mixed | formal **ASPICE** deliverables (requirements EPF-REQ-001, architecture EPF-ARC-001, test spec EPF-TST-001, report EPF-RPT-001) |

---

## License

[MIT](LICENSE). The image-processing pipeline and overall concept descend from
[`Zippo2000/EPF`](https://github.com/Zippo2000/EPF) (itself derived from jwchen119's
FireBeetle e-paper frame). The Cython module, Waveshare panel driver and the captured
Wi-Fi/portal code in the *sibling* repo retain their original licenses.
