import argparse
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
        "HerbariumID", "FullNameCache", "Country", "Locality", "Latitude", "Longitude",
        "CollectionDateBegin", "outlier_detected", "outlier_status", "outlier_confidence",
        "outlier_severity", "outlier_score", "outlier_primary_detector",
        "outlier_primary_field", "outlier_reason", "outlier_summary"
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
    except Exception as exc:
        logger.error(f"Unable to parse CSV training data: {exc}")
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
    except Exception as exc:
        logger.error(f"Training failed: {exc}")


def main():
    parser = argparse.ArgumentParser(
        description="Biodiv Outlier and Data-Quality Detection CLI Toolkit"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # 1. Health Command
    subparsers.add_parser("status", help="Check local environment & Ollama status")

    # 2. Detect JSON Command
    json_parser = subparsers.add_parser("detect-json", help="Run detection on a JSON file")
    json_parser.add_argument("--file", required=True, help="Path to the input JSON file")
    json_parser.add_argument("--output", help="Custom path for output JSON file")
    json_parser.add_argument("--enable-llm", action="store_true", help="Enable LLM reasoning")
    json_parser.add_argument("--llm-provider", default="none", help="LLM provider choice")
    json_parser.add_argument("--semantic", dest="enable_semantic", action="store_true", help="Semantic checks")
    json_parser.add_argument("--rule-based", dest="enable_quality", action="store_true", help="Quality rule-based engine")
    json_parser.set_defaults(handle_func=detect_json)

    # 3. Detect CSV Command
    csv_parser = subparsers.add_parser("detect-csv", help="Run detection on a CSV file")
    csv_parser.add_argument("--file", required=True, help="Path to input CSV file")
    csv_parser.add_argument("--output", help="Custom path for output CSV file")
    csv_parser.add_argument("--enable-llm", action="store_true", help="Enable LLM reasoning")
    csv_parser.add_argument("--llm-provider", default="none", help="LLM provider choice")
    csv_parser.add_argument("--chunksize", type=int, default=1000, help="Chunk tracking window size")
    csv_parser.add_argument("--max-records", type=int, help="Limit total rows to process")
    csv_parser.add_argument("--max-llm-records", type=int, default=25, help="Max items context limit for LLM checks")
    csv_parser.add_argument("--disable-llm-only-flagged", dest="llm_only_flagged", action="store_false", help="Evaluate all rows instead of only flagged items via LLM")
    csv_parser.add_argument("--semantic", dest="enable_semantic", action="store_true", help="Disable semantic checks")
    csv_parser.add_argument("--rule-based", dest="enable_quality", action="store_true", default=False, help="Enable quality checks")
    csv_parser.set_defaults(handle_func=detect_csv)

    # 4. Train CSV Command
    train_parser = subparsers.add_parser("train", help="Train models locally with a CSV file")
    train_parser.add_argument("--file", required=True, help="Path to training dataset CSV")
    train_parser.add_argument("--training-subset-size", type=int, default=500, help="Subset constraints size")
    train_parser.add_argument("--training-seed", type=int, default=42, help="Random engine seed value")
    train_parser.set_defaults(handle_func=train_csv)

    args = parser.parse_args()

    if args.command == "status":
        handle_health()
    else:
        args.handle_func(args)


if __name__ == "__main__":
    main()
