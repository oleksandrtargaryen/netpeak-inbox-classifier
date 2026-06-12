"""Reads the CSV, runs every request through the classifier concurrently,
and returns the validated results.

Concurrency is capped with a semaphore so we don't hammer the free tier. On a
429 we back off and retry a few times instead of giving up on the request.
"""

import asyncio
import csv

from .classifier import classify, fallback
from .models import ClassifiedRequest

MAX_RETRIES_ON_RATELIMIT = 4


def read_requests(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _is_rate_limit(err: Exception) -> bool:
    text = str(err).lower()
    return "429" in text or "rate" in text or "resource_exhausted" in text


async def _classify_one(client, row: dict, sem: asyncio.Semaphore) -> ClassifiedRequest:
    async with sem:
        delay = 2.0
        for attempt in range(MAX_RETRIES_ON_RATELIMIT):
            try:
                return await classify(client, row)
            except Exception as e:  # noqa: BLE001 - we want to react to anything here
                if _is_rate_limit(e) and attempt < MAX_RETRIES_ON_RATELIMIT - 1:
                    await asyncio.sleep(delay)
                    delay *= 2  # simple exponential backoff
                    continue
                # not a rate limit (or out of retries) -> keep the request via fallback
                return fallback(row, str(e))


async def run(rows: list[dict], client, concurrency: int = 5) -> list[ClassifiedRequest]:
    sem = asyncio.Semaphore(concurrency)
    tasks = [_classify_one(client, row, sem) for row in rows]
    return await asyncio.gather(*tasks)
