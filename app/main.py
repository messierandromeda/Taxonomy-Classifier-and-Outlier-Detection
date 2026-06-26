from contextlib import asynccontextmanager
import json
import io
import logging
from pathlib import Path
import pandas as pd
from typing import Annotated
from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    status,
    Query
)
from fastapi.responses import StreamingResponse, Response

from app.schemas import (
    DetectRequest,
    DetectResponse,
)

from app.pipeline import run_detectors
from app.train import run_training
from app.ollama_config import (
    OLLAMA_MODEL,
    is_ollama_running,
    start_ollama_if_needed,
)
from app.preprocessing.process_csv import process_csv_in_chunks
from app.utils import apply_bgbm_columns_if_needed, prepare_dataframe
from app.config import UNINITIALIZED_MSG, RULE_BASED_MSG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        log_message = record.getMessage()
        if "/health" in log_message and "200" in log_message:
            return False
        return True


uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(HealthCheckFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_ollama_if_needed()
    yield


app = FastAPI(
    title="Biodiv Outlier and Data-Quality Detection Service",
    version="0.2.0",
    description=(
        "REST service for biodiversity data-quality checks and outlier detection."
    ),
    lifespan=lifespan,
)


@app.get("/health")
def health():
    """Health check endpoint for the API.

    Returns the service status, whether Ollama is reachable, and the configured
    Ollama model name.
    """
    return {
        "status": "ok",
        "ollama_running": is_ollama_running(),
        "ollama_model": OLLAMA_MODEL,
    }

@app.post(
    "/detect-json",
    response_model=DetectResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Returned when the outlier detection models are not trained yet.",
            "content": {"application/json": {"example": {"detail": UNINITIALIZED_MSG}}},
        }
    },
)
async def detect_json(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str = "none",
    download_csv: bool = False,
    enable_semantic: bool = True,
    enable_quality: Annotated[bool, Query(description=RULE_BASED_MSG)] = False,
):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Only JSON files are supported.")

    raw = await file.read()
    try:
        data = json.loads(raw)
        if data is None:
            raise HTTPException(
                status_code=400,
                detail="Provide JSON body or JSON file upload.",
            )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file contents.")
    request = DetectRequest(**data)

    response = run_detectors(
        records=request.records,
        enable_quality=enable_quality,
        enable_outliers=request.enable_outliers,
        enable_semantic=enable_semantic,
        enable_llm=enable_llm,
        llm_provider=llm_provider,
        numeric_fields=request.numeric_fields,
        text_fields=request.text_fields,
    )

    if not download_csv:
        return response

    json_string = response.model_dump_json(indent=4)
    filename = Path(file.filename).stem

    return Response(
        content=json_string,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}_output.json"},
    )


@app.post(
    "/detect-csv",
    response_model=DetectResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Returned when the outlier detection models are not trained yet.",
            "content": {"application/json": {"example": {"detail": UNINITIALIZED_MSG}}},
        }
    },
)
async def detect_csv(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str = "none",
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
    download_csv: bool = False,
    enable_semantic: bool = True,
    enable_quality: Annotated[bool, Query(description=RULE_BASED_MSG)] = False,
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported.",
        )

    raw = await file.read()

    response = process_csv_in_chunks(
        file_bytes=raw,
        enable_llm=enable_llm,
        llm_provider=llm_provider,
        chunksize=chunksize,
        max_records=max_records,
        max_llm_records=max_llm_records,
        llm_only_flagged=llm_only_flagged,
        enable_quality=enable_quality,  # checks for missing columns
        enable_semantic=enable_semantic,
    )

    if not download_csv:
        return response

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

    existing_columns = [column for column in important_columns if column in df.columns]

    df = df[existing_columns]

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)

    filename = Path(file.filename).stem

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}_annotated_output.csv"
        },
    )


@app.post("/train-csv")
async def train_csv(
    file: UploadFile = File(...),
    training_subset_size: int = Form(500),
    training_seed: int = Form(42),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files are supported.",
        )

    raw = await file.read()

    try:
        df = pd.read_csv(
            io.BytesIO(raw),
            sep=None,
            engine="python",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to parse CSV training data: {exc}",
        )

    df = apply_bgbm_columns_if_needed(df)
    df = prepare_dataframe(df)
    records = df.to_dict(orient="records")

    if not records:
        raise HTTPException(
            status_code=400,
            detail="CSV file contains no records.",
        )

    try:
        run_training(
            records=records,
            training_subset_size=training_subset_size,
            training_seed=training_seed,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Training failed: {exc}",
        )

    return {
        "message": "Training completed successfully.",
        "trained_records": len(records),
        "training_subset_size": training_subset_size,
        "training_seed": training_seed,
    }
