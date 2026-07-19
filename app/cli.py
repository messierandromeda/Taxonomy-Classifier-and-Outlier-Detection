#!/usr/bin/env python3

import argparse 
import asyncio
import logging

import pandas as pd

from .pipeline import process_csv
from .config import DEFAULT_CONFIG, configure_logging

configure_logging()
log = logging.getLogger(__name__)

async def _run(args):
    df = pd.read_csv(args.input, sep=None, engine='python')
    log.info('Received %s with %d rows', args.input, len(df))
    result = await process_csv(
        df=df,
        model=DEFAULT_CONFIG['model'],
    )
    result.to_csv(args.output, index=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    asyncio.run(_run(args))


if __name__ == '__main__':
    main()