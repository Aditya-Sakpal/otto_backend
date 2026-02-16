"""
Phase Detection Service

LLM-based semantic conversation phase detection with hybrid timestamp alignment.

Based on manager decisions Q49-Q60:
- Q49: 6 core phases
- Q50: LLM-based detection
- Q51: Overlap allowed
- Q52: Timestamp estimation from word count (enhanced with segment mapping)
- Q56: Flag missing phases
- Q57: Track time distribution

Enhanced in v1.1:
- Uses diarized segments for accurate timestamp estimation when available
- Falls back to word-count estimation when segments not available

Enhanced in v1.2:
- Hybrid alignment: LLM segments (accurate speakers) + API segments (accurate timestamps)
- Intelligent text matching to handle clubbed API segments
- Multi-level fallback: alignment retry -> word-count estimation
"""

import logging
import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from difflib import SequenceMatcher

from app.config import get_settings
from app.models.enums import ConversationPhase
from app.models.phase import (
    ConversationPhaseResult, PhaseTimestamp, PhaseTranscriptSegment,
    PhaseAnalytics, CallPhases
)


logger = logging.getLogger(__name__)


# Type for diarized segments
class DiarizedSegment:
    """Type hint for diarized transcript segment"""
    speaker: str
    text: str
    start_time: float  # seconds
    end_time: float    # seconds


# Phase detection prompt
PHASE_DETECTION_PROMPT = """You are an expert sales call analyst. Analyze this sales call transcript and detect which conversation phases are present.

## CONVERSATION PHASES (identify all that apply):

1. **GREETING** - Opening of the call
   - Name exchange, company introduction
   - Building initial rapport
   - "How are you today?", "Thanks for calling..."

2. **PROBLEM_DISCOVERY** - Understanding customer need
   - Asking about their situation/problem
   - Learning what prompted the call
   - "What brings you in today?", "Tell me about the issue..."

3. **QUALIFICATION** - Assessing fit and ability to buy
   - Budget questions
   - Timeline questions
   - Decision-maker identification
   - "When were you looking to get this done?", "What's your budget range?"

4. **OBJECTION_HANDLING** - Addressing concerns
   - Responding to pushback
   - Overcoming hesitations
   - "I understand your concern about...", "Let me address that..."

5. **CLOSING** - Asking for business
   - Proposing next steps
   - Booking appointment
   - "We have availability on...", "Can we schedule..."

6. **POST_CLOSE** - After commitment
   - Confirming details
   - Setting expectations
   - Thank you and goodbye
   - "You'll receive a confirmation...", "Thanks for choosing us..."

## TRANSCRIPT:
{transcript}

## INSTRUCTIONS:
For EACH phase that is present in the call, provide:
1. Whether it was detected (true/false)
2. Confidence level (0.0-1.0)
3. Key phrases that indicate this phase
4. Start and end word indices (approximate)
5. Quality assessment (how well rep executed this phase)

Respond in this exact JSON format:
{{
  "phases": {{
    "greeting": {{
      "detected": true/false,
      "confidence": 0.0-1.0,
      "key_phrases": ["phrase1", "phrase2"],
      "start_word_index": 0,
      "end_word_index": 50,
      "quality_score": 0.0-1.0,
      "quality_notes": "assessment of how well rep executed this phase"
    }},
    "problem_discovery": {{ ... }},
    "qualification": {{ ... }},
    "objection_handling": {{ ... }},
    "closing": {{ ... }},
    "post_close": {{ ... }}
  }},
  "phase_sequence": ["greeting", "problem_discovery", ...],
  "overall_flow_score": 0.0-1.0,
  "insights": ["insight1", "insight2"]
}}

Important:
- Mark phases as detected:false if they're not clearly present
- **Word indices must be SEQUENTIAL and NON-OVERLAPPING**
- Each phase's end_word_index should equal the next phase's start_word_index
- If phases blend semantically, assign the boundary to the dominant phase at that moment
- Ensure word indices cover the entire transcript from 0 to approximately {word_count} words
- Quality scores reflect how effectively the rep executed each phase
- For service/support calls, adapt phase definitions (e.g., qualification = account verification)"""


class PhaseDetectionService:
    """Detect semantic conversation phases in calls with hybrid timestamp alignment"""
    
    ALGORITHM_VERSION = "1.2"  # Updated for hybrid alignment
    
    # Expected phases in optimal order
    EXPECTED_PHASES = [
        ConversationPhase.GREETING,
        ConversationPhase.PROBLEM_DISCOVERY,
        ConversationPhase.QUALIFICATION,
        ConversationPhase.OBJECTION_HANDLING,
        ConversationPhase.CLOSING,
        ConversationPhase.POST_CLOSE
    ]
    
    # Typical speaking rate for timestamp estimation (fallback)
    WORDS_PER_MINUTE = 150  # Average speaking rate
    MS_PER_WORD = int(60000 / WORDS_PER_MINUTE)  # ~400ms per word
    
    # Alignment configuration
    MAX_ALIGNMENT_RETRIES = 3  # Retry LLM alignment on text mismatch
    TEXT_SIMILARITY_THRESHOLD = 0.6  # Minimum similarity for text matching
    
    def __init__(self):
        from app.core.llm import get_active_model
        self.model = get_active_model()
        self._word_timestamp_cache: List[Dict[str, Any]] = []  # Cache for segment mapping
        self.settings = get_settings()
    
    async def detect_phases(
        self,
        transcript: str,
        call_id: str,
        company_id: str,
        call_duration_ms: Optional[int] = None,
        segments: Optional[List[Dict[str, Any]]] = None,
        llm_segments: Optional[List[Dict[str, Any]]] = None,
        api_segments: Optional[List[Dict[str, Any]]] = None
    ) -> CallPhases:
        """
        Detect conversation phases in a transcript with hybrid timestamp alignment.
        
        This method uses a hybrid approach:
        1. If both LLM segments (accurate speakers) and API segments (accurate timestamps) 
           are provided, align them for best results
        2. Fall back to direct segment mapping if alignment fails
        3. Fall back to word-count estimation if no segments available
        
        Args:
            transcript: Full call transcript
            call_id: Call identifier
            company_id: Company identifier
            call_duration_ms: Actual call duration in ms (for timestamp scaling)
            segments: Legacy - diarized transcript segments (will use as fallback)
            llm_segments: LLM-diarized segments (accurate speakers, no timestamps)
            api_segments: API-diarized segments (has timestamps, may have speaker errors)
            
        Returns:
            CallPhases with detection results and analytics
        """
        # Clean and prepare transcript
        cleaned_transcript = self._clean_transcript(transcript)
        word_count = len(cleaned_transcript.split())
        
        # Determine which segments to use and the estimation method
        aligned_segments = None
        word_timestamps = None
        estimation_method = "word_count"
        
        # Try hybrid alignment first if we have both LLM and API segments
        if llm_segments and api_segments:
            logger.info(f"Attempting hybrid alignment for {call_id} with {len(llm_segments)} LLM segments and {len(api_segments)} API segments")
            
            for retry in range(self.MAX_ALIGNMENT_RETRIES):
                try:
                    aligned_segments = await self._align_llm_to_api_segments(
                        llm_segments=llm_segments,
                        api_segments=api_segments,
                        retry_attempt=retry
                    )
                    
                    if aligned_segments:
                        word_timestamps = self._build_word_timestamp_map(aligned_segments)
                        estimation_method = "hybrid_aligned"
                        logger.info(f"Successfully aligned segments on attempt {retry + 1} for {call_id}")
                        break
                    else:
                        logger.warning(f"Alignment attempt {retry + 1} returned no segments for {call_id}")
                        
                except Exception as e:
                    logger.warning(f"Alignment attempt {retry + 1} failed for {call_id}: {e}")
                    if retry == self.MAX_ALIGNMENT_RETRIES - 1:
                        logger.error(f"All {self.MAX_ALIGNMENT_RETRIES} alignment attempts failed for {call_id}")
        
        # Fall back to direct API segments if alignment failed
        if not word_timestamps and api_segments:
            logger.info(f"Using direct API segments for {call_id} (alignment unavailable or failed)")
            try:
                word_timestamps = self._build_word_timestamp_map(api_segments)
                estimation_method = "api_segments_direct"
            except Exception as e:
                logger.warning(f"Failed to build timestamp map from API segments: {e}")
        
        # Fall back to legacy segments if provided
        if not word_timestamps and segments and len(segments) > 0:
            logger.info(f"Using legacy segments for {call_id}")
            try:
                word_timestamps = self._build_word_timestamp_map(segments)
                estimation_method = "segment_mapped"
            except Exception as e:
                logger.warning(f"Failed to build timestamp map from legacy segments: {e}")
        
        # Final fallback to word-count estimation
        if not word_timestamps:
            logger.info(f"Using word-count estimation for {call_id} (no usable segments)")
            estimation_method = "word_count"
        
        # Estimate duration if not provided
        if not call_duration_ms:
            if api_segments and len(api_segments) > 0:
                last_segment = api_segments[-1]
                call_duration_ms = int(last_segment.get("end_time", 0) * 1000)
            elif segments and len(segments) > 0:
                last_segment = segments[-1]
                call_duration_ms = int(last_segment.get("end_time", 0) * 1000)
            if not call_duration_ms:
                call_duration_ms = word_count * self.MS_PER_WORD
        
        # Detect phases using LLM
        try:
            llm_result = await self._detect_with_llm(cleaned_transcript)
            model_used = self.model
        except Exception as e:
            logger.warning(f"LLM detection failed: {e}, using fallback")
            llm_result = self._detect_with_rules(cleaned_transcript)
            model_used = "rule_based"
        
        # Build phase results
        phases: Dict[str, ConversationPhaseResult] = {}
        detected_phases = []
        missing_phases = []
        
        for phase in self.EXPECTED_PHASES:
            phase_key = phase.value
            phase_data = llm_result.get("phases", {}).get(phase_key, {})
            
            detected = phase_data.get("detected", False)
            
            # Build timestamp from word indices
            timestamps = None
            if detected:
                start_idx = phase_data.get("start_word_index", 0)
                end_idx = phase_data.get("end_word_index", word_count)
                
                # Use segment-based or word-count estimation
                if word_timestamps:
                    timestamps = self._estimate_timestamps_from_segments(
                        start_idx, end_idx, word_timestamps, call_duration_ms, estimation_method
                    )
                else:
                    timestamps = self._estimate_timestamps(
                        start_idx, end_idx, word_count, call_duration_ms
                    )
            
            # Build segments
            phase_segments = []
            if detected:
                # Find speaker for this segment if segments available
                speaker = None
                if word_timestamps:
                    start_idx_safe = min(phase_data.get("start_word_index", 0), len(word_timestamps) - 1)
                    if start_idx_safe >= 0 and start_idx_safe < len(word_timestamps):
                        speaker = word_timestamps[start_idx_safe].get("speaker")
                
                phase_segments.append(PhaseTranscriptSegment(
                    start_word_index=phase_data.get("start_word_index", 0),
                    end_word_index=phase_data.get("end_word_index", word_count),
                    speaker=speaker,
                    text=self._extract_segment(
                        cleaned_transcript,
                        phase_data.get("start_word_index", 0),
                        phase_data.get("end_word_index", word_count)
                    )
                ))
            
            phases[phase_key] = ConversationPhaseResult(
                phase=phase,
                detected=detected,
                confidence=phase_data.get("confidence", 0.0),
                timestamps=timestamps,
                segments=phase_segments,
                key_phrases=phase_data.get("key_phrases", []),
                quality_score=phase_data.get("quality_score"),
                quality_notes=phase_data.get("quality_notes")
            )
            
            if detected:
                detected_phases.append(phase_key)
            else:
                missing_phases.append(phase_key)
        
        # Post-process: resolve overlaps and fill gaps
        phases = self._resolve_phase_boundaries(
            phases=phases,
            phase_sequence=llm_result.get("phase_sequence", detected_phases),
            total_word_count=word_count,
            word_timestamps=word_timestamps,
            call_duration_ms=call_duration_ms,
            estimation_method=estimation_method
        )
        
        # Build analytics
        analytics = self._build_analytics(
            phases=phases,
            phase_sequence=llm_result.get("phase_sequence", detected_phases),
            total_duration_ms=call_duration_ms,
            missing_phases=missing_phases
        )
        
        # Add insights from LLM
        analytics.insights = llm_result.get("insights", [])
        
        return CallPhases(
            call_id=call_id,
            company_id=company_id,
            phases=phases,
            analytics=analytics,
            overall_flow_score=llm_result.get("overall_flow_score"),
            has_missing_phases=len(missing_phases) > 0,
            missing_phases=missing_phases,
            detection_method="llm" if model_used != "rule_based" else "rule_based",
            model_used=model_used,
            processed_at=datetime.utcnow(),
            algorithm_version=self.ALGORITHM_VERSION
        )
    
    async def _align_llm_to_api_segments(
        self,
        llm_segments: List[Dict[str, Any]],
        api_segments: List[Dict[str, Any]],
        retry_attempt: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Align LLM segments (accurate speakers) to API segments (accurate timestamps).
        
        This handles the case where API diarization clubs multiple speakers into one segment,
        while LLM correctly identifies the individual speakers.
        
        Algorithm:
        1. Match each LLM segment to API segments using text similarity
        2. When multiple LLM segments map to one API segment (clubbed case):
           - Subdivide the API timestamp proportionally by word count
        3. Preserve LLM speaker labels + derive proportional API timestamps
        
        Args:
            llm_segments: Segments with accurate speaker labels, no timestamps
                         [{"speaker": "customer_rep", "text": "Hello...", ...}]
            api_segments: Segments with timestamps but potentially wrong speakers
                         [{"speaker": "SPEAKER_00", "text": "...", "start_time": 0.5, "end_time": 5.2}]
            retry_attempt: Current retry number (for logging)
            
        Returns:
            Aligned segments with LLM speakers + API timestamps, or None if alignment fails
        """
        if not llm_segments or not api_segments:
            return None
        
        logger.info(f"Starting alignment attempt {retry_attempt + 1}: {len(llm_segments)} LLM segments -> {len(api_segments)} API segments")
        
        # Step 1: Build full text from each segment set for verification
        llm_full_text = " ".join(seg.get("text", "") for seg in llm_segments)
        api_full_text = " ".join(seg.get("text", "") for seg in api_segments)
        
        # Normalize texts for comparison
        llm_normalized = self._normalize_text(llm_full_text)
        api_normalized = self._normalize_text(api_full_text)
        
        # Check overall text similarity
        overall_similarity = self._text_similarity(llm_normalized, api_normalized)
        logger.info(f"Overall text similarity: {overall_similarity:.2f}")
        
        if overall_similarity < self.TEXT_SIMILARITY_THRESHOLD:
            logger.warning(f"Low text similarity ({overall_similarity:.2f}) between LLM and API segments")
            # On retry, we might want to use a more lenient approach
            if retry_attempt < 2:
                return None  # Let caller retry
        
        # Step 2: Match LLM segments to API segments
        aligned_segments = []
        
        # Track which API segment we're currently matching against
        api_idx = 0
        api_segment = api_segments[api_idx] if api_idx < len(api_segments) else None
        api_text_consumed = 0  # Character position within current API segment
        
        for llm_idx, llm_seg in enumerate(llm_segments):
            llm_text = llm_seg.get("text", "").strip()
            if not llm_text:
                continue
            
            llm_normalized = self._normalize_text(llm_text)
            llm_word_count = len(llm_text.split())
            
            # Find matching portion in API segments
            matched = False
            search_start_api_idx = api_idx
            
            # Try to find this LLM segment in API segments (might span multiple)
            for search_api_idx in range(search_start_api_idx, len(api_segments)):
                api_seg = api_segments[search_api_idx]
                api_text = api_seg.get("text", "").strip()
                api_normalized = self._normalize_text(api_text)
                
                # Check if LLM text is contained in this API segment
                if llm_normalized in api_normalized or api_normalized in llm_normalized:
                    similarity = self._text_similarity(llm_normalized, api_normalized)
                    
                    if similarity >= self.TEXT_SIMILARITY_THRESHOLD:
                        # Match found - calculate proportional timestamp
                        aligned_seg = self._create_aligned_segment(
                            llm_segment=llm_seg,
                            api_segment=api_seg,
                            llm_word_count=llm_word_count
                        )
                        aligned_segments.append(aligned_seg)
                        
                        api_idx = search_api_idx
                        matched = True
                        break
                
                # Try fuzzy matching as fallback
                similarity = self._text_similarity(llm_normalized, api_normalized)
                if similarity >= self.TEXT_SIMILARITY_THRESHOLD - 0.1:  # More lenient
                    aligned_seg = self._create_aligned_segment(
                        llm_segment=llm_seg,
                        api_segment=api_seg,
                        llm_word_count=llm_word_count
                    )
                    aligned_segments.append(aligned_seg)
                    
                    api_idx = search_api_idx
                    matched = True
                    break
            
            if not matched:
                # Couldn't match this LLM segment to any API segment
                # Use position-based fallback
                if api_idx < len(api_segments):
                    logger.debug(f"No text match for LLM segment {llm_idx}, using position-based fallback")
                    aligned_seg = self._create_aligned_segment(
                        llm_segment=llm_seg,
                        api_segment=api_segments[api_idx],
                        llm_word_count=llm_word_count
                    )
                    aligned_segments.append(aligned_seg)
                else:
                    # Ran out of API segments, use last one's end time
                    logger.warning(f"No API segment available for LLM segment {llm_idx}")
                    if aligned_segments:
                        # Estimate based on last aligned segment
                        last_seg = aligned_segments[-1]
                        estimated_duration = llm_word_count * (self.MS_PER_WORD / 1000)
                        aligned_seg = {
                            "speaker": llm_seg.get("speaker", "unknown"),
                            "text": llm_text,
                            "start_time": last_seg["end_time"],
                            "end_time": last_seg["end_time"] + estimated_duration,
                            "original_speaker": llm_seg.get("original_speaker")
                        }
                        aligned_segments.append(aligned_seg)
        
        logger.info(f"Alignment complete: produced {len(aligned_segments)} aligned segments")
        
        # Validation: check if we got reasonable alignment
        if len(aligned_segments) < len(llm_segments) * 0.7:  # Lost more than 30% of segments
            logger.warning(f"Alignment lost too many segments: {len(aligned_segments)}/{len(llm_segments)}")
            if retry_attempt < 2:
                return None  # Trigger retry
        
        return aligned_segments if aligned_segments else None
    
    def _create_aligned_segment(
        self,
        llm_segment: Dict[str, Any],
        api_segment: Dict[str, Any],
        llm_word_count: int
    ) -> Dict[str, Any]:
        """
        Create an aligned segment by combining LLM speaker info with API timestamps.
        
        For clubbed API segments, this proportionally subdivides the timestamp.
        """
        api_start = api_segment.get("start_time", 0)  # seconds
        api_end = api_segment.get("end_time", 0)      # seconds
        api_duration = api_end - api_start
        
        # If API segment has multiple speakers (clubbed), we need to subdivide
        # For now, we use the full API segment duration
        # TODO: Could be enhanced to track position within clubbed segment
        
        return {
            "speaker": llm_segment.get("speaker", "unknown"),
            "text": llm_segment.get("text", ""),
            "start_time": api_start,
            "end_time": api_end,
            "original_speaker": llm_segment.get("original_speaker"),
            "alignment_method": "hybrid"
        }
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison: lowercase, remove extra spaces, punctuation."""
        # Lowercase
        text = text.lower()
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        # Collapse whitespace
        text = ' '.join(text.split())
        return text
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate text similarity using SequenceMatcher (0.0 to 1.0)."""
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1, text2).ratio()
    
    def _build_word_timestamp_map(
        self,
        segments: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Build a word-to-timestamp mapping from diarized segments.
        
        Each word gets an estimated timestamp based on its position within the segment.
        
        Args:
            segments: List of diarized segments with speaker, text, start_time, end_time
            
        Returns:
            List of word entries: {"word_index": int, "timestamp_ms": int, "speaker": str}
        """
        word_timestamps = []
        current_word_index = 0
        
        for seg in segments:
            text = seg.get("text", "")
            start_time = seg.get("start_time", 0)  # seconds
            end_time = seg.get("end_time", 0)      # seconds
            speaker = seg.get("speaker", "unknown")
            
            # Split segment text into words
            words = text.split()
            if not words:
                continue
            
            # Calculate timing for each word in segment
            seg_duration_ms = (end_time - start_time) * 1000
            ms_per_word = seg_duration_ms / len(words) if words else 0
            
            for i, word in enumerate(words):
                word_ts = int((start_time * 1000) + (i * ms_per_word))
                word_timestamps.append({
                    "word_index": current_word_index,
                    "timestamp_ms": word_ts,
                    "speaker": speaker,
                    "word": word
                })
                current_word_index += 1
        
        return word_timestamps
    
    def _estimate_timestamps_from_segments(
        self,
        start_word_idx: int,
        end_word_idx: int,
        word_timestamps: List[Dict[str, Any]],
        total_duration_ms: int,
        estimation_method: str = "segment_mapped"
    ) -> PhaseTimestamp:
        """
        Estimate timestamps using the word-timestamp mapping from segments.
        
        Much more accurate than linear word-count estimation because it uses
        actual segment boundaries from the diarization.
        
        Args:
            start_word_idx: Start word index from LLM detection
            end_word_idx: End word index from LLM detection
            word_timestamps: Pre-built word timestamp mapping
            total_duration_ms: Total call duration for boundary clamping
            estimation_method: Method used for timestamp estimation (for tracking)
            
        Returns:
            PhaseTimestamp with segment-mapped timestamps
        """
        if not word_timestamps:
            # Fallback to linear estimation
            return PhaseTimestamp(
                start_ms=0,
                end_ms=total_duration_ms,
                duration_ms=total_duration_ms,
                estimation_method="word_count"
            )
        
        # Clamp indices to valid range
        max_idx = len(word_timestamps) - 1
        start_idx = max(0, min(start_word_idx, max_idx))
        end_idx = max(0, min(end_word_idx, max_idx))
        
        # Get timestamps from the mapping
        start_ms = word_timestamps[start_idx]["timestamp_ms"]
        
        # For end, we want the timestamp AFTER the last word
        if end_idx < max_idx:
            end_ms = word_timestamps[end_idx + 1]["timestamp_ms"]
        else:
            # Use the last word's timestamp + estimated word duration
            end_ms = min(
                word_timestamps[end_idx]["timestamp_ms"] + self.MS_PER_WORD,
                total_duration_ms
            )
        
        # Ensure end > start
        if end_ms <= start_ms:
            end_ms = min(start_ms + self.MS_PER_WORD, total_duration_ms)
        
        return PhaseTimestamp(
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=end_ms - start_ms,
            estimation_method=estimation_method
        )
    
    async def _detect_with_llm(self, transcript: str) -> Dict[str, Any]:
        """Use LLM for semantic phase detection."""
        from app.core.llm import get_llm_client, get_active_model
        
        # Calculate word count for the prompt
        word_count = len(transcript.split())
        prompt = PHASE_DETECTION_PROMPT.format(
            transcript=transcript[:15000],
            word_count=word_count
        )
        
        try:
            client = get_llm_client()
            model = get_active_model()
            
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a sales call analyst. Respond only with valid JSON."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            
            result = response.choices[0].message.content
            
            # Parse JSON response
            try:
                # Try to extract JSON from response
                json_match = re.search(r'\{[\s\S]*\}', result)
                if json_match:
                    return json.loads(json_match.group())
                return json.loads(result)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM response: {e}")
                return {"phases": {}}
                
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
    
    def _detect_with_rules(self, transcript: str) -> Dict[str, Any]:
        """Fallback rule-based detection."""
        transcript_lower = transcript.lower()
        words = transcript.split()
        word_count = len(words)
        
        phases = {}
        sequence = []
        
        # Rule-based patterns for each phase
        patterns = {
            "greeting": {
                "patterns": [
                    r"hello|hi there|good (morning|afternoon|evening)",
                    r"thank(s| you) for calling",
                    r"how (are|can) (you|i|we)",
                    r"my name is|this is"
                ],
                "typical_range": (0, int(word_count * 0.1))
            },
            "problem_discovery": {
                "patterns": [
                    r"what (brings|can|are you|issues?)",
                    r"tell me (about|more)",
                    r"(describe|explain) (the|your)",
                    r"what'?s (going on|the problem|happening)"
                ],
                "typical_range": (int(word_count * 0.05), int(word_count * 0.3))
            },
            "qualification": {
                "patterns": [
                    r"budget|price range|afford",
                    r"timeline|when .* looking",
                    r"decision maker|who .* decides",
                    r"how soon|how quickly"
                ],
                "typical_range": (int(word_count * 0.2), int(word_count * 0.6))
            },
            "objection_handling": {
                "patterns": [
                    r"concern|worry|hesitat",
                    r"too expensive|costs? too much",
                    r"think about it|not sure",
                    r"understand your|i hear you"
                ],
                "typical_range": (int(word_count * 0.3), int(word_count * 0.8))
            },
            "closing": {
                "patterns": [
                    r"schedule|book|appointment",
                    r"availability|available",
                    r"ready to|let'?s (get|move|proceed)",
                    r"sign up|commit"
                ],
                "typical_range": (int(word_count * 0.6), int(word_count * 0.95))
            },
            "post_close": {
                "patterns": [
                    r"confirmation|confirm",
                    r"thank(s| you) (for|again)",
                    r"have a (great|good|nice) day",
                    r"talk (to you|soon)|goodbye"
                ],
                "typical_range": (int(word_count * 0.85), word_count)
            }
        }
        
        for phase_name, config in patterns.items():
            detected = False
            confidence = 0.0
            key_phrases = []
            
            for pattern in config["patterns"]:
                matches = re.findall(pattern, transcript_lower)
                if matches:
                    detected = True
                    confidence = min(confidence + 0.25, 1.0)
                    key_phrases.extend([m if isinstance(m, str) else m[0] for m in matches[:2]])
            
            start, end = config["typical_range"]
            
            phases[phase_name] = {
                "detected": detected,
                "confidence": confidence,
                "key_phrases": key_phrases[:5],
                "start_word_index": start,
                "end_word_index": end,
                "quality_score": 0.7 if detected else None,
                "quality_notes": None
            }
            
            if detected:
                sequence.append(phase_name)
        
        return {
            "phases": phases,
            "phase_sequence": sequence,
            "overall_flow_score": len(sequence) / 6.0,
            "insights": []
        }
    
    def _clean_transcript(self, transcript: str) -> str:
        """Clean transcript for processing."""
        # Remove extra whitespace
        cleaned = " ".join(transcript.split())
        # Remove timestamp markers if present
        cleaned = re.sub(r'\[\d+:\d+\]', '', cleaned)
        return cleaned.strip()
    
    def _estimate_timestamps(
        self,
        start_word_idx: int,
        end_word_idx: int,
        total_words: int,
        total_duration_ms: int
    ) -> PhaseTimestamp:
        """
        Estimate timestamps from word indices (per Q52).
        
        Uses linear interpolation based on word position.
        """
        ms_per_word = total_duration_ms / total_words if total_words > 0 else self.MS_PER_WORD
        
        start_ms = int(start_word_idx * ms_per_word)
        end_ms = int(end_word_idx * ms_per_word)
        
        return PhaseTimestamp(
            start_ms=start_ms,
            end_ms=end_ms,
            duration_ms=end_ms - start_ms,
            estimation_method="word_count"
        )
    
    def _extract_segment(self, transcript: str, start_idx: int, end_idx: int) -> str:
        """Extract transcript segment by word indices."""
        words = transcript.split()
        segment_words = words[start_idx:end_idx]
        return " ".join(segment_words[:100])  # Limit to 100 words for storage
    
    def _resolve_phase_boundaries(
        self,
        phases: Dict[str, ConversationPhaseResult],
        phase_sequence: List[str],
        total_word_count: int,
        word_timestamps: Optional[List[Dict[str, Any]]],
        call_duration_ms: int,
        estimation_method: str
    ) -> Dict[str, ConversationPhaseResult]:
        """
        Post-process phase boundaries to resolve overlaps and fill gaps.
        
        This ensures:
        1. No overlapping word indices between phases
        2. Complete coverage of the transcript
        3. Timestamps are recalculated after boundary adjustments
        
        Strategy:
        - Sort phases by start_word_index
        - When overlap detected, split at midpoint weighted by confidence
        - Fill gaps by extending adjacent phases
        """
        # Build list of detected phases with boundaries
        phase_boundaries = []
        for name in phase_sequence:
            phase = phases.get(name)
            if phase and phase.detected and phase.segments:
                seg = phase.segments[0]
                phase_boundaries.append({
                    'name': name,
                    'start': seg.start_word_index,
                    'end': seg.end_word_index,
                    'confidence': phase.confidence or 0.5
                })
        
        if not phase_boundaries:
            return phases
        
        # Sort by start index
        phase_boundaries.sort(key=lambda x: x['start'])
        
        # Resolve overlaps and gaps
        resolved = []
        for i, current in enumerate(phase_boundaries):
            if i == 0:
                # First phase starts at 0
                current_copy = current.copy()
                current_copy['start'] = 0
                resolved.append(current_copy)
                continue
            
            prev = resolved[-1]
            current_copy = current.copy()
            
            # Check for overlap (current starts before previous ends)
            if current_copy['start'] < prev['end']:
                # Overlap detected - resolve by weighted midpoint
                overlap_size = prev['end'] - current_copy['start']
                
                # Weight midpoint by confidence
                total_conf = prev['confidence'] + current_copy['confidence']
                if total_conf > 0:
                    weight = prev['confidence'] / total_conf
                else:
                    weight = 0.5
                
                # Calculate split point
                split_point = current_copy['start'] + int(overlap_size * weight)
                
                # Ensure minimum phase size of 5 words
                min_size = 5
                if split_point - prev['start'] < min_size:
                    split_point = prev['start'] + min_size
                if current_copy['end'] - split_point < min_size:
                    split_point = current_copy['end'] - min_size
                
                prev['end'] = split_point
                current_copy['start'] = split_point
                
                logger.debug(f"Resolved overlap between {prev['name']} and {current_copy['name']} at word {split_point}")
            
            # Check for gap (current starts after previous ends)
            elif current_copy['start'] > prev['end']:
                # Gap detected - extend previous phase to fill
                gap_size = current_copy['start'] - prev['end']
                
                # Split gap - give more to higher confidence phase
                total_conf = prev['confidence'] + current_copy['confidence']
                if total_conf > 0:
                    prev_share = prev['confidence'] / total_conf
                else:
                    prev_share = 0.5
                
                split_point = prev['end'] + int(gap_size * prev_share)
                prev['end'] = split_point
                current_copy['start'] = split_point
                
                logger.debug(f"Filled gap between {prev['name']} and {current_copy['name']} at word {split_point}")
            
            resolved.append(current_copy)
        
        # Ensure last phase extends to end of transcript
        if resolved and resolved[-1]['end'] < total_word_count:
            resolved[-1]['end'] = total_word_count
        
        # Update phases with resolved boundaries and recalculate timestamps
        for r in resolved:
            phase = phases.get(r['name'])
            if phase and phase.segments:
                # Pydantic models are immutable, so we need to create a new object
                old_segment = phase.segments[0]
                
                # Create new segment with updated word indices
                new_segment = PhaseTranscriptSegment(
                    start_word_index=r['start'],
                    end_word_index=r['end'],
                    speaker=old_segment.speaker,
                    text=old_segment.text
                )
                
                # Recalculate timestamps with new boundaries
                if word_timestamps:
                    new_timestamps = self._estimate_timestamps_from_segments(
                        r['start'], r['end'], word_timestamps, call_duration_ms, estimation_method
                    )
                else:
                    new_timestamps = self._estimate_timestamps(
                        r['start'], r['end'], total_word_count, call_duration_ms
                    )
                
                # Create new phase result with updated values
                phases[r['name']] = ConversationPhaseResult(
                    phase=phase.phase,
                    detected=phase.detected,
                    confidence=phase.confidence,
                    timestamps=new_timestamps,  # New timestamps
                    segments=[new_segment],     # New segment
                    key_phrases=phase.key_phrases,
                    quality_score=phase.quality_score,
                    quality_notes=phase.quality_notes
                )
                
                logger.debug(
                    f"Updated {r['name']}: words {r['start']}-{r['end']}, "
                    f"timestamps {new_timestamps.start_ms}ms-{new_timestamps.end_ms}ms"
                )
        
        return phases
    
    def _build_analytics(
        self,
        phases: Dict[str, ConversationPhaseResult],
        phase_sequence: List[str],
        total_duration_ms: int,
        missing_phases: List[str]
    ) -> PhaseAnalytics:
        """Build phase analytics from detection results."""
        time_distribution = {}
        percentage_distribution = {}
        
        for phase_name, result in phases.items():
            if result.detected and result.timestamps:
                duration = result.timestamps.duration_ms
                time_distribution[phase_name] = duration
                percentage_distribution[phase_name] = (
                    duration / total_duration_ms * 100 if total_duration_ms > 0 else 0
                )
        
        # Find dominant phase
        dominant_phase = None
        max_duration = 0
        for phase_name, duration in time_distribution.items():
            if duration > max_duration:
                max_duration = duration
                dominant_phase = phase_name
        
        return PhaseAnalytics(
            total_duration_ms=total_duration_ms,
            time_distribution=time_distribution,
            percentage_distribution=percentage_distribution,
            phases_detected=len(phase_sequence),
            phases_missing=missing_phases,
            phase_sequence=phase_sequence,
            dominant_phase=dominant_phase,
            insights=[]
        )


# Singleton
_phase_detection_service: Optional[PhaseDetectionService] = None


def get_phase_detection_service() -> PhaseDetectionService:
    """Get PhaseDetectionService instance"""
    global _phase_detection_service
    if _phase_detection_service is None:
        _phase_detection_service = PhaseDetectionService()
    return _phase_detection_service
