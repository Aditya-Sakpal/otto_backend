"""Unit tests for follow-up guidance pure parsers (no DB)."""
import pytest

from app.services.pending_action_service import (
    objections_from_raw_analysis,
    response_suggestions_for_objection,
)


# ── objections_from_raw_analysis ─────────────────────────────────────────

def test_parses_nested_objections_with_list_suggestions():
    raw = {
        "objections": {
            "objections": [
                {
                    "objection_text": "Too expensive",
                    "response_suggestions": ["Offer financing", "Show ROI"],
                },
                {
                    "objection_text": "Need to think",
                    "response_suggestions": [],
                },
            ]
        }
    }
    out = objections_from_raw_analysis(raw)
    assert len(out) == 2
    assert out[0] == {"objection": "Too expensive", "suggested_response": "Offer financing"}
    assert out[1] == {"objection": "Need to think", "suggested_response": None}


def test_parses_bare_list_of_objections():
    raw = {"objections": [{"text": "Price", "suggested_response": "Bundle discount"}]}
    out = objections_from_raw_analysis(raw)
    assert out == [{"objection": "Price", "suggested_response": "Bundle discount"}]


def test_handles_string_suggestion():
    raw = {"objections": {"objections": [{"objection_text": "X", "suggested_responses": "Just one"}]}}
    out = objections_from_raw_analysis(raw)
    assert out[0]["suggested_response"] == "Just one"


def test_skips_objection_without_text():
    raw = {"objections": {"objections": [{"response_suggestions": ["orphan"]}]}}
    assert objections_from_raw_analysis(raw) == []


def test_falls_back_to_category_text():
    raw = {"objections": {"objections": [{"category_text": "Budget"}]}}
    out = objections_from_raw_analysis(raw)
    assert out == [{"objection": "Budget", "suggested_response": None}]


@pytest.mark.parametrize("raw", [None, {}, {"objections": None}, {"objections": 42}, "nonsense"])
def test_empty_or_malformed_returns_empty(raw):
    assert objections_from_raw_analysis(raw) == []


# ── response_suggestions_for_objection ───────────────────────────────────

def test_matches_objection_by_text_case_insensitive():
    raw = {
        "objections": {
            "objections": [
                {"objection_text": "Too Expensive", "response_suggestions": ["A", "B"]},
                {"objection_text": "Other", "response_suggestions": ["C"]},
            ]
        }
    }
    assert response_suggestions_for_objection(raw, "too expensive") == ["A", "B"]
    assert response_suggestions_for_objection(raw, "OTHER") == ["C"]


def test_no_match_returns_empty():
    raw = {"objections": {"objections": [{"objection_text": "X", "response_suggestions": ["a"]}]}}
    assert response_suggestions_for_objection(raw, "Y") == []


def test_string_suggestion_wrapped_in_list():
    raw = {"objections": {"objections": [{"objection_text": "X", "suggested_response": "one"}]}}
    assert response_suggestions_for_objection(raw, "X") == ["one"]


@pytest.mark.parametrize("raw,obj", [(None, "x"), ({}, "x"), ({"objections": []}, None)])
def test_guards(raw, obj):
    assert response_suggestions_for_objection(raw, obj) == []
