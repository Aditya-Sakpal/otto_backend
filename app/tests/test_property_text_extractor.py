"""Unit tests for the deterministic property-text extractor (no DB/LLM).

Covers the fallback that mines roof type / stories / size / solar / HOA / condition
from summary + service_requested text when Shunya leaves property_details null,
plus the integration into build_property_brief (text fills only fields Shunya
didn't provide; real property_details always wins).
"""
from uuid import uuid4

from app.services.property_text_extractor import extract_property_from_text
from app.services.appointment_service import build_property_brief


# ── Extractor unit cases (modeled on real prod summaries) ────────────────
def test_extract_tile_and_condition():
    out = extract_property_from_text(
        "Roof inspection and cracked/missing roof tile repair",
        "The homeowner reported a cracked roof tile and a missing section of the roof.",
    )
    assert out["roof_type"] == "tile"
    assert out["roof_condition"] in ("cracked tiles", "missing material")


def test_extract_concrete_tile_solar():
    out = extract_property_from_text(
        "Free quote for concrete tile roof underlayment replacement including "
        "removal and reinstallation of 32 solar panels",
    )
    assert out["roof_type"] == "tile"
    assert out["has_solar"] is True
    assert out["roof_condition"] == "underlayment issue"


def test_extract_shingle_two_story_sqft():
    out = extract_property_from_text(
        "Customer has a two-story home, about 2,400 sq ft, asphalt shingle roof, leaking after the storm.",
    )
    assert out["roof_type"] == "shingle"
    assert out["stories"] == "two"
    assert out["property_size"] == "2,400 sqft"
    assert out["roof_condition"] == "leaking"


def test_extract_hoa_and_no_solar():
    out = extract_property_from_text("Single-story house in an HOA community, no solar.")
    assert out["stories"] == "single"
    assert out["hoa_status"] == "yes"
    assert out["has_solar"] is False


def test_extract_no_hoa():
    out = extract_property_from_text("No HOA on this property.")
    assert out["hoa_status"] == "no"


def test_extract_nothing_from_unrelated_text():
    out = extract_property_from_text("AC unit inspection and refrigerant leak repair", "")
    # No roof/property keywords → no roof_type/stories/size.
    assert "roof_type" not in out
    assert "stories" not in out
    assert "property_size" not in out


def test_extract_empty_input():
    assert extract_property_from_text(None, "", "   ") == {}


# ── Integration: brief fills from text when property_details is null ──────
def _cand(**kw):
    base = {
        "call_id": uuid4(), "call_date": "2026-05-01T00:00:00+00:00", "call_type": "csr_call",
        "property_details": None, "customer_details": None, "service_requested": None,
        "qualification_status": None, "booking_status": None, "summary": None,
        "service_address_structured": None,
    }
    base.update(kw)
    return base


def test_brief_fills_roof_from_text_when_pd_null():
    brief = build_property_brief([_cand(
        service_requested="Roof inspection and cracked roof tile repair",
        summary="Two-story tile roof home, leaking after monsoon.",
    )])
    assert brief.has_data is True
    assert brief.roof_type == "tile"
    assert brief.stories == "two"


def test_brief_structured_pd_wins_over_text():
    # Shunya provided roof_type=metal; text says tile → structured wins.
    brief = build_property_brief([_cand(
        property_details={"roof_type": "metal"},
        summary="Concrete tile roof with cracked tiles.",
    )])
    assert brief.roof_type == "metal"


def test_brief_text_fills_only_missing_fields():
    # Shunya gave stories but not roof_type; text supplies roof_type.
    brief = build_property_brief([_cand(
        property_details={"stories": "single"},
        summary="Asphalt shingle roof, leaking.",
    )])
    assert brief.stories == "single"      # from Shunya
    assert brief.roof_type == "shingle"   # from text fallback
