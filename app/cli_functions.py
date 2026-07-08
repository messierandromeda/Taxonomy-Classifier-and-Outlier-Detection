import json
import logging
from pathlib import Path
import pandas as pd
from app.schemas import DetectRequest
from app.pipeline import run_detectors
from app.train import run_training
from app.config import (
    HERBARIUM_ID,
    FULL_NAME_CACHE,
    COUNTRY,
    LOCALITY,
    LATITUDE,
    LONGITUDE,
    COLLECTION_DATE_BEGIN,
    start_ollama_if_needed,
    is_ollama_running,
    OLLAMA_MODEL,
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
        enable_outliers=args.enable_outliers if hasattr(args, 'enable_outliers') else True,
        enable_semantic=args.enable_semantic,
        enable_llm=args.enable_llm,
        use_ollama=args.use_ollama,
        numeric_fields=request.numeric_fields,
        text_fields=request.text_fields,
        enable_rule_detector=args.enable_rule_detector if hasattr(args, 'enable_rule_detector') else None,
        enable_semantic_rule_detector=args.enable_semantic_rule_detector if hasattr(args, 'enable_semantic_rule_detector') else None,
        enable_iqr_detector=args.enable_iqr_detector if hasattr(args, 'enable_iqr_detector') else None,
        enable_zscore_detector=args.enable_zscore_detector if hasattr(args, 'enable_zscore_detector') else None,
        enable_modified_zscore_detector=args.enable_modified_zscore_detector if hasattr(args, 'enable_modified_zscore_detector') else None,
        enable_date_outlier_detector=args.enable_date_outlier_detector if hasattr(args, 'enable_date_outlier_detector') else None,
        enable_isolation_forest_detector=args.enable_isolation_forest_detector if hasattr(args, 'enable_isolation_forest_detector') else None,
        enable_hdbscan_geo_detector=args.enable_hdbscan_geo_detector if hasattr(args, 'enable_hdbscan_geo_detector') else None,
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
        use_ollama=args.use_ollama,
        chunksize=args.chunksize,
        max_records=args.max_records,
        max_llm_records=args.max_llm_records,
        llm_only_flagged=args.llm_only_flagged,
        enable_quality=args.enable_quality,
        enable_semantic=args.enable_semantic,
        enable_outliers=args.enable_outliers if hasattr(args, 'enable_outliers') else True,
        enable_rule_detector=args.enable_rule_detector if hasattr(args, 'enable_rule_detector') else None,
        enable_semantic_rule_detector=args.enable_semantic_rule_detector if hasattr(args, 'enable_semantic_rule_detector') else None,
        enable_iqr_detector=args.enable_iqr_detector if hasattr(args, 'enable_iqr_detector') else None,
        enable_zscore_detector=args.enable_zscore_detector if hasattr(args, 'enable_zscore_detector') else None,
        enable_modified_zscore_detector=args.enable_modified_zscore_detector if hasattr(args, 'enable_modified_zscore_detector') else None,
        enable_date_outlier_detector=args.enable_date_outlier_detector if hasattr(args, 'enable_date_outlier_detector') else None,
        enable_isolation_forest_detector=args.enable_isolation_forest_detector if hasattr(args, 'enable_isolation_forest_detector') else None,
        enable_hdbscan_geo_detector=args.enable_hdbscan_geo_detector if hasattr(args, 'enable_hdbscan_geo_detector') else None,
    )

    df = pd.DataFrame(response.annotated_records)

    important_columns = [
        HERBARIUM_ID,
        FULL_NAME_CACHE,
        COUNTRY,
        LOCALITY,
        LATITUDE,
        LONGITUDE,
        COLLECTION_DATE_BEGIN,
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
