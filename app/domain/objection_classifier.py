"""
Objection classification utility.

Maps raw objection strings from Shunya to standardized objection categories.
"""
from typing import List, Dict
from app.domain.enums import ObjectionType


class ObjectionClassifier:
    """
    Classifier for mapping raw objection strings to ObjectionType categories.

    This classifier uses keyword-based pattern matching to categorize objections
    from Shunya into one of 10 predefined categories. If no match is found,
    objections are classified as "other".
    """

    # Category → List of keywords/patterns mapping
    CLASSIFICATION_RULES: Dict[ObjectionType, List[str]] = {
        ObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY: [
            "immediate", "service unavailable", "not available",
            "can't serve", "don't service", "wait time", "backlog",
            "booked out", "no availability", "fully booked",
            "no capacity", "unavailable", "can't help right now",
            "not servicing", "too busy", "overbooked"
        ],
        ObjectionType.PHONE_CONNECTION_ISSUES: [
            "phone", "connection", "call quality", "hear you",
            "dropped call", "bad connection", "signal", "audio",
            "can't hear", "line breaking", "static", "breaking up",
            "poor quality", "cut out", "disconnected", "reception"
        ],
        ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE: [
            "think about", "need time", "consider", "decide later",
            "talk to", "consult", "discuss", "get back to you",
            "not ready", "call back", "follow up", "spouse",
            "partner", "family", "think it over", "sleep on it",
            "need to decide", "decision later"
        ],
        ObjectionType.SCHEDULING_CONFLICTS: [
            "schedule", "timing", "time conflict", "not available",
            "busy", "can't make it", "appointment conflict",
            "reschedule", "different time", "date doesn't work",
            "conflict", "availability", "time doesn't work",
            "booked", "another appointment", "can't do that time"
        ],
        ObjectionType.SERVICE_FEE_CONCERNS: [
            "price", "cost", "expensive", "too much", "pricing",
            "fee", "charge", "rate", "budget", "afford",
            "cheaper", "discount", "money", "payment",
            "high", "low price", "quote", "estimate cost",
            "financial", "costly"
        ],
        ObjectionType.IN_PERSON_ESTIMATES_ONLY: [
            "in person", "on-site", "come out", "visit",
            "see it", "look at it", "estimate in person",
            "physical inspection", "need to see", "in-person",
            "on site", "face to face", "physically", "inspect"
        ],
        ObjectionType.INEFFICIENT_AGENT_COMMUNICATION: [
            "agent", "representative", "unclear", "confusing",
            "don't understand", "explain better", "not helpful",
            "poor service", "unprofessional", "rude",
            "communication", "didn't listen", "not clear",
            "hard to understand", "CSR", "customer service",
            "rep", "operator"
        ],
        ObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS: [
            "privacy", "data", "personal information", "security",
            "share information", "confidential", "trust",
            "safe", "protect", "information security",
            "private", "secure", "data protection", "sensitive"
        ],
        ObjectionType.SERVICE_NOT_CATERED: [
            "don't offer", "not provide", "don't do", "outside scope",
            "not our service", "can't help with", "different service",
            "not catered", "don't handle", "not available for",
            "don't service", "not in our area", "outside area",
            "service area", "not covered", "don't work with",
            "outside your scope", "outside my scope", "outside the scope", "scope"
        ],
    }

    # Mapping from old objection types to new categories
    OLD_TO_NEW_MAPPING: Dict[str, List[ObjectionType]] = {
        "price": [ObjectionType.SERVICE_FEE_CONCERNS],
        "pricing": [ObjectionType.SERVICE_FEE_CONCERNS],
        "cost": [ObjectionType.SERVICE_FEE_CONCERNS],
        "costs": [ObjectionType.SERVICE_FEE_CONCERNS],

        "timing": [ObjectionType.SCHEDULING_CONFLICTS, ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE],
        "time": [ObjectionType.SCHEDULING_CONFLICTS, ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE],
        "schedule": [ObjectionType.SCHEDULING_CONFLICTS],
        "scheduling": [ObjectionType.SCHEDULING_CONFLICTS],

        "authority": [ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE],
        "decision": [ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE],

        "need": [ObjectionType.SERVICE_NOT_CATERED],
        "needs": [ObjectionType.SERVICE_NOT_CATERED],

        "competitor": [ObjectionType.OTHER],
        "competition": [ObjectionType.OTHER],

        "other": [ObjectionType.OTHER],
        "misc": [ObjectionType.OTHER],
        "miscellaneous": [ObjectionType.OTHER],
    }

    @classmethod
    def classify(cls, raw_objection: str) -> str:
        """
        Classify a raw objection string into a category.

        Args:
            raw_objection: Raw objection string from Shunya

        Returns:
            Classified objection category (string value from ObjectionType enum)
        """
        if not raw_objection or not isinstance(raw_objection, str):
            return ObjectionType.OTHER.value

        # Normalize: lowercase and strip
        normalized = raw_objection.lower().strip()

        # Try to match against each category's keywords
        for category, keywords in cls.CLASSIFICATION_RULES.items():
            for keyword in keywords:
                if keyword.lower() in normalized:
                    return category.value

        # No match found - classify as "other"
        return ObjectionType.OTHER.value

    @classmethod
    def classify_list(cls, raw_objections: List[str]) -> List[str]:
        """
        Classify a list of raw objection strings.

        Args:
            raw_objections: List of raw objection strings

        Returns:
            List of classified objection categories
        """
        if not raw_objections:
            return []

        return [cls.classify(obj) for obj in raw_objections]

    @classmethod
    def classify_and_deduplicate(cls, raw_objections: List[str]) -> List[str]:
        """
        Classify objections and remove duplicates while preserving order.

        If multiple raw objections map to the same category, only the first
        occurrence is kept.

        Args:
            raw_objections: List of raw objection strings

        Returns:
            List of unique classified objection categories
        """
        if not raw_objections:
            return []

        classified = cls.classify_list(raw_objections)

        # Deduplicate while preserving order
        seen = set()
        unique_classified = []
        for obj in classified:
            if obj not in seen:
                seen.add(obj)
                unique_classified.append(obj)

        return unique_classified

    @classmethod
    def expand_objection_filter(cls, objection: str) -> List[str]:
        """
        Expand an objection filter to include mapped new categories.

        If the input is an old objection type, returns the mapped new categories.
        If the input is a new category, returns it as-is.

        Args:
            objection: Objection type to expand (old or new)

        Returns:
            List of objection categories to filter by
        """
        if not objection:
            return []

        normalized = objection.lower().strip()

        # Check if it's an old objection type
        if normalized in cls.OLD_TO_NEW_MAPPING:
            return [cat.value for cat in cls.OLD_TO_NEW_MAPPING[normalized]]

        # Check if it's already a new category
        try:
            obj_type = ObjectionType(normalized)
            return [obj_type.value]
        except ValueError:
            # Not a valid enum value, return as-is for backward compatibility
            return [objection]
