from abc import ABC, abstractmethod
from typing import Any, Dict, List
from app.schemas import DetectionFlag


class BaseDetector(ABC):
    """Abstract base class for data-quality and outlier detectors.

    Detector implementations must define a `detect` method and may optionally
    implement `train` when they require a model or statistics built from data.
    """

    name: str

    @abstractmethod
    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Return a mapping from record identifier to a list of detection flags."""
        raise NotImplementedError

    def train(self, records: List[Dict[str, Any]]) -> None:
        """Optional training step for detectors that fit on a subset of data."""
        return None


def get_record_id(record: Dict[str, Any], index: int) -> str:
    """Choose a stable record identifier from available record fields.

    Falls back to the record index when no identifier field is present.
    """
    return str(
        record.get("id")
        or record.get("occurrenceID")
        or record.get("catalogNumber")
        or index
    )
