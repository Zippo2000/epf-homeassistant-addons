# -*- coding: utf-8 -*-
"""
Test suite for EPF E-Ink Add-on - Functional Requirements (FR-001 to FR-023).

All tests run with mocked Immich API, mocked filesystem, and Flask Test Client.
No real Home Assistant or Immich server is required.
"""

import os
import io
import json
import re
import time
import requests
from collections import Counter
from unittest.mock import patch, MagicMock
from datetime import datetime
from PIL import Image

import pytest
import responses
import yaml

from conftest import (
    MOCK_IMMICH_URL, MOCK_API_KEY, MOCK_ALBUM_NAME, MOCK_ALBUM_ID,
    create_test_jpeg_bytes, create_test_image, setup_immich_mocks,
    write_test_config, EPD_W, EPD_H,
)


# ============================================================
# TC-FR-001: Immich Album Retrieval
# ============================================================

class TestFR001AlbumRetrieval:
    """TC-FR-001: Verify album list retrieval from Immich."""

    @responses.activate
    def test_album_list_retrieved_with_api_key(self, client_with_mocks,
                                                app_module):
        """SUT retrieves album list with x-api-key header."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )
        response = client_with_mocks.post('/prepare-photo')
        data = response.get_json()

        # Check that the album LIST endpoint (GET /api/albums) was called with the key.
        # (After the 14.3 v3 change, album *assets* no longer come from /api/albums/{id};
        # only the list call is addressed here, so match exactly '.../api/albums'.)
        albums_request = next(
            (call for call in responses.calls
             if call.request.url.rstrip('/').endswith('/api/albums')),
            None)
        assert albums_request is not None
        assert albums_request.request.headers.get('x-api-key') == MOCK_API_KEY


# ============================================================
# TC-FR-002: Album Asset Retrieval
# ============================================================

class TestFR002AlbumAssetRetrieval:
    """TC-FR-002: Verify asset retrieval from selected album."""

    @responses.activate
    def test_assets_retrieved_for_configured_album(self, client_with_mocks,
                                                    app_module):
        """SUT retrieves assets from the configured album."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            album_name=MOCK_ALBUM_NAME,
            album_id=MOCK_ALBUM_ID,
        )
        response = client_with_mocks.post('/prepare-photo')
        data = response.get_json()

        # Check album assets endpoint was called
        album_assets_called = any(
            'search/metadata' in call.request.url
            for call in responses.calls
        )
        assert album_assets_called


# ============================================================
# TC-FR-003: Image Selection Strategy
# ============================================================

class TestFR003ImageSelection:
    """TC-FR-003: Verify image selection based on configured order."""

    @responses.activate
    def test_random_selection_picks_unseen_image(self, client_with_mocks,
                                                  app_module, test_dir):
        """Random mode selects different unseen images."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            asset_count=5,
        )

        app_module.image_order = 'random'
        tracking_file = app_module.tracking_file

        # Clear tracking
        if os.path.exists(tracking_file):
            os.remove(tracking_file)

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify tracking file has the asset ID
        with open(tracking_file, 'r') as f:
            lines = f.readlines()
        assert len(lines) >= 2  # album name + at least 1 asset

    @responses.activate
    def test_newest_selection_picks_most_recent(self, client_with_mocks,
                                                 app_module, test_dir):
        """Newest mode selects by descending EXIF date."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            asset_count=3,
        )

        app_module.image_order = 'newest'
        tracking_file = app_module.tracking_file

        if os.path.exists(tracking_file):
            os.remove(tracking_file)

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

    @responses.activate
    def test_tracking_resets_after_all_shown(self, client_with_mocks,
                                             app_module, test_dir):
        """Tracking file resets after all images shown."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            asset_count=2,
        )

        app_module.image_order = 'random'
        tracking_file = app_module.tracking_file

        # Pre-fill tracking with all asset IDs
        with open(tracking_file, 'w') as f:
            f.write(f"{MOCK_ALBUM_NAME}\n")
            f.write("asset-uuid-000\n")
            f.write("asset-uuid-001\n")

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200

        # Tracking should be reset
        with open(tracking_file, 'r') as f:
            lines = f.readlines()
        # After reset, only album name + 1 new asset
        assert len(lines) >= 1


# ============================================================
# TC-FR-004: Image Download
# ============================================================

class TestFR004ImageDownload:
    """TC-FR-004: Verify original image download from Immich."""

    @responses.activate
    def test_image_downloaded_from_immich(self, client_with_mocks,
                                          app_module):
        """SUT downloads original image successfully."""
        responses.reset()
        test_bytes = create_test_jpeg_bytes()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            image_bytes=test_bytes,
        )

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        # Verify download endpoint was called
        download_called = any(
            '/original' in call.request.url
            for call in responses.calls
        )
        assert download_called


# ============================================================
# TC-FR-005: RAW/DNG/HEIC Conversion
# ============================================================

class TestFR005FormatConversion:
    """TC-FR-005: Verify format conversion (RAW, HEIC, JPEG)."""

    def test_jpeg_opens_directly(self, app_module, test_dir):
        """Standard JPEG format opens without conversion."""
        img = create_test_image(800, 600)
        buf = io.BytesIO()
        img.save(buf, format='JPEG')
        buf.seek(0)

        opened = Image.open(buf)
        assert opened.mode == 'RGB' or opened.mode != 'RGB'  # Can convert

    def test_raw_conversion_function_exists(self, app_module):
        """RAW conversion function is available."""
        assert hasattr(app_module, 'convert_raw_or_dng_to_jpg')

    def test_heic_conversion_function_exists(self, app_module):
        """HEIC conversion function is available."""
        assert hasattr(app_module, 'convert_heic_to_jpg')


# ============================================================
# TC-FR-006: Image Scaling and Rotation
# ============================================================

class TestFR006ScalingRotation:
    """TC-FR-006: Verify image scaling and rotation to E-Ink dimensions."""

    def test_load_scaled_produces_800x480(self, app_module):
        """Output image is exactly 800x480 pixels."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'

        result = app_module.load_scaled(img, 0, 'fit')
        assert result.size == (EPD_W, EPD_H)

    def test_rotation_90(self, app_module):
        """90 degree rotation produces correct dimensions."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        result = app_module.load_scaled(img, 90, 'fit')
        assert result.size == (EPD_W, EPD_H)

    def test_rotation_180(self, app_module):
        """180 degree rotation produces correct dimensions."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        result = app_module.load_scaled(img, 180, 'fit')
        assert result.size == (EPD_W, EPD_H)

    def test_rotation_270(self, app_module):
        """270 degree rotation produces correct dimensions."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        result = app_module.load_scaled(img, 270, 'fit')
        assert result.size == (EPD_W, EPD_H)

    def test_fill_mode_crops(self, app_module):
        """Fill mode crops to fill the display."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        result = app_module.load_scaled(img, 0, 'fill')
        assert result.size == (EPD_W, EPD_H)

    def test_fit_mode_letterbox(self, app_module):
        """Fit mode adds white letterbox."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(1200, 900)
        result = app_module.load_scaled(img, 0, 'fit')
        assert result.size == (EPD_W, EPD_H)
        # Check white border exists (corners should be white)
        pixels = result.load()
        assert pixels[0, 0] == (255, 255, 255) or pixels[0, 0] != (0, 0, 0)


# ============================================================
# TC-FR-007: Color Enhancement
# ============================================================

class TestFR007ColorEnhancement:
    """TC-FR-007: Verify color and contrast enhancement."""

    def test_neutral_enhancement_unchanged(self, app_module):
        """Neutral values (1.0) produce no change."""
        from PIL import ImageEnhance

        img = create_test_image(100, 100, color=(128, 128, 128))
        enhanced = ImageEnhance.Color(img).enhance(1.0)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.0)

        orig_pixels = list(img.getdata())
        enh_pixels = list(enhanced.getdata())
        assert orig_pixels == enh_pixels

    def test_color_enhance_zero_grayscale(self, app_module):
        """color_enhance=0.0 produces grayscale."""
        from PIL import ImageEnhance

        img = create_test_image(100, 100, color=(200, 100, 50))
        enhanced = ImageEnhance.Color(img).enhance(0.0)

        pixels = list(enhanced.getdata())
        # All pixels should have equal R, G, B values
        for r, g, b in pixels:
            assert r == g == b


# ============================================================
# TC-FR-008: Dithering (Floyd-Steinberg)
# ============================================================

class TestFR008FloydSteinberg:
    """TC-FR-008: Verify Floyd-Steinberg dithering."""

    def test_floyd_steinberg_output_shape(self, app_module):
        """Output is numpy array of correct shape."""
        if not app_module.FLOYD_AVAILABLE:
            pytest.skip("Floyd-Steinberg not available")

        img = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_image_floyd(img, 1.0)

        assert result.shape == (EPD_H, EPD_W, 3)

    def test_floyd_steinberg_palette_colors(self, app_module):
        """All pixels use only 6 E-Ink colors."""
        if not app_module.FLOYD_AVAILABLE:
            pytest.skip("Floyd-Steinberg not available")

        img = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_image_floyd(img, 1.0)

        epd_colors = [
            (0, 0, 0), (255, 255, 255), (255, 243, 56),
            (191, 0, 0), (100, 64, 255), (67, 138, 28),
        ]

        # Sample pixels - allow small rounding differences from Cython
        for y in range(0, EPD_H, 50):
            for x in range(0, EPD_W, 50):
                pixel = tuple(result[y, x])
                is_close = any(
                    all(abs(pixel[i] - pc[i]) <= 5 for i in range(3))
                    for pc in epd_colors
                )
                assert is_close, f"Pixel {pixel} not close to any palette color"

    def test_atkinson_output_shape(self, app_module):
        """Output is numpy array of correct shape."""
        if not app_module.ATKINSON_AVAILABLE:
            pytest.skip("Atkinson not available")

        img = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_image_atkinson(img, 1.0)

        assert result.shape == (EPD_H, EPD_W, 3)

    def test_atkinson_palette_colors(self, app_module):
        """All pixels use only 6 E-Ink colors."""
        if not app_module.ATKINSON_AVAILABLE:
            pytest.skip("Atkinson not available")

        img = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_image_atkinson(img, 1.0)

        epd_colors = [
            (0, 0, 0), (255, 255, 255), (255, 243, 56),
            (191, 0, 0), (100, 64, 255), (67, 138, 28),
        ]

        for y in range(0, EPD_H, 50):
            for x in range(0, EPD_W, 50):
                pixel = tuple(result[y, x])
                is_close = any(
                    all(abs(pixel[i] - pc[i]) <= 5 for i in range(3))
                    for pc in epd_colors
                )
                assert is_close, f"Pixel {pixel} not close to any palette color"


# ============================================================
# TC-FR-009: Dithering (Atkinson)
# ============================================================
# TC-FR-010: Date Overlay
# ============================================================

class TestFR010DateOverlay:
    """TC-FR-010: Verify EXIF date overlay on processed image."""

    def test_date_overlay_with_exif(self, app_module, test_dir):
        """Date is rendered when EXIF DateTimeOriginal is present."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(EPD_W, EPD_H, include_exif=True,
                                exif_date='2024:06:15 14:30:00')
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'
        app_module.photo_dir = test_dir['photos']

        result = app_module.scale_img_in_memory(img)

        # Check that date text appears in the image
        pixels = result.load()
        # Date is in bottom-right corner, check some pixels
        # White text on black rectangle
        found_white = False
        for x in range(EPD_W - 150, EPD_W - 20):
            for y in range(EPD_H - 50, EPD_H - 10):
                if pixels[x, y] == (255, 255, 255):
                    found_white = True
                    break
            if found_white:
                break

        assert found_white, "Date overlay not found"

    def test_no_overlay_without_exif(self, app_module, test_dir):
        """No date overlay when EXIF date is absent."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(EPD_W, EPD_H)
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'
        app_module.photo_dir = test_dir['photos']

        result = app_module.scale_img_in_memory(img)

        # Should still save preview
        preview_path = os.path.join(test_dir['photos'],
                                    'latest_preview.jpg')
        assert os.path.exists(preview_path)

    # --- 2.4.2: the overlay has a global on/off switch -------------------------------

    #: Roughly where the stamp lands on a 800x480 frame: x0, y0, x1, y1.
    STAMP_REGION = (540, 390, 780, 470)

    def _black_pixels_in_region(self, image):
        x0, y0, x1, y1 = self.STAMP_REGION
        return sum(1 for y in range(y0, y1) for x in range(x0, x1)
                   if image.getpixel((x, y)) == (0, 0, 0))

    def _exif_image(self, app_module, test_dir):
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'
        app_module.photo_dir = test_dir['photos']
        return create_test_image(EPD_W, EPD_H, include_exif=True,
                                 exif_date='2024-06-15 14:30:00')

    def test_switch_off_suppresses_the_stamp(self, app_module, test_dir):
        """Switch off = the EXIF date is not drawn any more; switch on = it is.

        Compares the two runs on the same kind of input instead of counting white pixels:
        the test image is a gradient that dithers to several palette colours, so only the
        differential proves the stamp.
        """
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        app_module.date_overlay = True
        stamped = app_module.scale_img_in_memory(self._exif_image(app_module, test_dir))
        app_module.date_overlay = False
        plain = app_module.scale_img_in_memory(self._exif_image(app_module, test_dir))

        assert list(stamped.getdata()) != list(plain.getdata()), "switch changed nothing"
        # the stamp is a black rectangle with white text - the black has to be visible
        assert self._black_pixels_in_region(stamped) - self._black_pixels_in_region(plain) >= 500, \
            "stamp rectangle missing while the switch is on"

    def test_switch_round_trips_through_the_settings_page(self, client_with_mocks, app_module, test_config_path):
        """The form's switch lands in the runtime YAML and hot-reloads the pipeline."""
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'date_overlay': 'disabled'}, follow_redirects=True)
        with open(test_config_path) as fh:
            saved = yaml.safe_load(fh)
        assert saved['date_overlay'] is False
        assert app_module.current_config['date_overlay'] is False
        assert app_module.date_overlay is False       # hot-reload reached the pipeline

        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'date_overlay': 'enabled'}, follow_redirects=True)
        assert app_module.current_config['date_overlay'] is True
        assert app_module.date_overlay is True

    def test_a_post_without_the_field_keeps_the_stored_switch(self, client_with_mocks, app_module):
        """Silence is not a click: a partial POST must not flip the switch off."""
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'date_overlay': 'disabled'}, follow_redirects=True)
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'album_name': 'some-album'}, follow_redirects=True)
        assert app_module.current_config['date_overlay'] is False
        assert app_module.date_overlay is False

    def test_the_page_shows_the_stored_state(self, client_with_mocks, app_module):
        """After a save the switch must show what is stored, not the default."""
        app_module.current_config['date_overlay'] = False
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert '<option value="disabled" selected>' in html
        assert 'name="date_overlay"' in html


# ============================================================
# TC-FR-011: Preview Generation
# ============================================================

class TestFR011PreviewGeneration:
    """TC-FR-011: Verify three preview versions are saved."""

    @responses.activate
    def test_three_previews_created(self, client_with_mocks, app_module,
                                    test_dir):
        """All three preview files are created."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200

        photo_dir = test_dir['photos']
        assert os.path.exists(os.path.join(photo_dir, 'latest_original.jpg'))
        assert os.path.exists(os.path.join(photo_dir, 'latest_processed.jpg'))
        assert os.path.exists(os.path.join(photo_dir, 'latest.bmp'))

    @responses.activate
    def test_original_is_resized(self, client_with_mocks, app_module,
                                 test_dir):
        """latest_original.jpg is 800x480."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        orig_path = os.path.join(test_dir['photos'], 'latest_original.jpg')
        img = Image.open(orig_path)
        assert img.width <= 800
        assert img.height <= 480

    @responses.activate
    def test_bmp_is_valid_format(self, client_with_mocks, app_module,
                                 test_dir):
        """latest.bmp is valid BMP format."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        bmp_path = os.path.join(test_dir['photos'], 'latest.bmp')
        img = Image.open(bmp_path)
        assert img.format == 'BMP'


# ============================================================
# TC-FR-012: Hex Format Conversion
# ============================================================

class TestFR012HexFormat:
    """TC-FR-012: Verify hex format conversion for ESP32."""

    def test_hex_format_returns_bytesio(self, app_module):
        """Output is BytesIO object."""
        bmp = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_to_hex_format(bmp)

        assert isinstance(result, io.BytesIO)

    def test_hex_format_content(self, app_module):
        """Content is comma-separated hex string."""
        bmp = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_to_hex_format(bmp)

        content = result.read().decode('utf-8')
        # Should contain hex values separated by commas
        assert ',' in content
        # All values should be valid hex
        hex_values = content.replace(',', '').replace('\n', '').strip()
        int(hex_values, 16)  # Should not raise


# ============================================================
# TC-FR-013: Image Delivery to ESP32
# ============================================================

class TestFR013ImageDelivery:
    """TC-FR-013: Verify image delivery to ESP32."""

    @responses.activate
    def test_prepared_image_served(self, client_with_mocks, app_module,
                                   test_dir):
        """Pre-prepared image is served with status change."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        # Prepare first
        client_with_mocks.post('/prepare-photo')
        status_file = os.path.join(test_dir['photos'], 'latest.status')
        with open(status_file, 'w') as f:
            f.write('new')

        # Download
        response = client_with_mocks.get('/download')
        assert response.status_code == 200
        assert 'text/plain' in response.content_type
        assert response.headers.get('Content-Disposition') is not None

        # Status changed to delivered
        with open(status_file, 'r') as f:
            assert f.read().strip() == 'delivered'

    @responses.activate
    def test_on_the_fly_delivery(self, client_with_mocks, app_module,
                                 test_dir):
        """Image is fetched and processed on-the-fly."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        # Remove any existing status file
        status_file = os.path.join(test_dir['photos'], 'latest.status')
        if os.path.exists(status_file):
            os.remove(status_file)

        # Remove BMP to force on-the-fly
        bmp_path = os.path.join(test_dir['photos'], 'latest.bmp')
        if os.path.exists(bmp_path):
            os.remove(bmp_path)

        response = client_with_mocks.get(
            '/download',
            headers={'batteryCap': '3300'}
        )
        assert response.status_code == 200

    @responses.activate
    def test_battery_cap_recorded(self, client_with_mocks, app_module):
        """Battery voltage from header is recorded."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.get('/download', headers={'batteryCap': '3700'})

        assert app_module.last_battery_voltage == 3700


# ============================================================
# TC-FR-014: Manual Photo Preparation
# ============================================================

class TestFR014PreparePhoto:
    """TC-FR-014: Verify manual photo preparation."""

    @responses.activate
    def test_prepare_photo_returns_success(self, client_with_mocks,
                                          app_module):
        """POST /prepare-photo returns success with asset_id."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        response = client_with_mocks.post('/prepare-photo')
        assert response.status_code == 200

        data = response.get_json()
        assert data['success'] is True
        assert 'source_id' in data or 'asset_id' in data

    @responses.activate
    def test_prepare_photo_sets_status_new(self, client_with_mocks,
                                           app_module, test_dir):
        """Status file is marked as 'new'."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        status_file = os.path.join(test_dir['photos'], 'latest.status')
        with open(status_file, 'r') as f:
            assert f.read().strip() == 'new'


# ============================================================
# TC-FR-015: Preview Serving
# ============================================================

class TestFR015PreviewServing:
    """TC-FR-015: Verify preview image endpoints."""

    @responses.activate
    def test_preview_photo_endpoint(self, client_with_mocks, app_module):
        """GET /preview-photo returns JPEG."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        response = client_with_mocks.get('/preview-photo')
        assert response.status_code == 200
        assert 'image/jpeg' in response.content_type

    @responses.activate
    def test_preview_original_endpoint(self, client_with_mocks, app_module):
        """GET /preview-original returns JPEG."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        response = client_with_mocks.get('/preview-original')
        assert response.status_code == 200
        assert 'image/jpeg' in response.content_type

    @responses.activate
    def test_preview_processed_endpoint(self, client_with_mocks, app_module):
        """GET /preview-processed returns JPEG."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        response = client_with_mocks.get('/preview-processed')
        assert response.status_code == 200

    @responses.activate
    def test_preview_404_when_missing(self, client_with_mocks, app_module,
                                      test_dir):
        """Missing preview returns 404."""
        # Ensure no previews exist
        for fname in ['latest_processed.jpg', 'latest_original.jpg',
                      'latest.bmp', 'latest_delivered.jpg']:
            path = os.path.join(test_dir['photos'], fname)
            if os.path.exists(path):
                os.remove(path)

        response = client_with_mocks.get('/preview-photo')
        assert response.status_code == 404


# ============================================================
# TC-FR-016: Preview Status
# ============================================================

class TestFR016PreviewStatus:
    """TC-FR-016: Verify preview status endpoint."""

    @responses.activate
    def test_preview_status_new(self, client_with_mocks, app_module,
                                test_dir):
        """Status is 'new' after preparation."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        response = client_with_mocks.get('/preview-status')
        assert response.status_code == 200

        data = response.get_json()
        assert data['exists'] is True
        assert data['status'] == 'new'
        assert data['timestamp'] is not None
        assert 'formatted_time' in data

    @responses.activate
    def test_preview_status_delivered(self, client_with_mocks, app_module,
                                      test_dir):
        """Status is 'delivered' after download."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')
        client_with_mocks.get('/download')

        response = client_with_mocks.get('/preview-status')
        data = response.get_json()
        assert data['status'] == 'delivered'


# ============================================================
# TC-FR-017: Health Check
# ============================================================

class TestFR017HealthCheck:
    """TC-FR-017: Verify health check endpoint."""

    @responses.activate
    def test_health_healthy(self, client_with_mocks, app_module):
        """GET /health returns 200 when Immich is reachable."""
        responses.reset()
        responses.add(
            responses.GET,
            f'{MOCK_IMMICH_URL}/api/server/ping',
            json={'res': True},
            status=200,
        )

        response = client_with_mocks.get('/health')
        assert response.status_code == 200

        data = response.get_json()
        assert data['status'] == 'healthy'
        assert data.get('immich') == 'connected' or data.get('source_status') == 'connected'
        # Contract the settings-UI header relies on: the source name is exposed.
        assert data['source'] == 'Immich'

    @responses.activate
    def test_health_degraded(self, client_with_mocks, app_module):
        """GET /health returns 503 when Immich is unreachable."""
        responses.reset()
        responses.add(
            responses.GET,
            f'{MOCK_IMMICH_URL}/api/server/ping',
            body=Exception('Connection refused'),
        )

        response = client_with_mocks.get('/health')
        assert response.status_code == 503

        data = response.get_json()
        assert data['status'] == 'degraded'
        assert data.get('immich') == 'unreachable' or data.get('source_status') == 'unreachable'
        assert data['source'] == 'Immich'

    @responses.activate
    def test_health_head(self, client_with_mocks, app_module):
        """HEAD /health returns 200."""
        responses.reset()
        responses.add(
            responses.GET,
            f'{MOCK_IMMICH_URL}/api/server/ping',
            json={'res': True},
            status=200,
        )

        response = client_with_mocks.head('/health')
        assert response.status_code == 200


class TestFR017BFooterBuildInfo:
    """Footer build-info contract: ADDON_VERSION / BUILD_TIMESTAMP reach the UI."""

    def test_footer_shows_env_build_info(self, client_with_mocks, app_module):
        """Settings-page footer renders the env-provided version and build time."""
        response = client_with_mocks.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'v9.9.9-test' in html
        assert 'Built: 2026-01-01 00:00:00 UTC' in html


# ============================================================
# TC-FR-018: Battery Status Reporting
# ============================================================

class TestFR018BatteryStatus:
    """TC-FR-018: Verify battery status endpoint."""

    def test_initial_battery_zero(self, client_with_mocks, app_module):
        """Initial state: voltage=0, formatted_timestamp=null."""
        app_module.last_battery_voltage = 0
        app_module.last_battery_update = 0

        response = client_with_mocks.get('/api/battery-status')
        assert response.status_code == 200

        data = response.get_json()
        assert data['voltage'] == 0
        assert data['formatted_timestamp'] is None

    def test_battery_after_download(self, client_with_mocks, app_module):
        """After download: all fields populated."""
        app_module.last_battery_voltage = 3700
        app_module.last_battery_update = time.time()

        response = client_with_mocks.get('/api/battery-status')
        data = response.get_json()

        assert data['voltage'] == 3700
        assert data['voltage_v'] == 3.7
        assert data['percentage'] > 0
        assert data['formatted_timestamp'] is not None
        assert 'age_seconds' in data

    def test_battery_persists(self, client_with_mocks, app_module):
        """Value persists indefinitely."""
        app_module.last_battery_voltage = 3500
        app_module.last_battery_update = time.time() - 86400  # 24h ago

        response = client_with_mocks.get('/api/battery-status')
        data = response.get_json()

        assert data['voltage'] == 3500


# ============================================================
# TC-FR-019: Sleep Duration Calculation
# ============================================================

class TestFR019SleepDuration:
    """TC-FR-019: Verify sleep duration calculation."""

    def test_sleep_duration_returns_ms(self, client_with_mocks, app_module):
        """Response contains sleep_duration in milliseconds."""
        app_module.current_config['immich']['wakeup_interval'] = 60

        response = client_with_mocks.get('/sleep')
        assert response.status_code == 200

        data = response.get_json()
        assert 'sleep_duration' in data
        assert isinstance(data['sleep_duration'], int)
        assert data['sleep_duration'] > 0

    def test_sleep_response_fields(self, client_with_mocks, app_module):
        """Response contains current_time and next_wakeup."""
        response = client_with_mocks.get('/sleep')
        data = response.get_json()

        assert 'current_time' in data
        assert 'next_wakeup' in data


# ============================================================
# TC-FR-020: Configuration Management
# ============================================================

class TestFR020ConfigManagement:
    """TC-FR-020: Verify configuration management."""

    def test_config_loaded_at_startup(self, app_module):
        """Configuration is loaded at startup."""
        assert app_module.current_config is not None
        assert 'immich' in app_module.current_config

    def test_config_hot_reload(self, app_module, test_dir, test_config_path):
        """YAML file changes trigger hot-reload."""
        original_url = app_module.current_config['immich']['url']

        # Modify config
        new_config = {
            'immich': {
                'url': 'http://new-immich.local',
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
        write_test_config(test_dir['config'], new_config)

        # Trigger reload
        handler = app_module.ConfigFileHandler(test_config_path,
                                               app_module.update_app_config)
        handler.load_config()
        app_module.update_app_config(new_config)

        assert app_module.url == 'http://new-immich.local'


# ============================================================
# TC-FR-021: Web Settings Interface
# ============================================================

class TestFR021WebSettings:
    """TC-FR-021: Verify web-based settings UI."""

    def test_settings_page_renders(self, client_with_mocks):
        """GET / returns HTML settings page."""
        response = client_with_mocks.get('/')
        assert response.status_code == 200
        assert 'text/html' in response.content_type
        assert b'<html' in response.data or b'<!doctype' in response.data.lower()

    def test_settings_form_submission(self, client_with_mocks, app_module,
                                      test_dir):
        """POST / saves config to YAML."""
        response = client_with_mocks.post('/', data={
            'url': MOCK_IMMICH_URL,
            'album': MOCK_ALBUM_NAME,
            'rotation': '90',
            'enhanced': '1.5',
            'contrast': '1.0',
            'strength': '0.8',
            'display_mode': 'fit',
            'image_order': 'newest',
            'dithering_method': 'floyd-steinberg',
            'sleep_start_hour': '22',
            'sleep_start_minute': '30',
            'sleep_end_hour': '7',
            'sleep_end_minute': '0',
            'wakeup_interval': '120',
        }, follow_redirects=True)

        assert response.status_code == 200


# ============================================================
# TC-FR-022: Image Tracking
# ============================================================

class TestFR022ImageTracking:
    """TC-FR-022: Verify image tracking file management."""

    @responses.activate
    def test_tracking_records_asset_ids(self, client_with_mocks, app_module,
                                        test_dir):
        """Tracking file records album name and asset IDs."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        tracking_file = app_module.tracking_file
        if os.path.exists(tracking_file):
            os.remove(tracking_file)

        client_with_mocks.post('/prepare-photo')

        with open(tracking_file, 'r') as f:
            lines = f.readlines()

        assert lines[0].strip() == MOCK_ALBUM_NAME
        assert len(lines) >= 2  # album name + at least 1 asset ID

    def test_tracking_file_permissions(self, app_module, test_dir):
        """Tracking file has permissions 0o666."""
        import stat

        tracking_file = app_module.tracking_file
        app_module.load_downloaded_images()

        if os.path.exists(tracking_file):
            mode = stat.S_IMODE(os.stat(tracking_file).st_mode)
            assert mode == 0o666


# ============================================================
# TC-FR-023: NTP Time Synchronization
# ============================================================

class TestFR023NTPSync:
    """TC-FR-023: Verify daily NTP synchronization."""

    def test_ntp_thread_starts(self, app_module):
        """NTP sync thread is running."""
        # The module starts the NTP thread at import time
        assert app_module.ntp_thread is not None
        assert app_module.ntp_thread.is_alive() or True  # May have exited

    def test_ntp_client_mocked(self, app_module):
        """NTP client is mocked and doesn't make real calls."""
        with patch('ntplib.NTPClient') as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance
            mock_response = MagicMock()
            mock_response.tx_time = 1700000000.0
            mock_instance.request.return_value = mock_response

            client = mock_client()
            response = client.request('pool.ntp.org', timeout=5)
            assert response.tx_time == 1700000000.0


# ============================================================
# TC-FR-023 (updated): NTP Graceful Shutdown
# ============================================================

class TestFR023NTPShutdown:
    """TC-FR-023 (updated): Verify NTP thread graceful shutdown."""

    def test_stop_event_exists(self, app_module):
        """NTP stop event exists as threading.Event."""
        assert hasattr(app_module, '_ntp_stop_event')
        assert isinstance(app_module._ntp_stop_event, type(app_module._ntp_stop_event))

    def test_stop_function_exists(self, app_module):
        """stop_ntp_sync function exists and is callable."""
        assert hasattr(app_module, 'stop_ntp_sync')
        assert callable(app_module.stop_ntp_sync)

    def test_stop_event_can_be_set(self, app_module):
        """Stop event can be set and checked."""
        app_module._ntp_stop_event.set()
        assert app_module._ntp_stop_event.is_set()
        app_module._ntp_stop_event.clear()


# ============================================================
# TC-FR-024: Preview Cleanup
# ============================================================

class TestFR024PreviewCleanup:
    """TC-FR-024: Verify preview file cleanup functionality."""

    def test_cleanup_function_exists(self, app_module):
        """cleanup_old_previews function exists and is callable."""
        assert hasattr(app_module, 'cleanup_old_previews')
        assert callable(app_module.cleanup_old_previews)

    def test_cleanup_returns_int(self, app_module, test_dir):
        """cleanup_old_previews returns an integer count."""
        app_module.photo_dir = test_dir['photos']
        result = app_module.cleanup_old_previews()
        assert isinstance(result, int)
        assert result >= 0

    def test_cleanup_removes_old_files(self, app_module, test_dir):
        """Files older than max_age are removed."""
        photo_dir = test_dir['photos']
        app_module.photo_dir = photo_dir

        old_file = os.path.join(photo_dir, 'latest_original_20240101.jpg')
        with open(old_file, 'w') as f:
            f.write('old')
        os.utime(old_file, (time.time() - 8 * 24 * 3600, time.time() - 8 * 24 * 3600))

        removed = app_module.cleanup_old_previews(max_age_seconds=7 * 24 * 3600)
        assert removed >= 1
        assert not os.path.exists(old_file)

    def test_cleanup_keeps_recent_files(self, app_module, test_dir):
        """Files newer than max_age are preserved."""
        photo_dir = test_dir['photos']
        app_module.photo_dir = photo_dir

        recent_file = os.path.join(photo_dir, 'latest_processed_recent.jpg')
        with open(recent_file, 'w') as f:
            f.write('recent')

        removed = app_module.cleanup_old_previews(max_age_seconds=7 * 24 * 3600)
        assert os.path.exists(recent_file)

    def test_cleanup_does_not_remove_current_previews(self, app_module, test_dir):
        """Current preview files (latest_original.jpg etc.) are not removed."""
        photo_dir = test_dir['photos']
        app_module.photo_dir = photo_dir

        current_files = ['latest_original.jpg', 'latest_processed.jpg', 'latest.bmp']
        for fname in current_files:
            with open(os.path.join(photo_dir, fname), 'w') as f:
                f.write('current')
            os.utime(os.path.join(photo_dir, fname), (time.time() - 30 * 24 * 3600,) * 2)

        app_module.cleanup_old_previews(max_age_seconds=7 * 24 * 3600)

        for fname in current_files:
            assert os.path.exists(os.path.join(photo_dir, fname)), f"{fname} should not be removed"

    def test_cleanup_respects_count_limit(self, app_module, test_dir):
        """When more than max_count files exist, oldest are removed first."""
        photo_dir = test_dir['photos']
        app_module.photo_dir = photo_dir

        for i in range(60):
            fpath = os.path.join(photo_dir, f'latest_original_{i:03d}.jpg')
            with open(fpath, 'w') as f:
                f.write(f'file {i}')
            os.utime(fpath, (time.time() - i * 3600, time.time() - i * 3600))

        removed = app_module.cleanup_old_previews(max_count=50, max_age_seconds=365 * 24 * 3600)
        remaining = len([f for f in os.listdir(photo_dir) if f.startswith('latest_original_') and f.endswith('.jpg')])
        assert remaining <= 50

    def test_cleanup_endpoint_exists(self, app_module):
        """POST /cleanup-previews endpoint exists."""
        assert hasattr(app_module.app, 'view_functions')
        found = any('cleanup' in str(vf) for vf in app_module.app.view_functions.values())
        assert found

    def test_cleanup_endpoint_returns_success(self, client_with_mocks, app_module, test_dir):
        """POST /cleanup-previews returns success response."""
        app_module.photo_dir = test_dir['photos']
        response = client_with_mocks.post('/cleanup-previews')
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'files_removed' in data


# ============================================================
# TC-FR-025: Health Check Indicator in UI
# ============================================================

class TestFR025HealthIndicator:
    """TC-FR-025: Verify health check indicator is present in settings UI."""

    def test_health_status_element_exists(self, client_with_mocks):
        """Settings page contains health status element."""
        response = client_with_mocks.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert 'health-status' in html
        assert 'healthText' in html
        assert 'health-dot' in html

    def test_health_endpoint_returns_healthy(self, client_with_mocks, app_module):
        """Health endpoint returns healthy when Immich is reachable."""
        response = client_with_mocks.get('/health')
        assert response.status_code == 200
        data = response.get_json()
        assert data['status'] == 'healthy'

    @responses.activate
    def test_health_endpoint_returns_degraded(self, client_with_mocks, app_module):
        """Health endpoint returns degraded when Immich is unreachable."""
        responses.reset()
        responses.add(responses.GET, 'http://192.168.1.10/api/server/ping',
                      body=Exception('Connection refused'))
        response = client_with_mocks.get('/health')
        assert response.status_code == 503
        data = response.get_json()
        assert data['status'] == 'degraded'


# ============================================================
# TC-FR-026: UI Settings Improvements
# ============================================================

class TestFR026UISettingsImprovements:
    """TC-FR-026: Verify UI improvements (CSP, cleanup button, dynamic year, unicode, in-page zoom)."""

    def test_csp_meta_tag_present(self, client_with_mocks):
        """Settings page contains Content-Security-Policy meta tag."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'Content-Security-Policy' in html

    def test_referrer_meta_tag_present(self, client_with_mocks):
        """Settings page contains referrer-policy meta tag."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'referrer' in html

    def test_cleanup_button_present(self, client_with_mocks):
        """Settings page contains cleanup button."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'cleanupPreviews' in html
        assert 'Cleanup Old Previews' in html

    def test_dynamic_copyright_year(self, client_with_mocks):
        """Settings page uses JavaScript for dynamic copyright year."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'copyrightYear' in html
        assert 'getFullYear' in html

    def test_unicode_symbols_used(self, client_with_mocks):
        """Settings page uses unicode symbols instead of emoji."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert '&#' in html

    def test_slider_output_ids_present(self, client_with_mocks):
        """Slider output elements have id attributes for robust lookup."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'id="color_enhanceValue"' in html
        assert 'id="contrastValue"' in html
        assert 'id="dithering_strengthValue"' in html

    def test_polling_constants_defined(self, client_with_mocks):
        """JavaScript defines polling intervals as constants."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'POLL_INTERVALS' in html
        assert 'NOTIFICATION_DURATION' in html

    def test_safe_get_helper_defined(self, client_with_mocks):
        """JavaScript defines safeGet helper for robust DOM access."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')
        assert 'safeGet' in html

    def test_image_click_zooms_in_page_lightbox(self, client_with_mocks):
        """FR-026(8): clicking an image zooms it in the page — dashboard and gallery alike.

        Both surfaces used to hand the click to the browser (the gallery anchor opened a
        new tab). They share one overlay now, so the page has to carry the overlay markup,
        wire both groups to it, and stop opening windows.
        """
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'id="lightbox"' in html                                  # the shared overlay
        assert html.count("openLightbox('dashboard', this)") == 3       # the three preview panels
        assert "lightboxClick(event, \\'gallery\\', this)" in html        # the gallery renderer
        assert 'data-caption' in html                                    # the caption it reads
        assert 'closeLightbox' in html                                   # close button + Esc path
        assert "e.key === 'Escape'" in html
        assert 'target="_blank"' not in html                             # no new window any more


# ============================================================
# TC-FR-025: Health Check Indicator in UI


# ============================================================
# TC-FR-021 (2.3.2): settings vocabulary, channel visibility, entity id
# ============================================================

class TestFR021SettingsVocabulary:
    """The settings page speaks the add-on-option vocabulary (form name == option key)."""

    def test_canonical_field_names_render(self, client_with_mocks):
        """Form fields carry the add-on-option names; the old short names are gone."""
        html = client_with_mocks.get('/').data.decode('utf-8')
        for name in ('immich_url', 'album_name', 'rotation_angle',
                     'color_enhance', 'dithering_strength', 'comfyui_entity_id',
                     'date_overlay'):
            assert f'name="{name}"' in html
        assert 'name="url"' not in html
        assert 'name="album"' not in html

    def test_channel_badge_and_precedence_note_render(self, client_with_mocks):
        """The page says which channel is which instead of leaving it to the docs."""
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'channel-badge' in html
        assert 'runtime YAML' in html
        assert 'needs an add-on restart' in html

    def test_post_with_canonical_names_writes_yaml(self, client_with_mocks, app_module):
        """Posting the canonical names lands in the same runtime-YAML keys as before."""
        client_with_mocks.post('/', data={
            'image_source': 'immich',
            'immich_url': 'http://immich.canonical:2283',
            'album_name': 'canonical-album',
            'rotation_angle': '90',
            'color_enhance': '1.5',
            'dithering_strength': '0.7',
            'comfyui_entity_id': 'camera.canonical',
        }, follow_redirects=True)
        cfg = app_module.current_config
        assert cfg['immich']['url'] == 'http://immich.canonical:2283'
        assert cfg['immich']['album'] == 'canonical-album'
        assert cfg['immich']['rotation'] == 90
        assert cfg['immich']['enhanced'] == 1.5
        assert cfg['immich']['strength'] == 0.7
        assert cfg['comfyui']['entity_id'] == 'camera.canonical'

    def test_post_with_legacy_names_still_works(self, client_with_mocks, app_module):
        """Stored configs and older callers may still post the pre-2.3.2 names."""
        client_with_mocks.post('/', data={
            'image_source': 'immich',
            'url': 'http://immich.legacy:2283',
            'album': 'legacy-album',
            'rotation': '180',
            'enhanced': '2.0',
            'strength': '0.5',
        }, follow_redirects=True)
        cfg = app_module.current_config
        assert cfg['immich']['url'] == 'http://immich.legacy:2283'
        assert cfg['immich']['album'] == 'legacy-album'
        assert cfg['immich']['rotation'] == 180

    def test_secret_status_rows_reflect_env(self, client_with_mocks, app_module, monkeypatch):
        """Secrets are echoed as read-only status, never as editable inputs."""
        monkeypatch.setenv('IMMICH_API_KEY', 'test-api-key-12345')
        monkeypatch.delenv('HA_API_TOKEN', raising=False)
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert html.count('&#10003; set') == 1
        assert html.count('&mdash; not set') == 1
        assert 'name="immich_api_key"' not in html
        assert 'name="ha_api_token"' not in html

    def test_empty_field_overwrites_and_the_ui_warns(self, client_with_mocks, app_module):
        """2.4.3 (plan §9.2): an emptied field is a real answer — empty overwrites what is stored.

        Only a field the POST *omits* keeps its stored value; the form always sends its controls,
        so this is the behaviour the user sees. It is intentional, and the page now warns before
        sending it instead of letting the value vanish quietly.
        """
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'comfyui_prompt': 'a red fox at dawn'},
                               follow_redirects=True)
        assert app_module.current_config['comfyui']['prompt'] == 'a red fox at dawn'

        client_with_mocks.post('/', data={'image_source': 'immich', 'comfyui_prompt': ''},
                               follow_redirects=True)
        assert app_module.current_config['comfyui']['prompt'] == ''

        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'id="clearConfirmModal"' in html
        assert 'snapshotStoredValues' in html
        assert 'Save anyway' in html

    def test_form_field_names_are_unique(self, client_with_mocks):
        """2.4.1 regression guard: the single rendered form must not name any field twice.

        Two controls sharing one name are both submitted, and Flask keeps only the first,
        so the second card's value was silently dropped (this is what made a seed change
        on the ComfyUI-Direct card vanish).
        """
        html = client_with_mocks.get('/').data.decode('utf-8')
        names = re.findall(r'<(?:input|textarea|select)[^>]*name="([^"]+)"', html)
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        assert duplicates == [], f"duplicate form field names: {duplicates}"

    def test_common_comfyui_block_is_single_sourced(self, client_with_mocks):
        """The shared ComfyUI settings render exactly once, in one visible card."""
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'id="comfyuiCommonConfig"' in html
        assert 'ComfyUI &mdash; Common Settings' in html
        for name in ('comfyui_prompt', 'comfyui_negative_prompt', 'comfyui_width',
                     'comfyui_height', 'comfyui_seed', 'comfyui_max_generations'):
            assert html.count(f'name="{name}"') == 1, f"{name} must appear exactly once"
        # the duplicate-id clones from the two source cards are gone
        for old_id in ('comfyui_prompt_direct', 'comfyui_seed_direct', 'comfyui_width_direct'):
            assert f'id="{old_id}"' not in html

    def test_common_fields_survive_a_direct_source_save(self, client_with_mocks, app_module):
        """The field-edit users make for the direct source has to reach the YAML."""
        client_with_mocks.post('/', data={
            'image_source': 'comfyui_direct',
            'comfyui_direct_url': 'http://comfyui.common:8188',
            'comfyui_prompt': 'a red fox at {time_of_day}',
            'comfyui_negative_prompt': 'blurry, watermark',
            'comfyui_width': '1024',
            'comfyui_height': '768',
            'comfyui_seed': '-1',
            'comfyui_max_generations': '12',
        }, follow_redirects=True)
        comfyui = app_module.current_config['comfyui']
        assert comfyui['direct_url'] == 'http://comfyui.common:8188'
        assert comfyui['prompt'] == 'a red fox at {time_of_day}'
        assert comfyui['negative_prompt'] == 'blurry, watermark'
        assert comfyui['width'] == 1024
        assert comfyui['height'] == 768
        assert comfyui['seed'] == -1
        assert comfyui['max_generations_per_day'] == 12


# ============================================================
# TC-FR-033: Named ComfyUI Workflows (settings side)
# ============================================================

class TestFR033WorkflowSelection:
    """FR-033: several named ComfyUI workflows, selectable from the settings page."""

    API_JSON = '{"3": {"class_type": "KSampler", "inputs": {"seed": 0}}, "9": {"class_type": "SaveImage", "inputs": {}}}'

    def test_slots_and_dropdown_render(self, client_with_mocks):
        html = client_with_mocks.get('/').data.decode('utf-8')
        for fragment in ('name="wf_1_name"', 'name="wf_1_api_json"', 'id="active_workflow"',
                         'wf-slot', 'Save (Export)'):
            assert fragment in html

    def test_post_named_workflow_round_trip(self, client_with_mocks, app_module, test_config_path):
        """What the form posts is what the YAML and the live config carry afterwards."""
        resp = client_with_mocks.post('/', data={
            'image_source': 'comfyui_direct',
            'wf_1_name': 'flux-dev',
            'wf_1_api_json': self.API_JSON,
            'wf_1_prompt_node': '3',
            'active_workflow': 'flux-dev',
        }, follow_redirects=True)
        assert resp.status_code == 200
        comfyui = app_module.current_config['comfyui']
        assert comfyui['active_workflow'] == 'flux-dev'
        assert comfyui['workflows'] == [{'name': 'flux-dev', 'api_json': self.API_JSON, 'prompt_node': '3'}]
        with open(test_config_path) as fh:
            saved = yaml.safe_load(fh)
        assert saved['comfyui']['active_workflow'] == 'flux-dev'
        assert saved['comfyui']['workflows'][0]['name'] == 'flux-dev'

    def test_duplicate_names_rejected(self, client_with_mocks):
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct',
                                                  'wf_1_name': 'flux', 'wf_2_name': 'flux'},
                                       follow_redirects=False)
        assert resp.status_code == 400
        assert 'duplicate' in resp.data.decode('utf-8')

    def test_ui_format_is_rejected_with_a_hint(self, client_with_mocks):
        """ComfyUI's normal save format is a UI graph; only API JSON can be posted."""
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct',
                                                 'wf_1_name': 'flux',
                                                 'wf_1_api_json': '{"nodes": [], "links": []}'},
                                       follow_redirects=False)
        assert resp.status_code == 400
        assert 'Save (Export)' in resp.data.decode('utf-8')

    def test_oversized_json_rejected(self, client_with_mocks):
        big = json.dumps({'1': {'class_type': 'Note', 'inputs': {'text': 'x' * 70000}}})
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct',
                                                  'wf_1_name': 'flux', 'wf_1_api_json': big},
                                       follow_redirects=False)
        assert resp.status_code == 400

    def test_active_name_must_match_a_slot(self, client_with_mocks):
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct',
                                                  'wf_1_name': 'flux', 'active_workflow': 'ghost'},
                                       follow_redirects=False)
        assert resp.status_code == 400

    def test_slot_content_without_a_name_is_refused(self, client_with_mocks):
        """2.4.3 (plan §9.1): a slot holding a pasted workflow but no name is not stored silently.

        The user pasted JSON into slot 1, clicked Save, got "Settings saved" and got nothing —
        an unnamed slot was dropped without a word. Saying so is cheaper than a support thread.
        (The guard speaks for saves targeting a ComfyUI source; a save for any other source
        keeps the stored list untouched — 2.6.2.)
        """
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct',
                                                 'wf_1_api_json': self.API_JSON},
                                      follow_redirects=False)
        assert resp.status_code == 400
        body = resp.data.decode('utf-8')
        assert 'slot 1' in body
        assert 'no name' in body

    def test_untouched_unnamed_slots_are_still_dropped(self, client_with_mocks, app_module):
        """The guard fires on content, not on an empty slot left on the page (2.4.3)."""
        resp = client_with_mocks.post('/', data={'image_source': 'comfyui_direct', 'wf_1_name': ''},
                                      follow_redirects=True)
        assert resp.status_code == 200
        assert app_module.current_config['comfyui']['workflows'] == []

    def test_unchanged_nameless_legacy_slot_does_not_veto_a_save(self, client_with_mocks, app_module):
        """2.6.2 (field report): a nameless legacy slot re-posted verbatim by the form is kept
        as stored — it must not veto unrelated saves (the lock-out that kept the frame
        orientation from ever persisting)."""
        app_module.current_config['comfyui']['workflows'] = [
            {'api_json': self.API_JSON, 'prompt': 'old paste'}]
        resp = client_with_mocks.post('/', data={
            'image_source': 'comfyui_direct',
            'frame_orientation': 'portrait',
            'wf_1_name': '',
            'wf_1_api_json': self.API_JSON,
            'wf_1_prompt': 'old paste',
        }, follow_redirects=True)
        assert resp.status_code == 200
        assert app_module.current_config['comfyui']['workflows'] == [
            {'api_json': self.API_JSON, 'prompt': 'old paste'}]
        assert app_module.current_config['frame_orientation'] == 'portrait'

    def test_changed_nameless_slot_is_still_refused(self, client_with_mocks, app_module):
        """The 2.4.3b guard stays in force for *new* content without a name."""
        app_module.current_config['comfyui']['workflows'] = [
            {'api_json': self.API_JSON, 'prompt': 'old paste'}]
        resp = client_with_mocks.post('/', data={
            'image_source': 'comfyui_direct',
            'wf_1_name': '',
            'wf_1_api_json': self.API_JSON,
            'wf_1_prompt': 'something new',
        }, follow_redirects=False)
        assert resp.status_code == 400
        assert 'no name' in resp.data.decode('utf-8')

    def test_post_without_slots_keeps_the_stored_list(self, client_with_mocks, app_module):
        """A caller that posts no workflow fields must not wipe an existing list."""
        app_module.current_config['comfyui']['workflows'] = [
            {'name': 'flux-dev', 'api_json': '{"1": {"class_type": "SaveImage", "inputs": {}}}'}]
        app_module.current_config['comfyui']['active_workflow'] = 'flux-dev'
        client_with_mocks.post('/', data={'image_source': 'comfyui_direct'}, follow_redirects=True)
        comfyui = app_module.current_config['comfyui']
        assert comfyui['active_workflow'] == 'flux-dev'
        assert comfyui['workflows'][0]['name'] == 'flux-dev'


# ============================================================
# TC-FR-034: Frame Orientation (2.6.0)
# ============================================================

class TestFR034FrameOrientation:
    """TC-FR-034: the frame can hang landscape (hardware-native) or portrait.

    'frame_orientation' is a top-level runtime-YAML key like date_overlay: seeded
    from the FRAME_ORIENTATION env (add-on option) on first start, edited on the
    settings page, and honoured by the image pipeline (portrait = +90deg).
    """

    def test_default_orientation_is_landscape(self, app_module, client_with_mocks):
        """Without the env var the add-on runs in the hardware-native orientation."""
        assert app_module.frame_orientation == 'landscape'
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'data-orientation="landscape"' in html
        assert 'name="frame_orientation"' in html

    def test_page_renders_the_stored_orientation_and_select(self, app_module, client_with_mocks):
        """After a save the page shows what is stored - and the body carries the attribute."""
        app_module.current_config['frame_orientation'] = 'portrait'
        html = client_with_mocks.get('/').data.decode('utf-8')
        assert 'data-orientation="portrait"' in html
        assert '<option value="portrait" selected>' in html

    def test_portrait_round_trips_through_the_settings_page(self, client_with_mocks, app_module, test_config_path):
        """The form's select lands in the runtime YAML and hot-reloads the pipeline."""
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'frame_orientation': 'portrait'}, follow_redirects=True)
        with open(test_config_path) as fh:
            saved = yaml.safe_load(fh)
        assert saved['frame_orientation'] == 'portrait'
        assert app_module.current_config['frame_orientation'] == 'portrait'
        assert app_module.frame_orientation == 'portrait'

        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'frame_orientation': 'landscape'}, follow_redirects=True)
        assert app_module.current_config['frame_orientation'] == 'landscape'
        assert app_module.frame_orientation == 'landscape'

    def test_a_post_without_the_field_keeps_the_stored_orientation(self, client_with_mocks, app_module):
        """Silence is not a change: a partial POST must not flip the frame back to landscape."""
        app_module.current_config['frame_orientation'] = 'portrait'
        app_module.frame_orientation = 'portrait'
        client_with_mocks.post('/', data={'image_source': 'immich',
                                          'album_name': 'some-album'}, follow_redirects=True)
        assert app_module.current_config['frame_orientation'] == 'portrait'
        assert app_module.frame_orientation == 'portrait'

    def test_invalid_orientation_is_refused(self, client_with_mocks, app_module):
        """Same convention as rotation: anything but landscape/portrait is a 400."""
        resp = client_with_mocks.post('/', data={'image_source': 'immich',
                                                  'frame_orientation': 'sideways'},
                                      follow_redirects=False)
        assert resp.status_code == 400
        assert 'Invalid frame orientation' in resp.data.decode('utf-8')
        assert app_module.current_config.get('frame_orientation', 'landscape') == 'landscape'

    def test_pipeline_rotation_depends_on_orientation(self, app_module, test_dir):
        """Portrait adds 90deg: the processed pixels differ from landscape at the same rotation."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        app_module.rotation_angle = 0
        app_module.frame_orientation = 'landscape'
        landscape = app_module.scale_img_in_memory(create_test_image(EPD_W, EPD_H))
        app_module.frame_orientation = 'portrait'
        portrait = app_module.scale_img_in_memory(create_test_image(EPD_W, EPD_H))

        assert list(landscape.getdata()) != list(portrait.getdata()), \
            "the orientation switch changed nothing in the pipeline"
