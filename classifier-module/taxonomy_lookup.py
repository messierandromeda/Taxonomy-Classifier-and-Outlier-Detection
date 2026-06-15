import httpx

from config import GBIF_CONFIDENCE_RESOLVED
from models import TaxonMatch

async def match_gbif(name: str, genus: str, family: str, client: httpx.AsyncClient) -> TaxonMatch:
    response = await client.get(
        'https://api.gbif.org/v2/species/match',
        params={'name': name, 'genus': genus, 'family': family, 'strict': 'false'},
        timeout=30.0,
    )
    response.raise_for_status()
    data = response.json()

    diagnostics = data.get('diagnostics', {})
    usage = data.get('usage', {})

    if diagnostics.get('matchType') == 'NONE' or not usage.get('key'):
        return TaxonMatch()

    confidence = diagnostics.get('confidence')
    return TaxonMatch(
        identifier=str(usage['key']),
        confidence=confidence if confidence is not None else -1,
        status='resolved' if confidence >= GBIF_CONFIDENCE_RESOLVED else 'fuzzy',
    )