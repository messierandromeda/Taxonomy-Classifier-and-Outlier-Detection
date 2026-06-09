import time
import logging
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
from app.detectors.hdbscan_geo_detector import HDBSCANGeoDetector
from app.detectors.llm_detector import LLMDetector
from app.report import (
    merge_flags,
    calculate_record_score,
    calculate_record_severity,
)
from app.schemas import DetectResponse, RecordQualityResult
from app.ollama_config import OLLAMA_MODEL, OLLAMA_URL
from app.utils import add_event_year, normalize_records

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

def prepare_records(records: list[dict]) -> list[dict]:
    if not records:
        return False
    records = normalize_records(records)
    records = add_event_year(records)
    return records


def merge_detector_results(merged: dict, records: list[dict]) -> DetectResponse:
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

# Main pipeline
def run_detectors(
    records: list[dict],
    enable_quality: bool = True,
    enable_outliers: bool = True,
    enable_semantic: bool = True,
    enable_llm: bool = False,
    llm_provider: str = "none",
    text_fields: list[str] | None = None,
) -> DetectResponse:

    result = prepare_records(records)

    if not result:
        return DetectResponse(count=0, results=[])

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
        HDBSCANGeoDetector(),
    ]

    detectors = []

    if enable_quality:
        detectors.extend(quality_detectors)

    if enable_semantic:
        detectors.extend(semantic_detectors)

    if enable_outliers:
        detectors.extend(outlier_detectors)

    if enable_llm and llm_provider != "none":
        detectors.append(LLMDetector(
            provider=llm_provider,
            text_fields=text_fields,
            model=OLLAMA_MODEL,
            ollama_url=OLLAMA_URL,
            timeout=30,
        ))

    flag_maps = []
    
    logging.info(f"\n[RUN] Processing {len(result)} records")

    for detector in detectors:
        try: 
            detector_name = detector.name

            start_time = time.time()
            flag_map = detector.detect(result)
            logging.info(f"[DETECTOR START] {detector_name}")
            elapsed = time.time() - start_time

            flag_count = sum(len(flags) for flags in flag_map.values())
            record_count = sum(1 for flags in flag_map.values() if flags)

            logging.info(
                f"[DETECTOR DONE] {detector_name} | "
                f"flagged_records={record_count} | "
                f"flags={flag_count} | "
                f"time={elapsed:.2f}s"
            )

            flag_maps.append(flag_map)
        except Exception as e:
            logging.error(f"Skipping {detector_name}: {e}")
            continue

    merged = merge_flags(*flag_maps)

    return merge_detector_results(merged, result)

def run_llm_only(
    records: list[dict],
    llm_provider: str = "ollama",
    text_fields: list[str] | None = None,
) -> DetectResponse:

    result = prepare_records(records)

    if not result:
        return DetectResponse(count=0, results=[])

    detector = LLMDetector(
            provider=llm_provider,
            text_fields=text_fields,
            model=OLLAMA_MODEL,
            ollama_url=OLLAMA_URL,
            timeout=30,
        )

    flag_map = detector.detect(result)

    return merge_detector_results(flag_map, result)

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