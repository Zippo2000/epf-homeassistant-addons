# Software Test Report (ASPICE SWE.4 / SWE.5 / SWE.6)

**Project:** EPF Home Assistant Add-ons Repository
**Document ID:** EPF-RPT-001
**Version:** 2.3.0
**Date:** 2026-11-15
**Baseline:** branch `main` — code base **v2.3.0** (post §14 remediation + UI-track 2.1.0–2.1.2 +
gallery history 2.2.0 + ingress URL fix 2.2.1 + gallery options 2.3.0)
**Test Spec Reference:** EPF-TST-001 (see `docs/test_specification_aspice.md`)
**Status:** Completed — all tiers green (L0 offline, L1 live Immich, L3 production-image smoke)

> **Why a new report:** the previous revision (1.1.0) described the *v1* single-source build
> (93 nominal / 78 executed cases) and was already internally inconsistent. This revision re-baselines
> the report to the **multi-source v2** code base and to the **140-test** suite that is actually run
> by `Dockerfile.test`. The Immich client is now **v3-conformant** (finding 14.3), and the two
> test-side assertions affected by that port (FR-001/FR-002) are reflected below.
> The **2.0.3** revision re-counts the suite after the UI-track work: one new offline case
> (`TestFR017B` footer build-info contract) and the 5 opt-in **live** cases that now auto-skip
> without an `.env`.
>
> The **2.2.1** revision re-counted the suite after the UI redesign track (2.1.0–2.1.2) and the
> gallery-history feature (2.2.0/2.2.1), and re-ran the **L1 live tier** (real Immich) and the
> **L3 production-image smoke** — both recorded in §6.
>
> The **2.3.0** revision re-baselines again: the gallery limits became real add-on options (plan
> milestone M2), which added **4** cases to `tests/test_gallery_history.py` → offline suite **162**
> cases (21 in that file). L0, L1 and the L3 smoke were re-run green on 2026-11-15. The gallery
> feature now also has a requirement (**FR-032**) and a test case (**TC-FR-032**) in the catalogues.

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| **Total Test Cases** | **167** (162 offline + 5 opt-in live) |
| **Passed** | **167** — 162 offline (L0) **+ 5 live against a real Immich (L1)** |
| **Failed** | 0 |
| **Skipped** | 0 in the combined view (the L0 run skips the 5 live cases by design; they are executed in the L1 run) |
| **Pass Rate** | 100% |
| **Execution Time** | L0 18.1 s (2026-11-15) · L1 0.9 s (2026-11-15) |
| **Test Environment** | Docker (Debian Bookworm, Python 3.11, pytest 7.4.3) |
| **Verdict** | **PASS** — software meets all specified requirements; Immich client is v3-conformant (14.3), verified against a live server |
| **L3 production smoke** | **PASS** — shipped `Dockerfile` image (gunicorn 2×2, healthcheck) + real Immich: `/health`, `/prepare-photo`, `/download`, `/sleep`, gallery, footer — see §6.2 |

---

## 2. Test Execution Summary

### 2.1 Test Environment

| Component | Value |
|-----------|-------|
| **Container Image** | EPF E-Ink add-on test image, built from `epf-eink-addon/Dockerfile.test` |
| **Base OS** | Debian Bookworm |
| **Python Version** | 3.11 |
| **pytest Version** | 7.4.3 |
| **Cython Module** | Compiled in-container from `cpy.pyx` (`setup.py build_ext --inplace`) |
| **Mock Framework** | `responses` 0.24.1 + `unittest.mock` |
| **External Dependencies** | None (fully mocked) |

### 2.2 Mock Configuration

| Mocked Service | Implementation | Purpose |
|---------------|----------------|---------|
| Immich API (**v3**) | `responses` library | `GET /api/albums`, paginated **`POST /api/search/metadata`**, `GET /api/assets/{id}/original`, `/api/server/ping` |
| HA Supervisor | `os.environ` patches | bashio environment variables |
| Filesystem | `pytest.tmp_path` | isolates file operations per test |
| NTP | `unittest.mock.patch` | prevents real network calls |
| Watchdog | `unittest.mock.patch` | prevents real file watching |
| ESP32 Client | Flask Test Client | simulates device HTTP requests |

> **Change vs v1.x:** the album-asset mock now returns the **v3 `search/metadata`** shape
> (`{assets:{items,…,nextPage,…,total}}`) to match the provider change in finding **14.3**.

---

## 3. Detailed Results by Suite

### 3.1 Functional requirements — `tests/test_functional.py`

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| `TestFR001` … `TestFR026` + `TestFR017B` (footer build-info) | **78** | **78** | **0** | **100%** |

### 3.2 Non-Functional / IFR / SEC / PER — `tests/test_nonfunctional.py`

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| NFR (logging, health, performance, theme) + IFR (Immich, ESP32, Ingress, port) + SEC + PER | **27** | **27** | **0** | **100%** |

### 3.3 Provider unit tests — `tests/test_providers.py`  *(new in v2)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| `ImmichProvider`, `ComfyUI-HA`, `ComfyUI-Direct`, `ProviderFactory`, `MultiSourceIntegration` | **36** | **36** | **0** | **100%** |

### 3.4 Gallery history — `tests/test_gallery_history.py`  *(new in v2.2.0; option cases added in v2.3.0)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| Shot-id sanitisation, archiving a pair, grouped reader, per-pattern pruning, live-slot safety, end-to-end prepare, option round-trip (M2) | **21** | **21** | **0** | **100%** |

**Total: 167 collected — 162 passed offline + 5 skipped; the 5 live cases pass in the L1 run (§6.1)
→ 167/167, 0 failed (100 %).**

---

## 4. Requirements Coverage

The full case catalogue and the per-requirement coverage matrix are maintained in
[`docs/test_specification_aspice.md`](test_specification_aspice.md) (EPF-TST-001). Compared with
the v1.x report, this release **adds coverage** for the multi-source feature set:

- **FR-027** — image-source selection (`immich` / `comfyui_ha` / `comfyui_direct`): covered.
- **FR-028** — ComfyUI via Home Assistant (`ai_task.generate_image`): covered (unit + integration).
- **FR-002** — album-asset retrieval is now asserted against the **v3 `search/metadata`** endpoint (14.3).
- **FR-032 / TC-FR-032 — gallery history** (features 2.2.0–2.3.0): covered by **21** automated
  cases in `tests/test_gallery_history.py`; the requirement and test-case IDs were added to
  EPF-REQ-001 / EPF-TST-001 in this revision.

The remaining FR/NFR/IFR/SEC/PER catalogue is unchanged and passing.

---

## 5. Defect / Test-Maintenance Notes

No **product** defects were found in this run. During the §14 remediation, two **test-side**
assertions were corrected to follow the provider's new v3 behaviour (these are test changes, not code defects):

- **FR-002** — the URL assertion moved from the retired `/api/albums/{id}` route to `search/metadata`.
- **FR-001** — the album-**list** matcher was disambiguated from the (removed) album-asset route.

Both landed with the v3 port (finding **14.3**) and are part of the offline result.

Defects found and fixed on the **2.1.x–2.2.1** track (planning docs:
`plans/preview-galerie-geschichte.md`, `plans/ui-modernisierung.md`):

- **Product** — `cleanup_old_previews()` shared one counter across all patterns, so only the first
  pattern was ever capped; each pattern is now capped independently (`test_prunes_each_kind_to_max_count`).
- **Product** — the gallery reader globbed `latest_original_*.jpg` & friends while the pipeline writes
  **fixed** names, so the Gallery tab could never populate (fixed in 2.1.2).
- **Product** — the gallery API returned **absolute** `/preview-file/...` URLs, which break under HA
  ingress; now relative `./preview-file/...` (fixed in 2.2.1, re-proved live in §6.2).
- **Product** — one stray `)` from the 2.1.0 redesign aborted the whole `<script>` block, leaving the
  settings page inert (fixed in 2.1.1).
- **Test-side** — `test_unicode_symbols_used` had gone red when the 2.1.0 SVG redesign dropped the
  page's numeric HTML entities; the Gallery label uses numeric entities again.

---

## 6. Test Execution Log (excerpt)

```
platform linux -- Python 3.11, pytest-7.4.3, pluggy-1.x
rootdir: /app
collected 167 items

tests/test_functional.py      :: 78 passed
tests/test_nonfunctional.py  :: 27 passed
tests/test_providers.py      :: 36 passed
tests/test_gallery_history.py :: 21 passed
tests/test_live.py           :: 5 skipped (opt-in, no .env in the offline run)
======================= 162 passed, 5 skipped in 18.06s ========================
```

### 6.1 L1 — live tier against a real Immich (run 2026-11-15)

```
platform linux -- Python 3.11.2, pytest-7.4.3  (EPF_LIVE_TESTS=1, server from the git-ignored .env)
collected 5 items

tests/test_live.py::test_l01_album_resolution PASSED
tests/test_live.py::test_l02_search_metadata_paginated PASSED
tests/test_live.py::test_l03_original_download PASSED
tests/test_live.py::test_l04_provider_fetch_image PASSED
tests/test_live.py::test_l05_download_end_to_end PASSED
============================== 5 passed in 0.91s ==============================
```

This is the tier that can falsify a real-API assumption: album resolution, the paged
`POST /api/search/metadata` listing, the original download and the add-on's own `/download` route
all hold against the current server.

### 6.2 L3 — production-image smoke (shipped `Dockerfile`, run 2026-11-15)

Image built from `epf-eink-addon/Dockerfile` (build context = add-on dir), started with the real
gunicorn 2×2 command line, real Immich credentials from the git-ignored `.env`:

| Check | Result |
|-------|--------|
| Container healthcheck (`/health`, s6 + `wget`) | **healthy** |
| Footer version / build time (derived, findings §1) | `v2.2.1 \| Built: 2026-11-15 … UTC` — matches the manifest, nothing hand-edited |
| `GET /health` | `200` — `{"source":"Immich","source_status":"connected","status":"healthy"}` |
| `POST /prepare-photo` | real Immich asset → `success: true`, returns the `source_id` |
| `GET /api/gallery-previews` | lists the archived **pair** (`original_<id>.jpg` + `processed_<id>.jpg`), grouped by id, URLs **relative** (`./preview-file/…`, the 2.2.1 fix) |
| `GET /download` (with `batteryCap`) | `200`, `filename=frame.txt`, `text/plain`, **no `};` tail** (contract intact), state flipped `new → delivered` |
| `GET /sleep` | answers with next wakeup + duration |
| `GET /api/battery-status` / `/api/generation-status` | answer as specified |
| `POST /cleanup-previews` | answers; live slot untouched |
| Settings page `/` | renders; 3 tabs present; health-pill tooltip/init text present |

> The add-on entrypoint `run.sh` cannot run outside Home Assistant: its `with-contenv bashio` shebang
> needs the HA runtime (`bashio` is not in the plain base image), and s6 starts services with a
> sanitised environment. The smoke therefore invokes the shipped image through `with-contenv gunicorn
> …` — everything below the entrypoint is the real shipped code.

---

## 7. Reproduction

The add-on test entrypoint is `Dockerfile.test`; all Immich/HA values are supplied by the mocks, so
**no real credentials** are required:

```bash
docker build -f epf-eink-addon/Dockerfile.test -t epf-eink-tests:local epf-eink-addon
docker run --rm epf-eink-tests:local        # runs the bundled /run.sh (pytest)
```

The **L1** live tier is opt-in and reads its connection details from the git-ignored
`epf-eink-addon/.env` (`IMMICH_URL` / `IMMICH_API_KEY` / `IMMICH_ALBUM`):

```bash
cd epf-eink-addon && cp .env.example .env   # then fill in real values
sh epf-eink-addon/run-live-tests.sh
```

> Windows/Git-Bash caveat: do **not** pass `/run.sh` as an argument to `docker run` (MSYS rewrites
> the path and Docker reports a misleading "no such file"), rely on the image `CMD`. Absolute build
> contexts / volume specs get mangled the same way — keep them relative.

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Test Manager | EPF Project | 2026-11-15 | - |
| Quality Assurance | - | - | *(menschliches Zeichen steht aus)* |
| Project Lead | EPF Project | 2026-11-15 | - |

---

*Regenerated for code base **v2.3.0** on branch `main`, 2026-11-15: **162** offline cases pass,
the **5** live cases pass against a real Immich, and the production image passes the L3 smoke
documented above — the release gate of `AGENTS.md` is satisfied. Still open (not automatable here):
the browser-side visual acceptance (light/dark/mobile/CSP) and the L4 field run on a real frame —
see `plans/findings.md`.*
