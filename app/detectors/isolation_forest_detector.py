from typing import Any, Dict, List
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class IsolationForestDetector(BaseDetector):
    name = "isolation_forest_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        contamination: float = 0.05,
    ):

        self.numeric_fields = numeric_fields or [
            "decimalLatitude",
            "decimalLongitude",
        ]
        self.contamination = contamination
        self.scaler: StandardScaler | None = None
        self.model: IsolationForest | None = None

    def train(self, records: List[Dict[str, Any]]) -> None:
        df = pd.DataFrame(records)
        fields = [
            field
            for field in self.numeric_fields
            if field in df.columns
        ]

        if not fields:
            return

        numeric = df[fields].apply(pd.to_numeric, errors="coerce").dropna()

        if len(numeric) < 10:
            return

        self.scaler = StandardScaler().fit(numeric)
        X = self.scaler.transform(numeric)

        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
        ).fit(X)

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        df = pd.DataFrame(records)

        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        fields = [
            field
            for field in self.numeric_fields
            if field in df.columns
        ]

        if not fields:
            return results

        numeric = df[fields].apply(pd.to_numeric, errors="coerce").dropna()

        if len(numeric) < 10:
            return results

        if self.model is not None and self.scaler is not None:
            X = self.scaler.transform(numeric)
            predictions = self.model.predict(X)
            scores = -self.model.score_samples(X)
        else:
            self.scaler = StandardScaler().fit(numeric)
            X = self.scaler.transform(numeric)
            self.model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
            ).fit(X)
            predictions = self.model.predict(X)
            scores = -self.model.score_samples(X)

        max_score = max(scores) if len(scores) else 1.0

        for row_index, prediction, raw_score in zip(
            numeric.index,
            predictions,
            scores,
        ):
            if prediction != -1:
                continue

            record_id = get_record_id(records[row_index], row_index)
            score = min(1.0, float(raw_score / max_score))
            
            if fields == ["decimalLatitude", "decimalLongitude"]:
                flag_type = "coordinate_multivariate_outlier"
                message = (
                    "Coordinate pair is unusual when latitude and longitude "
                    "are considered together."
                )
            elif "eventYear" in fields:
                flag_type = "coordinate_date_multivariate_outlier"
                message = (
                    "Record is unusual when coordinates and collection year "
                    "are considered together."
                )
            else:
                flag_type = "multivariate_outlier"
                message = (
                    "Record is unusual when selected numeric fields are "
                    "considered together."
                )

            results[record_id].append(
                DetectionFlag(
                    field=",".join(fields),
                    method=self.name,
                    type=flag_type,
                    severity="medium" if score < 0.85 else "high",
                    score=score,
                    message=message,
                    value={
                        field: records[row_index].get(field)
                        for field in fields
                    },
                )
            )

        return results