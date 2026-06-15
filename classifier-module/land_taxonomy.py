import httpx
import asyncio

from config import API_RETRIES, LAND_API_BASE, log
from models import CLCMatch, LandTaxonomyResponse

async def wait_for_api(client: httpx.AsyncClient, retries: int = API_RETRIES) -> None:
    """Block until the land-taxonomy API health endpoint responds 200."""
    for i in range(retries):
        try:
            response = await client.get(f'{LAND_API_BASE}/')
            response.raise_for_status()
            log.info('Land taxonomy API is ready.')
            return
        except httpx.ConnectError:
            log.warning('API not ready, retrying (%d/%d)…', i + 1, retries)
            await asyncio.sleep(2)
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f'Land taxonomy API returned an error: {exc}') from exc
    raise RuntimeError('Land taxonomy API did not get ready in time.') 
 
async def match_land(text: str, client: httpx.AsyncClient, use_ollama: bool) -> CLCMatch:
    """POST text to the land taxonomy classifier and return parsed JSON."""
    response = await client.post(
        f'{LAND_API_BASE}/classify',
        json={'text': text, 'top_k': 1, 'use_ollama': use_ollama},
    )
    response.raise_for_status()
    data = LandTaxonomyResponse(**response.json())
    top = data.matches[0]

    return CLCMatch(
        code=top.level3.clc_code,
        name=top.level3.english_name,
        confidence=top.level3.confidence,
        reason=top.reason,
        input=data.input_text,
        source='OpenAI' if not use_ollama else 'ollama'
    )
