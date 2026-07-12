"""
staircase.py — standalone runner for the v0..v5 prompt staircase.

Why a script instead of the notebook for full-scale runs:
  - output survives a killed kernel / lost cell (logs to a FILE, not just stdout)
  - resumable: skips any version whose output CSV already exists, so a failure at
    v1 doesn't force re-running v0
  - the outer loop is guarded, unlike the notebook's bare `await run_reps(...)` —
    an exception in process_csv used to kill the whole run silently past the try/
    except that only wrapped individual ROWS, not the version loop itself

Usage:
    python run_staircase.py --input data/working100.csv --reps 5 --versions 0-5
    python run_staircase.py --input data/working100.csv --reps 5 --versions 3   # just v3
    python run_staircase.py --input data/working100.csv --reps 5 --resume        # skip done files
"""

from __future__ import annotations
import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from testing.util.process import process_csv, resolve_taxa, taxon_diff_report
from testing.util.config import RESULT_PATH
from app.config import DEFAULT_MODEL

# --- logging: to a FILE, so a lost/interrupted kernel doesn't lose the trace ---
LOG_PATH = Path(RESULT_PATH) / "run_staircase.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, mode="a"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("staircase")


def parse_versions(spec: str) -> list[int]:
    """'0-5' -> [0,1,2,3,4,5]; '3' -> [3]; '0,2,4' -> [0,2,4]"""
    if "-" in spec:
        lo, hi = spec.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(v) for v in spec.split(",")]


async def run_one_version(
    df: pd.DataFrame,
    model: str,
    version: int,
    reps: int,
    taxa: dict,
    out_path: Path,
) -> bool:
    """Runs all reps for one version. Returns True on success. Any exception is
    logged with the version number and re-raised is NOT done here — the caller
    decides whether to continue to the next version or stop."""
    log.info("v%d: starting (%d rows x %d reps = %d calls)", version, len(df), reps, len(df) * reps)
    t0 = time.monotonic()

    frames = []
    for rep in range(reps):
        log.info("v%d: rep %d/%d", version, rep + 1, reps)
        try:
            r = await process_csv(df, model, version, taxa=taxa)
        except Exception:
            # THIS is the guard that was missing: process_csv failing used to
            # take down the whole run with no trace of which version/rep it hit.
            log.exception("v%d rep %d: process_csv raised — aborting this version", version, rep)
            return False

        if len(r) != len(df):
            log.error("v%d rep %d: got %d rows, expected %d — not writing partial output",
                      version, rep, len(r), len(df))
            return False

        r["rep"] = rep
        r["version"] = version
        if "difficulty_tag" in df.columns:
            r["difficulty"] = df["difficulty_tag"].values
        frames.append(r)

        # write incrementally: if rep 4/5 dies, reps 0-3 are still on disk
        pd.concat(frames, ignore_index=True).to_csv(out_path, index=False)

    elapsed = time.monotonic() - t0
    log.info("v%d: done in %.0fs -> %s", version, elapsed, out_path)
    return True


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--versions", default="0-5")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--resume", action="store_true",
                    help="skip any version whose output CSV already exists")
    args = ap.parse_args()

    versions = parse_versions(args.versions)
    df = pd.read_csv(args.input, dtype={"row_id": str})
    log.info("loaded %d rows from %s | versions=%s | reps=%d | model=%s",
             len(df), args.input, versions, args.reps, args.model)

    out_dir = Path(f'{RESULT_PATH}/exp2')
    out_dir.mkdir(parents=True, exist_ok=True)

    # GBIF resolved ONCE for the whole run, shared across every version/rep —
    # not re-fetched per version, which would 6x the taxonomy API calls for
    # data that doesn't change across the staircase.
    log.info("resolving taxa via GBIF...")
    taxa = await resolve_taxa(df)
    diff = taxon_diff_report(df, taxa)
    diff.to_csv(out_dir / "taxon_diff_report.csv", index=False)
    log.info("GBIF: %d/%d names changed (see taxon_diff_report.csv) — spot-check before trusting",
             len(diff), len(df))

    for version in versions:
        out_path = out_dir / f"version_{version}.csv"

        if args.resume and out_path.exists():
            existing = pd.read_csv(out_path)
            if existing["rep"].nunique() >= args.reps and len(existing) == len(df) * args.reps:
                log.info("v%d: already complete (%s) — skipping", version, out_path)
                continue
            log.info("v%d: found incomplete/partial %s — re-running", version, out_path)

        ok = await run_one_version(df, args.model, version, args.reps, taxa, out_path)
        if not ok:
            log.error("v%d FAILED. Stopping here — earlier versions' CSVs are intact. "
                      "Fix the issue above and re-run with --resume --versions %d-5",
                      version, version)
            sys.exit(1)

    log.info("all versions complete")


if __name__ == "__main__":
    asyncio.run(main())