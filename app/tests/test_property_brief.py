"""Unit tests for build_property_brief (pure, no DB)."""
from datetime import datetime, timezone
from uuid import uuid4

from app.services.appointment_service import (
    build_property_brief,
    _format_service_address,
)

UTC = timezone.utc


def _cand(call_type="csr_call", when=None, property_details=None, customer_details=None,
          service_requested=None, qualification_status=None, booking_status=None, summary=None,
          service_address_structured=None):
    return {
        "call_id": uuid4(),
        "call_date": when or datetime(2026, 6, 1, tzinfo=UTC),
        "call_type": call_type,
        "property_details": property_details,
        "customer_details": customer_details,
        "service_requested": service_requested,
        "qualification_status": qualification_status,
        "booking_status": booking_status,
        "summary": summary,
        "service_address_structured": service_address_structured,
    }


FULL_BLOB = {
    "roof_type": "tile",
    "roof_age_years": 14,
    "stories": "two",
    "hoa_status": "yes",
    "hoa_name": "Sunridge",
    "gated_community": True,
    "gate_access": "Gate code 4417",
    "has_solar": False,
    "pets": "large dog",
    "pet_notes": "friendly",
    "property_size": "2400 sqft",
    "current_issues": ["Active leak over garage after monsoon"],
    "property_access_notes": "Use side gate",
}


# ── Case 1: full blob → fully populated ──────────────────────────────────
def test_full_blob_fully_populated():
    b = build_property_brief([_cand(
        property_details=FULL_BLOB,
        customer_details={"decision_makers": ["homeowner", "spouse"]},
        service_requested="Roof repair",
        qualification_status="qualified",
        booking_status="booked",
    )])
    assert b.has_data is True
    assert b.service_requested == "Roof repair"
    assert b.roof_type == "tile"
    assert b.roof_age_years == 14
    assert b.stories == "two"
    assert b.property_size == "2400 sqft"
    assert b.hoa_status == "yes"
    assert b.hoa_name == "Sunridge"
    assert b.gated_community is True
    assert b.gate_access == "Gate code 4417"
    assert b.pets == "large dog"
    assert b.current_issues == ["Active leak over garage after monsoon"]
    assert b.problem_summary == "Active leak over garage after monsoon"
    assert b.decision_makers == ["homeowner", "spouse"]
    assert b.qualification_status == "qualified"
    assert b.booking_status == "booked"


# ── Case 2: partial blob → partial brief ─────────────────────────────────
def test_partial_blob():
    b = build_property_brief([_cand(
        property_details={"roof_type": "shingle", "stories": "unknown"},  # 'unknown' dropped
        service_requested="Roof inspection",
    )])
    assert b.has_data is True
    assert b.roof_type == "shingle"
    assert b.stories is None          # 'unknown' sentinel cleaned
    assert b.property_size is None    # absent
    assert b.hoa_name is None
    assert b.decision_makers == []
    assert b.service_requested == "Roof inspection"


# ── Case 3: no structured detail but a summary → brief from summary ───────
# Shunya leaves property_details/customer_details null in prod while still
# extracting a usable summary; that summary alone now drives an actionable brief.
def test_summary_only_yields_brief():
    b = build_property_brief([_cand(
        property_details=None, customer_details=None,
        summary="Homeowner reports a refrigerant leak; coil replaced in December.",
    )])
    assert b.has_data is True
    assert b.problem_summary == "Homeowner reports a refrigerant leak; coil replaced in December."
    assert b.roof_type is None
    assert b.decision_makers == []


def test_truly_empty_candidate_empty_brief():
    # No structured detail, no service_requested, sentinel summary → nothing usable.
    b = build_property_brief([_cand(
        property_details=None, customer_details=None,
        service_requested="unknown", summary="",
    )])
    assert b.has_data is False
    assert b.source_call_id is None


def test_no_candidates_empty_brief():
    b = build_property_brief([])
    assert b.has_data is False


# ── Case 4: customer_details present → decision makers surfaced ───────────
def test_customer_details_decision_makers():
    b = build_property_brief([_cand(
        property_details=None,
        customer_details={"decision_makers": ["homeowner", "HOA board"]},
    )])
    assert b.has_data is True
    assert b.decision_makers == ["homeowner", "HOA board"]


def test_decision_maker_singular_key():
    b = build_property_brief([_cand(
        property_details={"roof_type": "metal"},
        customer_details={"decision_maker": "homeowner"},
    )])
    assert b.decision_makers == ["homeowner"]


# ── Case 5: multiple calls → latest CSR call selected ────────────────────
def test_latest_csr_call_selected():
    older_csr = _cand(call_type="csr_call", when=datetime(2026, 5, 1, tzinfo=UTC),
                      property_details={"roof_type": "shingle"})
    newer_csr = _cand(call_type="csr_call", when=datetime(2026, 6, 1, tzinfo=UTC),
                      property_details={"roof_type": "tile"})
    # Unsorted input on purpose — helper must pick newest CSR.
    b = build_property_brief([older_csr, newer_csr])
    assert b.roof_type == "tile"
    assert b.source_call_id == newer_csr["call_id"]


def test_csr_preferred_over_newer_sales_call():
    sales = _cand(call_type="sales_call", when=datetime(2026, 6, 5, tzinfo=UTC),
                  property_details={"roof_type": "metal"})
    csr = _cand(call_type="csr_call", when=datetime(2026, 6, 1, tzinfo=UTC),
                property_details={"roof_type": "tile"})
    b = build_property_brief([sales, csr])
    assert b.roof_type == "tile"          # CSR preferred even though sales is newer
    assert b.source_call_id == csr["call_id"]


def test_falls_back_to_non_csr_when_no_csr_has_detail():
    sales = _cand(call_type="sales_call", when=datetime(2026, 6, 5, tzinfo=UTC),
                  property_details={"roof_type": "metal"})
    csr_no_detail = _cand(call_type="csr_call", when=datetime(2026, 6, 1, tzinfo=UTC),
                          property_details=None, customer_details=None)
    b = build_property_brief([sales, csr_no_detail])
    assert b.has_data is True
    assert b.roof_type == "metal"
    assert b.source_call_id == sales["call_id"]


# ── Case 6: prod-shaped CSR call (no structured details, but service + address) ──
def test_service_requested_only_yields_brief():
    b = build_property_brief([_cand(
        property_details=None, customer_details=None,
        service_requested="HVAC diagnostic and repair quote",
    )])
    assert b.has_data is True
    assert b.service_requested == "HVAC diagnostic and repair quote"


def test_service_address_surfaced():
    b = build_property_brief([_cand(
        service_requested="AC unit inspection",
        service_address_structured={
            "line1": "16244 West Papago Street",
            "city": "Goodyear",
            "state": "Arizona",
            "postal_code": "85338",
        },
    )])
    assert b.has_data is True
    assert b.service_address == "16244 West Papago Street, Goodyear, Arizona 85338"


def test_address_only_yields_brief():
    # Even with only an address (state present), the call is a usable source.
    b = build_property_brief([_cand(
        service_address_structured={"state": "AZ", "postal_code": "85338"},
    )])
    assert b.has_data is True
    assert b.service_address == "AZ 85338"


# ── _format_service_address helper ───────────────────────────────────────
def test_format_service_address_helper():
    assert _format_service_address(None) is None
    assert _format_service_address("not-a-dict") is None
    # All-sentinel sub-fields → None.
    assert _format_service_address(
        {"line1": "unknown", "city": "", "state": None, "postal_code": "unknown"}
    ) is None
    assert _format_service_address({"state": "AZ"}) == "AZ"
    assert _format_service_address(
        {"city": "Goodyear", "state": "AZ", "postal_code": "85338"}
    ) == "Goodyear, AZ 85338"
