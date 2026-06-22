import pandas as pd
import httpx

from config import log
from land_classifier import classify_land
from taxonomy_lookup import match_gbif
from models import ClassifierResult, TaxonMatch


def _get_text(row: pd.Series) -> tuple[str | None, str]:
    for field in ('FundortUNdOeko', 'Locality'):
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            return str(val).strip(), field
    return None, ''


async def process_row(row: pd.Series, client: httpx.AsyncClient, use_ollama: bool) -> ClassifierResult:
    herbarium_id = row.get('HerbariumID', '?')
    text, field = _get_text(row)

    if not text:
        log.warning('Row %s has no usable text field; skipping land classification', herbarium_id)

    clc = await classify_land(text or '', use_ollama)
    clc.field = field

    try:
        taxon = await match_gbif(row['FullNameCache'], row['Genus'], row['Family'], client)
    except Exception as exc:
        log.warning('Taxonomy lookup failed for %s: %s', herbarium_id, exc)
        taxon = TaxonMatch(status='error')

    return ClassifierResult(
        id=herbarium_id,
        taxon=taxon,
        clc=clc,
    )