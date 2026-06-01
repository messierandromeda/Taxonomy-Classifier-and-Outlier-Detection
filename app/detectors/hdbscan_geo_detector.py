from typing import Any, Dict, List
import pandas as pd
from sklearn.preprocessing import StandardScaler

try:
    import hdbscan
except ImportError:
    hdbscan = None

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class HDBSCANGeoDetector(BaseDetector):
    name = "hdbscan_geo_detector"

    def __init__(
        self,
        min_cluster_size: int = 5,
        min_samples: int = 4,
    ):
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.scaler: StandardScaler | None = None
        self.model: Any | None = None

    def train(self, records: List[Dict[str, Any]]) -> None:
        if hdbscan is None:
            return

        df = pd.DataFrame(records)

        required = [
            "decimalLatitude",
            "decimalLongitude",
        ]

        if not all(field in df.columns for field in required):
            return

        coords = (
            df[required]
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )

        if len(coords) < self.min_cluster_size * 2:
            return

        self.scaler = StandardScaler().fit(coords)
        X = self.scaler.transform(coords)

        self.model = hdbscan.HDBSCAN(
            min_cluster_size=self.min_cluster_size,
            min_samples=self.min_samples,
            prediction_data=True,
        ).fit(X)

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        if hdbscan is None:
            return {get_record_id(record, index): [] for index, record in enumerate(records)}

        df = pd.DataFrame(records)

        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        required = [
            "decimalLatitude",
            "decimalLongitude",
        ]

        if not all(field in df.columns for field in required):
            return results

        coords = (
            df[required]
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )

        if len(coords) < self.min_cluster_size * 2:
            return results

        if self.model is not None and self.scaler is not None:
            X = self.scaler.transform(coords)
            labels, strengths = hdbscan.approximate_predict(self.model, X)
        else:
            # Fit with prediction_data so we can call approximate_predict()
            self.scaler = StandardScaler().fit(coords)
            X = self.scaler.transform(coords)
            self.model = hdbscan.HDBSCAN(
                min_cluster_size=self.min_cluster_size,
                min_samples=self.min_samples,
                prediction_data=True,
            ).fit(X)
            # obtain labels and membership strengths for all points
            try:
                labels, strengths = hdbscan.approximate_predict(self.model, X)
            except Exception:
                labels = self.model.labels_
                strengths = [0.0] * len(labels)

        # Outliers are flagged as -1; use membership strength to compute score
        for row_index, label, strength in zip(coords.index, labels, strengths):
            if label != -1:
                continue

            record_id = get_record_id(records[row_index], row_index)

            # membership strength in [0,1] -> lower strength => more outlier-like
            try:
                strength_val = float(strength)
            except Exception:
                strength_val = 0.0

            score = max(0.0, min(1.0, 1.0 - strength_val))
            severity = "medium" if score < 0.85 else "high"

            results[record_id].append(
                DetectionFlag(
                    field="decimalLatitude,decimalLongitude",
                    method=self.name,
                    type="coordinate_cluster_outlier",
                    severity=severity,
                    score=score,
                    message=(
                        "Coordinate pair does not belong to a dense "
                        "geographic cluster (HDBSCAN)."
                    ),
                    value={
                        "decimalLatitude": records[row_index].get("decimalLatitude"),
                        "decimalLongitude": records[row_index].get("decimalLongitude"),
                        "membership_strength": strength_val,
                    },
                )
            )

        return results
