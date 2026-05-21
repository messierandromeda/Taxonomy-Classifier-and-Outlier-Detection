from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field


# Allowed severity levels for all detector flags.
Severity = Literal[
    "info",
    "low",
    "medium",
    "high",
    "critical",
]


# Supported LLM providers.
LLMProvider = Literal[
    "none",
    "ollama",
    "huggingface",
]


class DetectionFlag(BaseModel):
    # Field or fields where the problem was found.
    field: str

    # Detector name.
    method: str

    # Machine-readable problem type.
    type: str

    # Human-readable severity.
    severity: Severity = "low"

    # Numeric score between 0 and 1.
    score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

    # Explanation for the user.
    message: str

    # Original or contextual value.
    value: Optional[Any] = None


class RecordQualityResult(BaseModel):
    # Record id after normalization.
    id: str

    # Highest severity among all flags.
    severity: Severity

    # Highest score among all flags.
    score: float = Field(
        ge=0.0,
        le=1.0,
    )

    # All flags found for this record.
    flags: List[DetectionFlag]


class DetectRequest(BaseModel):
    records: List[Dict[str, Any]]

    enable_quality: bool = True
    enable_outliers: bool = True
    enable_semantic: bool = True

    enable_llm: bool = False
    llm_provider: LLMProvider = "none"

    numeric_fields: Optional[List[str]] = None
    text_fields: Optional[List[str]] = None

    record_id_field: Optional[str] = None
    field_mapping: Optional[Dict[str, str]] = None
    
class DetectResponse(BaseModel):
    # Number of returned record results.
    count: int

    # Quality results per record.
    results: List[RecordQualityResult]