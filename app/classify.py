#!/usr/bin/env python3

import argparse, asyncio
import pandas as pd
from .pipeline import process_csv

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--use-ollama', action='store_true')
    args = p.parse_args()

    df = pd.read_csv(args.input, sep=None, engine='python')
    asyncio.run(process_csv(df, args.use_ollama, output_path=args.output))

if __name__ == '__main__':
    main()