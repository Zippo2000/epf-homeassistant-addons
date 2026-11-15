# ComfyUI-Workflow-Auswahl (v2.4.0)

**Ziel:** Im Add-on den ComfyUI-Workflow **auswählen** (z. B. `flux-dev`, `qwen-2-1`), statt ein
einziges JSON-Feld umzuschreiben. Pro Workflow eigener Prompt/Parameter, Umschalten ohne
HA-Neustart (runtime YAML + Watchdog).

---

**Status:** **umgesetzt in v2.4.0** (2026-11-15). Phasen 1–3 sind drin; Phase 2 (§6) bleibt optional
und ist es auch — Grund siehe unten.

**Umsetzungsnachtrag (2026-11-15):**

* Runtime-YAML: `comfyui.workflows` (Liste) + `comfyui.active_workflow`; **Seed** über die zwei neuen
  Add-on-Optionen (`comfyui_workflows` als JSON-array, `comfyui_active_workflow`); danach gehört die
  Liste dem Settings-Page (Seed nur beim ersten Start, wie bei allen Runtime-YAML-Feldern).
* Settings-Page: Dropdown *(built-in)* + benannte Slots, vier Slots mit Name / API-JSON / Prompt /
  Negative / Node-Mapping / Steps / CFG / Sampler / Scheduler; validiert **beim Speichern**
  (eindeutige Namen, API-Format, Größengrenze, Auswahl muss zu einem Slot passen); wirkt ohne Neustart
  (Watchdog baut den Provider neu). Ein POST **ohne** Workflow-Felder lässt die gespeicherte Liste in Ruhe.
* Provider: Entry-Werte schlagen globale; **Node-Mapping vor dem generischen Scan** — erst dadurch wird
  Qwen (`TextEncodeQwenImage21.prompt`) ansprechbar, weil der Prompt dort in einem Nicht-`CLIPTextEncode`
  Eingang liegt; ein Graph mit eigenem Modell-Node lässt die Checkpoint-Suche weiterhin bleiben.
* Tests: 11 Provider-Fälle + 7 Settings-Fälle (offline), 3 Live-Fälle (TC-L09 eingebauter Graph,
  TC-L10 Auswahl-Roundtrip, TC-L10b echter Export-Graph vom Referenzserver).
  **L0 192 grün · L1 8 grün · Produktions-Smoke Report §6.4** (Seed → Dropdown, POST → YAML → Watchdog,
  echte Generierung `workflow=flux`, Validierungs-400er, `/download`-Vertrag unverändert).
* Nebenbefund aus dem Bau: die Slot-`label for` zeigen jetzt auf echte `id`s (waren dangling).
* **Offen geblieben:** Phase 2 — der Datei-Lese-Endpunkt am Referenzserver lieferte auf alle probierten
  Varianten nur das Verzeichnis-Listing, nicht den Dateiinhalt (Paste des Export-Graphen bleibt der
  supportete Weg) — und die **Paar-Aufteilungs**-Entscheidung (Report §6.3, Punkt 2).

---

## 1 · Ist-Stand (validiert, Stand 2.3.2)

`providers.py::ComfyUIDirectProvider` kann genau zwei Dinge:

| Modus | Verhalten | Beleg |
|---|---|---|
| `comfyui_workflow_json` **leer** | eingebauter Mini-Graph: `CheckpointLoaderSimple` + 2× `CLIPTextEncode` + `EmptyLatentImage` + `KSampler` + `VAEDecode` + `SaveImage`; Steps **20**, CFG **8,0**, `euler`/`normal` hart | `providers.py:584-630` |
| `comfyui_workflow_json` **gesetzt** | ersetzt den Graphen komplett, geht 1:1 an `POST /prompt` | `providers.py:612-624` |

* Injektion in ein fremdes JSON = **Scan** über alle Knoten nach `text` / `text_g` / `seed` / `width` / `height`.
  **Kein** Negative-Prompt, **kein** Steps/CFG/Sampler.
* Checkpoint: Option → Auto-Detect (erster Servereintrag) → Fallback; gilt **nur** für den eingebauten
  Graphen (fremdes JSON bringt sein Modell mit → kein `/object_info`-Lookup).
* **Format:** API-Format (`{"<id>": {"class_type": …, "inputs": …}}`). ComfyUis UI speichert
  **UI-Format** (`nodes`/`links`); der passende Export-Button heißt **„Save (Export)"**.
* **Ein** JSON-Feld ⇒ heute: Flux *oder* Qwen, Wechsel = JSON austauschen. Kein Dropdown.

### 1.1 Live-Messung am Referenzserver (2026-11-15)

| Messung | Ergebnis | Konsequenz |
|---|---|---|
| `GET /userdata?dir=workflows` | **Liste** (7 Dateien) | Auflisten möglich |
| Dateiinhalt derselben Route (`file=`, `filename=`, Pfadstil, `/api/`-Präfix) | liefert immer die **Liste** | Inhalt-Lesen ungelöst ⇒ UI→API-Import **optional** |
| `GET /history` | API-Format-Graphen, 8 Einträge; Qwen-Graph: 9 Knoten | **validierter Import-Weg** („letzter Lauf") |
| Qwen-Graph-Knoten | `TextEncodeQwenImage21` mit Input **`prompt`**, Save via `SaveImageAdvanced` | Prompt-Injektion braucht **Node-Mapping**; `SaveImage`-Annahme aufbrechen |
| Flux-Graphen (Referenz) | `CheckpointLoaderSimple` + `CLIPTextEncode(text)` | funktionieren schon heute per Paste |

**Folge-Diagnose (Mitliefernder Bug):** ein Qwen-Workflow bekommt heute **nie** den Add-on-Prompt —
der Scan kennt nur `text`/`text_g`. Ohne dieses Feature bleibt das ein stiller Fehler.

---

## 2 · Design (entweder/oder entschieden)

### 2.1 Speicherung

Nur in der **runtime YAML** (das HA-Optionsfeld ist für JSON zu groß; passt zur Entscheidung (b)
aus 2.3.2: Settings-Seite = Editing-Ort, HA-Optionen = Seed + Secrets).

```yaml
comfyui:
  active_workflow: qwen-2-1          # '' = eingebauter Graph (Verhalten wie bisher)
  workflows:
    - name: flux-dev
      api_json: '{"3": {"class_type": "KSampler", ...}}'   # API-Format (ComfyUI „Save (Export)")
      prompt: "cinematic landscape, {season}"              # optional, sonst globaler Prompt
      negative_prompt: ""                                  # optional
      prompt_node: ""            # leer = heutiger Scan
      prompt_input: text
      negative_node: ""
      negative_input: text
      seed_node: ""
      steps: 20
      cfg: 3.5
      sampler: euler
      scheduler: normal
    - name: qwen-2-1
      api_json: '...'
      prompt_node: '459:452'
      prompt_input: prompt
      seed_node: '373'
```

**Formular:** feste **4 Slots** (`wf_1_*` … `wf_4_*`), Feldnamen = YAML-Schlüssel pro Slot
(2.3.2-Vokabularregel). Der Server baut die Liste aus dem POST neu auf und verwirft namenlose Slots.
Dropdown „Active workflow" = `(built-in)` + die vier Namen. Slots 1–2 ausgeklappt, 3–4 in `<details>`.

### 2.2 Geltungsbereich je Feld (Doku-Tabelle, weil sonst Verwirrung)

| Feld | eingebauter Graph | eigenes API-JSON |
|---|---|---|
| `prompt` / `negative_prompt` | ✅ (heutige Knoten 6/7) | ✅ über Node-Mapping, sonst Scan |
| `prompt_node` / `prompt_input` / `negative_node` / `negative_input` / `seed_node` | — (entfällt) | ✅ neu |
| `steps` / `cfg` / `sampler` / `scheduler` | ✅ neu konfigurierbar | ❌ (stehen im JSON) |
| `width` / `height` / `seed` (global) | ✅ | ✅ (Scan setzt `width`/`height`/`seed`) |
| `checkpoint` | ✅ (nur hier relevant) | ❌ (Modell steht im JSON) |

### 2.3 Regeln

1. **Abwärtskompatibilität:** kein `workflows`/`active_workflow` in der YAML → Verhalten **exakt** wie
   heute (eingebauter Graph oder `workflow_json`-Feld). Bestandene Tests bleiben grün.
2. `active_workflow` = `''` → eingebauter Graph mit globalen Werten (plus `workflow_json`-Alias-Feld).
3. `active_workflow` = Name → Eintrag; leere Eintragsfelder fallen auf global zurück.
4. **Validierung beim Speichern:** Namen eindeutig, `api_json` muss lesbarer Node-Dict sein (sonst
   **400** + Log, kein stilles Unter-den-Tisch-Fallen), max. 4 Slots, JSON-Fenstergröße begrenzt
   (`wf_json_max_bytes`, Default 64 KiB — ein Flux-Export ist ~20-40 KB).
5. **Injektion** zentral in `_inject_into(workflow, entry)`; Node-Mapping gewinnt, sonst Scan.
6. Save-Erkennung: `/history/<id>` → `outputs[*].images[0].filename` (funktioniert für
   `SaveImageAdvanced` nachweislich ✓, kein `SaveImage`-Zwang mehr in der Doku).
7. `comfyui_ha`-Pfad (HA-`ai_task`-Service) ist **nicht** betroffen — Workflow-Auswahl gehört dort an
   die HA-Service-Seite; im README explicit sagen.

---

## 3 · Touchpoints

| Datei | Änderung |
|---|---|
| `providers.py` | `ComfyUIDirectProvider`: `workflows`/`active_workflow`-Parameter, `_resolve_entry()`, `_inject_into()`, Steps/CFG/Sampler/Scheduler für den eingebauten Graphen konfigurierbar; Factory reicht durch |
| `app.py` | `DEFAULT_CONFIG['comfyui']` + `workflows`/`active_workflow`; POST-Handler: Slot-Felder → Liste, Validierung (400), `update_app_config`-Pfad bleibt |
| `templates/settings.html` | „ComfyUI Workflows"-Card: Dropdown + 4 Slots (2 offen, 2 `<details>`), Channel-Badge `runtime YAML` |
| `config.yaml` / `run.sh` | Version `2.4.0`; **keine** neuen HA-Optionen (begründen: YAML-Kanal) |
| `tests/test_providers.py` | ~8 neue Fälle |
| `tests/test_functional.py` | ~5 neue Fälle (Formular + POST + Validierung) |
| `epf-eink-addon/README.md`, `ARCHITECTURE.md`, `AGENTS.md` | Doku (Abschnitt 5) |
| `docs/requirements_specification_aspice.md` | **FR-033 ComfyUI Workflow Selection** (+ Zählung 33) |
| `docs/test_specification_aspice.md` | **TC-FR-033** (13 Fälle), Stand 2.4.0 |
| `docs/test_report_aspice.md` | Neu ausgezählt + **§6.4 Live-Leg Flux/Qwen** |
| `epf-eink-addon/CHANGELOG.md` | 2.4.0-Eintrag |

## 4 · Testplan

**L0 (offline, Pflicht-Gate):**
1. ohne Liste → eingebauter Graph unverändert (Regression)
2. Liste + `active_workflow` → gewählter `api_json` landet bei `/prompt`
3. Node-Mapping: Prompt landet im Qwen-Knoten-Input `prompt` (Der-Bug-Fall)
4. Node-Mapping seed + negativer Prompt
5. Eintrags-Prompt gewinnt gegen global; leere Felder fallen auf global zurück
6. Steps/CFG/Sampler/Scheduler wirken auf den eingebauten Graphen
7. `api_json` ungültig → 400 (POST-Validierung)
8. Doppelte Namen → 400
9. JSON zu groß → 400
10. POST schreibt Liste + `active_workflow` in die YAML (Round-trip) und Watchdog/Provider-Rebuild
11. Legacy: nur `workflow_json` gesetzt → unverändertes Verhalten
12. Render-Test: Dropdown + Slots + Badge
13. `max_generations_per_day` pro Quelle unverändert (Regression)

**L1** (echtes Immich): 5 Fälle bleiben grün. **L3** (Produktions-Image): Smoke wie bisher.

**L3c — Live-Nachweis ComfyUI (Referenzserver), manuell/semi-automatisch:**
1. Zwei echte Einträge anlegen: `flux-dev`, `qwen-2-1` (API-JSON je aus `/history` eines echten Laufs
   — validiert, dass der Weg funktioniert; ComfyUI-„Save (Export)"-Pfad dokumentieren)
2. Über das Formular speichern → YAML → Hot Reload (kein Neustart)
3. **Flux:** echte Generierung, Bild kommt zurück, Prompt ist im JSON **ausgewechselt** (Nachweis:
   gerenderter Prompt ≠ eingebetteter)
4. **Qwen:** gleiche Prüfung — hier **muss** der Node-Mapping-Pfad greifen (sonst alter Bug)
5. Umschalten `active_workflow` per Formular → nächste Generierung nutzt den anderen Graphen
6. Limits/Galerie/Archiv-Hook verhalten sich wie in 2.3.x (Regression)

**Nicht automivar:** L4 am echten Frame.

## 5 · Doku-Endzustand

README (Add-on): Workflow-Liste als eigenes Kapitel, Format-Hinweis „API-Format / Save (Export)",
Pro-Feld-Geltungstabelle, „Save (Export)"-Schritt-für-Schritt, Hinweis `comfyui_ha` ausgenommen.
ARCHITECTURE: Provider-Komponente + Design-Entscheidung (Warum Paste statt Server-Import).
AGENTS: Vokabular-Regel extends auf `wf_N_*`; klarstellen welcher Kanal was hält.
ASPICE: FR-033 / TC-FR-033 / Report-Neuauszählung + §6.4. `plans/*-Status` am Ende aktuell.

## 6 · Optional (Phase 2, nicht in 2.4.0)

„Aus ComfyUI importieren": Server-Liste (`/userdata?dir=workflows`) → Dateiinhalt (Route erst klären)
→ **UI→API-Konverter** (Nodes/Links → `{id:{class_type,inputs}}`, Widget-Reihenfolge aus
`/object_info`, ~50-70 Zeilen, Risiko: Custom-Nodes). Nutzen-bringender Vorab-Schritt:
**„Import from last run"** über `/history` (API-Format, ~15 Zeilen, validiert).

## 7 · DoD

L0 grün (alle neuen Fälle), L1 grün, L3+L3c nachgewiesen, Doku (README/ARCHITECTURE/AGENTS/ASPICE/
CHANGELOG/Pläne) nachgezogen, Version `2.4.0`, keine Secrets/Umgebungs-Werte in getrackten Dateien,
Commit/Tag/Push erst nach Go.

**Ergebnis 2026-11-15:** erfüllt — L0 **192/192** (19,2 s), L1 **8/8** (26,0 s, echte GPU-Generierungen
inkl. echtem Export-Graph), Produktions-Smoke mit Seed → Dropdown → POST → Watchdog → Generierung
(Report §6.4); Doku und ASPICE nachgezogen; Version `2.4.0`; Secret-Scan über alle getrackten Dateien
unauffällig (IP/Hostname/Checkpoint-Namen/Key-Muster je 0, `.env` weiterhin ungetrackt). **Commit/Tag/
Push stehen noch aus — warten auf Go.** Schwebend wie zuvor: browserseitige Abnahme in einem echten HA
und der L4-Feldlauf (nicht laborautomatisierbar).
