# -*- coding: utf-8 -*-
"""
pytest conftest.py - Shared fixtures for EPF E-Ink Add-on tests.

All tests run in isolation using:
- Flask Test Client (no real HTTP server)
- Mocked Immich API via `responses` library
- Mocked filesystem via pytest tmp_path
- Mocked NTP, watchdog, and HA supervisor
"""

import os
import sys
import io
import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pytest
import responses
import yaml
from PIL import Image


# ============================================================
# Constants
# ============================================================

MOCK_IMMICH_URL = "http://mock-immich.local"
MOCK_API_KEY = "test-api-key-12345"
MOCK_ALBUM_NAME = "test_album"
MOCK_ALBUM_ID = "album-uuid-001"
EPD_W = 800
EPD_H = 480

EPD_PALETTE = [
    (0, 0, 0),
    (255, 255, 255),
    (255, 243, 56),
    (191, 0, 0),
    (100, 64, 255),
    (67, 138, 28),
]


# ============================================================
# Helper: Generate test images
# ============================================================

def create_test_image(width=800, height=600, color=(128, 128, 128),
                    include_exif=False, exif_date=None):
    """Create a test PIL Image, optionally with EXIF date."""
    img = Image.new('RGB', (width, height), color)
    # Add gradient for dithering visibility
    pixels = img.load()
    for y in range(height):
        for x in range(width):
            r = int(255 * x / width)
            g = int(255 * y / height)
            b = 128
            pixels[x, y] = (r, g, b)

    if include_exif and exif_date:
        from PIL.ExifTags import Base
        exif = img.getexif()
        exif[36867] = exif_date  # DateTimeOriginal
        img.info['exif'] = exif.tobytes()

    return img


def create_test_jpeg_bytes(width=800, height=600, include_exif=False,
                           exif_date=None):
    """Return JPEG bytes of a test image."""
    img = create_test_image(width, height, include_exif=include_exif,
                            exif_date=exif_date)
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=95)
    buf.seek(0)
    return buf.getvalue()


# ============================================================
# Helper: Mock Immich API responses
# ============================================================

def mock_albums_response(albums=None):
    """Return a list of albums for /api/albums."""
    if albums is None:
        albums = [{
            'id': MOCK_ALBUM_ID,
            'albumName': MOCK_ALBUM_NAME,
            'assetCount': 3,
        }]
    return albums


def mock_album_assets_response(asset_count=3, image_order='newest'):
    """Return assets for /api/albums/{id}."""
    assets = []
    for i in range(asset_count):
        asset = {
            'id': f'asset-uuid-{i:03d}',
            'originalPath': f'/photos/test_image_{i}.jpg',
            'type': 'IMAGE',
            'exifInfo': {
                'dateTimeOriginal': f'2024-06-{15 - i:02d}T10:00:00.000Z',
                'fileName': f'test_image_{i}.jpg',
            }
        }
        assets.append(asset)

    if image_order == 'newest':
        assets.sort(key=lambda x: x['exifInfo']['dateTimeOriginal'],
                    reverse=True)
    return {'assets': assets}


def setup_immich_mocks(responses_mock, album_name=MOCK_ALBUM_NAME,
                       album_id=MOCK_ALBUM_ID, asset_count=3,
                       image_bytes=None, api_key=MOCK_API_KEY,
                       immich_url=MOCK_IMMICH_URL, ping_ok=True,
                       album_not_found=False, assets_empty=False):
    """Set up all Immich API mocks."""

    # Ping endpoint
    if ping_ok:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/server/ping',
            json={'res': True},
            status=200,
        )
    else:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/server/ping',
            body=Exception('Connection refused'),
        )

    # Albums list
    if album_not_found:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/albums',
            json=[],
            status=200,
        )
    else:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/albums',
            json=[{
                'id': album_id,
                'albumName': album_name,
                'assetCount': asset_count,
            }],
            status=200,
        )

    # Album assets
    if assets_empty:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/albums/{album_id}',
            json={'assets': []},
            status=200,
        )
    else:
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/albums/{album_id}',
            json=mock_album_assets_response(asset_count),
            status=200,
        )

    # Asset download
    if image_bytes is None:
        image_bytes = create_test_jpeg_bytes()
    responses_mock.add(
        responses.GET,
        f'{immich_url}/api/assets/asset-uuid-000/original',
        body=image_bytes,
        status=200,
        content_type='image/jpeg',
    )
    for i in range(1, asset_count):
        responses_mock.add(
            responses.GET,
            f'{immich_url}/api/assets/asset-uuid-{i:03d}/original',
            body=image_bytes,
            status=200,
            content_type='image/jpeg',
        )


# ============================================================
# Helper: Write test config YAML
# ============================================================

def write_test_config(config_dir, config=None):
    """Write a test config.yaml file."""
    if config is None:
        config = {
            'immich': {
                'url': MOCK_IMMICH_URL,
                'album': MOCK_ALBUM_NAME,
                'rotation': 270,
                'enhanced': 1.8,
                'contrast': 0.9,
                'strength': 1.0,
                'display_mode': 'fill',
                'image_order': 'random',
                'dithering_method': 'atkinson',
                'sleep_start_hour': 23,
                'sleep_start_minute': 0,
                'sleep_end_hour': 6,
                'sleep_end_minute': 0,
                'wakeup_interval': 60,
            }
        }
    config_path = os.path.join(config_dir, 'config.yaml')
    with open(config_path, 'w') as f:
        yaml.safe_dump(config, f)
    return config_path


# ============================================================
# Helper: Import app module with mocked environment
# ============================================================

def import_app_with_env(env_overrides=None, photo_dir=None, config_path=None):
    """
    Import the app module with custom environment variables.
    Removes cached module first to allow re-import.
    """
    # Remove cached module
    for mod_name in list(sys.modules.keys()):
        if mod_name == 'app' or mod_name.startswith('app.'):
            del sys.modules[mod_name]

    # Set environment
    env = {
        'IMMICH_API_KEY': MOCK_API_KEY,
        'IMMICH_URL': MOCK_IMMICH_URL,
        'ALBUM_NAME': MOCK_ALBUM_NAME,
        'ROTATION_ANGLE': '270',
        'COLOR_ENHANCE': '1.8',
        'CONTRAST': '0.9',
        'DITHERING_STRENGTH': '1.0',
        'DISPLAY_MODE': 'fill',
        'IMAGE_ORDER': 'random',
        'DITHERING_METHOD': 'atkinson',
        'SLEEP_START_HOUR': '23',
        'SLEEP_START_MINUTE': '0',
        'SLEEP_END_HOUR': '6',
        'SLEEP_END_MINUTE': '0',
        'WAKEUP_INTERVAL': '60',
        'LOG_LEVEL': 'WARNING',
    }
    if env_overrides:
        env.update(env_overrides)

    env_patches = []
    for key, value in env.items():
        env_patches.append(patch.dict(os.environ, {key: str(value)}))

    for p in env_patches:
        p.start()

    # Patch photo_dir and config_path via environment
    if photo_dir:
        patch.dict(os.environ, {'IMMICH_PHOTO_DEST': photo_dir}).start()
    if config_path:
        patch.dict(os.environ, {'CONFIG_PATH': config_path}).start()

    # Patch ntplib to avoid real NTP calls
    patch('ntplib.NTPClient').start()

    # Patch watchdog Observer to avoid real file watching
    mock_observer = MagicMock()
    patch('watchdog.observers.Observer', return_value=mock_observer).start()

    # Now import the app module
    import app as app_module

    return app_module


# ============================================================
# Pytest Fixtures
# ============================================================

@pytest.fixture
def mock_immich_url():
    return MOCK_IMMICH_URL


@pytest.fixture
def mock_api_key():
    return MOCK_API_KEY


@pytest.fixture
def mock_album_name():
    return MOCK_ALBUM_NAME


@pytest.fixture
def mock_album_id():
    return MOCK_ALBUM_ID


@pytest.fixture
def test_image_bytes():
    """Return JPEG bytes of a test image."""
    return create_test_jpeg_bytes()


@pytest.fixture
def test_image_bytes_exif():
    """Return JPEG bytes with EXIF date."""
    return create_test_jpeg_bytes(
        include_exif=True,
        exif_date='2024:06:15 14:30:00'
    )


@pytest.fixture
def test_image_pil():
    """Return a PIL Image for testing."""
    return create_test_image(800, 600)


@pytest.fixture
def test_image_800x480():
    """Return a PIL Image at exact E-Ink dimensions."""
    return create_test_image(EPD_W, EPD_H)


@pytest.fixture
def test_config():
    """Return a standard test configuration dict."""
    return {
        'immich': {
            'url': MOCK_IMMICH_URL,
            'album': MOCK_ALBUM_NAME,
            'rotation': 270,
            'enhanced': 1.8,
            'contrast': 0.9,
            'strength': 1.0,
            'display_mode': 'fill',
            'image_order': 'random',
            'dithering_method': 'atkinson',
            'sleep_start_hour': 23,
            'sleep_start_minute': 0,
            'sleep_end_hour': 6,
            'sleep_end_minute': 0,
            'wakeup_interval': 60,
        }
    }


@pytest.fixture
def test_dir(tmp_path):
    """Create a temporary directory structure for test files."""
    photo_dir = tmp_path / 'photos'
    photo_dir.mkdir()

    config_dir = tmp_path / 'config'
    config_dir.mkdir()

    return {
        'root': tmp_path,
        'photos': str(photo_dir),
        'config': str(config_dir),
    }


@pytest.fixture
def test_config_path(test_dir, test_config):
    """Write and return path to test config.yaml."""
    return write_test_config(test_dir['config'], test_config)


@pytest.fixture
def app_module(test_dir, test_config_path):
    """
    Import the app module with mocked environment and isolated filesystem.
    This is the core fixture that sets up the entire test environment.
    """
    # Stop any previously started patches
    from unittest.mock import patch as _patch

    # Patch ntplib before importing
    mock_ntp_client = MagicMock()
    mock_ntp_response = MagicMock()
    mock_ntp_response.tx_time = 1700000000.0
    mock_ntp_client.request.return_value = mock_ntp_response

    with _patch.dict(os.environ, {
        'IMMICH_API_KEY': MOCK_API_KEY,
        'IMMICH_URL': MOCK_IMMICH_URL,
        'ALBUM_NAME': MOCK_ALBUM_NAME,
        'ROTATION_ANGLE': '270',
        'COLOR_ENHANCE': '1.8',
        'CONTRAST': '0.9',
        'DITHERING_STRENGTH': '1.0',
        'DISPLAY_MODE': 'fill',
        'IMAGE_ORDER': 'random',
        'DITHERING_METHOD': 'atkinson',
        'SLEEP_START_HOUR': '23',
        'SLEEP_START_MINUTE': '0',
        'SLEEP_END_HOUR': '6',
        'SLEEP_END_MINUTE': '0',
        'WAKEUP_INTERVAL': '60',
        'LOG_LEVEL': 'WARNING',
        'IMMICH_PHOTO_DEST': test_dir['photos'],
        'CONFIG_PATH': test_config_path,
    }):
        with _patch('ntplib.NTPClient', return_value=mock_ntp_client):
            mock_observer = MagicMock()
            with _patch('watchdog.observers.Observer',
                        return_value=mock_observer):
                # Remove cached module
                for mod_name in list(sys.modules.keys()):
                    if mod_name == 'app' or mod_name.startswith('app.'):
                        del sys.modules[mod_name]

                import app as app_mod

                # Override photo_dir and config_path in the module
                app_mod.photo_dir = test_dir['photos']
                app_mod.config_path = test_config_path
                app_mod.tracking_file = os.path.join(
                    test_dir['photos'], 'tracking.txt')

                # Reset battery state
                app_mod.last_battery_voltage = 0
                app_mod.last_battery_update = 0

                # Reset tracking file
                tracking = app_mod.tracking_file
                if os.path.exists(tracking):
                    os.remove(tracking)

                yield app_mod


@pytest.fixture
def flask_client(app_module):
    """Return a Flask test client."""
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as client:
        yield client


@pytest.fixture
def app_with_immich_mocks(app_module, test_dir, test_config_path,
                          test_image_bytes):
    """
    App module with Immich API responses mocked via `responses`.
    Use this fixture for tests that call /download or /prepare-photo.
    """
    with responses.mock as rsps:
        setup_immich_mocks(
            rsps,
            image_bytes=test_image_bytes,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )
        yield app_module


@pytest.fixture
def client_with_mocks(flask_client, app_module, test_dir, test_config_path,
                      test_image_bytes):
    """
    Flask test client with all external services mocked.
    This is the most commonly used fixture for endpoint tests.
    """
    with responses.mock as rsps:
        setup_immich_mocks(
            rsps,
            image_bytes=test_image_bytes,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )
        # Reset battery state
        app_module.last_battery_voltage = 0
        app_module.last_battery_update = 0
        yield flask_client
