from typing import Any
import pandas as pd
from datetime import datetime
from app.preprocessing.bgbm_normalizer import (
    normalize_bgbm_record,
)
from fastapi import HTTPException
from app.config import (
    HERBARIUM_ID,
    BILD,
    DB,
    FAMILY,
    FULL_NAME_CACHE,
    ANMERKUNGEN,
    SAMMLERTEAM,
    SAMMELNUMMER,
    COLLECTION_DATE_BEGIN,
    COLLECTION_DATE_END,
    COUNTRY,
    LOCALITY,
    TITEL_ETIKETT,
    EXPEDITIONSANGABE,
    SHOW_ON_MAP,
    LATITUDE,
    LONGITUDE,
    FUNDORT_UND_OEKO,
    NAME_CACHE,
    GENUS,
    IDENTIFIER,
    BARCODE,
    STABLE_URI,
)

BGBM_COLUMNS = [
    HERBARIUM_ID,
    BILD,
    DB,
    FAMILY,
    FULL_NAME_CACHE,
    ANMERKUNGEN,
    SAMMLERTEAM,
    SAMMELNUMMER,
    COLLECTION_DATE_BEGIN,
    COLLECTION_DATE_END,
    COUNTRY,
    LOCALITY,
    TITEL_ETIKETT,
    EXPEDITIONSANGABE,
    SHOW_ON_MAP,
    LATITUDE,
    LONGITUDE,
    FUNDORT_UND_OEKO,
    NAME_CACHE,
    GENUS,
    IDENTIFIER,
    BARCODE,
    STABLE_URI,
]


def extract_year(value: Any) -> int | None:
    """Extract a four-digit year from a variety of date string formats.

    Supports ISO date strings, European date formats, and simple year-only values.
    """
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


def normalize_records(records: list[dict]) -> list[dict]:
    """Normalize all records into the internal BGBM-derived schema."""
    return [normalize_bgbm_record(record) for record in records]


def add_event_year(records: list[dict]) -> list[dict]:
    """Add a derived `eventYear` field based on collection or event date strings."""
    for record in records:
        record["eventYear"] = extract_year(
            record.get("collectionDateBegin") or record.get("eventDate")
        )

    return records


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Replace pandas missing values with Python None for downstream processing."""
    return df.where(pd.notnull(df), None)


def apply_bgbm_columns_if_needed(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Assign BGBM header names to a CSV chunk if it lacks explicit column labels."""

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
