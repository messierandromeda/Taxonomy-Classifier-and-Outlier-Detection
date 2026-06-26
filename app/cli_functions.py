import json
import logging
from pathlib import Path
import pandas as pd
from app.schemas import DetectRequest
from app.pipeline import run_detectors
from app.train import run_training
from app.ollama_config import (
    OLLAMA_MODEL,
    is_ollama_running,
    start_ollama_if_needed,
)
from app.preprocessing.process_csv import process_csv_in_chunks
from app.utils import apply_bgbm_columns_if_needed, prepare_dataframe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def handle_health():
    """Checks the local environment status."""
    start_ollama_if_needed()
    print("\n--- Service Status ---")
    print(f"Ollama Running: {is_ollama_running()}")
    print(f"Ollama Model:   {OLLAMA_MODEL}\n")


def detect_json(args):
    """Processes a local JSON file offline."""
    input_path = Path(args.file)
    if not input_path.suffix.lower() == ".json":
        logger.error("Only JSON files are supported.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            logger.error("Invalid JSON file contents.")
            return

    request = DetectRequest(**data)

    start_ollama_if_needed()

    response = run_detectors(
        records=request.records,
        enable_quality=args.enable_quality,
        enable_outliers=request.enable_outliers,
        enable_semantic=args.enable_semantic,
        enable_llm=args.enable_llm,
        llm_provider=args.llm_provider,
        numeric_fields=request.numeric_fields,
        text_fields=request.text_fields,
    )

    json_output = response.model_dump_json(indent=4)
    if args.output:
        out_path = Path(args.output)
    else:
        out_path = input_path.parent / f"{input_path.stem}_output.json"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(json_output)
    logger.info(f"Results successfully saved to: {out_path}")


def detect_csv(args):
    """Processes a local CSV file offline in chunks."""
    input_path = Path(args.file)
    if not input_path.suffix.lower() == ".csv":
        logger.error("Only CSV files are supported.")
        return

    with open(input_path, "rb") as f:
        raw_bytes = f.read()

    start_ollama_if_needed()

    response = process_csv_in_chunks(
        file_bytes=raw_bytes,
        enable_llm=args.enable_llm,
        llm_provider=args.llm_provider,
        chunksize=args.chunksize,
        max_records=args.max_records,
        max_llm_records=args.max_llm_records,
        llm_only_flagged=args.llm_only_flagged,
        enable_quality=args.enable_quality,
        enable_semantic=args.enable_semantic,
    )

    df = pd.DataFrame(response.annotated_records)

    important_columns = [
        "HerbariumID",
        "FullNameCache",
        "Country",
        "Locality",
        "Latitude",
        "Longitude",
        "CollectionDateBegin",
        "outlier_detected",
        "outlier_status",
        "outlier_confidence",
        "outlier_severity",
        "outlier_score",
        "outlier_primary_detector",
        "outlier_primary_field",
        "outlier_reason",
        "outlier_summary",
    ]
    existing_columns = [col for col in important_columns if col in df.columns]
    df = df[existing_columns]

    if args.output:
        out_path = Path(args.output)
    else:
        out_path = input_path.parent / f"{input_path.stem}_annotated_output.csv"

    df.to_csv(out_path, index=False)
    logger.info(f"Results successfully saved to: {out_path}")


def train_csv(args):
    """Trains the models using a local CSV file offline."""
    input_path = Path(args.file)
    if not input_path.suffix.lower() == ".csv":
        logger.error("Only CSV files are supported.")
        return

    try:
        df = pd.read_csv(input_path, sep=None, engine="python")
    except Exception as e:
        logger.error(f"Unable to parse CSV training data: {e}")
        return

    df = apply_bgbm_columns_if_needed(df)
    df = prepare_dataframe(df)
    records = df.to_dict(orient="records")

    if not records:
        logger.error("CSV file contains no records.")
        return

    try:
        run_training(
            records=records,
            training_subset_size=args.training_subset_size,
            training_seed=args.training_seed,
        )
        logger.info("Training completed successfully.")
        print(f"Trained records: {len(records)}")
    except Exception as e:
        logger.error(f"Training failed: {e}")
