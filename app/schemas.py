from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field

Severity = Literal[
    "info",
    "low",
    "medium",
    "high",
    "critical",
]

LLMProvider = Literal[
    "none",
    "ollama",
    "huggingface",
]


class DetectionFlag(BaseModel):
    field: str
    method: str
    type: str
    severity: Severity = "low"
    # Numeric score between 0 and 1.
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    message: str
    value: Optional[Any] = None


class RecordQualityResult(BaseModel):
    id: str
    severity: Severity
    score: float = Field(
        ge=0.0,
        le=1.0,
    )
    flags: List[DetectionFlag]


class DetectRequest(BaseModel):
    records: List[Dict[str, Any]]
    enable_quality: bool = True
    enable_outliers: bool = True
    enable_semantic: bool = True
    enable_llm: bool = False
    llm_provider: LLMProvider = "none"
    # Quality detectors
    enable_rule_detector: Optional[bool] = None
    # Semantic detectors
    enable_semantic_rule_detector: Optional[bool] = None
    # Outlier detectors
    enable_iqr_detector: Optional[bool] = None
    enable_zscore_detector: Optional[bool] = None
    enable_modified_zscore_detector: Optional[bool] = None
    enable_date_outlier_detector: Optional[bool] = None
    enable_isolation_forest_detector: Optional[bool] = None
    enable_hdbscan_geo_detector: Optional[bool] = None
    numeric_fields: Optional[List[str]] = None
    text_fields: Optional[List[str]] = None
    training_subset_size: int = 500
    training_seed: int = 42
    record_id_field: Optional[str] = None
    field_mapping: Optional[Dict[str, str]] = None


class DetectResponse(BaseModel):
    count: int
    results: List[RecordQualityResult]
    annotated_records: Optional[List[Dict[str, Any]]] = None
