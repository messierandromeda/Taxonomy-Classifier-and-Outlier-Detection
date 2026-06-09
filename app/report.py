from typing import Any

SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def get_flag_value(flag: Any, key: str, default=None):
    """
    Read a value from either:
    - Pydantic DetectionFlag object
    - plain dictionary from LLMDetector
    """

    if isinstance(flag, dict):
        return flag.get(key, default)

    return getattr(flag, key, default)


def merge_flags(*flag_maps):
    """
    Merge results from multiple detectors.

    Input:
        detector_1 -> {record_id: [flags]}
        detector_2 -> {record_id: [flags]}

    Output:
        merged -> {record_id: [all flags]}
    """

    merged = {}

    for flag_map in flag_maps:
        for record_id, flags in flag_map.items():

            if record_id not in merged:
                merged[record_id] = []

            merged[record_id].extend(flags)

    return merged


def calculate_record_score(flags):
    """
    Calculate the final score for one record.

    Current strategy:
    - use the highest individual flag score
    - simple and conservative
    """

    if not flags:
        return 0

    return max(
        get_flag_value(flag, "score", 0)
        for flag in flags
    )


def calculate_record_severity(flags):
    """
    Calculate the final severity for one record.

    Current strategy:
    - use the highest severity among all flags
    """

    if not flags:
        return "info"

    return max(
        (
            get_flag_value(flag, "severity", "info")
            for flag in flags
        ),
        key=lambda severity: SEVERITY_ORDER.get(severity, 0),
    )