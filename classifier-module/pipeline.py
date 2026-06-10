import os
import pandas as pd
import httpx
import asyncio

from process import process_row
from config import log, BATCH_SIZE
from land_taxonomy import wait_for_api
from models import ClassifierResult

async def check_batch(batch, client, use_ollama) -> list:
    results = []
    batch_results = await asyncio.gather(
        *[process_row(row, client, use_ollama) for row in batch], 
        return_exceptions = True
    )

    for i, result in enumerate(batch_results):
        if isinstance(result, Exception):
            result = ClassifierResult(
                    id=batch[i].get('HerbariumID', '?'),
                    error=str(result)
                )
            log.error('FAIL %s: %s', batch[i].get('HerbariumID', '?'), result)
        results.append(result.to_row())
    
    return results

async def wait_for_ollama(client: httpx.AsyncClient, retries: int = 5) -> None:
    for i in range(retries):
        try:
            r = await client.post(
                'http://ollama:11434/v1/chat/completions',
                json={'model': 'llama3.2',
                      'messages': [{'role': 'user', 'content': 'ok'}],
                      'max_tokens': 1},
                timeout=600.0
            )
            r.raise_for_status()
            return
        except (httpx.TimeoutException, httpx.HTTPError):
            log.warning('Ollama warm-up attempt %d/%d failed, retrying', i+1, retries)
    raise RuntimeError('Ollama did not warm up in time')

async def process_csv(input, use_ollama) -> None:
    output_path = os.environ.get('OUTPUT_CSV', '../data/output.csv')
    results = []
 
    async with httpx.AsyncClient(timeout=300.0) as client:
        await wait_for_api(client)
        
        if use_ollama:
            await wait_for_ollama(client)
        

        batch = []

        for i, (_, row) in enumerate(input.iterrows()):
            batch.append(row)

            if len(batch) == BATCH_SIZE:
                results.extend(await check_batch(batch, client, use_ollama))
                batch = []
            
            if (i + 1) % 500 == 0:
                pd.DataFrame(results).to_csv(output_path, index=False)
                log.info('Checkpoint written at row %d', i + 1)
        
        results.extend(await check_batch(batch, client, use_ollama))
            

 
    pd.DataFrame(results).to_csv(output_path, index=False)
    log.info('Done. %d rows written to %s', len(results), output_path)
    return results