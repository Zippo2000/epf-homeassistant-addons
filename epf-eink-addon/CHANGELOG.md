# Changelog

All notable changes to this project will be documented in this file.

## [1.0.1] - 2025-11-07

MODIFIZIERTE DATEIEN:
1. app_modified.py      (Original: app.py)
2. settings_modified.html (Original: settings.html)

=============================================================================
ÄNDERUNGEN IN app.py:
=============================================================================

NEUE ROUTEN:
------------
1. /prepare-photo (POST)
   - Manuelles Abrufen und Vorbereiten eines Fotos aus Immich
   - Speichert Foto als:
     * /photos/latest.bmp (für ESP32)
     * /photos/latest_preview.jpg (für Web-Vorschau)
     * /photos/latest.status (Status: 'new' oder 'delivered')
   - Markiert Foto als 'new' (noch nicht ausgeliefert)

2. /preview-photo (GET)
   - Liefert Vorschau-Foto (JPEG) für Webinterface
   - Unabhängig vom Auslieferungsstatus

3. /preview-status (GET)
   - Gibt Status des aktuellen Fotos zurück (JSON)
   - Enthält: exists, status, timestamp, formatted_time

MODIFIZIERTE ROUTE:
------------------
/download (GET) - KOMPLETT ÜBERARBEITET
   - Prüft ob vorbereitetes Foto mit Status 'new' existiert
   - Falls JA: Liefert vorbereitetes Foto aus, ändert Status auf 'delivered'
   - Falls NEIN: Holt neues Foto von Immich, verarbeitet es, speichert es
     mit Status 'delivered' und liefert es aus

FUNKTIONSWEISE:
---------------
Szenario 1: Manueller Button gedrückt
  → /prepare-photo erstellt Foto mit Status 'new'
  → ESP32 wacht auf → /download findet Status 'new'
  → Foto wird ausgeliefert, Status → 'delivered'
  → Vorschau bleibt im Web sichtbar

Szenario 2: Kein manuelles Foto
  → ESP32 wacht auf → /download findet kein 'new' Foto
  → Automatisches Holen und Verarbeiten
  → Foto wird ausgeliefert UND als Vorschau gespeichert
  → Status → 'delivered'

=============================================================================
ÄNDERUNGEN IN settings.html:
=============================================================================

NEUE KOMPONENTEN:
-----------------
1. Photo Preview Card
   - Zeigt Vorschau des letzten vorbereiteten Fotos
   - Status-Badge: "✨ Ready to deliver" oder "✓ Already delivered"
   - Timestamp der Foto-Vorbereitung
   - Button "🔄 Prepare New Photo"
   - Placeholder wenn kein Foto vorhanden

2. CSS-Erweiterungen
   - .prepare-photo-btn (Gradient-Button mit Hover-Effekten)
   - .preview-container
   - #photoPreview Styling

3. JavaScript-Funktionen
   - updatePhotoStatus() - Aktualisiert Foto-Status vom Server
   - prepareNewPhoto() - Löst manuelles Foto-Abrufen aus
   - Auto-Update alle 30 Sekunden
   - Beim Laden der Seite

=============================================================================
DATEISTRUKTUR:
=============================================================================

Neue Dateien in /photos/:
- latest.bmp           (Vorbereitetes Foto für ESP32, BMP-Format)
- latest_preview.jpg   (Vorschau für Webinterface, JPEG-Format)
- latest.status        (Textdatei mit 'new' oder 'delivered')

=============================================================================

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

## [1.0.3] - 2026-04-03

### Changed
- **FR-018 Battery Status**: Removed 90000-second expiry for battery readings. The last known battery value is now retained indefinitely and displayed with a timestamp showing when the reading was taken (date + time). This ensures users can always see the last reported battery status, even if the ESP32 hasn't reported in a while.

### Modified Files
- `app.py`: Removed timeout logic in `/api/battery-status` and settings route; added `formatted_timestamp` field to API response
- `templates/settings.html`: Added timestamp display below battery percentage/voltage in header; updated JavaScript to refresh timestamp on polling
