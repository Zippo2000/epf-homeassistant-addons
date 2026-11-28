#-*- coding:utf8 -*-

# ==============================================================================
# Home Assistant Add-on: EPF E-Ink Photo Frame
# Based on Zippo2000/EPF with HA Integration
# Full-featured Flask Server with Cython Optimization
# Version 2.0.0 - Multi-Source Support (Immich, ComfyUI via HA, ComfyUI Direct)
# ==============================================================================

from __future__ import annotations

from typing import Optional, Dict, Any, Set, Tuple, Callable, List
import re
import sys

from flask import Flask, jsonify, send_file, render_template, request, redirect, url_for, Blueprint
import yaml
import requests
import os
import io
import json
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
import uuid
import glob as glob_module

from providers import (
    ImageProvider, ImmichProvider, ComfyUIHAProvider, ComfyUIDirectProvider,
    create_provider, resolve_prompt_variables, GenerationTracker
)

# =============== BUILD INFO (version & build time) ===============
# Both values are DERIVED, never hand-maintained (see plans/findings.md §1):
#   * BUILD_VERSION   <- env ADDON_VERSION (optional build-arg override),
#                        else the add-on manifest next to app.py (single source of truth)
#   * BUILD_TIMESTAMP <- env BUILD_TIMESTAMP (override), else the .build_stamp file
#                        written by the Dockerfile at image-build time
# Fallbacks keep local/dev runs honest: "dev" / "unknown" instead of a stale date.
def _resolve_build_version(default: str = "dev") -> str:
    value: str = os.environ.get('ADDON_VERSION', '').strip()
    if value:
        return value
    manifest: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
    try:
        with open(manifest, 'r', encoding='utf-8') as f:
            match = re.search(r'^\s*version\s*:\s*["\']?([^"\'\s\r\n]+)', f.read(), re.M)
        if match:
            return match.group(1)
    except OSError:
        pass
    return default


def _resolve_build_timestamp(default: str = "unknown") -> str:
    value: str = os.environ.get('BUILD_TIMESTAMP', '').strip()
    if value:
        return value
    stamp: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.build_stamp')
    try:
        with open(stamp, 'r', encoding='utf-8') as f:
            value = f.read().strip()
        if value:
            return value
    except OSError:
        pass
    return default


BUILD_VERSION: str = _resolve_build_version()
BUILD_TIMESTAMP: str = _resolve_build_timestamp()


def _env_bool(name: str, default: bool) -> bool:
    """Seed a boolean setting from the environment (`run.sh` forwards the add-on option).

    HA hands booleans over as `true`/`false`; an unset variable means "use the default".
    A value we cannot read must not change what the frame shows, so it falls back loudly.
    """
    raw: str = os.getenv(name, '').strip().lower()
    if not raw:
        return default
    if raw in ('true', '1', 'yes', 'on'):
        return True
    if raw in ('false', '0', 'no', 'off'):
        return False
    logger.warning(f"{name}={raw!r} is not a boolean; keeping the default ({default})")
    return default

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
def _seed_workflows(raw: str) -> List[Dict[str, Any]]:
    """HA-option seed for the named-workflow list: a JSON-array string from run.sh (2.4.0).

    The settings page owns the list from the first save onwards; a broken seed must not
    stop the add-on, so it degrades to an empty list with a warning.
    """
    if not raw:
        return []
    try:
        parsed: Any = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("COMFYUI_WORKFLOWS seed is not valid JSON; starting with an empty list")
        return []
    if not isinstance(parsed, list):
        logger.warning("COMFYUI_WORKFLOWS seed is not a JSON array; starting with an empty list")
        return []
    return [w for w in parsed if isinstance(w, dict) and w.get('name')]


DEFAULT_CONFIG: Dict[str, Any] = {
    'image_source': os.getenv('IMAGE_SOURCE', 'immich'),
    # Global pipeline settings - they belong to no source (2.4.2). The settings page owns
    # them; the add-on option below only seeds the value on first start.
    'date_overlay': _env_bool('DATE_OVERLAY', True),
    # How the physical frame hangs (2.6.0+): landscape is the hardware-native orientation.
    # portrait swaps the output dimensions to 480x800. The pipeline only auto-rotates the
    # source when its orientation mismatches the physical frame orientation (and the source
    # is not square). Seeded from the add-on option, like date_overlay.
    'frame_orientation': os.getenv('FRAME_ORIENTATION', 'landscape'),
    'immich': {
        'url': os.getenv('IMMICH_URL', ''),
        'album': os.getenv('ALBUM_NAME', 'default_album'),
        'rotation': int(os.getenv('ROTATION_ANGLE', '0')),
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
        'entity_id': os.getenv('COMFYUI_ENTITY_ID', ''),
        'prompt': os.getenv('COMFYUI_PROMPT', ''),
        'negative_prompt': os.getenv('COMFYUI_NEGATIVE_PROMPT', ''),
        'width': int(os.getenv('COMFYUI_WIDTH', '800')),
        'height': int(os.getenv('COMFYUI_HEIGHT', '480')),
        'seed': int(os.getenv('COMFYUI_SEED', '-1')),
        'max_generations_per_day': int(os.getenv('COMFYUI_MAX_GENERATIONS', '50')),
        'direct_url': os.getenv('COMFYUI_DIRECT_URL', ''),
        'workflow_json': os.getenv('COMFYUI_WORKFLOW_JSON', ''),
        'checkpoint': os.getenv('COMFYUI_CHECKPOINT', ''),
        # 2.4.0: named workflows. The runtime YAML is the editing channel; the HA options
        # only seed the list, and these keys are the global defaults an entry can override
        # (they must survive a settings save).
        'workflows': _seed_workflows(os.getenv('COMFYUI_WORKFLOWS', '')),
        'active_workflow': os.getenv('COMFYUI_ACTIVE_WORKFLOW', ''),
        'steps': int(os.getenv('COMFYUI_STEPS', '20')),
        'cfg': float(os.getenv('COMFYUI_CFG', '8.0')),
        'sampler': os.getenv('COMFYUI_SAMPLER', 'euler'),
        'scheduler': os.getenv('COMFYUI_SCHEDULER', 'normal'),
    },
    'gallery': {
        'max_count': int(os.getenv('GALLERY_MAX_COUNT', '50')),
        'retention_days': int(os.getenv('GALLERY_RETENTION_DAYS', '7')),
    }
}

current_config: Dict[str, Any] = DEFAULT_CONFIG.copy()

# =============== NAMED COMFYUI WORKFLOWS (2.4.0) ===============
#: Number of workflow slots in the settings form (the YAML list can hold more).
MAX_WORKFLOWS: int = 4
#: A ComfyUI "Save (Export)" API graph is tens of KB; beyond this something is wrong.
WORKFLOW_JSON_MAX_BYTES: int = 65536
WORKFLOW_NAME_MAX_CHARS: int = 40

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
# Global pipeline switch (2.4.2): renders the EXIF date on the processed image when on.
date_overlay: bool = current_config.get('date_overlay', True)
# Frame orientation (2.6.0): landscape = hardware-native; portrait rotates the pipeline 90deg.
frame_orientation: str = current_config.get('frame_orientation', 'landscape')
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

# =============== PREVIEW GALLERY HISTORY ===============
GALLERY_PATTERNS: List[str] = ['original_*.jpg', 'processed_*.jpg', 'delivered_*.jpg']
# Limits are seeded from the add-on options (run.sh exports GALLERY_MAX_COUNT /
# GALLERY_RETENTION_DAYS) and are refreshed by update_app_config() whenever the
# settings page rewrites the runtime YAML. The names stay module-level on purpose:
# cleanup_gallery() reads them at call time and the tests rebind them directly.
GALLERY_MAX_COUNT: int = int(os.getenv('GALLERY_MAX_COUNT', '50'))
GALLERY_RETENTION_DAYS: int = int(os.getenv('GALLERY_RETENTION_DAYS', '7'))
GALLERY_MAX_AGE_SECONDS: int = 86400 * GALLERY_RETENTION_DAYS

def _gallery_groups(target_dir: str, patterns: List[str]) -> Dict[str, List[Tuple[str, float]]]:
    """Group the archived gallery files by shot id (the '<kind>_<id>.jpg' naming rule).

    A group is one shot: its original, its processed render, and (once M2 lands) its delivered
    file. Files whose name does not carry a shot id are not gallery entries - the live single
    slot, a stray file - and are left untouched, which is the same rule the reader applies.
    """
    groups: Dict[str, List[Tuple[str, float]]] = {}
    for pattern in patterns:
        for filepath in glob_module.glob(os.path.join(target_dir, pattern)):
            stem: str = os.path.splitext(os.path.basename(filepath))[0]
            parts: List[str] = stem.split('_', 1)
            if len(parts) != 2:
                continue
            try:
                mtime: float = os.path.getmtime(filepath)
            except OSError:
                continue
            groups.setdefault(parts[1], []).append((filepath, mtime))
    return groups


def _cleanup_previews_per_shot(target_dir: str, age_limit: int, count_limit: int, patterns: List[str]) -> int:
    """Prune the gallery **per shot**, so a shot is never left with half of its pair.

    Both limits apply to whole shots: age eviction drops a shot whose newest file is older than
    the retention window, count eviction keeps the newest `count_limit` shots and drops the rest
    whole. A shot's age is the mtime of its newest member - the key the reader sorts by - so the
    pruner and /api/gallery-previews judge by the same measure and the cap means shots (pairs),
    not files per pattern (live finding, report 6.3).
    """
    groups: Dict[str, List[Tuple[str, float]]] = _gallery_groups(target_dir, patterns)
    total_removed: int = 0
    now: float = time.time()

    def group_age(files: List[Tuple[str, float]]) -> float:
        return max(mtime for _, mtime in files)

    def remove_files(files: List[Tuple[str, float]], reason: str) -> None:
        nonlocal total_removed
        for filepath, mtime in files:
            try:
                os.remove(filepath)
                total_removed += 1
                logger.info(f"Cleaned up {reason}: {filepath} (age: {(now - mtime) / 3600:.1f}h)")
            except OSError as e:
                logger.warning(f"Failed to remove {filepath}: {e}")

    # 1. age eviction - whole shots, even when under the count limit
    dropped_by_age: set = set()
    for shot, files in groups.items():
        if now - group_age(files) > age_limit:
            remove_files(files, "old preview")
            dropped_by_age.add(shot)

    # 2. count eviction - keep the newest count_limit shots whole
    survivors: List[Tuple[str, float]] = [
        (shot, group_age(files))
        for shot, files in groups.items()
        if shot not in dropped_by_age
    ]
    survivors.sort(key=lambda item: item[1], reverse=True)
    for shot, _age in survivors[count_limit:]:
        remove_files(groups[shot], "excess preview")

    if total_removed > 0:
        logger.info(f"Preview cleanup complete: {total_removed} files removed")
    return total_removed


def cleanup_old_previews(directory: Optional[str] = None, max_age_seconds: Optional[int] = None, max_count: Optional[int] = None, patterns: Optional[List[str]] = None, group_by_shot: bool = False) -> int:
    target_dir: str = directory or photo_dir
    age_limit: int = max_age_seconds or MAX_PREVIEW_AGE_SECONDS
    count_limit: int = max_count or MAX_PREVIEW_COUNT
    use_patterns: List[str] = patterns or PREVIEW_PATTERNS

    # The gallery prunes per shot so that pairs stay pairs; the live preview directory keeps the
    # original per-pattern behaviour (it holds single-slot files, not groups).
    if group_by_shot:
        return _cleanup_previews_per_shot(target_dir, age_limit, count_limit, use_patterns)

    total_removed: int = 0
    now: float = time.time()

    for pattern in use_patterns:
        removed: int = 0
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
        total_removed += removed

    if total_removed > 0:
        logger.info(f"Preview cleanup complete: {total_removed} files removed")
    return total_removed

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

def _target_dimensions(frame_orientation: str) -> Tuple[int, int]:
    """Return (width, height) for the processed frame based on physical orientation."""
    if frame_orientation == 'portrait':
        return 480, 800
    return 800, 480


def _source_orientation(width: int, height: int) -> str:
    """Classify the source image orientation after EXIF auto-transpose."""
    if height == 0:
        return 'square'
    ratio = width / height
    if ratio > 1.1:
        return 'landscape'
    if ratio < 0.9:
        return 'portrait'
    return 'square'


def _needs_auto_rotation(width: int, height: int, frame_orientation: str) -> bool:
    """Return True when the source image should be rotated 90° to match the frame."""
    src_orientation = _source_orientation(width, height)
    if src_orientation == 'square':
        return False
    return src_orientation != frame_orientation


def scale_img_in_memory(image: PILImage, target_width: int = 800, target_height: int = 480, bg_color: Tuple[int, int, int] = (255, 255, 255)) -> PILImage:
    global rotation_angle, dithering_method, frame_orientation
    # Effective rotation: the stored rotation plus 90° only when the source orientation
    # does not match the physical frame orientation (and the source is not square).
    # The output dimensions depend on frame_orientation (800x480 landscape, 480x800 portrait).
    target_width, target_height = _target_dimensions(frame_orientation)
    image = ImageOps.exif_transpose(image)
    extra_rotation: int = 90 if _needs_auto_rotation(image.width, image.height, frame_orientation) else 0
    rotation: int = (rotation_angle + extra_rotation) % 360
    
    datetime_str: Optional[str] = None
    try:
        exif = image.getexif()
        datetime_str = exif.get(36867) if exif else None
        if not datetime_str and exif:
            datetime_str = exif.get(306)
    except Exception:
        datetime_str = None
    
    if not CYTHON_AVAILABLE:
        logger.error("Cython not available - image processing will fail!")
        raise RuntimeError("Cython module 'cpy' is required but not available")
    
    logger.info(f"Using Cython load_scaled(rotation={rotation}, mode={display_mode}, target={target_width}x{target_height}, orientation={frame_orientation})")
    img: PILImage = load_scaled(image, rotation, display_mode, target_width, target_height)
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
    
    if date_overlay and datetime_str:
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

# =============== PREVIEW GALLERY ARCHIVE ===============
# History layer: each Prepare keeps timestamped *copies* in photos/gallery/
# so the Gallery can show a bounded history. The live single-slot files
# (latest.*) used by the ESP32 hand-shake are intentionally left untouched.

def _gallery_dir() -> str:
    return os.path.join(photo_dir, 'gallery')

def _shot_id(source_id: Optional[str]) -> str:
    """Correlation id for one shot: the source id (sanitised) or a ts+uuid fallback."""
    if source_id:
        s: str = re.sub(r'_+', '_', re.sub(r'[^A-Za-z0-9._-]', '_', str(source_id))).strip('_')
        if s:
            return s[:64]
    return 'ts_' + datetime.utcnow().strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:6]

def _copy_into_gallery(src_rel: str, dst_name: str) -> None:
    src: str = os.path.join(photo_dir, src_rel)
    if not os.path.exists(src):
        return
    dest_dir: str = _gallery_dir()
    os.makedirs(dest_dir, exist_ok=True)
    dst: str = os.path.join(dest_dir, dst_name)
    tmp: str = dst + '.tmp'
    try:
        copy2(src, tmp)
        os.replace(tmp, dst)
    except OSError as e:
        logger.warning(f"Failed to archive preview {src}->{dst}: {e}")
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass

def _archive_previews(source_id: Optional[str]) -> None:
    shot: str = _shot_id(source_id)
    _copy_into_gallery('latest_original.jpg', 'original_%s.jpg' % shot)
    _copy_into_gallery('latest_processed.jpg', 'processed_%s.jpg' % shot)
    logger.info(f"Archived previews for shot '{shot}'")

def cleanup_gallery() -> int:
    # group_by_shot: gallery_max_count / gallery_retention_days count shots (pairs), not files
    # per pattern - see _cleanup_previews_per_shot.
    return cleanup_old_previews(
        directory=_gallery_dir(),
        patterns=GALLERY_PATTERNS,
        max_age_seconds=GALLERY_MAX_AGE_SECONDS,
        max_count=GALLERY_MAX_COUNT,
        group_by_shot=True,
    )


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
    global GALLERY_MAX_COUNT, GALLERY_RETENTION_DAYS, GALLERY_MAX_AGE_SECONDS
    global date_overlay, frame_orientation
    
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
    date_overlay = bool(new_config.get('date_overlay', True))
    frame_orientation = str(new_config.get('frame_orientation', 'landscape'))
    sleep_start_hour = new_config['immich']['sleep_start_hour']
    sleep_end_hour = new_config['immich']['sleep_end_hour']
    sleep_start_minute = new_config['immich']['sleep_start_minute']
    sleep_end_minute = new_config['immich']['sleep_end_minute']

    gallery_cfg = new_config.get('gallery') or {}
    GALLERY_MAX_COUNT = int(gallery_cfg.get('max_count', GALLERY_MAX_COUNT))
    GALLERY_RETENTION_DAYS = int(gallery_cfg.get('retention_days', GALLERY_RETENTION_DAYS))
    GALLERY_MAX_AGE_SECONDS = 86400 * GALLERY_RETENTION_DAYS
    
    reset_provider()
    
    logger.info(f"Config updated: source={image_source}, URL={url}, Album={album_name}, Rotation={rotation_angle}, Orientation={frame_orientation}, Dithering={dithering_method}, DateOverlay={date_overlay}")

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
def form_field(canonical: str, legacy: str, default: Any) -> Any:
    """Read a settings form field by its canonical (add-on option) name.

    `canonical` is the name used by the form and by the add-on options in config.yaml;
    `legacy` is the short pre-2.3.2 form name that stored configs, older bookmarks and
    existing tests may still post. The key written into the runtime YAML is unchanged
    (see ARCHITECTURE.md, invariants).
    """
    value = request.form.get(canonical)
    if value is None:
        value = request.form.get(legacy)
    return default if value is None else value


#: Spellings the settings form uses for a boolean; anything else means "off".
TRUE_WORDS: Tuple[str, ...] = ('true', '1', 'yes', 'on', 'enabled')


def form_bool(name: str, current: bool) -> bool:
    """Read a boolean from the settings form; a POST that omits the field keeps the stored value.

    The form always sends its controls, so the switch changes through the page. Callers that
    post a partial form (older tests, scripts) must not be able to flip a setting by silence.
    """
    value: Optional[str] = request.form.get(name)
    if value is None:
        return current
    return value.strip().lower() in TRUE_WORDS


#: Fields a workflow slot carries (form name = `wf_<slot>_<field>`, YAML key = `<field>`).
WF_SLOT_FIELDS: Tuple[str, ...] = (
    'name', 'api_json', 'prompt', 'negative_prompt',
    'prompt_node', 'prompt_input', 'negative_node', 'negative_input', 'seed_node',
    'steps', 'cfg', 'sampler', 'scheduler',
)


def _slot_has_content(form: Any, slot: int) -> bool:
    """True when a settings-form slot carries anything at all (2.4.3, plan §9.1).

    Used to refuse a slot that has content but no name: such a slot used to vanish at save
    time without a word, which is what made a pasted workflow disappear.
    """
    return any((form.get(f'wf_{slot}_{field}') or '').strip() for field in WF_SLOT_FIELDS)


def _slot_unchanged(form: Any, slot: int, stored: Dict[str, Any]) -> bool:
    """True when every resubmitted slot value equals what the YAML already holds (2.6.2).

    The settings page pre-fills the slots from the stored list, so a save always posts the
    stored content back — even for a nameless legacy slot. The 2.4.3b guard is about *new*
    pasted content that would vanish silently; resubmitting unchanged stored content is a
    no-op and must not veto the save (field report: one nameless slot locked every save,
    including unrelated ones like the frame orientation).
    """
    for field in WF_SLOT_FIELDS:
        if field == 'name':
            continue
        posted: str = (form.get(f'wf_{slot}_{field}') or '').strip()
        have: Any = stored.get(field, '')
        if field in ('prompt_input', 'negative_input') and have in ('', None) and posted == 'text':
            continue  # the form's default placeholder, not a stored value
        if field in ('steps', 'cfg'):
            if posted:
                try:
                    if float(posted) != float(have):
                        return False
                except (TypeError, ValueError):
                    return False
            elif have not in ('', None):
                return False
        elif posted != str(have):
            return False
    return True


def parse_workflow_slots(form: Any, current_config: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str, Optional[str]]:
    """Rebuild the named-workflow list from the settings form slots (2.4.0).

    Slots without a name are dropped — but a slot that carries **content** without a name is
    refused with a message, because that is a user who pasted a workflow and would otherwise
    get nothing back (2.4.3). Names must be unique and short. A pasted workflow
    has to be ComfyUI **API** JSON — what "Save (Export)" produces — because that is what
    `POST /prompt` takes; the format ComfyUI stores by default is a UI graph (`nodes` /
    `links`) and cannot be submitted. We say so at save time instead of letting the next
    generation fail. A POST that carries no `wf_*` field at all leaves the stored list
    untouched (legacy callers and the pre-2.4.0 tests).

    Returns `(workflows, active_workflow, error)`; `error` is set on rejection.
    """
    previous: Dict[str, Any] = current_config.get('comfyui', {}) or {}
    if not any(str(key).startswith('wf_') for key in form.keys()):
        return list(previous.get('workflows') or []), str(previous.get('active_workflow') or ''), None
    
    workflows: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    
    for slot in range(1, MAX_WORKFLOWS + 1):
        name: str = (form.get(f'wf_{slot}_name') or '').strip()
        if not name:
            if _slot_has_content(form, slot):
                stored_list: List[Dict[str, Any]] = list(previous.get('workflows') or [])
                stored: Dict[str, Any] = stored_list[slot - 1] if slot - 1 < len(stored_list) and isinstance(stored_list[slot - 1], dict) else {}
                if _slot_unchanged(form, slot, stored):
                    # Unchanged stored content: keep the entry exactly as stored (name and all)
                    # instead of dropping or vetoing it (2.6.2).
                    workflows.append(dict(stored))
                    continue
                return [], '', (f'slot {slot} has content but no name — a slot is only stored '
                                'when it is named (give it a name, or clear it)')
            continue
        if len(name) > WORKFLOW_NAME_MAX_CHARS:
            return [], '', f'workflow name too long: {name[:20]}... (max {WORKFLOW_NAME_MAX_CHARS} characters)'
        if name in seen:
            return [], '', f'duplicate workflow name: {name}'
        seen.add(name)
        
        entry: Dict[str, Any] = {'name': name}
        raw_json: str = (form.get(f'wf_{slot}_api_json') or '').strip()
        if raw_json:
            if len(raw_json.encode('utf-8')) > WORKFLOW_JSON_MAX_BYTES:
                return [], '', f"workflow '{name}': JSON larger than {WORKFLOW_JSON_MAX_BYTES // 1024} KiB"
            try:
                parsed: Any = json.loads(raw_json)
            except json.JSONDecodeError as exc:
                return [], '', f"workflow '{name}': API JSON not parsable ({exc.msg} at line {exc.lineno})"
            if (not isinstance(parsed, dict) or not parsed
                    or not all(isinstance(node, dict) and 'class_type' in node for node in parsed.values())):
                return [], '', (f"workflow '{name}': not ComfyUI API format (expected "
                                f'{{"<node id>": {{"class_type": ...}}}} — use "Save (Export)" in '
                                'ComfyUI, not the normal save)')
            entry['api_json'] = raw_json
        
        for field in ('prompt', 'negative_prompt', 'prompt_node', 'prompt_input',
                      'negative_node', 'negative_input', 'seed_node', 'sampler', 'scheduler'):
            value: str = (form.get(f'wf_{slot}_{field}') or '').strip()
            if value:
                entry[field] = value
        
        for field, cast, low, high in (('steps', int, 1, 200), ('cfg', float, 0.0, 30.0)):
            raw_value: str = (form.get(f'wf_{slot}_{field}') or '').strip()
            if not raw_value:
                continue
            try:
                number: float = cast(raw_value)
            except ValueError:
                return [], '', f"workflow '{name}': {field} is not a number: {raw_value}"
            if not (low <= float(number) <= high):
                return [], '', f"workflow '{name}': {field} out of range ({low}-{high}): {raw_value}"
            entry[field] = number
        
        workflows.append(entry)
    
    active: str = (form.get('active_workflow') or '').strip()
    if active and active not in seen:
        return workflows, '', f'active workflow "{active}" has no slot with that name'
    
    return workflows, active, None


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
            # global switch, source-independent (2.4.2)
            'date_overlay': form_bool('date_overlay', current_config.get('date_overlay', True)),
            # frame orientation (2.6.0): the form always posts the select; a partial POST keeps
            # the stored value (2.4.3b rule) and invalid values are refused below (FR-034/D5).
            'frame_orientation': (request.form.get('frame_orientation')
                                  or current_config.get('frame_orientation', 'landscape')),
            'immich': {
                'url': form_field('immich_url', 'url', current_config['immich']['url']),
                'album': form_field('album_name', 'album', current_config['immich']['album']),
                'rotation': int(form_field('rotation_angle', 'rotation', current_config['immich']['rotation'])),
                'enhanced': float(form_field('color_enhance', 'enhanced', current_config['immich']['enhanced'])),
                'contrast': float(request.form.get('contrast', current_config['immich']['contrast'])),
                'strength': float(form_field('dithering_strength', 'strength', current_config['immich']['strength'])),
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
                'entity_id': request.form.get('comfyui_entity_id', current_config.get('comfyui', {}).get('entity_id', '')),
                'prompt': request.form.get('comfyui_prompt', current_config.get('comfyui', {}).get('prompt', '')),
                'negative_prompt': request.form.get('comfyui_negative_prompt', current_config.get('comfyui', {}).get('negative_prompt', '')),
                'width': int(request.form.get('comfyui_width', current_config.get('comfyui', {}).get('width', 800))),
                'height': int(request.form.get('comfyui_height', current_config.get('comfyui', {}).get('height', 480))),
                'seed': int(request.form.get('comfyui_seed', current_config.get('comfyui', {}).get('seed', -1))),
                'max_generations_per_day': int(request.form.get('comfyui_max_generations', current_config.get('comfyui', {}).get('max_generations_per_day', 50))),
                'direct_url': request.form.get('comfyui_direct_url', current_config.get('comfyui', {}).get('direct_url', '')),
                'workflow_json': request.form.get('comfyui_workflow_json', current_config.get('comfyui', {}).get('workflow_json', '')),
                'checkpoint': request.form.get('comfyui_checkpoint', current_config.get('comfyui', {}).get('checkpoint', '')),
                # global defaults a named workflow may override — not form fields, kept from
                # the running config so a save never drops them (see 2.4.0 plan §2.2).
                'steps': int(current_config.get('comfyui', {}).get('steps', 20)),
                'cfg': float(current_config.get('comfyui', {}).get('cfg', 8.0)),
                'sampler': current_config.get('comfyui', {}).get('sampler', 'euler'),
                'scheduler': current_config.get('comfyui', {}).get('scheduler', 'normal'),
                'workflows': [],
                'active_workflow': '',
            },
            'gallery': {
                'max_count': int(request.form.get('gallery_max_count', current_config.get('gallery', {}).get('max_count', 50))),
                'retention_days': int(request.form.get('gallery_retention_days', current_config.get('gallery', {}).get('retention_days', 7))),
            }
        }
        
        if new_config['immich']['rotation'] not in [0, 90, 180, 270]:
            return "Invalid rotation", 400
        if new_config['frame_orientation'] not in ('landscape', 'portrait'):
            return "Invalid frame orientation", 400
        
        # Workflow slots are a ComfyUI-only setting: a save targeting any other source keeps the
        # stored list untouched, so a broken slot (content without a name — legacy configs from
        # before 2.4.3b) cannot veto an immich save (2.6.1). Against a ComfyUI source the 2.4.3b
        # guard stays in force: name it or clear it.
        target_source: str = request.form.get('image_source', (current_config or {}).get('immich', {}).get('source', ''))
        if target_source in ('comfyui_ha', 'comfyui_direct'):
            workflows, active_workflow, wf_error = parse_workflow_slots(request.form, current_config)
            if wf_error:
                logger.warning(f"Settings rejected: {wf_error}")
                return f"Invalid workflow configuration: {wf_error}", 400
            new_config['comfyui']['workflows'] = workflows
            new_config['comfyui']['active_workflow'] = active_workflow
            if workflows or active_workflow:
                logger.info(f"ComfyUI workflows: {[w.get('name', '(unnamed)') for w in workflows]}, "
                            f"active='{active_workflow or '(built-in)'}'")
        else:
            stored_comfy = (current_config or {}).get('comfyui', {}) or {}
            new_config['comfyui']['workflows'] = list(stored_comfy.get('workflows') or [])
            new_config['comfyui']['active_workflow'] = str(stored_comfy.get('active_workflow') or '')
        
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
        build_timestamp=BUILD_TIMESTAMP,
        runtime_status={
            # Read-only echo of the two channels that must never land in the YAML.
            'immich_api_key_set': bool(os.getenv('IMMICH_API_KEY', '')),
            'ha_api_token_set': bool(os.getenv('HA_API_TOKEN', '')),
            'log_level': LOG_LEVEL,
        },
        max_workflows=MAX_WORKFLOWS
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
        _archive_previews(source_id)
        cleanup_gallery()
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
    """Return the archived preview history, grouped by source id, newest first."""
    try:
        files: List[Dict[str, Any]] = []
        gdir: str = _gallery_dir()
        for pattern in GALLERY_PATTERNS:
            for filepath in glob_module.glob(os.path.join(gdir, pattern)):
                try:
                    base: str = os.path.basename(filepath)
                    stem, _ext = os.path.splitext(base)
                    parts = stem.split('_', 1)
                    if len(parts) != 2:
                        continue
                    kind, shot = parts
                    mtime: float = os.path.getmtime(filepath)
                    files.append({
                        'id': shot,
                        'kind': kind,
                        # Relative URL: the UI is embedded under HA ingress (/api/ingress/<token>/).
                        # An absolute '/preview-file/...' would resolve to the HA root and 404.
                        'url': './preview-file/' + base,
                        'name': base,
                        'modified': datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M:%S'),
                        'timestamp': mtime,
                    })
                except (OSError, ValueError):
                    continue
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for f in files:
            groups.setdefault(f['id'], []).append(f)
        ids = sorted(
            groups.keys(),
            key=lambda i: max(x['timestamp'] for x in groups[i]),
            reverse=True,
        )[:GALLERY_MAX_COUNT]
        out: List[Dict[str, Any]] = []
        for i in ids:
            for f in sorted(groups[i], key=lambda x: x['modified'], reverse=True):
                f.pop('timestamp', None)
                out.append(f)
        return jsonify({'files': out, 'count': len(ids)})
    except Exception as e:
        logger.error(f"Gallery previews failed: {e}", exc_info=True)
        return jsonify({'files': [], 'error': str(e)}), 500

@bp.route('/preview-file/<filename>', methods=['GET'])
def preview_file(filename: str) -> Any:
    """Serve a specific preview file by filename."""
    safe_name: str = os.path.basename(filename)
    for _base in (photo_dir, _gallery_dir()):
        filepath: str = os.path.join(_base, safe_name)
        if os.path.exists(filepath):
            return send_file(filepath, mimetype='image/jpeg')
    return jsonify({'error': 'File not found'}), 404

# Register blueprint
app.register_blueprint(bp)
logger.info("Blueprint registered")

@app.after_request
def _no_cache_settings_page(response):
    """The settings page re-renders from the live config (e.g. the body's orientation
    attribute after a save). Browser heuristic caching of that HTML is exactly how a
    'saved but the page still shows the old state' complaint appears, so the page is
    never cached; the binary endpoints (previews, frame, health JSON) are untouched."""
    if response.content_type and response.content_type.startswith('text/html'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

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
