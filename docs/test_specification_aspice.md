# Software Test Specification (ASPICE SWE.4 / SWE.5)

**Project:** EPF Home Assistant Add-ons Repository  
**Document ID:** EPF-TST-001  
**Version:** 1.0.0  
**Date:** 2025-11-08  
**Baseline:** Repository commit 52 (main branch)  
**Status:** Released  
**Parent Document:** EPF-REQ-001 (Requirements Specification)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the software test cases for verifying the EPF (E-Paper Photo Frame) Home Assistant Add-on in accordance with ASPICE processes SWE.4 (Software Unit Verification) and SWE.5 (Software Integration and Integration Test). Each test case is traceable to one or more requirements defined in EPF-REQ-001.

### 1.2 Scope
The scope encompasses all functional, non-functional, interface, security, and performance requirements for the `epf-eink-addon`. This includes:
- 24 Functional Requirements (FR-001 to FR-024)
- 8 Non-Functional Requirements (NFR-001 to NFR-008)
- 5 Interface Requirements (IFR-001 to IFR-005)
- 4 Security Requirements (SEC-001 to SEC-004)
- 3 Performance Requirements (PER-001 to PER-003)

### 1.3 References
- ASPICE v3.1 Process Reference Model
- EPF-REQ-001: Requirements Specification
- Home Assistant Add-on Specification v1.0
- Immich API v1.x
- Waveshare 7.3inch E-Paper (7-color) Datasheet

### 1.4 Terminology and Abbreviations

| Term | Definition |
|------|-----------|
| TC | Test Case |
| SUT | System Under Test |
| PASS | Test passed successfully |
| FAIL | Test failed |
| N/A | Not applicable |
| EPF | E-Paper Photo Frame |
| HA | Home Assistant |

---

## 2. Test Environment

### 2.1 Test Architecture (Mock-Based)

All tests run in an isolated Docker container without requiring Home Assistant or a real Immich server. External dependencies are simulated using `unittest.mock` and `responses` libraries.

```
┌─────────────────────────────────────────────────┐
│              Test Container                      │
│  ┌───────────────────────────────────────────┐  │
│  │           pytest Test Runner              │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │     Mock Immich API (responses)     │  │  │
│  │  │     Mock HA Supervisor (mock)       │  │  │
│  │  │     Mock ESP32 Client (test client) │  │  │
│  │  │     Mock NTP (mock)                 │  │  │
│  │  │     Mock Filesystem (tmp_path)      │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  │                    ↓                       │  │
│  │         Flask Test Client                  │  │
│  │                    ↓                       │  │
│  │         EPF Add-on (app.py)                │  │
│  │                    ↓                       │  │
│  │         Cython Module (cpy.so)             │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

### 2.1 Hardware Requirements

| Component | Specification |
|-----------|--------------|
| Host Machine | x86_64 or ARM64, 4 GB RAM minimum |
| Docker | 20.10+ for test container execution |

### 2.2 Software Requirements

| Component | Version |
|-----------|---------|
| Docker | 20.10+ |
| Python | 3.11+ (inside container) |
| pytest | 7.0+ |
| responses | 0.23+ (HTTP mocking) |
| Flask Test Client | Built-in |
| Cython Module | Compiled in container build |
| Debian Bookworm | Base image for container |

### 2.3 Mock Services

| Mock Service | Purpose | Implementation |
|-------------|---------|---------------|
| Mock Immich API | Simulates album/asset/ping endpoints | `responses` library |
| Mock HA Supervisor | Simulates bashio env vars | `os.environ` + `unittest.mock` |
| Mock Filesystem | Isolates file operations | `pytest.tmp_path` |
| Mock NTP | Prevents real network calls | `unittest.mock.patch` |
| Mock ESP32 Client | Simulates device requests | Flask Test Client |
| Mock Cython | Fallback if cpy.so unavailable | `unittest.mock.MagicMock` |

### 2.4 Test Data

| Data Type | Description | Source |
|-----------|------------|--------|
| Test JPEG | 800x600 RGB test image | Generated via Pillow |
| Test Albums | 3 mock albums with varying asset counts | `responses` mock |
| Test Assets | Mock asset metadata with EXIF info | `responses` mock |
| Test Config | YAML configuration for test runs | `tmp_path` fixture |

---

## 3. Test Cases

### 3.1 Functional Requirements Test Cases

#### TC-FR-001: Immich Album Retrieval

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-001 |
| **Requirement** | FR-001 |
| **Title** | Verify album list retrieval from Immich |
| **Priority** | High |
| **Preconditions** | SUT is running; Immich server is accessible; valid API key configured |
| **Test Input** | GET request to `/api/albums` with `x-api-key` header |
| **Test Steps** | 1. Configure valid Immich URL and API key in SUT<br>2. Trigger album retrieval via `/download` or `/prepare-photo` endpoint<br>3. Capture HTTP request sent to Immich<br>4. Verify response contains JSON array of albums |
| **Expected Result** | SUT successfully retrieves album list from Immich; HTTP request includes `x-api-key` header; response is valid JSON array |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-002: Album Asset Retrieval

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-002 |
| **Requirement** | FR-002 |
| **Title** | Verify asset retrieval from selected album |
| **Priority** | High |
| **Preconditions** | Album name configured; Immich server accessible; album contains assets |
| **Test Input** | Album ID matching configured `album_name` |
| **Test Steps** | 1. Configure `album_name` to match an existing Immich album<br>2. Trigger image fetch via `/download` endpoint<br>3. Verify SUT calls `/api/albums/{album_id}`<br>4. Verify response contains assets array |
| **Expected Result** | SUT retrieves all assets from the configured album; assets array is non-empty for albums with content |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-003: Image Selection Strategy

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-003 |
| **Requirement** | FR-003 |
| **Title** | Verify image selection based on configured order |
| **Priority** | High |
| **Preconditions** | Album with 5+ images; tracking.txt exists or is empty |
| **Test Input** | `image_order` set to `random` and `newest` (separate runs) |
| **Test Steps** | 1. Set `image_order` to `random`<br>2. Fetch 3 images via `/download`<br>3. Verify selected images are different and marked as shown<br>4. Reset tracking file<br>5. Set `image_order` to `newest`<br>6. Fetch 3 images<br>7. Verify images are selected by EXIF date (newest first)<br>8. Continue fetching until all images shown<br>9. Verify tracking file resets automatically |
| **Expected Result** | Random mode selects different unseen images; Newest mode selects by descending EXIF date; After all images shown, tracking file resets and cycle restarts |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-004: Image Download

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-004 |
| **Requirement** | FR-004 |
| **Title** | Verify original image download from Immich |
| **Priority** | High |
| **Preconditions** | Valid asset ID available; Immich server accessible |
| **Test Input** | Asset ID from album |
| **Test Steps** | 1. Select an asset from the album<br>2. Verify SUT calls `/api/assets/{asset_id}/original`<br>3. Verify response contains binary image data<br>4. Verify downloaded file is valid image format |
| **Expected Result** | SUT downloads original image successfully; binary data is valid and matches source file size |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-005: RAW/DNG/HEIC Conversion

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-005-RAW |
| **Requirement** | FR-005 |
| **Title** | Verify RAW format conversion to RGB |
| **Priority** | High |
| **Preconditions** | Test RAW files (.dng, .arw, .cr2, .nef) available |
| **Test Input** | RAW image file |
| **Test Steps** | 1. Upload a RAW (.dng) file to Immich test album<br>2. Trigger download and processing<br>3. Verify `convert_raw_or_dng_to_jpg` is called<br>4. Verify output is PIL Image in RGB mode<br>5. Verify camera white balance is applied |
| **Expected Result** | RAW file is converted to RGB PIL Image; white balance is applied correctly; no errors during conversion |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-005-HEIC |
| **Requirement** | FR-005 |
| **Title** | Verify HEIC format conversion to RGB |
| **Priority** | High |
| **Preconditions** | Test HEIC file available |
| **Test Input** | HEIC image file |
| **Test Steps** | 1. Upload a HEIC file to Immich test album<br>2. Trigger download and processing<br>3. Verify `convert_heic_to_jpg` is called<br>4. Verify output is PIL Image in RGB mode |
| **Expected Result** | HEIC file is converted to RGB PIL Image using pillow-heif; no errors during conversion |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-005-STD |
| **Requirement** | FR-005 |
| **Title** | Verify standard format handling (JPEG, BMP) |
| **Priority** | High |
| **Preconditions** | Test JPEG and BMP files available |
| **Test Input** | JPEG and BMP image files |
| **Test Steps** | 1. Upload a JPEG file to Immich test album<br>2. Trigger download and processing<br>3. Verify file is opened directly without conversion<br>4. Verify output is PIL Image in RGB mode<br>5. Repeat steps 1-4 with BMP file |
| **Expected Result** | Standard formats are opened directly; output is PIL Image in RGB mode; no conversion errors |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-006: Image Scaling and Rotation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-006 |
| **Requirement** | FR-006 |
| **Title** | Verify image scaling and rotation to E-Ink dimensions |
| **Priority** | High |
| **Preconditions** | Valid image loaded; Cython module compiled |
| **Test Input** | Rotation angles: 0, 90, 180, 270; Display modes: fit, fill |
| **Test Steps** | 1. Load test image (any size)<br>2. Set rotation to 0, display mode to `fit`<br>3. Process image via `cpy.load_scaled`<br>4. Verify output is 800x480 pixels<br>5. Repeat for rotation 90, 180, 270<br>6. Set display mode to `fill`<br>7. Verify output is 800x480 with cropping<br>8. Verify EXIF auto-transpose is applied |
| **Expected Result** | Output image is exactly 800x480 pixels; rotation is applied correctly; `fit` mode adds white letterbox; `fill` mode crops to fill; EXIF orientation is respected |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-007: Color Enhancement

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-007 |
| **Requirement** | FR-007 |
| **Title** | Verify color and contrast enhancement |
| **Priority** | Medium |
| **Preconditions** | Scaled image available |
| **Test Input** | Color factor: 0.0, 1.0, 2.0; Contrast factor: 0.0, 1.0, 2.0 |
| **Test Steps** | 1. Load scaled 800x480 image<br>2. Apply color_enhance=1.0, contrast=1.0 (neutral)<br>3. Verify image is unchanged<br>4. Apply color_enhance=2.0<br>5. Verify color saturation increased<br>6. Apply contrast=2.0<br>7. Verify contrast increased<br>8. Apply color_enhance=0.0<br>9. Verify image is grayscale |
| **Expected Result** | Enhancement factors are applied correctly using PIL ImageEnhance; neutral values (1.0) produce no change; extreme values produce expected effects |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-008: Dithering (Floyd-Steinberg)

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-008 |
| **Requirement** | FR-008 |
| **Title** | Verify Floyd-Steinberg dithering |
| **Priority** | High |
| **Preconditions** | Enhanced image available; Cython module compiled |
| **Test Input** | Dithering strength: 0.0, 0.5, 1.0 |
| **Test Steps** | 1. Load enhanced 800x480 image<br>2. Set dithering method to `floyd-steinberg`<br>3. Set dithering strength to 1.0<br>4. Process via `cpy.convert_image`<br>5. Verify output is numpy array of shape (800, 480, 3)<br>6. Verify all pixel values are in 6-color palette<br>7. Repeat with strength 0.5 and 0.0<br>8. Verify dithering effect decreases with strength |
| **Expected Result** | Output is RGB numpy array (800x480x3); all pixels use only 6 E-Ink colors (Black, White, Yellow, Red, Blue, Green); error diffusion is visible at strength 1.0; no dithering at strength 0.0 |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-009: Dithering (Atkinson)

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-009 |
| **Requirement** | FR-009 |
| **Title** | Verify Atkinson dithering |
| **Priority** | High |
| **Preconditions** | Enhanced image available; Cython module compiled |
| **Test Input** | Dithering strength: 0.0, 0.5, 1.0 |
| **Test Steps** | 1. Load enhanced 800x480 image<br>2. Set dithering method to `atkinson`<br>3. Set dithering strength to 1.0<br>4. Process via `cpy.convert_image_atkinson`<br>5. Verify output is numpy array of shape (800, 480, 3)<br>6. Verify error is multiplied by 0.75 and distributed to 6 neighbors at 1/8 each<br>7. Verify all pixel values are in 6-color palette<br>8. Repeat with strength 0.5 and 0.0 |
| **Expected Result** | Output is RGB numpy array (800x480x3); Atkinson error diffusion pattern is applied; all pixels use only 6 E-Ink colors; dithering strength modulates effect |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-010: Date Overlay

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-010-EXIF |
| **Requirement** | FR-010 |
| **Title** | Verify EXIF date overlay on processed image |
| **Priority** | Medium |
| **Preconditions** | Image with EXIF DateTimeOriginal available |
| **Test Input** | Image with EXIF DateTimeOriginal = "2024:06:15 14:30:00" |
| **Test Steps** | 1. Load image with EXIF DateTimeOriginal<br>2. Process image through full pipeline<br>3. Verify date "2024-06-15" is rendered in bottom-right corner<br>4. Verify date is white text on black rectangle<br>5. Load image without EXIF date<br>6. Process image<br>7. Verify no date overlay is present |
| **Expected Result** | Date is rendered as "YYYY-MM-DD" in bottom-right corner; white text on black rectangle; no overlay when EXIF date is absent |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-011: Preview Generation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-011 |
| **Requirement** | FR-011 |
| **Title** | Verify three preview versions are saved |
| **Priority** | High |
| **Preconditions** | Image processed through pipeline |
| **Test Input** | Processed image |
| **Test Steps** | 1. Process an image through full pipeline<br>2. Verify `latest_original.jpg` exists in photo directory<br>3. Verify `latest_processed.jpg` exists<br>4. Verify `latest.bmp` exists<br>5. Verify `latest_original.jpg` is 800x480 unprocessed<br>6. Verify `latest_processed.jpg` is dithered<br>7. Verify `latest.bmp` is valid BMP format |
| **Expected Result** | All three preview files are created; `latest_original.jpg` is resized source; `latest_processed.jpg` is fully processed; `latest.bmp` is valid BMP for ESP32 |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-012: Hex Format Conversion

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-012 |
| **Requirement** | FR-012 |
| **Title** | Verify hex format conversion for ESP32 |
| **Priority** | High |
| **Preconditions** | Valid BMP image (800x480) available |
| **Test Input** | BMP image |
| **Test Steps** | 1. Load processed BMP image<br>2. Call `convert_to_hex_format`<br>3. Verify output is BytesIO object<br>4. Verify content is comma-separated hex string<br>5. Verify each byte contains two 4-bit palette indices<br>6. Verify Content-Type is `text/plain`<br>7. Verify filename is `frame.txt` |
| **Expected Result** | Output is comma-separated hex string; high nibble = left pixel, low nibble = right pixel; Content-Type is `text/plain`; filename is `frame.txt` |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-013: Image Delivery to ESP32

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-013-PRE |
| **Requirement** | FR-013 |
| **Title** | Verify image delivery with pre-prepared image |
| **Priority** | High |
| **Preconditions** | Pre-prepared image with status `new` exists |
| **Test Input** | GET request to `/download` |
| **Test Steps** | 1. Prepare image via `/prepare-photo` endpoint<br>2. Verify status file shows `new`<br>3. Send GET request to `/download`<br>4. Verify response is `frame.txt` with hex-encoded image<br>5. Verify status file is updated to `delivered` |
| **Expected Result** | Pre-prepared image is served; status changes from `new` to `delivered`; response is valid hex-encoded image |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-013-OTF |
| **Requirement** | FR-013 |
| **Title** | Verify on-the-fly image delivery |
| **Priority** | High |
| **Preconditions** | No pre-prepared image exists |
| **Test Input** | GET request to `/download` with `batteryCap` header |
| **Test Steps** | 1. Remove any existing status file<br>2. Send GET request to `/download` with `batteryCap: 3300` header<br>3. Verify SUT fetches and processes image from Immich<br>4. Verify response is `frame.txt` with hex-encoded image<br>5. Verify battery voltage is recorded |
| **Expected Result** | Image is fetched and processed on-the-fly; hex-encoded image is served; battery voltage from header is recorded |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-014: Manual Photo Preparation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-014 |
| **Requirement** | FR-014 |
| **Title** | Verify manual photo preparation via /prepare-photo |
| **Priority** | Medium |
| **Preconditions** | SUT running; Immich accessible |
| **Test Input** | POST request to `/prepare-photo` |
| **Test Steps** | 1. Send POST request to `/prepare-photo`<br>2. Verify SUT fetches image from Immich<br>3. Verify image is processed through pipeline<br>4. Verify all three preview versions are saved<br>5. Verify status file is marked as `new`<br>6. Verify JSON response contains success status and asset_id |
| **Expected Result** | Image is fetched, processed, and saved; status file is `new`; JSON response contains `{"success": true, "asset_id": "..."}` |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-015: Preview Serving

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-015 |
| **Requirement** | FR-015 |
| **Title** | Verify preview image endpoints |
| **Priority** | Medium |
| **Preconditions** | Preview images exist (from prior processing) |
| **Test Input** | GET requests to `/preview-photo`, `/preview-original`, `/preview-processed`, `/preview-delivered` |
| **Test Steps** | 1. Send GET to `/preview-photo`<br>2. Verify JPEG image is returned<br>3. Send GET to `/preview-original`<br>4. Verify unprocessed JPEG is returned<br>5. Send GET to `/preview-processed`<br>6. Verify dithered JPEG is returned<br>7. Send GET to `/preview-delivered`<br>8. Verify last delivered JPEG is returned<br>9. Delete preview files<br>10. Repeat requests<br>11. Verify 404 JSON error is returned for each |
| **Expected Result** | Each endpoint returns correct JPEG image; missing files return 404 with JSON error |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-016: Preview Status

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-016 |
| **Requirement** | FR-016 |
| **Title** | Verify preview status endpoint |
| **Priority** | Medium |
| **Preconditions** | SUT running; status file may or may not exist |
| **Test Input** | GET request to `/preview-status` |
| **Test Steps** | 1. Prepare image via `/prepare-photo`<br>2. Send GET to `/preview-status`<br>3. Verify JSON contains `exists: true`<br>4. Verify `status` is `new`<br>5. Verify `timestamp` is Unix epoch<br>6. Verify `formatted_time` is human-readable<br>7. Download image via `/download`<br>8. Send GET to `/preview-status`<br>9. Verify `status` is `delivered` |
| **Expected Result** | JSON response contains `exists`, `status`, `timestamp`, `formatted_time`; status transitions from `new` to `delivered` after download |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-017: Health Check

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-017-OK |
| **Requirement** | FR-017 |
| **Title** | Verify health check when Immich is reachable |
| **Priority** | High |
| **Preconditions** | SUT running; Immich server accessible |
| **Test Input** | GET request to `/health` |
| **Test Steps** | 1. Send GET to `/health`<br>2. Verify HTTP status is 200<br>3. Verify response is `{"status": "healthy", "immich": "connected"}`<br>4. Send HEAD to `/health`<br>5. Verify HTTP status is 200 |
| **Expected Result** | GET returns 200 with healthy status; HEAD returns 200 |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-017-FAIL |
| **Requirement** | FR-017 |
| **Title** | Verify health check when Immich is unreachable |
| **Priority** | High |
| **Preconditions** | SUT running; Immich server stopped or unreachable |
| **Test Input** | GET request to `/health` |
| **Test Steps** | 1. Stop Immich server or block network access<br>2. Send GET to `/health`<br>3. Verify HTTP status is 503<br>4. Verify response is `{"status": "degraded", "immich": "unreachable"}` |
| **Expected Result** | GET returns 503 with degraded status when Immich ping fails |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-018: Battery Status Reporting

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-018 |
| **Requirement** | FR-018 |
| **Title** | Verify battery status endpoint |
| **Priority** | Medium |
| **Preconditions** | SUT running; no prior battery data |
| **Test Input** | GET request to `/api/battery-status` |
| **Test Steps** | 1. Send GET to `/api/battery-status` before any download<br>2. Verify voltage is 0<br>3. Verify `formatted_timestamp` is null<br>4. Send GET to `/download` with `batteryCap: 3300` header<br>5. Send GET to `/api/battery-status`<br>6. Verify voltage is 3300<br>7. Verify `voltage_v` is 3.3<br>8. Verify percentage is calculated<br>9. Verify `formatted_timestamp` is YYYY-MM-DD HH:MM:SS<br>10. Wait 60 seconds<br>11. Send GET to `/api/battery-status`<br>12. Verify last value is retained (not expired) |
| **Expected Result** | Initial state: voltage=0, formatted_timestamp=null; After download: all fields populated; Value persists indefinitely |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-019: Sleep Duration Calculation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-019 |
| **Requirement** | FR-019 |
| **Title** | Verify sleep duration calculation |
| **Priority** | High |
| **Preconditions** | SUT running; sleep time range and wakeup interval configured |
| **Test Input** | GET request to `/sleep` |
| **Test Steps** | 1. Configure `wakeup_interval=60`, `sleep_start=22:00`, `sleep_end=06:00`<br>2. Send GET to `/sleep` during active hours<br>3. Verify `sleep_duration` is 60 minutes in ms<br>4. Verify `next_wakeup` is current time + 60 minutes<br>5. Send GET to `/sleep` during sleep range<br>6. Verify wakeup is deferred to sleep_end time<br>7. Configure `wakeup_interval=5` (less than 10 min threshold)<br>8. Send GET to `/sleep`<br>9. Verify next interval is skipped |
| **Expected Result** | Sleep duration respects wakeup_interval; Sleep range defers wakeup; Remaining sleep < 10 min skips interval |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-020: Configuration Management

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-020-START |
| **Requirement** | FR-020 |
| **Title** | Verify configuration loading at startup |
| **Priority** | High |
| **Preconditions** | SUT not running; environment variables set |
| **Test Input** | Environment variables via bashio |
| **Test Steps** | 1. Set environment variables (IMMICH_API_KEY, IMMICH_URL, etc.)<br>2. Start SUT<br>3. Verify configuration is loaded from environment<br>4. Verify all config parameters are accessible in application |
| **Expected Result** | Configuration is loaded from environment variables at startup; all parameters are accessible |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-020-HOT |
| **Requirement** | FR-020 |
| **Title** | Verify configuration hot-reload via YAML file |
| **Priority** | High |
| **Preconditions** | SUT running; watchdog monitoring active |
| **Test Input** | Modified config/config.yaml |
| **Test Steps** | 1. Record current configuration values<br>2. Modify `config/config.yaml` (change album_name)<br>3. Wait up to 2 seconds<br>4. Verify configuration is updated without restart<br>5. Verify new album_name is active |
| **Expected Result** | YAML file changes trigger hot-reload; configuration updates within 2 seconds; no application restart required |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-021: Web Settings Interface

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-021 |
| **Requirement** | FR-021 |
| **Title** | Verify web-based settings UI |
| **Priority** | High |
| **Preconditions** | SUT running; browser or HTTP client available |
| **Test Input** | GET/POST request to `/` |
| **Test Steps** | 1. Send GET to `/`<br>2. Verify HTML settings page is returned<br>3. Verify 3-column photo preview grid exists (delivered, original, processed)<br>4. Verify server connection fields (URL, album)<br>5. Verify display settings (rotation, display mode, image order, dithering method)<br>6. Verify enhancement sliders (color, contrast, dithering strength)<br>7. Verify power management controls (sleep time range, wakeup interval)<br>8. Verify battery status display<br>9. Verify dark/light theme toggle<br>10. Verify prepare new photo button<br>11. Submit form with modified values<br>12. Verify configuration is saved to YAML<br>13. Verify hot-reload is triggered |
| **Expected Result** | All UI elements are present and functional; form submission saves config and triggers hot-reload; page is responsive |
| **Verification Method** | Test (Manual/Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-022: Image Tracking

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-022 |
| **Requirement** | FR-022 |
| **Title** | Verify image tracking file management |
| **Priority** | Medium |
| **Preconditions** | Album with 3 images; empty tracking.txt |
| **Test Input** | Sequential image downloads |
| **Test Steps** | 1. Download first image<br>2. Verify tracking.txt contains album name on line 1<br>3. Verify asset ID is on line 2<br>4. Download second and third images<br>5. Verify all 3 asset IDs are recorded<br>6. Download fourth image (all shown)<br>7. Verify tracking file is reset (only album name header remains)<br>8. Verify tracking file permissions are 0o666 |
| **Expected Result** | Tracking file records album name and shown asset IDs; file resets after all images shown; permissions are 0o666 |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-023: NTP Time Synchronization

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-023 |
| **Requirement** | FR-023 |
| **Title** | Verify daily NTP synchronization |
| **Priority** | Low |
| **Preconditions** | SUT running; network access to pool.ntp.org |
| **Test Input** | Time-based trigger (04:00) or manual trigger |
| **Test Steps** | 1. Verify NTP sync thread is running<br>2. Check log for NTP sync attempt at 04:00<br>3. Verify system clock is synchronized<br>4. Simulate NTP failure (block pool.ntp.org)<br>5. Verify retry occurs after 3600 seconds<br>6. Verify error is logged |
| **Expected Result** | NTP sync runs daily at 04:00; failed attempts retry after 3600 seconds; errors are logged |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-FR-024: Preview Cleanup

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-FR-024 |
| **Requirement** | FR-024 |
| **Title** | Verify preview file cleanup functionality |
| **Priority** | Medium |
| **Preconditions** | SUT running; multiple preview files exist in photo directory |
| **Test Input** | POST request to /cleanup-previews |
| **Test Steps** | 1. Create multiple preview files with varying ages<br>2. Verify files exist before cleanup<br>3. Send POST to /cleanup-previews<br>4. Verify response contains files_removed count<br>5. Verify old files (>7 days) are removed<br>6. Verify count-based eviction works when >50 files exist<br>7. Verify cleanup does not remove current preview files (latest_original.jpg, latest_processed.jpg, latest.bmp) |
| **Expected Result** | Old/excess preview files are removed; response contains accurate count; current previews are preserved |
| **Verification Method** | Test (Automated) |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-009: Type Annotations

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-009 |
| **Requirement** | NFR-009 |
| **Title** | Verify type annotations throughout codebase |
| **Priority** | Medium |
| **Preconditions** | app.py source code available |
| **Test Input** | Static analysis of app.py |
| **Test Steps** | 1. Verify `from __future__ import annotations` is present<br>2. Verify all function signatures have parameter and return type hints<br>3. Verify global variables have type annotations<br>4. Verify class attributes have type annotations<br>5. Verify typing module imports (Optional, Dict, Any, Set, Tuple, Callable, List) |
| **Expected Result** | All public functions, class methods, and module-level variables have type annotations |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

---

### 3.2 Non-Functional Requirements Test Cases

#### TC-NFR-001: Multi-Architecture Support

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-001 |
| **Requirement** | NFR-001 |
| **Title** | Verify multi-architecture build and runtime |
| **Priority** | High |
| **Preconditions** | Docker build environment; access to multi-arch builders |
| **Test Input** | Build command for each architecture |
| **Test Steps** | 1. Build container for armhf<br>2. Verify build succeeds<br>3. Build for armv7, aarch64, amd64, i386<br>4. Verify each build succeeds<br>5. Verify base image is Debian Bookworm<br>6. Run container on each architecture<br>7. Verify application starts successfully |
| **Expected Result** | Container builds and runs on all 5 architectures; base image is Debian Bookworm |
| **Verification Method** | Inspection, Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-002: Startup Behavior

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-002 |
| **Requirement** | NFR-002 |
| **Title** | Verify application startup configuration |
| **Priority** | High |
| **Preconditions** | Add-on installed in Home Assistant |
| **Test Input** | config.yaml inspection |
| **Test Steps** | 1. Inspect config.yaml<br>2. Verify `type: application`<br>3. Verify `boot: auto`<br>4. Verify `init: false`<br>5. Verify `ingress: true`<br>6. Verify `ingress_port: 5000`<br>7. Start add-on<br>8. Verify container starts without init system |
| **Expected Result** | All startup configuration values match specification; container starts correctly |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-003: Container Health Monitoring

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-003 |
| **Requirement** | NFR-003 |
| **Title** | Verify Docker health check configuration |
| **Priority** | High |
| **Preconditions** | Container is running |
| **Test Input** | Docker inspect command |
| **Test Steps** | 1. Run `docker inspect` on running container<br>2. Verify HEALTHCHECK is defined<br>3. Verify interval is 30 seconds<br>4. Verify timeout is 10 seconds<br>5. Verify start_period is 60 seconds<br>6. Verify retries is 3<br>7. Verify health check URL is `http://localhost:5000/health` |
| **Expected Result** | HEALTHCHECK is configured with specified parameters; health endpoint is polled correctly |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-004: Logging

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-004 |
| **Requirement** | NFR-004 |
| **Title** | Verify structured logging configuration |
| **Priority** | High |
| **Preconditions** | SUT running |
| **Test Input** | Log output inspection |
| **Test Steps** | 1. Start SUT<br>2. Capture stdout output<br>3. Verify log format matches `%(asctime)s - %(name)s - %(levelname)s - %(message)s`<br>4. Verify default log level is INFO<br>5. Change `log_level` to `debug`<br>6. Verify DEBUG messages appear<br>7. Change to `error`<br>8. Verify only ERROR messages appear |
| **Expected Result** | Log format matches specification; log level is configurable; default is INFO |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-005: Gunicorn Production Server

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-005 |
| **Requirement** | NFR-005 |
| **Title** | Verify Gunicorn server configuration |
| **Priority** | High |
| **Preconditions** | SUT running |
| **Test Input** | run.sh inspection; process inspection |
| **Test Steps** | 1. Inspect run.sh<br>2. Verify gunicorn command includes `--workers 2`<br>3. Verify `--threads 2`<br>4. Verify `--timeout 120`<br>5. Verify bind is `0.0.0.0:5000`<br>6. Verify running processes show 2 gunicorn workers |
| **Expected Result** | Gunicorn is configured with 2 workers, 2 threads, 120s timeout, bound to 0.0.0.0:5000 |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-006: Response Time

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-006 |
| **Requirement** | NFR-006 |
| **Title** | Verify image processing completes within timeout |
| **Priority** | Medium |
| **Preconditions** | SUT running; test images available |
| **Test Input** | 800x480 test image |
| **Test Steps** | 1. Start timer<br>2. Trigger image processing via `/prepare-photo`<br>3. Stop timer when processing completes<br>4. Verify processing time is under 120 seconds<br>5. Verify Cython module was used (check logs) |
| **Expected Result** | Image processing completes within 120 seconds; Cython module is used for performance-critical operations |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-007: Memory Footprint

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-007 |
| **Requirement** | NFR-007 |
| **Title** | Verify memory usage during image processing |
| **Priority** | Medium |
| **Preconditions** | SUT running; memory monitoring tool available |
| **Test Input** | 800x480 image processing |
| **Test Steps** | 1. Record baseline memory usage<br>2. Trigger image processing<br>3. Monitor peak memory during processing<br>4. Verify numpy arrays are 800x480x3 (~1.1 MB each)<br>5. Verify memory is released after processing<br>6. Verify total memory is within typical HA host constraints |
| **Expected Result** | Memory usage is within acceptable limits; numpy arrays are correct size; memory is properly released |
| **Verification Method** | Analysis |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-NFR-008: Theme Support

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-NFR-008 |
| **Requirement** | NFR-008 |
| **Title** | Verify web UI theme support |
| **Priority** | Low |
| **Preconditions** | SUT running; browser available |
| **Test Input** | Theme toggle interaction |
| **Test Steps** | 1. Open settings page in browser<br>2. Verify default theme (light) is applied<br>3. Click theme toggle<br>4. Verify dark theme is applied<br>5. Verify CSS custom properties change<br>6. Refresh browser<br>7. Verify theme preference is persisted from localStorage |
| **Expected Result** | Both light and dark themes are functional; theme preference persists across page reloads via localStorage |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

---

### 3.3 Interface Requirements Test Cases

#### TC-IFR-001: Immich REST API

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-IFR-001 |
| **Requirement** | IFR-001 |
| **Title** | Verify Immich API integration |
| **Priority** | High |
| **Preconditions** | Immich server running; valid API key |
| **Test Input** | API requests to Immich endpoints |
| **Test Steps** | 1. Verify SUT calls `GET /api/albums` to list albums<br>2. Verify SUT calls `GET /api/albums/{id}` for assets<br>3. Verify SUT calls `GET /api/assets/{id}/original` for download<br>4. Verify SUT calls `GET /api/server/ping` for health<br>5. Verify `x-api-key` header is included in all requests<br>6. Verify request timeouts are 10-30 seconds |
| **Expected Result** | All specified endpoints are called correctly; API key header is present; timeouts are within range |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-IFR-002: ESP32 Client Interface

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-IFR-002 |
| **Requirement** | IFR-002 |
| **Title** | Verify ESP32 HTTP client interface |
| **Priority** | High |
| **Preconditions** | SUT running on port 5000 |
| **Test Input** | HTTP GET request with batteryCap header |
| **Test Steps** | 1. Send GET to `/download` without batteryCap<br>2. Verify response is served<br>3. Send GET with `batteryCap: 3500` header<br>4. Verify response is `text/plain`<br>5. Verify Content-Disposition filename is `frame.txt`<br>6. Verify body is comma-separated hex-encoded pixel data |
| **Expected Result** | ESP32 clients are served correctly; batteryCap header is optional; response format is correct |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-IFR-003: Home Assistant Ingress

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-IFR-003 |
| **Requirement** | IFR-003 |
| **Title** | Verify HA Ingress integration |
| **Priority** | High |
| **Preconditions** | Add-on installed in Home Assistant |
| **Test Input** | Access via HA Ingress URL |
| **Test Steps** | 1. Access add-on via HA UI<br>2. Verify web UI loads under `/api/hassio_ingress/` path<br>3. Verify all resources (CSS, JS, images) load correctly<br>4. Verify form submissions work through proxy<br>5. Verify ProxyFix middleware handles reverse proxy headers |
| **Expected Result** | Web UI functions correctly under HA Ingress; all resources load; ProxyFix handles proxy headers |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-IFR-004: Configuration Schema

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-IFR-004 |
| **Requirement** | IFR-004 |
| **Title** | Verify configuration schema |
| **Priority** | High |
| **Preconditions** | config.yaml available |
| **Test Input** | config.yaml inspection |
| **Test Steps** | 1. Inspect config.yaml schema<br>2. Verify all 16 fields are defined with correct types<br>3. Verify `immich_api_key` is str<br>4. Verify `immich_url` is url<br>5. Verify `rotation_angle` is list: 0|90|180|270<br>6. Verify `color_enhance` is float 0-3<br>7. Verify `contrast` is float 0-2<br>8. Verify `dithering_strength` is float 0-1<br>9. Verify `wakeup_interval` is int 30-1440<br>10. Verify all other fields match specification |
| **Expected Result** | All configuration fields are defined with correct types and ranges in config.yaml |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-IFR-005: Network Port

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-IFR-005 |
| **Requirement** | IFR-005 |
| **Title** | Verify TCP port 5000 exposure |
| **Priority** | High |
| **Preconditions** | Add-on running |
| **Test Input** | Network port inspection |
| **Test Steps** | 1. Verify container exposes port 5000<br>2. Verify port mapping is configurable in HA UI<br>3. Send HTTP request to port 5000<br>4. Verify web interface responds<br>5. Verify ESP32 API endpoint responds on same port |
| **Expected Result** | Port 5000 is exposed and configurable; both web UI and API respond on this port |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

---

### 3.4 Security Requirements Test Cases

#### TC-SEC-001: API Key Protection

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-SEC-001 |
| **Requirement** | SEC-001 |
| **Title** | Verify Immich API key protection |
| **Priority** | High |
| **Preconditions** | SUT running; API key configured |
| **Test Input** | Log output inspection; HTTP response inspection |
| **Test Steps** | 1. Configure API key via HA UI<br>2. Verify key is stored as environment variable `IMMICH_API_KEY`<br>3. Trigger operations that use the API key<br>4. Inspect logs for any occurrence of the API key<br>5. Inspect HTTP responses for API key leakage<br>6. Verify API key is not echoed in any output |
| **Expected Result** | API key is only in environment variable; key does not appear in logs or HTTP responses |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-SEC-002: Container Isolation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-SEC-002 |
| **Requirement** | SEC-002 |
| **Title** | Verify Docker container isolation |
| **Priority** | High |
| **Preconditions** | Container running |
| **Test Input** | Docker inspect; security audit |
| **Test Steps** | 1. Run `docker inspect` on container<br>2. Verify `Privileged` is false<br>3. Verify user is not root (check `User` field)<br>4. Verify no unnecessary capabilities are granted<br>5. Verify container uses Home Assistant base image |
| **Expected Result** | Container runs without privileged access; non-root user context is used |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-SEC-003: Input Validation

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-SEC-003 |
| **Requirement** | SEC-003 |
| **Title** | Verify configuration input validation |
| **Priority** | High |
| **Preconditions** | SUT running |
| **Test Input** | Invalid configuration values |
| **Test Steps** | 1. Submit rotation_angle=45 (invalid)<br>2. Verify request is rejected with HTTP error<br>3. Submit color_enhance=5.0 (out of range)<br>4. Verify request is rejected<br>5. Submit wakeup_interval=10 (below minimum)<br>6. Verify request is rejected<br>7. Verify HA supervisor validates against config.yaml schema |
| **Expected Result** | Invalid configurations are rejected with appropriate HTTP error codes; HA supervisor validates against schema |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-SEC-004: Network Communication

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-SEC-004 |
| **Requirement** | SEC-004 |
| **Title** | Verify network communication security |
| **Priority** | Medium |
| **Preconditions** | SUT running; Immich accessible via HTTP and HTTPS |
| **Test Input** | Network traffic analysis |
| **Test Steps** | 1. Configure Immich URL with HTTP<br>2. Verify communication succeeds<br>3. Configure Immich URL with HTTPS<br>4. Verify communication succeeds<br>5. Verify request timeouts prevent connection hanging<br>6. Verify no user credentials are transmitted<br>7. Verify only API key authentication is used |
| **Expected Result** | Both HTTP and HTTPS are supported; timeouts prevent hanging; no credentials transmitted; API key authentication only |
| **Verification Method** | Inspection |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

---

### 3.5 Performance Requirements Test Cases

#### TC-PER-001: Image Processing Throughput

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-PER-001 |
| **Requirement** | PER-001 |
| **Title** | Verify dithering performance on ARMv7 |
| **Priority** | Medium |
| **Preconditions** | ARMv7 hardware or emulator available; Cython module compiled |
| **Test Input** | 800x480 RGB image |
| **Test Steps** | 1. Load 800x480 RGB test image<br>2. Start timer<br>3. Process with Floyd-Steinberg dithering<br>4. Stop timer<br>5. Verify processing time is under 30 seconds<br>6. Repeat with Atkinson dithering<br>7. Verify processing time is under 30 seconds<br>8. Verify algorithm uses O(n) pixel iteration |
| **Expected Result** | Both dithering algorithms complete within 30 seconds on ARMv7; algorithms use O(n) iteration |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-PER-002: Concurrent Request Handling

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-PER-002 |
| **Requirement** | PER-002 |
| **Title** | Verify concurrent request capacity |
| **Priority** | Medium |
| **Preconditions** | SUT running with Gunicorn (2 workers x 2 threads) |
| **Test Input** | 4 concurrent HTTP requests |
| **Test Steps** | 1. Send 4 concurrent requests to different endpoints<br>2. Verify all 4 requests are handled<br>3. Verify no request fails due to capacity<br>4. Send 5 concurrent requests<br>5. Verify 5th request is queued (not rejected)<br>6. Verify image processing requests are serialized through worker pool |
| **Expected Result** | Up to 4 concurrent requests handled without degradation; additional requests are queued |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

#### TC-PER-003: Config Reload Latency

| Attribute | Value |
|-----------|-------|
| **Test Case ID** | TC-PER-003 |
| **Requirement** | PER-003 |
| **Title** | Verify configuration hot-reload latency |
| **Priority** | Low |
| **Preconditions** | SUT running; watchdog monitoring active |
| **Test Input** | YAML file modification with timestamp |
| **Test Steps** | 1. Record current configuration value<br>2. Record timestamp T0<br>3. Modify config/config.yaml<br>4. Record timestamp T1 when modification is complete<br>5. Poll configuration until change is detected<br>6. Record timestamp T2 when change is visible<br>7. Calculate reload latency = T2 - T1<br>8. Verify latency is under 2 seconds |
| **Expected Result** | Configuration changes are applied within 2 seconds of YAML file modification |
| **Verification Method** | Test |
| **Actual Result** | _To be filled during execution_ |
| **Status** | Not Executed |

---

## 4. Test Traceability Matrix

| Test Case ID | Requirement(s) | Verification Method | Status |
|-------------|---------------|-------------------|--------|
| TC-FR-001 | FR-001 | Test | Not Executed |
| TC-FR-002 | FR-002 | Test | Not Executed |
| TC-FR-003 | FR-003 | Test | Not Executed |
| TC-FR-004 | FR-004 | Test | Not Executed |
| TC-FR-005-RAW | FR-005 | Test | Not Executed |
| TC-FR-005-HEIC | FR-005 | Test | Not Executed |
| TC-FR-005-STD | FR-005 | Test | Not Executed |
| TC-FR-006 | FR-006 | Test | Not Executed |
| TC-FR-007 | FR-007 | Test | Not Executed |
| TC-FR-008 | FR-008 | Test | Not Executed |
| TC-FR-009 | FR-009 | Test | Not Executed |
| TC-FR-010-EXIF | FR-010 | Test | Not Executed |
| TC-FR-011 | FR-011 | Test | Not Executed |
| TC-FR-012 | FR-012 | Test | Not Executed |
| TC-FR-013-PRE | FR-013 | Test | Not Executed |
| TC-FR-013-OTF | FR-013 | Test | Not Executed |
| TC-FR-014 | FR-014 | Test | Not Executed |
| TC-FR-015 | FR-015 | Test | Not Executed |
| TC-FR-016 | FR-016 | Test | Not Executed |
| TC-FR-017-OK | FR-017 | Test | Not Executed |
| TC-FR-017-FAIL | FR-017 | Test | Not Executed |
| TC-FR-018 | FR-018 | Test | Not Executed |
| TC-FR-019 | FR-019 | Test | Not Executed |
| TC-FR-020-START | FR-020 | Test | Not Executed |
| TC-FR-020-HOT | FR-020 | Test | Not Executed |
| TC-FR-021 | FR-021 | Test | Not Executed |
| TC-FR-022 | FR-022 | Test | Not Executed |
| TC-FR-023 | FR-023 | Test | Not Executed |
| TC-FR-024 | FR-024 | Test | Not Executed |
| TC-NFR-001 | NFR-001 | Inspection, Test | Not Executed |
| TC-NFR-002 | NFR-002 | Inspection | Not Executed |
| TC-NFR-003 | NFR-003 | Test | Not Executed |
| TC-NFR-004 | NFR-004 | Test | Not Executed |
| TC-NFR-005 | NFR-005 | Inspection | Not Executed |
| TC-NFR-006 | NFR-006 | Test | Not Executed |
| TC-NFR-007 | NFR-007 | Analysis | Not Executed |
| TC-NFR-008 | NFR-008 | Test | Not Executed |
| TC-NFR-009 | NFR-009 | Inspection | Not Executed |
| TC-NFR-009 | NFR-009 | Inspection | Not Executed |
| TC-IFR-001 | IFR-001 | Test | Not Executed |
| TC-IFR-002 | IFR-002 | Test | Not Executed |
| TC-IFR-003 | IFR-003 | Test | Not Executed |
| TC-IFR-004 | IFR-004 | Inspection | Not Executed |
| TC-IFR-005 | IFR-005 | Test | Not Executed |
| TC-SEC-001 | SEC-001 | Inspection | Not Executed |
| TC-SEC-002 | SEC-002 | Inspection | Not Executed |
| TC-SEC-003 | SEC-003 | Test | Not Executed |
| TC-SEC-004 | SEC-004 | Inspection | Not Executed |
| TC-PER-001 | PER-001 | Test | Not Executed |
| TC-PER-002 | PER-002 | Test | Not Executed |
| TC-PER-003 | PER-003 | Test | Not Executed |

---

## 5. Test Summary

### 5.1 Test Coverage

| Category | Requirements | Test Cases | Coverage |
|----------|-------------|------------|----------|
| Functional | 23 | 28 | 100% |
| Non-Functional | 8 | 8 | 100% |
| Interface | 5 | 5 | 100% |
| Security | 4 | 4 | 100% |
| Performance | 3 | 3 | 100% |
| **Total** | **43** | **48** | **100%** |

### 5.2 Verification Method Distribution

| Method | Count |
|--------|-------|
| Test | 39 |
| Inspection | 7 |
| Analysis | 1 |
| Test + Inspection | 1 |

---

## 6. Defect Report Template

| Defect ID | Test Case ID | Description | Severity | Status | Resolution |
|-----------|-------------|-------------|----------|--------|------------|
| _To be filled during execution_ | | | | | |

**Severity Levels:**
- **Critical**: System crash, data loss, security vulnerability
- **Major**: Feature not working as specified, workaround available
- **Minor**: Cosmetic issue, minor deviation from specification
- **Trivial**: Typo, formatting issue

---

## 7. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Test Manager | EPF Project | 2025-11-08 | - |
| Quality Assurance | - | - | - |
| Project Lead | EPF Project | 2025-11-08 | - |

---

*Document generated from EPF-REQ-001 (Requirements Specification). All test cases are traceable to requirements defined in the parent document.*
