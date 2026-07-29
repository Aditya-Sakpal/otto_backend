"""
Objection Extractor - Multi-Stage Pipeline for Objection Detection

Architecture:
- Stage 1: Extract raw customer statements (potential objections)
- Stage 2: Classify each statement as objection/non-objection
- Stage 3: LLM category re-mapping + sub_objection assignment
- Stage 4: Validate against transcript (programmatic - prevents hallucination)
- Stage 5: Calculate confidence scores (programmatic - ensures variability)
- Stage 6: Apply business logic filters
- Stage 7: LLM-based speaker validation (verifies speaker is customer)
- Stage 8: LLM-based semantic cross-validation (final quality check)
"""

from typing import Dict, Any, Optional, List, Tuple
import json
import re
from difflib import SequenceMatcher
from ....config import get_settings
from ....core.llm import get_llm_client, get_active_model
from ....models.enums import ObjectionCategory
import logging

logger = logging.getLogger(__name__)
settings = get_settings()


class ObjectionExtractor:
    """
    Multi-Stage Objection Extractor
    
    Solves common LLM issues:
    - Hallucination: Stage 3 validates against transcript
    - Static confidence: Stage 4 calculates based on evidence
    - Category errors: Stage 2 focuses only on classification
    - False positives: Multiple filtering stages
    """
    
    def __init__(self):
        self.model = get_active_model()
        self.client = get_llm_client()
        self.temperature = 0.2
        # Load objection categories dynamically from enum
        self.objection_categories = ObjectionCategory.get_category_mapping()
        self.category_descriptions = ObjectionCategory.get_category_descriptions()
    
    def _get_categories_prompt_text(self) -> str:
        """
        Generate dynamic category list for prompts from enum.
        
        Returns:
            Formatted string of categories with examples and warnings for use in prompts
        """
        lines = []
        for cat_id, details in self.category_descriptions.items():
            # Category header
            lines.append(f"**{cat_id} = {details['name']}**")
            
            # Description
            if details.get('description'):
                lines.append(f"- {details['description']}")
            
            # Examples
            if details.get('examples'):
                for example in details['examples']:
                    lines.append(f"- {example}")
            
            # Warnings
            if details.get('warnings'):
                for warning in details['warnings']:
                    lines.append(f"- {warning}")
            
            lines.append("")  # Empty line between categories
        
        return "\n".join(lines)
    
    async def extract(
        self,
        chunk_text: str,
        call_context: Dict[str, Any],
        previous_objections: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Multi-stage objection extraction pipeline.

        Stage 1: Extract candidate statements from customer
        Stage 2: Classify each as objection/non-objection with category
        Stage 3: LLM category re-mapping + sub_objection assignment
        Stage 4: Validate text exists in transcript (programmatic)
        Stage 5: Calculate confidence scores (programmatic)
        Stage 6: Apply business logic filters
        Stage 7: LLM-based speaker validation (verifies speaker is customer)
        Stage 8: LLM-based semantic cross-validation (final quality check)
        """
        try:
            # STAGE 1: Extract candidate customer statements
            candidates = await self._stage1_extract_candidates(chunk_text)
            logger.debug(f"Stage 1: Found {len(candidates)} candidate statements")

            if not candidates:
                return {"objections": [], "total_count": 0, "analysis_note": "No potential objections found in transcript"}

            # STAGE 2: Classify each candidate
            classified = await self._stage2_classify_candidates(candidates, chunk_text)
            logger.debug(f"Stage 2: Classified {len(classified)} candidates, {sum(1 for c in classified if c.get('is_objection'))} are objections")

            # STAGE 3: LLM category re-mapping (ensures correct categorization + sub_objection)
            classified = await self._stage3_remap_categories(classified, chunk_text)
            logger.debug(f"Stage 3: Category re-mapping complete for {sum(1 for c in classified if c.get('is_objection'))} objections")

            # STAGE 4: Validate against transcript (programmatic - prevents hallucination)
            validated = self._stage4_validate_against_transcript(classified, chunk_text)
            logger.debug(f"Stage 4: {len(validated)} objections passed validation")

            # STAGE 5: Calculate confidence scores (programmatic - ensures variability)
            scored = self._stage5_calculate_confidence(validated, chunk_text)
            logger.debug(f"Stage 5: Scored {len(scored)} objections")

            # STAGE 6: Apply business logic filters and format
            result = self._stage6_final_filters(scored, chunk_text)
            logger.debug(f"Stage 6: {result['total_count']} objections after business logic filters")

            # STAGE 7: LLM-based speaker validation
            if result.get("objections"):
                result = await self._stage7_validate_speakers(result, chunk_text)
                logger.debug(f"Stage 7: {result['total_count']} objections after speaker validation")

            # STAGE 8: LLM-based semantic cross-validation
            if result.get("objections"):
                result = await self._stage8_cross_validate_objections(result, chunk_text)
                logger.debug(f"Stage 8: {result['total_count']} objections after cross-validation")

            # POST-PIPELINE: Deduplicate semantically similar objections
            if result.get("objections"):
                result = self._deduplicate_objections(result)
                logger.debug(f"Dedup: {result['total_count']} objections after deduplication")

            # Handle previous objections merge if needed
            if previous_objections:
                result = self._merge_with_previous(result, previous_objections)

            logger.info(f"Objection extraction complete: {result['total_count']} objections found")
            return result

        except Exception as e:
            logger.error(f"Objection extraction failed: {e}")
            raise
    
    async def _stage1_extract_candidates(self, transcript: str) -> List[Dict[str, Any]]:
        """
        STAGE 1: Extract all customer statements that MIGHT be objections.
        
        Focus: Just extraction, no classification yet.
        """
        prompt = f"""Extract all CUSTOMER/HOME_OWNER statements that MIGHT express concern, resistance, or dissatisfaction.

**TRANSCRIPT:**
{transcript}

**RULES:**
1. ONLY extract statements from home_owner/customer (NOT customer_rep/agent)
2. Extract the EXACT text as it appears in the transcript
3. Include any statement that MIGHT be a concern - we'll filter later
4. Do NOT include: agreements, acknowledgments, questions asking for info, providing info

**OUTPUT FORMAT:**
Return your response in valid JSON format with this structure:
{{
  "candidates": [
    {{"text": "exact quote from customer", "context": "what was being discussed"}},
    {{"text": "exact quote from customer", "context": "what was being discussed"}}
  ]
}}

Extract now and return JSON:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You extract customer statements from transcripts. Extract EXACT quotes only. Always respond in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("candidates", [])
            
        except Exception as e:
            logger.error(f"Stage 1 extraction failed: {e}")
            return []
    
    async def _stage2_classify_candidates(self, candidates: List[Dict[str, Any]], transcript: str) -> List[Dict[str, Any]]:
        """
        STAGE 2: Classify each candidate as objection or non-objection.
        
        Focus: Classification and categorization only.
        """
        if not candidates:
            return []
        
        candidates_text = "\n".join([f"{i+1}. \"{c.get('text', '')}\" (context: {c.get('context', 'unknown')})" 
                                      for i, c in enumerate(candidates)])
        
        # Generate category list dynamically from enum
        categories_text = self._get_categories_prompt_text()
        
        prompt = f"""For each customer statement, determine if it's a GENUINE OBJECTION or NOT.

**CANDIDATES:**
{candidates_text}

**CLASSIFICATION RULES:**

**IS an objection:**
- Customer expresses frustration/disappointment with service
- Customer says they can't or won't do something
- Customer pushes back on price, time, policy
- Customer complains about wait times or communication

**NOT an objection:**
- Customer agrees to something ("That works", "Sounds good", "Perfect")
- Customer asks a clarifying question ("Next 4 weeks, right?")
- Customer provides information ("My name is...", "The address is...")
- Customer offers to accommodate ("I can reschedule", "We'll postpone our vacation")
- Customer acknowledges a situation without complaint

**CATEGORIES (only if is_objection=true):**

{categories_text}

**OUTPUT:**
{{
  "classifications": [
    {{
      "original_text": "exact text",
      "is_objection": true/false,
      "reasoning": "why this is/isn't an objection",
      "category_id": <1-10>,
      "category_text": "Exact category name from list above",
      "severity": "low/medium/high"
    }}
  ]
}}

Classify each candidate:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You classify customer statements as objections or non-objections with reasoning. Always respond in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("classifications", [])
            
        except Exception as e:
            logger.error(f"Stage 2 classification failed: {e}")
            return []

    async def _stage3_remap_categories(self, classified: List[Dict[str, Any]], transcript: str) -> List[Dict[str, Any]]:
        """
        STAGE 3: LLM-based category re-mapping and sub_objection assignment.

        Validates that each objection is mapped to the most specific category
        from the 9 defined categories (IDs 1-8, 10). Objections that don't fit
        any specific category are assigned to "Other" (ID 9) with a descriptive
        sub_objection label.
        """
        # Filter to only objections that need re-mapping
        objection_items = [c for c in classified if c.get("is_objection")]
        if not objection_items:
            return classified

        # Build the objections list for the prompt
        objections_text = "\n".join([
            f"{i+1}. \"{item.get('original_text', '')}\" → Current: category_id={item.get('category_id', 9)}, \"{item.get('category_text', 'Unknown')}\""
            for i, item in enumerate(objection_items)
        ])

        # Build the specific categories text (exclude "Other" / ID 9)
        specific_categories = []
        for cat_id, details in self.category_descriptions.items():
            if cat_id == 9:  # Skip "Other" — we want to push LLM toward specific categories
                continue
            line = f"{cat_id} = {details['name']}: {details.get('description', '')}"
            if details.get('examples'):
                line += f" (e.g., {', '.join(details['examples'][:2])})"
            specific_categories.append(line)
        categories_text = "\n".join(specific_categories)

        prompt = f"""Review these objection classifications and ensure each is mapped to the MOST SPECIFIC category possible.

**OBJECTIONS TO REVIEW:**
{objections_text}

**SPECIFIC CATEGORIES (use these FIRST - try to fit each objection into one of these):**
{categories_text}

**RULES:**
1. For each objection, determine if it fits one of the 9 specific categories listed above.
2. If it fits a specific category, set that category_id and use the EXACT category name as category_text.
3. ONLY if an objection truly does NOT match ANY of the 9 specific categories above, set category_id=9, category_text="Other", and provide a short sub_objection label describing the specific type (e.g., "Insurance denial concern", "Process fatigue", "Warranty dispute").
4. Do NOT change the original_text, severity, or is_objection fields.
5. The sub_objection field should be null for all specific categories (1-8, 10) and only populated when category_id=9.

**OUTPUT FORMAT (JSON only):**
{{
  "remapped": [
    {{
      "index": 1,
      "category_id": <1-10>,
      "category_text": "exact category name",
      "sub_objection": null or "short descriptive label"
    }}
  ]
}}

Review and remap now:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You validate and correct objection category classifications. Prefer specific categories over 'Other'. Always respond in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            remapped_list = result.get("remapped", [])

            # Apply re-mapping results to the objection items
            for remap in remapped_list:
                idx = remap.get("index", 1) - 1
                if 0 <= idx < len(objection_items):
                    item = objection_items[idx]
                    new_cat_id = remap.get("category_id", item.get("category_id", 9))
                    new_cat_text = remap.get("category_text", item.get("category_text", "Other"))
                    sub_objection = remap.get("sub_objection")

                    # Validate category_id is in valid range
                    if new_cat_id not in self.objection_categories:
                        logger.warning(f"Stage 3: Invalid remapped category_id {new_cat_id}, keeping original")
                        continue

                    # Ensure sub_objection is only set for "Other" (category 9)
                    if new_cat_id != 9:
                        sub_objection = None
                    elif new_cat_id == 9 and not sub_objection:
                        # LLM failed to provide sub_objection for "Other" — derive from reasoning or context
                        sub_objection = item.get("reasoning", "").strip()
                        if not sub_objection or len(sub_objection) > 60:
                            sub_objection = item.get("context", "").strip()
                        if not sub_objection or len(sub_objection) > 60:
                            # Last resort: truncate objection text to a short label
                            obj_text = item.get("original_text", "")[:80].strip()
                            sub_objection = f"Uncategorized: {obj_text[:50]}" if obj_text else "Uncategorized concern"
                        logger.info(f"Stage 3: Derived sub_objection for Other: '{sub_objection}'")

                    # Apply the re-mapping
                    old_cat = item.get("category_text", "Unknown")
                    item["category_id"] = new_cat_id
                    item["category_text"] = self.objection_categories.get(new_cat_id, new_cat_text)
                    item["sub_objection"] = sub_objection

                    if old_cat != item["category_text"]:
                        logger.info(f"Stage 3: Re-mapped '{old_cat}' -> '{item['category_text']}'" +
                                   (f" (sub: {sub_objection})" if sub_objection else ""))

            return classified

        except Exception as e:
            logger.error(f"Stage 3 category re-mapping failed: {e}")
            # Return original classified data on error
            return classified

    def _stage4_validate_against_transcript(self, classified: List[Dict[str, Any]], transcript: str) -> List[Dict[str, Any]]:
        """
        STAGE 4: Validate each objection exists in the transcript (PROGRAMMATIC).
        
        This prevents hallucination - if the text isn't in the transcript, it's rejected.
        """
        transcript_lower = transcript.lower()
        validated = []
        
        for item in classified:
            if not item.get("is_objection"):
                continue
            
            text = item.get("original_text", "")
            if not text:
                continue
            
            text_lower = text.lower()
            
            # Check if text exists in transcript (fuzzy match)
            match_score = self._calculate_text_match(text_lower, transcript_lower)
            
            if match_score >= 0.6:  # At least 60% match required
                item["text_match_score"] = match_score
                validated.append(item)
            else:
                logger.debug(f"Stage 3: Rejected (text not found, score={match_score:.2f}): {text[:50]}")
        
        return validated
    
    def _calculate_text_match(self, text: str, transcript: str) -> float:
        """Calculate how well the text matches the transcript."""
        # Clean both texts
        text_clean = re.sub(r'[^\w\s]', '', text.lower()).strip()
        transcript_clean = re.sub(r'[^\w\s]', '', transcript.lower())
        
        # Direct substring match
        if text_clean in transcript_clean:
            return 1.0
        
        # Word overlap match
        text_words = set(text_clean.split())
        significant_words = [w for w in text_words if len(w) > 3]
        
        if not significant_words:
            return 0.0
        
        found_words = sum(1 for w in significant_words if w in transcript_clean)
        return found_words / len(significant_words)
    
    def _stage5_calculate_confidence(self, validated: List[Dict[str, Any]], transcript: str) -> List[Dict[str, Any]]:
        """
        STAGE 5: Calculate confidence scores PROGRAMMATICALLY (not LLM).
        
        This ensures scores vary based on actual evidence, not LLM defaults.
        """
        scored = []
        
        for item in validated:
            # Base confidence from text match
            text_match = item.get("text_match_score", 0.5)
            
            # Reasoning quality bonus (if reasoning is detailed)
            reasoning = item.get("reasoning", "")
            reasoning_bonus = min(0.1, len(reasoning) / 500)  # Up to 0.1 for detailed reasoning
            
            # Severity adjustment
            severity = item.get("severity", "medium")
            severity_map = {"high": 0.1, "medium": 0.0, "low": -0.1}
            severity_adj = severity_map.get(severity, 0.0)
            
            # Category clarity (some categories are clearer than others)
            category_id = item.get("category_id", 9)
            category_clarity = {
                5: 0.05,  # Price concerns usually clear
                7: 0.05,  # Communication issues clear
                4: 0.0,   # Scheduling can be ambiguous
                1: 0.0,   # Service unavailability
                9: -0.1   # "Other" = less certain
            }
            clarity_adj = category_clarity.get(category_id, 0.0)
            
            # Calculate final confidence (0.5 to 0.95 range)
            raw_confidence = 0.6 + (text_match * 0.2) + reasoning_bonus + severity_adj + clarity_adj
            confidence = max(0.5, min(0.95, raw_confidence))
            
            # Round to 2 decimals for variety
            confidence = round(confidence, 2)
            
            item["confidence_score"] = confidence
            scored.append(item)
        
        return scored
    
    def _stage6_final_filters(self, scored: List[Dict[str, Any]], transcript: str) -> Dict[str, Any]:
        """
        STAGE 6: Apply final business logic filters and format output.
        """
        final_objections = []
        
        for item in scored:
            text = item.get("original_text", "")
            text_lower = text.lower()
            
            # FILTER: Accommodation/cooperation statements
            accommodation_patterns = [
                "i can reschedule", "we can reschedule", "i'll reschedule",
                "we'll postpone", "we might postpone", "postpone it until",
                "until after", "until this is completed", "until it's done",
                "just to be safe", "to be safe", "we can wait", "i can wait"
            ]
            if any(p in text_lower for p in accommodation_patterns):
                logger.debug(f"Stage 6: Filtered accommodation: {text[:50]}")
                continue
            
            # FILTER: Clarifying questions
            if text.strip().endswith("?") and any(p in text_lower for p in ["right?", "correct?", "you said"]):
                logger.debug(f"Stage 6: Filtered clarifying question: {text[:50]}")
                continue
            
            # FILTER: Too short
            if len(text.split()) <= 3:
                logger.debug(f"Stage 6: Filtered too short: {text}")
                continue
            
            # VALIDATE: Category ID must be 1-10
            category_id = item.get("category_id", 9)
            if category_id not in self.objection_categories:
                logger.warning(f"Invalid category_id {category_id}, defaulting to 9 (Other)")
                category_id = 9
            
            # VALIDATE: Category text must match enum
            category_text = item.get("category_text", "")
            expected_category_text = self.objection_categories.get(category_id, "Other")
            
            # Get sub_objection (only relevant for category_id=9 "Other")
            sub_objection = item.get("sub_objection", None)
            if category_id != 9:
                sub_objection = None

            # Normalize category text to match enum (handle LLM variations)
            if category_text != expected_category_text:
                # For category_id=9 "Other": if the LLM gave a descriptive name and
                # sub_objection wasn't set by Stage 3, preserve it as sub_objection
                if category_id == 9 and not sub_objection and category_text:
                    sub_objection = category_text
                    logger.info(f"Stage 6: Preserving non-canonical category_text '{category_text}' as sub_objection for Other")
                logger.info(f"Correcting category_text from '{category_text}' to '{expected_category_text}' for category_id {category_id}")
                category_text = expected_category_text

            # Final safety net: category_id=9 must always have a sub_objection
            if category_id == 9 and not sub_objection:
                reasoning = item.get("reasoning", "").strip()
                if reasoning and len(reasoning) <= 60:
                    sub_objection = reasoning
                else:
                    sub_objection = f"Uncategorized: {text[:50]}" if text else "Uncategorized concern"
                logger.info(f"Stage 6: Safety net sub_objection for Other: '{sub_objection}'")

            # Format for output
            objection = {
                "category_id": category_id,
                "category_text": category_text,
                "sub_objection": sub_objection,
                "objection_text": text,
                "overcome": False,
                "speaker_id": "home_owner",
                "timestamp": None,
                "confidence_score": item.get("confidence_score", 0.7),
                "severity": item.get("severity", "medium"),
                "response_suggestions": []
            }
            
            final_objections.append(objection)
        
        return {
            "objections": final_objections,
            "total_count": len(final_objections),
            "analysis_note": f"Multi-stage extraction: {len(final_objections)} objections validated"
        }
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate Jaccard word-overlap similarity between two texts.
        Returns a float between 0.0 and 1.0.
        """
        if not text1 or not text2:
            return 0.0
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        if not words1 or not words2:
            return 0.0
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        return len(intersection) / len(union) if union else 0.0

    def _deduplicate_objections(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove semantically duplicate objections within a single extraction result.

        Uses two similarity measures:
        1. SequenceMatcher (character-level)
        2. Jaccard word overlap

        If either score >= 0.5 (boosted by same category), keeps the higher-confidence objection.
        """
        objections = result.get("objections", [])
        if len(objections) <= 1:
            return result

        # Track which indices to keep
        removed = set()

        for i in range(len(objections)):
            if i in removed:
                continue
            for j in range(i + 1, len(objections)):
                if j in removed:
                    continue

                text_a = objections[i].get("objection_text", "").lower().strip()
                text_b = objections[j].get("objection_text", "").lower().strip()

                # Character-level similarity
                seq_sim = SequenceMatcher(None, text_a, text_b).ratio()
                # Word-level Jaccard similarity
                jaccard_sim = self._text_similarity(text_a, text_b)

                # Boost similarity if same category (same concern more likely)
                same_category = objections[i].get("category_id") == objections[j].get("category_id")
                boost = 0.1 if same_category else 0.0

                threshold = 0.5
                if (seq_sim + boost) >= threshold or (jaccard_sim + boost) >= threshold:
                    # Duplicate found — remove the one with lower confidence
                    conf_i = objections[i].get("confidence_score", 0.0)
                    conf_j = objections[j].get("confidence_score", 0.0)
                    loser = j if conf_i >= conf_j else i
                    logger.info(
                        f"Dedup: Removing objection '{objections[loser].get('objection_text', '')[:60]}' "
                        f"(seq={seq_sim:.2f}, jaccard={jaccard_sim:.2f}, same_cat={same_category})"
                    )
                    removed.add(loser)
                    # If i was removed, stop comparing it
                    if loser == i:
                        break

        kept = [obj for idx, obj in enumerate(objections) if idx not in removed]
        result["objections"] = kept
        result["total_count"] = len(kept)
        if removed:
            result["analysis_note"] = f"{len(kept)} objections after dedup (removed {len(removed)} duplicates)"
        return result

    def _merge_with_previous(self, new_result: Dict[str, Any], previous: Dict[str, Any]) -> Dict[str, Any]:
        """Merge new objections with previous chunk results using fuzzy matching."""
        prev_objections = previous.get("objections", [])
        new_objections = new_result.get("objections", [])

        for obj in new_objections:
            obj_text = obj.get("objection_text", "").lower().strip()
            if not obj_text:
                continue

            # Check fuzzy similarity against all existing objections
            is_duplicate = False
            for prev_obj in prev_objections:
                prev_text = prev_obj.get("objection_text", "").lower().strip()
                seq_sim = SequenceMatcher(None, obj_text, prev_text).ratio()
                jaccard_sim = self._text_similarity(obj_text, prev_text)
                if seq_sim >= 0.5 or jaccard_sim >= 0.5:
                    logger.info(
                        f"Cross-chunk dedup: Skipping '{obj_text[:60]}' "
                        f"(matches '{prev_text[:60]}', seq={seq_sim:.2f}, jaccard={jaccard_sim:.2f})"
                    )
                    is_duplicate = True
                    break

            if not is_duplicate:
                prev_objections.append(obj)

        return {
            "objections": prev_objections,
            "total_count": len(prev_objections),
            "analysis_note": f"Merged: {len(prev_objections)} total objections"
        }
    
    # ============================================================================
    # LEGACY CODE - NOT USED (Multi-stage pipeline is used instead)
    # ============================================================================
    # The following methods were part of an older single-stage extraction approach.
    # They are kept for reference but are NOT called by the current 8-stage pipeline.
    # Current flow: Stage1 → Stage2 → Stage3 → Stage4 → Stage5 → Stage6 → Stage7 → Stage8
    # ============================================================================
    
    # def _build_initial_prompt(self, chunk_text: str, call_context: Dict[str, Any]) -> str:
    #     """LEGACY: Build prompt for initial extraction."""
    #     
    #     # Generate category list dynamically from enum
    #     categories_text = self._get_categories_prompt_text()
    #     
    #     return f"""Analyze this call transcript and identify ONLY GENUINE customer objections.
# 
# **TRANSCRIPT:**
# {chunk_text}
# 
# ⚠️⚠️⚠️ **CRITICAL - READ CAREFULLY BEFORE RESPONDING** ⚠️⚠️⚠️
# 
# **ANTI-HALLUCINATION RULES:**
# 1. ONLY output objections that EXIST WORD-FOR-WORD in the transcript above
# 2. DO NOT invent, create, or imagine objections
# 3. DO NOT output example phrases from this prompt as actual objections
# 4. If you cannot find the EXACT TEXT in the transcript, DO NOT include it
# 5. Most calls have ZERO objections - that is normal and expected!
# 
# **WHAT IS NOT AN OBJECTION (NEVER include these):**
# 
# ❌ **Scheduling/Agreeing to dates:**
# - "Let's do Wednesday" = AGREEMENT, not objection
# - "That works for me" = AGREEMENT
# - "Tuesday the 26th. Okay, sure" = AGREEMENT
# - Choosing a date from options = AGREEMENT
# 
# ❌ **Clarifying Questions (asking for information):**
# - "How does payment work?" = QUESTION, not objection
# - "When is the walkthrough?" = QUESTION
# - "What time do they arrive?" = QUESTION
# - "Do I pay by check or online?" = QUESTION
# - "Next 4 weeks, right?" = CONFIRMING information, not objection
# - "You said 4 to 6?" = CLARIFYING, not objection
# 
# ❌ **Providing Information/Context:**
# - "My PO box is 1687" = INFORMATION
# - "The address is..." = INFORMATION
# - "My email is..." = INFORMATION
# - Explaining mail delivery situation = INFORMATION
# - "I don't know if it needs repairs or not" = providing CONTEXT, not objecting
# - "It's a rental, my mother owns it" = EXPLAINING SITUATION
# 
# ❌ **Acknowledgments:**
# - "Okay", "Yes", "Sure", "Alright", "Perfect"
# - "Sounds good", "That works", "Awesome"
# - "Thank you", "I appreciate it"
# 
# ❌ **COOPERATION/ACCOMMODATION (customer helping YOU):**
# - "We'll postpone our vacation until after" = COOPERATING with your schedule
# - "I can work around that" = ACCOMMODATING
# - "We can wait" = ACCEPTING
# - "That's fine, we'll make it work" = AGREEING
# 
# ❌ **Agent Statements:**
# - ANYTHING said by customer_rep/agent is NOT an objection
# - Only CUSTOMER (home_owner) can have objections
# 
# **WHAT IS A GENUINE OBJECTION (only include if clearly present):**
# 
# ✅ **Price/Fee Resistance:**
# - "That's too expensive"
# - "I can't afford that"
# - "Why is there a dispatch fee?"
# - Customer pushes back on cost
# - ❌ NOT: "I'm willing to pay extra" = WILLINGNESS, not objection
# 
# ✅ **Refusing/Declining:**
# - "No, I don't want that"
# - "I'm not interested"
# - "That won't work for me" (with resistance, not just logistics)
# 
# ✅ **Actual Scheduling Conflict (with resistance):**
# - "I work during those hours and can't make it" (expressing inability, not just asking)
# - "None of those times work for my schedule"
# 
# ✅ **Decision Delay (with clear hesitation):**
# - "I need to think about it" (said as pushing back, not just acknowledging)
# - "Let me talk to my spouse first" (delaying decision)
# 
# ✅ **Privacy Concerns (actual concern, not logistics):**
# - "Why do you need my social security number?"
# - "I don't want to give that information"
# 
# ✅ **Service Unavailability (when customer expresses disappointment):**
# - "You can't come until next month? That's too long"
# - "You don't service my area? I really need help"
# - ❌ NOT: "You're the 20th person I've called" = acknowledgment of situation
# - ❌ NOT: Acknowledging everyone is busy = just understanding, not objecting
# 
# **CRITICAL CONTEXT RULES:**
# ⚠️ **WILLINGNESS vs OBJECTION:**
# - "I'm willing to pay" = NOT an objection (shows budget availability)
# - "That's too expensive" = objection (shows price resistance)
# 
# ⚠️ **ACKNOWLEDGMENT vs OBJECTION:**
# - "I'm well aware of that" = acknowledging situation, NOT objecting
# - "You're the 20th person I've called" = expressing frustration about market, NOT objecting to YOU
# - Customer understanding your limitation = NOT an objection
# 
# ⚠️ **FRUSTRATION ABOUT SITUATION vs OBJECTION TO SERVICE:**
# - Frustrated about industry/market = NOT an objection to your company
# - "No one will come out" = describing problem, not objecting to your offer
# 
# **OUTPUT FORMAT:**
# 
# {{
#   "objections": [],
#   "total_count": 0,
#   "analysis_note": "No genuine objections found - customer agreed to scheduling and provided requested information"
# }}
# 
# OR if genuine objection found:
# 
# {{
#   "objections": [
#     {{
#       "category_id": 5,
#       "category_text": "{self.objection_categories[5]}",
#       "objection_text": "[EXACT quote from transcript]",
#       "overcome": true,
#       "speaker_id": "home_owner",
#       "timestamp": null,
#       "confidence_score": 0.85,
#       "severity": "medium",
#       "response_suggestions": []
#     }}
#   ],
#   "total_count": 1
# }}
# 
# **OBJECTION CATEGORIES (1-10) - USE CORRECT CATEGORY:**
# 
# {categories_text}
# 
# **CONFIDENCE SCORING:**
# - 0.9-1.0: Crystal clear objection ("That's way too expensive!")
# - 0.7-0.89: Clear objection ("I'm not sure about that")
# - 0.5-0.69: Possible mild concern
# - Below 0.5: SKIP
# 
# **FINAL CHECK BEFORE OUTPUT:**
# ☐ Is each objection_text an EXACT quote from the transcript?
# ☐ Is each objection from the CUSTOMER (not agent)?
# ☐ Is it expressing RESISTANCE (not just asking a question)?
# ☐ Is it NOT just agreeing to a date/time?
# ☐ Is it NOT just providing requested information?
# ☐ Would a reasonable person call this an "objection"?
# 
# If ANY answer is NO, do not include that objection.
# 
# Generate JSON now:
# 
# **OUTPUT RULES:**
# - Output ONLY valid JSON
# - category_id must be integer 1-10
# - speaker_id must be exact enum value
# - severity must be: low, medium, high, critical
# - overcome must be boolean
# - timestamp can be null
# - response_suggestions can be empty array
# 
# Generate the JSON now:"""
    
    # def _build_merge_prompt(
    #     self,
    #     chunk_text: str,
    #     call_context: Dict[str, Any],
    #     previous_objections: Dict[str, Any]
    # ) -> str:
    #     """LEGACY: Build prompt for merging with previous objections."""
    #     
    #     return f"""You previously extracted objections from the first part of this call.
# 
# **PREVIOUS OBJECTIONS:**
# {json.dumps(previous_objections, indent=2)}
# 
# **NEXT PART OF TRANSCRIPT:**
# {chunk_text}
# 
# **MERGE RULES:**
# 
# 1. **APPEND NEW OBJECTIONS:**
#    - Add any NEW objections from this chunk
#    - Keep ALL previous objections
#    - Do NOT duplicate objections (check objection_text similarity)
# 
# 2. **UPDATE OVERCOME STATUS:**
#    - If a previous objection is addressed in this chunk, update "overcome": true
# 
# 3. **INCREMENT TOTAL:**
#    - Update total_count to reflect all objections (previous + new)
# 
# 4. **AVOID DUPLICATES:**
#    - Before adding an objection, check if similar objection already exists
#    - "I need it today" and "Can you come sooner" are the same objection (category 1 or 4)
#    - "Why is there a fee?" and "Can you waive the charge?" are the same objection (category 5)
#    - "Let me think about it" mentioned twice is one objection (category 3)
# 
# **VERIFICATION:**
# - [ ] All previous objections are included
# - [ ] No duplicate objections
# - [ ] total_count matches array length
# 
# Output the COMPLETE updated JSON:"""
    
    # def _filter_and_validate_objections(self, result: Dict[str, Any], transcript: str = "") -> Dict[str, Any]:
    #     """
    #     LEGACY: Filter and validate objections (replaced by 7-stage pipeline)
    #     
    #     This method is no longer used. The new system has:
    #     - Stage 3: Transcript validation
    #     - Stage 4: Confidence scoring
    #     - Stage 5: Business logic filters
    #     - Stage 6: Speaker validation
    #     - Stage 7: Cross-validation
    #     
    #     Keeping for reference only.
    #     """
    #     pass
    #     # ... (all the legacy filtering code commented out above)
    
    
    # ============================================================================
    # END LEGACY CODE
    # ============================================================================


    async def _stage7_validate_speakers(
        self, 
        result: Dict[str, Any], 
        transcript: str
    ) -> Dict[str, Any]:
        """
        STAGE 7: LLM-based speaker validation.
        
        Verifies that each objection was actually said by a CUSTOMER (home_owner),
        not by a REP (customer_rep). This catches speaker ID errors that 
        word-matching filters cannot detect.
        """
        objections = result.get("objections", [])
        if not objections:
            return result
        
        # Build a list of statements to validate
        statements_to_validate = "\n".join([
            f"{i+1}. \"{obj['objection_text']}\""
            for i, obj in enumerate(objections)
        ])
        
        prompt = f"""For each statement below, find it in the transcript and identify WHO said it.

**STATEMENTS TO VALIDATE:**
{statements_to_validate}

**FULL TRANSCRIPT:**
{transcript}

**TASK:**
For each statement:
1. Find where it appears in the transcript
2. Check the speaker label on that line (customer_rep or home_owner)
3. Determine if it was said by the CUSTOMER or the REP

**IMPORTANT:**
- "customer_rep:", "rep:", "agent:" lines are REP statements
- "home_owner:", "customer:", "caller:" lines are CUSTOMER statements
- ONLY customers can have objections - if a statement is from a REP, it cannot be an objection!

**OUTPUT FORMAT (JSON only):**
{{
    "validations": [
        {{
            "statement_index": 1,
            "found_in_transcript": true/false,
            "actual_speaker": "customer_rep" | "home_owner" | "unknown",
            "is_customer_statement": true/false,
            "context_note": "brief note about what was found"
        }}
    ]
}}

Validate each statement:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You validate speaker identities from transcripts. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            validation_result = json.loads(response.choices[0].message.content)
            validations = validation_result.get("validations", [])
            
            # Filter out objections that weren't from customers
            validated_objections = []
            for i, obj in enumerate(objections):
                # Find corresponding validation
                validation = next(
                    (v for v in validations if v.get("statement_index") == i + 1),
                    None
                )
                
                if validation:
                    if validation.get("is_customer_statement", True):
                        # Update speaker_id if needed
                        obj["speaker_id"] = validation.get("actual_speaker", "home_owner")
                        validated_objections.append(obj)
                    else:
                        logger.info(f"Stage 6: Removed objection (REP statement): {obj['objection_text'][:50]}")
                else:
                    # If no validation found, keep it but log warning
                    logger.warning(f"Stage 6: No validation found for objection {i+1}, keeping")
                    validated_objections.append(obj)
            
            result["objections"] = validated_objections
            result["total_count"] = len(validated_objections)
            result["analysis_note"] = f"Speaker validation: {len(validated_objections)} customer objections"
            
            return result
            
        except Exception as e:
            logger.error(f"Stage 7 speaker validation failed: {e}")
            # Return original result on error
            return result
    
    async def _stage8_cross_validate_objections(
        self, 
        result: Dict[str, Any], 
        transcript: str
    ) -> Dict[str, Any]:
        """
        STAGE 8: LLM-based semantic cross-validation.
        
        Final quality check that reviews all remaining objections to catch:
        - False positives that slipped through (cooperation, acknowledgments, questions)
        - Incorrect categories
        - Misinterpretations
        """
        objections = result.get("objections", [])
        if not objections:
            return result
        
        objections_text = "\n".join([
            f"{i+1}. [{obj['speaker_id']}] {obj.get('category_text', 'Unknown')}"
            + (f" (sub: {obj.get('sub_objection')})" if obj.get('sub_objection') else "")
            + f": \"{obj['objection_text']}\""
            for i, obj in enumerate(objections)
        ])

        # Build canonical category list for the prompt
        categories_text = self._get_categories_prompt_text()

        prompt = f"""Review these detected objections from a call and validate each one.

**DETECTED OBJECTIONS:**
{objections_text}

**FULL TRANSCRIPT:**
{transcript}

**REVIEW EACH OBJECTION:**
For each one, determine:
1. Is this a GENUINE customer objection (expressing resistance/concern)?
2. Or is it actually something else that was misclassified?

**COMMON FALSE POSITIVES TO CATCH:**

❌ **COOPERATION/FLEXIBILITY (NOT objections):**
- "Kind of hit or miss" / "let's see what works" = flexibility, not objection
- "We'll postpone our vacation" = cooperating with schedule
- "I can reschedule" = accommodating

❌ **QUESTIONS/INFORMATION REQUESTS (NOT objections):**
- Questions ending in "?" asking for information
- "How does that work?" = seeking info
- "What time do you arrive?" = clarification

❌ **ACKNOWLEDGMENTS (NOT objections):**
- "I understand" / "That's fine" / "Okay"
- "Sounds good" / "That works"

❌ **REP STATEMENTS (CANNOT be objections):**
- Anything the representative/agent said
- Company policies being explained

❌ **PAST EXPERIENCES WITH OTHER COMPANIES (NOT objections to THIS company):**
- Customer describing problems with a PREVIOUS contractor/company is NOT an objection
- "The last company did a bad job" = context/explanation, not objection to current service
- "They installed it wrong before" = past experience, not resistance to current offer
- "People installed for me before weren't certified" = complaint about PAST company
- Only count as objection if the customer is expressing concern about THIS company doing the same

⚠️ **SEMANTIC DUPLICATES:**
- If multiple objections express the SAME underlying concern in different words, keep ONLY the most clearly stated one and mark the others as keep=false
- Example: "I want certified people" and "I need someone who knows what they're doing" = same concern about technician quality
- Example: "That's too much" and "I can't afford that price" = same price objection

✅ **GENUINE OBJECTIONS:**
- Customer resisting price: "That's too expensive"
- Customer refusing: "I don't want that"
- Customer expressing inability: "I can't make those times"
- Customer complaining: "I've been waiting too long"

**VALID CATEGORIES (use ONLY these exact names if correcting a category):**
{categories_text}

**IMPORTANT:** If correcting a category, you MUST use one of the exact category names listed above.
Do NOT invent new category names. If the objection doesn't fit categories 1-8 or 10, use "Other" (category 9).

**OUTPUT FORMAT (JSON only):**
{{
    "validated_objections": [
        {{
            "original_index": 1,
            "keep": true/false,
            "reason": "brief reason for keeping or removing",
            "corrected_category": null or "exact category name from list above"
        }}
    ],
    "summary": "X of Y objections validated as genuine"
}}

Validate:"""

        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You cross-validate objection detection results. Be strict - remove false positives. Output only valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            validation = json.loads(response.choices[0].message.content)
            validated_list = validation.get("validated_objections", [])
            
            # Build reverse lookup: canonical name -> category_id
            canonical_names = {name: cat_id for cat_id, name in self.objection_categories.items()}

            # Apply validation results
            final_objections = []
            for v in validated_list:
                if v.get("keep"):
                    idx = v.get("original_index", 1) - 1
                    if 0 <= idx < len(objections):
                        obj = objections[idx].copy()
                        # Apply category correction if provided
                        if v.get("corrected_category"):
                            corrected = v["corrected_category"]
                            if corrected in canonical_names:
                                # Valid canonical category name
                                obj["category_id"] = canonical_names[corrected]
                                obj["category_text"] = corrected
                                if corrected != "Other":
                                    obj["sub_objection"] = None
                            else:
                                # LLM returned a non-canonical name — treat as "Other" with sub_objection
                                logger.info(f"Stage 8: Non-canonical corrected_category '{corrected}', mapping to Other with sub_objection")
                                obj["category_id"] = 9
                                obj["category_text"] = "Other"
                                obj["sub_objection"] = corrected
                        final_objections.append(obj)
                else:
                    idx = v.get("original_index", 1) - 1
                    if 0 <= idx < len(objections):
                        logger.info(f"Stage 8: Removed false positive: {objections[idx]['objection_text'][:50]} - {v.get('reason', 'no reason')}")
            
            result["objections"] = final_objections
            result["total_count"] = len(final_objections)
            result["analysis_note"] = validation.get("summary", f"{len(final_objections)} objections validated")
            
            return result
            
        except Exception as e:
            logger.error(f"Stage 8 cross-validation failed: {e}")
            # Return original result on error
            return result


# Singleton instance
_objection_extractor: Optional[ObjectionExtractor] = None


def get_objection_extractor() -> ObjectionExtractor:
    """Get singleton objection extractor instance."""
    global _objection_extractor
    if _objection_extractor is None:
        _objection_extractor = ObjectionExtractor()
    return _objection_extractor

