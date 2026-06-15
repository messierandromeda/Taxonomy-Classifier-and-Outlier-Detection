from typing import Any, Dict, List
from datetime import datetime
import pandas as pd
import json
import logging
from pathlib import Path
from fastapi import status, HTTPException
from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id
from app.config import UNINITIALIZED_MSG

CURRENT_DIR = Path(__file__).resolve().parent
PATH = CURRENT_DIR / "models" / "date_outlier.json"
PATH.parent.mkdir(parents=True, exist_ok=True)

class DateOutlierDetector(BaseDetector):
    """Detects anomalous collection years using z-score and IQR logic.

    This detector computes statistical summaries from configured date fields and
    flags records with years that are unusually far from the dataset distribution.
    """

    name = "date_outlier_detector"

    def __init__(
        self,
        date_fields: List[str] | None = None,
        z_threshold: float = 3.0,
        iqr_k: float = 1.5,
        min_year_distance: int = 10,
    ):
        self.date_fields = date_fields or ["collectionDateBegin"]
        self.z_threshold = z_threshold
        self.iqr_k = iqr_k
        self.min_year_distance = min_year_distance
        self.cached_stats: Dict[str, Dict[str, float]] = {}

    def train(self, records: List[Dict[str, Any]]) -> None:
        """Compute summary statistics for configured date fields.

        Stores mean, standard deviation, quartiles and IQR fences for later
        outlier detection.
        """
        self.cached_stats = {}

        for field in self.date_fields:
            years = []

            for record in records:
                years.append(self._extract_year(record.get(field)))

            series = pd.Series(years, dtype="float64")
            clean = series.dropna()

            if len(clean) < 4:
                continue

            mean = clean.mean()
            std = clean.std(ddof=0)
            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1

            lower = q1 - self.iqr_k * iqr
            upper = q3 + self.iqr_k * iqr

            self.cached_stats[field] = {
                "mean": float(mean),
                "std": float(std),
                "q1": float(q1),
                "q3": float(q3),
                "iqr": float(iqr),
                "lower": float(lower),
                "upper": float(upper),
            }

        with open(PATH, "w", encoding="utf-8") as f:
            json.dump(self.cached_stats, f, indent=4)

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Flag records with anomalous years based on precomputed date statistics."""
        if PATH.exists():
            logging.info(f"Loading z-score data from {PATH}...")
            with open(PATH, "r", encoding="utf-8") as f:
                self.cached_stats = json.load(f)
        else:
            logging.critical(f"Model file NOT found at {PATH}! API cannot process detections.")
                
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNINITIALIZED_MSG
            )
        
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        for field in self.date_fields:
            years = []

            for record in records:
                years.append(self._extract_year(record.get(field)))

            series = pd.Series(years, dtype="float64")

            stats = self.cached_stats[field]
            mean = stats["mean"]
            std = stats["std"]
            lower = stats["lower"]
            upper = stats["upper"]
            iqr = stats["iqr"]


            for index, year in series.items():
                if pd.isna(year):
                    continue

                record_id = get_record_id(records[index], index)

                if std != 0:
                    z = abs((year - mean) / std)

                    if z > self.z_threshold:
                        score = min(1.0, z / 6)

                        results[record_id].append(
                            DetectionFlag(
                                field=field,
                                method=self.name,
                                type="collection_year_zscore_outlier",
                                severity="medium" if score < 0.85 else "high",
                                score=score,
                                message=(
                                    f"Collection year {int(year)} has z-score "
                                    f"{z:.2f}, above threshold {self.z_threshold}."
                                ),
                                value={
                                    "year": int(year),
                                    "mean_year": round(float(mean), 2),
                                    "z_score": round(float(z), 2),
                                },
                            )
                        )

                if iqr != 0 and (year < lower or year > upper):
                    distance_to_fence = min(
                        abs(year - lower),
                        abs(year - upper),
                    )

                    # Ignore small historical deviations, e.g. 1927 vs 1930.
                    if distance_to_fence < self.min_year_distance:
                        continue

                    distance = distance_to_fence / max(abs(iqr), 1e-9)

                    score = min(1.0, 0.5 + distance / 10)

                    results[record_id].append(
                        DetectionFlag(
                            field=field,
                            method=self.name,
                            type="collection_year_iqr_outlier",
                            severity="medium" if score < 0.85 else "high",
                            score=score,
                            message=(
                                f"Collection year {int(year)} is outside "
                                f"IQR fence [{lower:.1f}, {upper:.1f}]."
                            ),
                            value={
                                "year": int(year),
                                "iqr_lower": round(float(lower), 2),
                                "iqr_upper": round(float(upper), 2),
                                "distance_to_fence": round(float(distance_to_fence), 2),
                            },
                        )
                    )

        return results

    def _extract_year(self, value: Any) -> int | None:
        """Extract a year integer from a date-like value.

        Supports several common date formats and fallback to the first four
        digits when parsing fails.
        """
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
            "%m/%d/%Y"
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