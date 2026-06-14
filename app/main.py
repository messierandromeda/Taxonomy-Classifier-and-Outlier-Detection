from contextlib import asynccontextmanager
import json
import io

import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import StreamingResponse

from app.schemas import (
    DetectRequest,
    DetectResponse,
)

from app.pipeline import run_detectors
from app.ollama_config import (
    OLLAMA_MODEL,
    is_ollama_running,
    start_ollama_if_needed,
)
from app.preprocessing.process_csv import process_csv_in_chunks


# --------------------------------------------------
# FastAPI lifespan hook
# --------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_ollama_if_needed()
    yield


# --------------------------------------------------
# FastAPI application
# --------------------------------------------------

app = FastAPI(
    title="Biodiv Outlier and Data-Quality Detection Service",
    version="0.2.0",
    description=(
        "REST service for biodiversity data-quality "
        "checks and outlier detection."
    ),
    lifespan=lifespan,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "ollama_running": is_ollama_running(),
        "ollama_model": OLLAMA_MODEL,
    }


@app.post("/detect-json", response_model=DetectResponse)
async def detect(
    request: DetectRequest | None = Body(default=None),
    file: UploadFile | None = File(default=None),
):
    if file is not None:
        if not file.filename or not file.filename.endswith(".json"):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported.",
            )

        raw = await file.read()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON file.",
            )

        request = DetectRequest(**data)

    if request is None:
        raise HTTPException(
            status_code=400,
            detail="Provide JSON body or JSON file upload.",
        )

    return run_detectors(
        records=request.records,
        enable_quality=request.enable_quality,
        enable_outliers=request.enable_outliers,
        enable_semantic=request.enable_semantic,
        enable_llm=request.enable_llm,
        llm_provider=request.llm_provider,
        numeric_fields=request.numeric_fields,
        text_fields=request.text_fields,
        training_subset_size=request.training_subset_size,
        training_seed=request.training_seed,
    )


@app.post("/detect-csv")
async def detect_csv(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str = "none",
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
    training_subset_size: int = 500,
    download_csv: bool = False,
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
        training_subset_size=training_subset_size,
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

    existing_columns = [
        column
        for column in important_columns
        if column in df.columns
    ]

    df = df[existing_columns]

    stream = io.StringIO()
    df.to_csv(stream, index=False)
    stream.seek(0)

    return StreamingResponse(
        iter([stream.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=annotated_output.csv"
        },
    )