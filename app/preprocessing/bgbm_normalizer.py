from typing import Any
from ..config import get_columns


def is_empty(value: Any) -> bool:
    return value is None or value == "" or str(value).lower() == "nan"


def first_present(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if not is_empty(value):
            return value
    return None


def safe_float(value: Any) -> float | None:
    if is_empty(value):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_bgbm_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(record)

    normalized["id"] = first_present(
        record,
        [
            "id",
            "ID",
            get_columns().get("HERBARIUM_ID"),
            "catalogNumber",
            "CatalogNumber",
            get_columns().get("BARCODE"),
            "barcode",
            "occurrenceID",
            "OccurrenceID",
            "objectId",
            "record_id",
        ],
    )

    normalized["barcode"] = first_present(
        record,
        [
            get_columns().get("BARCODE"),
            "barcode",
            "catalogNumber",
            "CatalogNumber",
        ],
    )

    normalized["stableUri"] = first_present(
        record,
        [
            get_columns().get("STABLE_URI"),
            "stableUri",
            "stableURI",
            "uri",
            "URI",
            "objectUrl",
            "ObjectURL",
        ],
    )

    normalized["imageUrl"] = first_present(
        record,
        [
            get_columns().get("BILD"),
            "image",
            "Image",
            "imageUrl",
            "ImageURL",
            "mediaUrl",
            "MediaURL",
            "iiifManifest",
        ],
    )

    normalized["database"] = first_present(
        record,
        [
            get_columns().get("DB"),
            "database",
            "Database",
            "source",
            "Source",
        ],
    )

    normalized["identifier"] = first_present(
        record,
        [
            get_columns().get("IDENTIFIER"),
            "identifier",
            "identifiedBy",
            "IdentifiedBy",
            "recordedBy",
            "RecordedBy",
        ],
    )

    normalized["family"] = first_present(
        record,
        [
            get_columns().get("FAMILY"),
            "family",
        ],
    )

    normalized["genus"] = first_present(
        record,
        [
            get_columns().get("GENUS"),
            "genus",
        ],
    )

    normalized["scientificName"] = first_present(
        record,
        [
            get_columns().get("NAME_CACHE"),
            "scientificName",
            "ScientificName",
            "scientific_name",
            "species",
            "Species",
            "taxon",
            "Taxon",
        ],
    )

    normalized["scientificNameFull"] = first_present(
        record,
        [
            get_columns().get("FULL_NAME_CACHE"),
            "scientificNameFull",
            "fullScientificName",
            "FullScientificNameString",
            "scientificName",
            "ScientificName",
            get_columns().get("NAME_CACHE"),
        ],
    )

    normalized["country"] = first_present(
        record,
        [
            get_columns().get("COUNTRY"),
            "country",
            "countryName",
            "CountryName",
        ],
    )

    normalized["locality"] = first_present(
        record,
        [
            get_columns().get("LOCALITY"),
            "locality",
            "verbatimLocality",
            "VerbatimLocality",
            "location",
            "Location",
        ],
    )

    normalized["habitat"] = first_present(
        record,
        [
            get_columns().get("FUNDORT_UND_OEKO"),
            "habitat",
            "Habitat",
        ],
    )

    normalized["fundortUndOeko"] = first_present(
        record,
        [
            get_columns().get("FUNDORT_UND_OEKO"),
            "fundortUndOeko",
            "FundortUndOeko",
        ],
    )

    normalized["decimalLatitude"] = safe_float(
        first_present(
            record,
            [
                get_columns().get("LATITUDE"),
                "decimalLatitude",
                "DecimalLatitude",
                "latitude",
                "lat",
                "Lat",
            ],
        )
    )

    normalized["decimalLongitude"] = safe_float(
        first_present(
            record,
            [
                get_columns().get("LONGITUDE"),
                "decimalLongitude",
                "DecimalLongitude",
                "longitude",
                "lon",
                "lng",
                "Long",
                "Lng",
            ],
        )
    )

    normalized["showOnMap"] = first_present(
        record,
        [
            get_columns().get("SHOW_ON_MAP"),
            "showOnMap",
            "show_on_map",
        ],
    )

    normalized["eventDate"] = first_present(
        record,
        [
            get_columns().get("COLLECTION_DATE_BEGIN"),
            "eventDate",
            "EventDate",
            "date",
            "Date",
            "collectionDate",
            "CollectionDate",
        ],
    )

    normalized["collectionDateBegin"] = first_present(
        record,
        [
            get_columns().get("COLLECTION_DATE_BEGIN"),
            "collectionDateBegin",
            "eventDate",
            "EventDate",
        ],
    )

    normalized["collectionDateEnd"] = first_present(
        record,
        [
            get_columns().get("COLLECTION_DATE_END"),
            "collectionDateEnd",
        ],
    )

    normalized["collector"] = first_present(
        record,
        [
            get_columns().get("SAMMLERTEAM"),
            "collector",
            "Collector",
            "recordedBy",
            "RecordedBy",
            "collectors",
            "Collectors",
        ],
    )

    normalized["collectorNumber"] = first_present(
        record,
        [
            get_columns().get("SAMMELNUMMER"),
            "collectorNumber",
            "CollectorNumber",
            "recordNumber",
            "RecordNumber",
        ],
    )

    normalized["expedition"] = first_present(
        record,
        [
            get_columns().get("EXPEDITIONSANGABE"),
            "expedition",
            "Expedition",
        ],
    )

    normalized["labelText"] = first_present(
        record,
        [
            get_columns().get("TITEL_ETIKETT"),
            "labelText",
            "LabelText",
            "label",
            "Label",
            "description",
            "Description",
            "verbatimLabel",
            "VerbatimLabel",
        ],
    )

    normalized["collectorNotes"] = first_present(
        record,
        [
            get_columns().get("ANMERKUNGEN"),
            "collectorNotes",
            "collector_notes",
            "notes",
            "Notes",
        ],
    )

    normalized["semanticText"] = " | ".join(
        str(value)
        for value in [
            normalized.get("scientificName"),
            normalized.get("scientificNameFull"),
            normalized.get("family"),
            normalized.get("genus"),
            normalized.get("country"),
            normalized.get("locality"),
            normalized.get("habitat"),
            normalized.get("fundortUndOeko"),
            normalized.get("collector"),
            normalized.get("collectorNumber"),
            normalized.get("eventDate"),
            normalized.get("collectionDateBegin"),
            normalized.get("collectionDateEnd"),
            normalized.get("expedition"),
            normalized.get("collectorNotes"),
            normalized.get("labelText"),
        ]
        if not is_empty(value)
    )

    return normalized
