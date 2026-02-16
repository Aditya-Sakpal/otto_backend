"""
Lead Scoring Service - BANT-based lead qualification scoring.

Implements the BANT (Budget, Authority, Need, Timeline) scoring framework
with objection penalties and bonus points.

Based on Product Requirements Decision Log:
- Q25-Q36: BANT scoring decisions
- Fixed thresholds: Hot 75-100, Warm 50-74, Cold 0-49
- Dynamic recalculation on each interaction
- Full score breakdown for explainability
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
import logging

from ....models.enums import LeadBand, ObjectionSeverity


logger = logging.getLogger(__name__)


# ============================================================================
# SCORE BREAKDOWN MODELS
# ============================================================================

class ScoreBreakdown(BaseModel):
    """Detailed score breakdown for a single component - for explainability."""
    component: str = Field(..., description="BANT component or bonus/penalty type")
    points_possible: int = Field(..., description="Maximum points for this component")
    points_earned: Optional[int] = Field(None, description="Points earned (None = not determined)")
    reason: str = Field(..., description="Human-readable explanation")
    evidence: Optional[str] = Field(None, description="Supporting evidence from transcript")


class LeadScore(BaseModel):
    """Complete lead score with full breakdown for explainability."""
    total_score: int = Field(..., ge=0, le=100, description="Final score 0-100")
    lead_band: LeadBand = Field(..., description="Hot/Warm/Cold classification")
    breakdown: List[ScoreBreakdown] = Field(default_factory=list, description="Score breakdown per component")
    algorithm_version: str = Field(default="1.0", description="Scoring algorithm version")
    calculated_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: str = Field(default="high", description="high/medium/low based on data completeness")
    
    class Config:
        use_enum_values = True


# ============================================================================
# LEAD SCORING SERVICE
# ============================================================================

class LeadScoringService:
    """
    Calculate BANT-based lead scores.
    
    Scoring Framework:
    - Base BANT: 25 points each (Budget, Authority, Need, Timeline) = 100 total
    - Objection Penalties: Variable by severity and type
    - Bonus Points: Urgency, referrals, inbound calls, explicit needs
    
    Thresholds (Fixed - per manager decision Q29):
    - Hot: 75-100
    - Warm: 50-74
    - Cold: 0-49
    """
    
    ALGORITHM_VERSION = "1.0"
    
    # Base BANT weights (25 points each = 100 total)
    BANT_WEIGHTS = {
        "budget": 25,
        "authority": 25,
        "need": 25,
        "timeline": 25
    }
    
    # Objection penalties by severity (per Q26)
    OBJECTION_PENALTIES = {
        "high": -10,
        "medium": -5,
        "low": -2
    }
    
    # Type-specific objection multipliers (per Q26)
    OBJECTION_TYPE_MULTIPLIERS = {
        "price": 1.5,       # Price objections hurt more
        "competitor": 1.2,  # Competition is concerning
        "timing": 1.0,      # Timing is neutral
        "trust": 1.3,       # Trust issues are serious
        "authority": 1.1,   # Need to consult others
        "need": 0.8,        # Not sure they need it - less severe
        "other": 1.0
    }
    
    # Bonus points (per Q27)
    BONUSES = {
        "urgency_high": 10,              # "ASAP", "emergency", "immediately"
        "urgency_medium": 5,             # "soon", "within a month"
        "referral": 10,                  # Referred by existing customer
        "inbound": 5,                    # Customer initiated contact
        "multiple_decision_makers": 5,  # More than one DM involved positively
        "explicit_need": 5               # "I need", "we need", "must have"
    }
    
    # Band thresholds (per Q28 - fixed, not customizable per Q29)
    BAND_THRESHOLDS = {
        "hot": 75,    # 75-100
        "warm": 50,   # 50-74
        "cold": 0     # 0-49
    }
    
    def calculate_score(
        self,
        qualification: Dict[str, Any],
        objections: List[Dict[str, Any]],
        call_metadata: Dict[str, Any]
    ) -> LeadScore:
        """
        Calculate lead score based on BANT framework.
        
        Args:
            qualification: Dict with bant_scores, budget_mentioned, decision_maker, urgency, timeline
            objections: List of objections with severity, category, and overcome status
            call_metadata: Dict with is_inbound, is_referral, direction, etc.
        
        Returns:
            LeadScore with total score, band, and full breakdown
        """
        breakdown = []
        total_score = 0
        available_factors = 0
        
        # Get BANT scores from qualification data
        bant_scores = qualification.get("bant_scores", {})
        
        # === BUDGET (25 points) ===
        budget_score = self._score_budget(qualification, bant_scores)
        breakdown.append(budget_score)
        if budget_score.points_earned is not None:
            total_score += budget_score.points_earned
            available_factors += 1
        
        # === AUTHORITY (25 points) ===
        authority_score = self._score_authority(qualification, bant_scores)
        breakdown.append(authority_score)
        if authority_score.points_earned is not None:
            total_score += authority_score.points_earned
            available_factors += 1
        
        # === NEED (25 points) ===
        need_score = self._score_need(qualification, bant_scores)
        breakdown.append(need_score)
        if need_score.points_earned is not None:
            total_score += need_score.points_earned
            available_factors += 1
        
        # === TIMELINE (25 points) ===
        timeline_score = self._score_timeline(qualification, bant_scores)
        breakdown.append(timeline_score)
        if timeline_score.points_earned is not None:
            total_score += timeline_score.points_earned
            available_factors += 1
        
        # === OBJECTION PENALTIES ===
        objection_penalty = self._calculate_objection_penalty(objections)
        if objection_penalty.points_earned != 0:
            breakdown.append(objection_penalty)
            total_score += objection_penalty.points_earned  # Will be negative
        
        # === BONUS POINTS ===
        bonuses = self._calculate_bonuses(qualification, call_metadata)
        for bonus in bonuses:
            breakdown.append(bonus)
            total_score += bonus.points_earned
        
        # === PROPORTIONAL WEIGHTING FOR INCOMPLETE DATA (per Q33) ===
        # Don't penalize missing info - use proportional weighting
        if available_factors < 4 and available_factors > 0:
            # Scale up to 100 based on available factors
            # E.g., if only 2 factors available and scored 40/50, scale to 80/100
            base_score_from_bant = sum(
                b.points_earned for b in breakdown[:4] 
                if b.points_earned is not None
            )
            max_from_available = available_factors * 25
            
            if max_from_available > 0:
                # Calculate what the BANT portion would be if scaled to 100
                scaled_bant_score = int((base_score_from_bant / max_from_available) * 100)
                
                # Add back bonuses and penalties (not scaled)
                bonus_penalty_total = sum(
                    b.points_earned for b in breakdown[4:] 
                    if b.points_earned is not None
                )
                
                total_score = scaled_bant_score + bonus_penalty_total
                
                breakdown.append(ScoreBreakdown(
                    component="proportional_adjustment",
                    points_possible=0,
                    points_earned=0,
                    reason=f"Score scaled from {available_factors}/4 BANT factors",
                    evidence=f"Original BANT: {base_score_from_bant}/{max_from_available}, scaled to {scaled_bant_score}/100"
                ))
            
            confidence = "low" if available_factors <= 2 else "medium"
        else:
            confidence = "high"
        
        # === CLAMP SCORE to 0-100 ===
        total_score = max(0, min(100, total_score))
        
        # === DETERMINE BAND (per Q28) ===
        if total_score >= self.BAND_THRESHOLDS["hot"]:
            band = LeadBand.HOT
        elif total_score >= self.BAND_THRESHOLDS["warm"]:
            band = LeadBand.WARM
        else:
            band = LeadBand.COLD
        
        logger.info(f"Lead score calculated: {total_score} ({band.value}) with confidence={confidence}")
        
        return LeadScore(
            total_score=total_score,
            lead_band=band,
            breakdown=breakdown,
            algorithm_version=self.ALGORITHM_VERSION,
            calculated_at=datetime.utcnow(),
            confidence=confidence
        )
    
    def _score_budget(
        self, 
        qualification: Dict[str, Any],
        bant_scores: Dict[str, float]
    ) -> ScoreBreakdown:
        """
        Score budget component (25 points max).
        
        Uses explicit budget_mentioned flag or infers from bant_scores.budget.
        """
        budget_mentioned = qualification.get("budget_mentioned")
        budget_range = qualification.get("budget_range")
        budget_score = bant_scores.get("budget", 0.0)
        budget_indicators = qualification.get("budget_indicators", [])
        
        # If explicit flag available
        if budget_mentioned is True:
            evidence = f"Budget range: {budget_range}" if budget_range else "Budget discussed"
            if budget_indicators:
                evidence += f" | Indicators: {', '.join(budget_indicators[:3])}"
            return ScoreBreakdown(
                component="budget",
                points_possible=25,
                points_earned=25,
                reason="Budget confirmed/discussed",
                evidence=evidence
            )
        elif budget_mentioned is False:
            return ScoreBreakdown(
                component="budget",
                points_possible=25,
                points_earned=0,
                reason="Budget not discussed",
                evidence=None
            )
        
        # Use BANT score if available
        if budget_score > 0:
            points = int(budget_score * 25)
            evidence = None
            if budget_indicators:
                evidence = f"Indicators: {', '.join(budget_indicators[:3])}"
            
            if budget_score >= 0.8:
                reason = "Strong budget signals"
            elif budget_score >= 0.5:
                reason = "Some budget discussion"
            else:
                reason = "Weak budget signals"
                
            return ScoreBreakdown(
                component="budget",
                points_possible=25,
                points_earned=points,
                reason=reason,
                evidence=evidence
            )
        
        # Unknown - neutral (proportional weighting will handle)
        return ScoreBreakdown(
            component="budget",
            points_possible=25,
            points_earned=None,  # Signal unknown
            reason="Budget not determined",
            evidence=None
        )
    
    def _score_authority(
        self,
        qualification: Dict[str, Any],
        bant_scores: Dict[str, float]
    ) -> ScoreBreakdown:
        """
        Score authority component (25 points max).
        
        Decision maker status affects score significantly.
        """
        decision_maker = qualification.get("decision_maker")
        authority_score = bant_scores.get("authority", 0.0)
        decision_makers = qualification.get("decision_makers", [])
        
        # Build evidence from decision makers list
        evidence = None
        if decision_makers:
            evidence = f"Decision makers: {', '.join(decision_makers[:3])}"
        
        # If explicit flag available
        if decision_maker is True:
            return ScoreBreakdown(
                component="authority",
                points_possible=25,
                points_earned=25,
                reason="Decision maker confirmed",
                evidence=evidence or "Customer is the decision maker"
            )
        elif decision_maker is False:
            return ScoreBreakdown(
                component="authority",
                points_possible=25,
                points_earned=10,  # Partial credit - they're involved
                reason="Not primary decision maker",
                evidence="Needs approval from others"
            )
        
        # Use BANT score if available
        if authority_score > 0:
            points = int(authority_score * 25)
            
            if authority_score >= 0.8:
                reason = "Strong authority signals"
            elif authority_score >= 0.5:
                reason = "Some authority present"
            else:
                reason = "Limited authority"
                
            return ScoreBreakdown(
                component="authority",
                points_possible=25,
                points_earned=points,
                reason=reason,
                evidence=evidence
            )
        
        # Unknown
        return ScoreBreakdown(
            component="authority",
            points_possible=25,
            points_earned=None,
            reason="Authority not determined",
            evidence=None
        )
    
    def _score_need(
        self,
        qualification: Dict[str, Any],
        bant_scores: Dict[str, float]
    ) -> ScoreBreakdown:
        """
        Score need/urgency component (25 points max).
        """
        urgency = qualification.get("urgency", "").lower() if qualification.get("urgency") else ""
        need_score = bant_scores.get("need", 0.0)
        urgency_signals = qualification.get("urgency_signals", [])
        service_requested = qualification.get("service_requested")
        
        # Build evidence
        evidence_parts = []
        if service_requested:
            evidence_parts.append(f"Service: {service_requested}")
        if urgency_signals:
            evidence_parts.append(f"Signals: {', '.join(urgency_signals[:3])}")
        evidence = " | ".join(evidence_parts) if evidence_parts else None
        
        # Use urgency level if available
        if urgency:
            urgency_scores = {
                "high": (25, "High urgency - immediate need"),
                "medium": (15, "Medium urgency - near-term need"),
                "low": (5, "Low urgency - exploratory")
            }
            
            if urgency in urgency_scores:
                points, reason = urgency_scores[urgency]
                return ScoreBreakdown(
                    component="need",
                    points_possible=25,
                    points_earned=points,
                    reason=reason,
                    evidence=evidence or f"Urgency level: {urgency}"
                )
        
        # Use BANT score if available
        if need_score > 0:
            points = int(need_score * 25)
            
            if need_score >= 0.8:
                reason = "Strong need identified"
            elif need_score >= 0.5:
                reason = "Moderate need"
            else:
                reason = "Weak need signals"
                
            return ScoreBreakdown(
                component="need",
                points_possible=25,
                points_earned=points,
                reason=reason,
                evidence=evidence
            )
        
        # Unknown
        return ScoreBreakdown(
            component="need",
            points_possible=25,
            points_earned=None,
            reason="Need/urgency not determined",
            evidence=None
        )
    
    def _score_timeline(
        self,
        qualification: Dict[str, Any],
        bant_scores: Dict[str, float]
    ) -> ScoreBreakdown:
        """
        Score timeline component (25 points max).
        """
        timeline = qualification.get("timeline", "").lower() if qualification.get("timeline") else ""
        timeline_score = bant_scores.get("timeline", 0.0)
        appointment_date = qualification.get("appointment_date")
        
        # If appointment is scheduled, that's strong timeline
        if appointment_date:
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=25,
                reason="Appointment scheduled",
                evidence=f"Appointment: {appointment_date}"
            )
        
        if not timeline and timeline_score == 0:
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=None,
                reason="Timeline not discussed",
                evidence=None
            )
        
        # Check for urgent timeline keywords
        urgent_keywords = ["asap", "immediately", "urgent", "emergency", "this week", "next week", "today", "tomorrow"]
        if any(kw in timeline for kw in urgent_keywords):
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=25,
                reason="Urgent timeline (within 2 weeks)",
                evidence=f"Timeline: {timeline}"
            )
        
        # Check for near-term timeline
        nearterm_keywords = ["30 days", "1 month", "this month", "next month", "60 days", "2 months"]
        if any(kw in timeline for kw in nearterm_keywords):
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=20,
                reason="Near-term timeline (1-2 months)",
                evidence=f"Timeline: {timeline}"
            )
        
        # Check for medium-term timeline
        medium_keywords = ["90 days", "3 months", "quarter", "few months"]
        if any(kw in timeline for kw in medium_keywords):
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=15,
                reason="Medium-term timeline (2-3 months)",
                evidence=f"Timeline: {timeline}"
            )
        
        # Use BANT score if available
        if timeline_score > 0:
            points = int(timeline_score * 25)
            
            if timeline_score >= 0.8:
                reason = "Strong timeline signals"
            elif timeline_score >= 0.5:
                reason = "Some timeline discussed"
            else:
                reason = "Vague timeline"
                
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=points,
                reason=reason,
                evidence=f"Timeline: {timeline}" if timeline else None
            )
        
        # Long-term or vague timeline
        if timeline:
            return ScoreBreakdown(
                component="timeline",
                points_possible=25,
                points_earned=5,
                reason="Long-term or vague timeline",
                evidence=f"Timeline: {timeline}"
            )
        
        return ScoreBreakdown(
            component="timeline",
            points_possible=25,
            points_earned=None,
            reason="Timeline not discussed",
            evidence=None
        )
    
    def _calculate_objection_penalty(
        self,
        objections: List[Dict[str, Any]]
    ) -> ScoreBreakdown:
        """
        Calculate penalty for unresolved objections.
        
        Per Q26: Severity + type based penalties.
        Overcome objections don't penalize.
        """
        total_penalty = 0
        objection_details = []
        
        for obj in objections:
            # Skip overcome objections
            overcome = obj.get("overcome", False)
            if overcome:
                continue
            
            severity = obj.get("severity", "low")
            if isinstance(severity, ObjectionSeverity):
                severity = severity.value
            severity = severity.lower()
            
            obj_type = obj.get("category", obj.get("category_text", "other"))
            if obj_type:
                obj_type = obj_type.lower().replace(" ", "_").replace("-", "_")
            else:
                obj_type = "other"
            
            # Map common category names to our types
            category_mapping = {
                "price_concerns": "price",
                "pricing": "price",
                "cost": "price",
                "budget_concerns": "price",
                "competitor_comparison": "competitor",
                "competition": "competitor",
                "timing_issues": "timing",
                "not_right_time": "timing",
                "trust_concerns": "trust",
                "credibility": "trust",
                "authority_required": "authority",
                "need_approval": "authority",
                "not_sure_need": "need",
                "skepticism": "need"
            }
            obj_type = category_mapping.get(obj_type, obj_type)
            
            # Get base penalty
            base_penalty = self.OBJECTION_PENALTIES.get(severity, -2)
            
            # Get type multiplier
            type_multiplier = self.OBJECTION_TYPE_MULTIPLIERS.get(obj_type, 1.0)
            
            penalty = int(base_penalty * type_multiplier)
            total_penalty += penalty
            
            objection_text = obj.get("objection_text", obj.get("category_text", "Unknown"))[:50]
            objection_details.append(f"{obj_type} ({severity}): {penalty} pts")
        
        if total_penalty == 0:
            return ScoreBreakdown(
                component="objections",
                points_possible=0,
                points_earned=0,
                reason="No unresolved objections",
                evidence=None
            )
        
        return ScoreBreakdown(
            component="objections",
            points_possible=0,
            points_earned=total_penalty,  # Will be negative
            reason=f"Objection penalty ({len(objection_details)} unresolved)",
            evidence="; ".join(objection_details)
        )
    
    def _calculate_bonuses(
        self,
        qualification: Dict[str, Any],
        call_metadata: Dict[str, Any]
    ) -> List[ScoreBreakdown]:
        """
        Calculate bonus points per Q27.
        
        Bonuses for: urgency, referrals, inbound calls, explicit needs.
        """
        bonuses = []
        
        # Urgency bonus (beyond base need scoring)
        urgency = qualification.get("urgency", "").lower() if qualification.get("urgency") else ""
        urgency_signals = qualification.get("urgency_signals", [])
        
        # Check for high urgency signals
        high_urgency_keywords = ["asap", "emergency", "immediately", "urgent", "right away"]
        has_high_urgency = (
            urgency == "high" or
            any(kw in urgency for kw in high_urgency_keywords) or
            any(any(kw in sig.lower() for kw in high_urgency_keywords) for sig in urgency_signals if isinstance(sig, str))
        )
        
        if has_high_urgency:
            bonuses.append(ScoreBreakdown(
                component="bonus_urgency",
                points_possible=10,
                points_earned=10,
                reason="High urgency bonus",
                evidence="Customer expressed urgent need"
            ))
        elif urgency == "medium":
            bonuses.append(ScoreBreakdown(
                component="bonus_urgency",
                points_possible=5,
                points_earned=5,
                reason="Medium urgency bonus",
                evidence="Customer has near-term need"
            ))
        
        # Referral bonus
        is_referral = (
            call_metadata.get("is_referral") or
            qualification.get("referral_source") is not None or
            call_metadata.get("referral_source") is not None
        )
        if is_referral:
            referral_source = (
                qualification.get("referral_source") or 
                call_metadata.get("referral_source") or 
                "existing customer"
            )
            bonuses.append(ScoreBreakdown(
                component="bonus_referral",
                points_possible=10,
                points_earned=10,
                reason="Referral bonus",
                evidence=f"Referred by: {referral_source}"
            ))
        
        # Inbound bonus
        is_inbound = (
            call_metadata.get("is_inbound") or
            call_metadata.get("direction") == "inbound" or
            call_metadata.get("call_direction") == "inbound"
        )
        if is_inbound:
            bonuses.append(ScoreBreakdown(
                component="bonus_inbound",
                points_possible=5,
                points_earned=5,
                reason="Inbound call bonus",
                evidence="Customer initiated contact"
            ))
        
        # Explicit need bonus (from transcript analysis)
        explicit_need = qualification.get("explicit_need_expressed", False)
        urgency_signals_with_need = [
            sig for sig in urgency_signals 
            if isinstance(sig, str) and any(phrase in sig.lower() for phrase in ["i need", "we need", "must have", "have to get"])
        ]
        
        if explicit_need or urgency_signals_with_need:
            bonuses.append(ScoreBreakdown(
                component="bonus_explicit_need",
                points_possible=5,
                points_earned=5,
                reason="Explicit need expressed",
                evidence=urgency_signals_with_need[0] if urgency_signals_with_need else "Customer stated clear need"
            ))
        
        # Multiple decision makers bonus (when it's positive - they brought the team)
        decision_makers = qualification.get("decision_makers", [])
        if len(decision_makers) > 1:
            bonuses.append(ScoreBreakdown(
                component="bonus_multiple_dm",
                points_possible=5,
                points_earned=5,
                reason="Multiple decision makers involved",
                evidence=f"Decision makers: {', '.join(decision_makers[:3])}"
            ))
        
        return bonuses
    
    def recalculate_score(
        self,
        previous_score: LeadScore,
        new_qualification: Dict[str, Any],
        new_objections: List[Dict[str, Any]],
        new_metadata: Dict[str, Any]
    ) -> LeadScore:
        """
        Recalculate score on new interaction (per Q31: Dynamic recalculation).
        
        This is called when new call data is available for a customer.
        """
        # Simply recalculate with new data
        new_score = self.calculate_score(new_qualification, new_objections, new_metadata)
        
        # Log score change
        score_change = new_score.total_score - previous_score.total_score
        if abs(score_change) > 0:
            logger.info(
                f"Lead score recalculated: {previous_score.total_score} -> {new_score.total_score} "
                f"({'+' if score_change > 0 else ''}{score_change})"
            )
        
        return new_score


# ============================================================================
# SINGLETON
# ============================================================================

_lead_scoring_service: Optional[LeadScoringService] = None


def get_lead_scoring_service() -> LeadScoringService:
    """Get singleton LeadScoringService instance."""
    global _lead_scoring_service
    if _lead_scoring_service is None:
        _lead_scoring_service = LeadScoringService()
    return _lead_scoring_service
