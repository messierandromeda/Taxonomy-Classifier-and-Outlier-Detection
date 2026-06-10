# Land Taxonomy Classifier

A modular pipeline that classifies herbarium specimen records from the BGBM dataset against CORINE Land Cover (CLC) habitat categories and resolves the specimen taxonomy against the GBIF backbone. Part of the broader BiodivPipeline project for FAIR biodiversity data processing.

## Overview

The pipeline takes a CSV of herbarium records as input and returns a classified output CSV with CLC habitat codes derived from locality and habitat description fields, together with a GBIF identifier for each record.
It consists of two services:

- **land-taxonomy-api**: a FastAPI service that classifies free-text habitat descriptions against the CLC categories using an LLM (Source: https://github.com/biodivportal/land-taxonomy-classifier). Modified to add Ollama support and an enhanced, rubric-based prompt for more objective confidence scoring.
- **classifier-module**: a new async Python service that reads the input dataset, calls the land-taxonomy-api and GBIF for each record in batches, and returns structured output.

## Project Structure

```
land-taxonomy-classifier/
├── land-taxonomy-api/        # Existing service, modified main.py only
│   ├── main.py               # Added Ollama support and rubric-based prompt
│   ├── taxonomy.csv
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── README.md
│
├── classifier-module/        # New service
│   ├── main.py               # FastAPI app and /classify endpoint
│   ├── pipeline.py           # Batch orchestration over the input CSV
│   ├── process.py            # Per-row classification logic
│   ├── land_taxonomy.py      # Client for the land-taxonomy-api
│   ├── taxonomy_lookup.py    # GBIF identifier lookup
│   ├── models.py             # Pydantic models (input, output, API responses)
│   ├── config.py             # Constants, thresholds, logging setup
│   ├── requirements.txt
│   └── Dockerfile
│
├── data/                     # Mount point for output CSVs (not versioned)
│   └── output.csv
│
├── docker-compose.yml
└── README.md
```

## Requirements

- Docker
- Docker Compose
- An OpenAI API key
  - Ollama can be used instead if there is no API key available (intended for testing the pipeline end to end).

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd WP3-land-taxonomy-classifier
```

### 2. Configure environment

```bash
cp land-taxonomy-api/.env.example land-taxonomy-api/.env
```

Edit `.env` and add your OpenAI API key:

```
OPENAI_API_KEY=sk-your-key-here
```

### 3. Run the pipeline

```bash
docker compose up --build
```

### 4. Add input data

Open the interactive docs at http://0.0.0.0:8001/docs and use the POST /classify endpoint to upload an input CSV. Set the use_ollama flag if you are running without an OpenAI API key. \
The endpoint returns the processed CSV as a semicolon-separated download. A copy is also written to ./data/output.csv (checkpointed periodically during long runs so progress is not lost). \
The input delimiter is auto-detected, so comma- or semicolon-separated inputs are both accepted.

| Column | Description |
|--------|-------------|
| `HerbariumID` | Unique record identifier |
| `Locality` | Free-text locality string |
| `FundortUNdOeko` | Habitat and ecology description (optional, preferred over `Locality` when present) |
| `FullNameCache` | Free-text scientific plant name |
| `Genus` | Free-text plant genus |
| `Family` | Free-text plant family |

Output is written to `./data/output.csv`.

## Output Format

Each row in the output CSV corresponds to one input record:

| Column | Description |
|--------|-------------|
| `id` | Record identifier, for joining with input data |
| `clc_code` | CORINE Land Cover level 3 code (e.g. `311`) |
| `clc_name` | CLC category name (e.g. `Broadleaved Forest`) |
| `clc_confidence` | Match confidence (0.0-1.0) |
| `clc_reason` | LLM explanation for the match |
| `clc_input` | Input that was given in row |
| `clc_source` | Which model produced the classification (`ollama` or `openai`) |
| `clc_field` | Whether `FundortUNdOeko` or `Locality` was used as input |
| `taxon_identifier` | GBIF backbone key of given plant |
| `taxon_confidence` | GBIF match confidence (0-100) |
| `taxon_status` | Can be `resolved`, `fuzzy` or `unresolved` |
| `error` | Contains any errors when processing row |

## Notes

- Classification quality depends heavily on input text. Records with only place names (e.g. "Bayern, SW Grainau") produce lower-confidence, less specific results than records with actual habitat descriptions (e.g. "Weinbergshang").
- `FundortUNdOeko` is populated in approximately 26% of BGBM records; `Locality` covers 99.4%.
- The OpenAI API is called once per record. At 100k records, costs are non-trivial; consider using a smaller sample for development.
- `llama3.2` and `gpt-4o-mini` do not return the same results. The production model is currently intended to be an OpenAI model (e.g. gpt-4o), subject to change after evaluation. Ollama exists so the pipeline can be run without an API key, not as a production target.
- On the first compose call, Ollama may need a few minutes to download the model image; it is cached for subsequent runs. The first inference also triggers a one-time model load, which the pipeline waits for via a warm-up request before processing begins.
- Records are processed concurrently in batches (see BATCH_SIZE in config.py).

## Planned Extensions

- Nextflow module for nf-core pipeline integration
- Caching of resolved GBIF identifiers to reduce repeated lookups and API load
- Recording the GBIF match rank (species / genus / family) alongside the identifier

## AI Assistance

This project was developed with the assistance of Claude for 
architectural guidance, code review, and documentation. \
All code has been reviewed and tested by the authors.