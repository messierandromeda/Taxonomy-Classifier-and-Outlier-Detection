import httpx

from config import GBIF_CONFIDENCE_RESOLVED, log
from models import TaxonMatch

# temp cache: persists across run (not permanent)
_gbif_cache: dict[tuple, TaxonMatch] = {}


def _key(name: str, genus: str, family: str) -> tuple:
    return (name.strip().lower(), genus.strip().lower(), family.strip().lower())


async def _api_call(name: str, genus: str, family: str, client: httpx.AsyncClient) -> TaxonMatch:
    log.debug('GBIF lookup: %s', name)
    try:
        response = await client.get(
            'https://api.gbif.org/v2/species/match',
            params={'name': name, 'genus': genus, 'family': family, 'strict': 'false'},
            timeout=30.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        # transient error
        log.warning('GBIF request failed for %s: %s', name, exc)
        return TaxonMatch(status='error')

    data = response.json()
    diagnostics = data.get('diagnostics', {})
    usage = data.get('usage', {})

    # no possible match found
    if diagnostics.get('matchType') == 'NONE' or not usage.get('key'):
        log.debug('GBIF found no match for %s', name)
        return TaxonMatch()

    confidence = diagnostics.get('confidence')
    if confidence is None:
        # match but no confidence
        log.debug('GBIF match for %s has no confidence; marking unresolved', name)
        return TaxonMatch()

    return TaxonMatch(
        identifier=str(usage['key']),
        confidence=confidence,
        status='resolved' if confidence >= GBIF_CONFIDENCE_RESOLVED else 'fuzzy',
    )


async def match_gbif(name: str, genus: str, family: str, client: httpx.AsyncClient) -> TaxonMatch:
    if not name or not name.strip():
        return TaxonMatch()

    key = _key(name, genus, family)
    cached = _gbif_cache.get(key)
    if cached is not None:
        log.debug('GBIF cache hit: %s', name)
        return cached

    result = await _api_call(name, genus, family, client)

    # cache real answers (resolved / fuzzy / unresolved), not transient errors
    if result.status != 'error':
        _gbif_cache[key] = result

    return result