# Land Taxonomy Classifier

A modular pipeline that classifies herbarium specimen records from the BGBM dataset against CORINE Land Cover (CLC) habitat categories. It also identifies the specimen taxonomy. Part of the broader BiodivPipeline project for FAIR biodiversity data processing.

## Overview

The pipeline takes a CSV of herbarium records as input and produces a classified output CSV with CLC habitat codes derived from locality and habitat description fields. It also returns GBIF identifiers or WFO keys for each record.

It consists of two services:

- **land-taxonomy-api**: an existing FastAPI service that classifies free-text habitat descriptions against 64 CLC categories using an LLM (Source: https://github.com/biodivportal/land-taxonomy-classifier)
- **classifier-module**: a new Python service that reads the input dataset, calls the API for each record, and writes structured output

## Project Structure

```
land-taxonomy-classifier/
├── land-taxonomy-api/        # Existing service, unmodified except main.py
│   ├── main.py               # Added Ollama support and enhanced prompt template to ensure a more objective evaluation
│   ├── taxonomy.csv
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── README.md
│
├── classifier-module/        # New service
│   ├── classify.py           # Classify each row using LLMs using the main.py file in the land-taxonomy-api folder
│   ├── pipeline.py           # Pipeline for processing csv files
│   ├── main.py               # FastAPI endpoints
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
  - Ollama can be used instead if there is no API key available.

## Setup

### 1. Clone the repository

```bash
git clone <repo-url>
cd land-taxonomy-classifier
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

Call `http://0.0.0.0:8001/docs` and use the classify function to add input data.

| Column | Description |
|--------|-------------|
| `HerbariumID` | Unique record identifier |
| `Locality` | Free-text locality string |
| `FundortUNdOeko` | Habitat and ecology description (optional, preferred over Locality when present) |
| `FullNameCache` | Free-text scientific plant name |
| `Genus` | Free-text plant genus |
| `Family` | Free-text plant family |

Output is written to `./data/output.csv`.

## Output Format

Each row in the output CSV corresponds to one input record:

| Column | Description |
|--------|-------------|
| `HerbariumID` | Record identifier, for joining with input data |
| `clc_code` | CORINE Land Cover level 3 code (e.g. `311`) |
| `clc_name` | CLC category name (e.g. `Broadleaved Forest`) |
| `clc_confidence` | Match confidence score (0.0-1.0) |
| `clc_reason` | LLM explanation for the match |
| `clc_summary` | Short summary of the classified habitat |
| `clc_source_field` | Whether `FundortUNdOeko` or `Locality` was used as input |
| `taxon_identifier` | GBIF identifier (or WFO key) of given plant |
| `taxon_confidence` | Confidence of identifier |
| `taxon_source` | Whether the identifier is from GBIF or WFO |
| `taxon_status` | Can be `resolved`, `fuzzy` or `unresolved` |
| `error` | Contains any errors when processing row |

## Notes

- Classification quality depends heavily on input text. Records with only place names (e.g. "Bayern, SW Grainau") produce lower-confidence, less specific results than records with actual habitat descriptions (e.g. "Weinbergshang").
- `FundortUNdOeko` is populated in approximately 26% of BGBM records; `Locality` covers 99.4%.
- The OpenAI API is called once per record. At 100k records, costs are non-trivial; consider using a smaller sample for development. Replacement with a local Hugging Face model is planned for the optimisation phase.
- `llama3.2` and `gpt-4o-mini` do not return the same results. A decision needs to be made on what model will be used at the end.
- Ollama might require a few minutes on the first compose call to download the required image. In later calls, the image will be cached so it is a one time thing.
- Some times ollama might time out, retrying the input should work.

## Planned Extensions

- Nextflow module for nf-core pipeline integration
- Async batching for improved throughput
- Save processed identifiers to reduce api load.

## AI Assistance

This project was developed with the assistance of Claude for 
architectural guidance, code review, and documentation.
All code has been reviewed and tested by the authors.
