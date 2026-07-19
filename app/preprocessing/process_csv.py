import io
import pandas as pd

from app.schemas import DetectResponse, RecordQualityResult
from app.utils import prepare_dataframe, apply_bgbm_columns_if_needed
from app.pipeline import process_records_strategically, annotate_records


def process_csv_in_chunks(
    file_bytes: bytes,
    enable_llm: bool = False,
    use_ollama: bool = False,
    chunksize: int = 1000,
    max_records: int | None = None,
    max_llm_records: int = 25,
    llm_only_flagged: bool = True,
    enable_quality: bool = False,
    enable_semantic: bool = True,
    enable_outliers: bool = True,
    enable_rule_detector: bool | None = None,
    enable_semantic_rule_detector: bool | None = None,
    enable_iqr_detector: bool | None = None,
    enable_zscore_detector: bool | None = None,
    enable_modified_zscore_detector: bool | None = None,
    enable_date_outlier_detector: bool | None = None,
    enable_isolation_forest_detector: bool | None = None,
    enable_hdbscan_geo_detector: bool | None = None,
) -> DetectResponse:
    """Processes an uploaded CSV payload incrementally using configured pipelines."""

    all_results: list[RecordQualityResult] = []
    all_annotated_records: list[dict] = []
    total_seen = 0

    chunk_reader = pd.read_csv(
        io.BytesIO(file_bytes),
        chunksize=chunksize,
        sep=",",          
        engine="python",           
        encoding="utf-8-sig",   # remove UTF-8 Byte Order Mark (BOM)       
        on_bad_lines="skip",
        skip_blank_lines=True  
    )

    for chunk in chunk_reader:
        if max_records is not None and total_seen >= max_records:
            break
        
        # clean the column names, in case the BOM was not removed 
        chunk.columns = (
            chunk.columns.str.replace('ï»¿', '', regex=False) 
                         .str.replace('"', '', regex=False)    
                         .str.strip()                         
        )

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
            enable_outliers=enable_outliers,
            enable_semantic=enable_semantic,
            enable_llm=enable_llm,
            use_ollama=use_ollama,
            max_llm_records=max_llm_records,
            llm_only_flagged=llm_only_flagged,
            enable_rule_detector=enable_rule_detector,
            enable_semantic_rule_detector=enable_semantic_rule_detector,
            enable_iqr_detector=enable_iqr_detector,
            enable_zscore_detector=enable_zscore_detector,
            enable_modified_zscore_detector=enable_modified_zscore_detector,
            enable_date_outlier_detector=enable_date_outlier_detector,
            enable_isolation_forest_detector=enable_isolation_forest_detector,
            enable_hdbscan_geo_detector=enable_hdbscan_geo_detector,
        )

        all_results.extend(chunk_results)

        all_annotated_records.extend(annotate_records(records, chunk_results))

        total_seen += len(records)

    return DetectResponse(
        count=len(all_results),
        results=all_results,
        annotated_records=all_annotated_records,
    )
