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
        herbarium_id = batch[i].get('HerbariumID', '?')

        if isinstance(result, Exception):
            log.error('FAIL %s: %s', herbarium_id, result)

            result = ClassifierResult(
                id=herbarium_id,
                error=str(result)
            )
        else:
            log.debug('OK %s', herbarium_id)

        results.append(result.to_row())
    
    return results

def flush(rows, write_header, path) -> None:
    pd.DataFrame(rows).to_csv(path, mode='a', header=write_header, index=False, sep=';')
    return

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
            log.info('Ollama model is loaded and ready')
            return
        except (httpx.TimeoutException, httpx.HTTPError):
            log.warning('Ollama warm-up attempt %d/%d failed, retrying', i+1, retries)
    raise RuntimeError('Ollama did not warm up in time')

async def process_csv(input, use_ollama) -> None:
    output_path = os.environ.get('OUTPUT_CSV', '../data/output.csv')
    results = []
    total = len(input)
    header_written = False

    if os.path.exists(output_path):
        os.remove(output_path)

    log.info('Starting classification of %d rows (batch size %d, use_ollama=%s)', total, BATCH_SIZE, use_ollama)
 
    async with httpx.AsyncClient(timeout=300.0) as client:
        await wait_for_api(client)
        
        if use_ollama:
            log.info('Ollama selected; warming up model...')
            await wait_for_ollama(client)
        
        batch = []

        for i, (_, row) in enumerate(input.iterrows()):
            batch.append(row)

            if len(batch) == BATCH_SIZE:
                results.extend(await check_batch(batch, client, use_ollama))
                batch = []
            
            if (i + 1) % 60 == 0:
                flush(results, not header_written, output_path)
                header_written = True
                log.info('Checkpoint: %d/%d rows processed', i + 1, total)
                results = []
        
        results.extend(await check_batch(batch, client, use_ollama))
        if results:
            flush(results, not header_written, output_path)

 
    log.info('Done. %d rows written to %s', total, output_path)
    return