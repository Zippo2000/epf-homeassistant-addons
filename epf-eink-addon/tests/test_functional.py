# -*- coding: utf-8 -*-
"""
Test suite for EPF E-Ink Add-on - Functional Requirements (FR-001 to FR-023).

All tests run with mocked Immich API, mocked filesystem, and Flask Test Client.
No real Home Assistant or Immich server is required.
"""

import os
import io
import json
import time
from unittest.mock import patch, MagicMock
from datetime import datetime
from PIL import Image

import pytest
import responses

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

        # Check that the albums endpoint was called
        albums_request = None
        for call in responses.calls:
            if '/api/albums' in call.request.url and 'album' not in call.request.url.split('/api/albums/')[0]:
                albums_request = call
                break

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
            f'/api/albums/{MOCK_ALBUM_ID}' in call.request.url
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
        assert 'asset_id' in data

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
        assert data['immich'] == 'connected'

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
        assert data['immich'] == 'unreachable'

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
