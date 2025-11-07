#-*- coding:utf8 -*-

# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Based on Zippo2000/EPF with HA Integration
# Full-featured Flask Server with Cython Optimization
# ==============================================================================

BUILD_TIMESTAMP = "2025-11-07 16:29:29 CET"
BUILD_VERSION = "1.0.2"

from flask import Flask, jsonify, send_file, render_template, request, redirect, url_for, Blueprint
import yaml
import requests
import os
import io
import random
import rawpy
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
from pillow_heif import register_heif_opener
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import ntplib
import time
import logging
import sys
from werkzeug.middleware.proxy_fix import ProxyFix

# ==============================================================================
# Logging Setup
# ==============================================================================
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# ==============================================================================
# Cython Optimization
# ==============================================================================
try:
    from cpy import convert_image_atkinson, load_scaled
    CYTHON_AVAILABLE = True
    logger.info("✅ Cython optimization available")
except ImportError:
    CYTHON_AVAILABLE = False
    logger.warning("⚠️ Cython not available - using pure Python (slower)")

# ==============================================================================
# Default Configuration
# ==============================================================================
DEFAULT_CONFIG = {
    'immich': {
        'url': os.getenv('IMMICH_URL', 'http://192.168.1.10'),
        'album': os.getenv('ALBUM_NAME', 'default_album'),
        'rotation': int(os.getenv('ROTATION_ANGLE', '270')),
        'enhanced': float(os.getenv('COLOR_ENHANCE', '1.3')),
        'contrast': float(os.getenv('CONTRAST', '0.9')),
        'strength': float(os.getenv('DITHERING_STRENGTH', '0.8')),
        'display_mode': os.getenv('DISPLAY_MODE', 'fill'),
        'image_order': os.getenv('IMAGE_ORDER', 'random'),
        'dithering_method': os.getenv('DITHERING_METHOD', 'atkinson'),
        'sleep_start_hour': int(os.getenv('SLEEP_START_HOUR', '23')),
        'sleep_start_minute': int(os.getenv('SLEEP_START_MINUTE', '0')),
        'sleep_end_hour': int(os.getenv('SLEEP_END_HOUR', '6')),
        'sleep_end_minute': int(os.getenv('SLEEP_END_MINUTE', '0')),
        'wakeup_interval': int(os.getenv('WAKEUP_INTERVAL', '60')),
    }
}

current_config = DEFAULT_CONFIG.copy()

# Initialize configuration
url = current_config['immich']['url']
albumname = current_config['immich']['album']
rotationAngle = current_config['immich']['rotation']
img_enhanced = current_config['immich']['enhanced']
img_contrast = current_config['immich']['contrast']
strength = current_config['immich']['strength']
display_mode = current_config['immich']['display_mode']
image_order = current_config['immich']['image_order']
dithering_method = current_config['immich'].get('dithering_method', 'atkinson')
sleep_start_hour = current_config['immich']['sleep_start_hour']
sleep_start_minute = current_config['immich']['sleep_start_minute']
sleep_end_hour = current_config['immich']['sleep_end_hour']
sleep_end_minute = current_config['immich']['sleep_end_minute']

# API Configuration
apikey = os.getenv('IMMICH_API_KEY')
photodir = os.getenv('IMMICH_PHOTO_DEST', '/photos')
config_path = os.getenv('CONFIG_PATH', '/config/config.yaml')
tracking_file = os.path.join(photodir, 'tracking.txt')

# Ensure directory exists
os.makedirs(photodir, exist_ok=True)

# Ensure tracking.txt exists
if not os.path.exists(tracking_file):
    open(tracking_file, 'w').close()

headers = {
    'Accept': 'application/json',
    'x-api-key': apikey
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {'.jpeg', '.raw', '.jpg', '.bmp', '.dng', '.heic', '.arw', '.cr2', '.dng', '.nef', '.raw'}

# Set up directory for downloaded images
os.makedirs(photodir, exist_ok=True)
register_heif_opener()

# ==============================================================================
# E-Ink Palette (WaveShare 7.5inch Spectra-E6)
# ==============================================================================
palette = [
    (0, 0, 0),        # Black
    (255, 255, 255),  # White
    (255, 243, 56),   # Yellow
    (191, 0, 0),      # Deep Red
    (100, 64, 255),   # Blue
    (67, 138, 28)     # Green
]

# ==============================================================================
# Battery Tracking (Lithium Battery)
# ==============================================================================
last_battery_voltage = 0
last_battery_update = 0

BATTERY_LEVELS = {
    4200: 100, 4150: 95, 4110: 90, 4080: 85, 4020: 80,
    3980: 75, 3950: 70, 3910: 65, 3870: 60, 3850: 55,
    3840: 50, 3820: 45, 3800: 40, 3790: 35, 3770: 30,
    3750: 25, 3730: 20, 3710: 15, 3690: 10, 3610: 5,
    3400: 0
}

def calculate_battery_percentage(voltage):
    """Calculate battery percentage from voltage (Lithium Battery)"""
    if voltage >= 4200:
        return 100
    if voltage <= 3400:
        return 0
    
    voltages = list(BATTERY_LEVELS.keys())
    for i in range(len(voltages) - 1):
        if voltages[i] >= voltage >= voltages[i + 1]:
            v1, v2 = voltages[i], voltages[i + 1]
            p1, p2 = BATTERY_LEVELS[v1], BATTERY_LEVELS[v2]
            percentage = p2 + (voltage - v2) * (p1 - p2) / (v1 - v2)
            return round(percentage, 1)
    return 0

# ==============================================================================
# Tracking Functions
# ==============================================================================
def load_downloaded_images():
    """Load downloaded image IDs from tracking.txt"""
    global albumname
    try:
        if not os.path.exists(tracking_file):
            open(tracking_file, 'w').close()
            os.chmod(tracking_file, 0o666)
        
        with open(tracking_file, 'r+') as f:
            lines = f.readlines()
            if not lines or lines[0].strip() != albumname:
                f.seek(0)
                f.truncate()
                f.write(f"{albumname}\n")
                return set()
            return set(line.strip() for line in lines[1:] if line.strip())
    except Exception as e:
        logger.error(f"Error reading tracking file: {e}")
        return set()

def save_downloaded_image(asset_id):
    """Save downloaded image ID to tracking.txt"""
    global albumname
    try:
        if not os.path.exists(tracking_file):
            open(tracking_file, 'w').close()
            os.chmod(tracking_file, 0o666)
        
        with open(tracking_file, 'r+') as f:
            lines = f.readlines()
            if not lines or lines[0].strip() != albumname:
                f.seek(0)
                f.truncate()
                f.write(f"{albumname}\n")
            f.seek(0, 2)
            f.write(f"{asset_id}\n")
    except Exception as e:
        logger.error(f"Error writing to tracking file: {e}")

def reset_tracking_file():
    """Reset tracking.txt file"""
    try:
        open(tracking_file, 'w').close()
    except Exception as e:
        logger.error(f"Error resetting tracking file: {e}")

# ==============================================================================
# Image Processing Functions
# ==============================================================================
def atkinson_dither_pure_python(image, palette):
    """Pure Python Atkinson Dithering (Fallback if Cython unavailable)"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    width, height = image.size
    pixels = image.load()
    
    for y in range(height):
        for x in range(width):
            old_pixel = pixels[x, y]
            new_pixel = min(palette, key=lambda color:
                sum((old_pixel[i] - color[i])**2 for i in range(3)))
            pixels[x, y] = new_pixel
            error = tuple(old_pixel[i] - new_pixel[i] for i in range(3))
            
            def distribute_error(dx, dy, factor=1/8):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    current = pixels[nx, ny]
                    pixels[nx, ny] = tuple(
                        int(max(0, min(255, current[i] + error[i] * factor)))
                        for i in range(3)
                    )
            
            distribute_error(1, 0)
            distribute_error(2, 0)
            distribute_error(-1, 1)
            distribute_error(0, 1)
            distribute_error(1, 1)
            distribute_error(0, 2)
    
    return image

def floyd_steinberg_dither(image, palette):
    """Pure Python Floyd-Steinberg Dithering"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    width, height = image.size
    pixels = image.load()
    
    for y in range(height):
        for x in range(width):
            old_pixel = pixels[x, y]
            new_pixel = min(palette, key=lambda c: sum((old_pixel[i]-c[i])**2 for i in range(3)))
            pixels[x, y] = new_pixel
            error = tuple(old_pixel[i] - new_pixel[i] for i in range(3))
            
            def distribute(dx, dy, factor):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    current = pixels[nx, ny]
                    pixels[nx, ny] = tuple(int(max(0, min(255, current[i] + error[i] * factor))) for i in range(3))
            
            distribute(1, 0, 7/16)    # Rechts
            distribute(-1, 1, 3/16)   # Links-Unten
            distribute(0, 1, 5/16)    # Unten
            distribute(1, 1, 1/16)    # Rechts-Unten
    
    return image

def scale_img_in_memory(image, target_width=800, target_height=480, bg_color=(255, 255, 255)):
    """
    Process image in memory
    Uses Cython if available, falls back to pure Python
    """
    global rotation
    rotation = rotationAngle
    
    try:
        exif = image._getexif()
        date_time = exif.get(36867) if exif else None
        if not date_time and exif:
            date_time = exif.get(306)
    except:
        date_time = None
    
    # Read correct photo orientation from EXIF
    image = ImageOps.exif_transpose(image)
    
    # Use Cython if available, otherwise pure Python
    if CYTHON_AVAILABLE:
        img = load_scaled(image, rotation, display_mode)
    else:
        # Fallback: manual scaling
        if rotation in [90, 270]:
            temp_width, temp_height = target_height, target_width
        else:
            temp_width, temp_height = target_width, target_height
        
        aspect = image.width / image.height
        if aspect > temp_width / temp_height:
            new_width = temp_width
            new_height = int(temp_width / aspect)
        else:
            new_height = temp_height
            new_width = int(temp_height * aspect)
        
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        canvas = Image.new('RGB', (temp_width, temp_height), bg_color)
        x = (temp_width - new_width) // 2
        y = (temp_height - new_height) // 2
        canvas.paste(image, (x, y))
        
        if rotation != 0:
            canvas = canvas.rotate(360 - rotation, expand=False)
        
        img = canvas
    
    # Enhance
    enhanced_img = ImageEnhance.Color(img).enhance(img_enhanced)
    enhanced_img = ImageEnhance.Contrast(enhanced_img).enhance(img_contrast)
    
    # Prepare palette
    palette_list = []
    for color in palette:
        palette_list.extend(color)
    e = len(palette_list)
    palette_list += (768 - e) * [0]
    
    pal_image = Image.new("P", (1, 1))
    pal_image.putpalette(palette_list)
    
    # Dither with selected method
    if CYTHON_AVAILABLE:
        if dithering_method == 'floyd-steinberg':
            output_img = floyd_steinberg_dither(enhanced_img, palette)
        else:  # atkinson (default)
            output_img = convert_image_atkinson(enhanced_img, dithering_strength=strength)
            output_img = Image.fromarray(output_img, mode="RGB")
    else:
        if dithering_method == 'floyd-steinberg':
            output_img = floyd_steinberg_dither(enhanced_img, palette)
        else:
            output_img = atkinson_dither_pure_python(enhanced_img, palette)

    # Add date if available
    if date_time:
        draw = ImageDraw.Draw(output_img)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
        except:
            font = ImageFont.load_default()
        
        try:
            try:
                dt = datetime.strptime(date_time, "%Y:%m:%d %H:%M:%S")
                formatted_time = dt.strftime("%Y/%m/%d")
            except ValueError:
                dt = datetime.strptime(date_time, "%Y.%m.%d")
                formatted_time = dt.strftime("%Y/%m/%d")
        except:
            formatted_time = date_time
    
    # Speichere BMP (mode P ist OK für BMP)
    img_io = io.BytesIO()
    output_img.save(img_io, 'BMP')

    # Für JPEG Preview: Konvertiere zu RGB!
    preview_jpg_path = os.path.join(photodir, 'latest_preview.jpg')
    output_img.convert('RGB').save(preview_jpg_path, 'JPEG', quality=85)
    #          ^^^^^^^^^^^^^^ KRITISCH: Zurück zu RGB!

    img_io.seek(0)
    return img_io

def convert_raw_or_dng_to_jpg(input_file_path, output_dir):
    """Convert RAW/DNG to JPG"""
    with rawpy.imread(input_file_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
    base_name = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path = os.path.join(output_dir, f"{base_name}.jpg")
    Image.fromarray(rgb).save(jpg_path, 'JPEG')
    return jpg_path

def convert_heic_to_jpg(input_file_path, output_dir):
    """Convert HEIC to JPG"""
    img = Image.open(input_file_path).convert("RGB")
    base_name = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path = os.path.join(output_dir, f"{base_name}.jpg")
    img.save(jpg_path, "JPEG", quality=95)
    return jpg_path

# ==============================================================================
# Build Information
# ==============================================================================
BUILD_TIMESTAMP = "2025-11-07 13:44:09 CET"
BUILD_VERSION = "1.0.1"

# ==============================================================================
# Configuration Management
# ==============================================================================
class ConfigFileHandler(FileSystemEventHandler):
    """Watch config.yaml for changes"""
    
    def __init__(self, config_path, config_update_callback):
        self.config_path = config_path
        self.config_update_callback = config_update_callback
        self.ensure_config_exists()
        self.config = self.load_config()
    
    def ensure_config_exists(self):
        config_dir = os.path.dirname(self.config_path)
        if not os.path.exists(config_dir):
            try:
                os.makedirs(config_dir)
                logger.info(f"Created config directory: {config_dir}")
            except Exception as e:
                logger.error(f"Error creating config directory: {e}")
        
        if not os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'w') as f:
                    yaml.dump(DEFAULT_CONFIG, f)
                logger.info(f"Created default config: {self.config_path}")
            except Exception as e:
                logger.error(f"Error creating config: {e}")
    
    def on_modified(self, event):
        if event.src_path == self.config_path:
            logger.info("Config modified, reloading...")
            new_config = self.load_config()
            self.config_update_callback(new_config)
    
    def load_config(self):
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error reading config: {e}")
            return DEFAULT_CONFIG

def update_app_config(new_config):
    """Update configuration"""
    global current_config, url, albumname, rotationAngle, img_enhanced, img_contrast
    global strength, display_mode, image_order, dithering_method, sleep_start_hour, sleep_end_hour, sleep_start_minute, sleep_end_minute
    
    current_config = new_config
    url = new_config['immich']['url']
    albumname = new_config['immich']['album']
    rotationAngle = new_config['immich']['rotation']
    img_enhanced = new_config['immich']['enhanced']
    img_contrast = new_config['immich']['contrast']
    strength = new_config['immich']['strength']
    display_mode = new_config['immich']['display_mode']
    image_order = new_config['immich']['image_order']
    dithering_method = new_config['immich'].get('dithering_method', 'atkinson')
    sleep_start_hour = new_config['immich']['sleep_start_hour']
    sleep_end_hour = new_config['immich']['sleep_end_hour']
    sleep_start_minute = new_config['immich']['sleep_start_minute']
    sleep_end_minute = new_config['immich']['sleep_end_minute']
    
    logger.info(f"Config updated: URL={url}, Album={albumname}, Rotation={rotationAngle}°, Dithering={dithering_method}")

def start_config_watcher(config_path):
    """Start watching config.yaml"""
    config_handler = ConfigFileHandler(config_path, update_app_config)
    observer = Observer()
    observer.schedule(config_handler, path=os.path.dirname(config_path), recursive=False)
    observer.start()
    return observer

# ==============================================================================
# Flask App Setup
# ==============================================================================
app = Flask(__name__)

# ProxyFix für Home Assistant Ingress
# Important: This handles X-Forwarded-* headers properly
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

logger.info("=" * 80)
logger.info("EPF Flask Server (Zippo2000 + HA) Initializing")
logger.info(f"Build: Version {BUILD_VERSION} - {BUILD_TIMESTAMP}")
logger.info("=" * 80)
logger.info(f"Cython Available: {CYTHON_AVAILABLE}")
logger.info(f"Config Path: {config_path}")
logger.info("=" * 80)

# ==============================================================================
# BLUEPRINT SETUP
# ==============================================================================

bp = Blueprint('main', __name__)

@bp.route('/', methods=['GET', 'POST'])
def settings():
    """Settings page - ROOT ROUTE"""
    global current_config, last_battery_voltage, last_battery_update
    
    current_time = time.time()
    if current_time - last_battery_update < 3600:
        battery_voltage = last_battery_voltage
    else:
        battery_voltage = 0
    
    battery_percentage = calculate_battery_percentage(battery_voltage) if battery_voltage > 0 else 0
    
    if battery_voltage > 0:
        logger.info(f"Battery: {battery_voltage:.0f}mV ({battery_percentage:.1f}%)")
    
    if request.method == 'POST':
        new_config = {
            'immich': {
                'url': request.form.get('url', current_config['immich']['url']),
                'album': request.form.get('album', current_config['immich']['album']),
                'rotation': int(request.form.get('rotation', current_config['immich']['rotation'])),
                'enhanced': float(request.form.get('enhanced', current_config['immich']['enhanced'])),
                'contrast': float(request.form.get('contrast', current_config['immich']['contrast'])),
                'strength': float(request.form.get('strength', current_config['immich']['strength'])),
                'display_mode': request.form.get('display_mode', current_config['immich']['display_mode']),
                'image_order': request.form.get('image_order', current_config['immich']['image_order']),
                'dithering_method': request.form.get('dithering_method', current_config['immich'].get('dithering_method', 'atkinson')),
                'sleep_start_hour': int(request.form.get('sleep_start_hour', current_config['immich']['sleep_start_hour'])),
                'sleep_start_minute': int(request.form.get('sleep_start_minute', current_config['immich']['sleep_start_minute'])),
                'sleep_end_hour': int(request.form.get('sleep_end_hour', current_config['immich']['sleep_end_hour'])),
                'sleep_end_minute': int(request.form.get('sleep_end_minute', current_config['immich']['sleep_end_minute'])),
                'wakeup_interval': int(request.form.get('wakeup_interval', current_config['immich']['wakeup_interval'])),
            }
        }
        
        if new_config['immich']['rotation'] not in [0, 90, 180, 270]:
            return "Invalid rotation", 400
        
        try:
            with open(config_path, 'w') as f:
                yaml.safe_dump(new_config, f)
            update_app_config(new_config)
            return redirect(url_for('main.settings'))
        except Exception as e:
            return f"Error saving config: {str(e)}", 500
    
    return render_template('settings.html',
                           config=current_config if current_config else DEFAULT_CONFIG,
                           battery_voltage=battery_voltage,
                           battery_percentage=battery_percentage,
                           addon_version=BUILD_VERSION,
                           build_timestamp=BUILD_TIMESTAMP)

@bp.route('/health', methods=['GET', 'HEAD'])
def health():
    """Health check endpoint"""
    try:
        response = requests.get(f"{url}/api/server/ping", timeout=5)
        immich_ok = response.status_code == 200
    except:
        immich_ok = False
    
    status_code = 200 if immich_ok else 503
    return jsonify({
        "status": "healthy" if immich_ok else "degraded",
        "timestamp": datetime.now().isoformat(),
        "immich": "connected" if immich_ok else "unreachable"
    }), status_code

@bp.route('/download', methods=['GET'])
def process_and_download():
    """Download and process image from Immich"""
    global url, albumname, last_battery_voltage, last_battery_update
    
    # Battery tracking
    try:
        battery_voltage = float(request.headers.get('batteryCap', '0'))
        if battery_voltage > 0:
            last_battery_voltage = battery_voltage
            last_battery_update = time.time()
    except:
        pass
    
    # Check if pre-prepared photo exists AND is marked as NEW
    preview_bmp_path = os.path.join(photodir, 'latest.bmp')
    status_file = os.path.join(photodir, 'latest.status')
    
    if os.path.exists(preview_bmp_path) and os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status = f.read().strip()
            
            if status == 'new':
                logger.info("📤 Serving pre-prepared photo to ESP32")
                with open(status_file, 'w') as f:
                    f.write('delivered')
                
                return send_file(preview_bmp_path, mimetype='image/bmp', download_name='frame.bmp')
        except Exception as e:
            logger.warning(f"⚠️ Error reading status: {e}")

    # ====================================================================
    # No NEW photo available - fetch and prepare on-the-fly
    # ====================================================================
    logger.info("🔄 Fetching and preparing photo on-the-fly")

    try:
        # Use global variables (like original code)
        if not url or not albumname:
            return jsonify({"error": "Not configured"}), 500

        # Get albums (using global headers)
        response = requests.get(f"{url}/api/albums", headers=headers)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch albums"}), 500

        data = response.json()
        albumid = next((item['id'] for item in data if item.get('albumName') == albumname), None)

        if not albumid:
            return jsonify({"error": "Album not found"}), 404

        # Get photos
        response = requests.get(f"{url}/api/albums/{albumid}", headers=headers)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch album"}), 500

        data = response.json()
        if 'assets' not in data or not data['assets']:
            return jsonify({"error": "No images"}), 404

        # Get image ordering
        image_order_config = current_config['immich'].get('image_order', 'random')
        downloaded_images = load_downloaded_images()

        if image_order_config == 'newest':
            sorted_assets = sorted(data['assets'],
                key=lambda x: x.get('exifInfo', {}).get('dateTimeOriginal', '1970-01-01T00:00:00'),
                reverse=True)
            remaining_images = sorted_assets
        else:  # random
            remaining_images = [img for img in data['assets'] if img['id'] not in downloaded_images]
            if not remaining_images:
                reset_tracking_file()
                remaining_images = data['assets']

        # Select image
        selected_image = remaining_images[0]
        asset_id = selected_image['id']
        save_downloaded_image(asset_id)

        # Download
        response = requests.get(f"{url}/api/assets/{asset_id}/original", headers=headers, stream=True)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download"}), 500

        # Process image
        image_data = io.BytesIO(response.content)
        original_path = selected_image.get('originalPath', '').lower()

        if original_path.endswith(('.raw', '.dng', '.arw', '.cr2', '.nef')):
            with rawpy.imread(image_data) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
                image = Image.fromarray(rgb)
        elif original_path.endswith('.heic'):
            image = Image.open(image_data).convert("RGB")
        else:
            image = Image.open(image_data)

        # Process image
        processed_image = scale_img_in_memory(image)

        # Save as BMP
        preview_bmp_path = os.path.join(photodir, 'latest.bmp')
        with open(preview_bmp_path, 'wb') as f:
            f.write(processed_image.getvalue())

        # Save as JPEG for web preview
        processed_image.seek(0)
        bmp_image = Image.open(processed_image)
        preview_jpg_path = os.path.join(photodir, 'latest_preview.jpg')
        bmp_image.convert('RGB').save(preview_jpg_path, 'JPEG', quality=85)

        # Mark as DELIVERED
        with open(status_file, 'w') as f:
            f.write('delivered')

        logger.info(f"✅ Photo prepared on-the-fly and delivered: {asset_id}")

        # Send to ESP32
        processed_image.seek(0)
        return send_file(processed_image, mimetype='image/bmp', download_name='frame.bmp')

    except Exception as e:
        logger.error(f"❌ Error in /download: {e}")
        return jsonify({"error": str(e)}), 500


# ==============================================================================
# Photo Preview & Management Routes (v1.0.2)
# ==============================================================================

@bp.route('/prepare-photo', methods=['POST'])
def prepare_photo():
    """Manually fetch and prepare a new photo from Immich"""
    try:
        logger.info("📸 Manual photo preparation requested")
        
        immich_url = current_config['immich']['url']
        album_name = current_config['immich']['album']
        
        if not immich_url or not album_name:
            return jsonify({"error": "Immich not configured", "success": False}), 500
        
        logger.info(f"🔍 Fetching albums from {immich_url}")
        
        response = requests.get(f"{immich_url}/api/albums", headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": f"Failed to fetch albums: {response.status_code}", "success": False}), 500
        
        data = response.json()
        album_id = next((item['id'] for item in data if item.get('albumName') == album_name), None)
        
        if not album_id:
            return jsonify({"error": f"Album '{album_name}' not found", "success": False}), 404
        
        logger.info(f"✅ Found album: {album_name} (ID: {album_id})")
        
        response = requests.get(f"{immich_url}/api/albums/{album_id}", headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({"error": "Failed to fetch album assets", "success": False}), 500
        
        data = response.json()
        if 'assets' not in data or not data['assets']:
            return jsonify({"error": "No images in album", "success": False}), 404
        
        logger.info(f"📷 Found {len(data['assets'])} photos in album")
        
        image_order_config = current_config['immich']['image_order']
        downloaded_images = load_downloaded_images()
        
        if image_order_config == 'newest':
            sorted_assets = sorted(data['assets'],
                key=lambda x: x.get('exifInfo', {}).get('dateTimeOriginal', '1970-01-01T00:00:00'),
                reverse=True)
            remaining_images = sorted_assets
        else:
            remaining_images = [img for img in data['assets'] if img['id'] not in downloaded_images]
            if not remaining_images:
                reset_tracking_file()
                remaining_images = data['assets']
        
        selected_image = remaining_images[0]
        asset_id = selected_image['id']
        save_downloaded_image(asset_id)
        
        response = requests.get(f"{immich_url}/api/assets/{asset_id}/original", 
                               headers=headers, stream=True, timeout=30)
        if response.status_code != 200:
            return jsonify({"error": "Failed to download image", "success": False}), 500
        
        image_data = io.BytesIO(response.content)
        original_path = selected_image.get('originalPath', '').lower()
        
        if original_path.endswith(('.raw', '.dng', '.arw', '.cr2', '.nef')):
            with rawpy.imread(image_data) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
                image = Image.fromarray(rgb)
        elif original_path.endswith('.heic'):
            image = Image.open(image_data).convert("RGB")
        else:
            image = Image.open(image_data)
        
        processed_image = scale_img_in_memory(image)
        
        preview_bmp_path = os.path.join(photodir, 'latest.bmp')
        with open(preview_bmp_path, 'wb') as f:
            f.write(processed_image.getvalue())
        
        processed_image.seek(0)
        bmp_image = Image.open(processed_image)
        preview_jpg_path = os.path.join(photodir, 'latest_preview.jpg')
        bmp_image.convert('RGB').save(preview_jpg_path, 'JPEG', quality=85)
        
        status_file = os.path.join(photodir, 'latest.status')
        with open(status_file, 'w') as f:
            f.write('new')
        
        logger.info(f"✅ Photo prepared manually (marked as NEW): {asset_id}")
        
        return jsonify({
            "success": True,
            "message": "Photo prepared successfully",
            "asset_id": asset_id,
            "preview_url": f"./preview-photo?t={int(time.time())}"
        }), 200
        
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Network error: {e}")
        return jsonify({"error": f"Network error: {str(e)}", "success": False}), 500
    except Exception as e:
        logger.error(f"❌ Error preparing photo: {e}", exc_info=True)
        return jsonify({"error": str(e), "success": False}), 500


@bp.route('/preview-photo', methods=['GET'])
def preview_photo():
    """Serve the latest prepared photo as preview"""
    preview_jpg_path = os.path.join(photodir, 'latest_preview.jpg')
    
    if not os.path.exists(preview_jpg_path):
        return jsonify({"error": "No preview available"}), 404
    
    return send_file(preview_jpg_path, mimetype='image/jpeg')


@bp.route('/preview-status', methods=['GET'])
def preview_status():
    """Get the status of the current preview photo"""
    status_file = os.path.join(photodir, 'latest.status')
    preview_jpg_path = os.path.join(photodir, 'latest_preview.jpg')
    
    if not os.path.exists(preview_jpg_path):
        return jsonify({
            "exists": False,
            "status": None,
            "timestamp": None
        })
    
    status = "delivered"
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            status = f.read().strip()
    
    timestamp = os.path.getmtime(preview_jpg_path)
    
    return jsonify({
        "exists": True,
        "status": status,
        "timestamp": timestamp,
        "formatted_time": datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    })

@bp.route('/sleep', methods=['GET'])
def get_sleep_duration():
    """Get sleep duration for ESP32"""
    current_time = datetime.now()
    interval = int(current_config['immich']['wakeup_interval'])
    
    def calculate_next_interval_time(base_time, intervals=1):
        total_minutes = base_time.hour * 60 + base_time.minute
        next_total_minutes = interval * ((total_minutes // interval) + intervals)
        next_total_minutes = next_total_minutes % (24 * 60)
        
        next_time = base_time.replace(
            hour=next_total_minutes // 60,
            minute=next_total_minutes % 60,
            second=0,
            microsecond=0
        )
        
        if next_time < base_time:
            next_time = next_time + timedelta(days=1)
        
        return next_time
    
    next_wakeup = calculate_next_interval_time(current_time)
    
    sleep_start = current_time.replace(
        hour=current_config['immich']['sleep_start_hour'],
        minute=current_config['immich']['sleep_start_minute'],
        second=0,
        microsecond=0
    )
    
    sleep_end = current_time.replace(
        hour=current_config['immich']['sleep_end_hour'],
        minute=current_config['immich']['sleep_end_minute'],
        second=0,
        microsecond=0
    )
    
    if sleep_end < sleep_start:
        if current_time >= sleep_start:
            sleep_end = sleep_end + timedelta(days=1)
        elif current_time < sleep_end:
            sleep_start = sleep_start - timedelta(days=1)
    
    if sleep_start <= next_wakeup < sleep_end:
        next_wakeup = sleep_end
    
    sleep_ms = int((next_wakeup - current_time).total_seconds() * 1000)
    
    if sleep_ms < 600000:
        next_wakeup = calculate_next_interval_time(current_time, intervals=2)
        if sleep_start <= next_wakeup < sleep_end:
            next_wakeup = sleep_end
        sleep_ms = int((next_wakeup - current_time).total_seconds() * 1000)
    
    return jsonify({
        "current_time": current_time.strftime("%Y-%m-%d %H:%M:%S"),
        "next_wakeup": next_wakeup.strftime("%Y-%m-%d %H:%M:%S"),
        "sleep_duration": sleep_ms
    })

# ==============================================================================
# REGISTER BLUEPRINT WITH EMPTY PREFIX (ProxyFix handles the base path)
# ==============================================================================
app.register_blueprint(bp)
logger.info("✅ Blueprint registered")

# ==============================================================================
# NTP Sync (Optional)
# ==============================================================================
def run_daily_ntp_sync():
    """Daily NTP sync"""
    while True:
        try:
            now = datetime.now()
            next_sync = now.replace(hour=4, minute=0, second=0, microsecond=0)
            
            if now >= next_sync:
                next_sync = next_sync + timedelta(days=1)
            
            wait_seconds = (next_sync - now).total_seconds()
            time.sleep(wait_seconds)
            
            try:
                ntp_client = ntplib.NTPClient()
                response = ntp_client.request('pool.ntp.org', timeout=5)
                logger.info(f"NTP sync at {datetime.fromtimestamp(response.tx_time)}")
            except:
                logger.warning("NTP sync failed")
        except:
            time.sleep(3600)

# ==============================================================================
# Application Initialization
# ==============================================================================

# Start config watcher
config_observer = start_config_watcher(config_path)

# Load initial config
try:
    initial_config = ConfigFileHandler(config_path, update_app_config).config
    update_app_config(initial_config)
except Exception as e:
    logger.error(f"Failed to load initial config: {e}")

# Start NTP sync thread
ntp_thread = threading.Thread(target=run_daily_ntp_sync, daemon=True)
ntp_thread.start()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, use_reloader=False, debug=False)
