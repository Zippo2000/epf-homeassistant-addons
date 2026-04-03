# EPF E-Ink Add-on

E-Paper Photo Frame integration for Home Assistant with **multi-source support** (Immich, ComfyUI via HA, ComfyUI Direct).

## About

This add-on provides a Flask server that:
- Fetches images from **multiple sources**: Immich photo library, ComfyUI via Home Assistant, or ComfyUI Direct
- Processes and optimizes images for 7-color E-Ink displays (800x480)
- Serves images to ESP32-based E-Paper frames
- Manages display sleep/wake cycles
- Monitors battery levels
- Supports AI-generated images with dynamic prompt templates

## Installation

1. Add this repository to your Home Assistant add-on store
2. Install the "EPF E-Ink Add-on"
3. Configure the add-on with your credentials (see below)
4. Start the add-on

## Configuration

### Image Source Selection

**image_source** (required)
- Select the source for images
- Options: `immich`, `comfyui_ha`, `comfyui_direct`
- Default: `immich`

### Immich Settings (image_source: immich)

**immich_api_key** (required)
- Your Immich API key
- Generate this in Immich under User Settings → API Keys

**immich_url** (required)
- URL to your Immich instance
- Example: `http://192.168.1.100:2283` or `https://immich.example.com`

**album_name** (required)
- Name of the Immich album to use for the frame
- Default: `eink`

### ComfyUI via Home Assistant (image_source: comfyui_ha)

**ha_url** (required)
- URL to your Home Assistant instance
- Example: `http://192.168.1.100:8123`

**ha_api_token** (required)
- Home Assistant Long-Lived Access Token
- Create in HA: Profile → Long-Lived Access Tokens → Create Token

**comfyui_prompt**
- Prompt template for AI image generation
- Supports dynamic variables:
  - `{time_of_day}` → Context-aware (morning, afternoon, evening, night)
  - `{weather}` → Random (sunny, cloudy, misty, after rain, snowy)
  - `{season}` → Context-aware (spring, summer, autumn, winter)
  - `{day_of_week}` → Current day name
  - `{month}` → Current month name
  - `{random_element}` → Random element from predefined list
- Example: `A beautiful landscape at {time_of_day}, {weather} weather, {season} scenery, photorealistic`

**comfyui_negative_prompt**
- What to exclude from the generated image
- Example: `blurry, text, watermark, low quality`

**comfyui_width** / **comfyui_height**
- Output image dimensions
- Default: 800 x 480

**comfyui_seed**
- Random seed for generation
- `-1` = random (different image each time)
- Fixed number = reproducible results
- Default: `-1`

**comfyui_max_generations**
- Maximum generations per day (protects GPU resources)
- Default: 50

### ComfyUI Direct - Expert Mode (image_source: comfyui_direct)

**comfyui_direct_url** (required)
- Direct URL to your ComfyUI server
- Example: `http://192.168.1.200:8188`

**comfyui_workflow_json** (optional)
- Custom ComfyUI workflow API JSON
- Leave empty to use default workflow
- The prompt, dimensions, and seed will be injected into the workflow

### Display Settings

**rotation_angle**
- Image rotation in degrees
- Options: 0, 90, 180, 270
- Default: 270

**color_enhance**
- Color enhancement factor
- Range: 0.0 - 3.0
- Default: 1.8

**contrast**
- Contrast adjustment
- Range: 0.0 - 2.0
- Default: 0.9

**dithering_strength**
- Dithering intensity
- Range: 0.0 - 1.0
- Default: 1.0

**display_mode**
- How images fit the display
- Options: `fit` (letterbox), `fill` (crop)
- Default: `fill`

**image_order**
- Order for Immich image selection
- Options: `random`, `newest`
- Default: `random`

**dithering_method**
- Dithering algorithm
- Options: `atkinson`, `floyd-steinberg`
- Default: `atkinson`

### Power Management

**wakeup_interval**
- Time in minutes between image updates
- Range: 30 - 1440 (30 minutes to 24 hours)
- Default: 1440 (24 hours)

**sleep_start_hour** / **sleep_start_minute**
- Start of sleep window (display off)
- Default: 23:00

**sleep_end_hour** / **sleep_end_minute**
- End of sleep window (display on)
- Default: 06:00

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/` | GET/POST | Settings web interface |
| `/health` | GET/HEAD | Health check (source-agnostic) |
| `/download` | GET | Serve image to ESP32 (hex format) |
| `/prepare-photo` | POST | Manually prepare next photo |
| `/preview-original` | GET | Preview original source image |
| `/preview-processed` | GET | Preview processed E-Ink image |
| `/preview-delivered` | GET | Preview last delivered image |
| `/preview-status` | GET | Get preview status info |
| `/api/battery-status` | GET | Get battery voltage/percentage |
| `/api/generation-status` | GET | Get ComfyUI generation tracking info |
| `/sleep` | GET | Get ESP32 sleep duration |
| `/cleanup-previews` | POST | Clean up old preview files |

## Usage

1. Configure your ESP32 to point to: `http://homeassistant.local:5000`
2. The ESP32 will fetch a new image at each wake cycle
3. View logs in the Home Assistant add-on interface
4. Use the web settings interface to switch between image sources

## Hardware Requirements

- ESP32 (FireBeetle ESP32-E recommended)
- 7.3" E-Ink display (Waveshare 7.3inch e-Paper, 7-color)
- LiPo battery (optional, for battery operation)

## Architecture

The add-on uses a **Provider Architecture** pattern:
- **ImageProvider** (abstract base class) defines the interface for all image sources
- **ImmichProvider** fetches from Immich photo server
- **ComfyUIHAProvider** generates via Home Assistant `ai_task.generate_image` service
- **ComfyUIDirectProvider** connects directly to ComfyUI API (expert mode)
- **Provider Factory** creates the appropriate provider based on `image_source` config

This design allows adding new image sources without modifying the core application logic.

## Support

For issues, questions, or contributions:
- [GitHub Issues](https://github.com/Zippo2000/epf-homeassistant-addons/issues)
- [Original EPF Project](https://github.com/jwchen119/EPF)

## Credits

Based on the EPF project by jwchen119.
