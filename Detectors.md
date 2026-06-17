# Detectors Overview

The service combines the following detector types to create a comprehensive data-quality and outlier detection pipeline.

---

## Quality Detectors

### RuleDetector

Syntactic and format validation:
- Valid coordinate ranges (-90/90 for latitude, -180/180 for longitude)
- Valid date formats and date ordering
- Mandatory field presence
- Barcode and URL format validation
- Taxonomic consistency (genus matching scientific name)

## Statistical Outliers

### IQRDetector

Univariate outlier detection using interquartile range:
- Identifies values outside `[Q1 - k*IQR, Q3 + k*IQR]`
- Typical fields: latitude, longitude, collection year
- Reduced scores for coordinate data (biological clusters are common)

### ZScoreDetector

Standard deviation-based outlier detection:
- Flags values with z-score > threshold
- Sensitive to dataset mean and variance
- Default threshold: 3.0 standard deviations

### ModifiedZScoreDetector

Robust version using median absolute deviation:
- More resistant to skewed and clustered data
- Better for biodiversity datasets with geographic clustering
- Uses formula: `0.6745 * (value - median) / MAD`

### DateOutlierDetector

Analyzes collection year outliers:
- Z-score analysis on extracted years
- IQR fence detection with tolerance for small historical deviations
- Ignores year differences < 10 years

### IsolationForestDetector

Multivariate anomaly detection:
- Analyzes combinations of numeric fields
- Useful for coordinate + year combinations
- Outputs anomaly scores normalized to [0, 1]

### HDBSCANGeoDetector

Density-based geographic clustering:
- Identifies records not belonging to geographic clusters
- Uses approximate predict for efficiency
- Particularly useful for spatial outlier detection

---

## Semantic and Ecological Validation

### `SemanticRuleDetector`

Detects ecological and textual inconsistencies using domain-specific rules:

- desert species in aquatic habitats
- marine organisms in inland environments
- country and locality contradictions
- implausible habitat combinations
- future collection dates

Species-specific habitat contradiction rules for common herbarium specimens.

---

## Optional LLM Semantic Analysis

### `LLMDetector`

Optional semantic analysis using local Ollama language models.

The detector analyzes semantic relationships across:

- taxonomy (family, genus, scientific name)
- habitat and locality
- collection date
- geographic coordinates
- free-text notes (Anmerkungen, collector notes)
- label text and expeditions

Conservative design reduces false positives on historical specimens with incomplete metadata.

**Configuration:**
- Provider: Ollama
- Default model: `llama3.2:3b`
- Custom model via environment: `OLLAMA_MODEL`

---

## Detector Selection Strategy

The pipeline enables detectors based on configuration flags:

- `enable_quality` (default: true) — activates RuleDetector
- `enable_outliers` (default: true) — activates all statistical detectors
- `enable_semantic` (default: true) — activates SemanticRuleDetector
- `enable_llm` (default: false) — activates LLMDetector (requires Ollama)

### Training vs. Rule-Based

**Requires Training:**
- IQRDetector
- ZScoreDetector
- ModifiedZScoreDetector
- DateOutlierDetector
- IsolationForestDetector
- HDBSCANGeoDetector

**Rule-Based (No Training):**
- RuleDetector
- SemanticRuleDetector
- LLMDetector

---

## Flag Types

Each detector produces `DetectionFlag` objects with standardized fields:

- `field`: Name of the affected field
- `method`: Detector that produced the flag
- `type`: Flag category (e.g., "coordinate_iqr_outlier", "invalid_date_format")
- `severity`: "info", "low", "medium", "high", or "critical"
- `score`: Confidence value 0.0–1.0
- `message`: Human-readable explanation
- `value`: Field value(s) or context data

### Common Flag Types

**Coordinate Issues:**
- `invalid_coordinate_range` — latitude/longitude outside valid bounds
- `missing_or_invalid_coordinate` — missing or non-numeric coordinate
- `coordinate_iqr_outlier` — coordinate outside IQR fence
- `coordinate_zscore_outlier` — coordinate with high z-score
- `coordinate_modified_zscore_outlier` — robust z-score outlier
- `coordinate_multivariate_outlier` — unusual coordinate combination
- `coordinate_cluster_outlier` — coordinate outside geographic cluster (HDBSCAN)

**Date Issues:**
- `missing_date` — missing collection date
- `invalid_date_format` — unparseable date string
- `invalid_date_order` — begin date after end date
- `future_date` — collection date in the future
- `implausibly_old_date` — unreasonable historical date
- `collection_year_zscore_outlier` — year with high z-score
- `collection_year_iqr_outlier` — year outside IQR fence

**Taxonomic Issues:**
- `missing_taxonomic_field` — missing family, genus, or scientific name
- `taxonomic_internal_inconsistency` — genus doesn't match scientific name
- `invalid_taxonomic_format` — unusual scientific name format

**Geographic/Metadata Issues:**
- `missing_geographic_field` — missing country or locality
- `missing_identifier` — missing herbarium ID or barcode
- `invalid_barcode_format` — unusual barcode structure
- `invalid_url` — malformed URL in stableUri
- `suspicious_free_text` — unusually short or malformed text fields

**Semantic Issues:**
- `marine_inland_contradiction` — marine + inland habitat terms
- `water_dry_habitat_mixture` — water + dry habitat contradiction
- `country_locality_contradiction` — locality mentions foreign country
- `species_habitat_contradiction` — species-habitat mismatch
- `semantic_inconsistency` — LLM-detected semantic issue

---

## Performance Considerations

- **IQRDetector, ZScoreDetector, ModifiedZScoreDetector:** O(n) per field, fast on large datasets
- **DateOutlierDetector:** O(n) for year extraction and analysis
- **IsolationForestDetector:** O(n log n) training, O(n) inference
- **HDBSCANGeoDetector:** O(n log n) on clustered data (typical for geographic data)
- **RuleDetector, SemanticRuleDetector:** O(n), purely rule-based
- **LLMDetector:** O(n) but with per-record LLM latency (typically 1-5 seconds per record)

For large datasets, consider:
- Chunked processing via `/detect-csv`
- Limiting LLM records with `max_llm_records`
- Using `llm_only_flagged` to analyze only flagged records with LLM
