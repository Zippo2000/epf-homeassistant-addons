# Changelog

All notable changes to this project will be documented in this file.

## [1.0.4] - 2026-04-03

### Added
- **FR-024 Preview Cleanup**: New `cleanup_old_previews()` function with dual eviction strategy:
  - Age-based: Removes preview files older than 7 days
  - Count-based: Removes oldest files when more than 50 match a pattern
  - Protects current preview files (`latest_original.jpg`, `latest_processed.jpg`, `latest.bmp`)
- **New endpoint** `POST /cleanup-previews`: Triggers manual cleanup, returns count of removed files
- **FR-023 (updated) Graceful NTP Shutdown**: `_ntp_stop_event` (threading.Event) and `stop_ntp_sync()` function for clean thread termination. NTP loop now uses `event.wait()` instead of blocking `time.sleep()` for immediate response to stop signals

### Changed
- **Full Type Hints**: Added `from __future__ import annotations` and comprehensive Python type annotations throughout `app.py`:
  - All function signatures (parameters + return types)
  - All global variables (`BUILD_TIMESTAMP: str`, `last_battery_voltage: float`, etc.)
  - All class attributes (`ConfigFileHandler.config_path: str`, etc.)
  - Imports: `Optional, Dict, Any, Set, Tuple, Callable, List` from `typing`
- **UI/Schema Alignment**: `color_enhance` slider `max` attribute changed from `2.0` to `3.0` in `settings.html` to match config.yaml schema (resolves OI-003, OI-004)
- **BUILD_VERSION** updated to `1.0.4`
- **Import cleanup**: `from shutil import copy2` moved to top-level imports (was previously imported inside route handlers)
- **Import added**: `import glob as glob_module` for preview cleanup file matching

### Fixed
- Duplicate `from shutil import copy2` import removed
- `headers` dict type safety: `api_key` now defaults to empty string instead of `None`

### Documentation Updates
- `docs/architecture_document.md` → v1.1.0:
  - AC-005 (NTP shutdown) marked RESOLVED
  - AC-006 (preview cleanup) marked RESOLVED
  - AC-007 (type hints) added and marked RESOLVED
  - New Section 15: Design Decisions D-009 through D-012
- `docs/requirements_specification_aspice.md` → v1.1.0:
  - Added FR-024 (Preview Cleanup)
  - Added NFR-009 (Type Annotations)
  - OI-003, OI-004, OI-005 marked RESOLVED
  - Updated traceability matrix
- `docs/test_specification_aspice.md` → v1.1.0:
  - Added TC-FR-024 (Preview Cleanup test cases)
  - Added TC-NFR-009 (Type Annotations inspection)
  - Updated test traceability matrix
- `docs/test_report_aspice.md` → v1.1.0:
  - Updated to 93 tests, 100% pass rate, 14.75s execution time

### Tests
- **15 new test cases** added (93 total, up from 78):
  - `TestFR023NTPShutdown`: 3 tests (stop event, stop function, event set/clear)
  - `TestFR024PreviewCleanup`: 8 tests (function exists, returns int, removes old files, keeps recent files, protects current previews, count limit, endpoint exists, endpoint returns success)
  - `TestNFR009TypeAnnotations`: 4 tests (future annotations import, typing module imported, function annotations, global variable annotations)
- All 93 tests pass in Docker (debian:bookworm, Python 3.11.2, pytest 7.4.3)

### Modified Files
- `app.py`: Type hints, cleanup function, NTP graceful shutdown, import cleanup, version bump
- `templates/settings.html`: color_enhance slider max 2.0 → 3.0
- `tests/test_functional.py`: +11 new test classes/methods
- `tests/test_nonfunctional.py`: +4 new test methods for NFR-009
- `docs/architecture_document.md`: v1.1.0 updates
- `docs/requirements_specification_aspice.md`: v1.1.0 updates
- `docs/test_specification_aspice.md`: v1.1.0 updates
- `docs/test_report_aspice.md`: v1.1.0 with new test results

---

## [1.0.3] - 2026-04-03

### Changed
- **FR-018 Battery Status**: Removed 90000-second expiry for battery readings. The last known battery value is now retained indefinitely and displayed with a timestamp showing when the reading was taken (date + time). This ensures users can always see the last reported battery status, even if the ESP32 hasn't reported in a while.

### Modified Files
- `app.py`: Removed timeout logic in `/api/battery-status` and settings route; added `formatted_timestamp` field to API response
- `templates/settings.html`: Added timestamp display below battery percentage/voltage in header; updated JavaScript to refresh timestamp on polling

---

## [1.0.1] - 2025-11-07

### Modified Files
1. `app_modified.py` (original: `app.py`)
2. `settings_modified.html` (original: `settings.html`)

### Changes in app.py

#### New Routes
1. **`/prepare-photo` (POST)**
   - Manually fetch and prepare a photo from Immich
   - Saves the photo as:
     - `/photos/latest.bmp` (for ESP32)
     - `/photos/latest_preview.jpg` (for web preview)
     - `/photos/latest.status` (status: `'new'` or `'delivered'`)
   - Marks the photo as `'new'` (not yet delivered)

2. **`/preview-photo` (GET)**
   - Serves the preview photo (JPEG) for the web interface
   - Independent of delivery status

3. **`/preview-status` (GET)**
   - Returns the current photo status as JSON
   - Contains: `exists`, `status`, `timestamp`, `formatted_time`

#### Modified Route
- **`/download` (GET)** — Completely revised
  - Checks if a prepared photo with status `'new'` exists
  - If YES: Serves the prepared photo, changes status to `'delivered'`
  - If NO: Fetches a new photo from Immich, processes it, saves it with status `'delivered'` and serves it

#### How It Works

**Scenario 1: Manual button pressed**
- `/prepare-photo` creates a photo with status `'new'`
- ESP32 wakes up → `/download` finds status `'new'`
- Photo is delivered, status → `'delivered'`
- Preview remains visible in the web interface

**Scenario 2: No manual photo**
- ESP32 wakes up → `/download` finds no `'new'` photo
- Automatic fetch and processing
- Photo is delivered AND saved as preview
- Status → `'delivered'`

### Changes in settings.html

#### New Components
1. **Photo Preview Card**
   - Shows preview of the last prepared photo
   - Status badge: "Ready to deliver" or "Already delivered"
   - Timestamp of photo preparation
   - Button: "Prepare New Photo"
   - Placeholder when no photo is available

2. **CSS Extensions**
   - `.prepare-photo-btn` (gradient button with hover effects)
   - `.preview-container`
   - `#photoPreview` styling

3. **JavaScript Functions**
   - `updatePhotoStatus()` — Refreshes photo status from the server
   - `prepareNewPhoto()` — Triggers manual photo fetch
   - Auto-update every 30 seconds
   - Runs on page load

### File Structure

New files in `/photos/`:
- `latest.bmp` — Prepared photo for ESP32 (BMP format)
- `latest_preview.jpg` — Preview for web interface (JPEG format)
- `latest.status` — Text file with `'new'` or `'delivered'`

---

## [1.0.0] - 2025-10-29

### Added
- Initial release of EPF E-Ink Add-on
- Immich integration for photo fetching
- Image processing for E-Ink displays
- 7-color dithering support
- Battery monitoring endpoint
- Configurable sleep duration
- Image rotation support
- Color enhancement options
- Contrast adjustment
- Multi-architecture support (armhf, armv7, aarch64, amd64, i386)

### Features
- Flask-based web server
- REST API for ESP32 communication
- Automatic image optimization for E-Ink
- Configuration via Home Assistant UI
- Centralized logging in HA Supervisor

### Known Issues
- Cython optimization pending (Phase 3)
- Performance testing on ARM devices pending (Phase 6)

## [Unreleased]

### Planned
- Advanced dithering algorithms
- Multiple album support
- Scheduling features
- Image filters
- Statistics dashboard
- Battery level visualization
