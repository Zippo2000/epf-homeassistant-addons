# EPF E-Ink Add-on

E-Paper Photo Frame integration for Home Assistant with Immich support.

## About

This add-on provides a Flask server that:
- Fetches images from your Immich photo library
- Processes and optimizes images for E-Ink displays
- Serves images to ESP32-based E-Paper frames
- Manages display sleep/wake cycles
- Monitors battery levels

## Installation

1. Add this repository to your Home Assistant add-on store
2. Install the "EPF E-Ink Add-on"
3. Configure the add-on with your Immich credentials
4. Start the add-on

## Configuration

### Immich Settings

**immich_api_key** (required)
- Your Immich API key
- Generate this in Immich under User Settings → API Keys

**immich_url** (required)
- URL to your Immich instance
- Example: `http://192.168.1.100:2283` or `https://immich.example.com`

**album_name** (required)
- Name of the Immich album to use for the frame
- Default: `EPF`

### Display Settings

**rotation_angle**
- Image rotation in degrees
- Options: 0, 90, 180, 270
- Default: 0

**color_enhance**
- Color enhancement factor
- Range: 0.0 - 3.0
- Default: 1.0 (no enhancement)

**contrast**
- Contrast adjustment
- Range: 0.0 - 3.0
- Default: 1.0 (no adjustment)

**sleep_duration**
- Time in seconds between image updates
- Range: 60 - 86400 (1 minute to 24 hours)
- Default: 3600 (1 hour)

## Usage

1. Configure your ESP32 to point to: `http://homeassistant.local:5000`
2. The ESP32 will fetch a new image at each wake cycle
3. View logs in the Home Assistant add-on interface

## Hardware Requirements

- ESP32 (FireBeetle ESP32-E recommended)
- 7.3" E-Ink display (Waveshare 7.3inch e-Paper)
- LiPo battery (optional, for battery operation)

## Support

For issues, questions, or contributions:
- [GitHub Issues](https://github.com/Zippo2000/epf-homeassistant-addons/issues)
- [Original EPF Project](https://github.com/jwchen119/EPF)

## Credits

Based on the EPF project by jwchen119.
