import os
import pandas as pd
import httpx
import logging

from classifier import wait_for_api, process_row


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)

def process_csv(input, use_ollama) -> None:
    output_path = os.environ.get('OUTPUT_CSV', '../data/output.csv')
    results = []
 
    with httpx.Client(timeout=60.0) as client:
        wait_for_api(client)
 
        for i, (_, row) in enumerate(input.iterrows()):
            herbarium_id = row.get('HerbariumID', f'row_{i}')
            try:
                result = process_row(row, client, use_ollama)
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
    return results