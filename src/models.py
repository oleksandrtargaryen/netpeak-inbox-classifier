"""Schema for what we pull out of each request.

Validation lives in Pydantic because the LLM regularly returns either extra
fields, wrong enum casing, or plain text instead of json. I'd rather catch all
of that in one place.
"""

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    automation = "автоматизація"
    integration = "інтеграція"
    analytics = "звіт/аналітика"
    bug = "баг/підтримка"
    question = "питання/консультація"
    out_of_scope = "поза скоупом"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class ClassifiedRequest(BaseModel):
    # these three are copied straight from the csv, the model doesn't invent them
    id: str
    channel: str
    timestamp: str

    category: Category
    target_department: str | None = None
    priority: Priority
    short_summary: str
    requested_actions: list[str] = Field(default_factory=list)
    needs_clarification: bool

    # schema extensions (rationale is in the README):
    # when a request is too raw, build the concrete questions to ask right away
    clarification_questions: list[str] = Field(default_factory=list)
    # how confident the model is; handy for surfacing the borderline cases
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # internal flag: set when we had to fall back instead of a clean parse
    parse_error: bool = False

    @field_validator("target_department")
    @classmethod
    def empty_department_is_null(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        # the model likes to return "null"/"unknown" as a string
        if v == "" or v.lower() in {"null", "none", "невідомо", "не зрозуміло"}:
            return None
        return v


# fields we actually ask the model to fill (id/channel/timestamp we already know)
LLM_FIELDS = [
    "category",
    "target_department",
    "priority",
    "short_summary",
    "requested_actions",
    "needs_clarification",
    "clarification_questions",
    "confidence",
]
