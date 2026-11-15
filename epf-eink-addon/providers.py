# -*- coding:utf-8 -*-

"""
Image Provider Abstraction Layer for EPF E-Ink Photo Frame

Supports multiple image sources:
- Immich (photo server)
- ComfyUI via Home Assistant (ai_task.generate_image)
- ComfyUI Direct API (expert mode)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Tuple, List
import io
import os
import random
import time
import logging
import json
import base64
from datetime import datetime, timedelta

import requests
from PIL import Image
from PIL.Image import Image as PILImage

logger: logging.Logger = logging.getLogger(__name__)


# ==============================================================================
# Prompt Variables Template System
# ==============================================================================

PROMPT_VARIABLES: Dict[str, Any] = {
    "{time_of_day}": ["morning light", "golden hour", "twilight", "moonlit night", "bright noon"],
    "{weather}": ["sunny", "cloudy", "misty", "after rain", "snowy"],
    "{season}": ["spring", "summer", "autumn", "winter"],
    "{day_of_week}": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "{month}": ["January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"],
}

TIME_OF_DAY_MAP: Dict[str, str] = {
    "06": "early morning", "07": "early morning", "08": "morning",
    "09": "morning", "10": "late morning", "11": "late morning",
    "12": "noon", "13": "afternoon", "14": "afternoon",
    "15": "afternoon", "16": "late afternoon", "17": "golden hour",
    "18": "golden hour", "19": "evening", "20": "evening",
    "21": "twilight", "22": "night", "23": "night",
    "00": "midnight", "01": "night", "02": "night",
    "03": "night", "04": "pre-dawn", "05": "pre-dawn",
}

SEASON_MAP: Dict[str, str] = {
    "03": "spring", "04": "spring", "05": "spring",
    "06": "summer", "07": "summer", "08": "summer",
    "09": "autumn", "10": "autumn", "11": "autumn",
    "12": "winter", "01": "winter", "02": "winter",
}


def resolve_prompt_variables(prompt: str) -> str:
    """Resolve template variables in prompt with contextual values."""
    now: datetime = datetime.now()
    current_hour: str = now.strftime("%H")
    current_month: str = now.strftime("%m")
    
    context_variables: Dict[str, str] = {
        "{time_of_day}": TIME_OF_DAY_MAP.get(current_hour, "daytime"),
        "{weather}": random.choice(PROMPT_VARIABLES["{weather}"]),
        "{season}": SEASON_MAP.get(current_month, "summer"),
        "{day_of_week}": now.strftime("%A"),
        "{month}": now.strftime("%B"),
        "{random_element}": random.choice(PROMPT_VARIABLES["{time_of_day}"]),
    }
    
    resolved: str = prompt
    for var, value in context_variables.items():
        resolved = resolved.replace(var, value)
    
    for var, values in PROMPT_VARIABLES.items():
        resolved = resolved.replace(var, random.choice(values))
    
    return resolved


# ==============================================================================
# Generation Tracking
# ==============================================================================

class GenerationTracker:
    """Tracks image generations for rate limiting and history."""
    
    def __init__(self, tracking_file: str):
        self.tracking_file: str = tracking_file
        self.history: list = self._load_history()
    
    def _load_history(self) -> list:
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return []
        return []
    
    def _save_history(self) -> None:
        os.makedirs(os.path.dirname(self.tracking_file) if os.path.dirname(self.tracking_file) else '.', exist_ok=True)
        with open(self.tracking_file, 'w') as f:
            json.dump(self.history, f, indent=2)
    
    def log_generation(self, prompt: str, seed: int, source: str) -> None:
        """Log a new generation."""
        self.history.append({
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt[:200],
            "seed": seed,
            "source": source
        })
        self._save_history()
    
    def get_count_today(self) -> int:
        """Get generation count for today."""
        today: str = datetime.now().date().isoformat()
        return sum(1 for gen in self.history 
                  if gen["timestamp"].startswith(today))
    
    def reset_daily_count(self) -> None:
        """Remove entries from today."""
        today: str = datetime.now().date().isoformat()
        self.history = [gen for gen in self.history 
                       if not gen["timestamp"].startswith(today)]
        self._save_history()
    
    def get_last_generation(self) -> Optional[Dict[str, Any]]:
        """Get the last generation entry."""
        return self.history[-1] if self.history else None


# ==============================================================================
# Base Image Provider
# ==============================================================================

class ImageProvider(ABC):
    """Abstract base class for image sources."""
    
    @abstractmethod
    def fetch_image(self) -> Tuple[PILImage, str]:
        """
        Fetch and return an image.
        
        Returns:
            Tuple of (PIL Image, source_identifier)
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if the image source is available."""
        pass
    
    @abstractmethod
    def get_source_name(self) -> str:
        """Return human-readable source name."""
        pass
    
    @abstractmethod
    def get_config_summary(self) -> Dict[str, str]:
        """Return configuration summary for UI."""
        pass


# ==============================================================================
# Immich Provider
# ==============================================================================

class ImmichProvider(ImageProvider):
    """Provider for Immich photo server."""
    
    def __init__(self, url: str, api_key: str, album_name: str, 
                 image_order: str = 'random', photo_dir: str = 'photos'):
        self.url: str = url
        self.api_key: str = api_key
        self.album_name: str = album_name
        self.image_order: str = image_order
        self.photo_dir: str = photo_dir
        self.tracking_file: str = os.path.join(photo_dir, 'tracking.txt')
        self.headers: Dict[str, str] = {
            'Accept': 'application/json',
            'x-api-key': api_key
        }
    
    def _load_downloaded_images(self) -> set:
        """Load downloaded image IDs from tracking.txt"""
        try:
            if not os.path.exists(self.tracking_file):
                with open(self.tracking_file, 'w') as f:
                    pass
            
            os.chmod(self.tracking_file, 0o666)
            
            with open(self.tracking_file, 'r') as f:
                lines: list = f.readlines()
            
            if not lines or lines[0].strip() != self.album_name:
                with open(self.tracking_file, 'w') as f:
                    f.write(f"{self.album_name}\n")
                return set()
            
            return set(line.strip() for line in lines[1:] if line.strip())
        except Exception as e:
            logger.error(f"Error loading tracking file: {e}")
            return set()
    
    def _save_downloaded_image(self, asset_id: str) -> None:
        """Save downloaded image ID to tracking.txt"""
        try:
            downloaded: set = self._load_downloaded_images()
            downloaded.add(asset_id)
            
            with open(self.tracking_file, 'w') as f:
                f.write(f"{self.album_name}\n")
                for img_id in downloaded:
                    f.write(f"{img_id}\n")
        except Exception as e:
            logger.error(f"Error saving tracking file: {e}")
    
    def _reset_tracking_file(self) -> None:
        """Reset tracking file to start over"""
        try:
            with open(self.tracking_file, 'w') as f:
                f.write(f"{self.album_name}\n")
        except Exception as e:
            logger.error(f"Error resetting tracking file: {e}")
    
    def fetch_image(self) -> Tuple[PILImage, str]:
        """Fetch image from Immich album."""
        response = requests.get(f'{self.url}/api/albums', headers=self.headers, timeout=10)
        if response.status_code != 200:
            raise RuntimeError(f'Failed to fetch albums: {response.status_code}')
        
        data: list = response.json()
        album_id: Optional[str] = next(
            (item['id'] for item in data if item.get('albumName') == self.album_name), 
            None
        )
        
        if not album_id:
            raise RuntimeError(f'Album "{self.album_name}" not found')
        
        # Immich v3+: GET /api/albums/{id} no longer returns 'assets' —
        # fetch them via the paginated POST /api/search/metadata instead (basis EPF).
        album_assets: List[Dict[str, Any]] = []
        page = 1
        while True:
            search_body = {"albumIds": [album_id], "size": 1000, "page": page, "withExif": True}
            response = requests.post(f'{self.url}/api/search/metadata',
                                     headers=self.headers, json=search_body, timeout=30)
            if response.status_code != 200:
                raise RuntimeError(f'Failed to fetch album assets: {response.status_code}')
            result: Dict[str, Any] = response.json().get('assets', {})
            album_assets.extend(result.get('items', []))
            next_page = result.get('nextPage')
            if not next_page:
                break
            page = int(next_page)
        
        album_data: dict = {'assets': album_assets}
        if not album_data['assets']:
            raise RuntimeError('No images in album')
        
        downloaded_images: set = self._load_downloaded_images()
        
        selected_image: dict
        if self.image_order == 'newest':
            sorted_assets: list = sorted(
                album_data['assets'],
                key=lambda x: x.get('exifInfo', {}).get('dateTimeOriginal', '1970-01-01T00:00:00'),
                reverse=True
            )
            remaining_images: list = [img for img in sorted_assets if img['id'] not in downloaded_images]
            
            if not remaining_images:
                self._reset_tracking_file()
                remaining_images = sorted_assets
            
            selected_image = remaining_images[0]
        else:
            remaining_images = [img for img in album_data['assets'] if img['id'] not in downloaded_images]
            if not remaining_images:
                self._reset_tracking_file()
                remaining_images = album_data['assets']
            selected_image = random.choice(remaining_images)
        
        asset_id: str = selected_image['id']
        self._save_downloaded_image(asset_id)
        
        response = requests.get(
            f'{self.url}/api/assets/{asset_id}/original',
            headers=self.headers,
            stream=True,
            timeout=30
        )
        
        if response.status_code != 200:
            raise RuntimeError('Failed to download image')
        
        image_data: io.BytesIO = io.BytesIO(response.content)
        original_path_str: str = selected_image.get('originalPath', '').lower()
        
        image: PILImage
        if original_path_str.endswith(('.raw', '.dng', '.arw', '.cr2', '.nef')):
            import rawpy
            with rawpy.imread(image_data) as raw:
                rgb = raw.postprocess(use_camera_wb=True, use_auto_wb=False)
            image = Image.fromarray(rgb)
        elif original_path_str.endswith('.heic'):
            from pillow_heif import register_heif_opener
            register_heif_opener()
            image = Image.open(image_data).convert('RGB')
        else:
            image = Image.open(image_data)
        
        return image, asset_id
    
    def health_check(self) -> bool:
        """Check Immich server connectivity."""
        try:
            response = requests.get(f"{self.url}/api/server/ping", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_source_name(self) -> str:
        return "Immich"
    
    def get_config_summary(self) -> Dict[str, str]:
        return {
            "url": self.url,
            "album": self.album_name,
            "order": self.image_order
        }


# ==============================================================================
# ComfyUI via Home Assistant Provider
# ==============================================================================

class ComfyUIHAProvider(ImageProvider):
    """Provider for ComfyUI via Home Assistant ai_task service."""
    
    def __init__(self, ha_url: str, ha_token: str, prompt: str,
                 negative_prompt: str = "", width: int = 800, height: int = 480,
                 seed: int = -1, max_generations_per_day: int = 50,
                 photo_dir: str = 'photos', service_name: str = 'ai_task.generate_image',
                 entity_id: Optional[str] = None):
        self.ha_url: str = ha_url.rstrip('/')
        self.ha_token: str = ha_token
        self.prompt: str = prompt
        self.negative_prompt: str = negative_prompt
        self.width: int = width
        self.height: int = height
        self.seed: int = seed
        self.max_generations_per_day: int = max_generations_per_day
        self.service_name: str = service_name
        self.entity_id: str = entity_id or ''
        self.photo_dir: str = photo_dir
        
        generations_file: str = os.path.join(photo_dir, 'generations.json')
        self.tracker: GenerationTracker = GenerationTracker(generations_file)
        
        self.headers: Dict[str, str] = {
            "Authorization": f"Bearer {ha_token}",
            "Content-Type": "application/json"
        }
    
    def fetch_image(self) -> Tuple[PILImage, str]:
        """Generate image via HA ai_task service."""
        count_today: int = self.tracker.get_count_today()
        if count_today >= self.max_generations_per_day:
            raise RuntimeError(
                f'Daily generation limit reached: {count_today}/{self.max_generations_per_day}'
            )
        
        resolved_prompt: str = resolve_prompt_variables(self.prompt)
        
        current_seed: int = self.seed if self.seed != -1 else random.randint(0, 2**32 - 1)
        
        payload: Dict[str, Any] = {
            "task_name": "Image",
            "instructions": resolved_prompt,
        }
        
        entity_id: Optional[str] = self.entity_id or os.getenv('COMFYUI_ENTITY_ID', '')
        if entity_id:
            payload["entity_id"] = entity_id
        
        logger.info(f"Generating image via HA: instructions='{resolved_prompt[:50]}...', entity_id='{entity_id}'")
        logger.info(f"HA payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(
                f"{self.ha_url}/api/services/ai_task/generate_image",
                headers=self.headers,
                json=payload,
                timeout=180,
                params={"return_response": "true"}
            )
            
            if response.status_code != 200:
                logger.error(f"HA response status: {response.status_code}")
                logger.error(f"HA response body: {response.text[:500]}")
                raise RuntimeError(
                    f'HA service call failed: {response.status_code} - {response.text[:200]}'
                )
            
            result: Dict[str, Any] = response.json()
            logger.info(f"HA response keys: {list(result.keys())}")
            logger.info(f"HA response sample: {str(result)[:500]}")
            
            image: PILImage = self._extract_image_from_response(result)
            
            self.tracker.log_generation(resolved_prompt, current_seed, "comfyui_ha")
            
            generation_id: str = f"gen_{current_seed}_{int(time.time())}"
            return image, generation_id
            
        except requests.exceptions.Timeout:
            raise RuntimeError('HA service call timed out (180s). Image generation took too long.')
        except requests.exceptions.ConnectionError:
            raise RuntimeError('Cannot connect to Home Assistant. Check URL and connectivity.')
    
    def _extract_image_from_response(self, result: Dict[str, Any]) -> PILImage:
        """Extract image from HA service response."""
        if "service_response" in result:
            svc = result["service_response"]
            if "url" in svc:
                image_url: str = svc["url"]
                if not image_url.startswith("http"):
                    image_url = f"{self.ha_url}{image_url}"
                logger.info(f"Downloading image from: {image_url}")
                img_response = requests.get(image_url, timeout=60)
                if img_response.status_code != 200:
                    raise RuntimeError(f'Failed to download generated image: {img_response.status_code}')
                return Image.open(io.BytesIO(img_response.content)).convert('RGB')
            elif "media_source_id" in svc:
                raise RuntimeError(f"Image available as media_source: {svc['media_source_id']}. Direct URL not available.")
        
        if "image_data" in result:
            image_data: str = result["image_data"]
            if image_data.startswith("data:image"):
                base64_data: str = image_data.split(",")[1]
            else:
                base64_data = image_data
            image_bytes: bytes = base64.b64decode(base64_data)
            return Image.open(io.BytesIO(image_bytes)).convert('RGB')
        
        elif "url" in result:
            image_url = result["url"]
            img_response = requests.get(image_url, timeout=30)
            if img_response.status_code != 200:
                raise RuntimeError(f'Failed to download generated image: {img_response.status_code}')
            return Image.open(io.BytesIO(img_response.content)).convert('RGB')
        
        elif "images" in result and len(result["images"]) > 0:
            img_data = result["images"][0]
            if isinstance(img_data, str) and img_data.startswith(("data:", "http")):
                return self._extract_image_from_response({"image_data": img_data if img_data.startswith("data:") else ""})
            elif isinstance(img_data, dict) and "data" in img_data:
                return self._extract_image_from_response({"image_data": img_data["data"]})
        
        raise RuntimeError(f'Unexpected response format from HA service. Keys: {list(result.keys())}')
    
    def health_check(self) -> bool:
        """Check HA server connectivity."""
        try:
            response = requests.get(
                f"{self.ha_url}/api/",
                headers=self.headers,
                timeout=5
            )
            return response.status_code in (200, 404)
        except Exception:
            return False
    
    def get_source_name(self) -> str:
        return "ComfyUI (HA)"
    
    def get_config_summary(self) -> Dict[str, str]:
        count_today: int = self.tracker.get_count_today()
        last_gen: Optional[Dict[str, Any]] = self.tracker.get_last_generation()
        
        summary: Dict[str, str] = {
            "ha_url": self.ha_url,
            "prompt": self.prompt[:50] + "..." if len(self.prompt) > 50 else self.prompt,
            "seed": str(self.seed),
            "dimensions": f"{self.width}x{self.height}",
            "generations_today": f"{count_today}/{self.max_generations_per_day}"
        }
        
        if last_gen:
            summary["last_generation"] = last_gen["timestamp"][:19]
        
        return summary


# ==============================================================================
# ComfyUI Direct Provider
# ==============================================================================

class ComfyUIDirectProvider(ImageProvider):
    """Provider for direct ComfyUI API (expert mode)."""

    #: Last-resort fallback only — never an assumption about a specific server.
    DEFAULT_CHECKPOINT: str = "v1-5-pruned-emaonly.safetensors"
    
    def __init__(self, url: str, prompt: str, negative_prompt: str = "",
                 width: int = 800, height: int = 480, seed: int = -1,
                 max_generations_per_day: int = 50, photo_dir: str = 'photos',
                 workflow_json: Optional[str] = None,
                 checkpoint: Optional[str] = None,
                 workflows: Optional[List[Dict[str, Any]]] = None,
                 active_workflow: str = '',
                 steps: int = 20, cfg: float = 8.0,
                 sampler: str = 'euler', scheduler: str = 'normal'):
        self.url: str = url.rstrip('/')
        self.prompt: str = prompt
        self.negative_prompt: str = negative_prompt
        self.width: int = width
        self.height: int = height
        self.seed: int = seed
        self.max_generations_per_day: int = max_generations_per_day
        self.workflow_json: Optional[str] = workflow_json
        self.checkpoint: Optional[str] = checkpoint or None
        self._resolved_checkpoint: Optional[str] = None
        self.photo_dir: str = photo_dir
        # 2.4.0: named workflow list + the selected entry (runtime YAML only).
        self.workflows: List[Dict[str, Any]] = [w for w in (workflows or []) if isinstance(w, dict)]
        self.active_workflow: str = active_workflow or ''
        self.steps: int = int(steps)
        self.cfg: float = float(cfg)
        self.sampler: str = sampler
        self.scheduler: str = scheduler
        
        generations_file: str = os.path.join(photo_dir, 'generations.json')
        self.tracker: GenerationTracker = GenerationTracker(generations_file)
    
    def active_entry(self) -> Optional[Dict[str, Any]]:
        """The selected workflow entry, or None (= global values / built-in graph).

        An unknown name must not break generation: it falls back to the pre-2.4.0
        behaviour (built-in graph or the single ``workflow_json`` field) and says so.
        """
        if not self.active_workflow:
            return None
        for entry in self.workflows:
            if entry.get('name') == self.active_workflow:
                return entry
        logger.warning(
            f"ComfyUI Direct: active workflow '{self.active_workflow}' is not in the "
            f"workflow list; falling back to the global settings"
        )
        return None
    
    def _effective(self, entry: Optional[Dict[str, Any]], key: str, default: Any) -> Any:
        """Workflow-entry value wins, the global value fills the gap."""
        if entry:
            value: Any = entry.get(key)
            if value not in (None, ''):
                return value
        return default
    
    def _inject(self, workflow: Dict[str, Any], entry: Optional[Dict[str, Any]],
                prompt: str, negative: str, seed: int) -> Dict[str, Any]:
        """Put this run's prompt / seed (and dimensions) into a pasted graph.

        Explicit node mapping from the workflow entry wins — which is how a graph whose
        prompt node is not a plain ``CLIPTextEncode.text`` (e.g. Qwen's ``prompt`` input)
        gets the add-on prompt at all. Everything unmapped keeps the pre-2.4.0 scan.
        """
        touched: set = set()
        if entry:
            for node_key, input_key, value, fallback_input in (
                ('prompt_node', 'prompt_input', prompt, 'text'),
                ('negative_node', 'negative_input', negative, 'text'),
                ('seed_node', 'seed_input', seed, 'seed'),
            ):
                node_id: str = str(entry.get(node_key) or '')
                if not node_id:
                    continue
                spec: Optional[Dict[str, Any]] = workflow.get(node_id)
                if not isinstance(spec, dict):
                    logger.warning(
                        f"ComfyUI Direct: workflow '{entry.get('name')}' maps {node_key} to "
                        f"unknown node '{node_id}'; value ignored"
                    )
                    continue
                input_name: str = str(entry.get(input_key) or fallback_input)
                spec.setdefault('inputs', {})[input_name] = value
                touched.add((node_id, input_name))
        
        for node_id, spec in workflow.items():
            if not isinstance(spec, dict) or 'inputs' not in spec:
                continue
            inputs: Dict[str, Any] = spec['inputs']
            for name, value in (('text', prompt), ('text_g', prompt), ('seed', seed),
                                ('width', self.width), ('height', self.height)):
                if name in inputs and (node_id, name) not in touched:
                    inputs[name] = value
        
        # Sampling parameters only apply when the entry sets them explicitly: a pasted
        # graph carries its own numbers, and silently overriding them would surprise.
        if entry:
            for name, value in (('steps', entry.get('steps')), ('cfg', entry.get('cfg')),
                                ('sampler_name', entry.get('sampler')),
                                ('scheduler', entry.get('scheduler'))):
                if value in (None, ''):
                    continue
                for spec in workflow.values():
                    if isinstance(spec, dict) and name in spec.get('inputs', {}):
                        spec['inputs'][name] = value
        return workflow
    
    def _resolve_checkpoint(self) -> str:
        """Pick a checkpoint that actually exists on the target ComfyUI server.

        Priority: explicit ``checkpoint`` option -> first checkpoint the server reports
        on ``/object_info/CheckpointLoaderSimple`` -> built-in default. The lookup runs
        once per provider instance (providers are rebuilt on config reload) and never
        raises: a server that cannot be queried simply falls back to the built-in name,
        which is what the pre-2.3.1 behaviour relied on.
        """
        if self.checkpoint:
            return self.checkpoint
        if self._resolved_checkpoint:
            return self._resolved_checkpoint

        try:
            response = requests.get(
                f"{self.url}/object_info/CheckpointLoaderSimple", timeout=10
            )
            if response.status_code == 200:
                info: Dict[str, Any] = response.json()
                options: List[Any] = (
                    info.get("CheckpointLoaderSimple", {})
                    .get("input", {}).get("required", {})
                    .get("ckpt_name", [[]])[0]
                )
                if options:
                    self._resolved_checkpoint = str(options[0])
                    logger.info(
                        f"ComfyUI Direct: using checkpoint '{self._resolved_checkpoint}' "
                        f"as reported by {self.url}"
                    )
                    return self._resolved_checkpoint
            logger.warning(
                f"ComfyUI Direct: no checkpoint list from {self.url}; "
                f"using built-in default '{self.DEFAULT_CHECKPOINT}'"
            )
        except Exception as e:
            logger.warning(
                f"ComfyUI Direct: checkpoint lookup failed ({e}); "
                f"using built-in default '{self.DEFAULT_CHECKPOINT}'"
            )

        self._resolved_checkpoint = self.DEFAULT_CHECKPOINT
        return self._resolved_checkpoint

    def _build_workflow(self, checkpoint: Optional[str] = None,
                        entry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build the ComfyUI API JSON for this run (entry wins over globals)."""
        entry = entry if entry is not None else self.active_entry()
        prompt: str = self._effective(entry, 'prompt', self.prompt)
        negative: str = self._effective(entry, 'negative_prompt', self.negative_prompt)
        steps: int = int(self._effective(entry, 'steps', self.steps))
        cfg: float = float(self._effective(entry, 'cfg', self.cfg))
        sampler: str = self._effective(entry, 'sampler', self.sampler)
        scheduler: str = self._effective(entry, 'scheduler', self.scheduler)
        workflow_json: Optional[str] = (entry or {}).get('api_json') or self.workflow_json
        current_seed: int = self.seed if self.seed != -1 else random.randint(0, 2**32 - 1)
        
        if workflow_json:
            try:
                workflow: Dict[str, Any] = json.loads(workflow_json)
                if not isinstance(workflow, dict) or not workflow:
                    raise ValueError('not a non-empty node dictionary')
                return self._inject(workflow, entry, resolve_prompt_variables(prompt),
                                    negative, current_seed)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Invalid workflow JSON, using default ({e})")
        
        return {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": current_seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint or self.checkpoint or self._resolved_checkpoint or self.DEFAULT_CHECKPOINT}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": self.width, "height": self.height, "batch_size": 1}},
            "6": {"class_type": "CLIPTextEncode", "inputs": {"text": resolve_prompt_variables(prompt), "clip": ["4", 1]}},
            "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "epf"}}
        }
    
    def fetch_image(self) -> Tuple[PILImage, str]:
        """Generate image via direct ComfyUI API."""
        count_today: int = self.tracker.get_count_today()
        if count_today >= self.max_generations_per_day:
            raise RuntimeError(
                f'Daily generation limit reached: {count_today}/{self.max_generations_per_day}'
            )
        
        current_seed: int = self.seed if self.seed != -1 else random.randint(0, 2**32 - 1)
        entry: Optional[Dict[str, Any]] = self.active_entry()
        # Only the built-in workflow needs a checkpoint decision; a workflow that carries its
        # own model node (entry api_json or the single legacy field) never hits /object_info.
        uses_custom_graph: bool = bool((entry or {}).get('api_json') or self.workflow_json)
        resolved_checkpoint: Optional[str] = None if uses_custom_graph else self._resolve_checkpoint()
        workflow: Dict[str, Any] = self._build_workflow(checkpoint=resolved_checkpoint, entry=entry)
        
        client_id: str = f"epf_{int(time.time())}"
        
        logger.info(
            f"Generating image via ComfyUI Direct: workflow="
            f"{(entry or {}).get('name', '(built-in)')} seed={current_seed}"
        )
        
        try:
            response = requests.post(
                f"{self.url}/prompt",
                json={"prompt": workflow, "client_id": client_id},
                timeout=10
            )
            
            if response.status_code != 200:
                raise RuntimeError(f'ComfyUI queue failed: {response.status_code} - {response.text[:200]}')
            
            prompt_id: str = response.json()["prompt_id"]
            
            image_filename: Optional[str] = self._wait_for_generation(prompt_id, timeout=300)
            
            if not image_filename:
                raise RuntimeError('Generation timed out or failed')
            
            image_response = requests.get(
                f"{self.url}/view",
                params={"filename": image_filename, "type": "output"},
                timeout=30
            )
            
            if image_response.status_code != 200:
                raise RuntimeError(f'Failed to download generated image: {image_response.status_code}')
            
            image: PILImage = Image.open(io.BytesIO(image_response.content)).convert('RGB')
            
            resolved_prompt: str = resolve_prompt_variables(self._effective(entry, 'prompt', self.prompt))
            self.tracker.log_generation(resolved_prompt, current_seed, "comfyui_direct")
            
            generation_id: str = f"gen_{current_seed}_{int(time.time())}"
            return image, generation_id
            
        except requests.exceptions.Timeout:
            raise RuntimeError('ComfyUI request timed out')
        except requests.exceptions.ConnectionError:
            raise RuntimeError('Cannot connect to ComfyUI. Check URL and connectivity.')
    
    def _wait_for_generation(self, prompt_id: str, timeout: int = 300) -> Optional[str]:
        """Wait for generation to complete and return image filename."""
        start_time: float = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.url}/history/{prompt_id}",
                    timeout=5
                )
                
                if response.status_code == 200:
                    history: Dict[str, Any] = response.json()
                    
                    if prompt_id in history:
                        outputs: Dict[str, Any] = history[prompt_id].get("outputs", {})
                        for node_output in outputs.values():
                            if "images" in node_output and node_output["images"]:
                                return node_output["images"][0]["filename"]
                
                time.sleep(2)
                
            except Exception as e:
                logger.warning(f"Error checking generation status: {e}")
                time.sleep(2)
        
        return None
    
    def health_check(self) -> bool:
        """Check ComfyUI server connectivity."""
        try:
            response = requests.get(f"{self.url}/system_stats", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_source_name(self) -> str:
        return "ComfyUI (Direct)"
    
    def get_config_summary(self) -> Dict[str, str]:
        count_today: int = self.tracker.get_count_today()
        last_gen: Optional[Dict[str, Any]] = self.tracker.get_last_generation()
        
        summary: Dict[str, str] = {
            "url": self.url,
            "prompt": self.prompt[:50] + "..." if len(self.prompt) > 50 else self.prompt,
            "seed": str(self.seed),
            "dimensions": f"{self.width}x{self.height}",
            "workflow": self.active_workflow or "(built-in)",
            "generations_today": f"{count_today}/{self.max_generations_per_day}"
        }
        
        if last_gen:
            summary["last_generation"] = last_gen["timestamp"][:19]
        
        return summary


# ==============================================================================
# Provider Factory
# ==============================================================================

def create_provider(config: Dict[str, Any], photo_dir: str) -> ImageProvider:
    """Factory function to create the appropriate provider based on config."""
    source: str = config.get('image_source', 'immich')
    
    if source == 'immich':
        immich_config: Dict[str, Any] = config.get('immich', {})
        return ImmichProvider(
            url=immich_config.get('url', ''),
            api_key=os.getenv('IMMICH_API_KEY', ''),
            album_name=immich_config.get('album', ''),
            image_order=immich_config.get('image_order', 'random'),
            photo_dir=photo_dir
        )
    
    elif source == 'comfyui_ha':
        comfyui_config: Dict[str, Any] = config.get('comfyui', {})
        return ComfyUIHAProvider(
            ha_url=comfyui_config.get('ha_url', ''),
            ha_token=os.getenv('HA_API_TOKEN', ''),
            prompt=comfyui_config.get('prompt', ''),
            negative_prompt=comfyui_config.get('negative_prompt', ''),
            width=comfyui_config.get('width', 800),
            height=comfyui_config.get('height', 480),
            seed=comfyui_config.get('seed', -1),
            max_generations_per_day=comfyui_config.get('max_generations_per_day', 50),
            photo_dir=photo_dir,
            service_name=comfyui_config.get('service_name', 'ai_task.generate_image'),
            entity_id=comfyui_config.get('entity_id', '')
        )
    
    elif source == 'comfyui_direct':
        comfyui_config = config.get('comfyui', {})
        return ComfyUIDirectProvider(
            url=comfyui_config.get('direct_url', ''),
            prompt=comfyui_config.get('prompt', ''),
            negative_prompt=comfyui_config.get('negative_prompt', ''),
            width=comfyui_config.get('width', 800),
            height=comfyui_config.get('height', 480),
            seed=comfyui_config.get('seed', -1),
            max_generations_per_day=comfyui_config.get('max_generations_per_day', 50),
            photo_dir=photo_dir,
            workflow_json=comfyui_config.get('workflow_json', None),
            checkpoint=comfyui_config.get('checkpoint', ''),
            workflows=comfyui_config.get('workflows') or [],
            active_workflow=comfyui_config.get('active_workflow', ''),
            steps=comfyui_config.get('steps', 20),
            cfg=comfyui_config.get('cfg', 8.0),
            sampler=comfyui_config.get('sampler', 'euler'),
            scheduler=comfyui_config.get('scheduler', 'normal')
        )
    
    else:
        raise ValueError(f"Unknown image source: {source}")
