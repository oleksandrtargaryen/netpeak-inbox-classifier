"""Reads the CSV, runs every request through the classifier concurrently,
and returns the validated results.

Concurrency is capped with a semaphore so we don't hammer the free tier. On a
429 we back off and retry a few times instead of giving up on the request.
"""

import asyncio
import csv
import re

from .classifier import classify, fallback
from .models import ClassifiedRequest

MAX_RETRIES_ON_RATELIMIT = 6


def read_requests(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _is_rate_limit(err: Exception) -> bool:
    text = str(err).lower()
    return "429" in text or "rate" in text or "resource_exhausted" in text


def _retry_after(err: Exception, fallback_delay: float) -> float:
    # the API tells us how long to wait ("Please retry in 31.6s" / "retryDelay": "31s").
    # honour that instead of guessing, it's the difference between finishing and not.
    m = re.search(r"retry in ([\d.]+)s", str(err)) or re.search(r"'?retryDelay'?:\s*'?(\d+)s", str(err))
    if m:
        return float(m.group(1)) + 1  # small cushion
    return fallback_delay


async def _classify_one(client, row: dict, sem: asyncio.Semaphore) -> ClassifiedRequest:
    async with sem:
        delay = 5.0
        for attempt in range(MAX_RETRIES_ON_RATELIMIT):
            try:
                return await classify(client, row)
            except Exception as e:  # noqa: BLE001 - we want to react to anything here
                if _is_rate_limit(e) and attempt < MAX_RETRIES_ON_RATELIMIT - 1:
                    await asyncio.sleep(_retry_after(e, delay))
                    delay = min(delay * 2, 60)  # exponential, capped
                    continue
                # not a rate limit (or out of retries) -> keep the request via fallback
                return fallback(row, str(e))


async def run(rows: list[dict], client, concurrency: int = 3) -> list[ClassifiedRequest]:
    sem = asyncio.Semaphore(concurrency)
    tasks = [_classify_one(client, row, sem) for row in rows]
    return await asyncio.gather(*tasks)
