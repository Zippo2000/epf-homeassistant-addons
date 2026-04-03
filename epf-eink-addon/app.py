#-*- coding:utf8 -*-

# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Based on Zippo2000/EPF with HA Integration
# Full-featured Flask Server with Cython Optimization
# Version 2.0.0 - Multi-Source Support (Immich, ComfyUI via HA, ComfyUI Direct)
# ==============================================================================

from __future__ import annotations

from typing import Optional, Dict, Any, Set, Tuple, Callable, List
import sys

BUILD_TIMESTAMP = "2026-04-03 21:30:00 CET"
BUILD_VERSION = "2.0.0"

from flask import Flask, jsonify, send_file, render_template, request, redirect, url_for, Blueprint
import yaml
import requests
import os
import io
import random
import rawpy
import numpy as np
from numpy import ndarray
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
from PIL.Image import Image as PILImage
from pillow_heif import register_heif_opener
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
import threading
import ntplib
import time
import logging
import sys
from werkzeug.middleware.proxy_fix import ProxyFix
from shutil import copy2
import glob as glob_module

from providers import (
    ImageProvider, ImmichProvider, ComfyUIHAProvider, ComfyUIDirectProvider,
    create_provider, resolve_prompt_variables, GenerationTracker
)

# =============== LOGGING CONFIGURATION ===============
LOG_LEVEL: str = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger: logging.Logger = logging.getLogger(__name__)

# =============== CYTHON MODULE IMPORT ===============
try:
    import cpy
    logger.info(f"Cython functions: {[f for f in dir(cpy) if not f.startswith('_')]}")
    
    load_scaled: Callable[[PILImage, int, str], PILImage] = cpy.load_scaled
    
    if hasattr(cpy, 'convert_image'):
        def convert_image_floyd(img: PILImage, strength: float) -> ndarray:
            return cpy.convert_image(img, '', strength)
        FLOYD_AVAILABLE: bool = True
    else:
        FLOYD_AVAILABLE = False
    
    if hasattr(cpy, 'convert_image_atkinson'):
        def convert_image_atkinson(img: PILImage, strength: float) -> ndarray:
            return cpy.convert_image_atkinson(img, '', strength)
        ATKINSON_AVAILABLE: bool = True
    else:
        ATKINSON_AVAILABLE = False
    
    CYTHON_AVAILABLE: bool = ATKINSON_AVAILABLE or FLOYD_AVAILABLE
    
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
DEFAULT_CONFIG: Dict[str, Any] = {
    'image_source': os.getenv('IMAGE_SOURCE', 'immich'),
    'immich': {
        'url': os.getenv('IMMICH_URL', 'http://192.168.1.10'),
        'album': os.getenv('ALBUM_NAME', 'default_album'),
        'rotation': int(os.getenv('ROTATION_ANGLE', '270')),
        'enhanced': float(os.getenv('COLOR_ENHANCE', '1.8')),
        'contrast': float(os.getenv('CONTRAST', '0.9')),
        'strength': float(os.getenv('DITHERING_STRENGTH', '1.0')),
        'display_mode': os.getenv('DISPLAY_MODE', 'fill'),
        'image_order': os.getenv('IMAGE_ORDER', 'random'),
        'dithering_method': os.getenv('DITHERING_METHOD', 'atkinson'),
        'sleep_start_hour': int(os.getenv('SLEEP_START_HOUR', '23')),
        'sleep_start_minute': int(os.getenv('SLEEP_START_MINUTE', '0')),
        'sleep_end_hour': int(os.getenv('SLEEP_END_HOUR', '6')),
        'sleep_end_minute': int(os.getenv('SLEEP_END_MINUTE', '0')),
        'wakeup_interval': int(os.getenv('WAKEUP_INTERVAL', '1440')),
    },
    'comfyui': {
        'ha_url': os.getenv('HA_URL', ''),
        'prompt': os.getenv('COMFYUI_PROMPT', ''),
        'negative_prompt': os.getenv('COMFYUI_NEGATIVE_PROMPT', ''),
        'width': int(os.getenv('COMFYUI_WIDTH', '800')),
        'height': int(os.getenv('COMFYUI_HEIGHT', '480')),
        'seed': int(os.getenv('COMFYUI_SEED', '-1')),
        'max_generations_per_day': int(os.getenv('COMFYUI_MAX_GENERATIONS', '50')),
        'direct_url': os.getenv('COMFYUI_DIRECT_URL', ''),
        'workflow_json': os.getenv('COMFYUI_WORKFLOW_JSON', ''),
    }
}

current_config: Dict[str, Any] = DEFAULT_CONFIG.copy()

# =============== GLOBAL VARIABLES ===============
image_source: str = current_config.get('image_source', 'immich')
url: str = current_config['immich']['url']
album_name: str = current_config['immich']['album']
rotation_angle: int = current_config['immich']['rotation']
img_enhanced: float = current_config['immich']['enhanced']
img_contrast: float = current_config['immich']['contrast']
strength: float = current_config['immich']['strength']
display_mode: str = current_config['immich']['display_mode']
image_order: str = current_config['immich']['image_order']
dithering_method: str = current_config['immich'].get('dithering_method', 'atkinson')
sleep_start_hour: int = current_config['immich']['sleep_start_hour']
sleep_start_minute: int = current_config['immich']['sleep_start_minute']
sleep_end_hour: int = current_config['immich']['sleep_end_hour']
sleep_end_minute: int = current_config['immich']['sleep_end_minute']

# =============== API CONFIGURATION ===============
api_key: Optional[str] = os.getenv('IMMICH_API_KEY')
photo_dir: str = os.getenv('IMMICH_PHOTO_DEST', 'photos')
config_path: str = os.getenv('CONFIG_PATH', 'config/config.yaml')
tracking_file: str = os.path.join(photo_dir, 'tracking.txt')

os.makedirs(photo_dir, exist_ok=True)

if not os.path.exists(tracking_file):
    open(tracking_file, 'w').close()

headers: Dict[str, str] = {
    'Accept': 'application/json',
    'x-api-key': api_key if api_key else ''
}

ALLOWED_EXTENSIONS: List[str] = ['.jpeg', '.raw', '.jpg', '.bmp', '.dng', '.heic', '.arw', '.cr2', '.dng', '.nef', '.raw']
os.makedirs(photo_dir, exist_ok=True)
register_heif_opener()

# =============== ACTIVE PROVIDER ===============
active_provider: Optional[ImageProvider] = None

def get_active_provider() -> ImageProvider:
    global active_provider, current_config, photo_dir
    if active_provider is None:
        active_provider = create_provider(current_config, photo_dir)
    return active_provider

def reset_provider() -> None:
    global active_provider
    active_provider = create_provider(current_config, photo_dir)
    logger.info(f"Provider reset to: {active_provider.get_source_name()}")

# =============== BATTERY TRACKING ===============
last_battery_voltage: float = 0
last_battery_update: float = 0

BATTERY_LEVELS: Dict[int, int] = {
    4200: 100, 4150: 95, 4110: 90, 4080: 85, 4020: 80,
    3980: 75, 3950: 70, 3910: 65, 3870: 60, 3850: 55,
    3840: 50, 3820: 45, 3800: 40, 3790: 35, 3770: 30,
    3750: 25, 3730: 20, 3710: 15, 3690: 10, 3610: 5, 3400: 0
}

# =============== 6-COLOR PALETTE ===============
palette: List[Tuple[int, int, int]] = [
    (0, 0, 0),
    (255, 255, 255),
    (255, 243, 56),
    (191, 0, 0),
    (100, 64, 255),
    (67, 138, 28)
]

# =============== NTP SHUTDOWN EVENT ===============
_ntp_stop_event: threading.Event = threading.Event()

def calculate_battery_percentage(voltage: float) -> float:
    if voltage >= 4200:
        return 100.0
    if voltage <= 3400:
        return 0.0
    
    voltages: list = list(BATTERY_LEVELS.keys())
    for i in range(len(voltages) - 1):
        if voltages[i] >= voltage >= voltages[i + 1]:
            v1: int = voltages[i]
            v2: int = voltages[i + 1]
            p1: int = BATTERY_LEVELS[v1]
            p2: int = BATTERY_LEVELS[v2]
            percentage: float = p2 + (voltage - v2) * (p1 - p2) / (v1 - v2)
            return round(percentage, 1)
    return 0.0

# =============== PREVIEW CLEANUP ===============
PREVIEW_PATTERNS: List[str] = ['latest_original_*.jpg', 'latest_processed_*.jpg', 'latest_delivered_*.jpg']
MAX_PREVIEW_AGE_SECONDS: int = 7 * 24 * 3600
MAX_PREVIEW_COUNT: int = 50

def cleanup_old_previews(directory: Optional[str] = None, max_age_seconds: Optional[int] = None, max_count: Optional[int] = None) -> int:
    target_dir: str = directory or photo_dir
    age_limit: int = max_age_seconds or MAX_PREVIEW_AGE_SECONDS
    count_limit: int = max_count or MAX_PREVIEW_COUNT
    removed: int = 0
    
    now: float = time.time()
    
    for pattern in PREVIEW_PATTERNS:
        matching_files: List[str] = glob_module.glob(os.path.join(target_dir, pattern))
        
        if len(matching_files) <= count_limit:
            for filepath in matching_files:
                try:
                    file_age: float = now - os.path.getmtime(filepath)
                    if file_age > age_limit:
                        os.remove(filepath)
                        removed += 1
                        logger.info(f"Cleaned up old preview: {filepath} (age: {file_age/3600:.1f}h)")
                except OSError as e:
                    logger.warning(f"Failed to remove {filepath}: {e}")
        else:
            files_with_age: List[Tuple[str, float]] = []
            for filepath in matching_files:
                try:
                    file_age = now - os.path.getmtime(filepath)
                    files_with_age.append((filepath, file_age))
                except OSError:
                    continue
            
            files_with_age.sort(key=lambda x: x[1], reverse=True)
            
            for filepath, file_age in files_with_age:
                if len(matching_files) - removed <= count_limit:
                    break
                try:
                    os.remove(filepath)
                    removed += 1
                    logger.info(f"Cleaned up excess preview: {filepath}")
                except OSError as e:
                    logger.warning(f"Failed to remove {filepath}: {e}")
    
    if removed > 0:
        logger.info(f"Preview cleanup complete: {removed} files removed")
    
    return removed

# =============== HEX CONVERSION ===============
def depalette_image(pixels: ndarray, pal: List[Tuple[int, int, int]]) -> ndarray:
    palette_array: ndarray = np.array(pal)
    diffs: ndarray = np.sqrt(np.sum((pixels[:, :, None, :] - palette_array[None, None, :, :]) ** 2, axis=3))
    indices: ndarray = np.argmin(diffs, axis=2)
    indices[indices > 3] += 1
    return indices

def convert_to_hex_format(image_data: PILImage) -> io.BytesIO:
    pixels: ndarray = np.array(image_data)
    indices: ndarray = depalette_image(pixels, palette)
    height: int
    width: int
    height, width = indices.shape
    
    bytes_array: List[int] = []
    for y in range(height):
        for x in range(0, width, 2):
            if x + 1 < width:
                byte_value: int = (int(indices[y, x]) << 4) | int(indices[y, x + 1])
            else:
                byte_value = int(indices[y, x]) << 4
            bytes_array.append(byte_value)
    
    output = io.StringIO()
    for i, byte_value in enumerate(bytes_array):
        output.write(f"{byte_value:02X}")
        if (i + 1) % 16 == 0:
            output.write(",\n")
        else:
            output.write(",")
    
    result: str = output.getvalue().rstrip(',\n')
    output_bytes: io.BytesIO = io.BytesIO(result.encode('utf-8'))
    output_bytes.seek(0)
    return output_bytes

# =============== IMAGE PROCESSING ===============
def scale_img_in_memory(image: PILImage, target_width: int = 800, target_height: int = 480, bg_color: Tuple[int, int, int] = (255, 255, 255)) -> PILImage:
    global rotation_angle, dithering_method
    rotation: int = rotation_angle
    
    datetime_str: Optional[str] = None
    try:
        exif = image.getexif()
        datetime_str = exif.get(36867) if exif else None
        if not datetime_str and exif:
            datetime_str = exif.get(306)
    except Exception:
        datetime_str = None
    
    image = ImageOps.exif_transpose(image)
    
    if not CYTHON_AVAILABLE:
        logger.error("Cython not available - image processing will fail!")
        raise RuntimeError("Cython module 'cpy' is required but not available")
    
    logger.info(f"Using Cython load_scaled(rotation={rotation}, mode={display_mode})")
    img: PILImage = load_scaled(image, rotation, display_mode)
    logger.info(f"Image after load_scaled: size={img.size}, mode={img.mode}")
    
    enhanced_img: PILImage = ImageEnhance.Color(img).enhance(img_enhanced)
    enhanced_img = ImageEnhance.Contrast(enhanced_img).enhance(img_contrast)
    logger.info(f"Enhanced: color={img_enhanced}, contrast={img_contrast}")
    
    output_img: PILImage
    if dithering_method == 'floyd-steinberg' and FLOYD_AVAILABLE:
        logger.info(f"Using Floyd-Steinberg dithering: strength={strength}")
        output_img = Image.fromarray(convert_image_floyd(enhanced_img, strength), mode='RGB')
    elif dithering_method == 'atkinson' and ATKINSON_AVAILABLE:
        logger.info(f"Using Atkinson dithering: strength={strength}")
        output_img = Image.fromarray(convert_image_atkinson(enhanced_img, strength), mode='RGB')
    else:
        if FLOYD_AVAILABLE:
            logger.warning(f"{dithering_method} not available, using Floyd-Steinberg")
            output_img = Image.fromarray(convert_image_floyd(enhanced_img, strength), mode='RGB')
        else:
            raise RuntimeError("No dithering method available")
    
    logger.info(f"Image after dithering: size={output_img.size}, mode={output_img.mode}")
    
    if datetime_str:
        draw = ImageDraw.Draw(output_img)
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
        except Exception:
            font = ImageFont.load_default()
        
        try:
            try:
                dt = datetime.strptime(datetime_str, '%Y:%m:%d %H:%M:%S')
                formatted_time = dt.strftime('%Y-%m-%d')
            except ValueError:
                dt = datetime.strptime(datetime_str, '%Y.%m.%d')
                formatted_time = dt.strftime('%Y-%m-%d')
        except Exception:
            formatted_time = datetime_str
        
        text_bbox = draw.textbbox((0, 0), formatted_time, font=font)
        text_width: int = text_bbox[2] - text_bbox[0]
        text_height: int = text_bbox[3] - text_bbox[1]
        padding: int = 5
        
        position: Tuple[int, int] = (target_width - text_width - 40, target_height - text_height - 40)
        rect_coords: Tuple[int, int, int, int] = (
            position[0] - padding,
            position[1] - padding,
            position[0] + text_width + padding,
            position[1] + text_height + padding
        )
        
        draw.rectangle(rect_coords, fill=(0, 0, 0))
        draw.text(position, formatted_time, fill=(255, 255, 255), font=font)
        logger.info(f"Date overlay: {formatted_time}")
    
    preview_jpg_path: str = os.path.join(photo_dir, 'latest_preview.jpg')
    output_img.save(preview_jpg_path, 'JPEG', quality=85)
    logger.info("Preview saved")
    
    return output_img

def save_three_previews(image_original: PILImage) -> PILImage:
    original_path: str = os.path.join(photo_dir, 'latest_original.jpg')
    image_resized: PILImage = image_original.copy()
    image_resized.thumbnail((800, 480), Image.LANCZOS)
    image_resized.save(original_path, 'JPEG', quality=95)
    logger.info(f"Saved original preview: {original_path}")
    
    processed_rotated: PILImage = scale_img_in_memory(image_original)
    processed_path: str = os.path.join(photo_dir, 'latest_processed.jpg')
    processed_rotated.save(processed_path, 'JPEG', quality=95)
    logger.info(f"Saved processed preview: {processed_path}")
    
    bmp_path: str = os.path.join(photo_dir, 'latest.bmp')
    bmp_io = io.BytesIO()
    processed_rotated.save(bmp_io, 'BMP')
    with open(bmp_path, 'wb') as f:
        f.write(bmp_io.getvalue())
    logger.info(f"Saved BMP for ESP32: {bmp_path}")
    
    return processed_rotated

# =============== RAW/HEIC CONVERTERS ===============
def convert_raw_or_dng_to_jpg(input_file_path: str, output_dir: str) -> str:
    with rawpy.imread(input_file_path) as raw:
        rgb: ndarray = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
    basename: str = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path: str = os.path.join(output_dir, f'{basename}.jpg')
    Image.fromarray(rgb).save(jpg_path, 'JPEG')
    return jpg_path

def convert_heic_to_jpg(input_file_path: str, output_dir: str) -> str:
    img: PILImage = Image.open(input_file_path).convert('RGB')
    basename = os.path.splitext(os.path.basename(input_file_path))[0]
    jpg_path = os.path.join(output_dir, f'{basename}.jpg')
    img.save(jpg_path, 'JPEG', quality=95)
    return jpg_path

# =============== IMAGE TRACKING FUNCTIONS ===============
def load_downloaded_images() -> Set[str]:
    global album_name
    try:
        if not os.path.exists(tracking_file):
            with open(tracking_file, 'w') as f:
                pass
        os.chmod(tracking_file, 0o666)
        with open(tracking_file, 'r') as f:
            lines: list = f.readlines()
        if not lines or lines[0].strip() != album_name:
            with open(tracking_file, 'w') as f:
                f.write(f"{album_name}\n")
            return set()
        return {line.strip() for line in lines[1:] if line.strip()}
    except Exception as e:
        logger.error(f"Error reading tracking file: {e}")
        return set()

def save_downloaded_image(asset_id: str) -> None:
    global album_name
    try:
        if not os.path.exists(tracking_file):
            with open(tracking_file, 'w') as f:
                pass
        os.chmod(tracking_file, 0o666)
        with open(tracking_file, 'r') as f:
            lines: list = f.readlines()
        if not lines or lines[0].strip() != album_name:
            with open(tracking_file, 'w') as f:
                f.write(f"{album_name}\n")
        with open(tracking_file, 'a') as f:
            f.write(f"{asset_id}\n")
    except Exception as e:
        logger.error(f"Error writing to tracking file: {e}")

def reset_tracking_file() -> None:
    try:
        open(tracking_file, 'w').close()
    except Exception as e:
        logger.error(f"Error resetting tracking file: {e}")
class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, config_path: str, config_update_callback: Callable[[Dict[str, Any]], None]) -> None:
        self.config_path: str = config_path
        self.config_update_callback: Callable[[Dict[str, Any]], None] = config_update_callback
        self.config: Dict[str, Any] = {}
        self.ensure_config_exists()
        self.config = self.load_config()
    
    def ensure_config_exists(self) -> None:
        config_dir: str = os.path.dirname(self.config_path)
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
    
    def on_modified(self, event: FileSystemEvent) -> None:
        if event.src_path == self.config_path:
            logger.info("Config modified, reloading...")
            new_config: Dict[str, Any] = self.load_config()
            self.config_update_callback(new_config)
    
    def load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, 'r') as f:
                config: Any = yaml.safe_load(f)
                if config is None or 'immich' not in config:
                    logger.warning("Invalid YAML, using default config")
                    return DEFAULT_CONFIG
                return config
        except Exception as e:
            logger.error(f"Error reading config: {e}")
            return DEFAULT_CONFIG

def update_app_config(new_config: Dict[str, Any]) -> None:
    global current_config, image_source, url, album_name, rotation_angle, img_enhanced, img_contrast
    global strength, display_mode, image_order, dithering_method, sleep_start_hour, sleep_end_hour, sleep_start_minute, sleep_end_minute
    
    if new_config is None or 'immich' not in new_config:
        logger.warning("Invalid config received, ignoring update")
        return
    
    current_config = new_config
    image_source = new_config.get('image_source', 'immich')
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
    
    reset_provider()
    
    logger.info(f"Config updated: source={image_source}, URL={url}, Album={album_name}, Rotation={rotation_angle}, Dithering={dithering_method}")

def start_config_watcher(cfg_path: str) -> Observer:
    config_handler = ConfigFileHandler(cfg_path, update_app_config)
    observer: Observer = Observer()
    observer.schedule(config_handler, path=os.path.dirname(cfg_path), recursive=False)
    observer.start()
    return observer

# =============== FLASK APP ===============
app: Flask = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

logger.info("=" * 80)
logger.info("EPF Flask Server v2.0.0 - Multi-Source Support")
logger.info(f"Build Version: {BUILD_VERSION} - {BUILD_TIMESTAMP}")
logger.info("=" * 80)
logger.info(f"Cython Available: {CYTHON_AVAILABLE}")
logger.info(f"Config Path: {config_path}")
logger.info("=" * 80)

bp: Blueprint = Blueprint('main', __name__)

# =============== ROUTES ===============
@bp.route('/', methods=['GET', 'POST'])
def settings() -> Any:
    global current_config, last_battery_voltage, last_battery_update
    
    if current_config is None:
        current_config = DEFAULT_CONFIG.copy()
        logger.warning("current_config was None, reset to default")
    
    battery_voltage: float = last_battery_voltage
    battery_percentage: float = calculate_battery_percentage(battery_voltage) if battery_voltage > 0 else 0
    
    battery_last_read: Optional[str]
    if last_battery_update > 0:
        battery_last_read = datetime.fromtimestamp(last_battery_update).strftime('%Y-%m-%d %H:%M:%S')
    else:
        battery_last_read = None
    
    if battery_voltage > 0:
        logger.info(f"Battery: {battery_voltage:.0f}mV ({battery_percentage:.1f}%)")
    
    if request.method == 'POST':
        new_config: Dict[str, Any] = {
            'image_source': request.form.get('image_source', current_config.get('image_source', 'immich')),
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
            },
            'comfyui': {
                'ha_url': request.form.get('ha_url', current_config.get('comfyui', {}).get('ha_url', '')),
                'prompt': request.form.get('comfyui_prompt', current_config.get('comfyui', {}).get('prompt', '')),
                'negative_prompt': request.form.get('comfyui_negative_prompt', current_config.get('comfyui', {}).get('negative_prompt', '')),
                'width': int(request.form.get('comfyui_width', current_config.get('comfyui', {}).get('width', 800))),
                'height': int(request.form.get('comfyui_height', current_config.get('comfyui', {}).get('height', 480))),
                'seed': int(request.form.get('comfyui_seed', current_config.get('comfyui', {}).get('seed', -1))),
                'max_generations_per_day': int(request.form.get('comfyui_max_generations', current_config.get('comfyui', {}).get('max_generations_per_day', 50))),
                'direct_url': request.form.get('comfyui_direct_url', current_config.get('comfyui', {}).get('direct_url', '')),
                'workflow_json': request.form.get('comfyui_workflow_json', current_config.get('comfyui', {}).get('workflow_json', '')),
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
        battery_last_read=battery_last_read,
        addon_version=BUILD_VERSION,
        build_timestamp=BUILD_TIMESTAMP
    )

@bp.route('/health', methods=['GET', 'HEAD'])
def health() -> Any:
    try:
        provider = get_active_provider()
        is_healthy = provider.health_check()
    except Exception:
        is_healthy = False
    
    status_code: int = 200 if is_healthy else 503
    provider = get_active_provider()
    return jsonify({
        'status': 'healthy' if is_healthy else 'degraded',
        'timestamp': datetime.now().isoformat(),
        'source': provider.get_source_name(),
        'source_status': 'connected' if is_healthy else 'unreachable'
    }), status_code

@bp.route('/download', methods=['GET'])
def process_and_download() -> Any:
    global last_battery_voltage, last_battery_update
    
    try:
        battery_voltage: float = float(request.headers.get('batteryCap', 0))
        if battery_voltage > 0:
            last_battery_voltage = battery_voltage
            last_battery_update = time.time()
    except Exception:
        pass
    
    preview_bmp_path: str = os.path.join(photo_dir, 'latest.bmp')
    status_file: str = os.path.join(photo_dir, 'latest.status')
    
    if os.path.exists(preview_bmp_path) and os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                status: str = f.read().strip()
            
            if status == 'new':
                logger.info("Serving pre-prepared photo to ESP32")
                
                bmp_image: PILImage = Image.open(preview_bmp_path)
                hex_data: io.BytesIO = convert_to_hex_format(bmp_image)
                
                processed_path: str = os.path.join(photo_dir, 'latest_processed.jpg')
                delivered_path: str = os.path.join(photo_dir, 'latest_delivered.jpg')
                if os.path.exists(processed_path):
                    copy2(processed_path, delivered_path)
                    logger.info("Copied processed to delivered")
                
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
    
    logger.info("Fetching and preparing photo on-the-fly")
    
    try:
        provider = get_active_provider()
        image, source_id = provider.fetch_image()
        
        save_three_previews(image)
        
        processed_path = os.path.join(photo_dir, 'latest_processed.jpg')
        delivered_path = os.path.join(photo_dir, 'latest_delivered.jpg')
        if os.path.exists(processed_path):
            copy2(processed_path, delivered_path)
            logger.info("Copied processed to delivered (on-the-fly)")
        
        status_file = os.path.join(photo_dir, 'latest.status')
        with open(status_file, 'w') as f:
            f.write('delivered')
        
        preview_bmp_path = os.path.join(photo_dir, 'latest.bmp')
        bmp_image = Image.open(preview_bmp_path)
        hex_data = convert_to_hex_format(bmp_image)
        
        logger.info(f"Photo delivered on-the-fly (hex format) from {provider.get_source_name()}: {source_id}")
        
        return send_file(
            hex_data,
            mimetype='text/plain',
            as_attachment=True,
            download_name='frame.txt'
        )
    
    except RuntimeError as e:
        logger.error(f"Provider error: {e}")
        return jsonify({'error': str(e)}), 500
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error: {e}")
        return jsonify({'error': f'Network error: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error preparing photo: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@bp.route('/preview-photo', methods=['GET'])
def preview_photo() -> Any:
    processed_path: str = os.path.join(photo_dir, 'latest_processed.jpg')
    original_path: str = os.path.join(photo_dir, 'latest_original.jpg')
    
    if os.path.exists(processed_path):
        return send_file(processed_path, mimetype='image/jpeg')
    elif os.path.exists(original_path):
        return send_file(original_path, mimetype='image/jpeg')
    else:
        return jsonify({'error': 'No preview available'}), 404

@bp.route('/preview-status', methods=['GET'])
def preview_status() -> Any:
    status_file: str = os.path.join(photo_dir, 'latest.status')
    processed_path: str = os.path.join(photo_dir, 'latest_processed.jpg')
    
    if not os.path.exists(processed_path):
        return jsonify({'exists': False, 'status': None, 'timestamp': None})
    
    status: str = 'delivered'
    if os.path.exists(status_file):
        with open(status_file, 'r') as f:
            status = f.read().strip()
    
    timestamp: float = os.path.getmtime(processed_path)
    
    return jsonify({
        'exists': True,
        'status': status,
        'timestamp': timestamp,
        'formatted_time': datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    })

@bp.route('/preview-original', methods=['GET'])
def preview_original() -> Any:
    original_path: str = os.path.join(photo_dir, 'latest_original.jpg')
    if not os.path.exists(original_path):
        return jsonify({'error': 'No original available'}), 404
    return send_file(original_path, mimetype='image/jpeg')

@bp.route('/preview-processed', methods=['GET'])
def preview_processed() -> Any:
    processed_path: str = os.path.join(photo_dir, 'latest_processed.jpg')
    if not os.path.exists(processed_path):
        return jsonify({'error': 'No processed image available'}), 404
    return send_file(processed_path, mimetype='image/jpeg')

@bp.route('/preview-delivered', methods=['GET'])
def preview_delivered() -> Any:
    delivered_path: str = os.path.join(photo_dir, 'latest_delivered.jpg')
    if not os.path.exists(delivered_path):
        return jsonify({'error': 'No delivered image available'}), 404
    return send_file(delivered_path, mimetype='image/jpeg')

@bp.route('/api/battery-status', methods=['GET'])
def battery_status() -> Any:
    global last_battery_voltage, last_battery_update
    
    current_time: float = time.time()
    battery_voltage: float = last_battery_voltage
    battery_percentage: float = calculate_battery_percentage(battery_voltage) if battery_voltage > 0 else 0
    
    formatted_timestamp: Optional[str]
    if last_battery_update > 0:
        last_read_time = datetime.fromtimestamp(last_battery_update)
        formatted_timestamp = last_read_time.strftime('%Y-%m-%d %H:%M:%S')
    else:
        formatted_timestamp = None
    
    return jsonify({
        'voltage': int(battery_voltage),
        'voltage_v': round(battery_voltage / 1000, 2),
        'percentage': battery_percentage,
        'last_update': int(last_battery_update),
        'formatted_timestamp': formatted_timestamp,
        'age_seconds': int(current_time - last_battery_update) if last_battery_update > 0 else None
    })

@bp.route('/api/generation-status', methods=['GET'])
def generation_status() -> Any:
    provider = get_active_provider()
    source_name = provider.get_source_name()
    
    if source_name.startswith('ComfyUI') and hasattr(provider, 'tracker'):
        tracker: GenerationTracker = provider.tracker
        last_gen = tracker.get_last_generation()
        max_gens = getattr(provider, 'max_generations_per_day', 0)
        return jsonify({
            'source': source_name,
            'count_today': tracker.get_count_today(),
            'max_per_day': max_gens,
            'last_generation': last_gen['timestamp'][:19] if last_gen else None
        })
    
    return jsonify({
        'source': source_name,
        'count_today': 0,
        'max_per_day': 0,
        'last_generation': None
    })
    
    return jsonify({
        'source': source_name,
        'count_today': 0,
        'max_per_day': 0,
        'last_generation': None
    })

@bp.route('/prepare-photo', methods=['POST'])
def prepare_photo() -> Any:
    try:
        logger.info("Manual photo preparation requested")
        
        provider = get_active_provider()
        image, source_id = provider.fetch_image()
        
        save_three_previews(image)
        
        status_file: str = os.path.join(photo_dir, 'latest.status')
        with open(status_file, 'w') as f:
            f.write('new')
        
        logger.info(f"Photo prepared with 3 previews from {provider.get_source_name()}: {source_id}")
        
        return jsonify({
            'success': True,
            'message': 'Photo prepared successfully',
            'source_id': source_id,
            'source': provider.get_source_name()
        }), 200
    
    except RuntimeError as e:
        logger.error(f"Provider error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500
    except Exception as e:
        logger.error(f"Error preparing photo: {e}", exc_info=True)
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/sleep', methods=['GET'])
def get_sleep_duration() -> Any:
    current_time: datetime = datetime.now()
    interval: int = int(current_config['immich']['wakeup_interval'])
    
    def calculate_next_interval_time(base_time: datetime, intervals: int = 1) -> datetime:
        total_minutes: int = base_time.hour * 60 + base_time.minute
        next_total_minutes: int = ((total_minutes // interval) + intervals) * interval
        next_total_minutes %= (24 * 60)
        
        next_time: datetime = base_time.replace(
            hour=next_total_minutes // 60,
            minute=next_total_minutes % 60,
            second=0,
            microsecond=0
        )
        
        if next_time <= base_time:
            next_time = next_time + timedelta(days=1)
        
        return next_time
    
    next_wakeup: datetime = calculate_next_interval_time(current_time)
    
    sleep_start: datetime = current_time.replace(
        hour=current_config['immich']['sleep_start_hour'],
        minute=current_config['immich']['sleep_start_minute'],
        second=0,
        microsecond=0
    )
    
    sleep_end: datetime = current_time.replace(
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
    
    sleep_ms: int = int((next_wakeup - current_time).total_seconds() * 1000)
    
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

@bp.route('/cleanup-previews', methods=['POST'])
def trigger_cleanup() -> Any:
    try:
        removed: int = cleanup_old_previews()
        return jsonify({
            'success': True,
            'files_removed': removed,
            'message': f'Cleaned up {removed} old preview files'
        }), 200
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        return jsonify({'error': str(e), 'success': False}), 500

@bp.route('/api/gallery-previews', methods=['GET'])
def gallery_previews() -> Any:
    """Return list of all preview files for gallery view."""
    try:
        files: List[Dict[str, str]] = []
        patterns: List[str] = ['latest_original_*.jpg', 'latest_processed_*.jpg', 'latest_delivered_*.jpg']
        
        for pattern in patterns:
            matching = glob_module.glob(os.path.join(photo_dir, pattern))
            for filepath in matching:
                try:
                    mtime = os.path.getmtime(filepath)
                    files.append({
                        'name': os.path.basename(filepath),
                        'url': '/preview-file/' + os.path.basename(filepath),
                        'modified': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'timestamp': mtime
                    })
                except OSError:
                    continue
        
        files.sort(key=lambda x: x['timestamp'], reverse=True)
        return jsonify({'files': files})
    except Exception as e:
        logger.error(f"Gallery previews failed: {e}", exc_info=True)
        return jsonify({'files': [], 'error': str(e)}), 500

@bp.route('/preview-file/<filename>', methods=['GET'])
def preview_file(filename: str) -> Any:
    """Serve a specific preview file by filename."""
    safe_name: str = os.path.basename(filename)
    filepath: str = os.path.join(photo_dir, safe_name)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_file(filepath, mimetype='image/jpeg')

# Register blueprint
app.register_blueprint(bp)
logger.info("Blueprint registered")

# =============== STARTUP ===============
try:
    initial_config: Dict[str, Any] = ConfigFileHandler(config_path, update_app_config).config
    update_app_config(initial_config)
except Exception as e:
    logger.error(f"Failed to load initial config: {e}")

config_observer: Observer = start_config_watcher(config_path)

def run_daily_ntp_sync() -> None:
    while not _ntp_stop_event.is_set():
        try:
            now: datetime = datetime.now()
            next_sync: datetime = now.replace(hour=4, minute=0, second=0, microsecond=0)
            
            if now >= next_sync:
                next_sync = next_sync + timedelta(days=1)
            
            wait_seconds: float = (next_sync - now).total_seconds()
            
            if _ntp_stop_event.wait(timeout=wait_seconds):
                logger.info("NTP sync thread received stop signal")
                break
            
            try:
                ntp_client = ntplib.NTPClient()
                response = ntp_client.request('pool.ntp.org', timeout=5)
                logger.info(f"NTP sync at {datetime.fromtimestamp(response.tx_time)}")
            except Exception:
                logger.warning("NTP sync failed")
        except Exception:
            if _ntp_stop_event.wait(timeout=3600):
                break

def stop_ntp_sync() -> None:
    logger.info("Signaling NTP sync thread to stop...")
    _ntp_stop_event.set()

ntp_thread: threading.Thread = threading.Thread(target=run_daily_ntp_sync, daemon=True)
ntp_thread.start()

# =============== RUN APP ===============
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        stop_ntp_sync()
        ntp_thread.join(timeout=5)
        logger.info("NTP thread stopped, shutting down")
