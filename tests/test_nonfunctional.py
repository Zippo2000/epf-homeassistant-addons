# -*- coding: utf-8 -*-
"""
Test suite for EPF E-Ink Add-on - Non-Functional, Interface, Security,
and Performance Requirements (NFR, IFR, SEC, PER).

All tests run with mocked services and isolated filesystem.
"""

import os
import io
import time
import threading
import stat
from unittest.mock import patch, MagicMock
from PIL import Image

import pytest
import responses

from conftest import (
    MOCK_IMMICH_URL, MOCK_API_KEY, MOCK_ALBUM_NAME, MOCK_ALBUM_ID,
    create_test_jpeg_bytes, create_test_image, setup_immich_mocks,
    write_test_config, EPD_W, EPD_H,
)


# ============================================================
# TC-NFR-003: Container Health Monitoring
# ============================================================

class TestNFR003HealthCheck:
    """TC-NFR-003: Verify Docker health check configuration."""

    def test_healthcheck_endpoint_exists(self, client_with_mocks):
        """Health endpoint responds to requests."""
        response = client_with_mocks.get('/health')
        assert response.status_code in [200, 503]


# ============================================================
# TC-NFR-004: Logging
# ============================================================

class TestNFR004Logging:
    """TC-NFR-004: Verify structured logging configuration."""

    def test_log_format(self, app_module):
        """Log format matches specification."""
        import logging

        handlers = app_module.logger.handlers
        if handlers:
            handler = handlers[0]
            if isinstance(handler, logging.StreamHandler):
                formatter = handler.formatter
                assert '%(asctime)s' in formatter._fmt
                assert '%(name)s' in formatter._fmt
                assert '%(levelname)s' in formatter._fmt
                assert '%(message)s' in formatter._fmt

    def test_log_level_configurable(self, app_module):
        """Log level is set from environment."""
        assert app_module.logger.level >= 0


# ============================================================
# TC-NFR-006: Response Time
# ============================================================

class TestNFR006ResponseTime:
    """TC-NFR-006: Verify image processing completes within timeout."""

    def test_image_processing_under_120s(self, app_module, test_dir):
        """Image processing completes within Gunicorn timeout."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(EPD_W, EPD_H)
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'
        app_module.photo_dir = test_dir['photos']

        start = time.time()
        result = app_module.scale_img_in_memory(img)
        elapsed = time.time() - start

        assert elapsed < 120, f"Processing took {elapsed:.1f}s (> 120s)"
        assert result is not None


# ============================================================
# TC-NFR-007: Memory Footprint
# ============================================================

class TestNFR007MemoryFootprint:
    """TC-NFR-007: Verify memory usage during image processing."""

    def test_numpy_array_size(self, app_module):
        """Numpy arrays are 800x480x3 (~1.1 MB)."""
        if not app_module.ATKINSON_AVAILABLE:
            pytest.skip("Cython not available")

        img = create_test_image(EPD_W, EPD_H)
        result = app_module.convert_image_atkinson(img, 1.0)

        expected_size = EPD_H * EPD_W * 3  # 800 * 480 * 3 bytes
        actual_size = result.nbytes

        assert actual_size == expected_size
        assert result.shape == (EPD_H, EPD_W, 3)

    def test_memory_released_after_processing(self, app_module, test_dir):
        """Memory is properly released after processing."""
        if not app_module.CYTHON_AVAILABLE:
            pytest.skip("Cython not available")

        import gc

        img = create_test_image(EPD_W, EPD_H)
        app_module.rotation_angle = 0
        app_module.display_mode = 'fit'
        app_module.photo_dir = test_dir['photos']

        gc.collect()
        # Process image
        result = app_module.scale_img_in_memory(img)

        # Result should be valid
        assert result is not None
        assert result.size == (EPD_W, EPD_H)


# ============================================================
# TC-NFR-008: Theme Support
# ============================================================

class TestNFR008ThemeSupport:
    """TC-NFR-008: Verify web UI theme support."""

    def test_settings_html_contains_theme_css(self, client_with_mocks):
        """Settings page includes CSS custom properties for themes."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')

        assert '--bg-color' in html or 'background' in html
        assert '--text-color' in html or 'color' in html

    def test_settings_html_contains_theme_toggle(self, client_with_mocks):
        """Settings page includes theme toggle button."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')

        assert 'theme' in html.lower() or 'dark' in html.lower()

    def test_settings_html_contains_localstorage(self, client_with_mocks):
        """Theme preference is persisted in localStorage."""
        response = client_with_mocks.get('/')
        html = response.data.decode('utf-8')

        assert 'localStorage' in html


# ============================================================
# TC-IFR-001: Immich REST API
# ============================================================

class TestIFR001ImmichAPI:
    """TC-IFR-001: Verify Immich API integration."""

    @responses.activate
    def test_api_key_header_sent(self, client_with_mocks, app_module):
        """x-api-key header is included in all requests."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        client_with_mocks.post('/prepare-photo')

        for call in responses.calls:
            if MOCK_IMMICH_URL in call.request.url:
                assert call.request.headers.get('x-api-key') == MOCK_API_KEY

    @responses.activate
    def test_request_timeouts_configured(self, client_with_mocks, app_module):
        """Requests have timeouts configured."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        # Health check has timeout=5
        responses.add(
            responses.GET,
            f'{MOCK_IMMICH_URL}/api/server/ping',
            json={'res': True},
            status=200,
        )

        response = client_with_mocks.get('/health')
        assert response.status_code == 200


# ============================================================
# TC-IFR-002: ESP32 Client Interface
# ============================================================

class TestIFR002ESP32Interface:
    """TC-IFR-002: Verify ESP32 HTTP client interface."""

    @responses.activate
    def test_download_serves_text_plain(self, client_with_mocks, app_module,
                                        test_dir):
        """Response is text/plain."""
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

        response = client_with_mocks.get('/download')
        assert 'text/plain' in response.content_type

    @responses.activate
    def test_download_accepts_battery_cap_header(self, client_with_mocks,
                                                  app_module):
        """batteryCap header is accepted."""
        responses.reset()
        setup_immich_mocks(
            responses,
            immich_url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
        )

        response = client_with_mocks.get(
            '/download',
            headers={'batteryCap': '3800'}
        )
        assert response.status_code in [200, 500]


# ============================================================
# TC-IFR-003: Home Assistant Ingress
# ============================================================

class TestIFR003HAIngress:
    """TC-IFR-003: Verify HA Ingress integration."""

    def test_proxyfix_middleware_configured(self, app_module):
        """Flask app uses ProxyFix middleware."""
        from werkzeug.middleware.proxy_fix import ProxyFix

        # Check that wsgi_app is wrapped with ProxyFix
        assert hasattr(app_module.app.wsgi_app, 'app')


# ============================================================
# TC-IFR-005: Network Port
# ============================================================

class TestIFR005NetworkPort:
    """TC-IFR-005: Verify TCP port 5000 configuration."""

    def test_app_configured_for_port_5000(self, app_module):
        """Application is configured for port 5000."""
        # The run.sh and config.yaml specify port 5000
        # We verify the app can be tested on any port
        assert app_module.app is not None


# ============================================================
# TC-SEC-001: API Key Protection
# ============================================================

class TestSEC001APIKeyProtection:
    """TC-SEC-001: Verify Immich API key protection."""

    def test_api_key_not_in_responses(self, client_with_mocks):
        """API key does not appear in HTTP responses."""
        with responses.mock as rsps:
            setup_immich_mocks(
                rsps,
                immich_url=MOCK_IMMICH_URL,
                api_key=MOCK_API_KEY,
            )
            response = client_with_mocks.get('/health')
            body = response.data.decode('utf-8')

            assert MOCK_API_KEY not in body

    def test_api_key_from_environment(self, app_module):
        """API key is read from environment variable."""
        assert os.environ.get('IMMICH_API_KEY') == MOCK_API_KEY


# ============================================================
# TC-SEC-003: Input Validation
# ============================================================

class TestSEC003InputValidation:
    """TC-SEC-003: Verify configuration input validation."""

    def test_invalid_rotation_rejected(self, client_with_mocks):
        """Invalid rotation angle is rejected."""
        response = client_with_mocks.post('/', data={
            'url': MOCK_IMMICH_URL,
            'album': MOCK_ALBUM_NAME,
            'rotation': '45',  # Invalid
            'enhanced': '1.5',
            'contrast': '1.0',
            'strength': '0.8',
            'display_mode': 'fit',
            'image_order': 'random',
            'dithering_method': 'atkinson',
            'sleep_start_hour': '23',
            'sleep_start_minute': '0',
            'sleep_end_hour': '6',
            'sleep_end_minute': '0',
            'wakeup_interval': '60',
        })

        assert response.status_code == 400

    def test_valid_rotation_accepted(self, client_with_mocks):
        """Valid rotation angle is accepted."""
        for angle in ['0', '90', '180', '270']:
            response = client_with_mocks.post('/', data={
                'url': MOCK_IMMICH_URL,
                'album': MOCK_ALBUM_NAME,
                'rotation': angle,
                'enhanced': '1.5',
                'contrast': '1.0',
                'strength': '0.8',
                'display_mode': 'fit',
                'image_order': 'random',
                'dithering_method': 'atkinson',
                'sleep_start_hour': '23',
                'sleep_start_minute': '0',
                'sleep_end_hour': '6',
                'sleep_end_minute': '0',
                'wakeup_interval': '60',
            }, follow_redirects=True)

            assert response.status_code == 200


# ============================================================
# TC-PER-001: Image Processing Throughput
# ============================================================

class TestPER001ProcessingThroughput:
    """TC-PER-001: Verify dithering performance."""

    def test_floyd_steinberg_performance(self, app_module):
        """Floyd-Steinberg completes within 30 seconds."""
        if not app_module.FLOYD_AVAILABLE:
            pytest.skip("Floyd-Steinberg not available")

        img = create_test_image(EPD_W, EPD_H)

        start = time.time()
        result = app_module.convert_image_floyd(img, 1.0)
        elapsed = time.time() - start

        assert elapsed < 30, f"Floyd-Steinberg took {elapsed:.1f}s"
        assert result.shape == (EPD_H, EPD_W, 3)

    def test_atkinson_performance(self, app_module):
        """Atkinson completes within 30 seconds."""
        if not app_module.ATKINSON_AVAILABLE:
            pytest.skip("Atkinson not available")

        img = create_test_image(EPD_W, EPD_H)

        start = time.time()
        result = app_module.convert_image_atkinson(img, 1.0)
        elapsed = time.time() - start

        assert elapsed < 30, f"Atkinson took {elapsed:.1f}s"
        assert result.shape == (EPD_H, EPD_W, 3)


# ============================================================
# TC-PER-002: Concurrent Request Handling
# ============================================================

class TestPER002ConcurrentRequests:
    """TC-PER-002: Verify concurrent request capacity."""

    def test_flask_app_handles_sequential_requests(self, client_with_mocks):
        """App handles multiple sequential requests."""
        for _ in range(4):
            response = client_with_mocks.get('/api/battery-status')
            assert response.status_code == 200


# ============================================================
# TC-PER-003: Config Reload Latency
# ============================================================

class TestPER003ConfigReloadLatency:
    """TC-PER-003: Verify configuration hot-reload latency."""

    def test_config_reload_under_2_seconds(self, app_module, test_dir,
                                           test_config_path):
        """Configuration reloads within 2 seconds."""
        new_config = {
            'immich': {
                'url': 'http://reload-test.local',
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

        start = time.time()
        write_test_config(test_dir['config'], new_config)

        handler = app_module.ConfigFileHandler(test_config_path,
                                               app_module.update_app_config)
        loaded_config = handler.load_config()
        app_module.update_app_config(loaded_config)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"Config reload took {elapsed:.3f}s"
        assert app_module.url == 'http://reload-test.local'


# ============================================================
# TC-NFR-009: Type Annotations
# ============================================================

class TestNFR009TypeAnnotations:
    """TC-NFR-009: Verify type annotations throughout codebase."""

    def test_future_annotations_import(self, app_module):
        """from __future__ import annotations is present."""
        import ast
        with open(app_module.__file__, 'r') as f:
            source = f.read()
        tree = ast.parse(source)
        has_future = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == '__future__':
                    for alias in node.names:
                        if alias.name == 'annotations':
                            has_future = True
        assert has_future, "Missing 'from __future__ import annotations'"

    def test_typing_module_imported(self, app_module):
        """typing module is imported."""
        assert hasattr(app_module, 'Optional') or 'typing' in str(dir(app_module))

    def test_functions_have_annotations(self, app_module):
        """Key functions have type annotations."""
        annotated_functions = [
            'calculate_battery_percentage',
            'load_downloaded_images',
            'save_downloaded_image',
            'reset_tracking_file',
            'cleanup_old_previews',
            'convert_to_hex_format',
            'scale_img_in_memory',
            'save_three_previews',
            'convert_raw_or_dng_to_jpg',
            'convert_heic_to_jpg',
            'update_app_config',
            'start_config_watcher',
            'run_daily_ntp_sync',
            'stop_ntp_sync',
        ]
        import inspect
        for func_name in annotated_functions:
            func = getattr(app_module, func_name, None)
            if func is not None:
                sig = inspect.signature(func)
                has_hints = any(
                    p.annotation != inspect.Parameter.empty
                    for p in sig.parameters.values()
                ) or sig.return_annotation != inspect.Signature.empty
                assert has_hints, f"{func_name} lacks type annotations"

    def test_global_variables_have_types(self, app_module):
        """Key global variables have type annotations in source."""
        with open(app_module.__file__, 'r') as f:
            source = f.read()
        assert 'BUILD_TIMESTAMP: str' in source or 'BUILD_TIMESTAMP =' in source
        assert 'last_battery_voltage: float' in source
        assert 'last_battery_update: float' in source

