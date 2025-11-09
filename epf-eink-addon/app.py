#-*- coding:utf8 -*-

# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Based on Zippo2000/EPF with HA Integration
# Full-featured Flask Server with Cython Optimization
# ==============================================================================

BUILD_TIMESTAMP = "2025-11-08 18:20:00 CET"
BUILD_VERSION = "1.0.3"

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

# =============== LOGGING CONFIGURATION ===============
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# =============== CYTHON MODULE IMPORT ===============
try:
    import cpy
    logger.info(f"Cython functions: {[f for f in dir(cpy) if not f.startswith('_')]}")
    
    load_scaled = cpy.load_scaled
    
    if hasattr(cpy, 'convert_image'):
        def convert_image_floyd(img, strength):
            return cpy.convert_image(img, '', strength)
        FLOYD_AVAILABLE = True
    else:
        FLOYD_AVAILABLE = False
    
    if hasattr(cpy, 'convert_image_atkinson'):
        def convert_image_atkinson(img, strength):
            return cpy.convert_image_atkinson(img, '', strength)
        ATKINSON_AVAILABLE = True
    else:
        ATKINSON_AVAILABLE = False
    
    CYTHON_AVAILABLE = ATKINSON_AVAILABLE or FLOYD_AVAILABLE
    
    if CYTHON_AVAILABLE:
        logger.info(f"Cython available: Floyd={FLOYD_AVAILABLE}, Atkinson={ATKINSON_AVAILABLE}")
    else:
        logger.error("No dithering functions found in Cython module")
        
except ImportError as e:
    CYTHON_AVAILABLE = False
    FLOYD_AVAILABLE = False
    ATKINSON_AVAILABLE = False
    logger.error(f"Cython not available: {e}")

# =============== DEFAULT CONFIGURATION ===============
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

# =============== GLOBAL VARIABLES ===============
url = current_config['immich']['url']
album_name = current_config['immich']['album']
rotation_angle = current_config['immich']['rotation']
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

# =============== API CONFIGURATION ===============
api_key = os.getenv('IMMICH_API_KEY')
photo_dir = os.getenv('IMMICH_PHOTO_DEST', 'photos')
config_path = os.getenv('CONFIG_PATH', 'config/config.yaml')
tracking_file = os.path.join(photo_dir, 'tracking.txt')

os.makedirs(photo_dir, exist_ok=True)

if not os.path.exists(tracking_file):
    open(tracking_file, 'w').close()

headers = {
    'Accept': 'application/json',
    'x-api-key': api_key
}

ALLOWED_EXTENSIONS = ['.jpeg', '.raw', '.jpg', '.bmp', '.dng', '.heic', '.arw', '.cr2', '.dng', '.nef', '.raw']
os.makedirs(photo_dir, exist_ok=True)
register_heif_opener()

# =============== BATTERY TRACKING ===============
last_battery_voltage = 0
last_battery_update = 0

BATTERY_LEVELS = {
    4200: 100, 4150: 95, 4110: 90, 4080: 85, 4020: 80,
    3980: 75, 3950: 70, 3910: 65, 3870: 60, 3850: 55,
    3840: 50, 3820: 45, 3800: 40, 3790: 35, 3770: 30,
    3750: 25, 3730: 20, 3710: 15, 3690: 10, 3610: 5, 3400: 0
}

# =============== 6-COLOR PALETTE ===============
palette = [
    (0, 0, 0),         # Black
    (255, 255, 255),   # White
    (255, 243, 56),    # Yellow
    (191, 0, 0),       # Red
    (100, 64, 255),    # Blue
    (67, 138, 28)      # Green
]

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

# =============== IMAGE TRACKING FUNCTIONS ===============
def load_downloaded_images():
    """Load downloaded image IDs from tracking.txt"""
    global album_name
    try:
        if not os.path.exists(tracking_file):
            open(tracking_file, 'w').close()
        
        os.chmod(tracking_file, 0o666)
        
        with open(tracking_file, 'r') as f:
            lines = f.readlines()
        
        if not lines or lines[0].strip() != album_name:
            f.seek(0)
            f.truncate()
            f.write(f"{album_name}\n")
            return set()
        
        return {line.strip() for line in lines[1:] if line.strip()}
    
    except Exception as e:
        logger.error(f"Error reading tracking file: {e}")
        return set()

def save_downloaded_image(asset_id):
    """Save downloaded image ID to tracking.txt"""
    global album_name
    try:
        if not os.path.exists(tracking_file):
            open(tracking_file, 'w').close()
        
        os.chmod(tracking_file, 0o666)
        
        with open(tracking_file, 'r') as f:
            lines = f.readlines()
        
        if not lines or lines[0].strip() != album_name:
            f.seek(0)
            f.truncate()
            f.write(f"{album_name}\n")
        
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

# =============== NEW: DEPALETTE AND HEX CONVERSION ===============
def depalette_image(pixels, palette):
    """
    Convert RGB image to palette indices using nearest color matching.
    This is the Python equivalent of the Cython depalette_image function.
    """
    palette_array = np.array(palette)
    
    # Calculate color distances
    diffs = np.sqrt(np.sum((pixels[:, :, None, :] - palette_array[None, None, :, :]) ** 2, axis=3))
    
    # Find closest palette color for each pixel
    indices = np.argmin(diffs, axis=2)
    
    # Simulate special case from C code (index 3 becomes 1)
    indices[indices > 3] += 1
    
    return indices

def convert_to_hex_format(image_data):
    """
    Convert processed image data to hex-encoded format expected by ESP32.
    Two pixels are packed into one byte (4-bit per pixel).
    Returns comma-separated hex values as text.
    """
    # Get pixel data as numpy array
    pixels = np.array(image_data)
    
    # Convert to palette indices
    indices = depalette_image(pixels, palette)
    
    height, width = indices.shape
    
    # Pack two 4-bit indices into one byte
    bytes_array = []
    for y in range(height):
        for x in range(0, width, 2):
            if x + 1 < width:
                # Pack two pixels: left pixel in high nibble, right pixel in low nibble
                byte_value = (indices[y, x] << 4) | indices[y, x + 1]
            else:
                # Last pixel in row (if width is odd)
                byte_value = indices[y, x] << 4
            
            bytes_array.append(byte_value)
    
    # Convert to hex string with comma separators (ESP32 format)
    output = io.StringIO()
    for i, byte_value in enumerate(bytes_array):
        output.write(f"{byte_value:02X}")
        if (i + 1) % 16 == 0:  # Line break every 16 bytes for readability
            output.write(",\n")
        else:
            output.write(",")
    
    # Remove trailing comma
    result = output.getvalue().rstrip(',\n')
    
    # Return as BytesIO for Flask send_file
    output_bytes = io.BytesIO(result.encode('utf-8'))
    output_bytes.seek(0)
    
    return output_bytes

# =============== IMAGE PROCESSING ===============
def scale_img_in_memory(image, target_width=800, target_height=480, bg_color=(255, 255, 255)):
    """
    Process image in memory using Cython.
    Supports both Atkinson and Floyd-Steinberg dithering.
    """
    global rotation_angle, dithering_method
    rotation = rotation_angle
    
    # Extract EXIF date
    try:
        exif = image.getexif()
        datetime_str = exif.get(36867) if exif else None
        if not datetime_str and exif:
            datetime_str = exif.get(306)
    except:
        datetime_str = None
    
    # Auto-rotate based on EXIF
    image = ImageOps.exif_transpose(image)
    
    # Check Cython availability
    if not CYTHON_AVAILABLE:
        logger.error("Cython not available - image processing will fail!")
        raise RuntimeError("Cython module 'cpy' is required but not available")
    
    logger.info(f"Using Cython load_scaled(rotation={rotation}, mode={display_mode})")
    img = load_scaled(image, rotation, display_mode)
    logger.info(f"Image after load_scaled: size={img.size}, mode={img.mode}")
    
    # Enhancement
    enhanced_img = ImageEnhance.Color(img).enhance(img_enhanced)
    enhanced_img = ImageEnhance.Contrast(enhanced_img).enhance(img_contrast)
    logger.info(f"Enhanced: color={img_enhanced}, contrast={img_contrast}")
    
    # Dithering
    if dithering_method == 'floyd-steinberg' and FLOYD_AVAILABLE:
        logger.info(f"Using Floyd-Steinberg dithering: strength={strength}")
        output_img = convert_image_floyd(enhanced_img, strength)
        output_img = Image.fromarray(output_img, mode='RGB')
    elif dithering_method == 'atkinson' and ATKINSON_AVAILABLE:
        logger.info(f"Using Atkinson dithering: strength={strength}")
        output_img = convert_image_atkinson(enhanced_img, strength)
        output_img = Image.fromarray(output_img, mode='RGB')
    else:
        # Fallback
        if FLOYD_AVAILABLE:
            logger.warning(f"{dithering_method} not available, using Floyd-Steinberg")
            output_img = convert_image_floyd(enhanced_img, strength)
            output_img = Image.fromarray(output_img, mode='RGB')
        else:
            raise RuntimeError("No dithering method available")
    
    logger.info(f"Image after dithering: size={output_img.size}, mode={output_img.mode}")
    
    # Add date overlay
    if datetime_str:
        draw = ImageDraw.Draw(output_img)
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
        except:
            font = ImageFont.load_default()
        
        try:
            try:
                dt = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                formatted_time = dt.strftime('%Y-%m-%d')
            except ValueError:
                dt = datetime.strptime(datetime_str, '%Y.%m.%d')
                formatted_time = dt.strftime('%Y-%m-%d')
        except:
            formatted_time = datetime_str
        
        text_bbox = draw.textbbox((0, 0), formatted_time, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        padding = 5
        
        position = (target_width - text_width - 40, target_height - text_height - 40)
        rect_coords = (
            position[0] - padding,
            position[1] - padding,
            position[0] + text_width + padding,
            position[1] + text_height + padding
        )
        
        draw.rectangle(rect_coords, fill=(0, 0, 0))
        draw.text(position, formatted_time, fill=(255, 255, 255), font=font)
        logger.info(f"Date overlay: {formatted_time}")
    
    # Save preview as JPEG
    preview_jpg_path = os.path.join(photo_dir, 'latest_preview.jpg')
    output_img.save(preview_jpg_path, 'JPEG', quality=85)
    logger.info(f"Preview saved")
    
    return output_img

# =============== RAW/HEIC CONVERTERS ===============
def convert_raw_or_dng_to_jpg(input_file_path, output_dir):
    """Convert RAW/DNG to JPG"""
    with rawpy.imread(input_file_path) as raw:
        rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
    
    basename = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path = os.path.join(output_dir, f'{basename}.jpg')
    Image.fromarray(rgb).save(jpg_path, 'JPEG')
    return jpg_path

def convert_heic_to_jpg(input_file_path, output_dir):
    """Convert HEIC to JPG"""
    img = Image.open(input_file_path).convert('RGB')
    basename = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path = os.path.join(output_dir, f'{basename}.jpg')
    img.save(jpg_path, 'JPEG', quality=95)
    return jpg_path

# =============== CONFIGURATION WATCHER ===============
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
    global current_config, url, album_name, rotation_angle, img_enhanced, img_contrast
    global strength, display_mode, image_order, dithering_method, sleep_start_hour, sleep_end_hour, sleep_start_minute, sleep_end_minute
    
    current_config = new_config
    url = new_config['immich']['url']
    album_name = new_config['immich']['album']
    rotation_angle = new_config['immich']['rotation']
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
    
    logger.info(f"Config updated: URL={url}, Album={album_name}, Rotation={rotation_angle}, Dithering={dithering_method}")

def start_config_watcher(config_path):
    """Start watching config.yaml"""
    config_handler = ConfigFileHandler(config_path, update_app_config)
    observer = Observer()
    observer.schedule(config_handler, path=os.path.dirname(config_path), recursive=False)
    observer.start()
    return observer

# =============== FLASK APP ===============
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

logger.info("=" * 80)
logger.info("EPF Flask Server ( + HA) - Initializing")
logger.info(f"Build Version: {BUILD_VERSION} - {BUILD_TIMESTAMP}")
logger.info("=" * 80)
logger.info(f"Cython Available: {CYTHON_AVAILABLE}")
logger.info(f"Config Path: {config_path}")
logger.info("=" * 80)

bp = Blueprint('main', __name__)

# =============== ROUTES ===============
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
    
    return render_template(
        'settings.html',
        config=current_config if current_config else DEFAULT_CONFIG,
        battery_voltage=battery_voltage,
        battery_percentage=battery_percentage,
        addon_version=BUILD_VERSION,
        build_timestamp=BUILD_TIMESTAMP
    )

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
        'status': 'healthy' if immich_ok else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'immich': 'connected' if immich_ok else 'unreachable'
    }), status_code

@bp.route('/download', methods=['GET'])
def process_and_download():
    """
    Download and process image from Immich.
    CHANGED: Now returns hex-encoded format instead of BMP!
    """
    global url, album_name, last_battery_voltage, last_battery_update
    
    # Battery tracking
    try:
        battery_voltage = float(request.headers.get('batteryCap', 0))
        if battery_voltage > 0:
            last_battery_voltage = battery_voltage
            last_battery_update = time.time()
    except:
        pass
    
    # Check for pre-prepared photo
    preview_bmp_path = os.path.join(photo_dir, 'latest.bmp')
    status_file = os.path.join(photo_dir, 'latest.status')
    
    if os.path.exists(preview_bmp_path) and os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status = f.read().strip()
            
            if status == 'new':
                logger.info("Serving pre-prepared photo to ESP32")
                
                # CHANGED: Convert BMP to hex format before sending
                bmp_image = Image.open(preview_bmp_path)
                hex_data = convert_to_hex_format(bmp_image)
                
                with open(status_file, 'w') as f:
                    f.write('delivered')
                
                return send_file(
                    hex_data,
                    mimetype='text/plain',
                    as_attachment=True,
                    download_name='frame.txt'
                )
        except Exception as e:
            logger.warning(f"Error reading status: {e}")
    
    # Fetch and prepare photo on-the-fly
    logger.info("Fetching and preparing photo on-the-fly")
    
    try:
        if not url or not album_name:
            return jsonify({'error': 'Not configured'}), 500
        
        # Fetch album
        response = requests.get(f'{url}/api/albums', headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch albums'}), 500
        
        data = response.json()
        album_id = next((item['id'] for item in data if item.get('albumName') == album_name), None)
        
        if not album_id:
            return jsonify({'error': f'Album {album_name} not found'}), 404
        
        # Fetch album assets
        response = requests.get(f'{url}/api/albums/{album_id}', headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch album assets'}), 500
        
        data = response.json()
        if 'assets' not in data or not data['assets']:
            return jsonify({'error': 'No images in album'}), 404
        
        # Select image
        image_order_config = current_config['immich'].get('image_order', 'random')
        downloaded_images = load_downloaded_images()
        
        if image_order_config == 'newest':
            sorted_assets = sorted(
                data['assets'],
                key=lambda x: x.get('exifInfo', {}).get('dateTimeOriginal', '1970-01-01T00:00:00'),
                reverse=True
            )
            remaining_images = sorted_assets
        else:  # random
            remaining_images = [img for img in data['assets'] if img['id'] not in downloaded_images]
            if not remaining_images:
                reset_tracking_file()
                remaining_images = data['assets']
        
        selected_image = remaining_images[0]
        asset_id = selected_image['id']
        save_downloaded_image(asset_id)
        
        # Download image
        response = requests.get(
            f'{url}/api/assets/{asset_id}/original',
            headers=headers,
            stream=True,
            timeout=30
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Failed to download image'}), 500
        
        image_data = io.BytesIO(response.content)
        original_path = selected_image.get('originalPath', '').lower()
        
        # Process based on file type
        if original_path.endswith(('.raw', '.dng', '.arw', '.cr2', '.nef')):
            with rawpy.imread(image_data) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
            image = Image.fromarray(rgb)
        elif original_path.endswith('.heic'):
            image = Image.open(image_data).convert('RGB')
        else:
            image = Image.open(image_data)
        
        # Process image
        processed_image = scale_img_in_memory(image)
        
        # CHANGED: Convert to hex format instead of BMP
        hex_data = convert_to_hex_format(processed_image)
        
        # Save BMP for web preview (but send hex to ESP32)
        preview_bmp_path = os.path.join(photo_dir, 'latest.bmp')
        bmp_io = io.BytesIO()
        processed_image.save(bmp_io, 'BMP')
        with open(preview_bmp_path, 'wb') as f:
            f.write(bmp_io.getvalue())
        
        with open(status_file, 'w') as f:
            f.write('delivered')
        
        logger.info(f"Photo prepared on-the-fly and delivered (hex format): {asset_id}")
        
        return send_file(
            hex_data,
            mimetype='text/plain',
            as_attachment=True,
            download_name='frame.txt'
        )
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        return jsonify({'error': f'Network error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error preparing photo: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@bp.route('/preview-photo', methods=['GET'])
def preview_photo():
    """Serve the latest prepared photo as preview"""
    preview_jpg_path = os.path.join(photo_dir, 'latest_preview.jpg')
    
    if not os.path.exists(preview_jpg_path):
        return jsonify({'error': 'No preview available'}), 404
    
    return send_file(preview_jpg_path, mimetype='image/jpeg')

@bp.route('/preview-status', methods=['GET'])
def preview_status():
    """Get the status of the current preview photo"""
    status_file = os.path.join(photo_dir, 'latest.status')
    preview_jpg_path = os.path.join(photo_dir, 'latest_preview.jpg')
    
    if not os.path.exists(preview_jpg_path):
        return jsonify({
            'exists': False,
            'status': None,
            'timestamp': None
        })
    
    status = 'delivered'
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            status = f.read().strip()
    
    timestamp = os.path.getmtime(preview_jpg_path)
    
    return jsonify({
        'exists': True,
        'status': status,
        'timestamp': timestamp,
        'formatted_time': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    })

@bp.route('/prepare-photo', methods=['POST'])
def prepare_photo():
    """Manually fetch and prepare a new photo from Immich"""
    try:
        logger.info("Manual photo preparation requested")
        
        immich_url = current_config['immich']['url']
        album_name = current_config['immich']['album']
        
        if not immich_url or not album_name:
            return jsonify({'error': 'Immich not configured', 'success': False}), 500
        
        logger.info(f"Fetching albums from {immich_url}")
        
        # Fetch albums
        response = requests.get(f'{immich_url}/api/albums', headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({'error': f'Failed to fetch albums: {response.status_code}', 'success': False}), 500
        
        data = response.json()
        album_id = next((item['id'] for item in data if item.get('albumName') == album_name), None)
        
        if not album_id:
            return jsonify({'error': f'Album {album_name} not found', 'success': False}), 404
        
        logger.info(f"Found album '{album_name}' (ID: {album_id})")
        
        # Fetch album assets
        response = requests.get(f'{immich_url}/api/albums/{album_id}', headers=headers, timeout=10)
        if response.status_code != 200:
            return jsonify({'error': 'Failed to fetch album assets', 'success': False}), 500
        
        data = response.json()
        if 'assets' not in data or not data['assets']:
            return jsonify({'error': 'No images in album', 'success': False}), 404
        
        logger.info(f"Found {len(data['assets'])} photos in album")
        
        # Select image
        image_order_config = current_config['immich']['image_order']
        downloaded_images = load_downloaded_images()
        
        if image_order_config == 'newest':
            sorted_assets = sorted(
                data['assets'],
                key=lambda x: x.get('exifInfo', {}).get('dateTimeOriginal', '1970-01-01T00:00:00'),
                reverse=True
            )
            remaining_images = sorted_assets
        else:  # random
            remaining_images = [img for img in data['assets'] if img['id'] not in downloaded_images]
            if not remaining_images:
                reset_tracking_file()
                remaining_images = data['assets']
        
        selected_image = remaining_images[0]
        asset_id = selected_image['id']
        save_downloaded_image(asset_id)
        
        # Download image
        response = requests.get(
            f'{immich_url}/api/assets/{asset_id}/original',
            headers=headers,
            stream=True
        )
        
        if response.status_code != 200:
            return jsonify({'error': 'Failed to download image', 'success': False}), 500
        
        image_data = io.BytesIO(response.content)
        original_path = selected_image.get('originalPath', '').lower()
        
        # Process based on file type
        if original_path.endswith(('.raw', '.dng', '.arw', '.cr2', '.nef')):
            with rawpy.imread(image_data) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
            image = Image.fromarray(rgb)
        elif original_path.endswith('.heic'):
            image = Image.open(image_data).convert('RGB')
        else:
            image = Image.open(image_data)
        
        # Process image
        processed_image = scale_img_in_memory(image)
        
        # Save as BMP
        preview_bmp_path = os.path.join(photo_dir, 'latest.bmp')
        bmp_io = io.BytesIO()
        processed_image.save(bmp_io, 'BMP')
        with open(preview_bmp_path, 'wb') as f:
            f.write(bmp_io.getvalue())
        
        # Save status
        status_file = os.path.join(photo_dir, 'latest.status')
        with open(status_file, 'w') as f:
            f.write('new')
        
        logger.info(f"Photo prepared manually, marked as NEW: {asset_id}")
        
        return jsonify({
            'success': True,
            'message': 'Photo prepared successfully',
            'asset_id': asset_id,
            'preview_url': f'/preview-photo?t={int(time.time())}'
        }), 200
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        return jsonify({'error': f'Network error: {str(e)}', 'success': False}), 500
    except Exception as e:
        logger.error(f"Error preparing photo: {e}", exc_info=True)
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/sleep', methods=['GET'])
def get_sleep_duration():
    """Get sleep duration for ESP32"""
    current_time = datetime.now()
    interval = int(current_config['immich']['wakeup_interval'])
    
    def calculate_next_interval_time(base_time, intervals=1):
        total_minutes = base_time.hour * 60 + base_time.minute
        next_total_minutes = ((total_minutes // interval) + intervals) * interval
        next_total_minutes %= (24 * 60)
        
        next_time = base_time.replace(
            hour=next_total_minutes // 60,
            minute=next_total_minutes % 60,
            second=0,
            microsecond=0
        )
        
        if next_time <= base_time:
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
    
    if sleep_end <= sleep_start:
        if current_time >= sleep_start or current_time <= sleep_end:
            sleep_end = sleep_end + timedelta(days=1)
        elif current_time <= sleep_end:
            sleep_start = sleep_start - timedelta(days=1)
    
    if sleep_start <= next_wakeup <= sleep_end:
        next_wakeup = sleep_end
    
    sleep_ms = int((next_wakeup - current_time).total_seconds() * 1000)
    
    if sleep_ms <= 600000:
        next_wakeup = calculate_next_interval_time(current_time, intervals=2)
        if sleep_start <= next_wakeup <= sleep_end:
            next_wakeup = sleep_end
        sleep_ms = int((next_wakeup - current_time).total_seconds() * 1000)
    
    return jsonify({
        'sleep_duration': sleep_ms,
        'current_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
        'next_wakeup': next_wakeup.strftime('%Y-%m-%d %H:%M:%S')
    })

# Register blueprint
app.register_blueprint(bp)
logger.info("Blueprint registered")

# =============== STARTUP ===============
try:
    initial_config = ConfigFileHandler(config_path, update_app_config).config
    update_app_config(initial_config)
except Exception as e:
    logger.error(f"Failed to load initial config: {e}")

config_observer = start_config_watcher(config_path)

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

# Start NTP sync thread
ntp_thread = threading.Thread(target=run_daily_ntp_sync, daemon=True)
ntp_thread.start()

# =============== RUN APP ===============
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
