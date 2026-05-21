from typing import Any, Dict, List
import pandas as pd

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class IQRDetector(BaseDetector):
    name = "iqr_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        k: float = 1.5,
    ):
        self.numeric_fields = numeric_fields or [
            "decimalLatitude",
            "decimalLongitude",
        ]
        self.k = k

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

            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                continue

            lower = q1 - self.k * iqr
            upper = q3 + self.k * iqr

            for index, value in series.items():
                if pd.isna(value):
                    continue

                if value < lower or value > upper:
                    record_id = get_record_id(records[index], index)

                    distance = min(
                        abs(value - lower),
                        abs(value - upper),
                    ) / max(abs(iqr), 1e-9)

                    score = min(1.0, 0.5 + distance / 10)

                    severity = "medium" if score < 0.85 else "high"

                    # Coordinate IQR is noisy for clustered biodiversity data.
                    if field in ["decimalLatitude", "decimalLongitude"]:
                        score = score * 0.15

                        if distance < 5:
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
                            type="coordinate_iqr_outlier",
                            severity=severity,
                            score=score,
                            message=(
                                f"{field} value {value} is outside the IQR fence "
                                f"[{lower:.3f}, {upper:.3f}]."
                            ),
                            value={
                                "value": float(value),
                                "q1": round(float(q1), 6),
                                "q3": round(float(q3), 6),
                                "iqr": round(float(iqr), 6),
                                "lower_fence": round(float(lower), 6),
                                "upper_fence": round(float(upper), 6),
                            },
                        )
                    )

        return results