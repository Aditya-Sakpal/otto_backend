"""
SOP Evaluation Service

Evaluates call transcripts against SOP metrics.
Uses chunking strategy to handle large numbers of metrics efficiently.
"""

import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.config import get_settings
from app.models.sop import SOPMetric, SOPMetricScore, SOPImprovementArea, SOPEvaluation


logger = logging.getLogger(__name__)


class EvaluationService:
    """Service for evaluating calls against SOP metrics"""
    
    def __init__(self):
        """Initialize evaluation service"""
        self.llm_client = None
        self.settings = get_settings()
        self._init_llm_client()
    
    def _init_llm_client(self):
        """Initialize LLM client"""
        try:
            from app.core.llm import get_llm_client
            
            self.llm_client = get_llm_client()
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
    
    async def evaluate_call_against_sop(
        self,
        transcript_chunk: str,
        sop_metrics: List[SOPMetric],
        previous_evaluations: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate call transcript chunk against SOP metrics.
        
        Uses chunking strategy: splits metrics into smaller batches for parallel
        evaluation to reduce per-call token requirements and costs.
        
        Args:
            transcript_chunk: Transcript text
            sop_metrics: List of SOP metrics to evaluate
            previous_evaluations: Previous chunk evaluations for context
            
        Returns:
            Dict with evaluation results
        """
        if not self.llm_client:
            self._init_llm_client()
            if not self.llm_client:
                logger.error("LLM client not available")
                return {"metric_scores": []}
        
        chunk_size = self.settings.SOP_METRICS_CHUNK_SIZE
        total_metrics = len(sop_metrics)
        
        # If metrics fit in one chunk, evaluate directly
        if total_metrics <= chunk_size:
            logger.info(f"SOP Evaluation: {total_metrics} metrics (single batch)")
            return await self._evaluate_metrics_chunk(
                transcript_chunk, sop_metrics, previous_evaluations
            )
        
        # Otherwise, chunk metrics and evaluate in parallel
        chunks = self._chunk_metrics(sop_metrics, chunk_size)
        logger.info(f"SOP Evaluation: {total_metrics} metrics split into {len(chunks)} chunks of ~{chunk_size}")
        
        # Run chunk evaluations in parallel
        tasks = [
            self._evaluate_metrics_chunk(transcript_chunk, chunk, previous_evaluations)
            for chunk in chunks
        ]
        
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Aggregate results from all chunks
        return self._aggregate_chunk_results(chunk_results, total_metrics)
    
    def _chunk_metrics(self, metrics: List[SOPMetric], chunk_size: int) -> List[List[SOPMetric]]:
        """Split metrics into chunks of specified size"""
        return [metrics[i:i + chunk_size] for i in range(0, len(metrics), chunk_size)]
    
    def _aggregate_chunk_results(
        self, 
        chunk_results: List[Any], 
        total_metrics: int
    ) -> Dict[str, Any]:
        """Aggregate results from multiple chunk evaluations"""
        all_metric_scores = []
        all_observations = []
        failed_chunks = 0
        
        for i, result in enumerate(chunk_results):
            if isinstance(result, Exception):
                logger.warning(f"Chunk {i+1} failed with exception: {result}")
                failed_chunks += 1
                continue
            
            if isinstance(result, dict):
                all_metric_scores.extend(result.get("metric_scores", []))
                all_observations.extend(result.get("chunk_observations", []))
        
        logger.info(f"SOP Evaluation aggregated: {len(all_metric_scores)} metric_scores "
                   f"from {len(chunk_results)} chunks ({failed_chunks} failed)")
        
        return {
            "metric_scores": all_metric_scores,
            "chunk_observations": all_observations
        }
    
    async def _evaluate_metrics_chunk(
        self,
        transcript_chunk: str,
        sop_metrics: List[SOPMetric],
        previous_evaluations: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single chunk of metrics against the transcript.
        
        This is the core LLM call - kept separate to allow chunking.
        """
        try:
            from app.core.llm import get_active_model, get_max_tokens_param
            
            # Build evaluation prompt for this chunk
            prompt = self._build_evaluation_prompt(
                transcript_chunk,
                sop_metrics,
                previous_evaluations
            )
            
            # Use configurable max tokens per chunk (smaller = cheaper)
            max_tokens = self.settings.SOP_EVAL_MAX_TOKENS_PER_CHUNK
            
            response = await self.llm_client.chat.completions.create(
                model=get_active_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at evaluating sales calls against Standard Operating Procedures (SOPs). Always respond with valid JSON only. Be concise."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                **get_max_tokens_param(max_tokens)
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            finish_reason = response.choices[0].finish_reason
            usage = response.usage
            
            # Log response details
            logger.info(f"SOP Eval chunk ({len(sop_metrics)} metrics): "
                       f"finish_reason={finish_reason}, "
                       f"prompt_tokens={usage.prompt_tokens if usage else 'N/A'}, "
                       f"completion_tokens={usage.completion_tokens if usage else 'N/A'}")
            
            # Check for truncation
            if finish_reason == 'length':
                logger.warning(f"SOP Eval chunk truncated! content_length={len(result_text) if result_text else 0}. "
                              f"Consider increasing SOP_EVAL_MAX_TOKENS_PER_CHUNK or reducing SOP_METRICS_CHUNK_SIZE.")
            
            result = self._parse_evaluation_response(result_text)
            
            metric_count = len(result.get("metric_scores", []))
            logger.debug(f"SOP Eval chunk parsed: {metric_count}/{len(sop_metrics)} metric_scores")
            
            return result
            
        except Exception as e:
            logger.error(f"Chunk evaluation error: {str(e)}")
            return {"metric_scores": []}
    
    def _build_evaluation_prompt(
        self,
        transcript_chunk: str,
        sop_metrics: List[SOPMetric],
        previous_evaluations: Optional[List[Dict[str, Any]]]
    ) -> str:
        """Build evaluation prompt"""
        
        # Format metrics for prompt
        metrics_text = []
        for metric in sop_metrics:
            metric_text = f"""
Metric: {metric.metric_name} (ID: {metric.metric_id})
Description: {metric.description}
Evaluation Method: {metric.evaluation_method}
Target: {metric.target_value}
Weight: {metric.weight}
"""
            if metric.evaluation_criteria:
                metric_text += f"Criteria: {json.dumps(metric.evaluation_criteria, indent=2)}\n"
            metrics_text.append(metric_text)
        
        previous_text = ""
        if previous_evaluations:
            previous_text = f"""
PREVIOUS CHUNK EVALUATIONS:
{json.dumps(previous_evaluations, indent=2)}
"""
        
        prompt = f"""You are evaluating a sales call against company SOP metrics.

SOP METRICS TO EVALUATE:
{chr(10).join(metrics_text)}

{previous_text}

TRANSCRIPT CHUNK:
{transcript_chunk}

For each applicable metric:
1. Score from 0.0 to 1.0 based on evaluation_criteria
2. Provide evidence quote from transcript
3. Suggest improvement if score < target
4. Determine rating (excellent/good/needs_improvement/poor)

Some metrics may not be evaluable from this chunk - mark as "not_applicable"

Return JSON:
{{
  "metric_scores": [
    {{
      "metric_id": "...",
      "score": 0.0-1.0,
      "evidence": "...",
      "rating": "...",
      "improvement_suggestion": "..." or null,
      "applicable": true/false
    }}
  ],
  "chunk_observations": ["..."]
}}

Respond ONLY with valid JSON."""
        
        return prompt
    
    def _parse_evaluation_response(self, response_text: str) -> Dict[str, Any]:
        """Parse evaluation response with aggressive error recovery"""
        import logging
        import re
        logger = logging.getLogger(__name__)
        
        # Log input for debugging
        if not response_text:
            logger.warning("_parse_evaluation_response received empty/None response_text")
            return {"metric_scores": []}
        
        logger.info(f"_parse_evaluation_response: input length={len(response_text)}, starts_with={response_text[:50] if len(response_text) > 50 else response_text}")
        
        try:
            # Extract JSON
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            logger.info(f"_parse_evaluation_response: start_idx={start_idx}, end_idx={end_idx}")
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                
                # Try parsing
                try:
                    result = json.loads(json_str)
                    return result
                except json.JSONDecodeError as e:
                    # Log the actual JSON for debugging
                    logger.warning(f"JSON parse error at position {e.pos}: {e.msg}")
                    error_context_start = max(0, e.pos - 100)
                    error_context_end = min(len(json_str), e.pos + 100)
                    logger.debug(f"JSON around error: ...{json_str[error_context_start:error_context_end]}...")
                    
                    # Attempt aggressive fixes
                    json_str_fixed = json_str
                    
                    # Fix 0: Remove control characters (newlines, tabs in strings)
                    # Replace control characters within quoted strings
                    json_str_fixed = re.sub(r'[\x00-\x1f\x7f]', ' ', json_str_fixed)
                    
                    # Fix 1: Remove trailing commas
                    json_str_fixed = re.sub(r',\s*}', '}', json_str_fixed)
                    json_str_fixed = re.sub(r',\s*]', ']', json_str_fixed)
                    
                    # Fix 2: Fix missing commas between array elements
                    json_str_fixed = re.sub(r'"\s*\n\s*"', '",\n"', json_str_fixed)
                    json_str_fixed = re.sub(r'}\s*\n\s*{', '},\n{', json_str_fixed)
                    
                    # Fix 3: Remove double commas
                    json_str_fixed = re.sub(r',,+', ',', json_str_fixed)
                    
                    # Fix 4: Remove comments (if any)
                    json_str_fixed = re.sub(r'//.*?\n', '\n', json_str_fixed)
                    json_str_fixed = re.sub(r'/\*.*?\*/', '', json_str_fixed, flags=re.DOTALL)
                    
                    # Fix 5: Fix unescaped backslashes
                    # This is tricky, but we can try to escape single backslashes that aren't already escaped
                    json_str_fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', json_str_fixed)
                    
                    # Try again
                    try:
                        result = json.loads(json_str_fixed)
                        logger.info("Successfully recovered from JSON error using auto-repair")
                        return result
                    except Exception as repair_error:
                        logger.error(f"JSON auto-repair failed: {repair_error}")
                        
                        # Last resort: Try to extract just the metric_scores array
                        try:
                            scores_match = re.search(r'"metric_scores"\s*:\s*(\[.*?\])', json_str_fixed, re.DOTALL)
                            if scores_match:
                                scores_str = scores_match.group(1)
                                # Clean the array string
                                scores_str = re.sub(r'[\x00-\x1f\x7f]', ' ', scores_str)
                                # Try to parse just the array
                                scores_array = json.loads(scores_str)
                                logger.info("Recovered metric_scores array from malformed JSON")
                                return {"metric_scores": scores_array, "chunk_observations": []}
                        except Exception as array_error:
                            logger.error(f"Failed to extract metric_scores array: {array_error}")
            
            logger.warning(f"No valid JSON found in evaluation response - returning empty metric_scores. "
                          f"Response text (first 500 chars): {response_text[:500] if response_text else 'EMPTY'}")
            return {"metric_scores": []}
            
        except Exception as e:
            logger.error(f"Failed to parse evaluation response: {e}")
            return {"metric_scores": []}
    
    async def merge_chunk_evaluations(
        self,
        chunk_evaluations: List[Dict[str, Any]],
        sop_metrics: List[SOPMetric],
        sop_id: str,
        sop_name: str,
        sop_version: Optional[int] = None,
        sop_version_history_id: Optional[str] = None
    ) -> SOPEvaluation:
        """
        Merge evaluations from all chunks into final SOP compliance score.
        
        Args:
            chunk_evaluations: List of chunk evaluation results
            sop_metrics: Original SOP metrics
            sop_id: SOP document ID
            sop_name: SOP document name
            sop_version: SOP version number (for tracking which version was used)
            sop_version_history_id: SOP version history ID (for historical lookup)
            
        Returns:
            SOPEvaluation object
        """
        # Aggregate scores per metric
        metric_aggregates: Dict[str, Dict[str, Any]] = {}
        
        for chunk_eval in chunk_evaluations:
            for score_entry in chunk_eval.get("metric_scores", []):
                if not score_entry.get("applicable", True):
                    continue
                
                metric_id = score_entry.get("metric_id")
                if not metric_id:
                    continue
                
                if metric_id not in metric_aggregates:
                    metric_aggregates[metric_id] = {
                        "scores": [],
                        "evidences": [],
                        "suggestions": []
                    }
                
                metric_aggregates[metric_id]["scores"].append(score_entry.get("score", 0))
                
                evidence = score_entry.get("evidence")
                if evidence:
                    metric_aggregates[metric_id]["evidences"].append(evidence)
                
                suggestion = score_entry.get("improvement_suggestion")
                if suggestion:
                    metric_aggregates[metric_id]["suggestions"].append(suggestion)
        
        # Calculate final scores
        final_scores: List[SOPMetricScore] = []
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for metric in sop_metrics:
            metric_id = metric.metric_id
            agg = metric_aggregates.get(metric_id)
            
            if agg and agg["scores"]:
                # Average score across chunks
                avg_score = sum(agg["scores"]) / len(agg["scores"])
                weight = metric.weight
                weighted_score = avg_score * weight
                
                total_weighted_score += weighted_score
                total_weight += weight
                
                # Determine rating
                rating = self._get_rating(avg_score, metric.evaluation_criteria)
                
                final_scores.append(SOPMetricScore(
                    metric_id=metric_id,
                    metric_name=metric.metric_name,
                    score=round(avg_score, 2),
                    target=metric.target_value,
                    weight=weight,
                    weighted_score=round(weighted_score, 3),
                    rating=rating,
                    evidence=agg["evidences"][0] if agg["evidences"] else None,
                    improvement_suggestion=agg["suggestions"][0] if agg["suggestions"] else None
                ))
        
        # Calculate overall compliance
        overall_compliance = total_weighted_score / total_weight if total_weight > 0 else 0.0
        
        # Determine strengths and improvement areas
        strengths = [s for s in final_scores if s.score >= 0.8]
        improvement_needed = [s for s in final_scores if s.score < 0.7]
        
        top_strengths = [
            f"{s.metric_name}: {s.rating}"
            for s in sorted(strengths, key=lambda x: -x.score)[:3]
        ]
        
        improvement_areas = [
            SOPImprovementArea(
                area=s.metric_name,
                suggestion=s.improvement_suggestion or "Focus on improving this area",
                current_score=s.score,
                related_metrics=[s.metric_id]
            )
            for s in sorted(improvement_needed, key=lambda x: x.score)[:3]
        ]
        
        return SOPEvaluation(
            sop_id=sop_id,
            sop_name=sop_name,
            sop_version=sop_version,
            sop_version_history_id=sop_version_history_id,
            overall_compliance=round(overall_compliance, 2),
            metric_scores=final_scores,
            top_strengths=top_strengths,
            improvement_areas=improvement_areas,
            evaluated_at=datetime.utcnow()
        )
    
    def _get_rating(
        self,
        score: float,
        evaluation_criteria: Optional[Dict[str, Any]]
    ) -> str:
        """Determine rating from score and criteria"""
        
        if not evaluation_criteria:
            # Default rating based on score
            if score >= 0.9:
                return "excellent"
            elif score >= 0.7:
                return "good"
            elif score >= 0.5:
                return "needs_improvement"
            else:
                return "poor"
        
        # Use criteria score ranges
        for rating_name in ["excellent", "good", "needs_improvement", "poor"]:
            criteria = evaluation_criteria.get(rating_name)
            if not criteria or not isinstance(criteria, dict):
                continue
            
            score_range = criteria.get("score_range", [])
            if len(score_range) == 2:
                min_score, max_score = score_range
                if min_score <= score <= max_score:
                    return rating_name
        
        # Fallback
        return "good" if score >= 0.7 else "needs_improvement"

