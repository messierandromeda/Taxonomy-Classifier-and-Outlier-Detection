from abc import ABC, abstractmethod
from typing import Any, Dict, List
from app.schemas import DetectionFlag


class BaseDetector(ABC):
    name: str

    @abstractmethod
    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Return a dict: record_id -> list of flags."""
        raise NotImplementedError


def get_record_id(record: Dict[str, Any], index: int) -> str:
    return str(record.get("id") or record.get("occurrenceID") or record.get("catalogNumber") or index)
