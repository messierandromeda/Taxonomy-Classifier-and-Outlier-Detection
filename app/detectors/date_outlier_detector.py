from typing import Any, Dict, List
from datetime import datetime
import pandas as pd

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class DateOutlierDetector(BaseDetector):
    name = "date_outlier_detector"

    def __init__(
        self,
        date_fields: List[str] | None = None,
        z_threshold: float = 3.0,
        iqr_k: float = 1.5,
        min_year_distance: int = 10,
    ):
        # Date fields to analyze statistically.
        self.date_fields = date_fields or ["collectionDateBegin"]

        # Z-score threshold for year outliers.
        self.z_threshold = z_threshold

        # IQR multiplier for lower and upper fences.
        self.iqr_k = iqr_k

        # Ignore small historical year deviations.
        self.min_year_distance = min_year_distance

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        for field in self.date_fields:
            years = []

            # Extract only the year from each date value.
            for record in records:
                years.append(self._extract_year(record.get(field)))

            series = pd.Series(years, dtype="float64")
            clean = series.dropna()

            # Not enough data for meaningful statistics.
            if len(clean) < 4:
                continue

            mean = clean.mean()
            std = clean.std(ddof=0)

            q1 = clean.quantile(0.25)
            q3 = clean.quantile(0.75)
            iqr = q3 - q1

            lower = q1 - self.iqr_k * iqr
            upper = q3 + self.iqr_k * iqr

            for index, year in series.items():
                if pd.isna(year):
                    continue

                record_id = get_record_id(records[index], index)

                # -------------------------
                # Z-score year outlier
                # -------------------------
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

                # -------------------------
                # IQR year outlier
                # -------------------------
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