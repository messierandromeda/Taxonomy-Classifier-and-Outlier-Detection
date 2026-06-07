from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, status
import logging
from app.schemas import (
    DetectRequest,
    DetectResponse,
)

from app.pipeline import run_detectors
from app.ollama_config import OLLAMA_MODEL, is_ollama_running, start_ollama_if_needed
from app.preprocessing.process_csv import process_csv_in_chunks
from app.config import UNINITIALIZED_MSG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(filename)s:%(lineno)d - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_ollama_if_needed()
    yield

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

@app.post("/detect", response_model=DetectResponse)
def detect(request: DetectRequest):
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

@app.post(
    "/detect-csv", 
    response_model=DetectResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Returned when the outlier detection models are not trained yet.",
            "content": {
                "application/json": {
                    "example": {"detail": UNINITIALIZED_MSG}
                }
            }
        }
    })
async def detect_csv(
    file: UploadFile = File(...),
    enable_llm: bool = False,
    llm_provider: str = "none",
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    raw = await file.read()
    
    return process_csv_in_chunks(
        file_bytes=raw,
        enable_llm=enable_llm,
        llm_provider=llm_provider,
        chunksize=chunksize,
        max_records=max_records,
        max_llm_records=max_llm_records,
        llm_only_flagged=llm_only_flagged,
    )