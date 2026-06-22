from typing import Any


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

    # -------------------------
    # IDs / technische Felder
    # -------------------------
    normalized["id"] = first_present(
        record,
        [
            "id",
            "ID",
            "HerbariumID",
            "catalogNumber",
            "CatalogNumber",
            "Barcode",
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
            "Barcode",
            "barcode",
            "catalogNumber",
            "CatalogNumber",
        ],
    )

    normalized["stableUri"] = first_present(
        record,
        [
            "StableURI",
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
            "Bild",
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
            "DB",
            "database",
            "Database",
            "source",
            "Source",
        ],
    )

    normalized["identifier"] = first_present(
        record,
        [
            "Identifier",
            "identifier",
            "identifiedBy",
            "IdentifiedBy",
            "recordedBy",
            "RecordedBy",
        ],
    )

    # -------------------------
    # Taxonomie
    # -------------------------
    normalized["family"] = first_present(
        record,
        [
            "Family",
            "family",
        ],
    )

    normalized["genus"] = first_present(
        record,
        [
            "Genus",
            "genus",
        ],
    )

    normalized["scientificName"] = first_present(
        record,
        [
            "NameCache",
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
            "FullNameCache",
            "scientificNameFull",
            "fullScientificName",
            "FullScientificNameString",
            "scientificName",
            "ScientificName",
            "NameCache",
        ],
    )

    # -------------------------
    # Geografie / Fundort
    # -------------------------
    normalized["country"] = first_present(
        record,
        [
            "Country",
            "country",
            "countryName",
            "CountryName",
        ],
    )

    normalized["locality"] = first_present(
        record,
        [
            "Locality",
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
            "FundortUNdOeko",
            "habitat",
            "Habitat",
        ],
    )

    normalized["fundortUndOeko"] = first_present(
        record,
        [
            "FundortUNdOeko",
            "fundortUndOeko",
            "FundortUndOeko",
        ],
    )

    normalized["decimalLatitude"] = safe_float(
        first_present(
            record,
            [
                "Latitude",
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
                "Longitude",
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
            "ShowOnMap",
            "showOnMap",
            "show_on_map",
        ],
    )

    # -------------------------
    # Datum / Sammlung
    # -------------------------
    normalized["eventDate"] = first_present(
        record,
        [
            "CollectionDateBegin",
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
            "CollectionDateBegin",
            "collectionDateBegin",
            "eventDate",
            "EventDate",
        ],
    )

    normalized["collectionDateEnd"] = first_present(
        record,
        [
            "CollectionDateEnd",
            "collectionDateEnd",
        ],
    )

    normalized["collector"] = first_present(
        record,
        [
            "Sammlerteam",
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
            "Sammelnummer",
            "collectorNumber",
            "CollectorNumber",
            "recordNumber",
            "RecordNumber",
        ],
    )

    normalized["expedition"] = first_present(
        record,
        [
            "Expeditionsangabe",
            "expedition",
            "Expedition",
        ],
    )

    # -------------------------
    # Texte / Notizen / Label
    # -------------------------
    normalized["labelText"] = first_present(
        record,
        [
            "TitelEtikett",
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
            "Anmerkungen",
            "collectorNotes",
            "collector_notes",
            "notes",
            "Notes",
        ],
    )

    # -------------------------
    # Kombinierter Text für LLM / semantische Checks
    # -------------------------
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
