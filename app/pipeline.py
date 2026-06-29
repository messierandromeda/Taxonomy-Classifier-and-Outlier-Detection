import time
import random
import logging
from app.detectors.base import get_record_id

from app.detectors.rule_detector import RuleDetector
from app.detectors.semantic_rule_detector import SemanticRuleDetector

from app.detectors.iqr_detector import IQRDetector
from app.detectors.zscore_detector import ZScoreDetector
from app.detectors.modified_zscore_detector import ModifiedZScoreDetector
from app.detectors.isolation_forest_detector import IsolationForestDetector
from app.detectors.hdbscan_geo_detector import HDBSCANGeoDetector
from app.detectors.llm_detector import LLMDetector
from app.detectors.date_outlier_detector import DateOutlierDetector

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


def sample_training_records(
    records: list[dict],
    subset_size: int = 500,
    seed: int = 42,
) -> list[dict]:
    if subset_size <= 0 or not records:
        return []

    if subset_size >= len(records):
        return records

    rng = random.Random(seed)
    return rng.sample(records, k=subset_size)


def train_detectors(detectors, records: list[dict]) -> None:
    for detector in detectors:
        try:
            detector.train(records)
        except Exception:
            continue


def prepare_records(records: list[dict]) -> list[dict]:
    """Normalize raw records and add derived fields used by detectors."""
    if not records:
        return []

    records = normalize_records(records)
    records = add_event_year(records)

    return records


def summarize_outlier_result(result: RecordQualityResult | None) -> dict:
    """Summarize a single record quality result into a flat dictionary.

    Produces fields used for CSV annotation and API output.
    """
    if result is None or not result.flags:
        return {
            "outlier_detected": False,
            "outlier_status": "clean",
            "outlier_confidence": 0,
            "outlier_severity": "info",
            "outlier_score": 0,
            "outlier_primary_detector": "",
            "outlier_primary_field": "",
            "outlier_primary_type": "",
            "outlier_reason": "",
            "outlier_summary": "",
        }

    strongest_flag = max(
        result.flags,
        key=lambda flag: flag.score,
    )

    confidence = round(result.score * 100)

    if confidence == 0:
        status = "clean"
    elif confidence < 50:
        status = "fuzzy"
    elif confidence < 70:
        status = "likely"
    else:
        status = "confirmed"

    return {
        "outlier_detected": True,
        "outlier_status": status,
        "outlier_confidence": confidence,
        "outlier_severity": result.severity,
        "outlier_score": result.score,
        "outlier_primary_detector": strongest_flag.method,
        "outlier_primary_field": strongest_flag.field,
        "outlier_primary_type": strongest_flag.type,
        "outlier_reason": strongest_flag.message,
        "outlier_summary": (
            f"{result.severity.capitalize()} outlier detected in "
            f"{strongest_flag.field} by {strongest_flag.method}."
        ),
    }


def annotate_records(
    records: list[dict],
    results: list[RecordQualityResult],
) -> list[dict]:
    """Attach result summaries and flag metadata to the original records."""
    by_id = {result.id: result for result in results}

    annotated = []
    normalized_records = normalize_records(records)

    for index, record in enumerate(records):
        normalized_record = normalized_records[index]

        record_id = get_record_id(
            normalized_record,
            index,
        )

        result = by_id.get(record_id)

        new_record = dict(record)

        new_record.update(summarize_outlier_result(result))

        flags = result.flags if result else []

        new_record["outlier_flagged_fields"] = sorted({flag.field for flag in flags})

        new_record["outlier_detector_methods"] = sorted({flag.method for flag in flags})

        new_record["outlier_flag_types"] = sorted({flag.type for flag in flags})

        new_record["outlier_explanations"] = [flag.message for flag in flags]

        new_record["outlier_flags"] = [flag.model_dump() for flag in flags]

        annotated.append(new_record)

    return annotated


def merge_detector_results(
    merged: dict,
    records: list[dict],
) -> DetectResponse:
    """Merge detector flags into a DetectResponse with annotated records."""
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
        annotated_records=annotate_records(records, results),
    )


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
    """Run the configured detector ensemble and return quality results.

    This pipeline normalizes records, executes each
    enabled detector, merges flag outputs, and produces a final DetectResponse.
    """
    result = prepare_records(records)

    if not result:
        return DetectResponse(
            count=0,
            results=[],
            annotated_records=[],
        )

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
        logging.info(
            f"[PIPELINE] LLM detector added to main detector list "
            f"| provider={llm_provider}"
        )
        detectors.append(
            LLMDetector(
                provider=llm_provider,
                text_fields=text_fields,
                model=OLLAMA_MODEL,
                ollama_url=OLLAMA_URL,
                timeout=30,
            )
        )

    flag_maps = []

    logging.info(f"\n[RUN] Processing {len(result)} records")

    for detector in detectors:
        detector_name = detector.name

        logging.info(f"[DETECTOR START] {detector_name}")

        start_time = time.time()
        flag_map = detector.detect(result)
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

    merged = merge_flags(*flag_maps)

    return merge_detector_results(
        merged,
        result,
    )


def run_llm_only(
    records: list[dict],
    use_ollama: bool = False,
    text_fields: list[str] | None = None,
) -> DetectResponse:
    """Run only the LLM detector on normalized records.

    Useful when semantic LLM checks are required separately from the fast
    detector ensemble.
    """
    result = prepare_records(records)

    if not result:
        print("[PIPELINE] LLM skipped because no records were provided.")
        return DetectResponse(
            count=0,
            results=[],
            annotated_records=[],
        )

    print(
        f"[PIPELINE] Running LLM only | use_ollama={use_ollama} | records={len(result)}"
    )

    detector = LLMDetector(
        use_ollama=use_ollama,
        text_fields=text_fields,
        timeout=30,
    )

    logging.info("[DETECTOR START] llm_detector")

    start_time = time.time()
    flag_map = detector.detect(result)
    elapsed = time.time() - start_time

    flag_count = sum(len(flags) for flags in flag_map.values())

    record_count = sum(1 for flags in flag_map.values() if flags)

    logging.info(
        f"[DETECTOR DONE] llm_detector | "
        f"flagged_records={record_count} | "
        f"flags={flag_count} | "
        f"time={elapsed:.2f}s"
    )

    return merge_detector_results(
        flag_map,
        result,
    )


def select_flagged_records(
    records: list[dict],
    fast_response: DetectResponse,
) -> list[dict]:
    """Select records that were flagged by the quick detector pass.

    Returns only records with flags matching LLM-relevant categories.
    """
    flagged_ids = {
        result.id
        for result in fast_response.results
        if any(
            getattr(flag, "type", None) in LLM_RELEVANT_TYPES for flag in result.flags
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

    logging.info(
        f"[PIPELINE] LLM candidate selection "
        f"| flagged_ids={len(flagged_ids)} "
        f"| selected_records={len(selected)}"
    )

    return selected


def merge_chunk_results(
    fast_response: DetectResponse,
    llm_response: DetectResponse | None = None,
) -> list[RecordQualityResult]:
    """Merge a fast response with an optional LLM response.

    If an LLM response is provided, combine flags and recalculate scores and
    severities for affected records.
    """
    if llm_response is None:
        logging.warning("[PIPELINE] No LLM response to merge.")
        return fast_response.results

    logging.info(
        f"[PIPELINE] Merging LLM response | llm_results={len(llm_response.results)}"
    )

    by_id = {result.id: result for result in fast_response.results}

    for llm_result in llm_response.results:
        if llm_result.id in by_id:
            existing = by_id[llm_result.id]

            existing.flags.extend(llm_result.flags)

            existing.severity = calculate_record_severity(existing.flags)

            existing.score = calculate_record_score(existing.flags)

        else:
            by_id[llm_result.id] = llm_result

    return list(by_id.values())


def process_records_strategically(
    records: list[dict],
    enable_quality: bool = True,
    enable_outliers: bool = True,
    enable_semantic: bool = True,
    enable_llm: bool = False,
    use_ollama: bool = False,
    max_llm_records: int = 10,
    llm_only_flagged: bool = True,
) -> list[RecordQualityResult]:
    """Run the pipeline and optionally trigger an LLM refinement step.

    This function first runs the fast detector ensemble, then optionally selects
    records for LLM evaluation, and merges the results.
    """
    logging.info(
        f"[PIPELINE] process_records_strategically "
        f"| enable_llm={enable_llm} "
        f"| use_ollama={use_ollama} "
        f"| max_llm_records={max_llm_records} "
        f"| llm_only_flagged={llm_only_flagged}"
    )

    fast_response = run_detectors(
        records=records,
        enable_quality=enable_quality,
        enable_outliers=enable_outliers,
        enable_semantic=enable_semantic,
        enable_llm=False,
        llm_provider="none",
    )

    llm_response = None

    if enable_llm and max_llm_records > 0:
        print("[PIPELINE] LLM branch enabled.")

        if llm_only_flagged:
            llm_records = select_flagged_records(
                records,
                fast_response,
            )
        else:
            llm_records = records
            logging.info(
                f"[PIPELINE] LLM will process all records | records={len(llm_records)}"
            )

        llm_records = llm_records[:max_llm_records]

        logging.info(f"[PIPELINE] Sending records to LLM | records={len(llm_records)}")

        if llm_records:
            llm_response = run_llm_only(
                records=llm_records,
                use_ollama=use_ollama,
            )
        else:
            logging.warning(
                "[PIPELINE] LLM skipped because selected record list is empty."
            )
    else:
        logging.info("[PIPELINE] LLM branch disabled.")

    return merge_chunk_results(
        fast_response=fast_response,
        llm_response=llm_response,
    )
