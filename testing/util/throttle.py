"""
throttle.py — a single, correctly-calibrated pacing mechanism.

Previously there were THREE uncoordinated throttles: BATCH_SIZE, an
asyncio.Semaphore(5), and a TokenBucket — only the last was denominated in the
thing OpenAI actually limits (tokens/min), and it started FULL, so the first
~50 requests of every version fired as an instant burst before any pacing
kicked in. That burst is what produced the 429 flood, not a bad EST_TOKENS.

Fix: the token bucket is the ONLY gate. No semaphore. Batching becomes a pure
chunking/isolation concern, not a throughput concern.
"""

from __future__ import annotations
import asyncio
import time


class TokenBucket:
    def __init__(self, tpm: int = 200_000, safety: float = 0.7, max_burst_tokens: int = 6_000):
        self.rate = (tpm * safety) / 60      # sustained tokens/sec
        # Burst is SEPARATE from rate. Previously capacity (=tpm*safety) was the
        # max accumulation, so any idle gap — e.g. the ~12s at the end of a rep
        # while the last responses land — banked tens of thousands of tokens,
        # which the next rep then fired instantly into the same rolling window.
        self.capacity = max_burst_tokens     # ~3 calls' worth, not a minute's worth
        self.tokens = 0.0
        self.updated = time.monotonic()
        self.lock = asyncio.Lock()

    async def acquire(self, need: float) -> None:
        need = min(need, self.capacity)      # never deadlock on need > capacity
        async with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.capacity,
                                  self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= need:
                    self.tokens -= need
                    return
                await asyncio.sleep((need - self.tokens) / self.rate)

    async def reconcile(self, estimated: float, actual: float) -> None:
        """Call after the response comes back with real usage. Pre-call you only
        know prompt length, not completion length (v5's top-3 nearly doubles
        completion tokens vs v0-v3) — without this the bucket's belief about
        remaining budget silently drifts over a long run."""
        diff = actual - estimated
        if diff == 0:
            return
        async with self.lock:
            self.tokens = max(0.0, min(self.capacity, self.tokens - diff))


def estimate_tokens(system_prompt: str, user_prompt: str, expected_output: int = 300) -> int:
    """Rough chars/4 estimate from the ACTUAL prompt being sent, not a flat
    guess — v0 (~1830 tok) and v4/v5 (~1945-1994 tok) differ enough that a flat
    EST_TOKENS either starves the expensive versions or over-throttles the
    cheap ones. expected_output should be bumped for top_n=3 calls (v5)."""
    return (len(system_prompt) + len(user_prompt)) // 4 + expected_output