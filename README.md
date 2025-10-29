# EPF Home Assistant Add-ons Repository

This repository contains Home Assistant add-ons for the E-Paper Photo Frame (EPF) project.

## Available Add-ons

### 🖼️ EPF E-Ink Add-on

E-Paper Photo Frame with Immich integration for displaying photos on E-Ink displays.

**Features:**
- Fetches images from Immich photo management system
- Optimized image processing for E-Ink displays
- 7-color dithering support
- Battery monitoring for ESP32
- Sleep management for power efficiency

## Installation

1. Navigate to **Settings** → **Add-ons** → **Add-on Store** in Home Assistant
2. Click the **⋮** menu in the top right → **Repositories**
3. Add this repository URL:
   ```
   https://github.com/Zippo2000/epf-homeassistant-addons
   ```
4. Find "EPF E-Ink Add-on" in the add-on store and click **Install**

## Configuration

Configure the add-on through the Home Assistant UI:
- **Immich API Key**: Your Immich API key
- **Immich URL**: URL to your Immich instance
- **Album Name**: Name of the Immich album to use
- **Rotation Angle**: Image rotation (0, 90, 180, 270)
- **Color Enhance**: Color enhancement factor (0.0-3.0)
- **Contrast**: Contrast adjustment (0.0-3.0)

## Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/Zippo2000/epf-homeassistant-addons/issues)
- Original EPF Project: [jwchen119/EPF](https://github.com/jwchen119/EPF)

## License

MIT License - see individual add-on directories for details.

## Credits

Based on the EPF project by [jwchen119](https://github.com/jwchen119/EPF).
