from typing import Any, Dict, List
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class DBSCANGeoDetector(BaseDetector):
    name = "dbscan_geo_detector"

    def __init__(
        self,
        eps: float = 0.7,
        min_samples: int = 4,
    ):
        # Maximum distance between neighboring points.
        self.eps = eps

        # Minimum number of nearby points needed to form a cluster.
        self.min_samples = min_samples

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        df = pd.DataFrame(records)

        # Create empty result lists for all records.
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        required = [
            "decimalLatitude",
            "decimalLongitude",
        ]

        # DBSCAN only works if both coordinate fields exist.
        if not all(field in df.columns for field in required):
            return results

        # Convert coordinates to numeric values.
        coords = (
            df[required]
            .apply(pd.to_numeric, errors="coerce")
            .dropna()
        )

        # Too few points would create unstable clustering.
        if len(coords) < self.min_samples * 2:
            return results

        # Standardize coordinates before clustering.
        X = StandardScaler().fit_transform(coords)

        model = DBSCAN(
            eps=self.eps,
            min_samples=self.min_samples,
        )

        labels = model.fit_predict(X)

        # DBSCAN marks noise points as -1.
        for row_index, label in zip(coords.index, labels):
            if label != -1:
                continue

            record_id = get_record_id(records[row_index], row_index)

            results[record_id].append(
                DetectionFlag(
                    field="decimalLatitude,decimalLongitude",
                    method=self.name,
                    type="coordinate_cluster_outlier",
                    severity="high",
                    score=0.85,
                    message=(
                        "Coordinate pair does not belong to a dense "
                        "geographic cluster."
                    ),
                    value={
                        "decimalLatitude": records[row_index].get("decimalLatitude"),
                        "decimalLongitude": records[row_index].get("decimalLongitude"),
                    },
                )
            )

        return results