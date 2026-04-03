# -*- coding: utf-8 -*-
"""
Tests for Multi-Source Provider Architecture (FR-027 to FR-031)

Tests cover:
- ImageProvider abstraction layer
- ImmichProvider (refactored from existing code)
- ComfyUIHAProvider (Home Assistant ai_task service)
- ComfyUIDirectProvider (direct ComfyUI API)
- Prompt variable resolution
- Generation tracking and rate limiting
- Provider factory
- Integration with Flask routes
"""

import os
import sys
import json
import io
from unittest.mock import patch, MagicMock
from datetime import datetime

import pytest
import responses
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from providers import (
    ImageProvider, ImmichProvider, ComfyUIHAProvider, ComfyUIDirectProvider,
    create_provider, resolve_prompt_variables, GenerationTracker,
    PROMPT_VARIABLES, TIME_OF_DAY_MAP, SEASON_MAP
)
from tests.conftest import (
    MOCK_IMMICH_URL, MOCK_API_KEY, MOCK_ALBUM_NAME, MOCK_ALBUM_ID,
    create_test_jpeg_bytes, write_test_config, setup_immich_mocks
)


# ============================================================
# Prompt Variable Tests
# ============================================================

class TestPromptVariables:
    """Tests for prompt template variable resolution."""

    def test_resolve_time_of_day(self):
        prompt = "A scene at {time_of_day}"
        result = resolve_prompt_variables(prompt)
        assert "{time_of_day}" not in result
        assert "A scene at " in result

    def test_resolve_weather(self):
        prompt = "{weather} landscape"
        result = resolve_prompt_variables(prompt)
        assert "{weather}" not in result
        assert "landscape" in result

    def test_resolve_season(self):
        prompt = "{season} vibes"
        result = resolve_prompt_variables(prompt)
        assert "{season}" not in result
        assert "vibes" in result

    def test_resolve_multiple_variables(self):
        prompt = "A {season} {time_of_day} scene with {weather} weather"
        result = resolve_prompt_variables(prompt)
        assert "{season}" not in result
        assert "{time_of_day}" not in result
        assert "{weather}" not in result

    def test_no_variables_unchanged(self):
        prompt = "A beautiful landscape"
        result = resolve_prompt_variables(prompt)
        assert result == prompt

    def test_random_element_varies(self):
        prompt = "{random_element}"
        results = set()
        for _ in range(20):
            results.add(resolve_prompt_variables(prompt))
        assert len(results) > 1


# ============================================================
# Generation Tracker Tests
# ============================================================

class TestGenerationTracker:
    """Tests for generation tracking and rate limiting."""

    def test_initial_count_zero(self, tmp_path):
        tracker = GenerationTracker(str(tmp_path / 'gen.json'))
        assert tracker.get_count_today() == 0

    def test_log_generation(self, tmp_path):
        tracker = GenerationTracker(str(tmp_path / 'gen.json'))
        tracker.log_generation("test prompt", 42, "comfyui_ha")
        assert tracker.get_count_today() == 1

    def test_multiple_generations(self, tmp_path):
        tracker = GenerationTracker(str(tmp_path / 'gen.json'))
        for i in range(5):
            tracker.log_generation(f"prompt {i}", i, "comfyui_ha")
        assert tracker.get_count_today() == 5

    def test_last_generation(self, tmp_path):
        tracker = GenerationTracker(str(tmp_path / 'gen.json'))
        tracker.log_generation("test prompt", 42, "comfyui_ha")
        last = tracker.get_last_generation()
        assert last is not None
        assert last['prompt'] == "test prompt"
        assert last['seed'] == 42
        assert last['source'] == "comfyui_ha"

    def test_persistence(self, tmp_path):
        tracker_file = str(tmp_path / 'gen.json')
        tracker1 = GenerationTracker(tracker_file)
        tracker1.log_generation("persist test", 123, "comfyui_ha")
        
        tracker2 = GenerationTracker(tracker_file)
        assert tracker2.get_count_today() == 1

    def test_daily_reset(self, tmp_path):
        tracker = GenerationTracker(str(tmp_path / 'gen.json'))
        tracker.log_generation("old prompt", 1, "comfyui_ha")
        tracker.reset_daily_count()
        assert tracker.get_count_today() == 0


# ============================================================
# ImmichProvider Tests
# ============================================================

class TestImmichProvider:
    """Tests for the Immich image provider."""

    def test_health_check_success(self, tmp_path):
        with responses.mock:
            responses.add(
                responses.GET,
                f'{MOCK_IMMICH_URL}/api/server/ping',
                json={'res': True},
                status=200,
            )
            provider = ImmichProvider(
                url=MOCK_IMMICH_URL,
                api_key=MOCK_API_KEY,
                album_name=MOCK_ALBUM_NAME,
                photo_dir=str(tmp_path)
            )
            assert provider.health_check() is True

    def test_health_check_failure(self, tmp_path):
        provider = ImmichProvider(
            url='http://nonexistent.invalid',
            api_key=MOCK_API_KEY,
            album_name=MOCK_ALBUM_NAME,
            photo_dir=str(tmp_path)
        )
        assert provider.health_check() is False

    def test_get_source_name(self, tmp_path):
        provider = ImmichProvider(
            url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            album_name=MOCK_ALBUM_NAME,
            photo_dir=str(tmp_path)
        )
        assert provider.get_source_name() == "Immich"

    def test_get_config_summary(self, tmp_path):
        provider = ImmichProvider(
            url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            album_name=MOCK_ALBUM_NAME,
            image_order='random',
            photo_dir=str(tmp_path)
        )
        summary = provider.get_config_summary()
        assert summary['url'] == MOCK_IMMICH_URL
        assert summary['album'] == MOCK_ALBUM_NAME
        assert summary['order'] == 'random'

    @responses.activate
    def test_fetch_image(self, tmp_path):
        image_bytes = create_test_jpeg_bytes()
        setup_immich_mocks(responses, image_bytes=image_bytes)
        
        provider = ImmichProvider(
            url=MOCK_IMMICH_URL,
            api_key=MOCK_API_KEY,
            album_name=MOCK_ALBUM_NAME,
            photo_dir=str(tmp_path)
        )
        
        image, source_id = provider.fetch_image()
        
        assert isinstance(image, Image.Image)
        assert image.mode == 'RGB'
        assert source_id.startswith('asset-uuid-')


# ============================================================
# ComfyUIHAProvider Tests
# ============================================================

class TestComfyUIHAProvider:
    """Tests for the ComfyUI via Home Assistant provider."""

    def _make_ha_response(self, image_bytes):
        import base64
        b64 = base64.b64encode(image_bytes).decode('utf-8')
        return {
            "image_data": f"data:image/jpeg;base64,{b64}"
        }

    def test_health_check_success(self, tmp_path):
        ha_url = 'http://mock-ha.local:8123'
        with responses.mock:
            responses.add(
                responses.GET,
                f'{ha_url}/api/',
                json={},
                status=200,
            )
            provider = ComfyUIHAProvider(
                ha_url=ha_url,
                ha_token='test-token',
                prompt='test',
                photo_dir=str(tmp_path)
            )
            assert provider.health_check() is True

    def test_health_check_failure(self, tmp_path):
        provider = ComfyUIHAProvider(
            ha_url='http://nonexistent.invalid:8123',
            ha_token='test-token',
            prompt='test',
            photo_dir=str(tmp_path)
        )
        assert provider.health_check() is False

    def test_get_source_name(self, tmp_path):
        provider = ComfyUIHAProvider(
            ha_url='http://ha.local',
            ha_token='test-token',
            prompt='test',
            photo_dir=str(tmp_path)
        )
        assert provider.get_source_name() == "ComfyUI (HA)"

    @responses.activate
    def test_fetch_image_success(self, tmp_path):
        image_bytes = create_test_jpeg_bytes()
        ha_url = 'http://mock-ha.local:8123'
        
        responses.add(
            responses.POST,
            f'{ha_url}/api/services/ai_task/generate_image',
            json=self._make_ha_response(image_bytes),
            status=200,
        )
        
        provider = ComfyUIHAProvider(
            ha_url=ha_url,
            ha_token='test-token',
            prompt='A beautiful landscape',
            photo_dir=str(tmp_path)
        )
        
        image, source_id = provider.fetch_image()
        
        assert isinstance(image, Image.Image)
        assert image.mode == 'RGB'
        assert source_id.startswith('gen_')

    @responses.activate
    def test_rate_limiting(self, tmp_path):
        ha_url = 'http://mock-ha.local:8123'
        
        provider = ComfyUIHAProvider(
            ha_url=ha_url,
            ha_token='test-token',
            prompt='test',
            max_generations_per_day=2,
            photo_dir=str(tmp_path)
        )
        
        image_bytes = create_test_jpeg_bytes()
        responses.add(
            responses.POST,
            f'{ha_url}/api/services/ai_task/generate_image',
            json=self._make_ha_response(image_bytes),
            status=200,
        )
        responses.add(
            responses.POST,
            f'{ha_url}/api/services/ai_task/generate_image',
            json=self._make_ha_response(image_bytes),
            status=200,
        )
        
        provider.fetch_image()
        provider.fetch_image()
        
        with pytest.raises(RuntimeError, match='Daily generation limit'):
            provider.fetch_image()

    @responses.activate
    def test_ha_service_error(self, tmp_path):
        ha_url = 'http://mock-ha.local:8123'
        
        responses.add(
            responses.POST,
            f'{ha_url}/api/services/ai_task/generate_image',
            json={'error': 'Service not found'},
            status=404,
        )
        
        provider = ComfyUIHAProvider(
            ha_url=ha_url,
            ha_token='test-token',
            prompt='test',
            photo_dir=str(tmp_path)
        )
        
        with pytest.raises(RuntimeError, match='HA service call failed'):
            provider.fetch_image()

    def test_get_config_summary(self, tmp_path):
        provider = ComfyUIHAProvider(
            ha_url='http://ha.local',
            ha_token='test-token',
            prompt='A test prompt',
            photo_dir=str(tmp_path)
        )
        summary = provider.get_config_summary()
        assert summary['ha_url'] == 'http://ha.local'
        assert 'generations_today' in summary


# ============================================================
# ComfyUIDirectProvider Tests
# ============================================================

class TestComfyUIDirectProvider:
    """Tests for the direct ComfyUI API provider."""

    def test_health_check_success(self, tmp_path):
        comfyui_url = 'http://mock-comfyui.local:8188'
        with responses.mock:
            responses.add(
                responses.GET,
                f'{comfyui_url}/system_stats',
                json={'system': {}},
                status=200,
            )
            provider = ComfyUIDirectProvider(
                url=comfyui_url,
                prompt='test',
                photo_dir=str(tmp_path)
            )
            assert provider.health_check() is True

    def test_health_check_failure(self, tmp_path):
        provider = ComfyUIDirectProvider(
            url='http://nonexistent.invalid:8188',
            prompt='test',
            photo_dir=str(tmp_path)
        )
        assert provider.health_check() is False

    def test_get_source_name(self, tmp_path):
        provider = ComfyUIDirectProvider(
            url='http://comfyui.local',
            prompt='test',
            photo_dir=str(tmp_path)
        )
        assert provider.get_source_name() == "ComfyUI (Direct)"

    def test_build_default_workflow(self, tmp_path):
        provider = ComfyUIDirectProvider(
            url='http://comfyui.local',
            prompt='test prompt',
            negative_prompt='blurry',
            width=800,
            height=480,
            seed=42,
            photo_dir=str(tmp_path)
        )
        workflow = provider._build_workflow()
        assert '3' in workflow
        assert '6' in workflow
        assert workflow['6']['inputs']['text'] == 'test prompt'
        assert workflow['7']['inputs']['text'] == 'blurry'
        assert workflow['5']['inputs']['width'] == 800
        assert workflow['5']['inputs']['height'] == 480

    def test_build_workflow_random_seed(self, tmp_path):
        provider = ComfyUIDirectProvider(
            url='http://comfyui.local',
            prompt='test',
            seed=-1,
            photo_dir=str(tmp_path)
        )
        workflow1 = provider._build_workflow()
        workflow2 = provider._build_workflow()
        seed1 = workflow1['3']['inputs']['seed']
        seed2 = workflow2['3']['inputs']['seed']
        assert seed1 != seed2


# ============================================================
# Provider Factory Tests
# ============================================================

class TestProviderFactory:
    """Tests for the create_provider factory function."""

    def test_create_immich_provider(self, tmp_path):
        config = {
            'image_source': 'immich',
            'immich': {
                'url': MOCK_IMMICH_URL,
                'album': MOCK_ALBUM_NAME,
                'image_order': 'random',
            },
            'comfyui': {}
        }
        os.environ['IMMICH_API_KEY'] = MOCK_API_KEY
        provider = create_provider(config, str(tmp_path))
        assert isinstance(provider, ImmichProvider)

    def test_create_comfyui_ha_provider(self, tmp_path):
        config = {
            'image_source': 'comfyui_ha',
            'immich': {},
            'comfyui': {
                'ha_url': 'http://ha.local',
                'prompt': 'test',
                'width': 800,
                'height': 480,
                'seed': -1,
                'max_generations_per_day': 50,
            }
        }
        os.environ['HA_API_TOKEN'] = 'test-token'
        provider = create_provider(config, str(tmp_path))
        assert isinstance(provider, ComfyUIHAProvider)

    def test_create_comfyui_direct_provider(self, tmp_path):
        config = {
            'image_source': 'comfyui_direct',
            'immich': {},
            'comfyui': {
                'direct_url': 'http://comfyui.local',
                'prompt': 'test',
                'width': 800,
                'height': 480,
                'seed': -1,
                'max_generations_per_day': 50,
            }
        }
        provider = create_provider(config, str(tmp_path))
        assert isinstance(provider, ComfyUIDirectProvider)

    def test_create_unknown_provider_raises(self, tmp_path):
        config = {
            'image_source': 'unknown',
            'immich': {},
            'comfyui': {}
        }
        with pytest.raises(ValueError, match='Unknown image source'):
            create_provider(config, str(tmp_path))


# ============================================================
# Integration Tests with Flask Routes
# ============================================================

class TestMultiSourceIntegration:
    """Integration tests for multi-source support in Flask routes."""

    def test_health_shows_source(self, app_module, tmp_path):
        app_module.app.config['TESTING'] = True
        with app_module.app.test_client() as client:
            response = client.get('/health')
            data = response.get_json()
            assert 'source' in data
            assert 'source_status' in data

    def test_generation_status_immich(self, app_module, tmp_path):
        app_module.app.config['TESTING'] = True
        with app_module.app.test_client() as client:
            response = client.get('/api/generation-status')
            data = response.get_json()
            assert data['source'] == 'Immich'
            assert data['count_today'] == 0

    def test_settings_shows_image_source(self, app_module, tmp_path):
        app_module.app.config['TESTING'] = True
        with app_module.app.test_client() as client:
            response = client.get('/')
            assert response.status_code == 200
            html = response.data.decode('utf-8')
            assert 'image_source' in html
            assert 'comfyui_ha' in html
            assert 'comfyui_direct' in html
