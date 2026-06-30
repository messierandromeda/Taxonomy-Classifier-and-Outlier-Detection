from typing import Any, Dict, List
import pandas as pd
import json
from pathlib import Path
import logging
import sys
from fastapi import HTTPException, status
from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id
from app.config import UNINITIALIZED_MSG

CURRENT_DIR = Path(__file__).resolve().parent
PATH = CURRENT_DIR / "models" / "iqr_detector.json"
PATH.parent.mkdir(parents=True, exist_ok=True)


class IQRDetector(BaseDetector):
    """Detects numeric outliers using interquartile range fences.

    The detector computes IQR fences for configured numeric fields and flags
    values outside the lower and upper bounds.
    """

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
        self.cached_stats: Dict[str, Dict[str, float]] = {}

    def train(self, records: List[Dict[str, Any]]) -> None:
        """Compute IQR fences for each configured numeric field.

        Saves lower and upper bounds for later detection of outlier values.
        """
        df = pd.DataFrame(records)
        self.cached_stats = {}

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

            self.cached_stats[field] = {
                "q1": float(q1),
                "q3": float(q3),
                "iqr": float(iqr),
                "lower": float(q1 - self.k * iqr),
                "upper": float(q3 + self.k * iqr),
            }

        IS_TESTING = "pytest" in sys.modules

        if not IS_TESTING:
            with open(PATH, "w", encoding="utf-8") as f:
                json.dump(self.cached_stats, f, indent=4)
        else:
            logging.info(f"Pytest detected. Prevented overwrite on: {PATH}")

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Flag records whose numeric values fall outside learned IQR fences."""
        if PATH.exists():
            logging.info(f"Loading z-score data from {PATH}...")
            with open(PATH, "r", encoding="utf-8") as f:
                self.cached_stats = json.load(f)
        else:
            logging.critical(
                f"Model file NOT found at {PATH}! API cannot process detections."
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNINITIALIZED_MSG,
            )

        df = pd.DataFrame(records)

        results = {
            get_record_id(record, index): [] for index, record in enumerate(records)
        }

        for field in self.numeric_fields:
            if field not in df.columns or field not in self.cached_stats:
                continue

            series = pd.to_numeric(df[field], errors="coerce")

            stats = self.cached_stats[field]
            q1 = stats["q1"]
            q3 = stats["q3"]
            iqr = stats["iqr"]
            lower = stats["lower"]
            upper = stats["upper"]

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
