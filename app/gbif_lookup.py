import httpx

from .config import GBIF_CONFIDENCE_RESOLVED, log
from .util.models import TaxonMatch

# temp cache: persists across run (not permanent)
_gbif_cache: dict[tuple, TaxonMatch] = {}


def _key(name: str, genus: str, family: str) -> tuple:
    # coerce first: genus/family are only ~98% filled, and None.strip() raises
    return tuple((v or '').strip().lower() for v in (name, genus, family))


def _family_from(classification: list[dict]) -> str:
    """GBIF's authoritative family — trust this over the CSV's Family column."""
    return next(
        (c.get('name', '') for c in classification if c.get('rank') == 'FAMILY'),
        '',
    )


async def _api_call(name: str, genus: str, family: str, client: httpx.AsyncClient) -> TaxonMatch:
    log.debug('GBIF lookup: %s', name)
    try:
        response = await client.get(
            'https://api.gbif.org/v2/species/match',
            params={'scientificName': name, 'genus': genus, 'family': family, 'kingdom': 'Plantae', 'strict': 'false'},
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

    key = str(usage['key'])
    match_type = diagnostics.get('matchType', '')

    resolved = confidence >= GBIF_CONFIDENCE_RESOLVED and match_type in ('EXACT', 'FUZZY')

    return TaxonMatch(
        key=key,
        link=f'http://www.gbif.org/species/{key}',
        confidence=confidence,
        status='resolved' if resolved else 'fuzzy',
        # for the prompt
        canonical_name=usage.get('canonicalName', ''),
        rank=usage.get('rank', ''),                      # GENUS vs SPECIES
        family=_family_from(data.get('classification', [])),
        # for validation
        match_type=match_type,                           # EXACT | FUZZY | HIGHERRANK
        is_synonym=bool(data.get('synonym', False)),     # True => CSV name is outdated
        accepted_status=usage.get('status', ''),         # ACCEPTED | SYNONYM | ...
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


def taxon_prompt_fields(match: TaxonMatch, csv_name: str = '') -> dict[str, str]:
    if match.status != 'resolved' or not match.canonical_name:
        return {'Species': csv_name} if csv_name else {}

    label = 'Genus' if match.rank == 'GENUS' else 'Species'
    fields = {label: match.canonical_name}
    if match.family:
        fields['Family'] = match.family
    return fields