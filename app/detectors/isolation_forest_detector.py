from typing import Any, Dict, List
import pandas as pd
import joblib
import logging
from fastapi import HTTPException, status
from pathlib import Path
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id
from app.config import UNINITIALIZED_MSG

CURRENT_DIR = Path(__file__).resolve().parent
MODEL_PATH = CURRENT_DIR / "models" / "isolation_forest_mode.pkl"
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
SCALER_PATH = CURRENT_DIR / "models" / "isolation_forest_scaler.pkl"

class IsolationForestDetector(BaseDetector):
    name = "isolation_forest_detector"

    def __init__(
        self,
        numeric_fields: List[str] | None = None,
        contamination: float | str = "auto"
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

        joblib.dump(self.scaler, SCALER_PATH)
        logging.info(f"Isolation forest scalar successfully saved to {SCALER_PATH}")
        joblib.dump(self.model, MODEL_PATH)
        logging.info(f"Isolation forest model successfully saved to {MODEL_PATH}")

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        if MODEL_PATH.exists() and SCALER_PATH.exists():
            logging.info(f"Loading trained isolation forest model from {MODEL_PATH} and scalar from {SCALER_PATH}...")
            self.model = joblib.load(MODEL_PATH)
            self.scaler = joblib.load(SCALER_PATH)
        else:
            logging.critical(f"Model file NOT found at {MODEL_PATH}! API cannot process detections.")
                
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNINITIALIZED_MSG
            )
        
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
    
        X = self.scaler.transform(numeric)
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