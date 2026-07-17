# Land Taxonomy Classifier (WP3)

Takes a CSV of herbarium specimen records and returns a CORINE Land Cover (CLC) code and a GBIF backbone identifier for each row. The GBIF backbone identifier is resolved from the plant name, family and genus. To obtain the CLC code, an LLM uses free-text locality description and plant data (refined through GBIF output) and analyzes those. \
Both are returned together, joined by record ID.

Part of the BiodivPipeline project, where it runs as the `TAXONOMY_CLASSIFY` Nextflow module. It also runs standalone as a FastAPI service or a batch CLI.

**Scope.** Land classification is inferred from text, not from coordinates.

## Quickstart

### Requirements
- Docker + Docker Compose
- An OpenAI API key

### Setup
```bash
cp .env.example .env
# edit .env and change environment variables as desired
```

### Run the batch CLI (what the pipeline uses)
```bash
docker compose run --build --rm classifier \
  python -m app.cli --input <path-with-input.csv> --output <path-with-output.csv>
```

### Run as an interactive service
```bash
docker compose up --build
```
Open `http://localhost:8000/docs`.
- `POST /classify/csv`: upload a CSV, get back either a JSON or a processed CSV

### Run NF pipeline test
From the root folder:
```bash
nf-test test modules/local/taxonomy_classify/tests/main.nf.test
```

## Input

A CSV of herbarium records. Delimiter is auto-detected (comma or semicolon). Extra columns are ignored.

| Column | Role |
|---|---|
| `HerbariumID` | Record identifier. Falls back to the row index if absent. |
| `FullNameCache` | Scientific name (with authorship) sent to GBIF |
| `Genus`, `Family` | Sent to GBIF as matching context |
| `FundortUNdOeko` | Habitat/ecology text — **preferred** input for classification |
| `Locality` | Free-text locality — used when `FundortUNdOeko` is empty or redundant |
| `Anmerkungen` | Checked for cultivation markers (`cult.`, `kult`, `garten`, `garden`) so garden-grown specimens aren't classified by their natural habitat |
| `Latitude`, `Longitude` | Not used at runtime. |

**Column names are configurable.** Every column above is defined in `app/config.py` (`ID`, `NAME`, `GENUS`, `FAMILY`,  `LOCALITY_LABELS`, `CULTIVATED_FIELD`). For a dataset with different headers, remap them there. Because
the labels the LLM sees are built from these same settings, remapping columns also controls what the prompt contains.

### Row handling
Every input row produces exactly one output row; nothing is filtered out.

- **No usable locality text**: a warning is logged, no LLM call is made, and the land-cover fields come back empty (`llm_confidence` null, `llm_code` empty).
- **No scientific name**: no GBIF call; taxonomy fields come back empty with `taxon_status: unresolved`.

## Output

One row per input record, joinable on `id`. The pipeline runs in two phases: GBIF taxonomy is resolved once for the whole dataset first, then land classification runs in batches. This approach allows the classifier to use taxonomy results as additional context.

### Land cover (LLM)
| Column | Description |
|---|---|
| `id` | `HerbariumID` from the input |
| `llm_code` | CORINE Level-3 code, e.g. `311` |
| `llm_name` | CLC category name for that code |
| `llm_confidence` | `0.0`-`1.0`, self-assigned by the model against a fixed rubric |
| `llm_reason` | The model's justification for the top match |
| `llm_input` | The exact text sent to the model |
| `llm_all_matches` | The top-N candidates (default 3): code, name, confidence, reason. JSON string in CSV output, nested array in JSON output. |
| `llm_model`, `llm_prompt_variant`, `llm_top_n` | Run configuration |
| `llm_prompt_tokens`, `llm_completion_tokens`, `llm_cached_tokens` | Cost accounting |
| `llm_parse_failure` | Model output could not be parsed as JSON |
| `llm_unknown_code` | Model returned a code not in the CLC taxonomy |
| `llm_error` | Error text; empty on success |

### Taxonomy (GBIF)
| Column | Description |
|---|---|
| `taxon_key` | GBIF backbone key |
| `taxon_link` | Resolvable GBIF species URL |
| `taxon_confidence` | GBIF match confidence, `0`-`100` |
| `taxon_status` | `resolved` / `fuzzy` / `unresolved` / `error` (see below) |
| `taxon_canonical_name` | The name GBIF matched (may differ from the input name) |
| `taxon_rank` | `SPECIES`, `GENUS`, `SUBSPECIES`, … |
| `taxon_family` | Family from GBIF's classification — authoritative, may correct the input |
| `taxon_match_type` | `EXACT`, `FUZZY`, `HIGHERRANK`, `NONE` |
| `taxon_is_synonym`, `taxon_accepted_status` | Whether the matched name is a synonym |
| `error` | Row-level error; empty on success |

### `taxon_status`
- **`resolved`** — confidence ≥ 80 (`GBIF_CONFIDENCE_RESOLVED`) **and** match type
  is `EXACT` or `FUZZY`.
- **`fuzzy`** — a match was returned but didn't meet that bar. Note this includes `HIGHERRANK` hits *even at confidence 100*: hybrid resolving to its genus is
  `fuzzy`, not `resolved`.
- **`unresolved`** — no name supplied, or GBIF returned no match / no confidence.
- **`error`** — a transient GBIF failure (timeout, rate limit, auth). Safe to re-run; these rows are deliberately not cached.

### Reading the output correctly

- **Only a `resolved` taxon feeds the classifier as a clean name.** When status is `resolved`, the LLM receives GBIF's canonical name (rank-labelled, so a genus-only hit isn't presented as a species). For **any** other status — including `fuzzy` — the classifier falls back to the raw `FullNameCache` / `Genus` / `Family` from the input row. The GBIF *key* is never sent to the model. So an unresolved or fuzzy taxon still yields a land classification, just from unnormalised input.

- **Check `taxon_rank` before consuming `taxon_key`.** A `HIGHERRANK` match returns a valid key at *genus* level. The hybrid `Juncus effusus × Juncus inflexus` resolves to genus `Juncus` (key 2701072, rank `GENUS`) — a real key, but not a species. Consuming keys without checking rank silently mixes taxonomic levels.

- **The two confidences are unrelated.** `taxon_confidence` (0-100) is GBIF's `llm_confidence` (0.0-1.0) is the model scoring itself against a rubric that rewards specific habitat evidence in the text; it drives no logic and is not a calibrated probability. Do not threshold on it without validating it first.

- **High confidence ≠ correct.** The model reflects the text it was shown, not truth.

- **`taxon_is_synonym: true`** means the input name is outdated; `taxon_canonical_name` carries the currently accepted name.

- **Empty vs failed.** Empty fields mean the step was skipped (missing input); `llm_error` / `error` mean it was attempted and failed.

## Parameters

### Environment (`.env`)
| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | — | Required unless using other providers (to be implemented). |

### CLI arguments
| Argument | Purpose |
|---|---|
| `--input` | Path to the input CSV |
| `--output` | Path for the output CSV |

### Settings you may change (`app/config.py`)

These are the knobs meant to be tuned per dataset or per run.

| Setting | Default | What it does |
|---|---|---|
| `OPENAI_MODEL` | `gpt-5.4-mini` | Production model. Must appear in `MODEL_PARAMS` (`llm_lookup.py`) — an unlisted model runs without its per-model options (temperature / reasoning effort). |
| `GBIF_CONFIDENCE_RESOLVED` | `80` | Confidence threshold (0–100) at or above which a GBIF match counts as `resolved`. Below it, the match is `fuzzy` and the classifier falls back to the raw input name. |
| `BATCH_SIZE` | `10` | Rows classified concurrently per batch. Isolation/chunking only — it does **not** control throughput (the token bucket does). |
| Column names | see file | `ID`, `NAME`, `GENUS`, `FAMILY`, `LAT`, `LON`, `CULTIVATED_FIELD`, `LOCALITY_LABELS`, `FIELD_LABELS`. Remap these to match a dataset with different headers. `LOCALITY_LABELS` is priority-ordered — the first present field wins. |

### Settings you should recognise but rarely touch

| Setting | Default | Notes |
|---|---|---|
| `DEFAULT_CONFIG['version']` | `5` | Prompt-staircase version, read by the CLI. v5 = structured fields + cultivation guardrail + top-3. Lower versions exist for evaluation and drop features (the cultivation guard only activates at v4+). This is the main lever on classifier behaviour. |
| `PRICES` | — | Per-model token prices used for cost estimates. Update when OpenAI pricing changes; has no effect on classification. |
| `GEE_PROJECT`, `GEE_MAP` | — | Used only by the evaluation tooling (`util/gee_mapping.py`) during evaluation. Not currently in the pipeline. |
| `DEFAULT_MODEL` | = `OPENAI_MODEL` | Convenience alias. |

### Fixed internals (not in config)

These are hard-coded and documented here only so their behaviour isn't surprising: the token bucket runs at 200k tokens/min × 0.8 safety with a small burst cap (`throttle.py`), and the failed-row retry pass is sequential. \
The limit (200k tokens/min) is dependent on the OpenAI tier of the account that provides the OpenAI API key that is used (this limit is the base limit).

> The CLI reads only `model` and `version` from `DEFAULT_CONFIG`. The other keys (`variant`, `taxa`, `use_species`) are defaults for calling `process_csv` directly, e.g. from the evaluation notebooks — setting them in config has no effect on a CLI run.