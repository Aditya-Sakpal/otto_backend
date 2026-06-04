"""
Deterministic property-detail extractor (fallback for the pre-appointment brief).

Shunya leaves call_analyses.property_details NULL for every production call (the
property sub-extractor is not deployed on the live Shunya service), but the
already-populated `summary` / `service_requested` text routinely contains the
facts a rep needs — roof type, number of stories, solar, HOA, and the concrete
problem. This module mines those fields from that text so the brief surfaces real,
actionable data today without any Shunya dependency.

Deterministic by design: keyword/regex only (no LLM, no I/O), matching the
"deterministic, no new AI" contract of build_property_brief. Conservative — emits
a field only on a confident keyword hit, so a miss yields None rather than a guess.
"""
from __future__ import annotations

import re
from typing import Optional


# ── Roof type ──────────────────────────────────────────────────────────────
# Ordered: more specific phrases first. Value is the canonical roof_type.
_ROOF_TYPE_PATTERNS: list[tuple[str, str]] = [
    (r"\bconcrete tile\b", "tile"),
    (r"\bclay tile\b", "tile"),
    (r"\btile roof\b", "tile"),
    (r"\btiles?\b", "tile"),
    (r"\basphalt shingle", "shingle"),
    (r"\bshingles?\b", "shingle"),
    (r"\bmetal roof\b", "metal"),
    (r"\bstanding seam\b", "metal"),
    (r"\bfoam roof\b", "foam"),
    (r"\bflat roof\b", "flat"),
    (r"\btpo\b", "tpo"),
    (r"\bepdm\b", "epdm"),
]

# ── Stories ────────────────────────────────────────────────────────────────
_STORIES_PATTERNS: list[tuple[str, str]] = [
    (r"\bsingle[- ]story\b", "single"),
    (r"\bsingle[- ]storey\b", "single"),
    (r"\bone[- ]story\b", "single"),
    (r"\b1[- ]story\b", "single"),
    (r"\btwo[- ]story\b", "two"),
    (r"\btwo[- ]storey\b", "two"),
    (r"\b2[- ]story\b", "two"),
    (r"\bthree[- ]story\b", "three"),
    (r"\b3[- ]story\b", "three"),
    (r"\bsplit[- ]level\b", "split_level"),
]

# ── Square footage ─────────────────────────────────────────────────────────
# e.g. "2,400 sq ft", "2400 square feet", "1800 sqft"
_SQFT_RE = re.compile(
    r"(\d{1,2},\d{3}|\d{3,5})\s*(?:sq\.?\s*ft|sqft|square\s*f(?:ee|oo)t)\b",
    re.IGNORECASE,
)

# ── Solar ──────────────────────────────────────────────────────────────────
_SOLAR_RE = re.compile(r"\bsolar(?:\s*panel)?s?\b", re.IGNORECASE)
# Negations that flip a solar mention to "no solar" (rare; keep simple).
_NO_SOLAR_RE = re.compile(r"\bno\s+solar\b", re.IGNORECASE)

# ── HOA ────────────────────────────────────────────────────────────────────
_HOA_RE = re.compile(r"\bhoa\b|\bhomeowners?\s+association\b", re.IGNORECASE)
_NO_HOA_RE = re.compile(r"\bno\s+hoa\b", re.IGNORECASE)

# ── Roof condition / problem cues (for roof_condition) ──────────────────────
_ROOF_CONDITION_PATTERNS: list[tuple[str, str]] = [
    (r"\bleak", "leaking"),
    (r"\bcracked? (?:roof )?tile", "cracked tiles"),
    (r"\bmissing (?:section|shingle|tile)", "missing material"),
    (r"\bunderlayment", "underlayment issue"),
    (r"\bstorm damage\b", "storm damage"),
    (r"\bhail\b", "hail damage"),
]


def _first_match(text: str, patterns: list[tuple[str, str]]) -> Optional[str]:
    for pattern, value in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return value
    return None


def extract_property_from_text(*text_parts: Optional[str]) -> dict:
    """Mine property fields from free text (summary + service_requested, etc.).

    Returns a dict with only the keys that were confidently found. Mirrors the
    Shunya property_details shape (roof_type, stories, property_size, has_solar,
    hoa_status, roof_condition) so callers can treat it like a partial
    property_details blob. Empty dict when nothing is found.
    """
    text = " ".join(p for p in text_parts if p).strip()
    if not text:
        return {}

    out: dict = {}

    roof_type = _first_match(text, _ROOF_TYPE_PATTERNS)
    if roof_type:
        out["roof_type"] = roof_type

    stories = _first_match(text, _STORIES_PATTERNS)
    if stories:
        out["stories"] = stories

    m = _SQFT_RE.search(text)
    if m:
        out["property_size"] = f"{m.group(1)} sqft"

    if _NO_SOLAR_RE.search(text):
        out["has_solar"] = False
    elif _SOLAR_RE.search(text):
        out["has_solar"] = True

    if _NO_HOA_RE.search(text):
        out["hoa_status"] = "no"
    elif _HOA_RE.search(text):
        out["hoa_status"] = "yes"

    condition = _first_match(text, _ROOF_CONDITION_PATTERNS)
    if condition:
        out["roof_condition"] = condition

    return out
