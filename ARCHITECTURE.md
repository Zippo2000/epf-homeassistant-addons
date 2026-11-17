# Architecture & Interfaces

How the moving parts talk to each other in the **`epf-eink-addon`** Home Assistant add-on.
Read alongside [`README.md`](README.md) (product view), [`ANALYSE.md`](ANALYSE.md) (deep dive),
and the formal [`docs/architecture_document.md`](docs/architecture_document.md) (ASPICE SYS.3/SWE.2).

The system has **four actors**, one of which (the add-on server) is the brain and the
*only* place image processing happens:

```
                         ┌──────────────────────────  HOME ASSISTANT  ──────────────────────────┐
                         │  ┌───────────────────────────────────────────────────────────────┐  │
  photos  ┌───────────┐  │  │  epf-eink-addon (supervised container)                         │  │
──────────►│  IMMICHE   │  │  │                                                              │  │
           │  REST API  │  │  │   ┌────────────┐   ┌──────────────┐   ┌─────────────────┐  │  │
           └───────────┘  │  │   │  ImageProvider│  │  image        │   │  web UI (/)     │  │  │
                           │  │   │  (factory)    ├──►  pipeline    ├──►  settings/gallery │  │  │
  AI image ┌────────────┐  │  │   │  ├ Immich    │  │  (Cython      │   │  + health +     │  │  │
──────────►│  HOME        │  │  │   │  ├ ComfyUI  │  │   dither)      │   │  battery +      │  │  │
           │  ASSISTANT  │  │  │   │  │  HA svc   │  │  + 6-colour   │   │  prep/deliver   │  │  │
           │ (ai_task)    │  │  │   │  └ ComfyUI  │  │   packing      │   └─────────────────┘  │  │
           └────────────┘  │  │   │    Direct     │  └──────────────┘                            │  │
  AI image ┌────────────┐  │  │   └────────────┘                                                    │  │
──────────►│  COMFYUI    │  │  │                                                                     │  │
           │  server API  │  │  │   gunicorn :5000  (ingress + raw port)                              │  │
           └────────────┘  │  └───────────────────────────────┬───────────────────────────────────┘  │
                           └───────────────────────────────────┼──────────────────────────────────────┘
                                                                 │  LAN HTTP (trusted)
                                                                 ▼
                                              ┌─────────────────────────────────────┐
                                              │  ESP32 FRAME (sibling repo)         │
                                              │  WROOM + Waveshare 7.3" Spectra-6   │
                                              │  800×480, 6-colour + battery + btn  │
                                              │  wakes (RTC/button) → hibernate      │
                                              └─────────────────────────────────────┘
```

## Roles

* **Immich** — the self-hosted photo library. The **`ImmichProvider`** is its *client*: it
  resolves one **album by name**, walks its assets (ordered *random* or *newest*), downloads one
  **original**, and tracks which asset IDs it has already shown (`tracking.txt`).
* **Home Assistant** — plays two roles: (1) the **supervisor** that hosts the add-on and passes its
  **options** to it (via `bashio`, as env vars); (2) the **AI gateway** — when the source is
  *ComfyUI-via-HA*, the add-on calls HA's `ai_task.generate_image` service (a long-lived **HA token**
  authenticates) to synthesise a picture.
* **ComfyUI (direct)** — an expert-mode alternative: the **`ComfyUIDirectProvider`** posts a workflow
  to a raw ComfyUI `/prompt`, polls `/history/<id>` until an output image appears, and downloads it
  from `/view`.
* **The add-on server** (this repo) — the brain. On each device request it: picks a source image
  (through whichever provider is active), runs the **image pipeline**, and serves the frame to the
  frame. It owns the sleep schedule, the battery report, the health check, the preview/gallery, and
  the config. **All per-pixel work happens here, in Cython** — the frame stays dumb.
* **ESP32** — a thin HTTP client + display driver. Keeps a base URL (written by its captive
  portal), fetches one frame and a sleep duration over the LAN, drives the panel, hibernates.
  **No image processing**, **no credentials**.

---

## Interface A — Provider ⇄ Immich  (REST)

Transport: HTTP(S) to the Immich box; **auth via the `x-api-key` header** (read +
`asset.download`). Base = `immich.url` (from config) / `IMMICH_URL` (env). Target album =
`immich.album` (matched **by name**).

| Step | Call | Purpose / key fields |
|------|------|-----------------------|
| 1 | `GET {url}/api/albums` | Catalogue. The provider matches one by **`albumName`** to get the album `id`. |
| 2 | `GET {url}/api/albums/{id}` | Returns `{ "assets": [ {id, originalPath, exifInfo:{dateTimeOriginal}, …} ] }`. **⚠ This is the *legacy* album endpoint** — the standalone EPF already migrated to the v3 **paged `POST /api/search/metadata`**. If a target Immich retires the legacy route, this breaks (see ANALYSE). |
| 3 | `GET {url}/api/assets/{id}/original` (stream) | Raw bytes of the chosen asset (RAW/HEIC/JPEG decoded server-side). |
| 4 | `GET {url}/api/server/ping` | Used by the **health check** only. |

Selection is decided **server-side**: *newest* → descending `dateTimeOriginal`, or *random*; a
`tracking.txt` of already-shown IDs makes it "no repeat until the album is exhausted", then resets.

---

## Interface B — Providers ⇄ ComfyUI  (AI generation)

Both ComfyUI paths obey a shared **rate limit** (`comfyui.max_generations_per_day`) enforced by a
`GenerationTracker` that persists a JSON history (`generations.json`) and counts entries for "today".

**B1 — via Home Assistant** (`ComfyUIHAProvider`)
* `POST {ha_url}/api/services/ai_task/generate_image?return_response=true`
  *headers:* `Authorization: Bearer <HA_API_TOKEN>`; *body:* `{ "task_name": "Image",
  "instructions": <resolved prompt>, "entity_id": <COMFYUI_ENTITY_ID> }`.
* The prompt supports **template variables** resolved at call time: `{time_of_day}` (hour→phase map),
  `{weather}` (random), `{season}` (month→season map), `{day_of_week}`, `{month}`, `{random_element}`.
* The response is parsed defensively for several shapes: `service_response.url` (relative → prefixed
  with `ha_url`), `service_response.media_source_id` (→ raises "direct URL not available"),
  a raw base64 `image_data`, a top-level `url`, or an `images[]` list. The image is downloaded and
  run through the normal pipeline.

**B2 — direct** (`ComfyUIDirectProvider`)
* **Named workflows (2.4.0):** the runtime YAML holds a list `workflows` (`name` plus optional
  `api_json`, prompt/negative, node mapping, sampling) and `active_workflow`, which names the entry
  to run; the settings page edits both and the choice takes effect on the next generation without a
  restart. An entry's own values win over the globals; an unknown selection falls back and warns.
* Build a workflow: the selected entry's `api_json` → the single `comfyui_workflow_json` field → the
  **built-in** `KSampler` graph (checkpoint: option, else auto-detected via
  `/object_info/CheckpointLoaderSimple`, 2.3.1). `POST {url}/prompt` `{prompt, client_id}` →
  `prompt_id`.
* Prompt/seed/dimensions are injected into the graph: explicit **node mapping** from the entry first
  (`prompt_node`/`prompt_input`, `negative_node`/`negative_input`, `seed_node`), then the generic scan
  of `CLIPTextEncode` `text`/`text_g` and `KSampler` inputs. Entry-level
  `steps`/`cfg`/`sampler`/`scheduler` override the graph's own values; a pasted graph keeps them
  otherwise.
* **API format only** — what ComfyUI's "Save (Export)" produces (`{node id: {class_type, inputs}}`).
  The format ComfyUI stores by default is a UI graph (`nodes`/`links`) and cannot be posted; the
  settings page refuses it at save time instead of failing during generation.
* Poll `GET {url}/history/{prompt_id}` every 2 s (≤ 300 s) until an output `images[].filename`
  appears, then `GET {url}/view?filename=&type=output`.
* **B1** requires a reachable HA with the `ai_task` integration; **B2** only a raw ComfyUI.

---

## Interface C — ESP32 ⇄ Add-on  (device ↔ Flask, over the trusted LAN)

The device keeps a base URL in its NVS (from the captive portal, in the sibling repo) and speaks
plain HTTP/S. Two endpoints matter (both also used by the browser).

### `GET {base}/download`  — one ready-to-show frame
* **Request header from the device:** `batteryCap: <millivolts>` — folded into the battery report.
* **Response `200`:** the dithered frame as **`text/plain`**, filename **`frame.txt`** — a
  two-digit-uppercase-hex token per packed byte (see *Data formats*). **No `X-Photo-Url` header** in
  this add-on (the base EPF's planned NFC link was dropped).
* **Errors:** `500` `{"error": "…"}` on provider/network/processing failure.
* **Deliver model:** if a frame is already **prepared** (`latest.status == "new"`), it is served as-is
  and flipped to `"delivered"` (cheap, no re-fetch). Otherwise it is **fetched + processed on the
  fly**, the three preview JPEGs + `latest.bmp` are stored, then served. Either way the frame is the
  source of the panel bytes.

### `GET {base}/sleep`  — how long to hibernate
* **Request:** `Accept: application/json`. **Response `200`** (the firmware consumes `sleep_duration`):
  ```json
  { "sleep_duration": 203400000, "current_time": "…", "next_wakeup": "…" }
  ```
  `sleep_duration` in **ms**; computed from the **`wakeup_interval`** grid (round-up) clamped by the
  **sleep window** (`sleep_start..sleep_end`, midnight-span aware). Inside the window → wake at
  `sleep_end`; otherwise at the next interval slot. The container **TZ** (set as an add-on option if
  you need non-UTC) governs this — mirror the base EPF caveat.

---

## Interface D — Browser / Home Assistant ⇄ Add-on

* **Ingress:** `config.yaml` declares `ingress: true` + `ingress_port: 5000` +
  `panel_icon: mdi:image-frame` + `webui: http://[HOST]:[PORT:5000]`. `run.sh` exports
  `INGRESS_PATH=/api/hassio_ingress`, and `app.py` installs **`ProxyFix(x_for/x_proto/x_host/
  x_prefix)`** so the UI works correctly under HA's reverse proxy (both HTTP and HTTPS).
* **Gunicorn:** `2 workers × 2 threads`, 120 s timeout, binding `0.0.0.0:5000` (`run.sh`).
* **Docker `HEALTHCHECK`** (30 s / 10 s / 60 s start / 3 retries) probes **`GET /health`**, which
  pings the **active provider**'s connectivity — returning `503` when the source is unreachable.
* **The web UI** (`/`, `settings.html`) is the full control surface — source cards, sliders,
  sleep window, **health** (60 s), **battery** (30 s), **photo status** (10 s) polling, and the
  **prepare / cleanup / gallery** actions. It also persists a **dark/light theme** in `localStorage`.

### Other HTTP endpoints (catalogue)
| Method | Path | Purpose |
|--------|------|---------|
| GET/POST | `/` | Settings web UI (render / save). POST builds the config, **validates rotation ∈ {0,90,180,270}**, writes the YAML, hot-reloads, redirects. |
| GET/HEAD | `/health` | Source-agnostic health (200 / 503) — also the Docker health target. |
| GET | `/download` | Frame to the ESP32 (see Interface C). |
| POST | `/prepare-photo` | Manually fetch+process a frame now, set status `new`, store 3 previews. |
| GET | `/preview-photo` `/preview-original` `/preview-processed` `/preview-delivered` | Serve the respective preview JPEG. |
| GET | `/preview-status` | `{exists, status, timestamp, formatted_time}` for the current frame. |
| GET | `/api/battery-status` | Voltage/percentage/last-read. |
| GET | `/api/generation-status` | ComfyUI: today's count, cap, last generation (else zeros). |
| GET | `/api/gallery-previews` | List of preview files (newest first) for the gallery. |
| GET | `/preview-file/<name>` | One preview by file name. |
| POST | `/cleanup-previews` | Run the age(7 d)/count(50) evictor on the preview files. |
| GET | `/sleep` | Hibernate duration (see Interface C). |

---

## One display cycle (end to end)

```
[deep sleep, µA] ── RTC alarm / button ──▶
  GET /sleep
     in-window?  → hibernate(sleep_duration)            [no image]
     otherwise   → read battery mV
  GET /download  (header batteryCap:<mV>)
     ├ status=="new"  → serve pre-prepared frame, flip →"delivered"
     └ otherwise       → provider.fetch_image() → pipeline → 3 previews + BMP → serve, "delivered"
  → frame writes bytes to panel → TurnOnDisplay → panel Sleep
  → hibernate(/sleep's ms)
```

---

## Data format (the wire contract, EPF → ESP32)

The Spectra-6 panel is **6-colour**; each pixel is a **4-bit palette index** (0…6: black, white,
yellow, red, blue, green — with a small `>3 → +1` remap in the de-palette step that lands the four
chromatic colours on fixed slots). **Two pixel indices are packed into one byte** (left in the high
nibble), so `800 × 480 = 384 000` pixels → **192 000 bytes**. Those are serialised as **two-digit
uppercase-hex tokens** separated by commas, with a **newline every 16 tokens** and **no trailing
`};`** (the base EPF emitted a `};`; dropping it avoids the firmware's extra `0x00`). The firmware
parses each token with `strtol(…,16)` and feeds the panel **one byte at a time** — a direct match.
Size ≈ **576 KB** of text per refresh.

> **Keep-in-sync invariant:** the 800×480 geometry, the **4-bit index width**, the packing/byte
> order, and the *slot assignment of the six colours* must agree between this server and the
> firmware's parser. Change colour depth/packing on either side and redeploy both together. (The
> 6-vs-"7-colour" wording drift is a **doc bug**, not a code difference — see ANALYSE.)

---

## Deployment invariants (the coupling points)

1. **Config is two-channel** (env-seeded defaults + runtime YAML). Secrets ⇒ env only; photo/display
   settings ⇒ the mounted `config/config.yaml` (hot-reloaded). Changing a source or a secret ⇒
   **change the add-on option + restart**; the web UI does **not** write secrets.
   Since 2.3.2 the settings form uses the **same names as the add-on options** (`immich_url`,
   `album_name`, `rotation_angle`, `color_enhance`, `dithering_strength`, `comfyui_entity_id`, …); the
   keys inside the runtime YAML are the historical short ones (`url`, `album`, `rotation`, `enhanced`,
   `strength`) and are **not** renamed — `settings()` resolves canonical-name-first with the short name
   as a legacy alias (`form_field()`). Keep that alias: stored configs and old bookmarks post it. The
   page labels each card with its channel and echoes the env-only secrets as read-only status.
   Since 2.4.1 the form also has **one field name per config key** — it is a single `<form>`, so a name
   used twice means one of the two values is silently dropped (the browser submits both, Flask keeps the
   first). The six settings both ComfyUI sources share (prompt, negative prompt, width/height, seed,
   daily maximum) are therefore rendered once, in a **ComfyUI — Common Settings** card, and each source
   card keeps only its own fields. A regression test asserts no rendered name appears twice.
   Since 2.4.0 the same applies to the **named ComfyUI workflow list**: it lives in the runtime YAML,
   the add-on options (`comfyui_workflows`, `comfyui_active_workflow`) only seed the first start, and
   a POST that carries no workflow fields must never wipe a stored list.
   Since 2.4.2 the runtime YAML also carries **global, source-independent settings at the top level** —
   `date_overlay` (draw the photo's EXIF date, default on) is the first of them. The settings page owns
   those; the matching add-on option (`date_overlay` → `DATE_OVERLAY`) only seeds the first start, and a
   POST that omits the field keeps the stored value (silence is not a click). Do not move such a key
   into a source section — the panel shows it under Display Settings precisely because it applies to
   every source.
2. **One active provider at a time**, chosen by `image_source` and rebuilt by `reset_provider()` on
   every config change. `/health` and `/api/generation-status` are source-agnostic in that they
   interrogate whichever provider is active.
3. **Ingress + ProxyFix** is what makes the UI and the raw-port behaviour identical under HA; don't
   "simplify" the `ProxyFix` line away.
4. **The container is only "healthy" when the source is reachable** (HEALTHCHECK → `/health`). That
   is a deliberate choice (see ANALYSE for the trade-off) — a down Immich shows as an *unhealthy
   container*, even though the app itself is fine.
