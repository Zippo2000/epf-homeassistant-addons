# Software Test Report (ASPICE SWE.4 / SWE.5 / SWE.6)

**Project:** EPF Home Assistant Add-ons Repository
**Document ID:** EPF-RPT-001
**Version:** 2.4.1
**Date:** 2026-11-15
**Baseline:** branch `main` — code base **v2.4.1** (post §14 remediation + UI-track 2.1.0–2.1.2 +
gallery history 2.2.0 + ingress URL fix 2.2.1 + gallery options 2.3.0 + ComfyUI checkpoint resolution
2.3.1 + settings vocabulary & channel visibility 2.3.2 + named ComfyUI workflows 2.4.0 +
settings-form duplicate-field fix 2.4.1)
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
>
> The **2.3.1** revision closes live finding 1 of §6.3 (the built-in ComfyUI workflow hardcoded one
> server's checkpoint name): the checkpoint is now an option, and empty means *ask the server*.
> Four new provider cases → offline suite **166** cases; L0, L1 and the ComfyUI-direct live leg were
> re-run green on 2026-11-15. Environment values observed on the reference machine moved to §7.1.
>
> The **2.3.2** revision makes the two configuration channels explicit in the product itself: the
> settings form now uses the **add-on-option names** (with the pre-2.3.2 short names kept as a
> read-alias), `comfyui_entity_id` became editable, and the env-only secrets plus the log level are
> echoed as read-only status. Seven new functional cases and three provider cases → offline suite
> **174** cases. L0, L1 and the production-image smoke were re-run green on 2026-11-15 (§6.2).
>
> The **2.4.0** revision records **FR-033 / TC-FR-033** — named ComfyUI workflows with a selectable
> active entry, per-entry prompt/node-mapping/sampling overrides, and API-format validation at save
> time. Eleven new provider cases and seven new functional cases → offline suite **192** cases; the
> live tier grew to **8** cases (three of them ComfyUI, one running a real exported graph). L0, L1 and
> the production-image smoke were re-run green on 2026-11-15 (§6.1, §6.4).
>
> The **2.4.1** revision closes a field-reported defect: six ComfyUI settings were rendered **twice**
> in the single settings form (once per source card), and a duplicated `name` means the browser
> submits both values and Flask keeps the first — the second card's edit was silently dropped (§6.5,
> defect list). The shared settings are now rendered once in their own card. Three new functional
> cases → offline suite **195**; the **8** live cases are unchanged. L0, L1 and the production-image
> smoke were re-run green on 2026-11-15 (§6.5). The catalogue side of this is a **TC-FR-021** test-object
> extension (EPF-TST-001 rev 2.4.1); the requirement itself did not change.

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| **Total Test Cases** | **203** (195 offline + 8 opt-in live) |
| **Passed** | **203** — 195 offline (L0) **+ 8 live against a real Immich and a real ComfyUI (L1)** |
| **Failed** | 0 |
| **Skipped** | 0 in the combined view (the L0 run skips the 8 live cases by design; they are executed in the L1 run) |
| **Pass Rate** | 100% |
| **Execution Time** | L0 19.5 s (2026-11-15) · L1 26.3 s incl. three real GPU generations (2026-11-15) · L3 production smoke incl. one real ComfyUI generation, 12.4 s end to end (2026-11-15) |
| **Test Environment** | Docker (Debian Bookworm, Python 3.11, pytest 7.4.3) |
| **Verdict** | **PASS** — software meets all specified requirements; Immich client is v3-conformant (14.3), the second source (ComfyUI direct) works against a live server (§6.3), the named-workflow selection works end to end, including a real exported graph (§6.4), and the settings form now delivers every field it renders (§6.5) |
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
| `TestFR001` … `TestFR026` + `TestFR017B` (footer build-info) + `TestFR021SettingsVocabulary` (form vocabulary / channel labels / secret echo, 2.3.2; unique-field-name guard and shared-ComfyUI-block round trip, 2.4.1) + `TestFR033WorkflowSelection` (workflow dropdown, save round trip, save-time validation, 2.4.0) | **93** | **93** | **0** | **100%** |

### 3.2 Non-Functional / IFR / SEC / PER — `tests/test_nonfunctional.py`

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| NFR (logging, health, performance, theme) + IFR (Immich, ESP32, Ingress, port) + SEC + PER | **27** | **27** | **0** | **100%** |

### 3.3 Provider unit tests — `tests/test_providers.py`  *(new in v2)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| `ImmichProvider`, `ComfyUI-HA` (incl. entity-id resolution, 2.3.2), `ComfyUI-Direct` (incl. checkpoint resolution, 2.3.1; incl. named-workflow selection, node mapping and per-entry overrides, 2.4.0), `ProviderFactory`, `MultiSourceIntegration` | **54** | **54** | **0** | **100%** |

### 3.4 Gallery history — `tests/test_gallery_history.py`  *(new in v2.2.0; option cases added in v2.3.0)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| Shot-id sanitisation, archiving a pair, grouped reader, per-pattern pruning, live-slot safety, end-to-end prepare, option round-trip (M2) | **21** | **21** | **0** | **100%** |

### 3.5 Live tier (opt-in) — `tests/test_live.py`  *(ComfyUI cases added in v2.4.0)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| 5 Immich cases (L01–L05) + 3 ComfyUI cases (L09 built-in graph, L10 selection round trip, L10b real exported graph) against the reference environment of §7.1 | **8** | **8** | **0** | **100%** |

**Total: 203 collected — 195 passed offline + 8 skipped; the 8 live cases pass in the L1 run (§6.1)
→ 203/203, 0 failed (100 %).**

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
- **FR-021 / TC-FR-021 — web settings UI** (2.3.2): the form-name/option-key vocabulary, the
  legacy short-name alias, the read-only secret & log-level echo, the channel labels and the new
  `comfyui_entity_id` field are covered by **7** automated cases (`TestFR021WebSettings` +
  `TestFR021SettingsVocabulary`); the spec row was moved to Executed — Passed.
- **FR-033 / TC-FR-033 — named ComfyUI workflow selection** (2.4.0): the dropdown, the slot list, the
  per-entry prompt/node-mapping/sampling overrides, the save-time validation and the "POST without
  fields keeps the list" rule are covered by **18** automated offline cases (11 provider + 7 settings)
  plus the **3** live cases of §6.1; the catalogue rows were added in this revision.

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
- **Test-side (2.3.2)** — `test_slider_output_ids_present` asserts the slider output ids, which follow
  the field names; it was updated to `color_enhanceValue` / `contrastValue` / `dithering_strengthValue`
  when the form adopted the add-on-option vocabulary. The **runtime-YAML keys were deliberately not
  renamed** (`url`, `album`, `rotation`, `enhanced`, `strength`): `settings()` resolves the canonical
  name first and keeps the short name as a legacy alias, so stored configs keep working.

Defect found and fixed on the **2.4.1** track (reported from a real installation, not from the suite):

- **Product** — the settings page is **one form**, and the two ComfyUI cards each rendered the six
  shared settings (prompt, negative prompt, width, height, seed, max generations per day) under the
  **same** field name. Both controls are submitted — a `display: none` card is still a submitted card —
  and Flask keeps the first occurrence, so an edit made in the second card never reached the runtime
  YAML while the save still reported success. Symptom in the field: a seed change from `0` to `-1`
  "saved" and did nothing, and ComfyUI kept answering the following runs from cache with the previous
  file. Fixed by rendering those six settings **once**, in a shared **ComfyUI — Common Settings** card;
  guarded by `test_form_field_names_are_unique` plus the two companion cases (§6.5).
- **Product (cosmetic, accepted)** — `batteryTimestampHeader` appears as an id twice in the template,
  but the two elements live in mutually exclusive Jinja branches, so only one ever renders. No action.

---

## 6. Test Execution Log (excerpt)

```
platform linux -- Python 3.11, pytest-7.4.3, pluggy-1.x
rootdir: /app
collected 203 items

tests/test_functional.py      :: 93 passed
tests/test_nonfunctional.py  :: 27 passed
tests/test_providers.py      :: 54 passed
tests/test_gallery_history.py :: 21 passed
tests/test_live.py           :: 8 skipped (opt-in, no .env in the offline run)
======================= 195 passed, 8 skipped in 19.47s ========================
```

### 6.1 L1 — live tier against the real backends (Immich + ComfyUI, run 2026-11-15)

```
platform linux -- Python 3.11.2, pytest-7.4.3  (EPF_LIVE_TESTS=1, servers from the git-ignored .env)
collected 8 items

tests/test_live.py::test_l01_album_resolution PASSED
tests/test_live.py::test_l02_search_metadata_paginated PASSED
tests/test_live.py::test_l03_original_download PASSED
tests/test_live.py::test_l04_provider_fetch_image PASSED
tests/test_live.py::test_l05_download_end_to_end PASSED
tests/test_live.py::test_l09_builtin_graph_still_works PASSED
tests/test_live.py::test_l10_named_workflow_selection_round_trip PASSED
tests/test_live.py::test_l10b_real_exported_workflow PASSED
============================== 8 passed in 26.02s ==============================
```

This is the tier that can falsify a real-API assumption: album resolution, the paged
`POST /api/search/metadata` listing, the original download and the add-on's own `/download` route
all hold against the current server — and since 2.4.0 the ComfyUI leg runs real generations through
the built-in graph, a named selection and a **real exported graph** taken from the reference server.
Server/album/server-graph used are the reference environment of §7.1 — the values live in the
git-ignored `.env`, never in the code.

### 6.2 L3 — production-image smoke (shipped `Dockerfile`, run 2026-11-15)

Image built from `epf-eink-addon/Dockerfile` (build context = add-on dir), started with the real
gunicorn 2×2 command line, real Immich credentials from the git-ignored `.env`:

| Check | Result |
|-------|--------|
| Container healthcheck (`/health`, s6 + `wget`) | **healthy** |
| Footer version / build time (derived, findings §1) | `2.3.2` (re-run 2026-11-15) — derived from the manifest, nothing hand-edited |
| `GET /health` | `200` — `{"source":"Immich","source_status":"connected","status":"healthy"}` |
| `POST /prepare-photo` | real Immich asset → `success: true`, returns the `source_id` |
| `GET /api/gallery-previews` | lists the archived **pair** (`original_<id>.jpg` + `processed_<id>.jpg`), grouped by id, URLs **relative** (`./preview-file/…`, the 2.2.1 fix) |
| `GET /download` (with `batteryCap`) | `200`, `filename=frame.txt`, `text/plain`, **no `};` tail** (contract intact), state flipped `new → delivered` |
| `GET /sleep` | answers with next wakeup + duration |
| `GET /api/battery-status` / `/api/generation-status` | answer as specified |
| `POST /cleanup-previews` | answers; live slot untouched |
| Settings page `/` | renders; 3 tabs present; health-pill tooltip/init text present; **2.3.2**: canonical field names, per-card channel labels and the read-only secret/log-level status rows are served |
| **Form vocabulary POST (2.3.2)** | `POST /` with the canonical names → the same runtime-YAML keys; `POST /` with the legacy short names → the same keys (alias proven in the shipped image), watchdog fired, provider rebuilt |

> The add-on entrypoint `run.sh` cannot run outside Home Assistant: its `with-contenv bashio` shebang
> needs the HA runtime (`bashio` is not in the plain base image), and s6 starts services with a
> sanitised environment. The smoke therefore invokes the shipped image through `with-contenv gunicorn
> …` — everything below the entrypoint is the real shipped code.

### 6.3 L3b — second image source, live (ComfyUI direct, run 2026-11-15)

Same production image, `image_source=comfyui_direct`, pointed at the **real** ComfyUI (v0.38.2).
This is the live proof of the multi-source claim (FR-027/FR-030) and of the 2.3.0 options path.

| Check | Result |
|-------|--------|
| `GET /health` | `200` — `{"source":"ComfyUI (Direct)","source_status":"connected","status":"healthy"}` — source-agnostic health, proven against a live backend |
| Settings page | `comfyui_direct` pre-selected server-side; the new **Photo Gallery** card renders both fields |
| Add-on option → env → YAML → UI | `GALLERY_MAX_COUNT=5` / `GALLERY_RETENTION_DAYS=2` seeded into the runtime YAML at first start and shown in the fields (5 / 2) ✓ |
| Settings form → YAML → hot reload | form posted with 3 / 2 → YAML rewritten, watchdog fired, provider rebuilt, page shows 3 / 2 ✓ |
| `POST /prepare-photo` (real generation, workflow override) | `success: true` in 4.5 s; the **archive hook fires on this source too** (`Archived previews for shot 'gen_…'`) |
| Configured cap honoured live | with cap **3**: after the second archive the gallery holds exactly 3 files per pattern (4 pruned) ✓ |
| `GET /api/gallery-previews` | groups by shot id, reports the shot count ✓ |
| `POST /cleanup-previews` | removes nothing from the gallery — by design the gallery is pruned **at archive time**; the route cleans the legacy live-slot previews only ✓ |
| Checkpoint **auto-detection** (2.3.1), no workflow JSON | empty option → the add-on queried `/object_info/CheckpointLoaderSimple`, used the first checkpoint the server reports (log: `using checkpoint '…' as reported by …`) and generated for real in **4.6 s** ✓ |
| Explicit `comfyui_checkpoint` (2.3.1) through the settings form | form → YAML → hot reload → generation ran on the named checkpoint (**59 s**, the second reference checkpoint — visibly a different model) ✓; the explicit value short-circuits the lookup ✓ |

**Things this run exposed** (all pre-existing, none introduced by 2.3.0):

1. **The built-in default ComfyUI workflow did not fit a real server — closed in 2.3.1.** It used to
   hardcode one server's checkpoint name (`providers.py`, node 4), so a real `/prompt` answered
   `prompt_outputs_failed_validation` / `value_not_in_list`, and only a pasted workflow JSON made it
   work. The offline mocks cannot see this — only a live run can. **Decision taken and implemented:**
   a `comfyui_checkpoint` option (manifest + settings page), and *empty means ask the server*
   (`/object_info/CheckpointLoaderSimple`, queried once per provider instance, never when a custom
   workflow JSON is configured), with the previously hardcoded name kept as the last-resort fallback.
   Both paths proven live in the two rows above; four offline cases cover option precedence,
   auto-detection, fallback and the no-lookup rule.
2. **The per-pattern cap can split a pair.** Pruning counts files *per pattern*, so a shot can be left
   with only its original or only its processed file (seen live: `sim2` kept its original, lost its
   processed file) — the plan worded the limit as "max. **pairs**". Either document the semantics or
   prune per shot — **decision still open**. Related, already accepted as the 14.12 trade-off: the generation counter lives per
   process and is rebuilt on hot reload — the live run reported `count_today: 1` after two generations.

---

### 6.4 L3/L1 re-run for 2.4.0 — named workflows in the shipped image (run 2026-11-15)

Same production `Dockerfile`, `image_source=comfyui_direct`, seeded through the two new add-on
options (`comfyui_workflows` as a JSON array, `comfyui_active_workflow` naming one of them) — the
reference server of §7.1 doing the actual diffusion:

| Check | Result |
|-------|--------|
| Footer version (derived) | **v2.4.0** ✓ |
| `GET /health` against the live ComfyUI | `{"source":"ComfyUI (Direct)","source_status":"connected","status":"healthy"}` ✓ |
| Seed options → dropdown | the seeded entry appears in the dropdown **selected**; four slots render, first two open ✓ |
| Settings form POST (slot name + API JSON + steps + active selection) | `302` → runtime YAML holds the entry and `active_workflow: flux`, watchdog fired, provider rebuilt ✓ |
| POST **without** workflow fields | stored list untouched ✓ (the rule that protects old callers) |
| `POST /prepare-photo` with the named workflow active | real generation, log `workflow=flux seed=…`, gallery archive hook fires ✓ |
| Save-time validation | UI-format graph → `400` naming **"Save (Export)"** ✓; duplicate name → `400` ✓ |
| `/download` contract (regression) | `frame.txt`, `text/plain`, 16 tokens/row, **no `};` tail** ✓ |
| Generation status / gallery API | answer as specified ✓ |

**One product fix came out of building this:** the settings-page labels pointed at field ids the slot
inputs did not have (`for` ≠ `id`); the slot inputs now carry ids, so the labels are real labels.

### 6.5 L0/L1/L3 re-run for 2.4.1 — the form delivers every field it renders (run 2026-11-15)

Trigger was a field report: on a real installation running `image_source=comfyui_direct`, a seed change
on the settings page saved "successfully" and changed nothing, and the ComfyUI server answered the
runs after it from cache with the previous file. Root cause is the duplicated field name in §5 — the
pipeline itself was never involved. The shipped production image was rebuilt and driven through the
browser's own path (form `POST` → runtime YAML → watchdog → provider → generation on the reference
server of §7.1):

| Check | Result |
|-------|--------|
| Rendered page | 109 KB, **no field name appears twice**, no duplicate rendered id ✓ (the guard is now an automated test as well) |
| Footer version (derived) | **v2.4.1** ✓ |
| `GET /health` before the save | reports the seeded source (Immich) ✓ |
| Form `POST` exactly as the browser sends it (`image_source=comfyui_direct`, canonical names) | `302` → runtime YAML now carries `prompt`, `negative_prompt`, `width: 1024`, `height: 768`, **`seed: -1`**, `max_generations_per_day: 12`, `active_workflow: qwen` and the slot entry ✓ — every shared field arrives |
| Watchdog / provider rebuild after the save | fires ✓ |
| `POST /prepare-photo` (real GPU generation, named workflow active) | `200` in **12.4 s** — log `Generating image via ComfyUI Direct: workflow=qwen seed=1806705723`, **new file** on the server (`…00036`), three previews stored, gallery archive hook fires ✓ |
| `/download` contract (regression) | `frame.txt`, `text/plain`, 16 tokens/row, **no `};` tail** ✓ |
| L0 offline suite | **195 passed, 8 skipped** (the three new functional cases included) ✓ |
| L1 live tier | **8 passed**, including the real exported graph ✓ |

**What this proves:** every field the form renders reaches the runtime YAML — the loss was a rendering
accident, not the pipeline — and a named workflow with a random seed produces a genuinely new image on
the real server, which is what the field report said it did not.

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

### 7.1 Reference test environment (of record)

Values observed on the reference machine during the live runs of §6.1, §6.3 and §6.4 — recorded here so the
report can be reproduced, **not** product assumptions. Nothing in code, templates or the manifest may
hardcode them (connection details come from add-on options / the git-ignored `.env`; since 2.4.0 the
exported workflow graph the live tier posts is a `.env` value too):

| Item | Reference value |
|------|-----------------|
| Immich server / album | as configured in `epf-eink-addon/.env` (never committed) |
| ComfyUI server | 0.38.2 (checked 2026-11-15) |
| Checkpoints on the reference server | three installed; auto-detection picked the first one (names not committed) |
| Home Assistant | private instance — URL comes from the `ha_url` add-on option (not committed); this leg is still untested |
| Host runtime | Docker Desktop, Debian Bookworm base, Python 3.11 |

> The `comfyui_ha` source is the one live leg still missing: it needs a Long-Lived Token and an
> `ai_task` entity id from the user (the entity id is now also editable on the settings page, 2.3.2),
> and the `ai_task` integration on the HA side.

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Test Manager | EPF Project | 2026-11-15 | - |
| Quality Assurance | - | - | *(menschliches Zeichen steht aus)* |
| Project Lead | EPF Project | 2026-11-15 | - |

---

*Regenerated for code base **v2.4.1** on branch `main`, 2026-11-15: **195** offline cases pass,
the **8** live cases pass against a real Immich *and* a real ComfyUI (including a real exported
workflow graph), and the production image passes the L3 smoke (form vocabulary §6.2, named workflows
§6.4, form-delivers-every-field §6.5) plus the live ComfyUI-direct leg (§6.3) — the release gate of
`AGENTS.md` is satisfied.
Still open (not automatable here):
the browser-side visual acceptance (light/dark/mobile/CSP) and the L4 field run on a real frame —
see `plans/findings.md`.*
