# Land Taxonomy Classifier

A modular pipeline that classifies herbarium specimen records from the BGBM dataset against CORINE Land Cover (CLC) habitat categories. Part of the broader BiodivPipeline project for FAIR biodiversity data processing.

## Overview

The pipeline takes a CSV of herbarium records as input and produces a classified output CSV with CLC habitat codes derived from locality and habitat description fields.

It consists of two services:

- **land-taxonomy-api**: an existing FastAPI service that classifies free-text habitat descriptions against 64 CLC categories using an LLM (Source: https://github.com/biodivportal/land-taxonomy-classifier)
- **classifier-module**: a new Python service that reads the input dataset, calls the API for each record, and writes structured output

## Project Structure

```
land-taxonomy-classifier/
├── land-taxonomy-api/        # Existing service, unmodified
│   ├── main.py
│   ├── taxonomy.csv
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── README.md
│
├── classifier-module/        # New service
│   ├── classify.py
│   ├── requirements.txt
│   └── Dockerfile
│
├── data/                     # Mount point for input/output CSVs (not versioned)
│   ├── input.csv
│   └── output.csv
│
├── docker-compose.yml
└── README.md
```

## Requirements

- Docker
- Docker Compose
- An OpenAI API key

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

### 3. Add input data

Place your input CSV at `./data/input.csv`. The file must contain at least the following columns:

| Column | Description |
|--------|-------------|
| `HerbariumID` | Unique record identifier |
| `Locality` | Free-text locality string |
| `FundortUNdOeko` | Habitat and ecology description (optional, preferred over Locality when present) |

### 4. Run the pipeline

```bash
docker compose up --build
```

Output is written to `./data/output.csv`.

## Output Format

Each row in the output CSV corresponds to one input record:

| Column | Description |
|--------|-------------|
| `HerbariumID` | Record identifier, for joining with input data |
| `clc_code` | CORINE Land Cover level 3 code (e.g. `311`) |
| `clc_name` | CLC category name (e.g. `Broadleaved Forest`) |
| `confidence` | Match confidence score (0.0–1.0) |
| `reason` | LLM explanation for the match |
| `summary` | Short summary of the classified habitat |
| `source_field` | Whether `FundortUNdOeko` or `Locality` was used as input |

## Classification Logic

For each record, the classifier selects input text as follows:

- If `FundortUNdOeko` is present → use it (more ecologically descriptive)
- Otherwise → fall back to `Locality`

Only the top CLC match is retained per record.

## Notes

- Classification quality depends heavily on input text. Records with only place names (e.g. "Bayern, SW Grainau") produce lower-confidence, less specific results than records with actual habitat descriptions (e.g. "Weinbergshang").
- `FundortUNdOeko` is populated in approximately 26% of BGBM records; `Locality` covers 99.4%.
- The OpenAI API is called once per record. At 100k records, costs are non-trivial; consider using a smaller sample for development. Replacement with a local Hugging Face model is planned for the optimisation phase.

## Planned Extensions

- Swap OpenAI for a local Hugging Face zero-shot classifier
- Nextflow module for nf-core pipeline integration
- Async batching for improved throughput
- Save processed identifiers to reduce api load.

## AI Assistance

This project was developed with the assistance of Claude for 
architectural guidance, code review, and documentation.
All code has been reviewed and tested by the authors.