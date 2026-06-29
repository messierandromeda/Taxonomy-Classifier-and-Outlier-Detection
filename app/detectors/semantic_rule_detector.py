from typing import Any, Dict, List
from datetime import datetime
import re

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class SemanticRuleDetector(BaseDetector):
    """Detects higher-level semantic contradictions in habitat, locality, and species."""

    name = "semantic_rule_detector"

    SPECIES_HABITAT_RULES = {
        "cocos nucifera": {
            "contradiction": [
                "snow",
                "alpine",
                "mountain forest",
                "thueringer wald",
            ],
            "message": (
                "Cocos nucifera is tropical, but the habitat "
                "describes cold or alpine conditions."
            ),
        },
        "carnegiea gigantea": {
            "contradiction": [
                "swamp",
                "wetland",
                "river",
                "forest",
                "wald",
            ],
            "message": (
                "Carnegiea gigantea is a desert cactus, "
                "but the habitat describes wet conditions."
            ),
        },
        "nymphaea alba": {
            "contradiction": [
                "dry grassland",
                "trockenrasen",
                "dry cliff",
            ],
            "message": (
                "Nymphaea alba is aquatic, but the habitat "
                "describes dry terrestrial conditions."
            ),
        },
    }

    MARINE_TERMS = [
        "marine",
        "sea",
        "ocean",
        "coast",
        "coral",
        "reef",
        "meer",
        "küste",
        "riff",
    ]

    INLAND_TERMS = [
        "mountain",
        "forest",
        "wald",
        "berg",
        "trockenrasen",
        "dry meadow",
        "alpine",
    ]

    WATER_TERMS = [
        "water",
        "river",
        "lake",
        "wetland",
        "swamp",
        "fluss",
        "see",
        "moor",
        "sumpf",
    ]

    DRY_TERMS = [
        "dry",
        "arid",
        "xeric",
        "trocken",
        "steppe",
        "desert",
    ]

    FOREIGN_COUNTRY_TERMS = [
        "brazil",
        "mexico",
        "india",
        "china",
        "australia",
        "argentina",
        "chile",
        "afrika",
        "africa",
    ]

    def detect(
        self,
        records: List[Dict[str, Any]],
    ) -> Dict[str, List[DetectionFlag]]:
        """Evaluate records for semantic contradictions using rule-based text matching."""

        results = {
            get_record_id(record, index): [] for index, record in enumerate(records)
        }

        for index, record in enumerate(records):
            record_id = get_record_id(record, index)

            scientific_name = self._norm(record.get("scientificName"))
            country = self._norm(record.get("country"))
            locality = self._norm(record.get("locality"))
            habitat = self._norm(record.get("habitat"))
            notes = self._norm(record.get("collectorNotes"))
            label_text = self._norm(record.get("labelText"))

            combined_text = " ".join(
                [
                    scientific_name,
                    country,
                    locality,
                    habitat,
                    notes,
                    label_text,
                ]
            )

            if self._has(combined_text, self.MARINE_TERMS) and self._has(
                combined_text, self.INLAND_TERMS
            ):
                results[record_id].append(
                    DetectionFlag(
                        field="locality,habitat",
                        method=self.name,
                        type="marine_inland_contradiction",
                        severity="medium",
                        score=0.7,
                        message=(
                            "Marine/coastal terms occur together with "
                            "strong inland or mountain habitat terms."
                        ),
                        value={
                            "locality": record.get("locality"),
                            "habitat": record.get("habitat"),
                        },
                    )
                )

            if self._has(combined_text, self.WATER_TERMS) and self._has(
                combined_text, self.DRY_TERMS
            ):
                results[record_id].append(
                    DetectionFlag(
                        field="locality,habitat",
                        method=self.name,
                        type="water_dry_habitat_mixture",
                        severity="low",
                        score=0.45,
                        message=(
                            "Record contains both water-related and dry-habitat terms."
                        ),
                        value={
                            "locality": record.get("locality"),
                            "habitat": record.get("habitat"),
                        },
                    )
                )

            if country in ["germany", "deutschland"] and self._has(
                combined_text, self.FOREIGN_COUNTRY_TERMS
            ):
                results[record_id].append(
                    DetectionFlag(
                        field="country,locality",
                        method=self.name,
                        type="country_locality_contradiction",
                        severity="medium",
                        score=0.85,
                        message=(
                            "Country is Germany, but the locality text "
                            "contains strong foreign-country indicators."
                            "This can imply that the sample is collected abroad."
                        ),
                        value={
                            "country": record.get("country"),
                            "locality": record.get("locality"),
                        },
                    )
                )

            species_flag = self._check_species_rules(
                scientific_name,
                combined_text,
                record,
            )

            if species_flag is not None:
                results[record_id].append(species_flag)

        return results

    def _check_species_rules(
        self,
        scientific_name: str,
        combined_text: str,
        record: Dict[str, Any],
    ) -> DetectionFlag | None:
        """Check species-specific habitat contradiction rules and return a flag."""

        for species_name, rule in self.SPECIES_HABITAT_RULES.items():
            if species_name not in scientific_name:
                continue

            if self._has(combined_text, rule["contradiction"]):
                return DetectionFlag(
                    field="scientificName,habitat,locality",
                    method=self.name,
                    type="species_habitat_contradiction",
                    severity="high",
                    score=0.85,
                    message=rule["message"],
                    value={
                        "scientificName": record.get("scientificName"),
                        "locality": record.get("locality"),
                        "habitat": record.get("habitat"),
                    },
                )

        return None

    @staticmethod
    def _norm(value: Any) -> str:
        """Normalize a text value for case-insensitive keyword matching."""
        if value is None:
            return ""

        text = str(value).lower().strip()

        replacements = {
            "ä": "ae",
            "ö": "oe",
            "ü": "ue",
            "ß": "ss",
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        text = re.sub(r"\s+", " ", text)

        return text

    @classmethod
    def _has(
        cls,
        text: str,
        terms: List[str],
    ) -> bool:
        """Return True when any normalized term appears in the text."""

        normalized_terms = [cls._norm(term) for term in terms]

        return any(term in text for term in normalized_terms)

    @staticmethod
    def _is_future_date(value: Any) -> bool:
        """Return True when a value represents a future date."""
        if value is None:
            return False

        text = str(value).strip()

        formats = ["%Y-%m-%d", "%Y-%m", "%Y", "%d.%m.%Y", "%d/%m/%Y", "%m/%d/%Y"]

        for fmt in formats:
            try:
                parsed = datetime.strptime(text, fmt)
                return parsed.date() > datetime.now().date()
            except ValueError:
                continue

        return False
