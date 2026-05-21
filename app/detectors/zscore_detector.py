from typing import Any, Dict, List
import pandas as pd

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class ZScoreDetector(BaseDetector):
    name = "zscore_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        threshold: float = 3.0,
    ):
        # By default, only check coordinate fields required by the new dataset.
        self.numeric_fields = numeric_fields or [
            "decimalLatitude",
            "decimalLongitude",
        ]

        # Values with an absolute z-score above this threshold are flagged.
        self.threshold = threshold

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        df = pd.DataFrame(records)

        # Prepare an empty flag list for every record.
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        for field in self.numeric_fields:
            # Skip fields that do not exist in the current dataset.
            if field not in df.columns:
                continue

            # Convert values to numeric; invalid values become NaN.
            series = pd.to_numeric(df[field], errors="coerce")
            clean = series.dropna()

            # Z-score needs enough values to be meaningful.
            if len(clean) < 3:
                continue

            mean = clean.mean()
            std = clean.std(ddof=0)

            # If all values are equal, no outlier can be calculated.
            if std == 0:
                continue

            zscores = (series - mean) / std

            for index, z in zscores.items():
                if pd.isna(z):
                    continue

                if abs(z) >= self.threshold:
                    record_id = get_record_id(records[index], index)
                    value = series.iloc[index]

                    score = min(1.0, abs(float(z)) / 6.0)
                    severity = "medium" if score < 0.85 else "high"

                    # Coordinate outliers can be too sensitive in small datasets,
                    # so their score is reduced to avoid false positives.
                    if field in ["decimalLatitude", "decimalLongitude"]:
                        score = score * 0.35

                        if score < 0.4:
                            severity = "low"
                        elif score < 0.7:
                            severity = "medium"
                        else:
                            severity = "high"

                    results[record_id].append(
                        DetectionFlag(
                            field=field,
                            method=self.name,
                            type="coordinate_zscore_outlier",
                            severity=severity,
                            score=score,
                            message=(
                                f"{field} value has z-score {z:.2f}, "
                                f"above threshold {self.threshold}."
                            ),
                            value={
                                "value": float(value),
                                "mean": round(float(mean), 6),
                                "std": round(float(std), 6),
                                "z_score": round(float(z), 3),
                            },
                        )
                    )

        return results