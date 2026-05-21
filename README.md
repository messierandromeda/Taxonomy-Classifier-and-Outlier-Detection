# Biodiv Outlier and Data-Quality Detection Service

REST service for biodiversity data-quality validation, statistical outlier detection, and semantic consistency analysis.

The project is designed for herbarium and biodiversity datasets such as BGBM specimen exports and supports both structured validation and optional LLM-based semantic analysis.

---

# Features

The service combines multiple independent detector types:

## Quality Detectors

Rule-based validation for hard data-quality constraints.

### `RuleDetector`

Checks:

- missing mandatory fields
- invalid latitude/longitude ranges
- invalid date formats
- invalid URL formats
- invalid barcode formats
- taxonomic inconsistencies
- coordinate completeness
- date ordering problems
- identifier consistency

---

## Statistical Outlier Detectors

Dataset-dependent anomaly detection.

### `IQRDetector`

Univariate outlier detection using interquartile range fences.

Typical use cases:

- unusual latitude values
- unusual longitude values
- numeric field anomalies

---

### `ZScoreDetector`

Univariate statistical outlier detection using z-scores.

---

### `ModifiedZScoreDetector`

Robust outlier detection using median absolute deviation.

Less sensitive to skewed distributions and clustered biodiversity data.

---

### `DateOutlierDetector`

Detects suspicious collection years using:

- z-score analysis
- IQR-based year outlier detection

Small historical year deviations are ignored to reduce false positives.

---

### `IsolationForestDetector`

Multivariate anomaly detection using Isolation Forest.

Can analyze combinations such as:

- latitude + longitude
- latitude + longitude + collection year

---

### `DBSCANGeoDetector`

Density-based geographic cluster outlier detection.

Useful for:

- isolated coordinate records
- geographically implausible clusters
- coordinate noise

---

## Semantic and Ecological Validation

### `SemanticRuleDetector`

Detects ecological and textual inconsistencies such as:

- desert species in aquatic habitats
- marine organisms in inland environments
- locality/country contradictions
- implausible habitat combinations
- future collection dates

---

## Optional LLM Semantic Validation

### `LLMDetector`

Optional semantic analysis using local or remote language models.

Supported providers:

- Ollama
- Hugging Face (optional)

The detector analyzes semantic relationships between:

- taxonomy
- habitat
- locality
- coordinates
- country
- dates
- free-text notes

The LLM detector is conservative and tries to reduce false positives.

---

# Supported Input Formats

The service supports:

- JSON payloads
- CSV uploads
- local CSV test files
- local JSON test files

---

# API Endpoints

## Health Check

```http
GET /health
```

Returns service and Ollama status.

---

## Detect From JSON

```http
POST /detect
```

Accepts biodiversity records directly as JSON.

---

## Detect From CSV Upload

```http
POST /detect-csv
```

Accepts CSV uploads and processes them in chunks.

Supports:

- chunked processing
- optional LLM filtering
- configurable LLM limits

---

## Detect Local JSON File

```http
GET /detect-local-json
```

Loads and processes the configured local JSON test file.

---

## Detect Local CSV File

```http
GET /detect-local-csv
```

Loads and processes the configured local CSV test file.

---

# Run Locally

## Create Environment

```bash
python -m venv .venv
```

Activate environment:

### Linux/macOS

```bash
source .venv/bin/activate
```

### Windows

```powershell
.venv\Scripts\activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Start Service

```bash
uvicorn app.main:app --reload
```

---

## Open Swagger UI

```text
http://127.0.0.1:8000/docs
```

---

# Example JSON Request

```json
{
  "enable_llm": true,
  "llm_provider": "ollama",
  "records": [
    {
      "HerbariumID": "TEST-001",
      "FullNameCache": "Quercus robur L.",
      "Country": "Germany",
      "Locality": "Berlin desert",
      "Latitude": 52.52,
      "Longitude": 13.405,
      "FundortUNdOeko": "tropical rainforest"
    }
  ]
}
```

---

# Example CSV Upload

```bash
curl -X POST "http://127.0.0.1:8000/detect-csv" \
  -F "file=@data.csv"
```

---

# Example JSON Upload

```bash
curl -X POST "http://127.0.0.1:8000/detect" \
  -H "Content-Type: application/json" \
  --data @sample_records_payload.json
```

---

# LLM Mode With Ollama

Install Ollama locally:

```bash
ollama pull llama3.2:3b
ollama serve
```

The service automatically checks whether Ollama is reachable during startup.

---

# LLM Mode With Hugging Face

Optional dependencies:

```bash
pip install transformers torch
```

Example:

```json
{
  "enable_llm": true,
  "llm_provider": "huggingface",
  "records": [...]
}
```

---

# Docker

## Build and Start

```bash
docker compose up --build
```

---

## Open API

```text
http://localhost:8000/docs
```

---

# Project Structure

```text
project/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── schemas.py
│   ├── report.py
│   │
│   ├── detectors/
│   │   ├── base.py
│   │   ├── rule_detector.py
│   │   ├── iqr_detector.py
│   │   ├── zscore_detector.py
│   │   ├── modified_zscore_detector.py
│   │   ├── date_outlier_detector.py
│   │   ├── isolation_forest_detector.py
│   │   ├── dbscan_detector.py
│   │   ├── semantic_rule_detector.py
│   │   └── llm_detector.py
│   │
│   └── preprocessing/
│       └── bgbm_normalizer.py
│
├── tests/
├── test_daten/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

# Output Structure

Each processed record returns:

- `id`
- overall `severity`
- overall `score`
- list of `flags`

Each flag contains:

- affected `field`
- detector `method`
- detection `type`
- `severity`
- confidence `score`
- human-readable `message`
- original `value`

---

# Detector Pipeline

The pipeline currently supports:

## Quality Validation

- rule-based validation
- identifier checks
- date validation
- coordinate validation

---

## Statistical Outlier Detection

- IQR
- z-score
- modified z-score
- Isolation Forest
- DBSCAN

---

## Semantic Validation

- ecological plausibility
- geographic plausibility
- habitat consistency
- semantic LLM analysis

---

# Important Notes

This project is currently a research-oriented starter implementation and not yet a fully evaluated scientific production system.

Possible future improvements:

- country polygon validation
- GeoJSON-based coordinate checks
- biodiversity ontology integration
- embedding-based semantic similarity
- precision/recall/F1 evaluation
- larger benchmark datasets
- stronger taxonomy validation
- habitat knowledge bases
- asynchronous LLM batching
- nf-core compatible packaging
- CI/CD integration
- additional unit and integration tests