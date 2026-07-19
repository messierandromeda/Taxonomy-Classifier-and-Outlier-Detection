"""
Module configuration:
Variables, such as secrets, models, etc., are read from environment variables, so that they can be changed without needing to rebuild the docker image.
Dataset-specific information is saved in a JSON file, so that different datasets can be used. For this to work, DATASET_SCHEMA needs to read the correct file.
"""

import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Paths 
HERE = Path(__file__).resolve().parent

TAXONOMY_PATH = Path(os.getenv("TAXONOMY_PATH", HERE / "taxonomy.csv"))

# Models / providers
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") # Required!

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", OPENAI_MODEL)

# Tune Processing
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))
GBIF_CONFIDENCE_RESOLVED = int(os.getenv("GBIF_CONFIDENCE_RESOLVED", 80))

# Rate Limiting
OPENAI_TPM = int(os.getenv("OPENAI_TPM", 200_000))

# Pricing (per 1M tokens, as of 17-07-2026)
PRICES = {
    "gpt-5.4-mini": {"input": 0.75, "output": 4.5},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-5-nano":   {"input": 0.05, "output": 0.4},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.4},
    "gpt-5.6-terra": {"input": 2.5, "output": 15},
}

DEFAULT_CONFIG = {
    "model": DEFAULT_MODEL,
    "taxa": None,
    "use_species": True,
}

# Load Dataset Schema
DATASET_SCHEMA = Path(os.getenv("DATASET_SCHEMA", HERE / "schema.json")).resolve()


def _load_schema(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


_schema = _load_schema(DATASET_SCHEMA)
_columns = _schema["columns"]

# Used Columns
ID = _columns["id"]
NAME = _columns["name"]
GENUS = _columns["genus"]
FAMILY = _columns["family"]
LAT = _columns["lat"]
LON = _columns["lon"]
CULTIVATED_FIELD = _columns["cultivated_field"]

LOCALITY_LABELS = _schema.get("locality_labels", {})
FIELD_LABELS = _schema.get("field_labels", {})

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


def configure_logging(level: str | None = None) -> logging.Logger:
    """Set up logging, call once from main."""
    logging.basicConfig(
        level=level or LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return logging.getLogger("app")