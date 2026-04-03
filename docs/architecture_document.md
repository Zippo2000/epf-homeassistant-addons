# System & Software Architecture (ASPICE SYS.3 / SWE.2)

**Project:** EPF Home Assistant Add-ons Repository  
**Document ID:** EPF-ARC-001  
**Version:** 1.0.0  
**Date:** 2025-11-08  
**Baseline:** Repository commit 52 (main branch)  
**Status:** Released

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
- **G-001:** Provide a seamless bridge between Immich photo library and ESP32-based E-Ink display hardware
- **G-002:** Optimize images for 7-color E-Ink displays using performant Cython-compiled dithering algorithms
- **G-003:** Integrate natively into Home Assistant with configuration via HA UI and Ingress web interface
- **G-004:** Support power-efficient operation through configurable sleep schedules and ESP32 deep-sleep coordination
- **G-005:** Enable multi-architecture deployment (ARM and x86) via Home Assistant build system

### 2.2 Constraints
- **C-001:** Must operate as a Home Assistant supervised Docker container
- **C-002:** Must use the Home Assistant bashio configuration API for runtime configuration
- **C-003:** E-Ink display hardware is fixed at 800x480 pixels, 7-color palette (Waveshare 7.3inch)
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

### 4.2 Component Descriptions

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
| **Key Functions** | HTTP requests to `/api/albums`, `/api/albums/{id}`, `/api/assets/{id}/original`, `/api/server/ping` |
| **Dependencies** | requests library, environment variables (IMMICH_API_KEY, IMMICH_URL) |
| **Error Handling** | Timeout-based (10-30s), HTTP status code validation, JSON error responses |

#### C-005: Configuration Management
| Attribute | Value |
|-----------|-------|
| **Name** | Configuration Management |
| **Type** | Service Component |
| **Responsibility** | Dual-mode configuration: (1) Environment variable injection at startup via bashio, (2) Hot-reload via watchdog file observer on config/config.yaml |
| **Key Classes** | `ConfigFileHandler(FileSystemEventHandler)`, `update_app_config()` |
| **Design Rationale** | The dual-mode approach allows initial configuration through Home Assistant UI (which sets environment variables) while enabling runtime changes through direct YAML edits or the web settings form. The watchdog observer provides near-instant hot-reload without application restart. |

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
| **Responsibility** | Generate and serve three preview versions (original, processed, delivered) plus status tracking |
| **Key Functions** | `save_three_previews()`, preview route handlers |
| **Output Files** | `latest_original.jpg`, `latest_processed.jpg`, `latest.bmp`, `latest_delivered.jpg`, `latest.status` |

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
| **Features** | 3-column preview grid, dark/light theme, battery status display, slider controls, modal confirmation, AJAX form submission, auto-refresh timers |

#### C-012: Gunicorn WSGI Server
| Attribute | Value |
|-----------|-------|
| **Name** | Gunicorn WSGI Server |
| **Type** | Infrastructure Component |
| **Responsibility** | Production-grade HTTP server with worker process management |
| **Configuration** | 2 workers, 2 threads each, 120s timeout, bound to 0.0.0.0:5000 |
| **Design Rationale** | Gunicorn replaces Flask's development server for production use, providing process isolation, concurrent request handling, and graceful worker recycling. |

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
| `/sleep` | GET | Get ESP32 sleep duration | - | JSON | 200 |

### 5.2 External Interface Contracts

#### IFC-001: Immich REST API
```
Protocol:       HTTP/HTTPS
Authentication: x-api-key header
Timeouts:       10s (albums, ping), 30s (asset download)

GET /api/albums
  Response:     [{id: string, albumName: string, ...}]

GET /api/albums/{album_id}
  Response:     {assets: [{id: string, originalPath: string, exifInfo: {dateTimeOriginal: string}, ...}]}

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
    └── latest.status               # "new" or "delivered"
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
| Configuration Management | FR-020, FR-021, IFR-003, IFR-004, NFR-004, PER-003 |
| Tracking Service | FR-003, FR-022 |
| Preview Generator | FR-011, FR-014, FR-015, FR-016 |
| Power Management Service | FR-019 |
| Battery Monitor | FR-018 |
| NTP Synchronizer | FR-023 |
| Web Settings UI | FR-021, NFR-008 |
| Gunicorn WSGI Server | NFR-002, NFR-003, NFR-005, PER-002 |

---

## 13. Open Architectural Concerns

| ID | Concern | Impact | Recommendation |
|----|---------|--------|----------------|
| AC-001 | `cpy.so` binary in repository is architecture-specific (amd64) and will not work on ARM hosts without Docker recompilation. | Medium | Add `cpy.so` to `.gitignore`; rely solely on Docker build-time compilation. |
| AC-002 | No atomic file operations for tracking.txt; concurrent requests could cause race conditions. | Low | Use file locking (fcntl) or atomic rename pattern for tracking file updates. |
| AC-003 | Global mutable state for configuration variables; no thread-safe access guarantees. | Low | Use threading.Lock for config updates or immutable config snapshots per request. |
| AC-004 | No rate limiting or authentication on ESP32 endpoints; any LAN client can trigger image processing. | Medium | Add optional API key validation for `/download` endpoint or restrict via HA network policy. |
| AC-005 | NTP daemon thread has no graceful shutdown; container stop may interrupt sync. | Negligible | Daemon threads are terminated by OS on container stop; no action needed. |
| AC-006 | Single photo directory with no cleanup; old preview files accumulate. | Low | Implement periodic cleanup of stale preview files or size-based rotation. |

---

## 14. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| System Architect | EPF Project | 2025-11-08 | - |
| Software Architect | EPF Project | 2025-11-08 | - |
| Quality Assurance | - | - | - |

---

*Document generated from codebase analysis of repository state at commit 52 on main branch. All architectural descriptions reflect implemented design decisions, not planned features.*
