"""Tests for the schema and the fallback path. These don't hit the network,
they just check that validation behaves and that broken model output still
produces a usable record."""

import json

import pytest
from pydantic import ValidationError

from src.classifier import _parse, fallback
from src.models import Category, ClassifiedRequest, Priority

ROW = {
    "id": "REQ-001",
    "channel": "Slack",
    "timestamp": "2026-06-08 09:14",
    "raw_text": "треба автоматизувати звіт",
}


def test_valid_output_parses():
    raw = json.dumps(
        {
            "category": "автоматизація",
            "target_department": "Маркетинг",
            "priority": "medium",
            "short_summary": "Автоматизувати щотижневий звіт",
            "requested_actions": ["зробити автоматичну вивантажку"],
            "needs_clarification": False,
            "clarification_questions": [],
            "confidence": 0.8,
        }
    )
    r = _parse(ROW, raw)
    assert r.id == "REQ-001"
    assert r.category == Category.automation
    assert r.priority == Priority.medium
    assert r.parse_error is False


def test_bad_enum_is_rejected():
    with pytest.raises(ValidationError):
        ClassifiedRequest(
            id="x",
            channel="Slack",
            timestamp="t",
            category="not-a-category",
            priority="medium",
            short_summary="...",
            needs_clarification=False,
        )


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        ClassifiedRequest(
            id="x",
            channel="Slack",
            timestamp="t",
            category="автоматизація",
            priority="low",
            short_summary="...",
            needs_clarification=False,
            confidence=5,
        )


def test_department_string_null_becomes_none():
    r = ClassifiedRequest(
        id="x",
        channel="Slack",
        timestamp="t",
        category="питання/консультація",
        priority="low",
        short_summary="...",
        needs_clarification=False,
        target_department="невідомо",
    )
    assert r.target_department is None


def test_broken_json_uses_fallback():
    # _parse would raise on this; the pipeline catches it and calls fallback
    with pytest.raises(json.JSONDecodeError):
        _parse(ROW, "this is not json at all")

    fb = fallback(ROW, "boom")
    assert fb.parse_error is True
    assert fb.needs_clarification is True
    assert fb.id == "REQ-001"
