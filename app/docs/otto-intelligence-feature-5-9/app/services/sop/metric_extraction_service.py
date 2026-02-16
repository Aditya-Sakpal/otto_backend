"""
SOP Metric Extraction Service

LLM-based extraction of performance metrics from SOP documents using rolling context.
"""

import logging
import json
from typing import List, Dict, Any, Optional

from app.config import settings
from app.models.sop import SOPChunk, SOPMetric


logger = logging.getLogger(__name__)


class MetricExtractionService:
    """Service for extracting performance metrics from SOP documents"""
    
    def __init__(self):
        """Initialize metric extraction service"""
        self.llm_client = None
        self._init_llm_client()
    
    def _init_llm_client(self):
        """Initialize LLM client"""
        try:
            from app.core.llm import get_llm_client
            
            self.llm_client = get_llm_client()
        except Exception as e:
            logger.error(f"Failed to initialize LLM client: {e}")
    
    async def extract_metrics_rolling(
        self,
        chunks: List[SOPChunk],
        sop_id: str
    ) -> List[SOPMetric]:
        """
        Extract metrics from SOP chunks using rolling context.
        
        Each chunk builds on previous extraction to:
        1. Discover new metrics
        2. Refine existing metric definitions
        3. Merge duplicate metrics
        
        Args:
            chunks: List of SOP chunks
            sop_id: SOP document ID
            
        Returns:
            List of extracted SOPMetric objects
        """
        if not self.llm_client:
            logger.error("LLM client not available for metric extraction")
            return []
        
        accumulated_metrics = []
        
        for i, chunk in enumerate(chunks):
            logger.info(f"Extracting metrics from chunk {i+1}/{len(chunks)}")
            
            try:
                # Build context
                context = {
                    "previous_metrics": accumulated_metrics,
                    "chunk_text": chunk.text,
                    "chunk_index": i + 1,
                    "total_chunks": len(chunks),
                    "section_title": chunk.section_title
                }
                
                # Extract metrics from this chunk
                chunk_metrics = await self._extract_from_chunk(context)
                
                # Merge with accumulated metrics
                accumulated_metrics = self._merge_metrics(
                    accumulated_metrics,
                    chunk_metrics.get("new_metrics", []),
                    chunk_metrics.get("updated_metrics", [])
                )
                
            except Exception as e:
                logger.error(f"Error extracting from chunk {i+1}: {str(e)}")
                continue
        
        # Convert to SOPMetric objects
        metrics = []
        for metric_dict in accumulated_metrics:
            try:
                metric = SOPMetric(**metric_dict)
                metrics.append(metric)
            except Exception as e:
                logger.error(f"Error creating SOPMetric: {e}")
        
        return metrics
    
    async def _extract_from_chunk(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metrics from a single chunk"""
        
        # Build prompt
        prompt = self._build_extraction_prompt(context)
        
        try:
            from app.core.llm import get_active_model, get_max_tokens_param
            
            # Call LLM
            response = await self.llm_client.chat.completions.create(
                model=get_active_model(),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at extracting performance metrics from Standard Operating Procedures (SOPs)."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                **get_max_tokens_param(4000)
            )
            
            # Parse response
            result_text = response.choices[0].message.content
            result = self._parse_extraction_response(result_text)
            
            return result
            
        except Exception as e:
            logger.error(f"LLM extraction error: {str(e)}")
            return {"new_metrics": [], "updated_metrics": []}
    
    def _build_extraction_prompt(self, context: Dict[str, Any]) -> str:
        """Build LLM prompt for metric extraction"""
        
        previous_metrics_text = ""
        if context["previous_metrics"]:
            previous_metrics_text = f"""
PREVIOUS EXTRACTED METRICS:
{json.dumps(context['previous_metrics'], indent=2)}
"""
        
        prompt = f"""You are extracting performance metrics from an SOP document.

{previous_metrics_text}

NEW SECTION TO ANALYZE:
Section: {context['section_title']}
Chunk {context['chunk_index']} of {context['total_chunks']}

{context['chunk_text']}

Extract and MERGE performance metrics. For each metric include:
- metric_id: Unique identifier (snake_case)
- metric_name: Human-readable name
- description: What this metric measures
- evaluation_method: How to evaluate (from document)
- target_value: Expected score/value if specified (default 1.0)
- weight: Relative importance (0.0-1.0, default 0.1)
- applicable_roles: Which roles this applies to (list)
- evaluation_criteria: Specific criteria for scoring (dict with keys: excellent, good, needs_improvement, poor)
- source_section: Section where this was found
- category: Category of metric (e.g., "opening", "discovery", "closing")

Return JSON with:
{{
    "new_metrics": [array of NEW metrics found in this chunk],
    "updated_metrics": [array of UPDATES to existing metrics]
}}

For updated_metrics, include the metric_id and only the fields that should be updated.

If no metrics are found, return empty arrays.

Respond ONLY with valid JSON."""
        
        return prompt
    
    def _parse_extraction_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM extraction response"""
        try:
            # Extract JSON from response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}')
            
            if start_idx >= 0 and end_idx > start_idx:
                json_str = response_text[start_idx:end_idx + 1]
                result = json.loads(json_str)
                
                # Ensure arrays exist
                if "new_metrics" not in result:
                    result["new_metrics"] = []
                if "updated_metrics" not in result:
                    result["updated_metrics"] = []
                
                return result
            else:
                logger.warning("No JSON found in extraction response")
                return {"new_metrics": [], "updated_metrics": []}
                
        except Exception as e:
            logger.error(f"Failed to parse extraction response: {e}")
            return {"new_metrics": [], "updated_metrics": []}
    
    def _merge_metrics(
        self,
        existing: List[Dict[str, Any]],
        new: List[Dict[str, Any]],
        updates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Merge new and updated metrics with existing"""
        
        # Create map of existing metrics by ID
        metrics_map = {m.get("metric_id"): m for m in existing if "metric_id" in m}
        
        # Apply updates to existing metrics
        for update in updates:
            metric_id = update.get("metric_id")
            if metric_id and metric_id in metrics_map:
                # Merge update into existing metric
                metrics_map[metric_id].update(update)
        
        # Add new metrics (with deduplication)
        for new_metric in new:
            metric_id = new_metric.get("metric_id")
            if not metric_id:
                continue
            
            if metric_id not in metrics_map:
                # Check for semantic similarity (simplified - just check name)
                similar = self._find_similar_metric(new_metric, list(metrics_map.values()))
                
                if similar:
                    # Merge with similar metric
                    similar_id = similar.get("metric_id")
                    if similar_id:
                        metrics_map[similar_id] = self._merge_similar_metrics(
                            metrics_map[similar_id],
                            new_metric
                        )
                else:
                    # Add as new metric
                    metrics_map[metric_id] = new_metric
        
        return list(metrics_map.values())
    
    def _find_similar_metric(
        self,
        new_metric: Dict[str, Any],
        existing_metrics: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find similar metric (basic name matching)"""
        
        new_name = new_metric.get("metric_name", "").lower()
        if not new_name:
            return None
        
        for metric in existing_metrics:
            existing_name = metric.get("metric_name", "").lower()
            if not existing_name:
                continue
            
            # Simple similarity check
            if new_name == existing_name or new_name in existing_name or existing_name in new_name:
                return metric
        
        return None
    
    def _merge_similar_metrics(
        self,
        existing: Dict[str, Any],
        new: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge similar metrics, preferring more complete information"""
        
        merged = existing.copy()
        
        # Prefer longer/more complete fields
        for key, new_value in new.items():
            if key not in merged or not merged[key]:
                merged[key] = new_value
            elif isinstance(new_value, str) and len(new_value) > len(str(merged[key])):
                merged[key] = new_value
            elif isinstance(new_value, (list, dict)) and len(new_value) > len(merged.get(key, [])):
                merged[key] = new_value
        
        return merged
    
    async def normalize_metrics(self, metrics: List[SOPMetric]) -> List[SOPMetric]:
        """
        Normalize and validate metrics.
        
        - Ensure weights sum to approximately 1.0
        - Assign default values where missing
        - Deduplicate by metric_id
        """
        if not metrics:
            return []
        
        # Deduplicate by metric_id
        seen_ids = set()
        unique_metrics = []
        for metric in metrics:
            if metric.metric_id not in seen_ids:
                seen_ids.add(metric.metric_id)
                unique_metrics.append(metric)
        
        # Calculate total weight
        total_weight = sum(m.weight for m in unique_metrics)
        
        # Normalize weights if needed
        if total_weight > 0 and abs(total_weight - 1.0) > 0.05:
            logger.info(f"Normalizing weights (current total: {total_weight:.2f})")
            for metric in unique_metrics:
                metric.weight = metric.weight / total_weight
        
        # Ensure all have evaluation criteria
        for metric in unique_metrics:
            if not metric.evaluation_criteria:
                metric.evaluation_criteria = {
                    "excellent": {"score_range": [0.9, 1.0], "description": "Exceeds expectations"},
                    "good": {"score_range": [0.7, 0.89], "description": "Meets expectations"},
                    "needs_improvement": {"score_range": [0.5, 0.69], "description": "Below expectations"},
                    "poor": {"score_range": [0.0, 0.49], "description": "Significantly below expectations"}
                }
        
        return unique_metrics

