"""CLI entry point.

Usage:
    python -m src.main --input data/input_requests.csv --output output.json
    python -m src.main --telegram --sheets --concurrency 5
"""

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

from .pipeline import read_requests, run
from .report import build_report


def parse_args():
    p = argparse.ArgumentParser(description="Classify inbox requests with an LLM")
    p.add_argument("--input", default="data/input_requests.csv")
    p.add_argument("--output", default="output.json")
    p.add_argument("--report", default="report.md")
    p.add_argument("--concurrency", type=int, default=5)
    p.add_argument("--telegram", action="store_true", help="send the digest to Telegram")
    p.add_argument("--sheets", action="store_true", help="write results to a Google Sheet")
    return p.parse_args()


def make_client():
    from google import genai

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("GEMINI_API_KEY is not set (put it in .env). Can't reach the model.")
        sys.exit(1)
    return genai.Client(api_key=api_key)


async def main():
    load_dotenv()
    args = parse_args()

    rows = read_requests(args.input)
    print(f"Read {len(rows)} requests from {args.input}")

    client = make_client()
    results = await run(rows, client, concurrency=args.concurrency)

    payload = [r.model_dump() for r in results]
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"Wrote {args.output} ({len(payload)} records)")

    with open(args.report, "w", encoding="utf-8") as f:
        f.write(build_report(results))
    print(f"Wrote {args.report}")

    if args.telegram:
        from .integrations.telegram import send_digest

        send_digest(results)

    if args.sheets:
        from .integrations.sheets import write_results

        write_results(results)


if __name__ == "__main__":
    asyncio.run(main())
