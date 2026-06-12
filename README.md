# Inbox request classifier

Small service that reads a CSV of free-form internal requests, sends each one to an LLM,
and extracts structured fields (category, department, priority, summary, requested actions,
whether it needs clarification). Output goes to `output.json` plus a short `report.md` with
aggregates.

Built for the Netpeak AI Solutions test task. LLM is Google Gemini (`gemini-2.5-flash-lite`),
the free tier is enough.

## What it does

1. Reads `data/input_requests.csv` (`id, channel, timestamp, raw_text`).
2. For each request, calls Gemini with structured output and validates the answer against a
   strict Pydantic schema.
3. If the model returns something invalid, retries once with the error attached, then falls
   back to a safe record so the request is never silently lost.
4. Writes `output.json` (full result) and `report.md` (counts by category / priority /
   department, plus the list of requests that need clarification).

Requests are processed concurrently (asyncio), with a semaphore to stay friendly to the free
tier and exponential backoff on rate limits.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# put your key in .env: GEMINI_API_KEY=...  (get one at https://aistudio.google.com/apikey)

python -m src.main
```

That writes `output.json` and `report.md` to the project root.

Useful flags:

```bash
python -m src.main --input data/input_requests.csv --output output.json --concurrency 5
python -m src.main --telegram   # also send a digest to Telegram (needs bot token + chat id)
python -m src.main --sheets     # also write results to a Google Sheet (needs a service account)
```

Run the tests (no network, no key needed):

```bash
pytest -q
```

### Docker

```bash
docker compose up --build
```

It reads from `data/` and writes `output.json` / `report.md` back to the host.

## The schema

Required fields from the task:

| Field | Type | Notes |
|---|---|---|
| `category` | enum | автоматизація / інтеграція / звіт/аналітика / баг/підтримка / питання/консультація / поза скоупом |
| `target_department` | string \| null | null when the text doesn't make it clear |
| `priority` | low / medium / high | inferred from tone and content |
| `short_summary` | string | the gist in one sentence |
| `requested_actions` | list | concrete asks, can be empty |
| `needs_clarification` | bool | true when too vague to act on as-is |

I added three fields on top, each earns its place against the real data:

- **`clarification_questions`** - when a request is too raw (REQ-002 "хлопці треба бот",
  REQ-011 "нам би табличку якусь"), a bare `needs_clarification: true` isn't actionable. The
  questions to ask back are the useful part, so the model produces them directly.
- **`confidence`** (0..1) - some requests are genuinely ambiguous or duplicates (REQ-013 is the
  same Google Ads report as REQ-001, just a different person). A confidence score lets a human
  sort the borderline ones to the top instead of trusting every label equally.
- **`parse_error`** - internal flag, set only when we had to fall back. Makes failed records
  easy to filter without guessing.

Validation is Pydantic v2. Enum values, the 0..1 range on confidence, and "null"/"невідомо"
style strings collapsing to a real `null` are all enforced there.

## Where it breaks / limitations

- **Invalid LLM output.** The model occasionally returns prose instead of JSON, a wrong enum
  value, or an out-of-range number. Handling: ask for JSON via Gemini structured output, parse
  into Pydantic, retry once with the validation error fed back, and if it still fails write a
  fallback record (`parse_error: true`, `needs_clarification: true`). Nothing gets dropped, but
  a fallback record is obviously lower quality than a real classification.
- **Volume / free tier.** 18 rows is trivial. At thousands of rows the bottleneck is the API,
  not the code. The free tier is tight and per-model: `gemini-2.5-flash` gave me only ~20
  requests/day before a hard `RESOURCE_EXHAUSTED`, which is why the default is
  `gemini-2.5-flash-lite` (separate, larger quota and plenty fast for classification). There's
  concurrency + backoff that honours the server's `retryDelay`, but a big run on the free tier
  will still slow to a crawl. For real scale you'd want batching, a persistent queue, and result
  caching (see below). I did not build those.
- **Non-determinism.** Even at `temperature=0` the model isn't perfectly repeatable, and the
  same vague request can land in two plausible categories on different runs. The schema bounds
  *what* it can output, not *which* valid label it picks. I treat the labels as a first pass for
  a human, not ground truth - that's what `confidence` and the clarification list are for.
- **Cost.** `gemini-2.5-flash-lite` on the free tier is effectively free here. At paid volume the
  cost is one short call per request; the obvious win is caching by a hash of `raw_text` so
  re-runs and near-duplicates don't pay twice. Not implemented yet.
- **Categories are fixed.** The six categories come from the task. A request that fits none of
  them gets forced into the closest one (usually "питання/консультація" or "поза скоупом").

## What I'd do next with more time

- Cache results by hashed `raw_text` to make re-runs cheap and idempotent.
- Detect near-duplicate / related requests (REQ-001 vs REQ-013) and link them instead of
  classifying each in isolation.
- A tiny web UI or Slack command so teams get the structured view without running a script.
- A proper job queue + retries for large inboxes instead of a one-shot run.
- An eval set of hand-labelled requests to measure classification quality across prompt changes.

## Project layout

```
src/
  models.py        # Pydantic schema + enums
  classifier.py    # prompt, Gemini call, retry + fallback
  pipeline.py      # CSV reading, async processing, rate-limit backoff
  report.py        # report.md aggregates
  main.py          # CLI entry point
  integrations/
    telegram.py    # optional digest
    sheets.py      # optional Google Sheets export
tests/
  test_models.py   # schema validation + fallback, no network
data/
  input_requests.csv
```
