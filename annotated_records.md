# Annotated Records

This document explains how the `annotated_records` fields are calculated.

## Main idea

Each detector returns one or more flags for a record. A flag contains:

```text
field, method, type, severity, score, message, value
```

Then all flags of the same record are merged. The final `outlier_*` columns are calculated from these merged flags.

## Explanation of `outlier_score`
The `outlier_score` calculated as the highest score of all flags for this record and is not always from the LLM:

```python
outlier_score = max(flag.score for flag in flags)
```

If the highest flag was created by the LLM, then the score comes from the LLM. If the highest flag was created by a rule-based, statistical, or ML detector, then the score comes from that detector.

Example:

```text
rule_detector score          = 0.50
semantic_rule_detector score = 0.35
llm_detector score           = 0.00

outlier_score = 0.50
```

So the score source is the detector that produced the strongest flag.

## Record severity

The final severity is the highest severity among all flags:

```text
info < low < medium < high < critical
```

```python
outlier_severity = highest flag.severity
```

If there are no flags, the record is clean.

## Main output columns

| Column | Calculation / Meaning |
|---|---|
| `outlier_detected` | `true` if the record has at least one flag, otherwise `false`. |
| `outlier_score` | Highest `flag.score` of all flags for the record. Range: `0.0` to `1.0`. |
| `outlier_confidence` | Percentage version of the score: `round(outlier_score * 100)`. |
| `outlier_status` | Based on confidence: `0 = clean`, `<50 = fuzzy`, `<70 = likely`, `>=70 = confirmed`. |
| `outlier_severity` | Highest severity among all flags. |
| `outlier_primary_detector` | `method` of the flag with the highest score. |
| `outlier_primary_field` | `field` of the flag with the highest score. |
| `outlier_primary_type` | `type` of the flag with the highest score. |
| `outlier_reason` | `message` of the flag with the highest score. |
| `outlier_summary` | Short readable summary built from severity, field, and detector. |

## Additional metadata columns

| Column | Meaning |
|---|---|
| `outlier_flagged_fields` | All fields that were flagged. |
| `outlier_detector_methods` | All detectors that produced flags. |
| `outlier_flag_types` | All flag types found for the record. |
| `outlier_explanations` | All detector messages. |
| `outlier_flags` | Full raw flag objects for debugging and detailed analysis. |
| `outlier_model_count` | Number of detectors/models that flagged the record as an outlier. |
| `llm_flagged` | `true` if the LLM detector produced at least one outlier flag, otherwise `false`. |


## Model agreement columns

Two additional metadata columns describe how strongly the detectors agree on a record.

### `outlier_model_count`

`outlier_model_count` counts how many different detectors/models flagged the same record as an outlier.

Example:

```text
rule_detector             -> flagged
iqr_detector              -> flagged
isolation_forest_detector -> not flagged
llm_detector              -> flagged

outlier_model_count = 3
```

This value helps to see whether only one detector found a problem or whether several detectors agree that the record is suspicious.

### `llm_flagged`

`llm_flagged` is a boolean value. It shows whether the LLM detector itself produced at least one flag for the record.

```text
llm_flagged = true
```

This is useful because the final `outlier_score` does not always come from the LLM. A record can have a high score from another detector while the LLM did not flag it.

## Detectors used

The pipeline can use these detector groups:

| Group | Detectors | Purpose |
|---|---|---|
| Rule-based | `rule_detector` | Checks invalid/missing coordinates, dates, taxonomy, URLs, identifiers, etc. |
| Semantic rules | `semantic_rule_detector` | Checks simple ecological/geographic contradictions. |
| Statistical | `iqr_detector`, `zscore_detector`, `modified_zscore_detector`, `date_outlier_detector` | Finds unusual numeric or date values. |
| Machine learning | `isolation_forest_detector`, `hdbscan_geo_detector` | Finds multivariate or geographic cluster outliers. |
| LLM | `llm_detector` | Optional semantic plausibility check using Ollama. |

The LLM detector is only used when `enable_llm=True` and `llm_provider` is not `none`.

## Example

```json
{
  "outlier_detected": true,
  "outlier_status": "fuzzy",
  "outlier_confidence": 35,
  "outlier_severity": "low",
  "outlier_score": 0.35,
  "outlier_primary_detector": "semantic_rule_detector",
  "outlier_primary_field": "locality",
  "outlier_primary_type": "unusual_locality_text",
  "outlier_reason": "Locality contains unusual keywords.",
  "outlier_summary": "Low outlier detected in locality by semantic_rule_detector.",
  "outlier_model_count": 2,
  "llm_flagged": false
}
```

In this example, the final score is `0.35`. The confidence is therefore `35`. Because the primary detector is `semantic_rule_detector`, the score does **not** come from the LLM. The value `outlier_model_count = 2` means that two detectors produced flags for this record. The value `llm_flagged = false` means that the LLM did not flag this record.

## Clean record example

If no detector flags the record, the output is:

```json
{
  "outlier_detected": false,
  "outlier_status": "clean",
  "outlier_confidence": 0,
  "outlier_severity": "info",
  "outlier_score": 0,
  "outlier_primary_detector": "",
  "outlier_primary_field": "",
  "outlier_primary_type": "",
  "outlier_reason": "",
  "outlier_summary": "",
  "outlier_model_count": 0,
  "llm_flagged": false
}
```
