# -*- coding: utf-8 -*-
"""LIVE integration tests against a REAL Immich v3 server.

This is the *live* tier of the add-on's test model (see TESTSPEC.md and
AGENTS.md, "Top-level goal: flaw-free in Home Assistant"). It is the only
tier that can **falsify** real-backend contract assumptions that the offline,
fully-mocked suite cannot — most importantly, that the Immich image source
still speaks the target server's *current* API (album resolution, the paged
``POST /api/search/metadata`` asset listing, and the original download).

These tests are **skipped by default** and only run when the environment
explicitly opts in (``EPF_LIVE_TESTS=1``) AND supplies the connection
details, so the offline suite (``python -m pytest tests/``) never touches the
network:

      IMMICH_URL        base URL of the Immich server   (required)
      IMMICH_API_KEY    the server's API key             (with "asset.download")
      IMMICH_ALBUM      album name to test against        (default: "eink")

Run them with:    sh run-live-tests.sh       (reads the local, git-ignored .env)
Nothing here hard-codes a server address or a credential.

Covered:
  * TC-L01  album resolution              via GET  /api/albums
  * TC-L02  paginated asset fetch         via POST /api/search/metadata
  * TC-L03  original image download       via GET  /api/assets/{id}/original
  * TC-L04  the add-on's ImmichProvider   end-to-end (fetch_image())
  * TC-L05  the add-on's /download route  end-to-end (frame.txt, no "};" tail)
  * TC-L09  the REAL ComfyUI server, built-in graph (behaviour unchanged)
  * TC-L10  named-workflow selection round trip against that server (2.4.0)

The live ComfyUI tier reads:

      COMFYUI_URL            base URL of the ComfyUI server   (opt-in)
      COMFYUI_WORKFLOW_JSON  optional "Save (Export)" API graph of a real workflow
"""
import os
import re
import sys
import json
import tempfile

import pytest
from PIL.Image import Image as PILImage


# ---------------------------------------------------------------------------
# Opt-in + connection details (never hard-coded)
# ---------------------------------------------------------------------------
LIVE_ENABLED = os.environ.get("EPF_LIVE_TESTS") == "1"


def _env():
    url = os.environ.get("IMMICH_URL", "").rstrip("/")
    key = os.environ.get("IMMICH_API_KEY", "")
    album = os.environ.get("IMMICH_ALBUM", "eink")
    return url, key, album


@pytest.fixture(scope="module")
def immich():
    """Resolve the target album once for the whole module. Skips (rather than
    cascade into failures) when the server is simply not reachable or the
    connection details were not provided."""
    if not LIVE_ENABLED:
        pytest.skip("live tests disabled (set EPF_LIVE_TESTS=1)")

    url, key, album = _env()
    if not url or not key:
        pytest.skip("IMMICH_URL / IMMICH_API_KEY not provided")

    import requests

    headers = {"Accept": "application/json", "x-api-key": key}
    try:
        r = requests.get(f"{url}/api/albums", headers=headers, timeout=10)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - skip, don't fail
        pytest.skip(f"Immich at {url} not reachable ({exc})")

    match = next((a for a in r.json() if a.get("albumName") == album), None)
    if not match:
        pytest.skip(f"album {album!r} not found on {url}")

    return {
        "url": url,
        "key": key,
        "album": album,
        "album_id": match["id"],
        "asset_count": match.get("assetCount", 0),
        "headers": headers,
    }


def _collect_all_assets(info):
    """Walk the paginated v3 endpoint (size=1000, same as the provider) until
    exhausted and return every asset item."""
    import requests

    all_items = []
    page = 1
    while True:
        body = {"albumIds": [info["album_id"]], "size": 1000, "page": page, "withExif": True}
        r = requests.post(
            f"{info['url']}/api/search/metadata",
            headers=info["headers"], json=body, timeout=30,
        )
        assert r.status_code == 200, f"search/metadata page {page} -> {r.status_code}"
        result = r.json().get("assets", {})
        all_items.extend(result.get("items", []))
        next_page = result.get("nextPage")
        if not next_page:
            break
        page = int(next_page)
        assert page <= 1000, "safety abort: too many pages"
    return all_items


# ---------------------------------------------------------------------------
# TC-L01: album resolution
# ---------------------------------------------------------------------------
def test_l01_album_resolution(immich):
    assert immich["album_id"].strip() != ""
    assert len(immich["album_id"]) >= 8


# ---------------------------------------------------------------------------
# TC-L02: paginated asset fetch is complete and terminates
# ---------------------------------------------------------------------------
def test_l02_search_metadata_paginated(immich):
    items = _collect_all_assets(immich)
    assert items, "no assets returned by /api/search/metadata"
    for item in items:
        assert item.get("id"), "asset without id"
        assert "exifInfo" in item, "asset missing exifInfo"
    if immich["asset_count"]:
        assert len(items) == immich["asset_count"], (
            f"fetched {len(items)} assets but album reports {immich['asset_count']}")


# ---------------------------------------------------------------------------
# TC-L03: original image download
# ---------------------------------------------------------------------------
def test_l03_original_download(immich):
    import requests

    first = _collect_all_assets(immich)[0]
    aid = first["id"]
    r = requests.get(
        f"{immich['url']}/api/assets/{aid}/original",
        headers=immich["headers"], timeout=30, stream=True,
    )
    assert r.status_code == 200, f"original download -> {r.status_code}"
    ctype = r.headers.get("Content-Type", "")
    assert ctype.startswith("image/") or ctype == "application/octet-stream", ctype
    assert len(r.content) > 0, "empty image body"


# ---------------------------------------------------------------------------
# TC-L04: the add-on's real ImmichProvider end-to-end
# ---------------------------------------------------------------------------
def test_l04_provider_fetch_image(immich):
    from providers import ImmichProvider

    photo_dir = tempfile.mkdtemp(prefix="epf_live_prov_")
    provider = ImmichProvider(
        url=immich["url"],
        api_key=immich["key"],
        album_name=immich["album"],
        image_order="random",
        photo_dir=photo_dir,
    )
    image, asset_id = provider.fetch_image()

    assert isinstance(asset_id, str) and asset_id.strip(), \
        "provider did not return an asset id"
    assert isinstance(image, PILImage), "provider did not return a PIL image"
    assert image.size[0] > 0 and image.size[1] > 0, "empty image"
    assert image.mode == "RGB", f"expected RGB image, got mode={image.mode}"


# ---------------------------------------------------------------------------
# TC-L05: the add-on's /download route end-to-end
# ---------------------------------------------------------------------------
def test_l05_download_end_to_end(immich):
    """Drive the real ``/download`` route (what the ESP32 calls in HA) against
    the live server: album -> v3 asset fetch -> original download -> Cython
    dithering -> ``frame.txt``. NTP + watchdog are patched so the import is
    hermetic; the Immich call itself is fully live."""
    from unittest.mock import patch, MagicMock

    photo_dir = tempfile.mkdtemp(prefix="epf_live_dl_")
    config_dir = tempfile.mkdtemp(prefix="epf_live_cfg_")
    config_path = os.path.join(config_dir, "config.yaml")

    env = {
        "IMAGE_SOURCE": "immich",
        "IMMICH_URL": immich["url"],
        "IMMICH_API_KEY": immich["key"],
        "ALBUM_NAME": immich["album"],
        "IMMICH_PHOTO_DEST": photo_dir,
        "CONFIG_PATH": config_path,
        "LOG_LEVEL": "WARNING",
    }

    mock_ntp = MagicMock()
    mock_ntp_resp = MagicMock()
    mock_ntp_resp.tx_time = 1700000000.0
    mock_ntp.request.return_value = mock_ntp_resp
    mock_observer = MagicMock()

    resp = None
    with patch.dict(os.environ, env):
        with patch("ntplib.NTPClient", return_value=mock_ntp):
            with patch("watchdog.observers.Observer", return_value=mock_observer):
                for mod_name in list(sys.modules):
                    if mod_name == "app" or mod_name.startswith("app."):
                        del sys.modules[mod_name]
                import app as app_module

                # Force the on-the-fly path (no pre-prepared photo on disk).
                for fname in ("latest.bmp", "latest.status"):
                    pth = os.path.join(photo_dir, fname)
                    if os.path.exists(pth):
                        os.remove(pth)

                # Rebuild the active provider from the (live) module state.
                app_module.update_app_config(app_module.DEFAULT_CONFIG)

                client = app_module.app.test_client()
                resp = client.get("/download", headers={"batteryCap": "3950"})

    # -- assertions ----------------------------------------------------------
    if resp.status_code != 200:
        pytest.fail(f"/download -> {resp.status_code}: {resp.get_data(as_text=True)[:300]}")

    ctype = resp.headers.get("Content-Type", "")
    assert ctype.startswith("text/plain"), ctype

    disposition = resp.headers.get("Content-Disposition", "")
    assert "frame.txt" in disposition, f"Content-Disposition missing frame.txt: {disposition}"

    body = resp.get_data(as_text=True)
    assert body, "empty /download body"
    assert re.search(r"[0-9a-f]", body), "body does not look like packed hex nibbles"
    # Add-on contract: frame.txt has NO closing C-array marker (unlike base EPF).
    assert not body.rstrip().endswith("};"), "add-on frame.txt must not end with ';}'"


# ---------------------------------------------------------------------------
# TC-L09 / TC-L10: named ComfyUI workflows against the REAL server (2.4.0)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def comfyui():
    """Target ComfyUI server for the live workflow tier; skips when not provided."""
    if not LIVE_ENABLED:
        pytest.skip("live tests disabled (set EPF_LIVE_TESTS=1)")
    url = os.environ.get("COMFYUI_URL", "").rstrip("/")
    if not url:
        pytest.skip("COMFYUI_URL not provided (see .env.example)")

    import requests
    try:
        r = requests.get(f"{url}/system_stats", timeout=10)
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - skip, don't fail
        pytest.skip(f"ComfyUI at {url} not reachable ({exc})")

    return {"url": url, "workflow_json": os.environ.get("COMFYUI_WORKFLOW_JSON", "")}


def _direct_provider(info, tmp_prefix, workflows=None, active=""):
    """A provider pointed at the live server, with a throwaway photo dir."""
    from providers import ComfyUIDirectProvider

    photo_dir = tempfile.mkdtemp(prefix=tmp_prefix)
    return ComfyUIDirectProvider(
        url=info["url"],
        prompt="a small red cube on a white table",
        negative_prompt="text, watermark",
        width=512,
        height=512,
        seed=4321,
        steps=4,               # live tier: keep the GPU work small, this is a wiring test
        photo_dir=photo_dir,
        workflows=workflows,
        active_workflow=active,
    )


def test_l09_builtin_graph_still_works(comfyui):
    """No list, no selection -> the built-in graph on a real server, as before 2.4.0."""
    image, source = _direct_provider(comfyui, "epf_live_wf_builtin_").fetch_image()
    assert isinstance(image, PILImage), "no image back from the real server"
    assert image.size[0] > 0 and image.size[1] > 0
    assert source, "no source/filename reported"


def test_l10_named_workflow_selection_round_trip(comfyui):
    """List -> selection -> injection -> a real generation with the entry's own values."""
    probe = _direct_provider(comfyui, "epf_live_wf_probe_")
    # Exactly what fetch_image() would submit: the built-in graph with the checkpoint the
    # live server actually reports (the built-in default name is not on this server).
    graph = probe._build_workflow(checkpoint=probe._resolve_checkpoint())
    entry = {"name": "selected", "api_json": json.dumps(graph),
             "prompt_node": "6", "prompt_input": "text", "steps": 4}
    provider = _direct_provider(comfyui, "epf_live_wf_pick_", workflows=[entry], active="selected")

    assert provider.active_entry()["name"] == "selected"
    submitted = provider._build_workflow()
    assert submitted["6"]["inputs"]["text"] == provider.prompt, "prompt never reached the node"
    assert submitted["3"]["inputs"]["steps"] == 4, "entry sampling value ignored"

    image, source = provider.fetch_image()
    assert isinstance(image, PILImage), "the real server did not return an image"
    assert source, "no source/filename reported"


def test_l10b_real_exported_workflow(comfyui):
    """A genuine "Save (Export)" graph from the reference server, picked by name."""
    if not comfyui["workflow_json"]:
        pytest.skip("COMFYUI_WORKFLOW_JSON not provided (.env) - paste a Save (Export) graph")
    entry = {"name": "exported", "api_json": comfyui["workflow_json"], "steps": 4}
    provider = _direct_provider(comfyui, "epf_live_wf_export_", workflows=[entry], active="exported")
    image, source = provider.fetch_image()
    assert isinstance(image, PILImage), "the real server did not return an image"
    assert source, "no source/filename reported"
