# Software Test Report (ASPICE SWE.4 / SWE.5 / SWE.6)

**Project:** EPF Home Assistant Add-ons Repository
**Document ID:** EPF-RPT-001
**Version:** 2.0.3
**Date:** 2026-09-17
**Baseline:** branch `main` — code base **v2.0.3** (post §14 remediation, after the UI-track of `plans/findings.md`)
**Test Spec Reference:** EPF-TST-001 (see `docs/test_specification_aspice.md`)
**Status:** Completed — All Tests Passed

> **Why a new report:** the previous revision (1.1.0) described the *v1* single-source build
> (93 nominal / 78 executed cases) and was already internally inconsistent. This revision re-baselines
> the report to the **multi-source v2** code base and to the **140-test** suite that is actually run
> by `Dockerfile.test`. The Immich client is now **v3-conformant** (finding 14.3), and the two
> test-side assertions affected by that port (FR-001/FR-002) are reflected below.
> The **2.0.3** revision re-counts the suite after the UI-track work: one new offline case
> (`TestFR017B` footer build-info contract) and the 5 opt-in **live** cases that now auto-skip
> without an `.env`.

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| **Total Test Cases** | 146 (141 offline + 5 opt-in live) |
| **Passed** | 141 |
| **Failed** | 0 |
| **Skipped** | 5 (live tier, no `EPF_LIVE_TESTS`/`.env`) |
| **Pass Rate** | 100% |
| **Execution Time** | ~18.3 s |
| **Test Environment** | Docker (Debian Bookworm, Python 3.11, pytest 7.4.3) |
| **Verdict** | **PASS** — software meets all specified requirements; Immich client is v3-conformant (14.3) |

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

**Total: 146 collected — 141 passed, 5 skipped (opt-in live tier), 0 failed (100 %).**

---

## 4. Requirements Coverage

The full case catalogue and the per-requirement coverage matrix are maintained in
[`docs/test_specification_aspice.md`](test_specification_aspice.md) (EPF-TST-001). Compared with
the v1.x report, this release **adds coverage** for the multi-source feature set:

- **FR-027** — image-source selection (`immich` / `comfyui_ha` / `comfyui_direct`): covered.
- **FR-028** — ComfyUI via Home Assistant (`ai_task.generate_image`): covered (unit + integration).
- **FR-002** — album-asset retrieval is now asserted against the **v3 `search/metadata`** endpoint (14.3).

The remaining FR/NFR/IFR/SEC/PER catalogue is unchanged and passing.

---

## 5. Defect / Test-Maintenance Notes

No **product** defects were found in this run. During the §14 remediation, two **test-side**
assertions were corrected to follow the provider's new v3 behaviour (these are test changes, not code defects):

- **FR-002** — the URL assertion moved from the retired `/api/albums/{id}` route to `search/metadata`.
- **FR-001** — the album-**list** matcher was disambiguated from the (removed) album-asset route.

Both landed with the v3 port (finding **14.3**) and are part of the 141/141 offline result.

---

## 6. Test Execution Log (excerpt)

```
platform linux -- Python 3.11, pytest-7.4.3, pluggy-1.x
rootdir: /app
collected 146 items

tests/test_functional.py      :: 78 passed
tests/test_nonfunctional.py  :: 27 passed
tests/test_providers.py      :: 36 passed
tests/test_live.py           :: 5 skipped (opt-in, no .env)
======================= 141 passed, 5 skipped in 18.28s =========================
```

---

## 7. Reproduction

The add-on test entrypoint is `Dockerfile.test`; all Immich/HA values are supplied by the mocks, so
**no real credentials** are required:

```bash
docker build -f epf-eink-addon/Dockerfile.test -t epf-eink-tests:local epf-eink-addon
docker run --rm epf-eink-tests:local        # runs the bundled /run.sh (pytest)
```

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Test Manager | EPF Project | 2026-09-16 | - |
| Quality Assurance | - | - | - |
| Project Lead | EPF Project | 2026-09-16 | - |

---

*Regenerated for code base **v2.0.3** on branch `main`. All 141 offline test cases pass (the 5
opt-in live cases auto-skip without a `.env`); the Immich client is v3-conformant, the production
image is complete (incl. the DejaVu font, 14.7), and the footer version/build-time are now derived
in-image (see `plans/findings.md`, release 2.0.3).*
