from typing import Any, Dict, List
from datetime import datetime
from urllib.parse import urlparse
import re

from app.schemas import DetectionFlag
from app.detectors.base import BaseDetector, get_record_id


class RuleDetector(BaseDetector):
    """Simple rules-based detector for coordinate, date, taxonomic, and metadata issues."""
    name = "rule_detector"

    def detect(self, records: List[Dict[str, Any]]) -> Dict[str, List[DetectionFlag]]:
        """Flag syntactic and basic semantic issues in each record."""
        results: Dict[str, List[DetectionFlag]] = {}

        for index, record in enumerate(records):
            record_id = get_record_id(record, index)
            flags: List[DetectionFlag] = []

            lat = self._to_float(record.get("decimalLatitude"))
            lon = self._to_float(record.get("decimalLongitude"))

            if lat is None:
                flags.append(DetectionFlag(
                    field="decimalLatitude",
                    method=self.name,
                    type="missing_or_invalid_coordinate",
                    severity="low",
                    score=0.2,
                    message="Latitude is missing or not numeric.",
                    value=record.get("decimalLatitude"),
                ))
            elif lat < -90 or lat > 90:
                flags.append(DetectionFlag(
                    field="decimalLatitude",
                    method=self.name,
                    type="invalid_coordinate_range",
                    severity="critical",
                    score=1.0,
                    message="Latitude must be between -90 and 90.",
                    value=lat,
                ))

            if lon is None:
                flags.append(DetectionFlag(
                    field="decimalLongitude",
                    method=self.name,
                    type="missing_or_invalid_coordinate",
                    severity="low",
                    score=0.2,
                    message="Longitude is missing or not numeric.",
                    value=record.get("decimalLongitude"),
                ))
            elif lon < -180 or lon > 180:
                flags.append(DetectionFlag(
                    field="decimalLongitude",
                    method=self.name,
                    type="invalid_coordinate_range",
                    severity="critical",
                    score=1.0,
                    message="Longitude must be between -180 and 180.",
                    value=lon,
                ))

            begin_raw = record.get("collectionDateBegin") or record.get("eventDate")
            end_raw = record.get("collectionDateEnd")

            begin_date = self._parse_date(begin_raw)
            end_date = self._parse_date(end_raw)

            if self._is_empty(begin_raw):
                flags.append(DetectionFlag(
                    field="collectionDateBegin",
                    method=self.name,
                    type="missing_date",
                    severity="medium",
                    score=0.5,
                    message="CollectionDateBegin is missing.",
                    value=begin_raw,
                ))
            elif begin_date is None:
                flags.append(DetectionFlag(
                    field="collectionDateBegin",
                    method=self.name,
                    type="invalid_date_format",
                    severity="medium",
                    score=0.7,
                    message="CollectionDateBegin could not be parsed.",
                    value=begin_raw,
                ))

            if not self._is_empty(end_raw) and end_date is None:
                flags.append(DetectionFlag(
                    field="collectionDateEnd",
                    method=self.name,
                    type="invalid_date_format",
                    severity="medium",
                    score=0.7,
                    message="CollectionDateEnd could not be parsed.",
                    value=end_raw,
                ))

            if begin_date is not None and end_date is not None and begin_date > end_date:
                flags.append(DetectionFlag(
                    field="collectionDateBegin,collectionDateEnd",
                    method=self.name,
                    type="invalid_date_order",
                    severity="high",
                    score=0.85,
                    message="CollectionDateBegin is after CollectionDateEnd.",
                    value={
                        "collectionDateBegin": begin_raw,
                        "collectionDateEnd": end_raw,
                    },
                ))

            for field_name, raw_value, parsed_date in [
                ("collectionDateBegin", begin_raw, begin_date),
                ("collectionDateEnd", end_raw, end_date),
            ]:
                if parsed_date is None:
                    continue

                if parsed_date.date() > datetime.now().date():
                    flags.append(DetectionFlag(
                        field=field_name,
                        method=self.name,
                        type="future_date",
                        severity="high",
                        score=0.85,
                        message=f"{field_name} is in the future.",
                        value=raw_value,
                    ))

                if parsed_date.year < 1500:
                    flags.append(DetectionFlag(
                        field=field_name,
                        method=self.name,
                        type="implausibly_old_date",
                        severity="medium",
                        score=0.65,
                        message=f"{field_name} is implausibly old for this dataset.",
                        value=raw_value,
                    ))

            family = record.get("family")
            genus = record.get("genus")
            scientific_name = record.get("scientificName")
            scientific_name_full = record.get("scientificNameFull")

            if self._is_empty(family):
                flags.append(DetectionFlag(
                    field="family",
                    method=self.name,
                    type="missing_taxonomic_field",
                    severity="medium",
                    score=0.5,
                    message="Family is missing.",
                    value=family,
                ))

            if self._is_empty(genus):
                flags.append(DetectionFlag(
                    field="genus",
                    method=self.name,
                    type="missing_taxonomic_field",
                    severity="medium",
                    score=0.5,
                    message="Genus is missing.",
                    value=genus,
                ))

            if self._is_empty(scientific_name) and self._is_empty(scientific_name_full):
                flags.append(DetectionFlag(
                    field="scientificName,scientificNameFull",
                    method=self.name,
                    type="missing_taxonomic_field",
                    severity="high",
                    score=0.8,
                    message="Scientific name is missing.",
                    value={
                        "scientificName": scientific_name,
                        "scientificNameFull": scientific_name_full,
                    },
                ))

            if (
                not self._is_empty(genus)
                and not self._is_empty(scientific_name)
                and not str(scientific_name).lower().startswith(str(genus).lower())
            ):
                flags.append(DetectionFlag(
                    field="genus,scientificName",
                    method=self.name,
                    type="taxonomic_internal_inconsistency",
                    severity="high",
                    score=0.85,
                    message="Genus does not match the beginning of the scientific name.",
                    value={
                        "genus": genus,
                        "scientificName": scientific_name,
                    },
                ))

            if not self._is_empty(scientific_name) and not self._looks_like_scientific_name(scientific_name):
                flags.append(DetectionFlag(
                    field="scientificName",
                    method=self.name,
                    type="invalid_taxonomic_format",
                    severity="low",
                    score=0.35,
                    message="Scientific name format looks unusual.",
                    value=scientific_name,
                ))

            country = record.get("country")
            locality = record.get("locality")
            habitat = record.get("habitat")
            fundort_und_oeko = record.get("fundortUndOeko")

            if self._is_empty(country):
                flags.append(DetectionFlag(
                    field="country",
                    method=self.name,
                    type="missing_geographic_field",
                    severity="medium",
                    score=0.5,
                    message="Country is missing.",
                    value=country,
                ))

            if self._is_empty(locality):
                flags.append(DetectionFlag(
                    field="locality",
                    method=self.name,
                    type="missing_geographic_field",
                    severity="low",
                    score=0.35,
                    message="Locality is missing.",
                    value=locality,
                ))

            if self._is_empty(habitat) and self._is_empty(fundort_und_oeko):
                flags.append(DetectionFlag(
                    field="habitat,fundortUndOeko",
                    method=self.name,
                    type="missing_geographic_or_habitat_text",
                    severity="low",
                    score=0.35,
                    message="FundortUNdOeko / habitat text is missing.",
                    value={
                        "habitat": habitat,
                        "fundortUndOeko": fundort_und_oeko,
                    },
                ))

            herbarium_id = record.get("id")
            database = record.get("database")
            barcode = record.get("barcode")
            stable_uri = record.get("stableUri")

            if self._is_empty(herbarium_id):
                flags.append(DetectionFlag(
                    field="id",
                    method=self.name,
                    type="missing_identifier",
                    severity="high",
                    score=0.8,
                    message="HerbariumID / record id is missing.",
                    value=herbarium_id,
                ))

            if self._is_empty(database):
                flags.append(DetectionFlag(
                    field="database",
                    method=self.name,
                    type="missing_identifier",
                    severity="medium",
                    score=0.5,
                    message="DB value is missing.",
                    value=database,
                ))

            if self._is_empty(barcode):
                flags.append(DetectionFlag(
                    field="barcode",
                    method=self.name,
                    type="missing_identifier",
                    severity="medium",
                    score=0.5,
                    message="Barcode is missing.",
                    value=barcode,
                ))
            elif not self._looks_like_barcode(barcode):
                flags.append(DetectionFlag(
                    field="barcode",
                    method=self.name,
                    type="invalid_barcode_format",
                    severity="low",
                    score=0.35,
                    message="Barcode format looks unusual.",
                    value=barcode,
                ))

            if self._is_empty(stable_uri):
                flags.append(DetectionFlag(
                    field="stableUri",
                    method=self.name,
                    type="missing_identifier",
                    severity="medium",
                    score=0.5,
                    message="StableURI is missing.",
                    value=stable_uri,
                ))
            elif not self._is_valid_url(stable_uri):
                flags.append(DetectionFlag(
                    field="stableUri",
                    method=self.name,
                    type="invalid_url",
                    severity="medium",
                    score=0.7,
                    message="StableURI is not a valid http/https URL.",
                    value=stable_uri,
                ))

            notes = record.get("collectorNotes")

            if not self._is_empty(notes):
                text = str(notes).strip()

                if len(text) < 3:
                    flags.append(DetectionFlag(
                        field="collectorNotes",
                        method=self.name,
                        type="suspicious_free_text",
                        severity="low",
                        score=0.3,
                        message="Anmerkungen text is extremely short.",
                        value=notes,
                    ))

                if re.fullmatch(r"[\W_]+", text):
                    flags.append(DetectionFlag(
                        field="collectorNotes",
                        method=self.name,
                        type="suspicious_free_text",
                        severity="low",
                        score=0.35,
                        message="Anmerkungen contains only symbols or punctuation.",
                        value=notes,
                    ))

            results[record_id] = flags

        return results

    @staticmethod
    def _is_empty(value: Any) -> bool:
        """Return True for values that should be treated as missing."""
        return value is None or value == "" or str(value).strip().lower() == "nan"

    @staticmethod
    def _to_float(value: Any) -> float | None:
        """Attempt to convert a value to float, returning None on failure."""
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_date(value: Any) -> datetime | None:
        """Parse common date string formats into datetime objects."""
        if value is None or value == "":
            return None

        text = str(value).strip()

        if not text:
            return None

        formats = [
            "%Y-%m-%d",
            "%Y-%m",
            "%Y",
            "%d.%m.%Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%m/%d/%Y"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue

        if len(text) >= 4 and text[:4].isdigit():
            try:
                return datetime(int(text[:4]), 1, 1)
            except ValueError:
                return None

        return None

    @staticmethod
    def _looks_like_scientific_name(value: Any) -> bool:
        """Return True if a value resembles a binomial scientific name."""
        text = str(value).strip()

        if not text:
            return False

        return bool(re.match(r"^[A-ZÄÖÜ][a-zäöüß-]+(\s+[a-zäöüß-]+)?", text))

    @staticmethod
    def _looks_like_barcode(value: Any) -> bool:
        """Return True if a value resembles a herbarium barcode identifier."""
        text = str(value).strip()

        if not text:
            return False

        # Allows common herbarium barcode formats like:
        # "T 00000001", "B 10 123456", "BGBM12345"
        return bool(
            re.match(
                r"^[A-Za-z0-9][A-Za-z0-9 ._:/-]{2,80}$",
                text,
            )
        )

    @staticmethod
    def _is_valid_url(value: Any) -> bool:
        """Validate that a string is a well-formed http or https URL."""
        text = str(value).strip()

        try:
            parsed = urlparse(text)
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False