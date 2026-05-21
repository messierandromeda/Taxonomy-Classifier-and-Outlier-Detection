from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException
import pandas as pd
from io import StringIO
import json
import subprocess
import time
import requests
from datetime import datetime
from typing import Any
import os

from app.schemas import (
    DetectRequest,
    DetectResponse,
    RecordQualityResult,
)

from app.detectors.base import get_record_id

from app.detectors.rule_detector import RuleDetector
from app.detectors.semantic_rule_detector import SemanticRuleDetector

from app.detectors.iqr_detector import IQRDetector
from app.detectors.zscore_detector import ZScoreDetector
from app.detectors.modified_zscore_detector import ModifiedZScoreDetector

from app.detectors.date_outlier_detector import DateOutlierDetector

from app.detectors.isolation_forest_detector import (
    IsolationForestDetector,
)

from app.detectors.dbscan_detector import DBSCANGeoDetector
from app.detectors.llm_detector import LLMDetector

from app.preprocessing.bgbm_normalizer import (
    normalize_bgbm_record,
)

from app.report import (
    merge_flags,
    calculate_record_score,
    calculate_record_severity,
)


# --------------------------------------------------
# Ollama configuration
# --------------------------------------------------


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")


# --------------------------------------------------
# Expected BGBM CSV column order
# --------------------------------------------------

BGBM_COLUMNS = [
    "HerbariumID",
    "Bild",
    "DB",
    "Family",
    "FullNameCache",
    "Anmerkungen",
    "Sammlerteam",
    "Sammelnummer",
    "CollectionDateBegin",
    "CollectionDateEnd",
    "Country",
    "Locality",
    "TitelEtikett",
    "Expeditionsangabe",
    "ShowOnMap",
    "Latitude",
    "Longitude",
    "FundortUNdOeko",
    "NameCache",
    "Genus",
    "Identifier",
    "Barcode",
    "StableURI",
]


# --------------------------------------------------
# Detector types relevant for LLM analysis
# --------------------------------------------------

LLM_RELEVANT_TYPES = {
    "invalid_coordinate_range",
    "missing_or_invalid_coordinate",
    "missing_date",
    "invalid_date_format",
    "invalid_date_order",
    "future_date",
    "implausibly_old_date",
    "coordinate_iqr_outlier",
    "coordinate_zscore_outlier",
    "coordinate_modified_zscore_outlier",
    "collection_year_zscore_outlier",
    "collection_year_iqr_outlier",
    "coordinate_multivariate_outlier",
    "coordinate_date_multivariate_outlier",
    "coordinate_cluster_outlier",
    "marine_inland_contradiction",
    "water_dry_habitat_mixture",
    "country_locality_contradiction",
    "species_habitat_contradiction",
}


# --------------------------------------------------
# Ollama health check
# --------------------------------------------------

def is_ollama_running() -> bool:
    try:
        response = requests.get(
            OLLAMA_URL,
            timeout=2,
        )

        return response.status_code == 200

    except requests.RequestException:
        return False


# --------------------------------------------------
# Start Ollama automatically if needed
# --------------------------------------------------

def start_ollama_if_needed() -> None:
    if is_ollama_running():
        print("Ollama is already running.")
        return

    print("Starting Ollama server...")

    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )

    except FileNotFoundError:
        print("Warning: Ollama command was not found.")
        return

    for _ in range(10):
        time.sleep(1)

        if is_ollama_running():
            print("Ollama started successfully.")
            return

    print("Warning: Ollama could not be started automatically.")


# --------------------------------------------------
# FastAPI lifespan hook
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_ollama_if_needed()
    yield


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="Biodiv Outlier and Data-Quality Detection Service",
    version="0.2.0",
    description=(
        "REST service for biodiversity data-quality "
        "checks and outlier detection."
    ),
    lifespan=lifespan,
)


# --------------------------------------------------
# Extract year from date string
# --------------------------------------------------

def extract_year(value: Any) -> int | None:
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y-%m",
        "%Y",
        "%d.%m.%Y",
        "%d/%m/%Y",
        "%Y/%m/%d",
        "%d-%m-%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).year

        except ValueError:
            continue

    if len(text) >= 4 and text[:4].isdigit():
        try:
            return int(text[:4])

        except ValueError:
            return None

    return None


# --------------------------------------------------
# Normalize records into internal schema
# --------------------------------------------------

def normalize_records(records: list[dict]) -> list[dict]:
    return [
        normalize_bgbm_record(record)
        for record in records
    ]


# --------------------------------------------------
# Add derived eventYear field
# --------------------------------------------------

def add_event_year(records: list[dict]) -> list[dict]:
    for record in records:
        record["eventYear"] = extract_year(
            record.get("collectionDateBegin")
            or record.get("eventDate")
        )

    return records


# --------------------------------------------------
# Replace NaN with None
# --------------------------------------------------

def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.where(pd.notnull(df), None)


# --------------------------------------------------
# Assign BGBM headers if CSV has no header row
# --------------------------------------------------

def apply_bgbm_columns_if_needed(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if all(isinstance(col, int) for col in df.columns):

        if len(df.columns) != len(BGBM_COLUMNS):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"CSV has {len(df.columns)} columns, "
                    f"expected {len(BGBM_COLUMNS)} BGBM columns."
                ),
            )

        df.columns = BGBM_COLUMNS

    return df


# --------------------------------------------------
# Main detector pipeline
# --------------------------------------------------

def run_detectors(
    records: list[dict],
    enable_quality: bool = True,
    enable_outliers: bool = True,
    enable_semantic: bool = True,
    enable_llm: bool = False,
    llm_provider: str = "none",
    numeric_fields: list[str] | None = None,
    text_fields: list[str] | None = None,
) -> DetectResponse:

    # Normalize records.
    records = normalize_records(records)

    # Add eventYear field.
    records = add_event_year(records)

    if not records:
        return DetectResponse(
            count=0,
            results=[],
        )

    # --------------------------------------------------
    # Detector pipeline
    # --------------------------------------------------

    quality_detectors = [
        RuleDetector(),
    ]

    semantic_detectors = [
        SemanticRuleDetector(),
    ]

    outlier_detectors = [
        IQRDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        ZScoreDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        ModifiedZScoreDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        DateOutlierDetector(date_fields=["collectionDateBegin"]),
        IsolationForestDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        IsolationForestDetector(numeric_fields=["decimalLatitude", "decimalLongitude", "eventYear"]),
        DBSCANGeoDetector(),
    ]

    detectors = []

    if enable_quality:
            detectors.extend(quality_detectors)

    if enable_semantic:
            detectors.extend(semantic_detectors)

    if enable_outliers:
            detectors.extend(outlier_detectors)

    # --------------------------------------------------
    # Optional LLM detector
    # --------------------------------------------------

    if enable_llm and llm_provider != "none":
        LLMDetector(
            provider=llm_provider,
            text_fields=text_fields,
            model=OLLAMA_MODEL,
            ollama_url=OLLAMA_URL,
            timeout=30,
        )

    flag_maps = []

    print(f"\n[RUN] Processing {len(records)} records")

    # --------------------------------------------------
    # Run detectors
    # --------------------------------------------------
    print(f"\n[RUN] Processing {len(records)} records")

    for detector in detectors:
        detector_name = getattr(
            detector,
            "name",
            getattr(detector, "method_name", detector.__class__.__name__),
        )

        print(f"[DETECTOR START] {detector_name}")

        start_time = time.time()
        flag_map = detector.detect(records)
        elapsed = time.time() - start_time

        flag_count = sum(len(flags) for flags in flag_map.values())
        record_count = sum(1 for flags in flag_map.values() if flags)

        print(
            f"[DETECTOR DONE] {detector_name} | "
            f"flagged_records={record_count} | "
            f"flags={flag_count} | "
            f"time={elapsed:.2f}s"
        )

        flag_maps.append(flag_map)
    # --------------------------------------------------
    # Merge detector results
    # --------------------------------------------------

    merged = merge_flags(*flag_maps)

    results = []

    for index, record in enumerate(records):

        record_id = get_record_id(
            record,
            index,
        )

        flags = merged.get(record_id, [])

        results.append(
            RecordQualityResult(
                id=record_id,
                severity=calculate_record_severity(flags),
                score=calculate_record_score(flags),
                flags=flags,
            )
        )

    return DetectResponse(
        count=len(results),
        results=results,
    )


# --------------------------------------------------
# Run only LLM detector
# --------------------------------------------------

def run_llm_only(
    records: list[dict],
    llm_provider: str = "ollama",
    text_fields: list[str] | None = None,
) -> DetectResponse:

    records = normalize_records(records)
    records = add_event_year(records)

    if not records:
        return DetectResponse(
            count=0,
            results=[],
        )

    detector = LLMDetector(
            provider=llm_provider,
            text_fields=text_fields,
            model=OLLAMA_MODEL,
            ollama_url=OLLAMA_URL,
            timeout=30,
        )

    flag_map = detector.detect(records)

    results = []

    for index, record in enumerate(records):

        record_id = get_record_id(
            record,
            index,
        )

        flags = flag_map.get(record_id, [])

        results.append(
            RecordQualityResult(
                id=record_id,
                severity=calculate_record_severity(flags),
                score=calculate_record_score(flags),
                flags=flags,
            )
        )

    return DetectResponse(
        count=len(results),
        results=results,
    )


# --------------------------------------------------
# Select records relevant for LLM analysis
# --------------------------------------------------

def select_flagged_records(
    records: list[dict],
    fast_response: DetectResponse,
) -> list[dict]:

    flagged_ids = {
        result.id
        for result in fast_response.results
        if any(
            getattr(flag, "type", None)
            in LLM_RELEVANT_TYPES
            for flag in result.flags
        )
    }

    selected = []

    normalized_records = normalize_records(records)

    for index, record in enumerate(normalized_records):

        record_id = get_record_id(
            record,
            index,
        )

        if record_id in flagged_ids:
            selected.append(record)

    return selected


# --------------------------------------------------
# Merge fast detector + LLM results
# --------------------------------------------------

def merge_chunk_results(
    fast_response: DetectResponse,
    llm_response: DetectResponse | None = None,
) -> list[RecordQualityResult]:

    if llm_response is None:
        return fast_response.results

    by_id = {
        result.id: result
        for result in fast_response.results
    }

    for llm_result in llm_response.results:

        if llm_result.id in by_id:
            existing = by_id[llm_result.id]

            existing.flags.extend(llm_result.flags)

            existing.severity = calculate_record_severity(
                existing.flags
            )

            existing.score = calculate_record_score(
                existing.flags
            )

        else:
            by_id[llm_result.id] = llm_result

    return list(by_id.values())

def process_records_strategically(
    records: list[dict],
    enable_quality: bool = True,
    enable_outliers: bool = True,
    enable_semantic: bool = True,
    enable_llm: bool = False,
    llm_provider: str = "none",
    max_llm_records: int = 10,
    llm_only_flagged: bool = True,
) -> list[RecordQualityResult]:
    # First run all fast non-LLM detectors.
    fast_response = run_detectors(
        records=records,
        enable_quality=enable_quality,
        enable_outliers=enable_outliers,
        enable_semantic=enable_semantic,
        enable_llm=False,
        llm_provider="none",
    )

    llm_response = None

    # Optionally run LLM only on selected records.
    if enable_llm and llm_provider != "none" and max_llm_records > 0:
        if llm_only_flagged:
            llm_records = select_flagged_records(
                records,
                fast_response,
            )
        else:
            llm_records = records

        llm_records = llm_records[:max_llm_records]

        if llm_records:
            llm_response = run_llm_only(
                records=llm_records,
                llm_provider=llm_provider,
            )

    return merge_chunk_results(
        fast_response=fast_response,
        llm_response=llm_response,
    )

@app.get("/health")
def health():
    return {
        "status": "ok",
        "ollama_running": is_ollama_running(),
        "ollama_model": OLLAMA_MODEL,
    }

@app.post("/detect", response_model=DetectResponse)
def detect(request: DetectRequest):
    return run_detectors(
        records=request.records,
        enable_quality=request.enable_quality,
        enable_outliers=request.enable_outliers,
        enable_semantic=request.enable_semantic,
        enable_llm=request.enable_llm,
        llm_provider=request.llm_provider,
        numeric_fields=request.numeric_fields,
        text_fields=request.text_fields,
    )

@app.post("/detect-csv", response_model=DetectResponse)
async def detect_csv(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str = "none",
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    raw = await file.read()
    csv_text = raw.decode("utf-8")

    all_results: list[RecordQualityResult] = []
    total_seen = 0

    chunk_reader = pd.read_csv(StringIO(csv_text), chunksize=chunksize)

    for chunk in chunk_reader:
        chunk = apply_bgbm_columns_if_needed(chunk)
        chunk = prepare_dataframe(chunk)

        records = chunk.to_dict(orient="records")

        if max_records is not None:
            remaining = max_records - total_seen
            if remaining <= 0:
                break
            records = records[:remaining]

        chunk_results = process_records_strategically(
            records=records,
            enable_quality=True,
            enable_outliers=True,
            enable_semantic=True,
            enable_llm=enable_llm,
            llm_provider=llm_provider,
            max_llm_records=max_llm_records,
            llm_only_flagged=llm_only_flagged,
        )
        all_results.extend(chunk_results)
        total_seen += len(records)

    return DetectResponse(count=len(all_results), results=all_results)