import logging
import os
import time
import json
 
import httpx
import pandas as pd
from pygbif import species
 
# Config
LAND_API_BASE = os.environ.get('LAND_TAXONOMY_API_URL', 'http://land-taxonomy-api:8000')
GBIF_CONFIDENCE_RESOLVED = 90
GBIF_CONFIDENCE_MIN = 70
WFO_CONFIDENCE_RESOLVED = 70
API_RETRIES = 10
REQUEST_DELAY = 0.3
 
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)


# Land Taxonomy API
def wait_for_api(client: httpx.Client, retries: int = API_RETRIES) -> None:
    """Block until the land-taxonomy API health endpoint responds 200."""
    for i in range(retries):
        try:
            client.get(f'{LAND_API_BASE}/').raise_for_status()
            log.info('Land taxonomy API is ready.')
            return
        except httpx.ConnectError:
            log.warning('API not ready, retrying (%d/%d)…', i + 1, retries)
            time.sleep(2)
        except httpx.HTTPStatusError as exc:
            # Service is up but returning an error — retrying won't help.
            raise RuntimeError(f'Land taxonomy API returned an error: {exc}') from exc
    raise RuntimeError('Land taxonomy API did not get ready in time.')
 
 
def classify_row(text: str, client: httpx.Client, use_ollama: bool) -> dict:
    """POST text to the land taxonomy classifier and return parsed JSON."""
    response = client.post(
        f'{LAND_API_BASE}/classify',
        json={'text': text, 'top_k': 1, 'use_ollama': use_ollama},
    )
    response.raise_for_status()
    return response.json()

# Taxonomy Resolution
_UNRESOLVED = {'identifier': '', 'confidence': None, 'status': 'unresolved', 'source': ''}

def match_gbif(name: str, genus: str, family: str) -> dict:
    """Try GBIF first; fall back to WFO if confidence is too low."""
    log.debug('GBIF lookup: %s', name)
    response = species.name_backbone(
        scientificName=name,
        genus=genus,
        family=family,
        strict=False,
    )
 
    usage = response.get('usage')
    diagnostics = response.get('diagnostics')
    if not usage or not diagnostics:
        log.debug('GBIF returned no usage or diagnostics for %s, trying WFO', name)
        return match_wfo(name)
 
    gbif_id = usage['key']
    gbif_conf = diagnostics['confidence']
 
    if gbif_conf < GBIF_CONFIDENCE_MIN:
        log.debug('GBIF confidence %d too low for %s, trying WFO', gbif_conf, name)
        return match_wfo(name)
 
    return {
        'identifier': gbif_id,
        'confidence': gbif_conf,
        'status': 'resolved' if gbif_conf >= GBIF_CONFIDENCE_RESOLVED else 'fuzzy',
        'source': 'gbif',
    }

def match_wfo(name: str) -> dict:
    """Query World Flora Online reconciliation endpoint."""
    log.debug('WFO lookup: %s', name)
    try:
        response = httpx.get(
            'https://list.worldfloraonline.org/reconcile',
            params={'queries': json.dumps({'q1': {'query': name, 'limit': 1}})},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning('WFO request failed for %s: %s', name, exc)
        return _UNRESOLVED
 
    top = response.json().get('q1', {}).get('result', [])
    if not top:
        log.debug('WFO found no result for %s', name)
        return _UNRESOLVED
 
    score = top[0]['score']
    return {
        'identifier': top[0]['id'],
        'confidence': score,
        'status': 'resolved' if score >= WFO_CONFIDENCE_RESOLVED else 'fuzzy',
        'source': 'wfo',
    }
 

# Fallbacks for Land Taxonomy API
_NO_LAND = {
    'matches': [{'reason': '', 'level3': {'clc_code': -1, 'english_name': '', 'confidence': 0}}],
    'summary': '',
}
 
 
def _get_text(row: pd.Series) -> tuple[str | None, str]:
    """Return (text, source_field_name), or (None, '') if both fields are empty."""
    for field in ('FundortUNdOeko', 'Locality'):
        val = row.get(field)
        if pd.notna(val) and str(val).strip():
            return str(val).strip(), field
    return None, ''


# Main
def process_row(row: pd.Series, client: httpx.Client, use_ollama: bool) -> dict:
    """Classify one row; raises on unrecoverable errors."""
    text, source_field = _get_text(row)
 
    if text:
        land_taxonomy = classify_row(text, client, use_ollama)
        matches = land_taxonomy.get('matches', [])
        if not matches:
            raise ValueError('Land taxonomy returned empty matches list')
        top_match = matches[0].get('level3')
        if top_match is None:
            raise ValueError("'level3' key missing from land taxonomy response")
    else:
        log.warning('Row %s has no usable text field; using empty land result', row.get('HerbariumID'))
        land_taxonomy = _NO_LAND
        top_match = _NO_LAND['matches'][0]['level3']
        source_field = ''
 
    time.sleep(REQUEST_DELAY)
    taxon = match_gbif(row['FullNameCache'], row['Genus'], row['Family'])
 
    return {
        'HerbariumID': row['HerbariumID'],
        'clc_code': top_match['clc_code'],
        'clc_name': top_match['english_name'],
        'clc_confidence': top_match['confidence'],
        'clc_reason': land_taxonomy['matches'][0]['reason'],
        'clc_summary': land_taxonomy['summary'],
        'clc_source_field': source_field,
        'taxon_identifier': taxon['identifier'],
        'taxon_confidence': taxon['confidence'],
        'taxon_source': taxon['source'],
        'taxon_status': taxon['status'],
        'error': '',
    }


def main() -> None:
    input_path = os.environ.get('INPUT_CSV', '../data/input.csv')
    output_path = os.environ.get('OUTPUT_CSV', '../data/output.csv')
 
    df = pd.read_csv(input_path)
    results = []
 
    with httpx.Client(timeout=60.0) as client:
        wait_for_api(client)
 
        for i, (_, row) in enumerate(df.iterrows()):
            herbarium_id = row.get('HerbariumID', f'row_{i}')
            try:
                result = process_row(row, client)
                log.info('OK  %s', herbarium_id)
            except Exception as exc:
                log.error('FAIL %s: %s', herbarium_id, exc)
                result = {
                    'HerbariumID': herbarium_id,
                    'clc_code': '', 'clc_name': '', 'clc_confidence': '',
                    'clc_reason': '', 'clc_summary': '', 'clc_source_field': '',
                    'identifier': '', 'taxon_confidence': '', 'taxon_source': '',
                    'taxon_status': '', 'error': str(exc),
                }
 
            results.append(result)
 
            if (i + 1) % 500 == 0:
                pd.DataFrame(results).to_csv(output_path, index=False)
                log.info('Checkpoint written at row %d', i + 1)
 
    pd.DataFrame(results).to_csv(output_path, index=False)
    log.info('Done. %d rows written to %s', len(results), output_path)

