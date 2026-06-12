"""Talks to Gemini and turns one raw request into a validated ClassifiedRequest.

The flow per request: build the prompt, ask for json, validate with Pydantic.
If the model returns junk, retry once with the error attached. If it still
fails, we don't drop the request, we write a safe fallback instead.
"""

import json

from pydantic import ValidationError

from .models import Category, ClassifiedRequest

MODEL = "gemini-2.0-flash"

# json schema we hand to Gemini's structured output. Kept close to the Pydantic
# model but without the fields we fill ourselves.
RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {
            "type": "string",
            "enum": [c.value for c in Category],
        },
        "target_department": {"type": "string", "nullable": True},
        "priority": {"type": "string", "enum": ["low", "medium", "high"]},
        "short_summary": {"type": "string"},
        "requested_actions": {"type": "array", "items": {"type": "string"}},
        "needs_clarification": {"type": "boolean"},
        "clarification_questions": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
    },
    "required": [
        "category",
        "priority",
        "short_summary",
        "requested_actions",
        "needs_clarification",
        "confidence",
    ],
}

# Instructions are in English, but the category values must stay exactly as the
# Ukrainian strings the task defined, and the input text is mostly Ukrainian.
SYSTEM_PROMPT = """You are an assistant for the AI unit at Netpeak. Incoming messages are free-form requests from internal teams (marketing, sales, analytics, PM, HR, accounting, etc.), mostly written in Ukrainian, sometimes English.

Classify the request and extract structured fields. Return exactly one JSON object and nothing else.

Fields:
- category: one of "автоматизація", "інтеграція", "звіт/аналітика", "баг/підтримка", "питання/консультація", "поза скоупом". Use "поза скоупом" when it is not a task for the AI unit at all (hardware purchases, thank-you notes, off-topic).
- target_department: the requesting department if the text makes it clear (e.g. "Продажі", "HR", "Аналітика", "SMM", "Бухгалтерія", "Контент"). If unclear, return null.
- priority: low / medium / high. Infer it from tone and content. "ГОРИТЬ", "сьогодні до вечора", "терміново", a broken production automation map to high. "не горить", "просто цікаво", "колись" map to low.
- short_summary: the gist in one short sentence, in Ukrainian.
- requested_actions: a list of the concrete actions being asked for. Can be empty if nothing concrete is requested.
- needs_clarification: true when the request is too vague to act on as-is (e.g. "треба бот", "нам би табличку").
- clarification_questions: if needs_clarification is true, give 1-3 concrete questions worth asking the requester. Otherwise an empty list.
- confidence: 0..1, how confident you are in the classification. Lower it when the request is ambiguous.
"""


def build_user_prompt(row: dict) -> str:
    return (
        f"Channel: {row['channel']}\n"
        f"Time: {row['timestamp']}\n"
        f"Request text:\n{row['raw_text']}"
    )


def _parse(row: dict, raw_json: str) -> ClassifiedRequest:
    data = json.loads(raw_json)
    # the model only fills the content fields, we attach the identity fields
    data["id"] = row["id"]
    data["channel"] = row["channel"]
    data["timestamp"] = row["timestamp"]
    return ClassifiedRequest(**data)


def fallback(row: dict, reason: str) -> ClassifiedRequest:
    """When the model output can't be salvaged, keep the request with a flag
    so a human picks it up instead of it silently disappearing."""
    return ClassifiedRequest(
        id=row["id"],
        channel=row["channel"],
        timestamp=row["timestamp"],
        category=Category.question,
        target_department=None,
        priority="medium",
        short_summary=f"[auto-parse failed] {row['raw_text'][:120]}",
        requested_actions=[],
        needs_clarification=True,
        clarification_questions=["Could not process this request automatically, needs a manual look."],
        confidence=0.0,
        parse_error=True,
    )


async def classify(client, row: dict) -> ClassifiedRequest:
    from google.genai import types

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=RESPONSE_SCHEMA,
        temperature=0,
    )

    prompt = build_user_prompt(row)
    last_error = ""

    for attempt in range(2):
        contents = prompt
        if attempt > 0:
            # second try: tell the model what was wrong with the first answer
            contents = (
                f"{prompt}\n\nThe previous answer was invalid: {last_error}\n"
                "Return STRICTLY valid JSON matching the schema."
            )
        try:
            resp = await client.aio.models.generate_content(
                model=MODEL, contents=contents, config=config
            )
            return _parse(row, resp.text)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_error = str(e)[:300]

    return fallback(row, last_error)
