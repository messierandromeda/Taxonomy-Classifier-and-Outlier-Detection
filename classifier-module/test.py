import asyncio

import httpx
import pandas as pd
from taxonomy_lookup import match_gbif
from process import process_row

async def test_match_gbif():
    async with httpx.AsyncClient() as client:
        result = await asyncio.gather(match_gbif(
            name='Geranium pyrenaicum Burm.f.',
            genus='Geranium',
            family='GERANIACEAE',
            client=client
        ))

    print(result[0])

async def test_process_row():
    input_ = pd.Series({
        'HerbariumID': 'BGT0024961',
        'Family': 'GERANIACEAE',
        'FullNameCache': 'Geranium pyrenaicum Burm.f.',
        'Locality': None,
        'FundortUNdOeko': None,
        'Genus': 'Geranium'
    })
    async with httpx.AsyncClient() as client:
        result = await asyncio.gather(process_row(input_, client, False))
    print(result[0])

if __name__ == '__main__':
    asyncio.run(test_process_row())