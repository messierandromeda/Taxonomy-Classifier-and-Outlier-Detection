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
    """Detector that uses HDBSCAN on geographic coordinates to identify spatial outliers.

    The detector trains an HDBSCAN model on numeric latitude/longitude pairs and uses
    approximate cluster prediction to locate coordinate records that do not belong to
    any dense geographic cluster.
    """

    name = "hdbscan_geo_detector"

    def __init__(
        self,
        min_cluster_size: int = 5,
        min_samples: int = 4,
    ):
        """Initialize the detector with clustering hyperparameters.

        Args:
            min_cluster_size: Minimum number of points to form an HDBSCAN cluster.
            min_samples: Minimum number of samples used for core distance estimation.
        """
        self.min_cluster_size = min_cluster_size
        self.min_samples = min_samples
        self.scaler: StandardScaler | None = None
        self.model: Any | None = None

    def train(self, records: List[Dict[str, Any]]) -> None:
        """Fit the geographic clustering model and persist the scaler and model files.

        The training pipeline:
        1. Converts records into a DataFrame.
        2. Validates that latitude and longitude fields exist.
        3. Converts coordinate fields to numeric values and drops invalid rows.
        4. Requires at least twice the minimum cluster size to proceed.
        5. Fits a StandardScaler to normalize coordinates.
        6. Trains HDBSCAN on the scaled coordinates.
        7. Saves the trained scaler and model to disk for later detection.
        """
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
        """Detect coordinate records that are spatial outliers relative to trained clusters.

        Detection steps:
        1. Initialize a result map for every record.
        2. Return early if there are too few records to evaluate.
        3. Load the persisted scaler and HDBSCAN model from disk.
        4. Convert required coordinate fields to numeric values.
        5. Transform coordinates with the loaded scaler.
        6. Use HDBSCAN approximate prediction to obtain cluster labels and membership strengths.
        7. Flag records labeled -1 as outliers and compute a severity score from membership strength.

        Returns:
            A mapping from record identifiers to a list of DetectionFlag objects.
        """
        results = {
            get_record_id(record, index): []
            for index, record in enumerate(records)
        }

        if len(records) < self.min_cluster_size * 2:
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

        if len(coords) < self.min_cluster_size * 2:
            return results

        X = self.scaler.transform(coords)

        try:
            labels, strengths = hdbscan.approximate_predict(
                self.model,
                X,
            )
        except Exception:
            labels = [-1] * len(X)
            strengths = [0.0] * len(X)

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