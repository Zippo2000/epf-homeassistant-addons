# Configuration

## Immich Integration

This add-on integrates with [Immich](https://immich.app/), a self-hosted photo and video backup solution.

### Getting your Immich API Key

1. Open your Immich instance in a web browser
2. Log in with your credentials
3. Go to **User Settings** (click your profile picture)
4. Navigate to **API Keys**
5. Click **New API Key**
6. Give it a name (e.g., "EPF E-Ink Frame")
7. Copy the generated API key
8. Paste it into the add-on configuration

### Creating an Album for EPF

1. In Immich, go to **Albums**
2. Create a new album (e.g., "EPF" or "E-Ink Frame")
3. Add photos you want to display on the frame
4. Use this album name in the add-on configuration

## Display Configuration

### Rotation Angle

Set the rotation angle based on your physical E-Ink display orientation:
- **0°** - Portrait mode (default)
- **90°** - Landscape mode (rotated clockwise)
- **180°** - Portrait mode (upside down)
- **270°** - Landscape mode (rotated counter-clockwise)

### Image Enhancement

**Color Enhance** (0.0 - 3.0)
- Values < 1.0: Reduce color saturation
- Value = 1.0: No change (default)
- Values > 1.0: Increase color saturation
- Recommended: 1.2 - 1.5 for E-Ink displays

**Contrast** (0.0 - 3.0)
- Values < 1.0: Reduce contrast
- Value = 1.0: No change (default)
- Values > 1.0: Increase contrast
- Recommended: 1.1 - 1.3 for better E-Ink visibility

### Sleep Duration

Controls how often the display updates:
- **300** (5 minutes) - Frequent updates, higher battery consumption
- **3600** (1 hour) - Default, balanced
- **21600** (6 hours) - Infrequent updates, maximum battery life
- **86400** (24 hours) - Daily updates

## ESP32 Configuration

Point your ESP32 to the add-on endpoint:

```cpp
const char* serverPath = "http://homeassistant.local:5000";
```

Or use your Home Assistant IP:

```cpp
const char* serverPath = "http://192.168.1.100:5000";
```

## Troubleshooting

### No images displayed

1. Check if the Immich API key is correct
2. Verify the album name exists in Immich
3. Ensure the album contains at least one photo
4. Check add-on logs for errors

### ESP32 cannot connect

1. Verify network connectivity
2. Check if port 5000 is accessible
3. Try using IP address instead of hostname
4. Check firewall settings

### Poor image quality

1. Increase **color_enhance** to 1.3-1.5
2. Increase **contrast** to 1.2-1.3
3. Use high-resolution source images
4. Ensure proper **rotation_angle** setting

## Advanced Configuration

### Custom Port

If port 5000 is already in use, you can modify the port mapping in Home Assistant:

1. Stop the add-on
2. Go to **Configuration** tab
3. Edit **Network** section
4. Change port mapping (e.g., `5001:5000`)
5. Update ESP32 code accordingly
6. Restart the add-on

## Support

For additional help:
- [GitHub Issues](https://github.com/Zippo2000/epf-homeassistant-addons/issues)
- [Home Assistant Community](https://community.home-assistant.io/)
- [Original EPF Documentation](https://github.com/jwchen119/EPF)
