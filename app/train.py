import random
from typing import Dict, List
import logging
import pandas as pd
from pathlib import Path
from app.detectors.base import BaseDetector
from app.detectors.iqr_detector import IQRDetector
from app.detectors.zscore_detector import ZScoreDetector
from app.detectors.modified_zscore_detector import ModifiedZScoreDetector

from app.detectors.date_outlier_detector import DateOutlierDetector

from app.detectors.isolation_forest_detector import (
    IsolationForestDetector,
)
from app.pipeline import prepare_records

from app.detectors.hdbscan_geo_detector import HDBSCANGeoDetector


def sample_training_records(
    records: List[Dict[str, object]],
    subset_size: int = 500,
    seed: int = 42,
) -> List[Dict[str, object]]:
    """Randomly sample a reproducible subset of records for detector training."""
    if subset_size <= 0 or not records:
        return []

    if subset_size >= len(records):
        return records

    rng = random.Random(seed)
    return rng.sample(records, k=subset_size)


def train_detectors(
    detectors: list[BaseDetector],
    records: List[Dict[str, object]],
) -> None:
    """Train each detector on the provided record set, ignoring failures.

    Some detectors may be unable to train on a given dataset; failures are
    logged and skipped so the pipeline can continue.
    """
    for detector in detectors:
        try:
            detector.train(records)
        except Exception as e:
            detector_name = getattr(detector, "name", detector.__class__.__name__)
            logging.warning(f"Skipping training {detector_name}: {e}")
            continue


def run_training(
    records: list[dict],
    training_subset_size: int = 500,
    training_seed: int = 42,
):
    """Prepare records and train the offline detector ensemble.

    This helper normalizes input records, samples a training subset, and
    executes model/statistic training for each applicable detector.
    """
    result = prepare_records(records)

    outlier_detectors = [
        IQRDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        ZScoreDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        ModifiedZScoreDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        DateOutlierDetector(date_fields=["collectionDateBegin"]),
        IsolationForestDetector(numeric_fields=["decimalLatitude", "decimalLongitude"]),
        HDBSCANGeoDetector(),
    ]
    if training_subset_size and training_subset_size > 0:
        training_records = sample_training_records(
            result,
            subset_size=training_subset_size,
            seed=training_seed,
        )
        logging.info(
            f"[TRAIN] Training detectors on {len(training_records)} record subset"
        )
        train_detectors(outlier_detectors, training_records)


CURRENT_DIR = Path(__file__).resolve().parent
RAW_PATH = CURRENT_DIR / "data" / "train.csv"
SHUFFLED_PATH = Path("data/shuffled_training_data.csv")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if SHUFFLED_PATH.exists():
        df = pd.read_csv(SHUFFLED_PATH)
        logging.info(f"Loading {SHUFFLED_PATH} for training...")
    else:
        if RAW_PATH.exists():
            logging.info(f"Loading {RAW_PATH}...")
            df = pd.read_csv(RAW_PATH, low_memory=False)
            shuffled_df = df.sample(frac=0.5, random_state=42).reset_index(drop=True)
            try:
                shuffled_df.to_csv(SHUFFLED_PATH, index=False)
                logging.info(f"{SHUFFLED_PATH} is converted")
            except PermissionError as e:
                logging.error(
                    f'{e} -> Run the command "sudo chown -R $(whoami):$(id -gn) ."'
                )
            except Exception as e:
                logging.error(f"{e}")
        else:
            raise FileNotFoundError(f"Error: Raw data file missing at {RAW_PATH}")

    try:
        raw_records = df.to_dict(orient="records")
        run_training(raw_records, training_subset_size=100000, training_seed=42)
        logging.info("Offline ensemble training pipeline completed successfully.")
    except Exception as e:
        logging.error(f"Offline training execution failed: {e}")
