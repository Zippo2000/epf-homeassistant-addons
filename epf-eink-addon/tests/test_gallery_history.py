# -*- coding: utf-8 -*-
"""
Tests for the preview-gallery history feature (release 2.2.0, milestone M1).

Covers:
  * _shot_id derivation (sanitisation, length cap, ts+uuid fallback)
  * _archive_previews() copying fixed-name latest_* into the gallery dir
  * the /api/gallery-previews reader (grouping by id, newest-first, count cap)
  * cleanup_gallery() pruning (and, critically, never touching the live slot)
  * an end-to-end /prepare-photo test proving the archive hook fires

The suite is fully hermetic: preview "files" are tiny placeholder bytes (never
decoded here), and the filesystem is the fixture's tmp_path photo_dir.
"""

import os
import time

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _mk_preview(app, name):
    """Create a placeholder JPEG (undecoded by these tests) in the app photo_dir."""
    path = os.path.join(app.photo_dir, name)
    with open(path, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0' + b'0' * 32)
    return path


def _seed_pairs(app, n, base_ts, step=60):
    """Write n (original, processed) pairs into the gallery dir with staggered mtime."""
    gal = app._gallery_dir()
    os.makedirs(gal, exist_ok=True)
    for i in range(n):
        ts = base_ts + i * step
        for kind in ('original', 'processed'):
            p = os.path.join(gal, '%s_id%d.jpg' % (kind, i))
            with open(p, 'wb') as f:
                f.write(b'\xff\xd8\xff\xe0')
            os.utime(p, (ts, ts))


def _gallery_file_count(app):
    gal = app._gallery_dir()
    if not os.path.isdir(gal):
        return 0
    return len([f for f in os.listdir(gal)
                if any(f.startswith(k) for k in ('original_', 'processed_', 'delivered_'))])


def _get(app, path):
    client = app.app.test_client()
    resp = client.get(path)
    assert resp.status_code == 200, (path, resp.status_code)
    return resp.get_json()


# --------------------------------------------------------------------------
# _shot_id
# --------------------------------------------------------------------------

class TestShotId:
    def test_sanitizes_to_filename_safe(self, app_module):
        sid = app_module._shot_id('a/b c?d e#f')
        allowed = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-')
        assert all(ch in allowed for ch in sid)

    def test_strips_surrounding_separators(self, app_module):
        assert app_module._shot_id('/asset//name/') == 'asset_name'

    def test_caps_length_at_64(self, app_module):
        assert len(app_module._shot_id('x' * 200)) == 64

    def test_plain_id_passthrough(self, app_module):
        assert app_module._shot_id('asset-uuid-000') == 'asset-uuid-000'

    def test_fallback_is_unique_and_prefixed(self, app_module):
        a = app_module._shot_id(None)
        b = app_module._shot_id(None)
        assert a != b
        assert a.startswith('ts_')
        assert b.startswith('ts_')

    def test_empty_string_falls_back(self, app_module):
        assert app_module._shot_id('').startswith('ts_')


# --------------------------------------------------------------------------
# _archive_previews
# --------------------------------------------------------------------------

class TestArchive:
    def test_creates_pair_from_fixed_names(self, app_module):
        _mk_preview(app_module, 'latest_original.jpg')
        _mk_preview(app_module, 'latest_processed.jpg')
        app_module._archive_previews('shot-123')
        gal = app_module._gallery_dir()
        assert os.path.exists(os.path.join(gal, 'original_shot-123.jpg'))
        assert os.path.exists(os.path.join(gal, 'processed_shot-123.jpg'))
        # live single-slot files must remain present (untouched)
        assert os.path.exists(os.path.join(app_module.photo_dir, 'latest_original.jpg'))
        assert os.path.exists(os.path.join(app_module.photo_dir, 'latest_processed.jpg'))

    def test_missing_source_is_noop(self, app_module):
        app_module._archive_previews('shot-x')   # no latest_*.jpg present
        gal = app_module._gallery_dir()
        files = os.listdir(gal) if os.path.isdir(gal) else []
        assert not any(f.startswith('original_') for f in files)

    def test_uses_source_id_as_name(self, app_module):
        _mk_preview(app_module, 'latest_original.jpg')
        _mk_preview(app_module, 'latest_processed.jpg')
        app_module._archive_previews('asset-uuid-007')
        gal = app_module._gallery_dir()
        assert os.path.exists(os.path.join(gal, 'original_asset-uuid-007.jpg'))
        assert os.path.exists(os.path.join(gal, 'processed_asset-uuid-007.jpg'))


# --------------------------------------------------------------------------
# /api/gallery-previews reader
# --------------------------------------------------------------------------

class TestReader:
    def test_empty_gallery(self, app_module):
        data = _get(app_module, '/api/gallery-previews')
        assert data['files'] == []
        assert data['count'] == 0

    def test_groups_by_id_and_sorts_newest_first(self, app_module):
        _seed_pairs(app_module, 3, time.time() - 1000)
        data = _get(app_module, '/api/gallery-previews')
        ids = [f['id'] for f in data['files']]
        assert sorted(ids) == ['id0', 'id0', 'id1', 'id1', 'id2', 'id2']
        assert data['count'] == 3
        # newest group first: first appearance of id0 must be after id1 and id2
        first = {i: ids.index(i) for i in ('id0', 'id1', 'id2')}
        assert first['id2'] < first['id1'] < first['id0']

    def test_caps_at_max_count(self, app_module):
        app_module.GALLERY_MAX_COUNT = 2
        _seed_pairs(app_module, 5, time.time() - 5000)
        data = _get(app_module, '/api/gallery-previews')
        assert data['count'] == 2
        # newest two groups retained (id3, id4), 2 kinds each -> 4 files
        assert sorted(f['id'] for f in data['files']) == ['id3', 'id3', 'id4', 'id4']

    def test_kinds_are_tagged(self, app_module):
        _seed_pairs(app_module, 1, time.time() - 10)
        data = _get(app_module, '/api/gallery-previews')
        kinds = sorted(f['kind'] for f in data['files'])
        assert kinds == ['original', 'processed']
        for f in data['files']:
            # Relative (ingress-safe) URL, not an absolute one hitting the HA root
            assert f['url'].startswith('./preview-file/')


# --------------------------------------------------------------------------
# cleanup_gallery
# --------------------------------------------------------------------------

class TestGalleryPruning:
    def test_prunes_each_kind_to_max_count(self, app_module):
        app_module.GALLERY_MAX_COUNT = 3
        _seed_pairs(app_module, 6, time.time() - 90000)
        assert _gallery_file_count(app_module) == 12
        app_module.cleanup_gallery()
        # 3 originals + 3 processed of the newest ids retained
        assert _gallery_file_count(app_module) == 6
        assert os.path.exists(os.path.join(app_module._gallery_dir(), 'original_id5.jpg'))
        assert not os.path.exists(os.path.join(app_module._gallery_dir(), 'original_id0.jpg'))

    def test_respects_age_limit(self, app_module):
        # all older than the retention window -> pruned even if under count limit
        app_module.GALLERY_MAX_COUNT = 100
        app_module.GALLERY_MAX_AGE_SECONDS = 1
        _seed_pairs(app_module, 2, time.time() - 90000)   # far older than 1s
        app_module.cleanup_gallery()
        assert _gallery_file_count(app_module) == 0

    def test_live_single_slot_is_never_pruned(self, app_module):
        app_module.GALLERY_MAX_COUNT = 1
        app_module.GALLERY_MAX_AGE_SECONDS = 1
        _seed_pairs(app_module, 4, time.time() - 90000)
        live = _mk_preview(app_module, 'latest_original.jpg')
        old = time.time() - 99999999
        os.utime(live, (old, old))          # make the LIVE file "ancient"
        app_module.cleanup_gallery()
        # gallery is pruned, but the live slot file survives untouched
        assert os.path.exists(live)
        assert os.path.exists(os.path.join(app_module.photo_dir, 'latest_original.jpg'))


# --------------------------------------------------------------------------
# end-to-end: POST /prepare-photo archives (needs Immich mocks)
# --------------------------------------------------------------------------

class TestPreparePhotoHooksArchive:
    def test_prepare_photo_archives_a_pair(self, app_module, client_with_mocks, test_dir):
        resp = client_with_mocks.post('/prepare-photo')
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['success'] is True
        sid = body['source_id']                 # e.g. 'asset-uuid-000'
        gal = app_module._gallery_dir()
        # the archive file for this shot exists under a sanitised id
        shots = [f for f in os.listdir(gal) if f.endswith('.jpg')]
        assert any(f.startswith('original_') for f in shots), shots
        assert any(f.startswith('processed_') for f in shots), shots
        # and the live status flips to "new" (hand-shake contract intact)
        with open(os.path.join(app_module.photo_dir, 'latest.status')) as fh:
            assert fh.read().strip() == 'new'
