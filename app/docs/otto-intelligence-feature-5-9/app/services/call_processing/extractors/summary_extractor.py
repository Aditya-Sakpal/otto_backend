"""
Summary Extractor - Multi-Call Pipeline for Summary + Pending Action Extraction

Architecture:
- LLM Call 1: Summary fields (summary, key_points, action_items, next_steps, sentiment, confidence)
- LLM Call 2 (PA Stage 1): Intent Classification of candidate action statements
- LLM Call 3 (PA Stage 2): Revenue Impact Check on COMMITMENT/REQUEST candidates

Calls 1 and 2 run in parallel. Call 3 is sequential (depends on Call 2 output).
If no COMMITMENT/REQUEST candidates, Call 3 is skipped entirely.

Includes home services industry context for better extraction.
"""

from typing import Dict, Any, Optional, List
import json
import asyncio
from ....config import get_settings
from ....core.llm import get_llm_client, get_active_model
from .home_services_context import HOME_SERVICES_CONTEXT
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class SummaryExtractor:
    """Extracts summary, key_points, action_items, and pending_actions via 3-call pipeline."""

    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.1  # Factual

    async def extract(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_summary: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Extract summary section via 3 LLM calls.

        Call 1: Summary fields (parallel with Call 2)
        Call 2: PA Stage 1 — Intent Classification (parallel with Call 1)
        Call 3: PA Stage 2 — Revenue Impact Check (sequential after Call 2)

        Args:
            chunk_text: Transcript text
            call_context: Context about the call (date, timezone, etc.)
            previous_summary: Previous summary for merging (if multi-chunk)

        Returns:
            Combined dict: {summary, key_points, action_items, next_steps,
                           pending_actions, sentiment_score, confidence_score}
        """
        # Refresh model/client in case config changed
        self.client = get_llm_client()
        self.model = get_active_model()

        # --- Split previous_summary for merge prompts ---
        previous_summary_fields = None
        previous_pending_actions = []

        if previous_summary:
            previous_pending_actions = previous_summary.get("pending_actions", [])
            previous_summary_fields = {
                k: v for k, v in previous_summary.items()
                if k != "pending_actions"
            }

        # --- Build prompts ---
        if previous_summary_fields:
            summary_prompt = self._build_summary_merge_prompt(
                chunk_text, call_context, previous_summary_fields
            )
        else:
            summary_prompt = self._build_summary_prompt(chunk_text, call_context)

        if previous_pending_actions:
            pa_stage1_prompt = self._build_pa_stage1_merge_prompt(
                chunk_text, call_context, previous_pending_actions
            )
        else:
            pa_stage1_prompt = self._build_pa_stage1_prompt(chunk_text, call_context)

        # --- LLM Call 1 (Summary) + Call 2 (PA Stage 1) in parallel ---
        summary_task = self._llm_call(
            "You are an expert call analyst specializing in extracting narrative summaries, key points, and action items from conversations. Always respond in valid JSON format.",
            summary_prompt
        )
        pa_stage1_task = self._llm_call(
            "You are an expert call analyst specializing in identifying actionable commitments and requests from conversations. Always respond in valid JSON format.",
            pa_stage1_prompt
        )

        results = await asyncio.gather(summary_task, pa_stage1_task, return_exceptions=True)
        summary_result, stage1_result = results

        # Summary failure is fatal — re-raise for outer retry
        if isinstance(summary_result, Exception):
            logger.error(f"Summary extraction failed after retries: {summary_result}")
            raise summary_result

        # PA Stage 1 failure is non-fatal
        if isinstance(stage1_result, Exception):
            logger.warning(f"PA Stage 1 failed after retries, skipping pending actions: {stage1_result}")
            stage1_result = {"candidates": []}

        # --- Filter to COMMITMENT/REQUEST candidates only ---
        candidates = stage1_result.get("candidates", [])
        actionable = [c for c in candidates if c.get("intent") in ("COMMITMENT", "REQUEST")]
        logger.debug(f"PA Stage 1: {len(candidates)} candidates, {len(actionable)} actionable (COMMITMENT/REQUEST)")

        # --- LLM Call 3 (PA Stage 2) if actionable candidates exist ---
        final_pending_actions = []
        if actionable:
            try:
                stage2_prompt = self._build_pa_stage2_prompt(actionable, call_context)
                stage2_result = await self._llm_call(
                    "You are an expert call analyst specializing in evaluating business impact of action items. Always respond in valid JSON format.",
                    stage2_prompt
                )
                final_pending_actions = stage2_result.get("pending_actions", [])
                excluded = stage2_result.get("excluded", [])
                if excluded:
                    logger.debug(f"PA Stage 2: {len(final_pending_actions)} included, {len(excluded)} excluded")
            except Exception as e:
                logger.warning(f"PA Stage 2 failed after retries: {e}")
                final_pending_actions = []
        else:
            logger.debug("PA Stage 2: Skipped (no actionable candidates)")

        # --- Merge pending_actions across chunks (dedup by raw_text) ---
        if previous_pending_actions:
            seen = {a.get("raw_text", "").lower().strip() for a in previous_pending_actions}
            merged = list(previous_pending_actions)
            for pa in final_pending_actions:
                key = pa.get("raw_text", "").lower().strip()
                if key and key not in seen:
                    merged.append(pa)
                    seen.add(key)
            final_pending_actions = merged

        # --- Strip internal fields from pending_actions ---
        for pa in final_pending_actions:
            pa.pop("revenue_impact_reasoning", None)

        # --- Combine and return ---
        result = {**summary_result, "pending_actions": final_pending_actions}
        return result

    async def _llm_call(
        self, system_message: str, user_prompt: str, max_retries: int = 3
    ) -> Dict[str, Any]:
        """Make a single LLM call with retry logic. Returns parsed JSON dict."""
        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=self.temperature,
                    response_format={"type": "json_object"}
                )
                return json.loads(response.choices[0].message.content)
            except json.JSONDecodeError as e:
                logger.warning(f"LLM call JSON parse error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
            except Exception as e:
                logger.warning(f"LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                raise
        raise Exception(f"LLM call failed after {max_retries} attempts")

    # =========================================================================
    # SUMMARY PROMPTS (Call 1)
    # =========================================================================

    def _build_summary_prompt(self, chunk_text: str, call_context: Dict[str, Any]) -> str:
        """Build prompt for initial extraction of summary fields only (no pending_actions)."""

        call_date = call_context.get("call_date", "")
        call_time = call_context.get("call_time", "")
        timezone = call_context.get("timezone", "UTC")

        return f"""Analyze this call transcript and extract the SUMMARY section.

{HOME_SERVICES_CONTEXT}

**CALL CONTEXT:**
- Call Date: {call_date}
- Call Time: {call_time}
- Timezone: {timezone}

**TRANSCRIPT:**
{chunk_text}

Extract and generate JSON with this EXACT structure:

{{
  "summary": "A comprehensive paragraph summarizing the entire conversation, including customer needs, representative responses, and outcomes.",
  "key_points": [
    "First key point from the call",
    "Second key point from the call",
    "Third key point from the call"
  ],
  "action_items": [
    "Action item 1",
    "Action item 2"
  ],
  "next_steps": [
    "Next step 1",
    "Next step 2"
  ],
  "sentiment_score": 0.7,
  "confidence_score": 0.8
}}

**KEY POINTS CRITICAL RULES:**

⚠️⚠️⚠️ **ANTI-HALLUCINATION WARNING** ⚠️⚠️⚠️
1. ONLY include key points that are EXPLICITLY STATED in this transcript
2. DO NOT copy examples from this prompt - extract from the ACTUAL conversation
3. DO NOT include "willing to pay extra" unless customer LITERALLY said those words
4. DO NOT include "10-day inspection period" unless customer LITERALLY mentioned it
5. Each key point MUST be traceable to specific words in the transcript above

**WHAT TO INCLUDE IN KEY POINTS:**
- Customer's STATED problem: what issue are they calling about?
- Customer's STATED preferences: scheduling, communication, etc.
- Important details about the property/service discussed
- Outcome of the call: booked, not booked, follow-up needed

**WHAT TO EXCLUDE FROM KEY POINTS:**
❌ Generic statements not specific to THIS call
❌ Information not mentioned in the transcript
❌ Example phrases from this prompt (DO NOT COPY THEM!)

**CRITICAL INSTRUCTIONS:**

1. **DATE RESOLUTION (IMPORTANT):**
   Given call date of {call_date}:
   - "today" = {call_date}
   - "tomorrow" = {call_date} + 1 day
   - "next Monday" = the Monday following {call_date}
   - "next week" = {call_date} + 7 days
   - "in a few days" = {call_date} + 3 days (low confidence)
   - "end of month" = last day of current month
   - "ASAP" = {call_date} + 1 day

2. **SENTIMENT SCORE (0.0 to 1.0):**
   - 0.0-0.3: Very negative, angry, frustrated
   - 0.3-0.5: Somewhat negative, concerned
   - 0.5-0.7: Neutral to slightly positive
   - 0.7-0.9: Positive, satisfied
   - 0.9-1.0: Very positive, delighted

3. **CONFIDENCE SCORE (0.0 to 1.0):**
   How confident you are in the overall summary accuracy.

**OUTPUT RULES:**
- Output ONLY valid JSON matching the schema above
- Do NOT include pending_actions in this response (handled separately)
- All scores must be 0.0 to 1.0

Generate the JSON now:"""

    def _build_summary_merge_prompt(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_summary: Dict[str, Any]
    ) -> str:
        """Build prompt for merging summary fields across chunks (no pending_actions)."""

        call_date = call_context.get("call_date", "")

        return f"""You previously extracted summary information from the first part of this call.

**PREVIOUS SUMMARY:**
{json.dumps(previous_summary, indent=2)}

**CALL CONTEXT:**
- Call Date: {call_date}

**NEXT PART OF TRANSCRIPT:**
{chunk_text}

**MERGE RULES:**

1. **ARRAYS - APPEND, DON'T REPLACE:**
   - key_points: Add NEW points, keep ALL previous
   - action_items: Add NEW items, keep ALL previous
   - next_steps: Add NEW steps, keep ALL previous

2. **TEXT - EXPAND, DON'T CONDENSE:**
   - summary: Append new information to existing paragraph
   - Maintain chronological flow
   - Do NOT lose any details from previous summary

3. **SCORES - WEIGHTED AVERAGE:**
   - sentiment_score: Compute average weighted by chunk size
   - confidence_score: Update if new information affects confidence

4. **DATES:**
   - Continue using call date {call_date} for relative date resolution

**VERIFICATION CHECKLIST:**
- [ ] All previous key_points are included
- [ ] All previous action_items are included
- [ ] Summary paragraph includes previous + new information
- [ ] No information was lost

Output the COMPLETE updated JSON with fields: summary, key_points, action_items, next_steps, sentiment_score, confidence_score.
Do NOT include pending_actions (handled separately).

Output ONLY valid JSON:"""

    # =========================================================================
    # PENDING ACTIONS STAGE 1 PROMPTS (Call 2) — Intent Classification
    # =========================================================================

    def _build_pa_stage1_prompt(self, chunk_text: str, call_context: Dict[str, Any]) -> str:
        """
        PA Stage 1: Extract candidate action statements and classify intent.
        Casts a wide net — Stage 2 will filter for revenue impact.
        """
        call_date = call_context.get("call_date", "")
        call_time = call_context.get("call_time", "")
        timezone = call_context.get("timezone", "UTC")

        return f"""Analyze this call transcript and extract ALL statements where someone mentions doing something, committing to something, or requesting something.

{HOME_SERVICES_CONTEXT}

**CALL CONTEXT:**
- Call Date: {call_date}
- Call Time: {call_time}
- Timezone: {timezone}

**TRANSCRIPT:**
{chunk_text}

**YOUR TASK: INTENT CLASSIFICATION**

For EVERY statement in the transcript where someone mentions doing something,
classify its intent into one of these categories:

- **COMMITMENT** — Someone explicitly promises to do something ("I will call you tomorrow", "I'll send the estimate")
- **REQUEST** — Someone explicitly asks another to do something ("Can you send me photos?", "Please call me back")
- **PROCESS** — Describing how something works ("Someone will call you in 10 minutes", "You'll receive a confirmation email")
- **INFO** — Sharing information ("This usually takes 2 hours", "We tried calling you yesterday")
- **SOCIAL** — Pleasantries/greetings ("Have a great day", "Give me one second")

**CRITICAL: Cast a wide net.** Include anything that MIGHT be actionable.
A later stage will filter. It is better to include a borderline case than to miss a real commitment.

**EXTRACTION RULES:**
- Extract the EXACT text from the transcript (raw_text)
- Identify WHO said it (speaker: "rep" or "customer")
- Identify WHO is responsible for the action (owner)
- Classify the intent

**OWNER IDENTIFICATION RULES:**
- "I'll call you back" (said by rep) → owner: "customer_rep"
- "Can you send me photos?" (said by rep to customer) → owner: customer name or "customer"
- "I'll check my schedule" (said by customer) → owner: customer name or "customer"
- "Look for a roofing handyman" (rep recommends to customer) → owner: customer name or "customer"
- "manager", "company" → valid when representing clear organizational responsibility
- "someone", "team", "we", "they", "staff" WITHOUT a specific person → owner: "vague"

Output JSON with this EXACT structure:

{{
  "candidates": [
    {{
      "raw_text": "Exact text from transcript",
      "speaker": "rep or customer",
      "owner": "customer_rep, customer, customer name, manager, company, or vague",
      "intent": "COMMITMENT|REQUEST|PROCESS|INFO|SOCIAL",
      "reasoning": "Brief explanation of why this intent classification"
    }}
  ]
}}

Generate the JSON now:"""

    def _build_pa_stage1_merge_prompt(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_pending_actions: List[Dict[str, Any]]
    ) -> str:
        """
        PA Stage 1 for subsequent chunks: extract ONLY NEW candidates.
        Previous pending_actions provided as dedup context.
        """
        call_date = call_context.get("call_date", "")

        # Build concise dedup context from previous pending_actions
        prev_context = json.dumps(
            [{"raw_text": a.get("raw_text", ""), "type": a.get("type", "")} for a in previous_pending_actions[:10]],
            indent=2
        )

        return f"""You previously extracted action items from earlier parts of this call.

**PREVIOUSLY CAPTURED ACTIONS (for reference — do NOT re-extract these):**
{prev_context}

**CALL CONTEXT:**
- Call Date: {call_date}

**NEXT PART OF TRANSCRIPT:**
{chunk_text}

**YOUR TASK:** Extract NEW candidate action statements from this transcript segment ONLY.
Do NOT re-extract candidates that match previously captured actions.

Classify each candidate's intent:
- **COMMITMENT** — Explicit promise to do something
- **REQUEST** — Explicit ask for another to do something
- **PROCESS** — Describing how something works
- **INFO** — Sharing information
- **SOCIAL** — Pleasantries/greetings

**OWNER RULES:**
- "customer_rep" when rep committed to doing something
- Customer name or "customer" when customer must act
- "vague" for "someone", "team", "we", "they" without a specific person

Output JSON:

{{
  "candidates": [
    {{
      "raw_text": "Exact text from this transcript segment",
      "speaker": "rep or customer",
      "owner": "who is responsible",
      "intent": "COMMITMENT|REQUEST|PROCESS|INFO|SOCIAL",
      "reasoning": "Brief explanation"
    }}
  ]
}}

Output ONLY new candidates from this segment. Generate JSON now:"""

    # =========================================================================
    # PENDING ACTIONS STAGE 2 PROMPT (Call 3) — Revenue Impact Check
    # =========================================================================

    def _build_pa_stage2_prompt(
        self, candidates: List[Dict[str, Any]], call_context: Dict[str, Any]
    ) -> str:
        """
        PA Stage 2: Revenue impact check on COMMITMENT/REQUEST candidates.
        Formats passing candidates as final pending_actions.
        """
        call_date = call_context.get("call_date", "")
        timezone = call_context.get("timezone", "UTC")

        candidates_json = json.dumps(candidates, indent=2)

        return f"""You are given a list of candidate action items classified as COMMITMENT or REQUEST
from a home services call transcript.

**CALL CONTEXT:**
- Call Date: {call_date}
- Timezone: {timezone}

**CANDIDATES TO EVALUATE:**
{candidates_json}

**YOUR TASK: REVENUE IMPACT CHECK**

For EACH candidate, ask: "Would NOT completing this cost the company money or lose the customer?"

- If **YES** (revenue impact) → INCLUDE as a pending action
- If **NO** (no revenue impact) → EXCLUDE

**GUIDING PRINCIPLE:** A pending action is something that, if not done, costs money or loses the customer.
If you are unsure, do NOT include it. Fewer accurate tasks > noisy lists.

**INCLUDE examples (revenue impact):**
- "I will call you back tomorrow at 2pm" → follow-up = retention → INCLUDE
- "Can you send me photos of the damage?" → needed for estimate → INCLUDE
- "The technician will visit on Thursday" → service delivery → INCLUDE
- "Send me the estimate by email" → closing the sale → INCLUDE
- "I'll have my manager call you about the pricing" → escalation to close → INCLUDE

**EXCLUDE examples (no revenue impact):**
- "Give me one second" → immediate, not a pending task
- "We'll be in touch" → vague, no specific commitment
- "Thank you for calling" → pleasantry
- Actions with "vague" owner → no specific person responsible

**VAGUE OWNERS — EXCLUDE these:**
- If the candidate has owner "vague" (someone, team, we, they), EXCLUDE it
- Exception: "company" is valid when it represents a clear organizational responsibility

For each INCLUDED candidate, format as a pending action:

**VALID ACTION TYPES (use EXACTLY as shown):**
- call_back, follow_up_call, check_in
- send_quote, send_estimate, send_contract, send_info, send_photos, send_details
- schedule_appointment, schedule_visit, reschedule, confirm_appointment
- site_visit, inspection, measurement
- verify_insurance, verify_details, check_availability, confirm_address
- prepare_contract, collect_documents, send_invoice
- escalate, manager_review, get_approval
- setup_financing, process_payment, send_payment_link
- custom

**CRITICAL - DO NOT USE THESE (common mistakes):**
- "send_email", "email_customer" → use "send_info"
- "send_letter", "mail_document", "send_mail" → use "send_info"
- "call_customer", "callback" → use "call_back"
- "follow_up" → use "follow_up_call"
- "schedule", "book_appointment" → use "schedule_appointment"

**VALID CONTACT METHODS:** phone, email, sms, in_person, any

**CRITICAL - DO NOT USE THESE (common mistakes):**
- "mail" → use "email"
- "text" → use "sms"
- "call", "phone_call" → use "phone"
- "face-to-face", "in person" → use "in_person"

**DATE RESOLUTION:** Given call date of {call_date}:
- "today" = {call_date}
- "tomorrow" = {call_date} + 1 day
- "next Monday" = the Monday following {call_date}
- "next week" = {call_date} + 7 days
- "in a few days" = {call_date} + 3 days (low confidence)
- "end of month" = last day of current month
- "ASAP" = {call_date} + 1 day
- Specific date → ISO format: "2026-01-15T10:00:00"
- No date mentioned → "due_at": null

Output JSON with this EXACT structure:

{{
  "pending_actions": [
    {{
      "type": "call_back",
      "owner": "customer_rep",
      "due_at": "2026-01-16T14:00:00",
      "raw_text": "I will call you back tomorrow at 2pm",
      "confidence": 0.95,
      "contact_method": "phone",
      "revenue_impact_reasoning": "Follow-up call needed to retain customer interest"
    }}
  ],
  "excluded": [
    {{
      "raw_text": "We'll be in touch",
      "reason": "Vague, no specific commitment or timeline"
    }}
  ]
}}

Generate the JSON now:"""

    # =========================================================================
    # LEGACY METHODS — Commented out, kept for reference
    # These were the original single-call prompt builders, replaced by the
    # 3-call pipeline above (summary + PA Stage 1 + PA Stage 2).
    # =========================================================================

    # def _build_initial_prompt(self, chunk_text: str, call_context: Dict[str, Any]) -> str:
    #     """LEGACY: Build prompt for initial extraction (single LLM call for everything).
    #     Replaced by _build_summary_prompt + _build_pa_stage1_prompt + _build_pa_stage2_prompt."""
    #
    #     call_date = call_context.get("call_date", "")
    #     call_time = call_context.get("call_time", "")
    #     timezone = call_context.get("timezone", "UTC")
    #
    #     return f"""Analyze this call transcript and extract the SUMMARY section.
    #
    # {HOME_SERVICES_CONTEXT}
    #
    # **CALL CONTEXT:**
    # - Call Date: {call_date}
    # - Call Time: {call_time}
    # - Timezone: {timezone}
    #
    # **TRANSCRIPT:**
    # {chunk_text}
    #
    # Extract and generate JSON with this structure:
    #
    # {{{{
    #   "summary": "A comprehensive paragraph...",
    #   "key_points": ["..."],
    #   "action_items": ["..."],
    #   "next_steps": ["..."],
    #   "pending_actions": [{{{{ "type": "...", "owner": "...", ... }}}}],
    #   "sentiment_score": 0.7,
    #   "confidence_score": 0.8
    # }}}}
    #
    # ... (full prompt with action types, owner rules, etc.) ..."""

    # def _build_merge_prompt(
    #     self,
    #     chunk_text: str,
    #     call_context: Dict[str, Any],
    #     previous_summary: Dict[str, Any]
    # ) -> str:
    #     """LEGACY: Build prompt for merging with previous summary (single LLM call).
    #     Replaced by _build_summary_merge_prompt + programmatic pending_actions merge."""
    #
    #     call_date = call_context.get("call_date", "")
    #
    #     return f"""You previously extracted summary information from the first part of this call.
    #
    # **PREVIOUS SUMMARY:**
    # {json.dumps(previous_summary, indent=2)}
    #
    # **MERGE RULES:**
    # 1. ARRAYS - APPEND, DON'T REPLACE (key_points, action_items, next_steps, pending_actions)
    # 2. TEXT - EXPAND, DON'T CONDENSE (summary paragraph)
    # 3. SCORES - WEIGHTED AVERAGE (sentiment_score, confidence_score)
    #
    # Output the COMPLETE updated JSON:"""


# Singleton instance
_summary_extractor: Optional[SummaryExtractor] = None


def get_summary_extractor() -> SummaryExtractor:
    """Get singleton summary extractor instance."""
    global _summary_extractor
    if _summary_extractor is None:
        _summary_extractor = SummaryExtractor()
    return _summary_extractor
