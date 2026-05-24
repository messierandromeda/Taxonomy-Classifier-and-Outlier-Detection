from typing import Any
import pandas as pd
import datetime
from app.preprocessing.bgbm_normalizer import (
    normalize_bgbm_record,
)
from fastapi import HTTPException

# --------------------------------------------------
# Expected BGBM CSV column order
# --------------------------------------------------

BGBM_COLUMNS = [
    "HerbariumID",
    "Bild",
    "DB",
    "Family",
    "FullNameCache",
    "Anmerkungen",
    "Sammlerteam",
    "Sammelnummer",
    "CollectionDateBegin",
    "CollectionDateEnd",
    "Country",
    "Locality",
    "TitelEtikett",
    "Expeditionsangabe",
    "ShowOnMap",
    "Latitude",
    "Longitude",
    "FundortUNdOeko",
    "NameCache",
    "Genus",
    "Identifier",
    "Barcode",
    "StableURI",
]

# --------------------------------------------------
# Extract year from date string
# --------------------------------------------------

def extract_year(value: Any) -> int | None:
    if value is None:
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
    ]

    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).year

        except ValueError:
            continue

    if len(text) >= 4 and text[:4].isdigit():
        try:
            return int(text[:4])

        except ValueError:
            return None

    return None


# --------------------------------------------------
# Normalize records into internal schema
# --------------------------------------------------

def normalize_records(records: list[dict]) -> list[dict]:
    return [
        normalize_bgbm_record(record)
        for record in records
    ]


# --------------------------------------------------
# Add derived eventYear field
# --------------------------------------------------

def add_event_year(records: list[dict]) -> list[dict]:
    for record in records:
        record["eventYear"] = extract_year(
            record.get("collectionDateBegin")
            or record.get("eventDate")
        )

    return records


# --------------------------------------------------
# Replace NaN with None
# --------------------------------------------------

def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    return df.where(pd.notnull(df), None)


# --------------------------------------------------
# Assign BGBM headers if CSV has no header row
# --------------------------------------------------

def apply_bgbm_columns_if_needed(
    df: pd.DataFrame,
) -> pd.DataFrame:

    if all(isinstance(col, int) for col in df.columns):

        if len(df.columns) != len(BGBM_COLUMNS):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"CSV has {len(df.columns)} columns, "
                    f"expected {len(BGBM_COLUMNS)} BGBM columns."
                ),
            )

        df.columns = BGBM_COLUMNS

    return df