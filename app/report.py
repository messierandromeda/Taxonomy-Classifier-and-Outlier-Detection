from typing import Any

SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def get_flag_value(flag: Any, key: str, default=None):
    """Read a value from a DetectionFlag or a plain dictionary.

    Supports both pydantic-based detector output and the dictionary-based
    LLM detector output.
    """

    if isinstance(flag, dict):
        return flag.get(key, default)

    return getattr(flag, key, default)


def merge_flags(*flag_maps):
    """Merge multiple detector flag maps into a single combined map."""

    merged = {}

    for flag_map in flag_maps:
        for record_id, flags in flag_map.items():
            if record_id not in merged:
                merged[record_id] = []

            merged[record_id].extend(flags)

    return merged


def calculate_record_score(flags):
    """Compute a record-level score from its detector flags.

    Uses the maximum individual flag score as a conservative overall score.
    """

    if not flags:
        return 0

    return max(get_flag_value(flag, "score", 0) for flag in flags)


def calculate_record_severity(flags):
    """Compute the overall record severity based on highest flag severity."""

    if not flags:
        return "info"

    return max(
        (get_flag_value(flag, "severity", "info") for flag in flags),
        key=lambda severity: SEVERITY_ORDER.get(severity, 0),
    )
