import io
import pandas as pd

from app.schemas import DetectResponse, RecordQualityResult
from app.utils import prepare_dataframe, apply_bgbm_columns_if_needed
from app.pipeline import process_records_strategically, annotate_records


def process_csv_in_chunks(
    file_bytes: bytes,
    enable_llm: bool = False,
    llm_provider: str = "none",
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
    enable_quality: bool = False,
    enable_semantic: bool = True,
) -> DetectResponse:
    """Processes an uploaded CSV payload incrementally using configured pipelines."""

    all_results: list[RecordQualityResult] = []
    all_annotated_records: list[dict] = []
    total_seen = 0

    chunk_reader = pd.read_csv(
        io.BytesIO(file_bytes),
        chunksize=chunksize,
        sep=None,
        engine="python",
    )

    for chunk in chunk_reader:
        if max_records is not None and total_seen >= max_records:
            break

        chunk = apply_bgbm_columns_if_needed(chunk)
        chunk = prepare_dataframe(chunk)
        records = chunk.to_dict(orient="records")

        if max_records is not None:
            remaining = max_records - total_seen
            records = records[:remaining]

        if not records:
            continue

        chunk_results = process_records_strategically(
            records=records,
            enable_quality=enable_quality,
            enable_outliers=True,
            enable_semantic=enable_semantic,
            enable_llm=enable_llm,
            llm_provider=llm_provider,
            max_llm_records=max_llm_records,
            llm_only_flagged=llm_only_flagged,
        )

        all_results.extend(chunk_results)

        all_annotated_records.extend(annotate_records(records, chunk_results))

        total_seen += len(records)

    return DetectResponse(
        count=len(all_results),
        results=all_results,
        annotated_records=all_annotated_records,
    )
