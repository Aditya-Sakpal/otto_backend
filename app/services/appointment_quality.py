"""
Appointment data-quality helpers.

Used by the call-driven appointment ingest path (and any future write path)
to flag low-confidence values that the audit surfaced on the Pipeline
Appointments List view:

  * Issue #38 — impossible appointment times (1 AM, 3 AM, etc.)
  * Issue #40 — generic state-only locations ("AZ, US")

The helpers do not mutate the appointment; they return a quality verdict
that callers attach to ``extra_metadata``. This keeps the existing
``AppointmentResponse`` contract intact (no new top-level fields) while
giving operators and the frontend a structured signal to triage on.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Optional, Tuple, Dict, Any

# Business-hours window (tenant-local). Times outside this window are flagged
# as low confidence so the UI can surface them for manual review. We pick a
# generous window — early-morning trade calls and late-evening estimates are
# realistic; 1–5 AM is not.
DEFAULT_BUSINESS_HOURS_START = time(6, 0)   # 06:00
DEFAULT_BUSINESS_HOURS_END = time(21, 0)    # 21:00


def check_time_quality(
    scheduled_start: Optional[datetime],
    *,
    business_hours_start: time = DEFAULT_BUSINESS_HOURS_START,
    business_hours_end: time = DEFAULT_BUSINESS_HOURS_END,
) -> Optional[str]:
    """
    Return ``"low_confidence"`` when ``scheduled_start`` falls outside business
    hours, else ``None``.

    The check operates on the timestamp's local time (its tzinfo). Callers
    that have a tenant-specific timezone should convert the datetime first
    before calling this; if no tzinfo is supplied we treat it as UTC, which
    is the same default the rest of the codebase uses.

    Returning ``None`` (as opposed to ``"ok"``) keeps the call site terse:
    callers only attach metadata when there is something to flag.
    """
    if scheduled_start is None:
        return None
    dt = scheduled_start
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Compare naive wall-clock time objects — tz-aware vs naive ``time``
    # comparisons raise ``TypeError``, and the business-hours window is
    # expressed as a naive clock time anyway.
    local_t = dt.time()
    if local_t < business_hours_start or local_t > business_hours_end:
        return "low_confidence"
    return None


def check_location_quality(
    *,
    raw_address: Optional[str],
    structured_address: Optional[Dict[str, Any]],
    contact_address_parts: Optional[Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Decide what (if anything) to store as ``location_address`` and how to
    label its quality.

    Returns a tuple ``(address_to_store, quality_label)`` where:

      * ``address_to_store`` is the formatted string to write to
        ``AppointmentORM.location_address``. Returns ``None`` when no
        usable street-level info is available — better to leave the field
        empty than to surface "AZ, US" as if it were a real address.
      * ``quality_label`` is one of ``None``, ``"low"``, or ``"ok"``.
        Callers should write this onto ``extra_metadata.location_quality``.

    Resolution order:

      1. Prefer ``raw_address`` if it looks more specific than just a state.
      2. Fall back to a structured address joined into a single string,
         provided the structured form has at least a line1 / address line.
      3. Fall back to the contact card's address parts under the same rule.
      4. If nothing has a street-level component, return
         ``(None, "low")`` — the audit's #40 case.
    """

    def _has_street_level(text: Optional[str]) -> bool:
        if not text:
            return False
        cleaned = text.strip()
        if not cleaned:
            return False
        # A street-level address has more than ~2 comma-separated tokens.
        # "AZ, US" → 2 tokens, no street info → low quality.
        # "123 Main St, Phoenix, AZ" → 3 tokens, real address → ok.
        # We also require at least one digit OR a longer first token, since
        # most street addresses include a number or a word > 2 chars before
        # the first comma.
        tokens = [t.strip() for t in cleaned.split(",") if t.strip()]
        if len(tokens) < 3:
            return False
        first = tokens[0]
        return bool(any(ch.isdigit() for ch in first) or len(first) > 4)

    # 1. raw_address with street-level detail wins.
    if _has_street_level(raw_address):
        return raw_address.strip(), "ok"

    # 2. Structured address — only if it has a line1 / address line.
    if isinstance(structured_address, dict):
        line1 = structured_address.get("line1") or structured_address.get("address")
        if line1 and str(line1).strip():
            parts = [
                str(line1).strip(),
                str(structured_address.get("city") or "").strip(),
                str(structured_address.get("state") or "").strip(),
                str(structured_address.get("postal_code") or "").strip(),
                str(structured_address.get("country") or "").strip(),
            ]
            joined = ", ".join(p for p in parts if p)
            if _has_street_level(joined):
                return joined, "ok"

    # 3. Contact card parts — same street-level requirement.
    if contact_address_parts is not None:
        addr, city, state, postal = contact_address_parts
        if addr and str(addr).strip():
            joined = ", ".join(
                p for p in [str(addr).strip(), str(city or "").strip(), str(state or "").strip(), str(postal or "").strip()]
                if p
            )
            if _has_street_level(joined):
                return joined, "ok"

    # 4. Nothing street-level — drop the address rather than show "AZ, US".
    #    Operators see location_quality="low" in extra_metadata and can
    #    re-prompt the rep for a real address.
    return None, "low"


def merge_quality_metadata(
    existing: Optional[Dict[str, Any]],
    *,
    time_quality: Optional[str] = None,
    location_quality: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Merge quality flags into an appointment's ``extra_metadata`` dict.

    Returns a new dict (does not mutate ``existing``). Drops the relevant
    keys when the inputs are ``None``, so we don't pile up stale flags
    across re-ingests of the same appointment.
    """
    base = dict(existing or {})
    if time_quality is None:
        base.pop("time_quality", None)
    else:
        base["time_quality"] = time_quality
    if location_quality is None:
        base.pop("location_quality", None)
    else:
        base["location_quality"] = location_quality
    return base or None
