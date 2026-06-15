from typing import Any, Dict, List
import pandas as pd
from sklearn.preprocessing import StandardScaler
import joblib
import logging
import hdbscan
from pathlib import Path
from fastapi import HTTPException, status

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id
from app.config import UNINITIALIZED_MSG

CURRENT_DIR = Path(__file__).resolve().parent
MODEL_PATH = CURRENT_DIR / "models" / "hdbscan_model.pkl"
MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
SCALER_PATH = CURRENT_DIR / "models" / "hdbscan_scaler.pkl"


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

        joblib.dump(self.scaler, SCALER_PATH)
        logging.info(f"HDBSCAN scaler successfully saved to {SCALER_PATH}")

        joblib.dump(self.model, MODEL_PATH)
        logging.info(f"HDBSCAN model successfully saved to {MODEL_PATH}")

    def detect(
        self,
        records: List[Dict[str, Any]],
    ) -> Dict[str, List[DetectionFlag]]:
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        if not records:
            return results

        if MODEL_PATH.exists() and SCALER_PATH.exists():
            logging.info(
                f"Loading trained HDBSCAN model from {MODEL_PATH} "
                f"and scaler from {SCALER_PATH}..."
            )
            self.model = joblib.load(MODEL_PATH)
            self.scaler = joblib.load(SCALER_PATH)

        else:
            logging.critical(
                f"Model file NOT found at {MODEL_PATH}! "
                f"API cannot process detections."
            )

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=UNINITIALIZED_MSG,
            )

        df = pd.DataFrame(records)

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

        if coords.empty:
            return results

        X = self.scaler.transform(coords)

        try:
            labels, strengths = hdbscan.approximate_predict(
                self.model,
                X,
            )
        except Exception as exc:
            logging.warning(
                f"HDBSCAN prediction failed. "
                f"No HDBSCAN flags will be emitted for this batch: {exc}"
            )
            return results

        for row_index, label, strength in zip(
            coords.index,
            labels,
            strengths,
        ):
            if label != -1:
                continue

            record_id = get_record_id(
                records[row_index],
                row_index,
            )

            try:
                strength_val = float(strength)
            except Exception:
                strength_val = 0.0

            score = max(
                0.0,
                min(1.0, 1.0 - strength_val),
            )

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
                        "decimalLatitude": records[row_index].get(
                            "decimalLatitude"
                        ),
                        "decimalLongitude": records[row_index].get(
                            "decimalLongitude"
                        ),
                        "membership_strength": strength_val,
                    },
                )
            )

        return results