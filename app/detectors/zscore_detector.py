from typing import Any, Dict, List
import pandas as pd
import json
from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id
from pathlib import Path
import logging
import sys
from fastapi import HTTPException, status
from app.config import UNINITIALIZED_MSG

CURRENT_DIR = Path(__file__).resolve().parent
PATH = CURRENT_DIR / "models" / "z-score.json"
PATH.parent.mkdir(parents=True, exist_ok=True)


class ZScoreDetector(BaseDetector):
    """Detects numeric outliers by z-score relative to fitted field statistics."""

    name = "zscore_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        threshold: float = 3.0,
    ):

        self.numeric_fields = numeric_fields or [
            "decimalLatitude",
            "decimalLongitude",
        ]

        self.threshold = threshold
        self.cached_stats: Dict[str, Dict[str, float]] = {}

    def train(self, records: List[Dict[str, Any]]) -> None:
        """Fit mean and standard deviation for configured numeric fields."""
        df = pd.DataFrame(records)
        self.cached_stats = {}

        for field in self.numeric_fields:
            if field not in df.columns:
                continue

            series = pd.to_numeric(df[field], errors="coerce")
            clean = series.dropna()

            if len(clean) < 3:
                continue

            mean = clean.mean()
            std = clean.std(ddof=0)

            if std == 0:
                continue

            self.cached_stats[field] = {
                "mean": float(mean),
                "std": float(std),
            }

        IS_TESTING = "pytest" in sys.modules

        if not IS_TESTING:
            with open(PATH, "w", encoding="utf-8") as f:
                json.dump(self.cached_stats, f, indent=4)
        else:
            logging.info(f"Pytest detected. Prevented overwrite on: {PATH}")

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Flag numeric values whose z-score exceeds the configured threshold."""
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

            stats = self.cached_stats[field]
            mean = stats["mean"]
            std = stats["std"]

            if std == 0:
                continue

            series = pd.to_numeric(df[field], errors="coerce")

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
