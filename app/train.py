from __future__ import annotations

import random
from typing import Dict, List

from app.detectors.base import BaseDetector


def sample_training_records(
    records: List[Dict[str, object]],
    subset_size: int = 500,
    seed: int = 42,
) -> List[Dict[str, object]]:
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
    for detector in detectors:
        try:
            detector.train(records)
        except Exception:
            # Some detectors do not support training or may fail when data is insufficient.
            continue
