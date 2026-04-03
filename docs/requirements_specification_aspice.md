# Requirements Specification (ASPICE SWE.1 / SYS.2)

**Project:** EPF Home Assistant Add-ons Repository  
**Document ID:** EPF-REQ-001  
**Version:** 1.0.0  
**Date:** 2025-11-08  
**Baseline:** Repository commit 52 (main branch)  
**Status:** Released

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software requirements for the EPF (E-Paper Photo Frame) Home Assistant Add-on in accordance with ASPICE processes SWE.1 (Software Requirements Analysis) and SYS.2 (System Requirements Analysis). It serves as the single source of truth for functional, non-functional, interface, security, and performance requirements derived from the current codebase state.

### 1.2 Scope
The scope encompasses the single add-on `epf-eink-addon` within the repository, which provides a Flask-based server running inside a Home Assistant supervised Docker container. The server integrates with an Immich photo management backend, processes images for 7-color E-Ink displays (800x480), and serves the processed data to ESP32-based hardware clients.

### 1.3 References
- ASPICE v3.1 Process Reference Model
- Home Assistant Add-on Specification v1.0
- Immich API v1.x
- Waveshare 7.3inch E-Paper (7-color) Datasheet
- ESP32 FireBeetle E Hardware Reference

### 1.4 Terminology and Abbreviations

| Term | Definition |
|------|-----------|
| EPF | E-Paper Photo Frame |
| Immich | Self-hosted photo management system |
| ESP32 | Espressif microcontroller with WiFi |
| E-Ink | Electrophoretic display technology |
| Dithering | Color quantization with error diffusion |
| Cython | Python-to-C compiler for performance optimization |
| HA | Home Assistant |
| Ingress | HA mechanism for embedding add-on web UI |

---

## 2. System Context

### 2.1 System Boundary
The EPF Add-on operates as a Home Assistant supervised Docker container. It communicates with:
- **Immich Server** (external, via HTTP REST API)
- **ESP32 E-Paper Frame** (external, via HTTP client requests)
- **Home Assistant Supervisor** (internal, via bashio config API and ingress routing)
- **NTP Server** (external, pool.ntp.org)

### 2.2 Actors

| Actor | Role | Interaction |
|-------|------|-------------|
| HA User | Administrator | Configures add-on via HA UI / Ingress web interface |
| ESP32 Client | Hardware consumer | Fetches processed images, reports battery voltage, receives sleep duration |
| Immich Server | Data provider | Supplies album metadata and original image assets via REST API |
| HA Supervisor | Runtime environment | Provides configuration values, lifecycle management, ingress routing |

---

## 3. Requirements Catalog

### 3.1 Functional Requirements (FR)

#### FR-001: Immich Album Retrieval
| Attribute | Value |
|-----------|-------|
| **ID** | FR-001 |
| **Title** | Fetch album list from Immich |
| **Priority** | High |
| **Description** | The system SHALL retrieve the list of albums from the configured Immich server using the `/api/albums` endpoint with the configured API key in the `x-api-key` header. |
| **Input** | Immich URL, API key |
| **Output** | JSON array of albums |
| **Verification** | Test |
| **Traceability** | `app.py:download route` |

#### FR-002: Album Asset Retrieval
| Attribute | Value |
|-----------|-------|
| **ID** | FR-002 |
| **Title** | Fetch assets from selected album |
| **Priority** | High |
| **Description** | The system SHALL retrieve all assets from the album matching the configured album name using the `/api/albums/{album_id}` endpoint. |
| **Input** | Album ID, API key |
| **Output** | JSON object with assets array |
| **Verification** | Test |
| **Traceability** | `app.py:download route` |

#### FR-003: Image Selection Strategy
| Attribute | Value |
|-----------|-------|
| **ID** | FR-003 |
| **Title** | Select image based on configured order |
| **Priority** | High |
| **Description** | The system SHALL select an image from the album based on the configured `image_order` setting: `random` selects a random unseen image; `newest` selects the most recent unseen image by EXIF date. When all images have been shown, the tracking file SHALL be reset and the cycle restarts. |
| **Input** | Asset list, tracking file, image_order config |
| **Output** | Single selected asset |
| **Verification** | Test |
| **Traceability** | `app.py:download route, prepare-photo route` |

#### FR-004: Image Download
| Attribute | Value |
|-----------|-------|
| **ID** | FR-004 |
| **Title** | Download original image from Immich |
| **Priority** | High |
| **Description** | The system SHALL download the original image asset from Immich using the `/api/assets/{asset_id}/original` endpoint. |
| **Input** | Asset ID, API key |
| **Output** | Binary image data |
| **Verification** | Test |
| **Traceability** | `app.py:download route` |

#### FR-005: RAW/DNG/HEIC Conversion
| Attribute | Value |
|-----------|-------|
| **ID** | FR-005 |
| **Title** | Convert non-standard image formats to RGB |
| **Priority** | High |
| **Description** | The system SHALL convert RAW formats (.raw, .dng, .arw, .cr2, .nef) to RGB using rawpy with camera white balance, and HEIC files to RGB using pillow-heif. Standard formats (JPEG, BMP) SHALL be opened directly. |
| **Input** | Binary image data, file extension |
| **Output** | PIL Image in RGB mode |
| **Verification** | Test |
| **Traceability** | `app.py:convert_raw_or_dng_to_jpg, convert_heic_to_jpg` |

#### FR-006: Image Scaling and Rotation
| Attribute | Value |
|-----------|-------|
| **ID** | FR-006 |
| **Title** | Scale and rotate image to E-Ink display dimensions |
| **Priority** | High |
| **Description** | The system SHALL rotate the image by the configured angle (0, 90, 180, 270 degrees), apply EXIF auto-transpose, and scale to 800x480 pixels using either `fit` (letterbox with white background) or `fill` (crop to fill) mode. This processing SHALL be performed by the Cython module `cpy.load_scaled`. |
| **Input** | PIL Image, rotation angle, display mode |
| **Output** | PIL Image at 800x480 |
| **Verification** | Test |
| **Traceability** | `cpy.pyx:load_scaled, app.py:scale_img_in_memory` |

#### FR-007: Color Enhancement
| Attribute | Value |
|-----------|-------|
| **ID** | FR-007 |
| **Title** | Apply color and contrast enhancement |
| **Priority** | Medium |
| **Description** | The system SHALL apply color enhancement (factor 0.0-2.0) and contrast enhancement (factor 0.0-2.0) to the scaled image using PIL ImageEnhance before dithering. |
| **Input** | Scaled image, color factor, contrast factor |
| **Output** | Enhanced PIL Image |
| **Verification** | Test |
| **Traceability** | `app.py:scale_img_in_memory` |

#### FR-008: Dithering (Floyd-Steinberg)
| Attribute | Value |
|-----------|-------|
| **ID** | FR-008 |
| **Title** | Apply Floyd-Steinberg dithering |
| **Priority** | High |
| **Description** | The system SHALL apply Floyd-Steinberg error diffusion dithering to reduce the image to the 6-color E-Ink palette (Black, White, Yellow, Red, Blue, Green) with configurable strength (0.0-1.0). Processing SHALL be performed by the Cython module `cpy.convert_image`. |
| **Input** | Enhanced image, dithering strength |
| **Output** | Dithered RGB numpy array (800x480x3) |
| **Verification** | Test |
| **Traceability** | `cpy.pyx:convert_image` |

#### FR-009: Dithering (Atkinson)
| Attribute | Value |
|-----------|-------|
| **ID** | FR-009 |
| **Title** | Apply Atkinson dithering |
| **Priority** | High |
| **Description** | The system SHALL apply Atkinson error diffusion dithering (error multiplied by 0.75, distributed to 6 neighboring pixels at 1/8 each) to reduce the image to the 6-color E-Ink palette with configurable strength (0.0-1.0). Processing SHALL be performed by the Cython module `cpy.convert_image_atkinson`. |
| **Input** | Enhanced image, dithering strength |
| **Output** | Dithered RGB numpy array (800x480x3) |
| **Verification** | Test |
| **Traceability** | `cpy.pyx:convert_image_atkinson` |

#### FR-010: Date Overlay
| Attribute | Value |
|-----------|-------|
| **ID** | FR-010 |
| **Title** | Overlay EXIF date on processed image |
| **Priority** | Medium |
| **Description** | If EXIF DateTimeOriginal or DateTime metadata is present, the system SHALL render the date in `YYYY-MM-DD` format as white text on a black rectangle in the bottom-right corner of the processed image. |
| **Input** | Dithered image, EXIF datetime |
| **Output** | Image with date overlay |
| **Verification** | Test |
| **Traceability** | `app.py:scale_img_in_memory` |

#### FR-011: Preview Generation
| Attribute | Value |
|-----------|-------|
| **ID** | FR-011 |
| **Title** | Generate three preview versions |
| **Priority** | High |
| **Description** | The system SHALL save three versions of each processed image: (1) `latest_original.jpg` - unprocessed source resized to 800x480, (2) `latest_processed.jpg` - fully processed (rotated, enhanced, dithered), (3) `latest.bmp` - BMP format for ESP32 delivery. |
| **Input** | Original image, processed image |
| **Output** | Three files in photo directory |
| **Verification** | Test |
| **Traceability** | `app.py:save_three_previews` |

#### FR-012: Hex Format Conversion
| Attribute | Value |
|-----------|-------|
| **ID** | FR-012 |
| **Title** | Convert processed image to ESP32 hex format |
| **Priority** | High |
| **Description** | The system SHALL convert the processed BMP image to a comma-separated hex-encoded text format where each byte contains two 4-bit palette indices (high nibble = left pixel, low nibble = right pixel). The output SHALL be formatted as `text/plain` with filename `frame.txt`. |
| **Input** | BMP image |
| **Output** | BytesIO with comma-separated hex string |
| **Verification** | Test |
| **Traceability** | `app.py:convert_to_hex_format` |

#### FR-013: Image Delivery to ESP32
| Attribute | Value |
|-----------|-------|
| **ID** | FR-013 |
| **Title** | Serve processed image to ESP32 via /download |
| **Priority** | High |
| **Description** | The `/download` endpoint SHALL first check for a pre-prepared image with status `new`. If found, it SHALL serve the hex-encoded image and update status to `delivered`. If not found, it SHALL fetch and process a new image from Immich on-the-fly and serve it. |
| **Input** | HTTP GET request with optional batteryCap header |
| **Output** | Hex-encoded image file (frame.txt) |
| **Verification** | Test |
| **Traceability** | `app.py:download route` |

#### FR-014: Manual Photo Preparation
| Attribute | Value |
|-----------|-------|
| **ID** | FR-014 |
| **Title** | Manually prepare photo via /prepare-photo |
| **Priority** | Medium |
| **Description** | The `/prepare-photo` POST endpoint SHALL fetch an image from Immich, process it, save all three preview versions, and mark the status file as `new` for the next ESP32 download cycle. |
| **Input** | HTTP POST request |
| **Output** | JSON response with success status and asset_id |
| **Verification** | Test |
| **Traceability** | `app.py:prepare-photo route` |

#### FR-015: Preview Serving
| Attribute | Value |
|-----------|-------|
| **ID** | FR-015 |
| **Title** | Serve preview images via dedicated endpoints |
| **Priority** | Medium |
| **Description** | The system SHALL serve preview images via the following GET endpoints: `/preview-photo` (processed JPEG fallback), `/preview-original` (unprocessed JPEG), `/preview-processed` (dithered JPEG), `/preview-delivered` (last delivered JPEG). Each SHALL return 404 if the respective file does not exist. |
| **Input** | HTTP GET request |
| **Output** | JPEG image or JSON error |
| **Verification** | Test |
| **Traceability** | `app.py:preview routes` |

#### FR-016: Preview Status
| Attribute | Value |
|-----------|-------|
| **ID** | FR-016 |
| **Title** | Report preview photo status |
| **Priority** | Medium |
| **Description** | The `/preview-status` GET endpoint SHALL return a JSON object containing: `exists` (boolean), `status` (string: `new` or `delivered`), `timestamp` (Unix epoch), and `formatted_time` (human-readable). |
| **Input** | HTTP GET request |
| **Output** | JSON status object |
| **Verification** | Test |
| **Traceability** | `app.py:preview-status route` |

#### FR-017: Health Check
| Attribute | Value |
|-----------|-------|
| **ID** | FR-017 |
| **Title** | Provide health check endpoint |
| **Priority** | High |
| **Description** | The `/health` GET/HEAD endpoint SHALL ping the Immich server at `/api/server/ping` and return HTTP 200 with `{"status": "healthy", "immich": "connected"}` if successful, or HTTP 503 with `{"status": "degraded", "immich": "unreachable"}` if the ping fails. |
| **Input** | HTTP GET/HEAD request |
| **Output** | JSON health status |
| **Verification** | Test |
| **Traceability** | `app.py:health route, Dockerfile HEALTHCHECK` |

#### FR-018: Battery Status Reporting
| Attribute | Value |
|-----------|-------|
| **ID** | FR-018 |
| **Title** | Report battery status via API |
| **Priority** | Medium |
| **Description** | The `/api/battery-status` GET endpoint SHALL return the last reported battery voltage (received via `batteryCap` header on `/download`), calculated percentage, and timestamp. The last known value SHALL be retained indefinitely and SHALL NOT expire. A human-readable `formatted_timestamp` (YYYY-MM-DD HH:MM:SS) SHALL be included indicating when the reading was received. If no reading has been received yet, voltage SHALL be 0 and `formatted_timestamp` SHALL be null. |
| **Input** | HTTP GET request |
| **Output** | JSON with voltage, voltage_v, percentage, last_update, formatted_timestamp, age_seconds |
| **Verification** | Test |
| **Traceability** | `app.py:battery-status route` |

#### FR-019: Sleep Duration Calculation
| Attribute | Value |
|-----------|-------|
| **ID** | FR-019 |
| **Title** | Calculate ESP32 sleep duration |
| **Priority** | High |
| **Description** | The `/sleep` GET endpoint SHALL calculate the next wakeup time based on the configured `wakeup_interval` (30-1440 minutes), respecting the configured sleep time range (sleep_start to sleep_end). If the calculated next wakeup falls within the sleep range, the wakeup SHALL be deferred to the sleep end time. If the remaining sleep is less than 10 minutes, the next interval SHALL be skipped. |
| **Input** | HTTP GET request |
| **Output** | JSON with sleep_duration (ms), current_time, next_wakeup |
| **Verification** | Test |
| **Traceability** | `app.py:get_sleep_duration route` |

#### FR-020: Configuration Management
| Attribute | Value |
|-----------|-------|
| **ID** | FR-020 |
| **Title** | Manage configuration via HA and file watcher |
| **Priority** | High |
| **Description** | The system SHALL load configuration from Home Assistant via bashio environment variables at startup AND watch the `config/config.yaml` file for modifications using watchdog. Changes to the YAML file SHALL trigger a hot-reload of all configuration parameters without restarting the application. |
| **Input** | Environment variables, YAML file changes |
| **Output** | Updated global configuration |
| **Verification** | Test |
| **Traceability** | `app.py:ConfigFileHandler, run.sh` |

#### FR-021: Web Settings Interface
| Attribute | Value |
|-----------|-------|
| **ID** | FR-021 |
| **Title** | Provide web-based settings UI |
| **Priority** | High |
| **Description** | The root route `/` SHALL serve a responsive HTML settings page with: 3-column photo preview grid (delivered, original, processed), server connection fields (URL, album), display settings (rotation, display mode, image order, dithering method), image enhancement sliders (color, contrast, dithering strength), power management controls (sleep time range, wakeup interval), battery status display, dark/light theme toggle, and prepare new photo button. Form submission SHALL save configuration to YAML and trigger hot-reload. |
| **Input** | HTTP GET/POST request |
| **Output** | HTML page or redirect |
| **Verification** | Test |
| **Traceability** | `app.py:settings route, templates/settings.html` |

#### FR-022: Image Tracking
| Attribute | Value |
|-----------|-------|
| **ID** | FR-022 |
| **Title** | Track shown images to avoid repetition |
| **Priority** | Medium |
| **Description** | The system SHALL maintain a `tracking.txt` file that records the album name on the first line and all shown asset IDs on subsequent lines. When all images have been shown, the file SHALL be reset (keeping only the album name header). The tracking file SHALL have permissions set to 0o666. |
| **Input** | Asset IDs |
| **Output** | Updated tracking.txt |
| **Verification** | Test |
| **Traceability** | `app.py:load_downloaded_images, save_downloaded_image, reset_tracking_file` |

#### FR-023: NTP Time Synchronization
| Attribute | Value |
|-----------|-------|
| **ID** | FR-023 |
| **Title** | Perform daily NTP synchronization |
| **Priority** | Low |
| **Description** | The system SHALL run a background thread that synchronizes the system clock with `pool.ntp.org` daily at 04:00. Failed sync attempts SHALL be retried after 3600 seconds. The thread SHALL support graceful shutdown via a stop event signal. |
| **Input** | NTP server response |
| **Output** | System clock adjustment |
| **Verification** | Test |
| **Traceability** | `app.py:run_daily_ntp_sync, _ntp_stop_event` |

#### FR-024: Preview Cleanup
| Attribute | Value |
|-----------|-------|
| **ID** | FR-024 |
| **Title** | Automatic and manual preview file cleanup |
| **Priority** | Medium |
| **Description** | The system SHALL provide a cleanup function that removes stale preview files (latest_original_*.jpg, latest_processed_*.jpg, latest_delivered_*.jpg) based on two criteria: (1) age-based eviction for files older than 7 days, and (2) count-based eviction when more than 50 files match a pattern (oldest removed first). The cleanup SHALL be triggerable via POST `/cleanup-previews` endpoint and SHALL return the number of removed files. |
| **Input** | POST request to /cleanup-previews |
| **Output** | JSON response with files_removed count |
| **Verification** | Test |
| **Traceability** | `app.py:cleanup_old_previews, trigger_cleanup route` |

---

### 3.2 Non-Functional Requirements (NFR)

#### NFR-001: Multi-Architecture Support
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-001 |
| **Title** | Support multiple CPU architectures |
| **Priority** | High |
| **Description** | The add-on container SHALL be buildable and runnable on the following architectures: armhf, armv7, aarch64, amd64, i386. The base image SHALL be Debian Bookworm. |
| **Verification** | Inspection |
| **Traceability** | `config.yaml:arch, build.yaml, Dockerfile` |

#### NFR-002: Startup Behavior
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-002 |
| **Title** | Application startup configuration |
| **Priority** | High |
| **Description** | The add-on SHALL start as an `application` type with `auto` boot mode, without init system (`init: false`), and with ingress enabled on port 5000. |
| **Verification** | Inspection |
| **Traceability** | `config.yaml` |

#### NFR-003: Container Health Monitoring
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-003 |
| **Title** | Docker health check |
| **Priority** | High |
| **Description** | The container SHALL define a Docker HEALTHCHECK that polls `http://localhost:5000/health` every 30 seconds with a 10-second timeout, 60-second start period, and 3 retries. |
| **Verification** | Test |
| **Traceability** | `Dockerfile:HEALTHCHECK` |

#### NFR-004: Logging
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-004 |
| **Title** | Structured logging |
| **Priority** | High |
| **Description** | The application SHALL log to stdout with format `%(asctime)s - %(name)s - %(levelname)s - %(message)s`. The log level SHALL be configurable via the `log_level` option (debug, info, warning, error) and defaults to INFO. |
| **Verification** | Test |
| **Traceability** | `app.py:logging configuration, run.sh` |

#### NFR-005: Gunicorn Production Server
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-005 |
| **Title** | Production WSGI server |
| **Priority** | High |
| **Description** | The application SHALL be served by Gunicorn with 2 workers, 2 threads per worker, 120-second timeout, bound to 0.0.0.0:5000. |
| **Verification** | Inspection |
| **Traceability** | `run.sh` |

#### NFR-006: Response Time
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-006 |
| **Title** | Image processing performance |
| **Priority** | Medium |
| **Description** | Image processing (scaling, enhancement, dithering) for an 800x480 image SHALL complete within the Gunicorn timeout of 120 seconds. The Cython module SHALL be used for all performance-critical image processing operations. |
| **Verification** | Test |
| **Traceability** | `cpy.pyx, run.sh:timeout 120` |

#### NFR-007: Memory Footprint
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-007 |
| **Title** | Memory constraints |
| **Priority** | Medium |
| **Description** | The application SHALL operate within the memory constraints of typical Home Assistant host hardware. Image processing uses in-memory numpy arrays of size 800x480x3 (approximately 1.1 MB per array). |
| **Verification** | Analysis |
| **Traceability** | `cpy.pyx:EPD_W, EPD_H` |

#### NFR-008: Theme Support
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-008 |
| **Title** | Web UI dark/light theme |
| **Priority** | Low |
| **Description** | The settings web interface SHALL support both light and dark themes with CSS custom properties. The theme preference SHALL be persisted in localStorage. |
| **Verification** | Test |
| **Traceability** | `templates/settings.html` |

#### NFR-009: Type Annotations
| Attribute | Value |
|-----------|-------|
| **ID** | NFR-009 |
| **Title** | Code type hints |
| **Priority** | Medium |
| **Description** | All public functions, class methods, and module-level variables in `app.py` SHALL have Python type annotations. The `from __future__ import annotations` directive SHALL be used for forward reference support. Type hints SHALL cover all parameters, return types, and global state variables using the `typing` module (Optional, Dict, Any, Set, Tuple, Callable, List). |
| **Verification** | Inspection |
| **Traceability** | `app.py` |

---

### 3.3 Interface Requirements (IFR)

#### IFR-001: Immich REST API
| Attribute | Value |
|-----------|-------|
| **ID** | IFR-001 |
| **Title** | Immich API integration |
| **Priority** | High |
| **Description** | The system SHALL communicate with the Immich REST API using the following endpoints: `GET /api/albums` (list albums), `GET /api/albums/{id}` (get album assets), `GET /api/assets/{id}/original` (download image), `GET /api/server/ping` (health check). Authentication SHALL use the `x-api-key` header. All requests SHALL have a 10-30 second timeout. |
| **Protocol** | HTTPS/HTTP REST |
| **Verification** | Test |
| **Traceability** | `app.py:download, prepare-photo, health routes` |

#### IFR-002: ESP32 Client Interface
| Attribute | Value |
|-----------|-------|
| **ID** | IFR-002 |
| **Title** | ESP32 HTTP client interface |
| **Priority** | High |
| **Description** | The system SHALL serve ESP32 clients via HTTP on port 5000. The ESP32 SHALL send GET requests to `/download` and MAY include a `batteryCap` header with the current battery voltage in mV. The response SHALL be a `text/plain` file named `frame.txt` containing comma-separated hex-encoded pixel data. |
| **Protocol** | HTTP/1.1 |
| **Verification** | Test |
| **Traceability** | `app.py:download route` |

#### IFR-003: Home Assistant Ingress
| Attribute | Value |
|-----------|-------|
| **ID** | IFR-003 |
| **Title** | HA Ingress integration |
| **Priority** | High |
| **Description** | The add-on SHALL be accessible via Home Assistant Ingress on port 5000. The web UI SHALL function correctly when served under the `/api/hassio_ingress/` path prefix. The Flask app SHALL use ProxyFix middleware to handle reverse proxy headers. |
| **Protocol** | HTTP via HA proxy |
| **Verification** | Test |
| **Traceability** | `config.yaml:ingress, app.py:ProxyFix` |

#### IFR-004: Configuration Schema
| Attribute | Value |
|-----------|-------|
| **ID** | IFR-004 |
| **Title** | Home Assistant configuration schema |
| **Priority** | High |
| **Description** | The add-on SHALL define a configuration schema in `config.yaml` with the following typed fields: `immich_api_key` (str), `immich_url` (url), `album_name` (str), `rotation_angle` (list: 0|90|180|270), `color_enhance` (float 0-3), `contrast` (float 0-2), `dithering_strength` (float 0-1), `display_mode` (list: fit|fill), `image_order` (list: random|newest), `dithering_method` (list: atkinson|floyd-steinberg), `wakeup_interval` (int 30-1440), `sleep_start_hour` (int 0-23), `sleep_start_minute` (int 0-59), `sleep_end_hour` (int 0-23), `sleep_end_minute` (int 0-59), `log_level` (list: debug|info|warning|error). |
| **Protocol** | YAML |
| **Verification** | Inspection |
| **Traceability** | `config.yaml:schema` |

#### IFR-005: Network Port
| Attribute | Value |
|-----------|-------|
| **ID** | IFR-005 |
| **Title** | TCP port 5000 |
| **Priority** | High |
| **Description** | The add-on SHALL expose TCP port 5000 for both the web interface and the ESP32 API endpoint. The port mapping SHALL be configurable in the HA UI. |
| **Protocol** | TCP |
| **Verification** | Test |
| **Traceability** | `config.yaml:ports` |

---

### 3.4 Security Requirements (SEC)

#### SEC-001: API Key Protection
| Attribute | Value |
|-----------|-------|
| **ID** | SEC-001 |
| **Title** | Immich API key handling |
| **Priority** | High |
| **Description** | The Immich API key SHALL be stored only as an environment variable (`IMMICH_API_KEY`) and SHALL NOT be logged, echoed, or exposed in any HTTP response. The key SHALL be provided exclusively through the Home Assistant configuration UI. |
| **Verification** | Inspection |
| **Traceability** | `run.sh, app.py` |

#### SEC-002: Container Isolation
| Attribute | Value |
|-----------|-------|
| **ID** | SEC-002 |
| **Title** | Docker container isolation |
| **Priority** | High |
| **Description** | The add-on SHALL run as an isolated Docker container with no privileged access. The container SHALL use a non-root user context as provided by the Home Assistant base image. |
| **Verification** | Inspection |
| **Traceability** | `Dockerfile` |

#### SEC-003: Input Validation
| Attribute | Value |
|-----------|-------|
| **ID** | SEC-003 |
| **Title** | Configuration input validation |
| **Priority** | High |
| **Description** | All configuration values SHALL be validated against the schema defined in `config.yaml` by the Home Assistant supervisor. The application SHALL additionally validate critical parameters (e.g., rotation angle must be in [0, 90, 180, 270]) before processing. Invalid configurations SHALL be rejected with appropriate HTTP error codes. |
| **Verification** | Test |
| **Traceability** | `config.yaml:schema, app.py:settings route` |

#### SEC-004: Network Communication
| Attribute | Value |
|-----------|-------|
| **ID** | SEC-004 |
| **Title** | Network communication security |
| **Priority** | Medium |
| **Description** | Communication with the Immich server SHALL support both HTTP and HTTPS. The system SHALL use request timeouts to prevent connection hanging. No user credentials SHALL be transmitted; only API key-based authentication SHALL be used. |
| **Verification** | Inspection |
| **Traceability** | `app.py:requests calls` |

---

### 3.5 Performance Requirements (PER)

#### PER-001: Image Processing Throughput
| Attribute | Value |
|-----------|-------|
| **ID** | PER-001 |
| **Title** | Dithering performance |
| **Priority** | Medium |
| **Description** | The Cython-optimized dithering functions SHALL process an 800x480 RGB image within 30 seconds on ARMv7 hardware. The Floyd-Steinberg and Atkinson algorithms SHALL use O(n) pixel iteration with constant-space error diffusion. |
| **Verification** | Test |
| **Traceability** | `cpy.pyx:convert_image, convert_image_atkinson` |

#### PER-002: Concurrent Request Handling
| Attribute | Value |
|-----------|-------|
| **ID** | PER-002 |
| **Title** | Concurrent request capacity |
| **Priority** | Medium |
| **Description** | The Gunicorn server SHALL handle up to 4 concurrent requests (2 workers x 2 threads) without degradation. Image processing requests SHALL be serialized through the worker pool. |
| **Verification** | Test |
| **Traceability** | `run.sh:gunicorn` |

#### PER-003: Config Reload Latency
| Attribute | Value |
|-----------|-------|
| **ID** | PER-003 |
| **Title** | Configuration hot-reload latency |
| **Priority** | Low |
| **Description** | Configuration changes detected by the watchdog file observer SHALL be applied to the running application within 2 seconds of the YAML file modification. |
| **Verification** | Test |
| **Traceability** | `app.py:ConfigFileHandler` |

---

## 4. Requirements Traceability Matrix

| Req ID | Source File(s) | Verification Method | Status |
|--------|---------------|---------------------|--------|
| FR-001 | app.py | Test | Implemented |
| FR-002 | app.py | Test | Implemented |
| FR-003 | app.py | Test | Implemented |
| FR-004 | app.py | Test | Implemented |
| FR-005 | app.py | Test | Implemented |
| FR-006 | app.py, cpy.pyx | Test | Implemented |
| FR-007 | app.py | Test | Implemented |
| FR-008 | cpy.pyx | Test | Implemented |
| FR-009 | cpy.pyx | Test | Implemented |
| FR-010 | app.py | Test | Implemented |
| FR-011 | app.py | Test | Implemented |
| FR-012 | app.py | Test | Implemented |
| FR-013 | app.py | Test | Implemented |
| FR-014 | app.py | Test | Implemented |
| FR-015 | app.py | Test | Implemented |
| FR-016 | app.py | Test | Implemented |
| FR-017 | app.py, Dockerfile | Test | Implemented |
| FR-018 | app.py | Test | Implemented |
| FR-019 | app.py | Test | Implemented |
| FR-020 | app.py, run.sh | Test | Implemented |
| FR-021 | app.py, settings.html | Test | Implemented |
| FR-022 | app.py | Test | Implemented |
| FR-023 | app.py | Test | Implemented |
| FR-024 | app.py | Test | Implemented |
| NFR-001 | config.yaml, build.yaml, Dockerfile | Inspection | Implemented |
| NFR-002 | config.yaml | Inspection | Implemented |
| NFR-003 | Dockerfile | Test | Implemented |
| NFR-004 | app.py, run.sh | Test | Implemented |
| NFR-005 | run.sh | Inspection | Implemented |
| NFR-006 | cpy.pyx, run.sh | Test | Implemented |
| NFR-007 | cpy.pyx | Analysis | Implemented |
| NFR-008 | settings.html | Test | Implemented |
| NFR-009 | app.py | Inspection | Implemented |
| NFR-009 | app.py | Inspection | Implemented |
| IFR-001 | app.py | Test | Implemented |
| IFR-002 | app.py | Test | Implemented |
| IFR-003 | config.yaml, app.py | Test | Implemented |
| IFR-004 | config.yaml | Inspection | Implemented |
| IFR-005 | config.yaml | Test | Implemented |
| SEC-001 | run.sh, app.py | Inspection | Implemented |
| SEC-002 | Dockerfile | Inspection | Implemented |
| SEC-003 | config.yaml, app.py | Test | Implemented |
| SEC-004 | app.py | Inspection | Implemented |
| PER-001 | cpy.pyx | Test | Implemented |
| PER-002 | run.sh | Test | Implemented |
| PER-003 | app.py | Test | Implemented |

---

## 5. Open Issues and Risks

| ID | Description | Severity | Mitigation |
|----|-------------|----------|------------|
| OI-001 | `cpy.so` binary is committed to the repository; it is architecture-specific and will not work on non-amd64 platforms without recompilation during Docker build. | Medium | The Dockerfile recompiles the Cython module during build, overriding the committed .so. The committed file should be in .gitignore. |
| OI-002 | No TLS/HTTPS enforcement for ESP32 communication; images are served over plain HTTP on the local network. | Low | Acceptable for isolated LAN deployments; document in security guidance. |
| OI-003 | ~~The `color_enhance` slider in settings.html is capped at 2.0 while the config.yaml schema allows up to 3.0.~~ | ~~Low~~ | ~~UI inconsistency; slider max should match schema.~~ | **RESOLVED (v1.0.4)**: Slider max updated to 3.0. |
| OI-004 | ~~The `contrast` slider in settings.html is capped at 2.0 while the config.yaml schema allows up to 2.0 (matches). The `color_enhance` schema allows 0-3 but the slider only goes to 2.0.~~ | ~~Low~~ | ~~Align slider range with schema.~~ | **RESOLVED (v1.0.4)**: Slider range aligned with schema. |
| OI-005 | ~~NTP sync runs in a daemon thread with no graceful shutdown mechanism on container stop.~~ | ~~Low~~ | ~~Acceptable for container lifecycle; OS handles cleanup.~~ | **RESOLVED (v1.0.4)**: Graceful shutdown via threading.Event implemented. |
| OI-006 | No rate limiting on the `/download` endpoint; an ESP32 could trigger repeated Immich API calls. | Medium | ESP32 firmware controls call frequency; document expected behavior. |

---

## 6. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Project Lead | EPF Project | 2025-11-08 | - |
| Quality Assurance | - | - | - |

---

*Document generated from codebase analysis of repository state at commit 52 on main branch + v1.0.4 enhancements. All requirements reflect implemented functionality, not planned features.*
