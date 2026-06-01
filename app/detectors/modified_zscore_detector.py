from typing import Any, Dict, List
import pandas as pd

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class ModifiedZScoreDetector(BaseDetector):
    name = "modified_zscore_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        threshold: float = 3.5,
    ):
        self.numeric_fields = numeric_fields or [
            "decimalLatitude",
            "decimalLongitude",
        ]
        self.threshold = threshold
        self.cached_stats: Dict[str, Dict[str, float]] = {}

    def train(self, records: List[Dict[str, Any]]) -> None:
        df = pd.DataFrame(records)
        self.cached_stats = {}

        for field in self.numeric_fields:
            if field not in df.columns:
                continue

            series = pd.to_numeric(df[field], errors="coerce")
            clean = series.dropna()

            if len(clean) < 4:
                continue

            median = clean.median()
            mad = (clean - median).abs().median()

            if mad == 0:
                continue

            self.cached_stats[field] = {
                "median": float(median),
                "mad": float(mad),
            }

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        df = pd.DataFrame(records)

        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        for field in self.numeric_fields:
            if field not in df.columns:
                continue

            series = pd.to_numeric(df[field], errors="coerce")
            clean = series.dropna()

            if len(clean) < 4:
                continue

            median = clean.median()

            # MAD = Median Absolute Deviation.
            mad = (clean - median).abs().median()

            if mad == 0:
                continue

            if field in self.cached_stats:
                stats = self.cached_stats[field]
                median = stats["median"]
                mad = stats["mad"]

            for index, value in series.items():
                if pd.isna(value):
                    continue

                # Robust z-score using median instead of mean.
                modified_z = 0.6745 * (value - median) / mad

                if abs(modified_z) > self.threshold:
                    record_id = get_record_id(records[index], index)

                    score = min(1.0, abs(float(modified_z)) / 10)
                    severity = "medium"

                    if score >= 0.85:
                        severity = "high"

                    # Geographic coordinates can easily create false positives
                    # in biodiversity datasets with clustered observations.
                    if field in ["decimalLatitude", "decimalLongitude"]:
                        score *= 0.15

                        if abs(modified_z) < 20:
                            severity = "info"
                        elif score < 0.4:
                            severity = "low"
                        elif score < 0.7:
                            severity = "medium"
                        else:
                            severity = "high"

                    results[record_id].append(
                        DetectionFlag(
                            field=field,
                            method=self.name,
                            type="coordinate_modified_zscore_outlier",
                            severity=severity,
                            score=score,
                            message=(
                                f"{field} value has modified z-score "
                                f"{modified_z:.2f}, above threshold "
                                f"{self.threshold}."
                            ),
                            value={
                                "value": float(value),
                                "median": round(float(median), 6),
                                "mad": round(float(mad), 6),
                                "modified_z_score": round(float(modified_z), 3),
                            },
                        )
                    )

        return results