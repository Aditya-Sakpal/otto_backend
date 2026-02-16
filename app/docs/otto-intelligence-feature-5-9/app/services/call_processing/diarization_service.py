"""
Diarization Service

LLM-based fallback for transcription diarization and speaker labeling.
"""

from typing import Dict, Any, List, Optional
import json
import logging
from ...config import get_settings
from ...core.llm import get_llm_client, get_active_model

logger = logging.getLogger(__name__)
settings = get_settings()


class DiarizationService:
    """Service for LLM-based transcript diarization and speaker labeling."""
    
    def __init__(self):
        # We use the active model for diarization to ensure compatibility with the selected provider
        self.model = get_active_model()  
        self.client = get_llm_client()
        self.temperature = 0.1  # Low temperature for consistent results
    
    async def diarize_transcript(
        self,
        transcript_text: str
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to diarize a plain transcript without speaker labels.
        
        Args:
            transcript_text: Plain transcript text without speaker labels
        
        Returns:
            List of segments with speaker labels
        """
        try:
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            prompt = self._build_diarization_prompt(transcript_text)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing conversations and identifying different speakers based on context, speaking style, and conversation flow. You can distinguish between customer service representatives and customers."
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
            segments = result.get("segments", [])
            
            logger.info(f"LLM diarization created {len(segments)} segments")
            return segments
            
        except Exception as e:
            logger.error(f"LLM diarization failed: {e}")
            # Return single segment with unknown speaker as fallback
            return [{
                "speaker": "SPEAKER_00",
                "text": transcript_text,
                "start_time": 0.0,
                "end_time": 0.0
            }]
    
    async def label_speakers(
        self,
        segments: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use LLM to label generic speakers (SPEAKER_00, SPEAKER_01, Speaker A, Speaker B)
        as Agent/customer_rep or Customer/home_owner.
        
        Args:
            segments: List of segments with generic speaker labels
            context: Additional context about the call (optional)
        
        Returns:
            List of segments with labeled speakers
        """
        try:
            # Extract unique speakers
            unique_speakers = list(set(seg.get("speaker", "unknown") for seg in segments))
            
            # If speakers are already labeled (contain "customer_rep", "home_owner", etc.), skip
            known_labels = ["customer_rep", "home_owner", "agent", "customer", "manager"]
            if any(any(label in speaker.lower() for label in known_labels) for speaker in unique_speakers):
                logger.info("Speakers already labeled, skipping LLM labeling")
                return segments
            
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            # Build prompt for speaker labeling
            prompt = self._build_speaker_labeling_prompt(segments, unique_speakers, context)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing call transcripts and identifying speaker roles. You can distinguish between customer service agents/representatives and customers based on their language, tone, and conversation patterns."
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
            speaker_mapping = result.get("speaker_mapping", {})
            
            # Apply mapping to segments
            labeled_segments = []
            for seg in segments:
                labeled_seg = seg.copy()
                original_speaker = seg.get("speaker", "unknown")
                labeled_seg["speaker"] = speaker_mapping.get(original_speaker, original_speaker)
                labeled_seg["original_speaker"] = original_speaker  # Preserve original
                labeled_segments.append(labeled_seg)
            
            logger.info(f"LLM speaker labeling applied: {speaker_mapping}")
            return labeled_segments
            
        except Exception as e:
            logger.error(f"LLM speaker labeling failed: {e}")
            # Return segments unchanged
            return segments
    
    async def verify_and_enhance_diarization(
        self,
        segments: List[Dict[str, Any]],
        original_transcript: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        HYBRID APPROACH: Verify API diarization quality and enhance if needed.
        
        This is better than re-diarizing from scratch because:
        1. API diarization has accurate timestamps
        2. LLM can identify errors without losing timing info
        3. Combines strengths of both approaches
        
        Returns:
            {
                "segments": enhanced_segments,
                "quality_score": 0.0-1.0,
                "issues_found": ["list of issues"],
                "enhancements_made": ["list of fixes"],
                "verification_method": "llm_hybrid"
            }
        """
        try:
            logger.info(f"Verifying API diarization quality for {len(segments)} segments")
            
            # Sample segments for verification (first 15 for context)
            sample_segments = segments[:min(15, len(segments))]
            
            # Refresh client/model
            self.model = get_active_model()
            self.client = get_llm_client()

            # Build verification prompt
            prompt = self._build_verification_prompt(sample_segments, segments)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing conversation diarization quality. You can identify speaker labeling errors, missed speaker changes, and incorrect speaker assignments."
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
            
            quality_score = result.get("quality_score", 0.8)
            issues_found = result.get("issues_found", [])
            corrections = result.get("corrections", [])
            
            # Apply corrections to segments
            enhanced_segments = self._apply_corrections(segments, corrections)
            
            logger.info(f"Diarization verification: quality={quality_score}, issues={len(issues_found)}, corrections={len(corrections)}")
            
            return {
                "segments": enhanced_segments,
                "quality_score": quality_score,
                "issues_found": issues_found,
                "enhancements_made": [c.get("description", "") for c in corrections],
                "verification_method": "llm_hybrid",
                "original_segment_count": len(segments),
                "enhanced_segment_count": len(enhanced_segments)
            }
            
        except Exception as e:
            logger.error(f"Diarization verification failed: {e}")
            # Return original segments if verification fails
            return {
                "segments": segments,
                "quality_score": 0.7,
                "issues_found": [f"Verification failed: {str(e)}"],
                "enhancements_made": [],
                "verification_method": "none"
            }
    
    def _build_diarization_prompt(self, transcript_text: str) -> str:
        """Build prompt for LLM-based diarization."""
        
        return f"""You are given a transcript without speaker labels. Your task is to identify different speakers and split the conversation into segments.

**TRANSCRIPT:**
{transcript_text}

**INSTRUCTIONS:**

1. **Identify speaker changes** based on:
   - Conversation flow and turn-taking
   - Questions vs answers
   - Different speaking styles or tones
   - Context clues (greetings, introductions, etc.)

2. **Typical patterns**:
   - Agent/Representative: Greets first, asks questions, provides information, professional tone
   - Customer: Responds, asks for help, describes problems, conversational tone

3. **Label speakers as**:
   - SPEAKER_00: Usually the agent/representative (the one who initiates, asks qualifying questions)
   - SPEAKER_01: Usually the customer (the one responding, providing info, asking about services)
   - SPEAKER_02, SPEAKER_03: Additional speakers if present

4. **Create segments**: Split text into individual turns where each person speaks

5. **HANDLING BACKGROUND SPEECH & SIDE CONVERSATIONS:**
   - Sometimes the customer talks to someone else in the background (spouse, child, coworker)
   - This background speech should STILL be attributed to SPEAKER_01 (customer)
   - Examples of side conversations (keep as customer speech):
     * "The stickers and and tech it and then like those, just for the guy that's gun ready"
     * "Hold on, let me check my calendar"
     * "Honey, what day works for you?"
   - These are NOT new speakers - they're the customer talking to someone off-phone
   - Only create SPEAKER_02 if someone else DIRECTLY joins the phone call

6. **GARBLED/UNCLEAR SPEECH:**
   - Sometimes transcription captures unclear audio
   - Keep it with the current speaker, don't split on garbled text
   - Example: "Um, probably Monday, Tuesday or I'm sorry, one of those days or all three, I'm sorry"
   - This is ONE person (customer) being uncertain, not multiple speakers

**OUTPUT FORMAT:**

{{
  "segments": [
    {{
      "speaker": "SPEAKER_00",
      "text": "The exact text spoken by this speaker",
      "start_time": 0.0,
      "end_time": 0.0
    }},
    {{
      "speaker": "SPEAKER_01",
      "text": "The customer's response",
      "start_time": 0.0,
      "end_time": 0.0
    }}
  ],
  "total_segments": 2,
  "confidence": 0.9
}}

**CRITICAL RULES:**
- Each segment should contain ONLY what ONE speaker says
- Do NOT combine multiple speakers in one segment
- Do NOT skip or omit any text from the original transcript
- Preserve the exact wording from the transcript
- If you're unsure about a speaker change, err on the side of creating a new segment
- Background/side conversations are STILL the same speaker (customer talking to someone else)
- Only 2 speakers in most calls: Agent (SPEAKER_00) and Customer (SPEAKER_01)

Generate the JSON now:"""
    
    def _build_verification_prompt(
        self,
        sample_segments: List[Dict[str, Any]],
        all_segments: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for verifying API diarization quality."""
        
        # Format sample for display with more detail
        sample_text = ""
        for i, seg in enumerate(sample_segments):
            speaker = seg.get('speaker', 'unknown')
            text = seg.get('text', '')
            start = seg.get('start_time', 0)
            end = seg.get('end_time', 0)
            duration = end - start
            sample_text += f"\nSegment {i+1} [{speaker}] ({duration:.1f}s):\n{text[:500]}\n"
        
        unique_speakers = list(set(seg.get("speaker", "unknown") for seg in all_segments))
        avg_duration = sum(seg.get("end_time", 0) - seg.get("start_time", 0) for seg in all_segments) / len(all_segments) if all_segments else 0
        
        return f"""You are reviewing API diarization that often LUMPS MULTIPLE SPEAKER TURNS into single segments. Your job is to AGGRESSIVELY identify where segments should be SPLIT.

**CRITICAL ISSUE:** API diarization frequently combines 5-10 speaker turns into one massive segment!

**STATISTICS:**
- Total Segments: {len(all_segments)}
- Average Segment Duration: {avg_duration:.1f}s
- Unique Speakers: {', '.join(unique_speakers)}

**SAMPLE CONVERSATION:**
{sample_text}

**YOUR TASK:** Find EVERY place where speaker changes were missed

**LOOK FOR THESE PATTERNS (MUST SPLIT):**

1. **Short Responses Mixed In:**
   - "...project if you have a few minutes? Yes. Okay. Perfect. So right now..."
   - Split at: "Yes." (new segment), "Okay. Perfect." (new segment)

2. **Question-Answer Pairs:**
   - "...Do you have any questions? Um, like for payment..."
   - Split at: "Um, like for payment" (different speaker)

3. **Back-and-Forth Dialog:**
   - "...We can do that. All right. Perfect. Thank you so much. Of course..."
   - Split each turn: "All right. Perfect. Thank you" (customer), "Of course" (agent)

4. **Acknowledgments:**
   - "Okay.", "Yes.", "All right.", "Perfect.", "Thank you.", "Of course."
   - These are usually separate turns!

5. **Politeness Markers:**
   - "Thank you" / "You're welcome" = different speakers
   - "Bye" / "Bye" = turn taking

**OUTPUT FORMAT:**

For EACH segment that needs splitting, provide:
1. Segment index
2. List of EXACT text markers where to split
3. Speaker assignment for each part

{{{{
  "quality_score": 0.3,
  "issues_found": [
    "Segment 1: Contains 8 speaker turns lumped together",
    "Segment 3: Contains 15+ turns, needs aggressive splitting"
  ],
  "corrections": [
    {{{{
      "segment_index": 0,
      "issue": "Multiple speaker turns combined",
      "correction": "split_multiple",
      "split_points": [
        {{{{
          "split_marker": "Yes.",
          "before_speaker": "SPEAKER_01",
          "after_speaker": "SPEAKER_00",
          "context": "few minutes? | Yes. | Okay."
        }}}},
        {{{{
          "split_marker": "Okay. Perfect.",
          "before_speaker": "SPEAKER_00",
          "after_speaker": "SPEAKER_01",
          "context": "Yes. | Okay. Perfect. | So right now"
        }}}}
      ],
      "description": "Split into 3 parts: Agent question, Customer 'Yes', Agent response"
    }}}}
  ],
  "overall_assessment": "Poor API diarization - many turns combined",
  "confidence": 0.95
}}}}

**CRITICAL RULES:**
- BE VERY AGGRESSIVE - if there's ANY doubt, split it!
- Short responses ("Yes", "Okay", "All right") are ALWAYS separate turns
- Question followed by answer = different speakers
- Average segment should be 6-10 seconds, not 30+ seconds
- If segment > 20 seconds, it DEFINITELY has multiple turns
- Provide EXACT split markers (copy the text exactly)
- For each split, specify which speaker comes before and after

**SCORING:**
- Large segments (>20s) with dialog = Quality score < 0.4
- Few segments (<5) for multi-minute call = Quality score < 0.3
- Good diarization = 1 segment every 6-10 seconds

Generate the JSON now:"""
    
    def _apply_corrections(
        self,
        segments: List[Dict[str, Any]],
        corrections: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply LLM-suggested corrections to segments, including splits."""
        
        if not corrections:
            return segments
        
        enhanced_segments = []
        segments_to_process = list(segments)  # Work with a copy
        
        # Track which segments have been processed
        processed_indices = set()
        
        for correction in corrections:
            try:
                segment_index = correction.get("segment_index")
                correction_type = correction.get("correction", "")
                
                if segment_index is None or segment_index >= len(segments_to_process):
                    continue
                
                if segment_index in processed_indices:
                    continue
                
                original_segment = segments_to_process[segment_index]
                
                if correction_type == "split_multiple":
                    # SPLIT SEGMENT INTO MULTIPLE PARTS
                    split_points = correction.get("split_points", [])
                    if split_points:
                        split_segments = self._split_segment(original_segment, split_points)
                        enhanced_segments.extend(split_segments)
                        processed_indices.add(segment_index)
                        logger.info(f"Split segment {segment_index} into {len(split_segments)} parts")
                        continue
                
                elif correction_type == "reassign":
                    # Reassign speaker
                    new_speaker = correction.get("new_speaker")
                    if new_speaker:
                        original_segment = original_segment.copy()
                        original_segment["speaker"] = new_speaker
                        original_segment["correction_applied"] = "reassigned"
                        logger.debug(f"Reassigned segment {segment_index} to {new_speaker}")
                
                elif correction_type == "split":
                    # Simple split (old method, kept for backward compatibility)
                    original_segment = original_segment.copy()
                    original_segment["needs_review"] = True
                    original_segment["correction_applied"] = "flagged_for_split"
                    logger.debug(f"Flagged segment {segment_index} for potential split")
                
                # If not split_multiple, add the segment (possibly modified)
                if segment_index not in processed_indices:
                    enhanced_segments.append(original_segment)
                    processed_indices.add(segment_index)
                
            except Exception as e:
                logger.warning(f"Failed to apply correction: {e}")
                continue
        
        # Add segments that weren't processed
        for i, seg in enumerate(segments_to_process):
            if i not in processed_indices:
                enhanced_segments.append(seg)
        
        # Sort by start_time to maintain order
        enhanced_segments.sort(key=lambda x: x.get("start_time", 0))
        
        logger.info(f"Applied corrections: {len(segments)} → {len(enhanced_segments)} segments")
        
        return enhanced_segments
    
    def _split_segment(
        self,
        segment: Dict[str, Any],
        split_points: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Split a segment into multiple parts based on LLM-identified split points.
        
        Args:
            segment: Original segment to split
            split_points: List of split point dicts with split_marker, speakers
        
        Returns:
            List of new segments
        """
        text = segment.get("text", "")
        start_time = segment.get("start_time", 0)
        end_time = segment.get("end_time", 0)
        duration = end_time - start_time
        
        # Build list of split positions
        split_positions = []
        for sp in split_points:
            split_marker = sp.get("split_marker", "")
            if split_marker and split_marker in text:
                # Find position of split marker
                pos = text.find(split_marker)
                if pos >= 0:
                    split_positions.append({
                        "position": pos,
                        "marker": split_marker,
                        "before_speaker": sp.get("before_speaker"),
                        "after_speaker": sp.get("after_speaker")
                    })
        
        if not split_positions:
            # No valid split points found, return original
            return [segment]
        
        # Sort by position
        split_positions.sort(key=lambda x: x["position"])
        
        # Create new segments
        new_segments = []
        current_pos = 0
        current_speaker = segment.get("speaker")
        
        for i, split_info in enumerate(split_positions):
            split_pos = split_info["position"]
            
            # Extract text before split
            if split_pos > current_pos:
                part_text = text[current_pos:split_pos].strip()
                if part_text:
                    # Estimate timing proportionally
                    part_duration = (split_pos - current_pos) / len(text) * duration
                    part_start = start_time + (current_pos / len(text)) * duration
                    part_end = part_start + part_duration
                    
                    new_segments.append({
                        "speaker": split_info.get("before_speaker") or current_speaker,
                        "text": part_text,
                        "start_time": part_start,
                        "end_time": part_end,
                        "original_speaker": segment.get("original_speaker", segment.get("speaker")),
                        "split_from_segment": True
                    })
            
            # Move to after the split marker
            current_pos = split_pos + len(split_info["marker"])
            current_speaker = split_info.get("after_speaker") or current_speaker
        
        # Add remaining text
        if current_pos < len(text):
            part_text = text[current_pos:].strip()
            if part_text:
                part_start = start_time + (current_pos / len(text)) * duration
                
                new_segments.append({
                    "speaker": current_speaker,
                    "text": part_text,
                    "start_time": part_start,
                    "end_time": end_time,
                    "original_speaker": segment.get("original_speaker", segment.get("speaker")),
                    "split_from_segment": True
                })
        
        logger.debug(f"Split segment into {len(new_segments)} parts")
        return new_segments if new_segments else [segment]
    
    def _build_speaker_labeling_prompt(
        self,
        segments: List[Dict[str, Any]],
        unique_speakers: List[str],
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for speaker role labeling."""
        
        # Sample first 10 segments for context
        sample_segments = segments[:min(10, len(segments))]
        sample_text = "\n".join([
            f"{seg.get('speaker', 'unknown')}: {seg.get('text', '')[:100]}"
            for seg in sample_segments
        ])
        
        context_info = ""
        if context:
            context_info = f"""
**CALL CONTEXT:**
- Company: {context.get('company_id', 'unknown')}
- Phone: {context.get('phone_number', 'unknown')}
- Rep Role: {context.get('rep_role', 'customer_rep')}
"""
        
        return f"""You are analyzing a call transcript with generic speaker labels (SPEAKER_00, SPEAKER_01, etc. or Speaker A, Speaker B, etc.). Your task is to identify which speaker is the agent/representative and which is the customer.

{context_info}

**UNIQUE SPEAKERS FOUND:**
{', '.join(unique_speakers)}

**SAMPLE CONVERSATION (first few turns):**
{sample_text}

**INSTRUCTIONS:**

1. **Identify the agent/representative** by looking for:
   - Greets first ("Thank you for calling...", "How can I help you?")
   - Professional language and tone
   - Asks qualifying questions
   - Provides company information
   - Follows a script or structure
   - Offers solutions or schedules appointments

2. **Identify the customer** by looking for:
   - Describes their problem or need
   - Asks questions about services
   - Responds to agent's questions
   - More casual or emotional language
   - Expresses concerns or objections

3. **Label mapping**:
   - Agent → "customer_rep"
   - Customer → "home_owner"
   - Additional speakers → "manager" or keep original if uncertain

4. **HANDLING BACKGROUND SPEECH:**
   - Sometimes the customer talks to someone else in the background (spouse, child, coworker)
   - This should STILL be labeled as "home_owner" (same speaker)
   - Examples of background speech (keep as home_owner):
     * "The stickers and and tech it and then like those, just for the guy that's gun ready"
     * "Hold on honey, let me check the calendar"
     * Random unclear speech while customer is thinking
   - Only create a separate speaker if someone DIRECTLY joins the phone call
   - Most calls have ONLY 2 speakers: agent and customer

**OUTPUT FORMAT:**

{{
  "speaker_mapping": {{
    "SPEAKER_00": "customer_rep",
    "SPEAKER_01": "home_owner"
  }},
  "confidence": 0.95,
  "reasoning": "SPEAKER_00 greeted first and asked how they could help, indicating agent role. SPEAKER_01 described a problem, indicating customer."
}}

**CRITICAL RULES:**
- Use EXACTLY "customer_rep" for agent (not "agent", "representative", etc.)
- Use EXACTLY "home_owner" for customer (not "customer", "client", etc.)
- Map ALL speakers found in the unique speakers list
- Be confident in your assignment based on conversation patterns
- Background speech/side conversations = SAME speaker (home_owner)
- Most calls have ONLY 2 speakers - don't over-segment

Generate the JSON now:"""
    
    def has_diarization(self, segments: List[Dict[str, Any]]) -> bool:
        """Check if segments have speaker diarization."""
        if not segments:
            return False
        
        # Check if multiple speakers exist
        unique_speakers = set(seg.get("speaker", "unknown") for seg in segments)
        return len(unique_speakers) > 1
    
    def format_diarized_transcript(self, segments: List[Dict[str, Any]]) -> str:
        """Format segments into readable transcript with speaker labels."""
        formatted_lines = []
        
        for seg in segments:
            speaker = seg.get("speaker", "unknown")
            text = seg.get("text", "").strip()
            if text:
                formatted_lines.append(f"{speaker}: {text}")
        
        return "\n\n".join(formatted_lines)


# Singleton instance
_diarization_service: Optional[DiarizationService] = None


def get_diarization_service() -> DiarizationService:
    """Get singleton diarization service instance."""
    global _diarization_service
    if _diarization_service is None:
        _diarization_service = DiarizationService()
    return _diarization_service

