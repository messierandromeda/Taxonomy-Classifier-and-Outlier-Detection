"""
pipeline.py: Takes a DF in process_csv and builds the output in batches.
"""

from __future__ import annotations
import asyncio

import httpx
import pandas as pd

from .util.prompt_builder import build_system, build_user, top_n_for
from .util.throttle import TokenBucket, estimate_tokens
from .util.models import TaxonMatch, ClassifierResult, LLMMatch
from .gbif_lookup import match_gbif
from .llm_lookup import classify_land
from .config import log, BATCH_SIZE, ID, NAME, GENUS, FAMILY

_bucket = TokenBucket(tpm=200_000, safety=0.8)


# --- GBIF: resolved once, up front (unchanged) --------------------------------

async def resolve_taxa(df: pd.DataFrame) -> dict[str, TaxonMatch]:
    taxa: dict[str, TaxonMatch] = {}
    async with httpx.AsyncClient(timeout=300.0) as client:
        for _, row in df.iterrows():
            id = str(row.get(ID, "?"))
            try:
                taxa[id] = await match_gbif(
                    row.get(NAME), row.get(GENUS), row.get(FAMILY), client
                )
            except Exception as exc:
                log.warning("Taxonomy lookup failed for %s: %s", id, exc)
                taxa[id] = TaxonMatch(status="error")
    return taxa


def taxon_diff_report(df: pd.DataFrame, taxa: dict[str, TaxonMatch]) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        id = str(row.get(ID, "?"))
        t = taxa.get(id)
        if not t or not t.canonical_name:
            continue
        csv_name = str(row.get(NAME) or "").strip()
        if t.canonical_name and t.canonical_name != csv_name:
            rows.append({
                "id": id, "csv_name": csv_name, "gbif_name": t.canonical_name,
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
) -> ClassifierResult:
    id = str(row.get(ID, "?"))
    top_n = top_n_for(version)

    user_prompt, has_content = build_user(version, row, taxon, use_species)

    if not has_content:
        log.warning("Row %s has no usable text field; skipping classification", id)
        return ClassifierResult(
            id=id, taxon=taxon,
            llm=LLMMatch(id=id, input="", model=model,
                        top_n=top_n, prompt_variant=variant),
        )
    
    expected_output = 700 if top_n >= 3 else 300   # v5 asks for 3 matches -> longer completion
    est = estimate_tokens(system_prompt, user_prompt, expected_output)

    await _bucket.acquire(est)                      # THE gate — no semaphore alongside it
    llm = await classify_land(
        id=id, model=model,
        system_prompt=system_prompt, user_prompt=user_prompt,
        top_n=top_n, prompt_variant=variant,
    )

    if llm.prompt_tokens is not None and llm.completion_tokens is not None:
        actual = llm.prompt_tokens + llm.completion_tokens
        await _bucket.reconcile(est, actual)         # true up: pre-call estimate is a guess

    return ClassifierResult(id=id, taxon=taxon, llm=llm)


async def check_batch(batch, system_prompt, version, model, taxa, variant,
                      use_species=True) -> list[ClassifierResult]:
    """Returns TestResult objects (not .to_row() dicts) so the caller can find
    and retry failures before finalizing the batch."""
    results = await asyncio.gather(
        *[
            process_row(
                row=row, system_prompt=system_prompt, version=version,
                model=model, taxon=taxa.get(str(row.get(ID, "?"))),
                variant=variant, use_species=use_species
            )
            for row in batch
        ],
        return_exceptions=True,
    )

    out = []
    for i, result in enumerate(results):
        id = str(batch[i].get(ID, "?"))
        if isinstance(result, Exception):
            log.error("FAIL %s: %s", id, result)
            result = ClassifierResult(id=id, error=str(result))
        out.append(result)
    return out


async def _retry_failed(failed: list[tuple[pd.Series, str]], system_prompt, version,
                        model, taxa, variant, use_species) -> dict[str, ClassifierResult]:
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
    use_species: bool = True
) -> pd.DataFrame:
    variant = variant or f"v{version}"
    system_prompt = build_system(version)
    if taxa is None:
        taxa = await resolve_taxa(df)

    rows_id = {str(row.get(ID, "?")): row for _, row in df.iterrows()}
    result: list[ClassifierResult] = []
    batch: list[pd.Series] = []

    async def flush(batch):
        if not batch:
            return []
        return await check_batch(batch, system_prompt, version, model,
                                 taxa, variant, use_species)

    for _, row in df.iterrows():
        batch.append(row)
        if len(batch) == BATCH_SIZE:
            result.extend(await flush(batch))
            batch = []
    result.extend(await flush(batch))

    # one retry pass for anything that still has an error after gather+SDK retries
    failed = [(rows_id[r.id], r.id) for r in result if r.error and r.id in rows_id]
    if failed:
        retried = await _retry_failed(failed, system_prompt, version, model,
                                      taxa, variant, use_species)
        result = [retried.get(r.id, r) if r.error else r for r in result]

    return pd.DataFrame([r.to_row() for r in result])