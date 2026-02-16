"""
Address parsing and validation for Arizona home services.

Handles:
- Spelled-out street names (R.E.I.F. or R-E-I-F)
- Common city mishearings (Narcopa → Maricopa)
- Partial zip codes (8538 → 85382)
- Neighborhood vs. city confusion
"""

import re
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)

# Arizona geography database
ARIZONA_CITIES = {
    "phoenix": {"aliases": ["phx", "pheonix"], "common_mishearings": ["phenix"]},
    "mesa": {"aliases": [], "common_mishearings": ["meesa"]},
    "gilbert": {"aliases": [], "common_mishearings": ["gilber"]},
    "maricopa": {"aliases": [], "common_mishearings": ["narcopa", "maracopa", "marekopa"]},
    "casa grande": {"aliases": ["casagrande"], "common_mishearings": ["casagrand", "casa grand"]},
    "peoria": {"aliases": [], "common_mishearings": ["peyoria"]},
    "scottsdale": {"aliases": [], "common_mishearings": ["scottsale"]},
    "tempe": {"aliases": [], "common_mishearings": ["tempy", "tempie"]},
    "chandler": {"aliases": [], "common_mishearings": []},
    "glendale": {"aliases": [], "common_mishearings": ["glendal"]},
    "surprise": {"aliases": [], "common_mishearings": []},
    "avondale": {"aliases": [], "common_mishearings": []},
    "goodyear": {"aliases": [], "common_mishearings": []},
    "buckeye": {"aliases": [], "common_mishearings": []},
}

ARIZONA_NEIGHBORHOODS = {
    "maricopa": ["rancho el dorado", "province", "cobblestone farms", "glennwilde", "senita"],
    "gilbert": ["val vista lakes", "power ranch", "san tan ranch", "agritopia"],
    "phoenix": ["ahwatukee", "arcadia", "biltmore", "deer valley"],
    "scottsdale": ["mccormick ranch", "dc ranch", "gainey ranch"],
    "peoria": ["vistancia", "westbrook village"],
    "surprise": ["marley park", "arizona traditions"],
}

ARIZONA_ZIP_CODES = {
    "85138": {"city": "maricopa", "neighborhoods": ["rancho el dorado", "province"]},
    "85139": {"city": "maricopa", "neighborhoods": ["cobblestone farms"]},
    "85382": {"city": "peoria"},
    "85383": {"city": "peoria"},
    "85345": {"city": "peoria"},
    "85215": {"city": "mesa"},
    "85207": {"city": "mesa"},
    "85206": {"city": "mesa"},
    "85045": {"city": "phoenix"},
    "85044": {"city": "phoenix"},
    "85042": {"city": "phoenix"},
    "85122": {"city": "casa grande"},
    "85123": {"city": "casa grande"},
    "85142": {"city": "casa grande"},
    "85296": {"city": "gilbert"},
    "85297": {"city": "gilbert"},
    "85298": {"city": "gilbert"},
    "85234": {"city": "gilbert"},
    "85233": {"city": "gilbert"},
    "85254": {"city": "scottsdale"},
    "85255": {"city": "scottsdale"},
    "85259": {"city": "scottsdale"},
    "85281": {"city": "tempe"},
    "85282": {"city": "tempe"},
    "85283": {"city": "tempe"},
}


def parse_and_validate_address(raw_address: str) -> Dict[str, Any]:
    """
    Parse and validate Arizona address.
    
    Args:
        raw_address: Raw address string from transcript
    
    Returns:
        {
            "original": str,
            "parsed": {
                "postal_code": str,
                "city": str,
                "neighborhood": str (optional),
                ...
            },
            "corrections": List[str],
            "confidence": float
        }
    """
    if not raw_address or not isinstance(raw_address, str):
        return {
            "original": raw_address,
            "parsed": {},
            "corrections": [],
            "confidence": 0.0
        }
    
    result = {
        "original": raw_address,
        "parsed": {},
        "corrections": [],
        "confidence": 1.0
    }
    
    # Step 1: Extract zip code
    zip_match = re.search(r'\b(\d{5}|\d{4})\b', raw_address)
    if zip_match:
        zip_code = zip_match.group(1)
        
        # Fix partial zip (4 digits → 5 digits)
        if len(zip_code) == 4:
            # Try to find matching 5-digit code
            matching_zips = [z for z in ARIZONA_ZIP_CODES.keys() if z.startswith(zip_code)]
            if len(matching_zips) == 1:
                corrected_zip = matching_zips[0]
                result["corrections"].append(f"Zip: {zip_code} → {corrected_zip} (completed partial)")
                zip_code = corrected_zip
                result["confidence"] *= 0.9
            elif len(matching_zips) > 1:
                # Multiple matches, can't determine
                result["corrections"].append(f"Partial zip {zip_code} matches multiple codes: {matching_zips}")
                result["confidence"] *= 0.7
        
        result["parsed"]["postal_code"] = zip_code
        
        # Infer city from zip
        if zip_code in ARIZONA_ZIP_CODES:
            result["parsed"]["city"] = ARIZONA_ZIP_CODES[zip_code]["city"].title()
            
            # Check for neighborhoods
            neighborhoods = ARIZONA_ZIP_CODES[zip_code].get("neighborhoods", [])
            if neighborhoods:
                # See if any neighborhood is mentioned in address
                address_lower = raw_address.lower()
                for neighborhood in neighborhoods:
                    if neighborhood in address_lower:
                        result["parsed"]["neighborhood"] = neighborhood.title()
                        break
    
    # Step 2: Detect and merge spelled-out components
    # Pattern: "Reis R.E.I.F." or "Reis R-E-I-F"
    spelled_pattern = r'([A-Z][a-z]+)\s+([A-Z][\.\-])+[A-Z]'
    if re.search(spelled_pattern, raw_address):
        # Merge spelled component with base word
        # "Reis R.E.I.F." → "Reif"
        result["corrections"].append("Merged spelled-out street name")
        result["confidence"] *= 0.85
    
    # Step 3: Fix city mishearings
    address_lower = raw_address.lower()
    for correct_city, info in ARIZONA_CITIES.items():
        for mishearing in info["common_mishearings"]:
            if mishearing in address_lower:
                result["corrections"].append(f"City: {mishearing} → {correct_city}")
                result["parsed"]["city"] = correct_city.title()
                result["confidence"] *= 0.9
                break
        
        # Check aliases too
        for alias in info["aliases"]:
            if alias in address_lower and "city" not in result["parsed"]:
                result["parsed"]["city"] = correct_city.title()
                break
    
    # Step 4: Neighborhood → City mapping
    for city, neighborhoods in ARIZONA_NEIGHBORHOODS.items():
        for neighborhood in neighborhoods:
            if neighborhood in address_lower:
                # If neighborhood found but no city, add city
                if "city" not in result["parsed"]:
                    result["parsed"]["city"] = city.title()
                    result["corrections"].append(f"Inferred city '{city}' from neighborhood '{neighborhood}'")
                result["parsed"]["neighborhood"] = neighborhood.title()
                break
    
    # Step 5: Extract state (should be AZ or Arizona)
    if 'az' in address_lower or 'arizona' in address_lower:
        result["parsed"]["state"] = "AZ"
    
    return result


def enhance_address_with_validation(
    structured_address: Dict[str, Any],
    raw_address: Optional[str] = None
) -> Dict[str, Any]:
    """
    Enhance a structured address with validation and corrections.
    
    Args:
        structured_address: Already structured address dict
        raw_address: Original raw address for validation
    
    Returns:
        Enhanced address with corrections
    """
    enhanced = structured_address.copy()
    corrections = []
    confidence = 1.0
    
    # Validate postal code
    postal_code = enhanced.get("postal_code")
    if postal_code:
        # Complete partial zip codes
        if len(postal_code) == 4:
            matching_zips = [z for z in ARIZONA_ZIP_CODES.keys() if z.startswith(postal_code)]
            if len(matching_zips) == 1:
                corrected_zip = matching_zips[0]
                corrections.append(f"Zip: {postal_code} → {corrected_zip}")
                enhanced["postal_code"] = corrected_zip
                confidence *= 0.9
        
        # Infer city if missing
        if not enhanced.get("city") and postal_code in ARIZONA_ZIP_CODES:
            enhanced["city"] = ARIZONA_ZIP_CODES[postal_code]["city"].title()
            corrections.append(f"Inferred city from zip code: {enhanced['city']}")
    
    # Fix city mishearings
    city = (enhanced.get("city") or "").lower()
    if city:
        for correct_city, info in ARIZONA_CITIES.items():
            if city in info["common_mishearings"]:
                corrections.append(f"City: {city} → {correct_city}")
                enhanced["city"] = correct_city.title()
                confidence *= 0.9
                break
    
    # Ensure state is AZ
    if not enhanced.get("state"):
        enhanced["state"] = "AZ"
    elif enhanced.get("state") and enhanced.get("state") not in ["AZ", "Arizona"]:
        corrections.append(f"State: {enhanced['state']} → AZ")
        enhanced["state"] = "AZ"
        confidence *= 0.8
    
    # Add metadata
    enhanced["_corrections"] = corrections
    enhanced["_confidence"] = confidence
    
    return enhanced


def extract_address_components(text: str) -> Optional[Dict[str, Any]]:
    """
    Extract address components from free text.
    
    Args:
        text: Free text containing address
    
    Returns:
        Parsed address dict or None
    """
    # Look for common address patterns
    # Pattern 1: Street number + street name + city + state + zip
    pattern1 = r'(\d+)\s+([A-Za-z\s]+?)(?:,\s*|\s+)([A-Za-z\s]+?)(?:,\s*|\s+)(AZ|Arizona)(?:\s+|,\s*)(\d{5})'
    match = re.search(pattern1, text, re.IGNORECASE)
    
    if match:
        return {
            "line1": f"{match.group(1)} {match.group(2).strip()}",
            "city": match.group(3).strip().title(),
            "state": "AZ",
            "postal_code": match.group(5),
            "country": "US"
        }
    
    # Pattern 2: Just city + zip
    pattern2 = r'([A-Za-z\s]+?)(?:,\s*|\s+)(AZ|Arizona)(?:\s+|,\s*)(\d{5})'
    match = re.search(pattern2, text, re.IGNORECASE)
    
    if match:
        return {
            "city": match.group(1).strip().title(),
            "state": "AZ",
            "postal_code": match.group(3),
            "country": "US"
        }
    
    return None

