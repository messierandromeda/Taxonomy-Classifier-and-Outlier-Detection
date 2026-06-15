import pandas as pd
import httpx
import asyncio

from config import REQUEST_DELAY
from land_taxonomy import match_land 
from taxonomy_lookup import match_gbif
from models import ClassifierResult, CLCMatch

def _get_text(row: pd.Series) -> tuple[str | None, str]:
    """Return (text, source_field_name), or (None, '') if both fields are empty."""
    for field in ('FundortUNdOeko', 'Locality'):
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            return str(val).strip(), field
    return None, ''

async def process_row(row: pd.Series, client: httpx.AsyncClient, use_ollama: bool) -> ClassifierResult:
    """Classify one row; raises on unrecoverable errors."""
    await asyncio.sleep(REQUEST_DELAY)

    text, field = _get_text(row)
   
    clc = CLCMatch() if not text else await match_land(text, client, use_ollama)
    clc.field = field
 
    taxon = await match_gbif(row['FullNameCache'], row['Genus'], row['Family'], client)
 
    return ClassifierResult(
        id=row['HerbariumID'],
        taxon=taxon,
        clc=clc
    )