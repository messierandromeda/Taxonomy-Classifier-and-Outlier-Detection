"""
process.py — runs one prompt version over a DataFrame.

Changes from the semaphore+bucket version:
  - _llm_gate (Semaphore) REMOVED. The token bucket is the sole pacing
    mechanism — it's the only one denominated in what OpenAI actually limits
    (TPM). A semaphore caps *request count*, which is the wrong unit: 5
    concurrent short calls and 5 concurrent long calls look identical to a
    semaphore but are very different token loads.
  - BATCH_SIZE is now purely a chunking/memory concern. Batches can be large;
    the bucket paces the actual wire traffic regardless of how many tasks are
    "in flight" waiting on acquire().
  - Per-call token estimate from the real prompt (estimate_tokens), reconciled
    against actual usage after the response — see throttle.py.
  - A retry pass: rows that still failed after the SDK's own retries (i.e. hit
    a genuine, non-transient error) get ONE more attempt, sequentially, after
    the rest of the batch. Previously a row that exhausted retries just became
    a permanent `error` — the six version files would then have silently
    different missing rows, corrupting any row-aligned comparison.
"""

from __future__ import annotations
import asyncio

import httpx
import pandas as pd

from .config import ID_TEST, NAME, GENUS, FAMILY
from .classifier import classify_land_test
from .models import TestClassification, TestResult
from .prompt_builder import build_system, build_user, top_n_for
from .throttle import TokenBucket, estimate_tokens

from app.gbif_lookup import match_gbif
from app.models import TaxonMatch
from app.config import log, BATCH_SIZE

_bucket = TokenBucket(tpm=200_000, safety=0.8)


# --- GBIF: resolved once, up front (unchanged) --------------------------------

async def resolve_taxa(df: pd.DataFrame) -> dict[str, TaxonMatch]:
    taxa: dict[str, TaxonMatch] = {}
    async with httpx.AsyncClient(timeout=300.0) as client:
        for _, row in df.iterrows():
            rid = str(row.get(ID_TEST, "?"))
            try:
                taxa[rid] = await match_gbif(
                    row.get(NAME), row.get(GENUS), row.get(FAMILY), client
                )
            except Exception as exc:
                log.warning("Taxonomy lookup failed for %s: %s", rid, exc)
                taxa[rid] = TaxonMatch(status="error")
    return taxa


def taxon_diff_report(df: pd.DataFrame, taxa: dict[str, TaxonMatch]) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        rid = str(row.get(ID_TEST, "?"))
        t = taxa.get(rid)
        if not t or not t.canonical_name:
            continue
        csv_name = str(row.get(NAME) or "").strip()
        if t.canonical_name and t.canonical_name != csv_name:
            rows.append({
                "id": rid, "csv_name": csv_name, "gbif_name": t.canonical_name,
                "rank": t.rank, "match_type": t.match_type,
                "confidence": t.confidence, "is_synonym": t.is_synonym,
                "status": t.status,
            })
    return pd.DataFrame(rows)


# --- one row --------------------------------------------------------------

async def process_row(
    row: pd.Series,
    system_prompt: str,
    version: int,
    model: str,
    taxon: TaxonMatch | None,
    variant: str,
    use_species: bool = True,
    prompt: str | None = None
) -> TestResult:
    rid = str(row.get(ID_TEST, "?"))
    top_n = top_n_for(version)

    user_prompt, has_content = build_user(version, row, taxon, use_species)

    if not has_content:
        log.warning("Row %s has no usable text field; skipping classification", rid)
        return TestResult(
            id=rid, taxon=taxon,
            clc=TestClassification(id=rid, input="", model=model,
                                   top_n=top_n, prompt_variant=variant),
        )
    if prompt:
        system_prompt = prompt

    expected_output = 700 if top_n >= 3 else 300   # v5 asks for 3 matches -> longer completion
    est = estimate_tokens(system_prompt, user_prompt, expected_output)

    await _bucket.acquire(est)                      # THE gate — no semaphore alongside it
    clc = await classify_land_test(
        id=rid, model=model,
        system_prompt=system_prompt, user_prompt=user_prompt,
        top_n=top_n, prompt_variant=variant,
    )

    if clc.prompt_tokens is not None and clc.completion_tokens is not None:
        actual = clc.prompt_tokens + clc.completion_tokens
        await _bucket.reconcile(est, actual)         # true up: pre-call estimate is a guess

    return TestResult(id=rid, taxon=taxon, clc=clc)


async def check_batch(batch, system_prompt, version, model, taxa, variant,
                      use_species=True, prompt: str | None = None) -> list[TestResult]:
    """Returns TestResult objects (not .to_row() dicts) so the caller can find
    and retry failures before finalizing the batch."""
    results = await asyncio.gather(
        *[
            process_row(
                row=row, system_prompt=system_prompt, version=version,
                model=model, taxon=taxa.get(str(row.get(ID_TEST, "?"))),
                variant=variant, use_species=use_species, prompt=prompt
            )
            for row in batch
        ],
        return_exceptions=True,
    )

    out = []
    for i, result in enumerate(results):
        rid = str(batch[i].get(ID_TEST, "?"))
        if isinstance(result, Exception):
            log.error("FAIL %s: %s", rid, result)
            result = TestResult(id=rid, error=str(result))
        out.append(result)
    return out


async def _retry_failed(failed: list[tuple[pd.Series, str]], system_prompt, version,
                        model, taxa, variant, use_species) -> dict[str, TestResult]:
    """One retry pass, SEQUENTIAL (not gathered) — these already survived the
    SDK's own retry/backoff and still failed, so hammering them concurrently
    again is more likely to repeat the failure than fix it."""
    if not failed:
        return {}
    log.info("retrying %d row(s) that failed after SDK retries", len(failed))
    retried = {}
    for row, rid in failed:
        try:
            r = await process_row(row, system_prompt, version, model,
                                  taxa.get(rid), variant, use_species)
            retried[rid] = r
            if r.error:
                log.warning("retry still failed for %s: %s", rid, r.error)
        except Exception as exc:
            log.warning("retry raised for %s: %s", rid, exc)
    return retried


async def process_csv(
    df: pd.DataFrame,
    model: str,
    version: int,
    variant: str | None = None,
    taxa: dict[str, TaxonMatch] | None = None,
    use_species: bool = True,
    prompt: str | None = None
) -> pd.DataFrame:
    variant = variant or f"v{version}"
    system_prompt = build_system(version)
    if taxa is None:
        taxa = await resolve_taxa(df)

    rows_by_id = {str(row.get(ID_TEST, "?")): row for _, row in df.iterrows()}
    result: list[TestResult] = []
    batch: list[pd.Series] = []

    async def flush(batch):
        if not batch:
            return []
        return await check_batch(batch, system_prompt, version, model,
                                 taxa, variant, use_species, prompt)

    for _, row in df.iterrows():
        batch.append(row)
        if len(batch) == BATCH_SIZE:
            result.extend(await flush(batch))
            batch = []
    result.extend(await flush(batch))

    # one retry pass for anything that still has an error after gather+SDK retries
    failed = [(rows_by_id[r.id], r.id) for r in result if r.error and r.id in rows_by_id]
    if failed:
        retried = await _retry_failed(failed, system_prompt, version, model,
                                      taxa, variant, use_species)
        result = [retried.get(r.id, r) if r.error else r for r in result]

    return pd.DataFrame([r.to_row() for r in result])