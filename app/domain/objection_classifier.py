"""
Objection classification utility.

Maps raw objection strings from Shunya to standardized objection categories.
"""
from typing import List, Dict, Optional, Tuple
from app.domain.enums import CSRObjectionType

# Alias kept for internal use
ObjectionType = CSRObjectionType


class ObjectionClassifier:
    """
    Classifier for mapping raw objection strings to CSRObjectionType categories.

    This classifier uses keyword-based pattern matching to categorize objections
    from Shunya into one of 15 predefined CSR categories. If no match is found,
    objections are classified as "other".
    """

    # Category → List of keywords/patterns mapping
    CLASSIFICATION_RULES: Dict[CSRObjectionType, List[str]] = {
        CSRObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY: [
            "immediate", "service unavailable", "not available",
            "can't serve", "don't service", "wait time", "backlog",
            "booked out", "no availability", "fully booked",
            "no capacity", "unavailable", "can't help right now",
            "not servicing", "too busy", "overbooked"
        ],
        CSRObjectionType.PHONE_CONNECTION_ISSUES: [
            "phone", "connection", "call quality", "hear you",
            "dropped call", "bad connection", "signal", "audio",
            "can't hear", "line breaking", "static", "breaking up",
            "poor quality", "cut out", "disconnected", "reception"
        ],
        CSRObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE: [
            "think about", "need time", "consider", "decide later",
            "talk to", "consult", "discuss", "get back to you",
            "not ready", "call back", "follow up", "spouse",
            "partner", "family", "think it over", "sleep on it",
            "need to decide", "decision later"
        ],
        CSRObjectionType.SCHEDULING_CONFLICTS: [
            "schedule", "timing", "time conflict", "not available",
            "busy", "can't make it", "appointment conflict",
            "reschedule", "different time", "date doesn't work",
            "conflict", "availability", "time doesn't work",
            "booked", "another appointment", "can't do that time"
        ],
        CSRObjectionType.SERVICE_FEE_CONCERNS: [
            "price", "cost", "expensive", "too much", "pricing",
            "fee", "charge", "rate", "budget", "afford",
            "cheaper", "discount", "money", "payment",
            "high", "low price", "quote", "estimate cost",
            "financial", "costly"
        ],
        CSRObjectionType.IN_PERSON_ESTIMATES_ONLY: [
            "in person", "on-site", "come out", "visit",
            "see it", "look at it", "estimate in person",
            "physical inspection", "need to see", "in-person",
            "on site", "face to face", "physically", "inspect"
        ],
        CSRObjectionType.INEFFICIENT_AGENT_COMMUNICATION: [
            "agent", "representative", "unclear", "confusing",
            "don't understand", "explain better", "not helpful",
            "poor service", "unprofessional", "rude",
            "communication", "didn't listen", "not clear",
            "hard to understand", "CSR", "customer service",
            "rep", "operator"
        ],
        CSRObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS: [
            "privacy", "data", "personal information", "security",
            "share information", "confidential", "trust",
            "safe", "protect", "information security",
            "private", "secure", "data protection", "sensitive"
        ],
        CSRObjectionType.INSURANCE_RELATED: [
            "insurance", "covered", "coverage", "claim", "deductible",
            "policy", "insured", "warranty", "home warranty", "liable",
            "liability", "underwriter", "adjuster", "insurer"
        ],
        CSRObjectionType.TRUST_CREDIBILITY_CONCERNS: [
            "trust", "credibility", "reliable", "reputation", "reviews",
            "legitimate", "scam", "verified", "licensed", "certified",
            "background check", "references", "proven", "experience",
            "credentials", "accredited", "bonded", "trustworthy"
        ],
        CSRObjectionType.NOT_THE_DECISION_MAKER: [
            "not my decision", "need to ask", "husband", "wife",
            "landlord", "property owner", "owner", "homeowner",
            "manager", "boss", "approval", "authorize", "permission",
            "not my house", "renting", "tenant", "someone else decides"
        ],
        CSRObjectionType.WORKMANSHIP_QUALITY_COMPLAINTS: [
            "quality", "workmanship", "poor job", "bad work",
            "not satisfied", "dissatisfied", "complaint", "defective",
            "broken", "damage", "worse", "not fixed", "still broken",
            "came back", "recurring", "same problem", "redo",
            "unsatisfied", "unhappy with work"
        ],
        CSRObjectionType.COMPETITOR_RELATED_CONCERNS: [
            "competitor", "competition", "other company", "another company",
            "going with someone else", "better deal elsewhere", "cheaper elsewhere",
            "got a quote from", "already have a provider", "using another",
            "switching to", "better offer", "competitor price"
        ],
        CSRObjectionType.SERVICE_NOT_CATERED: [
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

        "competitor": [CSRObjectionType.COMPETITOR_RELATED_CONCERNS],
        "competition": [CSRObjectionType.COMPETITOR_RELATED_CONCERNS],

        "other": [CSRObjectionType.OTHER],
        "misc": [CSRObjectionType.OTHER],
        "miscellaneous": [CSRObjectionType.OTHER],
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
            return CSRObjectionType.OTHER.value

        # Normalize: lowercase and strip
        normalized = raw_objection.lower().strip()

        # Try to match against each category's keywords
        for category, keywords in cls.CLASSIFICATION_RULES.items():
            for keyword in keywords:
                if keyword.lower() in normalized:
                    return category.value

        # No match found - classify as "other"
        return CSRObjectionType.OTHER.value

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
    def classify_with_raw(cls, raw_objection: str) -> Tuple[str, Optional[str]]:
        """
        Classify a raw objection and preserve the raw text when it falls into 'other'.

        Returns:
            Tuple of (classified_category, raw_text_or_none).
            raw_text is only set when the category is 'other'.
        """
        if not raw_objection or not isinstance(raw_objection, str):
            return (CSRObjectionType.OTHER.value, None)

        normalized = raw_objection.lower().strip()

        for category, keywords in cls.CLASSIFICATION_RULES.items():
            for keyword in keywords:
                if keyword.lower() in normalized:
                    return (category.value, None)

        # No match - "other" with raw text preserved
        return (CSRObjectionType.OTHER.value, raw_objection.strip())

    @classmethod
    def classify_and_deduplicate_with_raw(cls, raw_objections: List[str]) -> List[Tuple[str, Optional[str]]]:
        """
        Classify objections, deduplicate non-'other' categories,
        and preserve raw text for 'other' entries.

        Returns:
            List of (classified_category, raw_text_or_none) tuples.
            Non-'other' categories are deduplicated.
            'other' entries are all preserved with their raw text.
        """
        if not raw_objections:
            return []

        seen_categories = set()
        result = []
        for raw in raw_objections:
            category, raw_text = cls.classify_with_raw(raw)
            if category != CSRObjectionType.OTHER.value:
                if category not in seen_categories:
                    seen_categories.add(category)
                    result.append((category, None))
            else:
                result.append((category, raw_text))

        return result

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
