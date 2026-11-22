# Software Test Report (ASPICE SWE.4 / SWE.5 / SWE.6)

**Project:** EPF Home Assistant Add-ons Repository
**Document ID:** EPF-RPT-001
**Version:** 2.4.3
**Date:** 2026-11-22
**Baseline:** branch `main` — code base **v2.4.3** (post §14 remediation + UI-track 2.1.0–2.1.2 +
gallery history 2.2.0 + ingress URL fix 2.2.1 + gallery options 2.3.0 + ComfyUI checkpoint resolution
2.3.1 + settings vocabulary & channel visibility 2.3.2 + named ComfyUI workflows 2.4.0 +
settings-form duplicate-field fix 2.4.1 + global date-stamp switch 2.4.2 + **per-shot gallery
pruning 2.4.3** + settings-page guards & full traceability 2.4.3b)
**Test Spec Reference:** EPF-TST-001 (see `docs/test_specification_aspice.md`)
**Tag:** `v2.4.3` — annotated, cut on 2026-11-22 at this baseline and pushed. Note for the field: the
add-on store does **not** read tags, it compares the manifest `version:` with the *installed* version,
so an install that pulled 2.4.3 before the 2.4.3b commits landed shows no pending update while running
without them — reinstall in HA to get them (see `plans/findings.md` §5).
**Status:** all three automatable tiers are green on the **v2.4.3 / 2.4.3b** code base — **L0** 205/205,
**L1** 8/8 against a real Immich *and* a real ComfyUI, **L3** production-image smoke on the shipped
image; all three re-run **2026-11-22** (§6.9). What remains is not automatable from here: the browser
acceptance (§6.5, incl. the new save-time dialog), finding 14.9, the `comfyui_ha` live leg, the
multi-day field run, and the human QA signature (§8)

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
>
> The **2.4.2** revision implements the global **date-stamp switch** on the settings page
> (`date_overlay`, default enabled) — the first setting that lives at the **top level** of the runtime
> YAML because it belongs to no source. **FR-010** was re-worded for it in EPF-REQ-001, and
> **TC-FR-010-EXIF** gained four cases (on/off differential, settings round trip through YAML and
> hot reload, partial POST keeps the stored value, page shows stored state) → offline suite **199**;
> the live tier is unchanged at **8**. L0, L1 and the production-image smoke were re-run green on
> 2026-11-17, including the switch demonstrated on a real Immich photo (§6.6).
>
> The **2.4.3** revision closes live finding **2** of §6.3 (the cap could **split a pair**): gallery
> pruning now counts whole **shots**, so both limits drop a shot complete and the pruner judges a shot
> by the same measure the reader sorts by — the cap finally means the same thing on both sides. Three
> new cases in `tests/test_gallery_history.py` → **24** there, offline suite **202**, combined
> **210** (§6.7). **FR-032** was re-worded in EPF-REQ-001 and **TC-FR-032** extended in EPF-TST-001.
> The live preview directory (`POST /cleanup-previews`, a single slot rather than a group) keeps its
> per-pattern behaviour — **FR-024** is unchanged. **L0 re-ran green on 2026-11-20; the L1 tier and
> the production-image smoke have not been re-run for this code base yet, so the 100 % below is the
> L0 tier plus the v2.4.2 live/L3 runs.**
>
> The **2.4.3b** revision implements the two settings-page guards the plan
> (`plans/ui-modernisierung.md` §9) had left open: a workflow slot that carries **content but no
> name** is refused at save time instead of vanishing, and an **emptied field** still overwrites the
> stored value — the form always sends its controls — but the page asks first. Three new cases in
> `tests/test_functional.py` (97 → **100**: two lock the slot rule, one pins the empty-field
> behaviour together with the warning), offline suite **202 → 205**, combined **213**. EPF-TST-001
> gained **TC-FR-027 … TC-FR-031**, so its traceability names all **55** requirements for the first
> time (§6.8).

---

## 1. Executive Summary

| Metric | Value |
|--------|-------|
| **Total Test Cases** | **213** (205 offline + 8 opt-in live) |
| **Passed** | **213** — 205 offline (L0) **+ 8 live against a real Immich and a real ComfyUI (L1)**; both tiers re-run green on this code base, 2026-11-22 (§6.9) |
| **Failed** | 0 |
| **Skipped** | 0 in the combined view (the L0 run skips the 8 live cases by design; they are executed in the L1 run) |
| **Pass Rate** | 100% |
| **Execution Time** | L0 **23.3 s (2026-11-22)** · L1 **40.2 s** incl. three real GPU generations (2026-11-22) · L3 production smoke incl. three real Immich generations **over** the gallery cap (2026-11-22, §6.9) |
| **Test Environment** | Docker (Debian Bookworm, Python 3.11, pytest 7.4.3) |
| **Verdict** | **PASS** — software meets all specified requirements; Immich client is v3-conformant (14.3), the second source (ComfyUI direct) works against a live server (§6.3), the named-workflow selection works end to end, including a real exported graph (§6.4), the settings form delivers every field it renders (§6.5) and now refuses an unnamed workflow slot and warns before an emptied field overwrites (§6.8), the global date-stamp switch governs the pipeline on the shipped image (§6.6), and gallery pruning keeps a shot whole (§6.7). **Baseline:** all three automatable tiers — L0, L1, L3 — have been re-run green on this code base (2026-11-22, §6.9); what is left is the browser acceptance and the human QA signature |
| **L3 production smoke** | **PASS on this code base (2026-11-22, §6.9)** — shipped `Dockerfile` image (gunicorn 2×2, real `with-contenv`, healthcheck) + real Immich: `/health`, `/prepare-photo`, `/download`, `/sleep`, gallery **pruned per shot over the cap**, watchdog reload, footer; the two 2.4.3b settings behaviours were confirmed over HTTP on the shipped image |

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
| `TestFR001` … `TestFR026` + `TestFR017B` (footer build-info) + `TestFR021SettingsVocabulary` (form vocabulary / channel labels / secret echo, 2.3.2; unique-field-name guard and shared-ComfyUI-block round trip, 2.4.1; empty-field-overwrites pin + the save-time warning, 2.4.3b) + `TestFR033WorkflowSelection` (workflow dropdown, save round trip, save-time validation incl. **content without a name**, 2.4.0/2.4.3b) + `TestFR010DateOverlay` switch cases (on/off differential, YAML + hot-reload round trip, partial POST keeps the value, page shows stored state, 2.4.2) | **100** | **100** | **0** | **100%** |

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
| Shot-id sanitisation, archiving a pair, grouped reader, **per-shot** pruning (a shot is dropped whole — the 2.4.3 split lock, the pruner/reader agreement, names without a shot id left alone), live-slot safety, end-to-end prepare, option round-trip (M2) | **24** | **24** | **0** | **100%** |

### 3.5 Live tier (opt-in) — `tests/test_live.py`  *(ComfyUI cases added in v2.4.0)*

| Scope | Tests | Passed | Failed | Pass Rate |
|-------|-------|--------|--------|-----------|
| 5 Immich cases (L01–L05) + 3 ComfyUI cases (L09 built-in graph, L10 selection round trip, L10b real exported graph) against the reference environment of §7.1 | **8** | **8** | **0** | **100%** |

**Total: 213 collected — 205 passed offline + 8 skipped; the 8 live cases pass in the L1 run (§6.1,
re-run green 2026-11-22, §6.9) → 213/213, 0 failed (100 %).**

---

## 4. Requirements Coverage

The full case catalogue and the per-requirement coverage matrix are maintained in
[`docs/test_specification_aspice.md`](test_specification_aspice.md) (EPF-TST-001). Compared with
the v1.x report, this release **adds coverage** for the multi-source feature set:

- **FR-027** — image-source selection (`immich` / `comfyui_ha` / `comfyui_direct`): covered.
- **FR-028** — ComfyUI via Home Assistant (`ai_task.generate_image`): covered (unit + integration).
- **FR-002** — album-asset retrieval is now asserted against the **v3 `search/metadata`** endpoint (14.3).
- **FR-032 / TC-FR-032 — gallery history** (features 2.2.0–2.3.0; per-shot pruning 2.4.3): covered
  by **24** automated cases in `tests/test_gallery_history.py`; the requirement and test-case IDs were
  added to EPF-REQ-001 / EPF-TST-001 in the 2.3.0 revision, and both were re-worded for the per-shot
  pruning in the 2.4.3 revision.
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
collected 213 items

tests/test_functional.py      :: 100 passed
tests/test_nonfunctional.py  :: 27 passed
tests/test_providers.py      :: 54 passed
tests/test_gallery_history.py :: 24 passed
tests/test_live.py           :: 8 skipped (opt-in, no .env in the offline run)
======================= 205 passed, 8 skipped in 23.34s ========================
```

> **First CI run of this job** (GitHub Actions, 2026-11-22, run `121969072464`): **205 passed,
> 8 skipped in 18.66 s — job green**, same suite, same image build. The junit artifact step was dead
> weight in its first version: the XML was written *inside* the `--rm` container, so the copy step
> copied from a container in which pytest had never run. It now mounts the report directory into the
> container and points `run.test.sh` at it via `EPF_JUNIT_XML` (default unchanged for local runs);
> verified before pushing — the report lands on the host and parses as 213/0/0/8. **Re-run after the
> fix** (run `121972075681`, same day): **205 passed, 8 skipped in 30.39 s**, nothing red, and the
> `junit-l0` artifact really uploaded — so DoD line 1 now rests on CI, not only on a local Docker run.

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

*Re-run on this code base 2026-11-22: **8/8 green in 40.2 s** — §6.9.*

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
2. **The per-pattern cap can split a pair — closed in 2.4.3.** Pruning counted files *per pattern*, so
   a shot could be left with only its original or only its processed file (seen live: `sim2` kept its
   original, lost its processed file) — the plan worded the limit as "max. **pairs**". **Decision taken
   and implemented (2.4.3):** prune **per shot** — both limits drop a shot complete, a shot's age is
   the mtime of its newest member (the key the reader sorts by), and names without a shot id are left
   alone; so the cap means shots on both sides and the two views agree. The live preview directory
   (`POST /cleanup-previews`) keeps the per-pattern behaviour — it holds the single live slot, not
   groups (**FR-024** unchanged). Three lock cases in `tests/test_gallery_history.py`: the cross-mtime
   layout this very run produced (per-pattern pruning would split it), the pruner/reader agreement, and
   the name-without-id rule; see §6.7. Related, already accepted as the 14.12 trade-off: the generation
   counter lives per process and is rebuilt on hot reload — the live run reported `count_today: 1`
   after two generations.

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

### 6.6 L0/L1/L3 re-run for 2.4.2 — the global date-stamp switch on the shipped image (run 2026-11-17)

The switch is a pipeline control, so it is proven on the **shipped production image** against the real
Immich of §7.1, driven through the browser's own path (form `POST` → runtime YAML → watchdog → provider
→ generation):

| Check | Result |
|-------|--------|
| Production image via the real s6 init path, env from the git-ignored `.env` | boots healthy; footer **v2.4.2** ✓ |
| Settings page renders the new control | `name="date_overlay"` present; after a save the page shows the **stored** state ✓ |
| Form `POST` Enabled | `200` → runtime YAML `date_overlay: true` → watchdog → provider rebuild ✓ |
| `POST /prepare-photo`, real Immich photo with real EXIF date | `200`; log **`Date overlay: <the photo's date>`**; three previews stored; the bottom-right stamp rectangle is present in the served processed preview ✓ |
| Form `POST` Disabled → same pipeline, next photo | YAML `date_overlay: false`, hot reload fires; log shows **no** overlay line and the stamp is gone ✓ |
| `POST` without the field | stored value survives ✓ (silence is not a click) |
| `/download` contract (regression) | `200`, `frame.txt`, `text/plain`, 16 tokens/row, **no `};` tail** ✓ |
| `/health`, `/sleep` | Immich **connected** (env secret channel intact) ✓, sleep window answers ✓ |
| L0 offline suite | **199 passed, 8 skipped** (the four new cases included) ✓ |
| L1 live tier | **8 passed** in 26.9 s ✓ |

**What this proves:** the switch is wired end to end on the image that ships — page → runtime YAML →
hot reload → pipeline — and the differential (stamp drawn vs. stamp absent on the same kind of real
photo) is the evidence the L0 differential test predicts the field behaviour.

**Harness notes from this run** (they bit once each, both are documented in `AGENTS.md` §Gotchas):
building the production image from the add-on directory **bakes a developer's local `config/` and
`photos/` into the image** when they exist in the build context (in HA the bind mount shadows them);
and a standalone smoke must keep `/init` as PID 1 and start gunicorn through the **real** `with-contenv`
path, because Docker's container environment reaches the main program only through it — a bare
`--entrypoint` override loses it, and Git-Bash mangles leading-slash arguments unless
`MSYS_NO_PATHCONV=1` is set.

---

### 6.7 L0 re-run for 2.4.3 — gallery pruning keeps a shot whole (run 2026-11-20)

Closes live finding **2** of §6.3. The pruning unit moved from *files per pattern* to *whole shots*
(`app.py:_gallery_groups`, `app.py:_cleanup_previews_per_shot`, reached through
`cleanup_gallery(group_by_shot=True)`); the live preview directory keeps the old per-pattern path
(`FR-024`, `POST /cleanup-previews`), because there is nothing to group there.

| Check | Result |
|-------|--------|
| **L0 offline suite** (the tier that owns this behaviour) | **202 passed, 8 skipped in 24.4 s** (2026-11-20) ✓ — gallery file **24** (21 + 3 new) |
| Pruning caps by **shots** | cap 3, six shots → the newest **three shots** survive, each with **both** of its files ✓ |
| **The split lock** (this run's finding, reproduced) | mtimes crossed so the two patterns disagree about the newest three: per-pattern pruning leaves **four** shots on disk, two of them half-pairs (`id3` original-only, `id0` processed-only) — per-shot pruning keeps exactly the three newest shots **complete** (`id0`/`id2`/`id3`) and drops `id1` whole. Proven both ways: forcing the pruner back to per-pattern makes this case fail (23 passed, 1 failed) ✓ |
| Pruner and reader agree | after pruning, what `/api/gallery-previews` reports is what is on disk (cap 3 → 3 shots, 6 files) ✓ |
| Names without a shot id | a stray file in the gallery dir is neither deleted nor counted against the cap ✓ |
| Age eviction | a shot older than the retention window is deleted **whole** ✓ (pre-existing case, still green) |
| Live-slot regression | `latest_original.jpg` untouched by gallery pruning ✓ (pre-existing case, still green) |
| Live-preview cleanup (`FR-024`) | per-pattern behaviour unchanged ✓ (pre-existing cases, still green) |
| **L1 live tier** | re-run green on this code base 2026-11-22 — §6.9 (the release gate is closed) |
| **L3 production-image smoke** | re-run green on this code base 2026-11-22, **with more shots than the cap** (cap 2, three real preparations) so the shipped pruner really ran — §6.9 |

**What this proves:** the behaviour that the live run falsified is now pinned by a test — and pinned by
a case that **fails under the old semantics** (the crossed-mtime layout), not just by a case that would
also pass under them, which is what the old "each kind to max count" case was: its assertions held
under both readings, so it proved nothing about the unit. The pruner and the reader now share one
measure, so the setting has one meaning.

### 6.8 L0 re-run for 2.4.3b — the settings page stops guessing (run 2026-11-20)

Closes the two items `plans/ui-modernisierung.md` §9 had left open for the next release. Both are
about the same shape of failure: **the page said "Settings saved" and quietly did nothing.**

| Check | Result |
|-------|--------|
| **L0 offline suite** (the tier that owns both behaviours) | **205 passed, 8 skipped in 24.9 s** (2026-11-20) ✓ — functional file **100** (97 + 3 new) |
| **A slot with content but no name** is refused | pasting an API graph into slot 1 and saving now answers **400** naming the slot, instead of storing nothing. Locked by `TestFR033WorkflowSelection::test_slot_content_without_a_name_is_refused`; **proven both ways** — disabling the guard makes exactly this case fail (302, the old "saved" redirect) while its sibling case stays green ✓ |
| An **empty slot** is still just an empty slot | naming nothing and posting nothing keeps the stored list ✓ (pre-existing case) |
| **An emptied field** still overwrites | prompt set, then saved empty → the YAML holds empty. That is intentional (the form always sends its controls; only a *missing* field keeps its value), now pinned by `TestFR021SettingsVocabulary::test_empty_field_overwrites_and_the_ui_warns` ✓ |
| The page **warns before** that overwrite | a confirmation naming the fields that would go from stored to empty, reusing the existing modal machinery ✓ — markup pinned by the same case, **looks** still to confirm in a browser (§6.5) |
| Traceability | EPF-TST-001 gained **TC-FR-027 … TC-FR-031** for FR-027 … FR-031 (they had no documented case since v1.2.0, though the tests ran all along); the matrix now names all **55** requirements |
| **L1 live tier / L3 production smoke** | re-run green on this code base 2026-11-22 — §6.9; the guard and the overwrite were additionally confirmed **over HTTP on the shipped image** |

**What this does not prove:** the warning is a browser-side interaction. The offline tier pins the
markup and the server behaviour; whether the dialog reads well on a phone, in dark mode, and through
HA ingress is still the §6.5 checklist.

### 6.9 L1 + L3 re-run on this code base (run 2026-11-22) — the last two automatable gates

**L1 — live integration** (`run-live-tests.sh`, reference environment §7.1, `.env` unchanged):
**8 passed in 40.2 s** — L01–L05 (album resolve, v3 paged `search/metadata`, original download,
selection, the add-on `/download` route end to end) **and** L09/L10/L10b (built-in graph, named-workflow
selection, a real exported graph) — with **three real GPU generations**, which is why this tier only
runs with consent. The `comfyui_ha` leg still has no token/entity id and remains the one untested leg.

**L3 — production-image smoke** (shipped `Dockerfile` built from this tree, amd64, started through its
normal s6 init, gunicorn 2×2 via the real `with-contenv`, secrets via `--env-file` with LF, empty named
volumes so nothing was baked in):

| Check | Result |
|-------|--------|
| `/health` — also the Docker `HEALTHCHECK` path (`wget --spider`) | **healthy**, source **Immich**, status **connected** to the real server ✓ |
| `/sleep` | answers; next wakeup from the configured window ✓ |
| `/download` — the ESP32 contract | `frame.txt`, `text/plain`, 2-hex tokens, newline every 16, **no closing `};`** ✓ |
| **Per-shot pruning on the shipped image** — run **over** the cap: cap 2, three shots prepared against a real Immich | after every prepare the archive holds **two shots, each with both files**; the oldest shot is gone **whole** — pairs stay pairs ✓ |
| Pruner/reader agreement on disk | `GET /api/gallery-previews` → `count: 2` = two shots, four files ✓ |
| Live preview slot | `latest_*` untouched by gallery pruning ✓ |
| Watchdog hot reload on the shipped image | `POST /` → “Config modified, reloading…” → every worker updated ✓ |
| **Settings guard over HTTP on the shipped image** (2.4.3b) | content + no name → **HTTP 400** naming slot 1; the same content **with** a name → accepted and stored ✓ |
| **Emptied field overwrites** (2.4.3b, shipped) | `prompt: hello-l3-probe` → POST empty → `prompt: ''` ✓ — the browser dialog is the new part in front of it |
| Footer (derived, never hand-edited) | version **v2.4.3** ✓ from the manifest; the build date showed the cached `.build_stamp` layer (this build reused it) — cosmetic, the chain is unchanged |
| Ingress / ProxyFix | not exercisable outside Home Assistant ✓ documented |

**Consequence:** the three automatable tiers (**L0, L1, L3**) are green on this code base, so the
release gate of the top-level goal is met. Open and **not automatable from here**: the browser
acceptance incl. the new save-time dialog (§6.5), finding **14.9**, the `comfyui_ha` live leg, the
multi-day field run (EPD wear), and the **human QA signature** (§8).

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
| Test Manager | EPF Project | 2026-11-22 | - |
| Quality Assurance | - | - | *(human signature still outstanding)* |
| Project Lead | EPF Project | 2026-11-22 | - |

---

*Regenerated for code base **v2.4.3** (incl. revision **2.4.3b**) on branch `main`, 2026-11-22:
**205** offline cases pass (**L0**, 23.3 s) — the **3** cases of §6.7 and the **3** of §6.8 included —
and the two automatable gates that were open last pass are now closed on **this** code base (§6.9):
**L1** 8/8 against a real Immich *and* a real ComfyUI (40.2 s, three real GPU generations) and the
**L3** production-image smoke, run with **more shots than the cap** so the shipped per-shot pruner
really executed, plus the two 2.4.3b settings behaviours over HTTP on the shipped image.
**213/213, 0 failed (100 %)** across L0+L1. The catalogue side is aligned: **FR-032** re-worded in
EPF-REQ-001, **TC-FR-032** extended and **TC-FR-027 … TC-FR-031** added in EPF-TST-001, so its
traceability names all 55 requirements; CI runs L0 on every push/PR (`.github/workflows/l0.yml`).
Live finding 2 of §6.3 and the two plan §9 items stay closed. Still open (not automatable here): the
browser-side visual acceptance incl. the new save-time warning dialog (§6.5, §6.8), finding **14.9**,
the `comfyui_ha` live leg, the L4 field run on a real frame — see `plans/findings.md` — and the **human
QA signature** of §8, which is what the v2.4.3 tag still waits for.*
