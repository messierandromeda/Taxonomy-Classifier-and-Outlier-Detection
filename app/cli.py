#!/usr/bin/env python3

import argparse 
import asyncio
import pandas as pd
from .pipeline import process_csv
from .config import DEFAULT_CONFIG

async def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    # p.add_argument('--use-ollama', action='store_true')
    args = p.parse_args()

    df = pd.read_csv(args.input, sep=None, engine='python')
    result = await asyncio.run(process_csv(
        df=df,
        model=DEFAULT_CONFIG['model'],
        version=DEFAULT_CONFIG['version']
    ))
    result.to_csv(args.output)

if __name__ == '__main__':
    main()