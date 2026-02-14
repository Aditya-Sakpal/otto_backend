"""
Unit tests for ObjectionClassifier.
"""
import pytest
from app.domain.objection_classifier import ObjectionClassifier
from app.domain.enums import ObjectionType


class TestObjectionClassifier:
    """Tests for ObjectionClassifier class."""

    def test_classify_immediate_service_unavailability(self):
        """Test classification of immediate service unavailability objections."""
        assert ObjectionClassifier.classify("Service not available right now") == \
            ObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY.value
        assert ObjectionClassifier.classify("We're fully booked") == \
            ObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY.value
        assert ObjectionClassifier.classify("No capacity available") == \
            ObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY.value
        assert ObjectionClassifier.classify("Can't serve you at this time") == \
            ObjectionType.IMMEDIATE_SERVICE_UNAVAILABILITY.value

    def test_classify_phone_connection_issues(self):
        """Test classification of phone connection issues objections."""
        assert ObjectionClassifier.classify("Can't hear you clearly") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value
        assert ObjectionClassifier.classify("Bad phone connection") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value
        assert ObjectionClassifier.classify("The call is breaking up") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value
        assert ObjectionClassifier.classify("Audio quality is poor") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value

    def test_classify_customer_needs_time_to_decide(self):
        """Test classification of customer needs time to decide objections."""
        assert ObjectionClassifier.classify("I need to think about it") == \
            ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value
        assert ObjectionClassifier.classify("Need to talk to my spouse") == \
            ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value
        assert ObjectionClassifier.classify("Can I get back to you later") == \
            ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value
        assert ObjectionClassifier.classify("Let me consult with my family") == \
            ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value

    def test_classify_scheduling_conflicts(self):
        """Test classification of scheduling conflicts objections."""
        assert ObjectionClassifier.classify("I have a schedule conflict") == \
            ObjectionType.SCHEDULING_CONFLICTS.value
        assert ObjectionClassifier.classify("That time doesn't work for me") == \
            ObjectionType.SCHEDULING_CONFLICTS.value
        assert ObjectionClassifier.classify("I'm busy at that time") == \
            ObjectionType.SCHEDULING_CONFLICTS.value
        assert ObjectionClassifier.classify("Need to reschedule") == \
            ObjectionType.SCHEDULING_CONFLICTS.value

    def test_classify_service_fee_concerns(self):
        """Test classification of service fee concerns objections."""
        assert ObjectionClassifier.classify("Too expensive") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value
        assert ObjectionClassifier.classify("Pricing is too high") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value
        assert ObjectionClassifier.classify("Can't afford it") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value
        assert ObjectionClassifier.classify("The cost is high") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value

    def test_classify_in_person_estimates_only(self):
        """Test classification of in-person estimates only objections."""
        assert ObjectionClassifier.classify("I need an in-person estimate") == \
            ObjectionType.IN_PERSON_ESTIMATES_ONLY.value
        assert ObjectionClassifier.classify("Can you come out to see it") == \
            ObjectionType.IN_PERSON_ESTIMATES_ONLY.value
        assert ObjectionClassifier.classify("Need on-site inspection") == \
            ObjectionType.IN_PERSON_ESTIMATES_ONLY.value
        assert ObjectionClassifier.classify("Have to look at it physically") == \
            ObjectionType.IN_PERSON_ESTIMATES_ONLY.value

    def test_classify_inefficient_agent_communication(self):
        """Test classification of inefficient agent communication objections."""
        assert ObjectionClassifier.classify("The agent is unclear") == \
            ObjectionType.INEFFICIENT_AGENT_COMMUNICATION.value
        assert ObjectionClassifier.classify("You're confusing me") == \
            ObjectionType.INEFFICIENT_AGENT_COMMUNICATION.value
        assert ObjectionClassifier.classify("The representative was rude") == \
            ObjectionType.INEFFICIENT_AGENT_COMMUNICATION.value
        assert ObjectionClassifier.classify("Poor customer service") == \
            ObjectionType.INEFFICIENT_AGENT_COMMUNICATION.value

    def test_classify_customer_data_privacy_concerns(self):
        """Test classification of customer data privacy concerns objections."""
        assert ObjectionClassifier.classify("I'm concerned about my privacy") == \
            ObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS.value
        assert ObjectionClassifier.classify("Is my personal information secure") == \
            ObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS.value
        assert ObjectionClassifier.classify("Data protection worries me") == \
            ObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS.value
        assert ObjectionClassifier.classify("Don't want to share confidential info") == \
            ObjectionType.CUSTOMER_DATA_PRIVACY_CONCERNS.value

    def test_classify_service_not_catered(self):
        """Test classification of service not catered objections."""
        assert ObjectionClassifier.classify("You don't offer this service") == \
            ObjectionType.SERVICE_NOT_CATERED.value
        assert ObjectionClassifier.classify("Not in your service area") == \
            ObjectionType.SERVICE_NOT_CATERED.value
        assert ObjectionClassifier.classify("You can't help with this") == \
            ObjectionType.SERVICE_NOT_CATERED.value
        assert ObjectionClassifier.classify("Outside your scope") == \
            ObjectionType.SERVICE_NOT_CATERED.value

    def test_classify_other(self):
        """Test classification of unmatched objections as 'other'."""
        assert ObjectionClassifier.classify("Random objection text that doesn't match") == \
            ObjectionType.OTHER.value
        assert ObjectionClassifier.classify("") == ObjectionType.OTHER.value
        assert ObjectionClassifier.classify(None) == ObjectionType.OTHER.value
        assert ObjectionClassifier.classify("   ") == ObjectionType.OTHER.value

    def test_classify_list(self):
        """Test bulk classification of objections."""
        raw = ["Too expensive", "Can't hear you", "Need time to think"]
        classified = ObjectionClassifier.classify_list(raw)

        assert len(classified) == 3
        assert ObjectionType.SERVICE_FEE_CONCERNS.value in classified
        assert ObjectionType.PHONE_CONNECTION_ISSUES.value in classified
        assert ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value in classified

    def test_classify_list_empty(self):
        """Test classification of empty list."""
        assert ObjectionClassifier.classify_list([]) == []
        assert ObjectionClassifier.classify_list(None) == []

    def test_classify_and_deduplicate(self):
        """Test classification with deduplication."""
        raw = ["Too expensive", "Pricing is high", "Can't hear you"]
        classified = ObjectionClassifier.classify_and_deduplicate(raw)

        # Both "Too expensive" and "Pricing is high" → service_fee_concerns
        # Should be deduplicated to 2 unique categories
        assert len(classified) == 2
        assert ObjectionType.SERVICE_FEE_CONCERNS.value in classified
        assert ObjectionType.PHONE_CONNECTION_ISSUES.value in classified

    def test_classify_and_deduplicate_preserves_order(self):
        """Test that deduplication preserves first occurrence order."""
        raw = ["Can't hear you", "Too expensive", "Bad connection", "High price"]
        classified = ObjectionClassifier.classify_and_deduplicate(raw)

        # Should have 2 unique categories in order: phone_connection_issues, service_fee_concerns
        assert len(classified) == 2
        assert classified[0] == ObjectionType.PHONE_CONNECTION_ISSUES.value
        assert classified[1] == ObjectionType.SERVICE_FEE_CONCERNS.value

    def test_expand_objection_filter_old_type_price(self):
        """Test expansion of old 'price' objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("price")
        assert ObjectionType.SERVICE_FEE_CONCERNS.value in expanded

    def test_expand_objection_filter_old_type_timing(self):
        """Test expansion of old 'timing' objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("timing")
        assert ObjectionType.SCHEDULING_CONFLICTS.value in expanded
        assert ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value in expanded

    def test_expand_objection_filter_old_type_authority(self):
        """Test expansion of old 'authority' objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("authority")
        assert ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value in expanded

    def test_expand_objection_filter_old_type_need(self):
        """Test expansion of old 'need' objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("need")
        assert ObjectionType.SERVICE_NOT_CATERED.value in expanded

    def test_expand_objection_filter_old_type_competitor(self):
        """Test expansion of old 'competitor' objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("competitor")
        assert ObjectionType.OTHER.value in expanded

    def test_expand_objection_filter_new_type(self):
        """Test expansion of new objection type returns itself."""
        expanded = ObjectionClassifier.expand_objection_filter("service_fee_concerns")
        assert len(expanded) == 1
        assert expanded[0] == ObjectionType.SERVICE_FEE_CONCERNS.value

    def test_expand_objection_filter_invalid_type(self):
        """Test expansion of invalid objection type."""
        expanded = ObjectionClassifier.expand_objection_filter("invalid_objection")
        assert len(expanded) == 1
        assert expanded[0] == "invalid_objection"

    def test_expand_objection_filter_empty(self):
        """Test expansion of empty/None objection."""
        assert ObjectionClassifier.expand_objection_filter("") == []
        assert ObjectionClassifier.expand_objection_filter(None) == []

    def test_case_insensitive_classification(self):
        """Test that classification is case-insensitive."""
        assert ObjectionClassifier.classify("TOO EXPENSIVE") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value
        assert ObjectionClassifier.classify("Can'T HeAr YoU") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value
        assert ObjectionClassifier.classify("NEED TIME TO THINK") == \
            ObjectionType.CUSTOMER_NEEDS_TIME_TO_DECIDE.value

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        assert ObjectionClassifier.classify("  Too expensive  ") == \
            ObjectionType.SERVICE_FEE_CONCERNS.value
        assert ObjectionClassifier.classify("\tCan't hear you\n") == \
            ObjectionType.PHONE_CONNECTION_ISSUES.value
