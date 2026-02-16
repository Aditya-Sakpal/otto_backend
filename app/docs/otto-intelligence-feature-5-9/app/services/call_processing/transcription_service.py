"""
Transcription Service

Service for transcribing audio using external APIs (Shunya/AssemblyAI) with LLM-based diarization fallback.
"""

from typing import Dict, Any, Optional, List
import logging
import aiohttp
from ...config import get_settings
from .diarization_service import get_diarization_service

settings = get_settings()
logger = logging.getLogger(__name__)


class TranscriptionService:
    """Service for audio transcription"""
    
    def __init__(self):
        self.shunya_api_url = settings.SHUNYA_API_URL
        self.shunya_api_key = settings.SHUNYA_API_KEY
        self.assemblyai_api_key = settings.ASSEMBLYAI_API_KEY
        self.use_shunya = bool(self.shunya_api_url and self.shunya_api_key)
        self.diarization_service = get_diarization_service()
        
        # Diarization settings from config
        self.enable_diarization = settings.ENABLE_DIARIZATION
        self.enable_llm_fallback = settings.ENABLE_LLM_DIARIZATION_FALLBACK
        self.enable_speaker_labeling = settings.ENABLE_LLM_SPEAKER_LABELING
        self.enable_hybrid_verification = settings.ENABLE_HYBRID_DIARIZATION_VERIFICATION
        self.diarization_priority = settings.DIARIZATION_PRIORITY.lower()  # "api" or "llm"
    
    async def transcribe(
        self,
        audio_path: str,
        enable_diarization: bool = None,
        call_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transcribe audio file with diarization and speaker labeling.
        
        Priority logic:
        - If DIARIZATION_PRIORITY="api": Try API first, fallback to LLM
        - If DIARIZATION_PRIORITY="llm": Try LLM first, fallback to API
        
        Args:
            audio_path: Path to audio file
            enable_diarization: Enable speaker diarization (uses config default if None)
            call_context: Context about the call for better speaker labeling
            
        Returns:
            Dict with transcript, segments (diarized and labeled), and metadata
        """
        # Use config default if not specified
        if enable_diarization is None:
            enable_diarization = self.enable_diarization
        
        # Priority: LLM diarization first
        if self.diarization_priority == "llm":
            logger.info("Diarization priority: LLM first, API fallback")
            
            # Try LLM diarization first
            try:
                result = await self._transcribe_with_llm_priority(audio_path, call_context)
                return await self._post_process_transcription(result, call_context)
            except Exception as e:
                logger.warning(f"LLM-priority transcription failed: {e}, falling back to API")
        
        # Priority: API diarization first (default)
        logger.info("Diarization priority: API first, LLM fallback")
        
        # Try Shunya first
        if self.use_shunya:
            try:
                result = await self._transcribe_with_shunya(audio_path, enable_diarization)
                return await self._post_process_transcription(result, call_context)
            except Exception as e:
                logger.warning(f"Shunya transcription failed: {e}, falling back to AssemblyAI or mock")
        
        # Try AssemblyAI
        if self.assemblyai_api_key:
            try:
                result = await self._transcribe_with_assemblyai(audio_path, enable_diarization)
                return await self._post_process_transcription(result, call_context)
            except Exception as e:
                logger.warning(f"AssemblyAI transcription failed: {e}, falling back to mock")
        
        # Fallback: Return mock transcript for testing
        # result = await self._mock_transcription(audio_path)
        # return await self._post_process_transcription(result, call_context)
        return None
    
    async def _transcribe_with_shunya(
        self,
        audio_path: str,
        enable_diarization: bool
    ) -> Dict[str, Any]:
        """Transcribe using Shunya API"""
        try:
            async with aiohttp.ClientSession() as session:
                # Upload audio file using correct Shunya API format
                with open(audio_path, 'rb') as f:
                    form_data = aiohttp.FormData()
                    form_data.add_field('file', f, filename='audio.wav')
                    form_data.add_field('language_code', 'en')
                    form_data.add_field('enable_diarization', str(enable_diarization).lower())
                    form_data.add_field('chunk_size', '120')
                    
                    headers = {'X-API-Key': self.shunya_api_key}
                    
                    async with session.post(
                        self.shunya_api_url,  # Already contains /transcribe
                        data=form_data,
                        headers=headers
                    ) as response:
                        if response.status != 200:
                            raise Exception(f"Shunya API error: {await response.text()}")
                        
                        result = await response.json()
                        
                        # Check if transcription was successful
                        if not result.get("success"):
                            raise Exception(f"Shunya transcription failed: {result}")
                        
                        # Convert Shunya format to our format
                        segments = []
                        for seg in result.get("segments", []):
                            segments.append({
                                "speaker": seg.get("speaker", "SPEAKER_00"),
                                "text": seg.get("text", ""),
                                "start_time": seg.get("start", 0.0),
                                "end_time": seg.get("end", 0.0)
                            })
                        
                        transcript_text = result.get("text", "")

                        logger.info(f"Shunya transcription result: {result}")
                        
                        return {
                            "transcript": transcript_text,
                            "segments": segments,
                            "duration": int(result.get("total_time", 0)),
                            "word_count": len(transcript_text.split())
                        }
        
        except Exception as e:
            raise Exception(f"Transcription with Shunya failed: {str(e)}")
    
    async def _transcribe_with_assemblyai(
        self,
        audio_path: str,
        enable_diarization: bool
    ) -> Dict[str, Any]:
        """Transcribe using AssemblyAI"""
        try:
            # AssemblyAI requires uploading file first, then submitting transcription job
            async with aiohttp.ClientSession() as session:
                # 1. Upload file
                headers = {'authorization': self.assemblyai_api_key}
                
                with open(audio_path, 'rb') as f:
                    async with session.post(
                        'https://api.assemblyai.com/v2/upload',
                        headers=headers,
                        data=f
                    ) as response:
                        if response.status != 200:
                            raise Exception(f"AssemblyAI upload error: {await response.text()}")
                        
                        upload_result = await response.json()
                        audio_url = upload_result['upload_url']
                
                # 2. Submit transcription job
                transcript_request = {
                    'audio_url': audio_url,
                    'speaker_labels': enable_diarization
                }
                
                async with session.post(
                    'https://api.assemblyai.com/v2/transcript',
                    headers=headers,
                    json=transcript_request
                ) as response:
                    if response.status != 200:
                        raise Exception(f"AssemblyAI transcribe error: {await response.text()}")
                    
                    transcript_result = await response.json()
                    transcript_id = transcript_result['id']
                
                # 3. Poll for completion (simplified - in production, use webhooks)
                import asyncio
                while True:
                    await asyncio.sleep(5)
                    
                    async with session.get(
                        f'https://api.assemblyai.com/v2/transcript/{transcript_id}',
                        headers=headers
                    ) as response:
                        result = await response.json()
                        
                        if result['status'] == 'completed':
                            segments = []
                            if enable_diarization and 'utterances' in result:
                                segments = [
                                    {
                                        "speaker": f"Speaker {u['speaker']}",
                                        "text": u['text'],
                                        "start_time": u['start'] / 1000.0,
                                        "end_time": u['end'] / 1000.0
                                    }
                                    for u in result['utterances']
                                ]

                            logger.info(f"AssemblyAI transcription result: {result}")
                            
                            return {
                                "transcript": result.get("text", ""),
                                "segments": segments,
                                "duration": result.get("audio_duration"),
                                "word_count": len(result.get("text", "").split())
                            }
                        
                        elif result['status'] == 'error':
                            raise Exception(f"AssemblyAI transcription failed: {result.get('error')}")
        
        except Exception as e:
            raise Exception(f"Transcription with AssemblyAI failed: {str(e)}")
    
    async def _transcribe_with_llm_priority(
        self,
        audio_path: str,
        call_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Transcribe with LLM diarization as primary method.
        
        Steps:
        1. Get basic transcription from any available API (with diarization for timestamps)
        2. Apply LLM diarization to the plain text for better speaker identification
        3. Apply LLM speaker labeling
        4. Preserve original API segments with timestamps for phase detection
        
        Falls back to API diarization if LLM fails.
        """
        logger.info("Using LLM-priority diarization strategy")
        
        # Step 1: Get transcript WITH diarization to preserve timestamps
        transcript_text = None
        original_segments_with_timestamps = []
        api_used = None
        
        # Try Shunya WITH diarization to get timestamps
        if self.use_shunya:
            try:
                result = await self._transcribe_with_shunya(audio_path, enable_diarization=True)
                transcript_text = result.get("transcript", "")
                original_segments_with_timestamps = result.get("segments", [])
                api_used = "shunya"
                logger.info(f"Got transcript from Shunya ({len(transcript_text)} chars, {len(original_segments_with_timestamps)} segments with timestamps)")
            except Exception as e:
                logger.warning(f"Shunya failed: {e}")
        
        # Try AssemblyAI WITH diarization
        if not transcript_text and self.assemblyai_api_key:
            try:
                result = await self._transcribe_with_assemblyai(audio_path, enable_diarization=True)
                transcript_text = result.get("transcript", "")
                original_segments_with_timestamps = result.get("segments", [])
                api_used = "assemblyai"
                logger.info(f"Got transcript from AssemblyAI ({len(transcript_text)} chars, {len(original_segments_with_timestamps)} segments with timestamps)")
            except Exception as e:
                logger.warning(f"AssemblyAI failed: {e}")
        
        if not transcript_text:
            raise Exception("Failed to get transcript from any source")
        
        # Step 2: Apply LLM diarization for better speaker identification
        logger.info("Applying LLM diarization for speaker identification")
        llm_segments = await self.diarization_service.diarize_transcript(transcript_text)
        
        # Step 3: Build result with BOTH segment types
        return {
            "transcript": transcript_text,
            "segments": llm_segments,  # LLM-diarized segments (better speaker identification, no timestamps)
            "segments_with_timestamps": original_segments_with_timestamps,  # Original API segments (timestamps preserved)
            "duration": 0,  # Will be calculated from segments_with_timestamps if available
            "word_count": len(transcript_text.split()),
            "diarization_method": "llm_primary",
            "api_used": api_used,
            "has_timestamped_segments": len(original_segments_with_timestamps) > 0
        }
    
    async def _post_process_transcription(
        self,
        result: Dict[str, Any],
        call_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Post-process transcription with LLM-based diarization and speaker labeling.
        
        HYBRID APPROACH (when enabled):
        1. If API provides diarization → Verify & enhance with LLM
        2. If no diarization → LLM diarization from scratch
        3. Always label speakers if enabled
        4. Preserve original timestamped segments if available
        
        This approach combines the strengths of both methods:
        - API: Accurate timestamps, fast
        - LLM: Better speaker identification, error correction
        """
        transcript = result.get("transcript", "")
        segments = result.get("segments", [])
        segments_with_timestamps = result.get("segments_with_timestamps", [])
        diarization_method = result.get("diarization_method", "unknown")
        
        logger.info(f"Post-processing transcription: {len(segments)} segments, method: {diarization_method}")
        
        # Check if we have diarization
        has_diarization = self.diarization_service.has_diarization(segments)
        
        # Step 1: Handle diarization based on what we have
        if has_diarization and self.enable_hybrid_verification and diarization_method != "llm_primary":
            # HYBRID: API provided diarization, verify and enhance with LLM
            logger.info("Using hybrid verification: API diarization + LLM enhancement")
            verification_result = await self.diarization_service.verify_and_enhance_diarization(
                segments,
                transcript
            )
            
            segments = verification_result["segments"]
            result["segments"] = segments
            result["diarization_method"] = "api_hybrid"
            result["diarization_quality"] = verification_result["quality_score"]
            result["diarization_issues_found"] = verification_result["issues_found"]
            result["diarization_enhancements"] = verification_result["enhancements_made"]
            
        elif not has_diarization and self.enable_llm_fallback and diarization_method != "llm_primary":
            # No diarization from API, use LLM fallback
            logger.info("No diarization found, using LLM fallback")
            segments = await self.diarization_service.diarize_transcript(transcript)
            result["segments"] = segments
            result["diarization_method"] = "llm_fallback"
            
        elif diarization_method == "llm_primary":
            # Already diarized by LLM (priority=llm)
            result["diarization_method"] = "llm_primary"
            # segments_with_timestamps should already be set
            
        elif has_diarization:
            # Has diarization but hybrid verification disabled
            result["diarization_method"] = "api"
            
        else:
            # No diarization and fallback disabled
            result["diarization_method"] = "none"
        
        # Step 2: LLM-based speaker labeling (SPEAKER_00 → customer_rep, etc.)
        if segments and self.enable_speaker_labeling:
            logger.info("Applying LLM speaker labeling")
            segments = await self.diarization_service.label_speakers(segments, call_context)
            result["segments"] = segments
            result["speaker_labeling_method"] = "llm"
        else:
            result["speaker_labeling_method"] = "original"
        
        # Step 3: Format transcript with speaker labels
        if segments:
            formatted_transcript = self.diarization_service.format_diarized_transcript(segments)
            result["formatted_transcript"] = formatted_transcript
            
            # Update main transcript if it was plain text or enhanced
            if not has_diarization or diarization_method in ["llm_fallback", "llm_primary", "api_hybrid"]:
                result["transcript"] = formatted_transcript
        
        # Step 4: Preserve timestamped segments if they exist
        if segments_with_timestamps:
            logger.info(f"Preserving {len(segments_with_timestamps)} timestamped segments for phase detection")
            result["segments_with_timestamps"] = segments_with_timestamps
        
        logger.info(f"Post-processing complete: {result.get('diarization_method')} diarization, {result.get('speaker_labeling_method')} labeling")
        
        return result
    
    async def _mock_transcription(self, audio_path: str) -> Dict[str, Any]:
        """Mock transcription for testing - detailed roofing call"""
        # Longer, more realistic transcript for testing rolling summarization
        transcript = """Speaker 1 (customer_rep): Thank you for calling Arizona Roofers, this is Travis speaking. How can I help you today?

Speaker 2 (home_owner): Hi Travis, my name is Kevin. I'm calling because I have a leaking roof issue. It's been giving me problems for the past few weeks.

Speaker 1 (customer_rep): I'm sorry to hear that, Kevin. A leaking roof is definitely something we need to address quickly. Can you tell me more about where the leak is located and what type of roof you have?

Speaker 2 (home_owner): Sure. It's a flat roof over my patio area. The house was built in 2006, so the roof is about 20 years old now. I've noticed water stains on the ceiling and some dripping when it rains.

Speaker 1 (customer_rep): Got it. Flat roofs can be tricky, especially after 20 years. Have you had any recent work done on the roof, like solar panel installation or any repairs?

Speaker 2 (home_owner): Actually yes, I do have solar panels on the roof. But they were installed a few years ago and the leak just started recently, so I don't think they're the cause.

Speaker 1 (customer_rep): That's good to know. Solar panels can sometimes affect roofing, but if they've been there for a while without issues, you're probably right. Now, let me check our schedule to see when we can get someone out to inspect the roof and provide you with a quote.

Speaker 2 (home_owner): That sounds good. How soon can you come out?

Speaker 1 (customer_rep): Well, Kevin, I need to be upfront with you. We're currently booked out for about 7 to 9 weeks for new projects. We've been really busy this season.

Speaker 2 (home_owner): Wow, 7 to 9 weeks? That's a long time. I was hoping to get this fixed sooner rather than later.

Speaker 1 (customer_rep): I completely understand your concern. A leaking roof isn't something you want to wait on. Let me suggest a couple of options. First, if it's an emergency situation where the leak is causing significant damage, we do have an emergency repair service that might be able to get out sooner, though there is an additional fee for that.

Speaker 2 (home_owner): Hmm, I'm not sure if I'd call it an emergency. It's definitely a problem, but the house isn't flooding or anything.

Speaker 1 (customer_rep): That's fair. Another option I can suggest is to look for a local roofing handyman or smaller contractor who might be able to patch it up temporarily or handle the repair more quickly. We specialize in larger residential and commercial projects, which is why our schedule is so full.

Speaker 2 (home_owner): That makes sense. I might look into that option. If I can't find anyone, can I call you back and get on the schedule for the 7 to 9 week timeframe?

Speaker 1 (customer_rep): Absolutely, Kevin. I'll make a note in our system with your information, and if you decide to go with us, just give us a call back and we'll get you scheduled. We'll also send you a follow-up email with some information about maintenance tips for flat roofs in the meantime.

Speaker 2 (home_owner): That would be helpful, thanks. So just to confirm, if I call back, you can book me for a repair in about 7 to 9 weeks?

Speaker 1 (customer_rep): That's correct. We'll schedule an inspection first, and then depending on what we find, we can schedule the actual repair. The whole process usually takes a couple of weeks from inspection to completion.

Speaker 2 (home_owner): Okay, I understand. Let me think about it and see if I can find someone local. If not, I'll definitely call you back.

Speaker 1 (customer_rep): Perfect, Kevin. Is there anything else I can help you with today?

Speaker 2 (home_owner): No, that's all. Thanks for your time and being honest about the timeline.

Speaker 1 (customer_rep): You're very welcome. Good luck with finding a solution, and don't hesitate to reach out if you need us. Have a great day!

Speaker 2 (home_owner): You too, bye.

Speaker 1 (customer_rep): Goodbye."""

        segments = [
            {"speaker": "customer_rep", "text": "Thank you for calling Arizona Roofers, this is Travis speaking. How can I help you today?", "start_time": 0.0, "end_time": 5.2},
            {"speaker": "home_owner", "text": "Hi Travis, my name is Kevin. I'm calling because I have a leaking roof issue. It's been giving me problems for the past few weeks.", "start_time": 5.5, "end_time": 12.8},
            {"speaker": "customer_rep", "text": "I'm sorry to hear that, Kevin. A leaking roof is definitely something we need to address quickly. Can you tell me more about where the leak is located and what type of roof you have?", "start_time": 13.0, "end_time": 22.5},
            {"speaker": "home_owner", "text": "Sure. It's a flat roof over my patio area. The house was built in 2006, so the roof is about 20 years old now. I've noticed water stains on the ceiling and some dripping when it rains.", "start_time": 22.8, "end_time": 35.2},
            {"speaker": "customer_rep", "text": "Got it. Flat roofs can be tricky, especially after 20 years. Have you had any recent work done on the roof, like solar panel installation or any repairs?", "start_time": 35.5, "end_time": 45.0},
            {"speaker": "home_owner", "text": "Actually yes, I do have solar panels on the roof. But they were installed a few years ago and the leak just started recently, so I don't think they're the cause.", "start_time": 45.3, "end_time": 55.0},
        ]
        
        return {
            "transcript": transcript,
            "segments": segments,
            "duration": 240,  # 4 minutes
            "word_count": len(transcript.split())
        }


# Singleton instance
_transcription_service: Optional[TranscriptionService] = None


def get_transcription_service() -> TranscriptionService:
    """Get singleton transcription service instance"""
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService()
    return _transcription_service

