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
            get_columns().get("HERBARIUM_ID", "HerbariumID"),
            "catalogNumber",
            "CatalogNumber",
            get_columns().get("BARCODE", "Barcode"),
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
            get_columns().get("BARCODE", "Barcode"),
            "barcode",
            "catalogNumber",
            "CatalogNumber",
        ],
    )

    normalized["stableUri"] = first_present(
        record,
        [
            get_columns().get("STABLE_URI", "StableURI"),
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
            get_columns().get("BILD", "Bild"),
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
            get_columns().get("DB", "DB"),
            "database",
            "Database",
            "source",
            "Source",
        ],
    )

    normalized["identifier"] = first_present(
        record,
        [
            get_columns().get("IDENTIFIER", "Identifier"),
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
            get_columns().get("FAMILY", "Family"),
            "family",
        ],
    )

    normalized["genus"] = first_present(
        record,
        [
            get_columns().get("GENUS", "Genus"),
            "genus",
        ],
    )

    normalized["scientificName"] = first_present(
        record,
        [
            get_columns().get("NAME_CACHE", "NameCache"),
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
            get_columns().get("FULL_NAME_CACHE", "FullNameCache"),
            "scientificNameFull",
            "fullScientificName",
            "FullScientificNameString",
            "scientificName",
            "ScientificName",
            get_columns().get("NAME_CACHE", "NameCache"),
        ],
    )

    normalized["country"] = first_present(
        record,
        [
            get_columns().get("COUNTRY", "Country"),
            "country",
            "countryName",
            "CountryName",
        ],
    )

    normalized["locality"] = first_present(
        record,
        [
            get_columns().get("LOCALITY", "Locality"),
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
            get_columns().get("FUNDORT_UND_OEKO", "FundortUNdOeko"),
            "habitat",
            "Habitat",
        ],
    )

    normalized["fundortUndOeko"] = first_present(
        record,
        [
            get_columns().get("FUNDORT_UND_OEKO", "FundortUNdOeko"),
            "fundortUndOeko",
            "FundortUndOeko",
        ],
    )

    normalized["decimalLatitude"] = safe_float(
        first_present(
            record,
            [
                get_columns().get("LATITUDE", "Latitude"),
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
                get_columns().get("LONGITUDE", "Longitude"),
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
            get_columns().get("SHOW_ON_MAP", "ShowOnMap"),
            "showOnMap",
            "show_on_map",
        ],
    )

    normalized["eventDate"] = first_present(
        record,
        [
            get_columns().get("COLLECTION_DATE_BEGIN", "CollectionDateBegin"),
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
            get_columns().get("COLLECTION_DATE_BEGIN", "CollectionDateBegin"),
            "collectionDateBegin",
            "eventDate",
            "EventDate",
        ],
    )

    normalized["collectionDateEnd"] = first_present(
        record,
        [
            get_columns().get("COLLECTION_DATE_END", "CollectionDateEnd"),
            "collectionDateEnd",
        ],
    )

    normalized["collector"] = first_present(
        record,
        [
            get_columns().get("SAMMLERTEAM", "Sammlerteam"),
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
            get_columns().get("SAMMELNUMMER", "Sammelnummer"),
            "collectorNumber",
            "CollectorNumber",
            "recordNumber",
            "RecordNumber",
        ],
    )

    normalized["expedition"] = first_present(
        record,
        [
            get_columns().get("EXPEDITIONSANGABE", "Expeditionsangabe"),
            "expedition",
            "Expedition",
        ],
    )

    normalized["labelText"] = first_present(
        record,
        [
            get_columns().get("TITEL_ETIKETT", "TitelEtikett"),
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
            get_columns().get("ANMERKUNGEN", "Anmerkungen"),
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
