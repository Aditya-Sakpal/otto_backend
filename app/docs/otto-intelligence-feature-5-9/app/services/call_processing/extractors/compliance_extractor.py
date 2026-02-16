"""
Compliance Extractor - Focused on SOP compliance and call evaluation.

Includes home services industry context for appropriate evaluation.
"""

from typing import Dict, Any, Optional
import json
from ....config import get_settings
from ....core.llm import get_llm_client, get_active_model
from .home_services_context import HOME_SERVICES_COMPLIANCE_CONTEXT
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class ComplianceExtractor:
    """Extracts compliance and SOP evaluation."""
    
    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.1  # Factual
    
    async def extract(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_compliance: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract compliance section.
        
        Args:
            chunk_text: Transcript text
            call_context: Context about the call (includes call_type_detection)
            previous_compliance: Previous compliance for merging
        
        Returns:
            Compliance section dictionary
        """
        # Refresh client/model
        self.model = get_active_model()
        self.client = get_llm_client()
        
        # Extract call type from context
        call_type = call_context.get('call_type_detection', {}).get('call_type', 'new_inquiry')
        
        if previous_compliance:
            prompt = self._build_merge_prompt(chunk_text, call_context, previous_compliance, call_type)
        else:
            prompt = self._build_initial_prompt(chunk_text, call_context, call_type)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert call quality analyst specializing in SOP compliance and representative performance evaluation. Always respond in valid JSON format."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Post-process: Validate issues and positive behaviors
            result = self._validate_compliance_output(result, chunk_text, call_type)
            
            # Add SOP version tracking (per Q1-Q9 SOP versioning)
            sop_info = call_context.get("sop_info", {})
            if sop_info:
                if "sop_compliance" in result:
                    result["sop_compliance"]["sop_version"] = sop_info.get("version")
                    result["sop_compliance"]["sop_version_history_id"] = sop_info.get("version_history_id")
            
            return result
            
        except Exception as e:
            logger.error(f"Compliance extraction failed: {e}")
            raise
    
    def _build_initial_prompt(self, chunk_text: str, call_context: Dict[str, Any], call_type: str = "new_inquiry") -> str:
        """Build prompt for initial extraction."""
        
        target_role = call_context.get("rep_role", "customer_rep")
        
        # Define expected stages based on call type
        if call_type == "confirmation":
            expected_stages_text = """
**CALL TYPE: CONFIRMATION**

For CONFIRMATION calls, evaluate these stages:
1. Greeting & Identification
2. Confirm Appointment Details
3. Answer Questions (if any)
4. Close Professionally

DO NOT evaluate or penalize for:
- Objection handling (none expected)
- Needs discovery (already done)
- Scheduling (already scheduled)
- Budget discussion (already qualified)
"""
        elif call_type == "follow_up":
            expected_stages_text = """
**CALL TYPE: FOLLOW-UP (Post-Sale)**

For FOLLOW-UP calls, evaluate these stages:
1. Greeting & Identification
2. Confirm Project Details
3. Set Expectations for Next Steps
4. Address Questions/Concerns
5. Close Professionally

DO NOT evaluate or penalize for:
- Objection handling (deal already won)
- Qualification (already qualified)
- Pricing discussion (already agreed)
"""
        elif call_type == "service_call":
            expected_stages_text = """
**CALL TYPE: SERVICE CALL**

For SERVICE CALL calls, evaluate these stages:
1. Greeting & Identification
2. Understand the Issue
3. Empathy & Acknowledgment
4. Propose Solution/Next Steps
5. Set Expectations
6. Close

DO NOT evaluate or penalize for:
- Sales techniques (this is service)
- Qualification (existing customer)
"""
        elif call_type == "quote_only":
            expected_stages_text = """
**CALL TYPE: QUOTE ONLY**

For QUOTE ONLY calls, evaluate these stages:
1. Greeting & Identification
2. Understand the Need
3. EDUCATE on need for in-person assessment
4. Handle objections about inspection
5. Attempt to schedule (if appropriate)
6. Close

CRITICAL: Rep should explain WHY an in-person visit is needed.
"""
        else:  # new_inquiry, fresh_sales, or default
            expected_stages_text = """
**CALL TYPE: NEW INQUIRY**

For NEW INQUIRY calls, evaluate these stages:
1. Greeting & Identification
2. Needs Discovery
3. Qualifying (BANT)
4. Scheduling (if applicable)
5. Setting Expectations
6. Objection Handling (if objections arose)
7. Close & Confirmation
"""
        
        return f"""Analyze this call transcript and extract the COMPLIANCE section.

{HOME_SERVICES_COMPLIANCE_CONTEXT}

**CALL CONTEXT:**
- Target Role: {target_role}
- Call Type: {call_type}

{expected_stages_text}

**TRANSCRIPT:**
{chunk_text}

Extract and generate JSON with this structure:

{{
  "target_role": "{target_role}",
  "evaluation_mode": "sop_only",
  "sop_compliance": {{
    "score": 0.9,
    "compliance_rate": 0.9,
    "stages": {{
      "total": 2,
      "followed": ["Intake", "Qualify"],
      "missed": []
    }},
    "issues": [
      "SPECIFIC compliance issues or missed steps (be concrete)"
    ],
    "positive_behaviors": [
      "SPECIFIC things the representative did well (with examples)",
      "Professional behaviors with context",
      "Effective techniques used with details"
    ],
    "confidence": 0.8
  }},
  "timestamps": {{}}
}}

**EVALUATION CRITERIA:**

1. **SOP Compliance Score (0.0 to 1.0):**
   - Did the rep follow standard operating procedures?
   - Were all required questions asked?
   - Was information gathered systematically?

2. **Issues - Be SPECIFIC:**
   ❌ BAD: "Did not ask about timeline"
   ✅ GOOD: "Failed to ask customer when they need the repair done (timeline qualification)"
   
   ❌ BAD: "Poor objection handling"
   ✅ GOOD: "When customer said 'sounds expensive', rep did not acknowledge concern or provide value justification"

3. **Positive Behaviors - Be SPECIFIC:**
   ❌ BAD: "Asked clarifying questions"
   ✅ GOOD: "Asked 'Is this for your main home or a rental property?' to understand decision authority"
   
   ❌ BAD: "Professional and courteous"
   ✅ GOOD: "Used customer's name (Marilyn) throughout call, creating personal connection"
   
   ❌ BAD: "Good objection handling"
   ✅ GOOD: "When customer hesitated about price, rep explained 25-year warranty value and financing options"

4. **Confidence (0.0 to 1.0):**
   How confident you are in this compliance evaluation.

**OUTPUT RULES:**
- Output ONLY valid JSON
- All scores must be 0.0 to 1.0
- stages.followed and stages.missed must be arrays
- issues and positive_behaviors must be arrays (can be empty)
- Make issues and positive_behaviors SPECIFIC with context

Generate the JSON now:"""
    
    def _build_merge_prompt(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_compliance: Dict[str, Any],
        call_type: str = "new_inquiry"
    ) -> str:
        """Build prompt for merging with previous compliance."""
        
        return f"""You previously extracted compliance information from the first part of this call.

**CALL TYPE: {call_type}**

**PREVIOUS COMPLIANCE:**
{json.dumps(previous_compliance, indent=2)}

**NEXT PART OF TRANSCRIPT:**
{chunk_text}

**MERGE RULES:**

1. **APPEND TO ARRAYS:**
   - sop_compliance.stages.followed: Add any NEW stages observed
   - sop_compliance.issues: Add any NEW issues identified
   - sop_compliance.positive_behaviors: Add any NEW positive behaviors

2. **UPDATE SCORES:**
   - score: Update based on overall performance across all chunks
   - compliance_rate: Recalculate based on stages followed vs missed
   - confidence: Weighted average

3. **PRESERVE:**
   - target_role and evaluation_mode must stay unchanged
   - All previous stages, issues, and behaviors must remain

4. **KEEP SPECIFIC:**
   - All issues and positive_behaviors should be specific with context
   - Avoid generic statements

Output the COMPLETE updated JSON:"""
    
    def _validate_compliance_output(
        self, 
        result: Dict[str, Any], 
        transcript: str,
        call_type: str
    ) -> Dict[str, Any]:
        """
        Validate and enhance compliance output.
        
        - Removes hallucinated issues (not in transcript)
        - Ensures positive behaviors are specific
        - Validates issues based on call type
        """
        sop_compliance = result.get('sop_compliance', {})
        
        # Validate issues against transcript
        issues = sop_compliance.get('issues', [])
        validated_issues = []
        transcript_lower = transcript.lower()
        
        for issue in issues:
            # Remove generic/vague issues
            if len(issue) < 20:
                logger.warning(f"Removed vague issue: {issue}")
                continue
            
            # Check for call-type inappropriate issues
            if call_type == "confirmation":
                # Don't penalize for missing qualification/objection handling
                if any(keyword in issue.lower() for keyword in ['qualify', 'objection', 'budget', 'timeline']):
                    logger.info(f"Removed inappropriate issue for confirmation call: {issue}")
                    continue
            
            if call_type == "follow_up":
                # Don't penalize for missing sales techniques
                if any(keyword in issue.lower() for keyword in ['qualify', 'objection', 'pricing', 'schedule']):
                    logger.info(f"Removed inappropriate issue for follow-up call: {issue}")
                    continue
            
            validated_issues.append(issue)
        
        sop_compliance['issues'] = validated_issues
        
        # Enhance positive behaviors if they're too generic
        positive_behaviors = sop_compliance.get('positive_behaviors', [])
        enhanced_behaviors = []
        
        for behavior in positive_behaviors:
            # Encourage specificity
            if len(behavior) < 20:
                logger.warning(f"Generic positive behavior (kept but flagged): {behavior}")
            enhanced_behaviors.append(behavior)
        
        sop_compliance['positive_behaviors'] = enhanced_behaviors
        
        result['sop_compliance'] = sop_compliance
        return result
    
    def generate_actionable_coaching(
        self,
        compliance_result: Dict[str, Any],
        transcript: str,
        call_type: str = "new_inquiry"
    ) -> Dict[str, Any]:
        """
        Generate actionable coaching feedback from compliance evaluation.
        
        Takes generic issues and positive behaviors and makes them specific,
        actionable, and contextual.
        
        Args:
            compliance_result: The compliance extraction result
            transcript: Full transcript for context
            call_type: Type of call for context-appropriate coaching
        
        Returns:
            Enhanced coaching with actionable recommendations
        """
        sop_compliance = compliance_result.get('sop_compliance', {})
        issues = sop_compliance.get('issues', [])
        positive_behaviors = sop_compliance.get('positive_behaviors', [])
        
        # Generate coaching recommendations
        coaching = {
            "strengths": [],
            "areas_for_improvement": [],
            "specific_actions": [],
            "examples_to_follow": []
        }
        
        # Convert positive behaviors to strengths with reinforcement
        for behavior in positive_behaviors:
            if len(behavior) < 30:
                # Too generic, skip or enhance
                continue
            
            coaching["strengths"].append({
                "behavior": behavior,
                "impact": self._explain_impact(behavior, "positive"),
                "reinforcement": f"Continue this approach - it {self._explain_why_good(behavior)}"
            })
        
        # Convert issues to actionable improvement areas
        for issue in issues:
            if len(issue) < 30:
                # Too generic, skip
                continue
            
            coaching["areas_for_improvement"].append({
                "issue": issue,
                "why_it_matters": self._explain_impact(issue, "negative"),
                "how_to_fix": self._generate_fix_suggestion(issue, call_type),
                "example_language": self._generate_example_language(issue)
            })
        
        return coaching
    
    def _explain_impact(self, behavior_or_issue: str, sentiment: str) -> str:
        """Explain why a behavior or issue matters."""
        lower = behavior_or_issue.lower()
        
        if sentiment == "positive":
            if "name" in lower:
                return "Personalizes the interaction and builds rapport"
            elif "empathy" in lower or "acknowledge" in lower:
                return "Makes customer feel heard and valued"
            elif "question" in lower or "clarify" in lower:
                return "Ensures accurate understanding and avoids mistakes"
            elif "value" in lower or "benefit" in lower:
                return "Helps customer see the return on investment"
            else:
                return "Contributes to positive customer experience"
        else:  # negative
            if "timeline" in lower:
                return "Without timeline, can't prioritize or schedule efficiently"
            elif "objection" in lower or "concern" in lower:
                return "Unaddressed concerns lead to lost sales"
            elif "budget" in lower or "price" in lower:
                return "Pricing uncertainty prevents booking decisions"
            elif "address" in lower:
                return "Incomplete address causes scheduling issues"
            else:
                return "May result in lost opportunity or customer frustration"
    
    def _explain_why_good(self, behavior: str) -> str:
        """Explain why a positive behavior is effective."""
        lower = behavior.lower()
        
        if "name" in lower:
            return "creates personal connection and trust"
        elif "empathy" in lower:
            return "demonstrates understanding and care"
        elif "question" in lower:
            return "shows engagement and professionalism"
        elif "value" in lower:
            return "helps customer see benefits beyond price"
        else:
            return "improves customer experience and trust"
    
    def _generate_fix_suggestion(self, issue: str, call_type: str) -> str:
        """Generate specific fix suggestion for an issue."""
        lower = issue.lower()
        
        if "timeline" in lower:
            if call_type == "new_inquiry":
                return "Ask: 'When are you looking to have this work done? Is there a specific deadline you're working with?'"
            else:
                return "Confirm expected timeline and set clear next-step dates"
        
        elif "objection" in lower or "concern" in lower:
            return "Use the ACE framework: Acknowledge the concern, Clarify with a question, Explain the value. Example: 'I understand price is important. What's your main concern about the investment? Let me explain...'"
        
        elif "budget" in lower or "price" in lower:
            return "Provide price range early and explain value: 'Most projects like this run $X-$Y. The price includes [warranty/quality/service]. We also offer financing options.'"
        
        elif "address" in lower:
            return "Always get full address spelled out: 'Can you spell that street name for me? And what's the ZIP code?'"
        
        elif "appointment" in lower or "schedule" in lower:
            return "Use assumptive close: 'I have openings Tuesday morning or Thursday afternoon. Which works better for you?'"
        
        else:
            return "Review training materials and practice with role-play scenarios"
    
    def _generate_example_language(self, issue: str) -> Optional[str]:
        """Generate example language for fixing an issue."""
        lower = issue.lower()
        
        if "timeline" in lower:
            return "When are you looking to get started? Are you working with any specific deadline?"
        
        elif "objection" in lower or "concern" in lower:
            return "I totally understand that concern. Can you tell me more about what's most important to you?"
        
        elif "budget" in lower or "price" in lower:
            return "Most projects like yours typically run between $X and $Y, depending on [specific factors]. Does that fit within your budget range?"
        
        elif "address" in lower:
            return "Let me make sure I have your address exactly right. Can you spell the street name for me?"
        
        else:
            return None


# Singleton instance
_compliance_extractor: Optional[ComplianceExtractor] = None


def get_compliance_extractor() -> ComplianceExtractor:
    """Get singleton compliance extractor instance."""
    global _compliance_extractor
    if _compliance_extractor is None:
        _compliance_extractor = ComplianceExtractor()
    return _compliance_extractor

