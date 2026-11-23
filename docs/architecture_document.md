# System & Software Architecture (ASPICE SYS.3 / SWE.2)

**Project:** EPF Home Assistant Add-ons Repository  
**Document ID:** EPF-ARC-001  
**Version:** 2.5.0  
**Date:** 2026-11-23  
**Baseline:** Repository commit (main branch) — code base **v2.5.0**: the v1.1.0 §14 remediation, the UI track (2.1.0–2.1.2), gallery history (2.2.0/2.2.1), gallery options (2.3.0), checkpoint resolution (2.3.1), settings vocabulary (2.3.2), named workflows (2.4.0), duplicate-field fix (2.4.1), date-stamp switch (2.4.2), per-shot gallery pruning (2.4.3), settings guards + CI (2.4.3b), in-page image zoom (2.5.0)  
**Status:** Released — re-baselined in this pass

> **Revision 2.5.0 (2026-11-23):** this pass brings EPF-ARC-001 up to the code it documents — it
> had frozen at v2.0.0 (2026-04-03). **IFC-001** now shows the Immich calls the provider actually
> makes (`POST /api/search/metadata`, v3 and paginated — the correction the 14.4 pass promised and
> never delivered); the endpoint catalog gained `/cleanup-previews`, `/api/gallery-previews` and
> `/preview-file/<filename>`; C-005, C-007 and C-011 describe the dual config channel, the gallery
> archive with per-shot pruning and the shared in-page lightbox; §6.4 adds the gallery/zoom flow;
> §14 adds D-013…D-016; §12 traceability now reaches FR-025…FR-033 and NFR-010; AC-001 is closed
> (the `.so` is compiled at image build). Section numbers after §13 are put back in order.
> The duplicated C-013…C-018 blocks stay — both copies describe the same components (note in §4.2).

---

## 1. Introduction

### 1.1 Purpose
This document describes the system and software architecture of the EPF (E-Paper Photo Frame) Home Assistant Add-on in accordance with ASPICE processes SYS.3 (System Architectural Design) and SWE.2 (Software Architectural Design). It documents the current architectural state as implemented in the repository.

### 1.2 Scope
The architecture covers the single add-on `epf-eink-addon` including its container definition, application components, external system interfaces, data flows, and deployment topology within the Home Assistant ecosystem.

### 1.3 References
- EPF-REQ-001: Requirements Specification (ASPICE SWE.1/SYS.2)
- ASPICE v3.1 Process Reference Model
- Home Assistant Add-on Specification
- Docker Container Architecture

---

## 2. Architectural Goals and Constraints

### 2.1 Goals
- **G-001:** Provide a seamless bridge between photo sources (Immich, ComfyUI) and ESP32-based E-Ink display hardware
- **G-002:** Optimize images for 6-color E-Ink displays using performant Cython-compiled dithering algorithms
- **G-003:** Integrate natively into Home Assistant with configuration via HA UI and Ingress web interface
- **G-004:** Support power-efficient operation through configurable sleep schedules and ESP32 deep-sleep coordination
- **G-005:** Enable multi-architecture deployment (ARM and x86) via Home Assistant build system
- **G-006:** Support multiple image sources (Immich, ComfyUI via HA, ComfyUI Direct) through a provider abstraction layer
- **G-007:** Enable AI-generated images with configurable prompt templates and daily generation limits
- **G-008:** Keep the browser side honest and quiet — source-health, battery and generation panels, an archived gallery, and an in-page image zoom (lightbox, 2.5.0) instead of extra windows

### 2.2 Constraints
- **C-001:** Must operate as a Home Assistant supervised Docker container
- **C-002:** Must use the Home Assistant bashio configuration API for runtime configuration
- **C-003:** E-Ink display hardware is fixed at 800x480 pixels, 6-color palette (Waveshare 7.3inch)
- **C-004:** ESP32 client firmware expects a specific hex-encoded pixel format (4-bit per pixel, packed)
- **C-005:** Cython module must be compiled during Docker build for each target architecture

---

## 3. System Context Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Home Assistant Host                         │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │              Docker Container (epf-eink-addon)             │     │
│  │                                                           │     │
│  │  ┌─────────────────────────────────────────────────────┐  │     │
│  │  │              Gunicorn WSGI Server                    │  │     │
│  │  │              (2 workers, 2 threads)                  │  │     │
│  │  │                      :5000                           │  │     │
│  │  └──────────────────────┬──────────────────────────────┘  │     │
│  │                         │                                  │     │
│  │  ┌──────────────────────▼──────────────────────────────┐  │     │
│  │  │              Flask Application (app.py)              │  │     │
│  │  │  ┌─────────────┐ ┌─────────────┐ ┌───────────────┐  │  │     │
│  │  │  │ Image       │ │ Config      │ │ Preview &     │  │  │     │
│  │  │  │ Processing  │ │ Management  │ │ Status API    │  │  │     │
│  │  │  │ Pipeline    │ │ (watchdog)  │ │               │  │  │     │
│  │  │  └──────┬──────┘ └─────────────┘ └───────────────┘  │  │     │
│  │  │         │                                            │  │     │
│  │  │  ┌──────▼──────┐                                    │  │     │
│  │  │  │ Cython      │                                    │  │     │
│  │  │  │ Module      │                                    │  │     │
│  │  │  │ (cpy.so)    │                                    │  │     │
│  │  │  └─────────────┘                                    │  │     │
│  │  └─────────────────────────────────────────────────────┘  │     │
│  └───────────────────────────────────────────────────────────┘     │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────┐     │
│  │              Home Assistant Supervisor                     │     │
│  │  - Configuration API (bashio)                              │     │
│  │  - Ingress Proxy (/api/hassio_ingress/)                    │     │
│  │  - Container Lifecycle Management                          │     │
│  └───────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
         │                              │                    │
         │ HTTP/HTTPS                   │ HTTP               │ HTTP
         ▼                              ▼                    ▼
┌─────────────────┐          ┌──────────────────┐  ┌──────────────────┐
│  Immich Server  │          │  ESP32 E-Paper   │  │  HA Web Browser  │
│  (Photo Library)│          │  Frame Client    │  │  (Settings UI)   │
└─────────────────┘          └──────────────────┘  └──────────────────┘
```

---

## 4. Component Architecture

### 4.1 Logical Component Decomposition

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        EPF E-Ink Add-on (Logical View)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    PRESENTATION LAYER                                │   │
│  │  ┌───────────────────┐  ┌───────────────────┐  ┌────────────────┐  │   │
│  │  │ Settings UI       │  │ Preview Grid      │  │ Theme Engine   │  │   │
│  │  │ (settings.html)   │  │ (3-column)        │  │ (dark/light)   │  │   │
│  │  └───────────────────┘  └───────────────────┘  └────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌─────────────────────────────────▼─────────────────────────────────────┐   │
│  │                    APPLICATION LAYER (Flask)                           │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │   │
│  │  │ Image        │ │ Config       │ │ Battery      │ │ Power        │ │   │
│  │  │ Delivery     │ │ Management   │ │ Monitoring   │ │ Management   │ │   │
│  │  │ Controller   │ │ Controller   │ │ Controller   │ │ Controller   │ │   │
│  │  │ /download    │ │ /settings    │ │ /api/battery │ │ /sleep       │ │   │
│  │  │ /prepare     │ │              │ │              │ │              │ │   │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ │   │
│  └─────────┼────────────────┼────────────────┼────────────────┼─────────┘   │
│            │                │                │                │              │
│  ┌─────────▼────────────────▼────────────────▼────────────────▼─────────┐   │
│  │                    SERVICE LAYER                                      │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │   │
│  │  │ Immich       │ │ Image        │ │ Tracking     │ │ Preview      │ │   │
│  │  │ Client       │ │ Processing   │ │ Service      │ │ Generator    │ │   │
│  │  │ Service      │ │ Pipeline     │ │              │ │              │ │   │
│  │  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ │   │
│  └─────────┼────────────────┼────────────────┼────────────────┼─────────┘   │
│            │                │                │                │              │
│  ┌─────────▼────────────────▼────────────────▼────────────────▼─────────┐   │
│  │                    DATA ACCESS LAYER                                  │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │   │
│  │  │ File System  │ │ Config YAML  │ │ Tracking     │ │ Photo Store  │ │   │
│  │  │ I/O          │ │ Reader       │ │ File I/O     │ │ (/photos/)   │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    INFRASTRUCTURE LAYER                              │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │   │
│  │  │ Cython       │ │ NTP Client   │ │ Logging      │ │ Gunicorn     │ │   │
│  │  │ (cpy.so)     │ │ (daemon)     │ │ (stdout)     │ │ WSGI Server  │ │   │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

> *The diagram above is the v1.x picture and shows the Immich client as a single service; the
> provider layer (C-013 … C-018) is what the code does since v2.0.0, and the Web Settings UI block
> now also carries the gallery grid and the shared in-page image overlay (lightbox, 2.5.0).*

### 4.2 Component Descriptions

> *C-013 … C-018 are listed twice below: the provider block was appended during the multi-source
> pass and the original list was kept. Both copies describe the same components and are kept in
> sync — edit both or neither (same convention as the duplicated TC blocks in EPF-TST-001).*

#### C-001: Flask Application Core (app.py)
| Attribute | Value |
|-----------|-------|
| **Name** | Flask Application Core |
| **Type** | Application Framework |
| **Responsibility** | HTTP request routing, request/response handling, Blueprint registration, WSGI application entry point |
| **Dependencies** | Flask, Werkzeug, PyYAML, requests, watchdog, ntplib |
| **Provided Interfaces** | HTTP endpoints (see Section 5) |
| **Required Interfaces** | Immich REST API, File System, Cython module |

#### C-002: Image Processing Pipeline
| Attribute | Value |
|-----------|-------|
| **Name** | Image Processing Pipeline |
| **Type** | Service Component |
| **Responsibility** | End-to-end image transformation: format conversion, scaling, rotation, enhancement, dithering, date overlay, preview generation, hex encoding |
| **Key Functions** | `scale_img_in_memory()`, `save_three_previews()`, `convert_to_hex_format()`, `depalette_image()` |
| **Dependencies** | Cython module (cpy.so), Pillow, numpy, rawpy, pillow-heif |
| **Design Rationale** | Separation of Python orchestration and Cython computation enables performance-critical operations (dithering, scaling) to run at near-C speed while maintaining Python flexibility for business logic. |

#### C-003: Cython Module (cpy.pyx / cpy.so)
| Attribute | Value |
|-----------|-------|
| **Name** | Cython Image Processing Module |
| **Type** | Native Extension |
| **Responsibility** | High-performance image scaling, rotation, Floyd-Steinberg dithering, Atkinson dithering, closest-color matching |
| **Key Functions** | `load_scaled()`, `convert_image()`, `convert_image_atkinson()`, `closestColor()`, `closestColor_Atkinson()` |
| **Constants** | EPD_W=800, EPD_H=480, 6-color E-Ink palette |
| **Design Rationale** | Cython provides C-level performance for pixel-by-pixel dithering algorithms that would be prohibitively slow in pure Python. The module is compiled during Docker build for each target architecture. |

#### C-004: Immich Client Service
| Attribute | Value |
|-----------|-------|
| **Name** | Immich Client Service |
| **Type** | External Service Adapter |
| **Responsibility** | Communicate with Immich REST API for album listing, asset retrieval, image download, and health checking |
| **Key Functions** | HTTP requests to `/api/albums` (resolve the album by name), `POST /api/search/metadata` (v3, paginated asset list with `withExif`), `/api/assets/{id}/original`, `/api/server/ping` — the legacy `GET /api/albums/{id}` response shape is gone (Immich v3) |
| **Dependencies** | requests library, environment variables (IMMICH_API_KEY, IMMICH_URL) |
| **Error Handling** | Timeout-based (10-30s), HTTP status code validation, JSON error responses |

#### C-005: Configuration Management
| Attribute | Value |
|-----------|-------|
| **Name** | Configuration Management |
| **Type** | Service Component |
| **Responsibility** | Dual-mode configuration: (1) Environment variable injection at startup via bashio, (2) Hot-reload via watchdog file observer on config/config.yaml |
| **Key Classes** | `ConfigFileHandler(FileSystemEventHandler)`, `update_app_config()`, `form_field()` (canonical name + legacy alias), `parse_workflow_slots()` |
| **Design Rationale** | The dual-mode approach allows initial configuration through Home Assistant UI (which sets environment variables) while enabling runtime changes through direct YAML edits or the web settings form. The watchdog observer provides near-instant hot-reload without application restart, and a reload also rebuilds the active provider. Secrets come from the environment only — never from the runtime YAML. |
| **One vocabulary (2.3.2)** | Settings-form field names equal the HA add-on option names (canonical first, legacy short name as alias); the runtime YAML keys stay as they are. A POST that omits a field keeps the stored value; an emptied field overwrites — which the form confirms before saving (2.4.3b). |
| **Channels on the form (2.3.2)** | Each card is labelled `runtime YAML` or `HA option`, and the env-only secrets plus `log_level` are echoed read-only — the only place a user can see which channel a value came from. |

#### C-006: Tracking Service
| Attribute | Value |
|-----------|-------|
| **Name** | Image Tracking Service |
| **Type** | Data Management Component |
| **Responsibility** | Track which images have been shown to prevent repetition; manage album-specific tracking state |
| **Key Functions** | `load_downloaded_images()`, `save_downloaded_image()`, `reset_tracking_file()` |
| **Storage** | Plain text file `tracking.txt` with album name header and one asset ID per line |

#### C-007: Preview Generator
| Attribute | Value |
|-----------|-------|
| **Name** | Preview Generator |
| **Type** | Service Component |
| **Responsibility** | Generate and serve the three live-slot previews (original, processed, delivered) plus the status file, keep the archived gallery history (FR-032) and prune both directories |
| **Key Functions** | `save_three_previews()`, `_shot_id()`, `_archive_previews()`, `_gallery_groups()`, `cleanup_gallery()`, `_cleanup_previews_per_shot()`, `cleanup_old_previews()`, preview route handlers |
| **Output Files** | live slot: `latest_original.jpg`, `latest_processed.jpg`, `latest.bmp`, `latest_delivered.jpg`, `latest.status`; archive: `gallery/<shotid>_original.jpg` + `gallery/<shotid>_processed.jpg` (2.2.0) |
| **Pruning (2.4.3)** | The gallery is pruned **per shot** — groups are judged by their newest member, the same measure `/api/gallery-previews` sorts and caps by, so `gallery_max_count` / `gallery_retention_days` mean one thing. The live-slot directory keeps **per-pattern** pruning (`POST /cleanup-previews`), because it holds a single slot and no groups. |

#### C-008: Power Management Service
| Attribute | Value |
|-----------|-------|
| **Name** | Power Management Service |
| **Type** | Service Component |
| **Responsibility** | Calculate ESP32 sleep durations based on configurable wakeup intervals and sleep time windows |
| **Key Functions** | `get_sleep_duration()` route with interval alignment and sleep window deferral logic |
| **Design Rationale** | The sleep calculation aligns wakeups to interval boundaries (e.g., every 6 hours on the hour) while deferring wakeups that fall within the configured sleep window. This enables the ESP32 to use deep sleep for maximum battery efficiency. |

#### C-009: Battery Monitor
| Attribute | Value |
|-----------|-------|
| **Name** | Battery Monitor |
| **Type** | Service Component |
| **Responsibility** | Track and report battery voltage/percentage from ESP32 client; provide voltage-to-percentage lookup for lithium battery discharge curve |
| **Key Functions** | `calculate_battery_percentage()`, `/api/battery-status` endpoint |
| **Data Source** | `batteryCap` HTTP header from ESP32 `/download` requests |

#### C-010: NTP Synchronizer
| Attribute | Value |
|-----------|-------|
| **Name** | NTP Synchronizer |
| **Type** | Background Daemon |
| **Responsibility** | Maintain accurate system time via daily NTP synchronization |
| **Key Functions** | `run_daily_ntp_sync()` daemon thread |
| **Schedule** | Daily at 04:00, retry after 3600s on failure |

#### C-011: Web Settings UI
| Attribute | Value |
|-----------|-------|
| **Name** | Web Settings Interface |
| **Type** | Presentation Component |
| **Responsibility** | Provide responsive HTML interface for configuration, photo preview, and manual photo preparation |
| **Technology** | Jinja2 templates, vanilla JavaScript, CSS custom properties |
| **Features** | 3-column preview grid, gallery tab (one card per shot, FR-032), dark/light theme (NFR-008), battery status and source-health panels (FR-025), source cards, ComfyUI prompt cards with the four named-workflow slots (FR-033), slider controls, modal confirmation, AJAX form submission, auto-refresh timers (`POLL_INTERVALS`, `NOTIFICATION_DURATION`), CSP + referrer hardening (NFR-010), build-info footer from the manifest version and the build stamp (2.0.3), save-time guards — one field name per config key (2.4.1) and the confirm/refuse rules (2.4.3b) |
| **In-page image zoom (2.5.0)** | Dashboard previews and gallery shots open one shared `#lightbox` overlay instead of a browser window: the image is rendered at its final size, pulled back onto the clicked thumbnail and animated out (FLIP); `←`/`→` step through the group, `Esc` closes, `prefers-reduced-motion` and a `<768px` layout are respected. Gallery anchors keep their `href` as the no-JS fallback, so the handler must `preventDefault()`, and the overlay markup stays **outside** `#settingsForm`. |

#### C-012: Gunicorn WSGI Server
| Attribute | Value |
|-----------|-------|
| **Name** | Gunicorn WSGI Server |
| **Type** | Infrastructure Component |
| **Responsibility** | Production-grade HTTP server with worker process management |
| **Configuration** | 2 workers, 2 threads each, 120s timeout, bound to 0.0.0.0:5000 |
| **Design Rationale** | Gunicorn replaces Flask's development server for production use, providing process isolation, concurrent request handling, and graceful worker recycling. |

#### C-013: ImageProvider (Abstract Base Class)
| Attribute | Value |
|-----------|-------|
| **Name** | ImageProvider Abstract Interface |
| **Type** | Design Pattern / Abstract Base Class |
| **Responsibility** | Define the contract for all image source providers: `fetch_image()`, `health_check()`, `get_source_name()`, `get_config_summary()` |
| **Key Methods** | `fetch_image() -> (PILImage, source_id)`, `health_check() -> bool`, `get_source_name() -> str`, `get_config_summary() -> dict` |
| **Module helpers** | `resolve_prompt_variables()` (FR-030, prompt template variables such as `{seed}`/`{slot}`), `GenerationTracker`, the named-workflow entry resolver |
| **Design Rationale** | Enables source-agnostic image fetching logic in app.py. New sources can be added without modifying core routes, following the Open/Closed Principle. |

#### C-014: ImmichProvider
| Attribute | Value |
|-----------|-------|
| **Name** | Immich Image Provider |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Fetch images from Immich photo server: album listing, asset selection (random/newest), image download, format conversion (JPEG, RAW, HEIC), tracking |
| **Key Functions** | `fetch_image()`, `health_check()`, `load_downloaded_images()`, `save_downloaded_image()` |
| **Dependencies** | Immich REST API, requests, rawpy, pillow-heif |
| **Features** | Album resolved by name, asset list via the **v3 paginated `POST /api/search/metadata`** (`size=1000`, `withExif`), original download, RAW/HEIC decode, no-repeat tracking (FR-001…FR-004) |

#### C-015: ComfyUIHAProvider
| Attribute | Value |
|-----------|-------|
| **Name** | ComfyUI via Home Assistant Provider |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Generate images via HA `ai_task.generate_image` service: prompt resolution, API call, response parsing, generation tracking, rate limiting |
| **Key Functions** | `fetch_image()`, `health_check()`, `_extract_image_from_response()` |
| **Dependencies** | HA REST API, HA Long-Lived Access Token, GenerationTracker |
| **Features** | Daily generation limit, prompt variable resolution, generation history persistence |

#### C-016: ComfyUIDirectProvider
| Attribute | Value |
|-----------|-------|
| **Name** | ComfyUI Direct Provider (Expert Mode) |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Direct ComfyUI server communication: workflow submission, queue polling, progress tracking, image retrieval |
| **Key Functions** | `fetch_image()`, `health_check()`, `_build_workflow()`, `_wait_for_generation()` |
| **Dependencies** | ComfyUI REST API, custom workflow JSON (optional) |
| **Features** | **Named workflows (FR-033, 2.4.0)**: the runtime YAML owns `comfyui.workflows` + `comfyui.active_workflow`, the page shows a dropdown and four slots, `parse_workflow_slots()` rebuilds the whole list from the POST, entry values win over globals, an unknown active entry falls back to the built-in graph with a warning, and only **API-format** graphs can be stored; prompt variable resolution, checkpoint resolution (2.3.1), per-day generation cap + tracking, queue timeout handling |

#### C-017: Provider Factory
| Attribute | Value |
|-----------|-------|
| **Name** | Provider Factory |
| **Type** | Creational Pattern |
| **Responsibility** | Create the appropriate provider instance based on `image_source` configuration value |
| **Key Functions** | `create_provider(config, photo_dir) -> ImageProvider` |
| **Design Rationale** | Single entry point for provider instantiation. Reads `image_source` from config and returns the correct provider type. Enables runtime provider switching on config change — the watchdog reload calls `reset_provider()` so the active instance always matches the stored settings. |

#### C-018: GenerationTracker
| Attribute | Value |
|-----------|-------|
| **Name** | Generation Tracking Service |
| **Type** | Data Management Component |
| **Responsibility** | Track ComfyUI image generations for rate limiting and status reporting |
| **Key Functions** | `log_generation()`, `get_count_today()`, `reset_daily_count()`, `get_last_generation()` |
| **Storage** | JSON file `generations.json` in photo directory |
| **Interface** | Serves `/api/generation-status` (today's count, the cap, the last generation) and enforces `comfyui.max_generations_per_day` (FR-031) |

#### C-013: ImageProvider (Abstract Base Class)
| Attribute | Value |
|-----------|-------|
| **Name** | ImageProvider Abstract Interface |
| **Type** | Design Pattern / Abstract Base Class |
| **Responsibility** | Define the contract for all image source providers: `fetch_image()`, `health_check()`, `get_source_name()`, `get_config_summary()` |
| **Key Methods** | `fetch_image() -> (PILImage, source_id)`, `health_check() -> bool`, `get_source_name() -> str`, `get_config_summary() -> dict` |
| **Module helpers** | `resolve_prompt_variables()` (FR-030, prompt template variables such as `{seed}`/`{slot}`), `GenerationTracker`, the named-workflow entry resolver |
| **Design Rationale** | Enables source-agnostic image fetching logic in app.py. New sources can be added without modifying core routes, following the Open/Closed Principle. |

#### C-014: ImmichProvider
| Attribute | Value |
|-----------|-------|
| **Name** | Immich Image Provider |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Fetch images from Immich photo server: album listing, asset selection (random/newest), image download, format conversion (JPEG, RAW, HEIC), tracking |
| **Key Functions** | `fetch_image()`, `health_check()`, `load_downloaded_images()`, `save_downloaded_image()` |
| **Dependencies** | Immich REST API, requests, rawpy, pillow-heif |
| **Features** | Album resolved by name, asset list via the **v3 paginated `POST /api/search/metadata`** (`size=1000`, `withExif`), original download, RAW/HEIC decode, no-repeat tracking (FR-001…FR-004) |

#### C-015: ComfyUIHAProvider
| Attribute | Value |
|-----------|-------|
| **Name** | ComfyUI via Home Assistant Provider |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Generate images via HA `ai_task.generate_image` service: prompt resolution, API call, response parsing, generation tracking, rate limiting |
| **Key Functions** | `fetch_image()`, `health_check()`, `_extract_image_from_response()` |
| **Dependencies** | HA REST API, HA Long-Lived Access Token, GenerationTracker |
| **Features** | Daily generation limit, prompt variable resolution, generation history persistence |

#### C-016: ComfyUIDirectProvider
| Attribute | Value |
|-----------|-------|
| **Name** | ComfyUI Direct Provider (Expert Mode) |
| **Type** | Concrete Provider Implementation |
| **Responsibility** | Direct ComfyUI server communication: workflow submission, queue polling, progress tracking, image retrieval |
| **Key Functions** | `fetch_image()`, `health_check()`, `_build_workflow()`, `_wait_for_generation()` |
| **Dependencies** | ComfyUI REST API, custom workflow JSON (optional) |
| **Features** | **Named workflows (FR-033, 2.4.0)**: the runtime YAML owns `comfyui.workflows` + `comfyui.active_workflow`, the page shows a dropdown and four slots, `parse_workflow_slots()` rebuilds the whole list from the POST, entry values win over globals, an unknown active entry falls back to the built-in graph with a warning, and only **API-format** graphs can be stored; prompt variable resolution, checkpoint resolution (2.3.1), per-day generation cap + tracking, queue timeout handling |

#### C-017: Provider Factory
| Attribute | Value |
|-----------|-------|
| **Name** | Provider Factory |
| **Type** | Creational Pattern |
| **Responsibility** | Create the appropriate provider instance based on `image_source` configuration value |
| **Key Functions** | `create_provider(config, photo_dir) -> ImageProvider` |
| **Design Rationale** | Single entry point for provider instantiation. Reads `image_source` from config and returns the correct provider type. Enables runtime provider switching on config change — the watchdog reload calls `reset_provider()` so the active instance always matches the stored settings. |

#### C-018: GenerationTracker
| Attribute | Value |
|-----------|-------|
| **Name** | Generation Tracking Service |
| **Type** | Data Management Component |
| **Responsibility** | Track ComfyUI image generations for rate limiting and status reporting |
| **Key Functions** | `log_generation()`, `get_count_today()`, `reset_daily_count()`, `get_last_generation()` |
| **Storage** | JSON file `generations.json` in photo directory |
| **Interface** | Serves `/api/generation-status` (today's count, the cap, the last generation) and enforces `comfyui.max_generations_per_day` (FR-031) |

---

## 5. Interface Definitions

### 5.1 HTTP Endpoint Catalog

| Endpoint | Method | Purpose | Request | Response | Status Codes |
|----------|--------|---------|---------|----------|--------------|
| `/` | GET | Serve settings UI | - | HTML page | 200 |
| `/` | POST | Save configuration | Form data | Redirect | 302, 400, 500 |
| `/health` | GET, HEAD | Health check | - | JSON | 200, 503 |
| `/download` | GET | Serve image to ESP32 | Optional `batteryCap` header | text/plain (frame.txt) | 200, 404, 500 |
| `/prepare-photo` | POST | Manually prepare photo | - | JSON | 200, 404, 500 |
| `/preview-photo` | GET | Serve preview (fallback) | - | image/jpeg | 200, 404 |
| `/preview-original` | GET | Serve original image | - | image/jpeg | 200, 404 |
| `/preview-processed` | GET | Serve processed image | - | image/jpeg | 200, 404 |
| `/preview-delivered` | GET | Serve last delivered image | - | image/jpeg | 200, 404 |
| `/preview-status` | GET | Get preview status | - | JSON | 200 |
| `/api/battery-status` | GET | Get battery status | - | JSON | 200 |
| `/api/generation-status` | GET | Get ComfyUI generation status | - | JSON | 200 |
| `/sleep` | GET | Get ESP32 sleep duration | - | JSON | 200 |
| `/cleanup-previews` | POST | Run the age/count evictor on the live-slot preview directory (per pattern) | - | JSON | 200 |
| `/api/gallery-previews` | GET | List the archived gallery grouped per shot (newest shot first, capped) | - | JSON | 200 |
| `/preview-file/<filename>` | GET | Serve one file from the photo or gallery directory | filename in path | image/jpeg | 200, 404 |

### 5.2 External Interface Contracts

#### IFC-001: Immich REST API
```
Protocol:       HTTP/HTTPS
Authentication: x-api-key header
Timeouts:       10s (albums, ping), 30s (asset download)

GET /api/albums
  Response:     [{id: string, albumName: string, ...}]      (the album is matched by albumName)

POST /api/search/metadata                                      (v3, paginated — 14.3/14.4)
  Request:      {"albumId": ..., "size": 1000, "withExif": true, ...}
  Response:     {"assets": [{id, assetPath, exifInfo: {dateTimeOriginal}, ...}], ...}
  Note:         the legacy GET /api/albums/{id} shape no longer carries assets

GET /api/assets/{asset_id}/original
  Response:     Binary image data

GET /api/server/ping
  Response:     200 OK or error
```

#### IFC-002: ESP32 Client Protocol
```
Protocol:       HTTP/1.1
Endpoint:       http://{ha-host}:5000/download

Request:
  GET /download
  Headers:
    batteryCap: <voltage in mV>  (optional)

Response:
  Content-Type: text/plain
  Content-Disposition: attachment; filename=frame.txt
  Body: <comma-separated hex-encoded 4-bit palette indices>
  Format: "0A,1B,2C,3D,..." (2 pixels per byte, 16 bytes per line)
```

#### IFC-003: Home Assistant Configuration
```
Protocol:       bashio config API (environment variables)
Injection:      Via run.sh entrypoint script

Environment Variables:
  IMMICH_API_KEY        string    (required)
  IMMICH_URL            url       (required)
  ALBUM_NAME            string    (default: "eink")
  ROTATION_ANGLE        int       (default: 270)
  COLOR_ENHANCE         float     (default: 1.8)
  CONTRAST              float     (default: 0.9)
  DITHERING_STRENGTH    float     (default: 1.0)
  DISPLAY_MODE          string    (default: "fill")
  IMAGE_ORDER           string    (default: "random")
  DITHERING_METHOD      string    (default: "atkinson")
  WAKEUP_INTERVAL       int       (default: 1440)
  SLEEP_START_HOUR      int       (default: 23)
  SLEEP_START_MINUTE    int       (default: 0)
  SLEEP_END_HOUR        int       (default: 6)
  SLEEP_END_MINUTE      int       (default: 0)
  LOG_LEVEL             string    (default: "info")
```

#### IFC-004: Home Assistant Ingress
```
Protocol:       HTTP via HA reverse proxy
Path Prefix:    /api/hassio_ingress/{token}/
Middleware:     Werkzeug ProxyFix (x_for=1, x_proto=1, x_host=1, x_prefix=1)
Port:           5000 (internal)
```

### 5.3 Internal Component Interfaces

#### Internal API: Image Processing Pipeline
```
Input:  PIL Image (any format/size)
Config: rotation_angle, display_mode, color_enhance, contrast,
        dithering_strength, dithering_method

Step 1: EXIF auto-transpose (PIL ImageOps)
Step 2: load_scaled(image, rotation, display_mode) -> 800x480 RGB  [Cython]
Step 3: ImageEnhance.Color(img).enhance(color_enhance)
Step 4: ImageEnhance.Contrast(img).enhance(contrast)
Step 5: convert_image_atkinson() OR convert_image_floyd()           [Cython]
Step 6: Date overlay (PIL ImageDraw)
Output: PIL Image (800x480 RGB, dithered to 6-color palette)
```

#### Internal API: Hex Format Conversion
```
Input:  BMP image (800x480, 6-color palette)
Process:
  1. Convert each pixel to nearest palette index (0-5)
  2. Pack two 4-bit indices into one byte (left pixel = high nibble)
  3. Format as comma-separated uppercase hex string
  4. Insert line break every 16 bytes
Output: BytesIO containing text like "0A,1B,2C,3D,..."
```

---

## 6. Data Flow Architecture

### 6.1 Primary Data Flow: Image Delivery to ESP32

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────┐
│  ESP32   │────>│  Flask   │────>│  Tracking    │────>│  Immich       │────>│  Image    │
│  Client  │ GET │  Router   │     │  Service     │     │  Client       │     │  Download │
│          │     │/download  │     │  (check)     │     │  Service      │     │           │
└──────────┘     └──────────┘     └──────────────┘     └───────────────┘     └──────────┘
                                                                                    │
                                                                                    ▼
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────────┐     ┌──────────┐
│  ESP32   │<────│  Hex     │<────│  BMP         │<────│  Image        │<────│  Format  │
│  Receives│     │  Encoder │     │  Generator   │     │  Processing   │     │  Convert │
│  frame.txt│     │          │     │              │     │  Pipeline     │     │          │
└──────────┘     └──────────┘     └──────────────┘     └───────────────┘     └──────────┘
```

**Flow Description:**
1. ESP32 sends GET `/download` with optional `batteryCap` header
2. Flask router checks for pre-prepared image (`latest.bmp` with status `new`)
3. If pre-prepared: serve hex-encoded BMP, update status to `delivered`
4. If not pre-prepared: check tracking service for unseen images
5. Fetch selected image from Immich via Immich Client Service
6. Convert format if needed (RAW/HEIC -> RGB)
7. Process through Image Processing Pipeline (scale, enhance, dither, overlay)
8. Save three preview versions and BMP
9. Encode BMP to hex format
10. Return `frame.txt` to ESP32

### 6.2 Secondary Data Flow: Manual Photo Preparation

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────────┐
│  HA User │────>│  Flask   │────>│  Image        │────>│  Preview      │
│  (Browser)│POST │  Router   │     │  Selection   │     │  Generator    │
│          │     │/prepare   │     │  & Download  │     │  (3 versions) │
└──────────┘     └──────────┘     └──────────────┘     └───────────────┘
                      │                                       │
                      ▼                                       ▼
               ┌──────────────┐                        ┌──────────────┐
               │  JSON        │                        │  Status:     │
               │  Response    │                        │  "new"       │
               └──────────────┘                        └──────────────┘
```

### 6.3 Tertiary Data Flow: Configuration Hot-Reload

```
┌──────────┐     ┌──────────┐     ┌──────────────┐     ┌───────────────┐
│  HA User │────>│  Config  │────>│  Watchdog    │────>│  Config       │
│  or YAML │     │  File    │     │  Observer    │     │  Update       │
│  Edit    │     │  Modify  │     │  (detect)    │     │  (apply)      │
└──────────┘     └──────────┘     └──────────────┘     └───────────────┘
                                                              │
                                                              ▼
                                                       ┌──────────────┐
                                                       │  Global      │
                                                       │  Variables   │
                                                       │  Updated     │
                                                       └──────────────┘
```

### 6.4 Quaternary Data Flow: Gallery History and In-Page Zoom (2.2.0–2.5.0)

```
┌──────────┐   GET /api/gallery-previews    ┌────────────────────┐
│ Browser  │ ─────────────────────────────► │ photos/gallery/    │
│ Gallery  │   grouped per shot,             │ <shotid>_*.jpg     │
│ tab      │   newest shot first             └────────────────────┘
│          │
│          │   click a card  →  #lightbox overlay (no new window/tab)
└──────────┘        FLIP open from the clicked thumbnail,
                    ←/→ steps through the group, Esc closes
```

- Preparation archives the pair (`_archive_previews()` on the `prepare_photo` path), the reader
  groups it back into shots, and `cleanup_gallery()` prunes **whole shots** judged by the newest
  file of the group (2.4.3) — the cap in the settings and the pruner read the same measure.
- The zoom is **one shared overlay** for both surfaces (the three dashboard previews and the
  gallery as rendered), uses the existing design tokens, honours `prefers-reduced-motion`, and
  has responsive rules below 768 px. Navigation inside an open overlay cross-fades; only the
  opening gesture is a FLIP.
- Guard on the test side: `test_image_click_zooms_in_page_lightbox` (FR-026 clause 8) asserts the
  overlay exists, both groups are wired to it and no `target="_blank"` remains in the page.

---

## 7. Deployment Architecture

### 7.1 Container Definition

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Container                              │
│  Image: ghcr.io/home-assistant/{arch}-base-debian:bookworm      │
│  Architectures: armhf, armv7, aarch64, amd64, i386              │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Base OS: Debian Bookworm                                  │  │
│  │  Runtime: Python 3.11                                      │  │
│  │  Build: gcc, g++, Cython 3.0.10, numpy 1.24.4             │  │
│  │  Libraries: libjpeg, zlib, freetype, lcms2, openjp2,      │  │
│  │               tiff, tk, tcl, ffi, libraw                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Workdir: /app                                                   │
│  Entry: /run.sh -> gunicorn app:app :5000                        │
│  Health: wget http://localhost:5000/health (30s/10s/60s/3)      │
│  Expose: 5000/tcp                                                │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Installed Python Packages:                                │  │
│  │  - Flask 3.0.3, Werkzeug 3.0.4                            │  │
│  │  - Pillow 10.4.0, pillow-heif 0.18.0                      │  │
│  │  - numpy 1.24.4, Cython 3.0.10                            │  │
│  │  - rawpy 0.21.0                                           │  │
│  │  - requests 2.32.3, urllib3 2.2.3                        │  │
│  │  - PyYAML 6.0.2, watchdog 6.0.0                           │  │
│  │  - ntplib 0.4.0, gunicorn 23.0.0                          │  │
│  │  - python-dotenv 1.0.1                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Compiled Native Module:                                   │  │
│  │  - cpy.so (Cython: load_scaled, convert_image,             │  │
│  │    convert_image_atkinson)                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Application Files:                                        │  │
│  │  - app.py (Flask application)                              │  │
│  │  - templates/settings.html (Web UI)                        │  │
│  │  - /photos/ (runtime photo storage)                        │  │
│  │  - config/config.yaml (runtime configuration)              │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 Build Pipeline

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Source      │────>│  Docker      │────>│  Cython      │────>│  Final       │
│  Repository  │     │  Base Image  │     │  Compilation │     │  Container   │
│              │     │  Pull        │     │  (setup.py)  │     │  Image       │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                  │
                                                  ▼
                                           ┌──────────────┐
                                           │  cpy.so      │
                                           │  (arch-      │
                                           │   specific)  │
                                           └──────────────┘

Build Steps:
1. Pull architecture-specific Debian Bookworm base image
2. Install system dependencies (Python 3.11, build tools, image libraries)
3. Install Python dependencies from requirements.txt
4. Compile Cython module (cpy.pyx -> cpy.so) for target architecture
5. Copy application files (app.py, templates/, run.sh)
6. Set health check and expose port 5000
```

### 7.3 Runtime File System Layout

```
/app/
├── app.py                          # Flask application
├── cpy.so                          # Compiled Cython module
├── cpy.pyx                         # Cython source (build-time only)
├── setup.py                        # Cython build script (build-time only)
├── requirements.txt                # Python dependencies (build-time only)
├── templates/
│   └── settings.html               # Web UI template
├── config/
│   └── config.yaml                 # Runtime configuration (watched)
└── photos/
    ├── tracking.txt                # Shown image tracker
    ├── latest_original.jpg         # Unprocessed source preview
    ├── latest_processed.jpg        # Fully processed preview
    ├── latest.bmp                  # BMP for ESP32 delivery
    ├── latest_delivered.jpg        # Last delivered to ESP32
    ├── latest.status               # "new" or "delivered"
    ├── generations.json            # ComfyUI generation history (C-018)
    └── gallery/                    # Archived shots — one <shotid>_original.jpg + <shotid>_processed.jpg pair per shot (C-007, FR-032)
```

---

## 8. Design Decisions and Rationale

### 8.1 D-001: Cython for Image Processing
**Decision:** Use Cython for scaling, rotation, and dithering algorithms.  
**Rationale:** Floyd-Steinberg and Atkinson dithering require per-pixel iteration with error diffusion to neighboring pixels. In pure Python, processing an 800x480 image (384,000 pixels x 3 channels) would take several minutes. Cython compiles to C, reducing processing time to seconds. The `nogil` declarations enable parallel execution potential.  
**Alternatives Considered:** Pure Python (too slow), NumPy vectorization (complex for error diffusion), GPU acceleration (not available on all HA hosts).

### 8.2 D-002: Dual Configuration Mode
**Decision:** Support both environment variable injection (startup) and YAML file watching (runtime).  
**Rationale:** Home Assistant add-ons receive configuration through the supervisor API, which bashio exposes as environment variables. However, the web settings UI writes to a YAML file. The watchdog observer bridges these two modes, enabling hot-reload without container restart.  
**Alternatives Considered:** Environment variables only (no hot-reload), YAML only (no HA UI integration).

### 8.3 D-003: Pre-Prepared Image Caching
**Decision:** Support both on-the-fly processing and pre-prepared image caching with status tracking.  
**Rationale:** The `/prepare-photo` endpoint allows users to manually queue the next image, while the `/download` endpoint can also process on-the-fly. The status file (`new`/`delivered`) prevents double-delivery and enables the web UI to show accurate preview state.  
**Alternatives Considered:** On-the-fly only (no manual control), Pre-prepared only (no fallback).

### 8.4 D-004: Hex-Encoded Pixel Format
**Decision:** Serve images as comma-separated hex-encoded 4-bit palette indices instead of raw BMP.  
**Rationale:** The ESP32 firmware expects this specific format. Packing two 4-bit indices per byte reduces data size by 50% compared to 8-bit-per-pixel BMP. The comma-separated text format is easy for the ESP32 to parse with `sscanf` or equivalent.  
**Alternatives Considered:** Raw BMP (larger payload, more parsing on ESP32), Binary packed format (harder to debug).

### 8.5 D-005: Atkinson as Default Dithering
**Decision:** Default to Atkinson dithering over Floyd-Steinberg.  
**Rationale:** Atkinson dithering distributes only 75% of the error (multiplied by 0.75) to 6 neighboring pixels instead of 100% to 4 neighbors. This produces softer, less noisy results that are better suited for E-Ink displays, which have limited color depth and visible grain.  
**Alternatives Considered:** Floyd-Steinberg (more detail but noisier), Ordered dithering (faster but lower quality).

### 8.6 D-006: Gunicorn Over Flask Dev Server
**Decision:** Use Gunicorn as the production WSGI server.  
**Rationale:** Flask's built-in development server is single-threaded and not designed for production. Gunicorn provides worker process isolation, concurrent request handling, and graceful restarts. The 2-worker, 2-thread configuration balances resource usage with concurrency needs.  
**Alternatives Considered:** Flask dev server (not production-ready), uWSGI (more complex configuration).

### 8.7 D-007: Debian Bookworm Over Alpine
**Decision:** Use Debian Bookworm as the base image instead of Alpine Linux.  
**Rationale:** The Cython compilation requires a full C compiler toolchain and several native libraries (libraw, libjpeg, etc.). Alpine's musl libc and package availability caused compatibility issues. Debian provides better compatibility with Python native extensions and image processing libraries.  
**Alternatives Considered:** Alpine (smaller image but compatibility issues), Ubuntu (larger image, similar compatibility).

### 8.8 D-008: Three Preview Versions
**Decision:** Save original, processed, and delivered image versions separately.  
**Rationale:** The 3-column preview grid in the web UI provides users with visibility into the entire image processing pipeline: what was fetched (original), what will be sent next (processed), and what was actually sent (delivered). This aids debugging and quality assessment.  
**Alternatives Considered:** Single preview (insufficient visibility), No preview (no user feedback).

---

## 9. Error Handling Strategy

### 9.1 Error Categories and Responses

| Error Category | Detection | Response | Logging |
|---------------|-----------|----------|---------|
| Immich unreachable | requests timeout / non-200 | HTTP 500 with JSON error | ERROR with exception info |
| Album not found | Album ID lookup returns None | HTTP 404 with JSON error | WARNING |
| No images in album | Empty assets array | HTTP 404 with JSON error | WARNING |
| Image download failure | Non-200 response | HTTP 500 with JSON error | ERROR |
| Format conversion failure | rawpy/Pillow exception | HTTP 500 with JSON error | ERROR with exc_info |
| Cython module missing | ImportError at startup | RuntimeError logged; processing fails | ERROR at startup |
| Config file invalid | YAML parse error / missing keys | Fallback to DEFAULT_CONFIG | WARNING |
| Tracking file corrupt | Read/IO error | Return empty set (restart cycle) | ERROR |
| NTP sync failure | ntplib exception | Retry after 3600s | WARNING |

### 9.2 Graceful Degradation
- **Cython unavailable:** Application logs error and raises RuntimeError on image processing. No silent fallback to Python implementation.
- **Immich unavailable:** Health check returns 503; image delivery fails with 500 error.
- **Config file missing:** Application creates default config file and logs warning.
- **Tracking file missing:** Application creates empty tracking file and starts fresh cycle.

---

## 10. Concurrency Model

### 10.1 Threading Architecture
```
Main Thread:
  └── Gunicorn (2 workers x 2 threads = 4 request threads)
       └── Flask request handlers (concurrent HTTP requests)

Background Threads:
  └── Watchdog Observer (config file monitoring)
  └── NTP Sync Daemon (daily time synchronization)
```

### 10.2 Shared State and Synchronization
| Shared Resource | Access Pattern | Synchronization |
|----------------|----------------|-----------------|
| Global config variables | Read by all requests, write by config handler | Implicit (GIL, single-writer) |
| tracking.txt | Read/write by download and prepare handlers | File-level (append mode, read-then-write) |
| latest.status | Read/write by download and prepare handlers | File-level (atomic write) |
| last_battery_voltage | Write by download, read by battery-status | Implicit (GIL) |
| Photo files | Write by processing, read by preview handlers | File-level (write-complete before read) |

### 10.3 Concurrency Risks
- **CR-001:** Simultaneous `/download` requests could process the same image twice (mitigated by tracking file check-and-save pattern, but not atomic).
- **CR-002:** Config hot-reload during image processing could cause inconsistent parameter usage within a single pipeline run (mitigated by reading globals at pipeline start).

---

## 11. Security Architecture

### 11.1 Trust Boundaries
```
┌──────────────────────────────────────────────────────────────────┐
│                     Trust Boundary: Container                    │
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │  Immich      │    │  Add-on      │    │  ESP32       │       │
│  │  Server      │◄──►│  Container   │◄──►│  Client      │       │
│  │  (Trusted)   │    │  (Trusted)   │    │  (Trusted)   │       │
│  └──────────────┘    └──────────────┘    └──────────────┘       │
│                                                                  │
│  ┌──────────────┐                                               │
│  │  HA Browser  │◄─── Ingress proxy (HA managed)                │
│  │  (Trusted)   │                                               │
│  └──────────────┘                                               │
└──────────────────────────────────────────────────────────────────┘
```

### 11.2 Security Controls
| Control | Implementation | Scope |
|---------|---------------|-------|
| API key isolation | Environment variable, never logged | SEC-001 |
| Container isolation | Docker non-root, no privileged | SEC-002 |
| Input validation | HA schema + application validation | SEC-003 |
| Request timeouts | 10-30s on all external HTTP calls | SEC-004 |
| No authentication on ESP32 endpoint | LAN-only, trusted network assumed | Documented risk |

---

## 12. Architecture Traceability

| Architecture Component | Requirements Satisfied |
|----------------------|----------------------|
| Flask Application Core | FR-013, FR-014, FR-015, FR-016, FR-017, FR-018, FR-019, FR-021, IFR-002, IFR-003, IFR-005 |
| Image Processing Pipeline | FR-005, FR-006, FR-007, FR-008, FR-009, FR-010, FR-011, FR-012, NFR-006, NFR-007, PER-001 |
| Cython Module | FR-006, FR-008, FR-009, NFR-006, NFR-007, PER-001 |
| Immich Client Service | FR-001, FR-002, FR-003, FR-004, FR-017, IFR-001 |
| Configuration Management | FR-020, FR-021, FR-027, IFR-003, IFR-004, NFR-004, PER-003 |
| Tracking Service | FR-003, FR-022 |
| Preview Generator | FR-011, FR-014, FR-015, FR-016, FR-032 |
| Power Management Service | FR-019 |
| Battery Monitor | FR-018 |
| NTP Synchronizer | FR-023 |
| Web Settings UI | FR-021, FR-025, FR-026 (incl. clause 8, the in-page lightbox), FR-032, FR-033, NFR-008, NFR-010 |
| Gunicorn WSGI Server | NFR-002, NFR-003, NFR-005, PER-002 |
| Preview Cleanup Service | FR-024, NFR-009 |
| Provider Layer — C-013 … C-018 | FR-027, FR-028, FR-029, FR-030, FR-031, FR-033 |

---

## 13. Open Architectural Concerns

| ID | Concern | Impact | Recommendation | Status |
|----|---------|--------|----------------|--------|
| AC-001 | `cpy.so` binary in repository is architecture-specific (amd64) and will not work on ARM hosts without Docker recompilation. | Medium | Add `cpy.so` to `.gitignore`; rely solely on Docker build-time compilation. | **RESOLVED (v2.0.0 build pipeline)**: both Dockerfiles compile the module in-container (`setup.py build_ext --inplace`); the committed `.so` is vestigial and only whitelisted in `.gitignore`. |
| AC-002 | No atomic file operations for tracking.txt; concurrent requests could cause race conditions. | Low | Use file locking (fcntl) or atomic rename pattern for tracking file updates. | Open |
| AC-003 | Global mutable state for configuration variables; no thread-safe access guarantees. | Low | Use threading.Lock for config updates or immutable config snapshots per request. | Open |
| AC-004 | No rate limiting or authentication on ESP32 endpoints; any LAN client can trigger image processing. | Medium | Add optional API key validation for `/download` endpoint or restrict via HA network policy. | Open |
| AC-005 | ~~NTP daemon thread has no graceful shutdown; container stop may interrupt sync.~~ | ~~Negligible~~ | ~~Daemon threads are terminated by OS on container stop; no action needed.~~ | **RESOLVED (v1.0.4)**: Implemented `_ntp_stop_event` threading.Event for graceful shutdown. |
| AC-006 | ~~Single photo directory with no cleanup; old preview files accumulate.~~ | ~~Low~~ | ~~Implement periodic cleanup of stale preview files or size-based rotation.~~ | **RESOLVED (v1.0.4)**: Implemented `cleanup_old_previews()` with age-based and count-based eviction. |
| AC-007 | ~~No type hints in application code; reduces maintainability and IDE support.~~ | ~~Low~~ | ~~Add Python type annotations throughout the codebase.~~ | **RESOLVED (v1.0.4)**: Full type hints added to all functions, variables, and class members. |

---

## 14. Design Decisions Added Since v1.0.4

### D-009: Graceful NTP Thread Shutdown
- **Problem:** NTP daemon thread had no mechanism for graceful shutdown
- **Solution:** Introduced `_ntp_stop_event` (threading.Event). The NTP loop checks this event before each sleep cycle and exits cleanly when signaled. A `stop_ntp_sync()` function is called during application shutdown.
- **Impact:** Clean container shutdown, no orphaned threads

### D-010: Preview File Cleanup
- **Problem:** Preview files (latest_original_*.jpg, latest_processed_*.jpg, latest_delivered_*.jpg) accumulated indefinitely
- **Solution:** Implemented `cleanup_old_previews()` function with dual eviction strategy:
  - Age-based: Files older than 7 days are removed
  - Count-based: When more than 50 files match a pattern, oldest are removed first
- **Interface:** Exposed via POST `/cleanup-previews` endpoint
- **Impact:** Prevents unbounded disk growth

### D-011: Type Hints Throughout Codebase
- **Problem:** No type annotations, reducing code clarity and IDE support
- **Solution:** Added `from __future__ import annotations` and comprehensive type hints using `typing` module (Optional, Dict, Any, Set, Tuple, Callable, List) for all function signatures, global variables, and class attributes
- **Impact:** Improved maintainability, better IDE autocomplete, earlier error detection

### D-012: UI/Schema Alignment for color_enhance
- **Problem:** Settings UI slider capped at 2.0 while config schema allows 0.0–3.0
- **Solution:** Updated slider `max` attribute from `2.0` to `3.0` in settings.html
- **Impact:** Consistent user experience, full schema range accessible via UI

### D-013: Provider Abstraction Behind a Factory (v2.0.0)
- **Problem:** Three image sources (Immich, ComfyUI via HA, ComfyUI direct) would otherwise each need their own HTTP logic inside `app.py`.
- **Solution:** `providers.py` holds the `ImageProvider` ABC, one implementation per source, and a `create_provider()` factory fed by `image_source`; a config reload rebuilds the active provider. The startup gate in `run.sh` is source-conditional, so a ComfyUI-only install needs no Immich credentials.
- **Impact:** `app.py` stays source-agnostic; a fourth source is a new subclass plus a factory branch, not new route code.

### D-014: Image Source Speaks the Immich v3 API (v2.0.0, plans 14.3/14.4)
- **Problem:** The album-asset call inherited from the standalone project was the legacy `GET /api/albums/{id}`, which v3 servers no longer populate.
- **Solution:** Resolve the album by name (`GET /api/albums`), list assets through the paginated `POST /api/search/metadata` (`size=1000`, `withExif`), download via `GET /api/assets/{id}/original`.
- **Impact:** Works against a real current Immich; proven by the L1 live tier (the only check that can catch API drift the offline mocks cannot).

### D-015: The Gallery Cap Counts Shots, the Live Slot Stays Per Pattern (v2.2.0–v2.4.3)
- **Problem:** The gallery cap was applied per file pattern, so an archived pair could be pruned half and the number in the settings page stopped matching the number of cards.
- **Solution:** `cleanup_gallery()` groups by shot id and judges a group by its newest member, deleting whole shots; the reader sorts and caps by the same measure. The live preview directory keeps per-pattern eviction because it holds one slot, not groups.
- **Impact:** One unit for one setting on the gallery side; the deliberate difference to the live slot is documented and guarded by the cross-mtime test.

### D-016: One Shared In-Page Lightbox, FLIP Open (v2.5.0)
- **Problem:** Clicking an image handed the click to the browser — a new window for a gallery shot, nothing useful on the dashboard — and the user asked for a zoom animation in the page instead.
- **Solution:** One `#lightbox` overlay shared by both surfaces. The image is rendered at its final size, positioned back onto the clicked thumbnail and animated out with the existing tokens (`--dur-slow`, `--ease-out-soft`); navigation inside the overlay cross-fades; `Esc` closes, `←`/`→` step through the group; `prefers-reduced-motion` and a `<768px` layout are honoured. Gallery anchors keep `href` as the no-JS fallback (`preventDefault()` in JS), and the overlay markup stays outside `#settingsForm` so the one-field-name-per-key guard stays green.
- **Impact:** Same gesture on both surfaces, no extra windows, no backend change; covered by the FR-026 clause 8 / TC-FR-026 step 9 guard test.

---

## 15. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| System Architect | EPF Project | 2026-11-23 | - |
| Software Architect | EPF Project | 2026-11-23 | - |
| Quality Assurance | - | - | *(human signature still outstanding)* |

---

*Document generated from codebase analysis of repository state at commit 52 on main branch + v1.0.4 enhancements. All architectural descriptions reflect implemented design decisions, not planned features.*

*Re-baselined for code base **v2.5.0** on branch `main`, 2026-11-23 (this pass): what the code has done since the v2.0.0 snapshot is now described — the Immich v3 calls, the gallery archive and its per-shot pruning, the workflow selection, the settings-form rules and the in-page image zoom. Test side at the same baseline: EPF-TST-001 / EPF-RPT-001, **206 offline + 8 live = 214, 100 %**. Browser acceptance of the animation itself stays manual (TESTSPEC §3).*
