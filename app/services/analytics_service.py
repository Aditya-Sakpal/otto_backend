"""
Analytics service.

Provides analytics calculations for objections and calls.
"""
import traceback
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from datetime import datetime, timedelta, date
from collections import defaultdict

from sqlalchemy import select, func, text, bindparam, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.metrics_service import _metrics_exclude_existing_and_service_not_offered
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.infrastructure.database.models.analysis import CallAnalysisORM

logger = get_logger(__name__)


def _build_call_log_entry(
    call: Any,  # Can be CallORM or synthetic call object
    analysis: Any,  # Can be CallAnalysisORM or synthetic analysis object
    contact_card: Optional[ContactCardORM],
) -> Dict[str, Any]:
    """Build a single call log entry for objection call lists."""
    contact_name = None
    if contact_card:
        if contact_card.first_name and contact_card.last_name:
            contact_name = f"{contact_card.first_name} {contact_card.last_name}"
        elif contact_card.first_name:
            contact_name = contact_card.first_name
        elif contact_card.last_name:
            contact_name = contact_card.last_name
        else:
            contact_name = contact_card.primary_phone or "Unknown"

    # Handle both real CallORM and synthetic call objects
    call_id = str(call.id) if hasattr(call, 'id') else None
    lead_id = str(call.lead_id) if hasattr(call, 'lead_id') and call.lead_id else None
    phone_number = getattr(call, 'phone_number', None)
    audio_url = getattr(call, 'audio_url', None)
    call_type = getattr(call, 'call_type', None)
    duration_seconds = getattr(call, 'duration_seconds', None)
    created_at = call.created_at.isoformat() if hasattr(call, 'created_at') and call.created_at else None
    transcript = getattr(call, 'transcript', None)
    
    # Handle both real CallAnalysisORM and synthetic analysis objects
    qualification_status = getattr(analysis, 'qualification_status', None) if analysis else None
    booking_status = getattr(analysis, 'booking_status', None) if analysis else None
    summary = getattr(analysis, 'summary', None) if analysis else None

    return {
        "call_id": call_id or "unknown",
        "lead_id": lead_id,
        "contact_name": contact_name or "Unknown",
        "phone_number": phone_number or "",
        "audio_url": audio_url,
        "call_type": call_type,
        "duration_seconds": duration_seconds,
        "created_at": created_at,
        "qualification_status": qualification_status,
        "booking_status": booking_status,
        "transcript": transcript,
        "summary": summary,
    }


class AnalyticsService:
    """Service for analytics calculations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    def _classify_objections_in_analysis(self, analysis: CallAnalysisORM) -> List[str]:
        """
        Classify raw objections from analysis into standardized categories.

        Args:
            analysis: CallAnalysisORM instance with raw objections

        Returns:
            List of classified objection categories (deduplicated)
        """
        from app.domain.objection_classifier import ObjectionClassifier

        if not analysis or not analysis.objections:
            return []

        return ObjectionClassifier.classify_and_deduplicate(analysis.objections)

    async def _build_objection_item(
        self,
        obj_type: str,
        rows_for_obj: List[Tuple[Any, Any, Any]],
        leads_set: set,
        include_company_metrics: bool,
        start_dt: Optional[datetime],
        end_dt: Optional[datetime],
        users_map: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Build the full metrics dict for an objection type (reused for top-level and sub-objections)."""
        from app.infrastructure.database.models.user import UserORM

        count = len(rows_for_obj)
        item: Dict[str, Any] = {
            "objection_type": obj_type,
            "count": count,
            "affected_leads_count": len(leads_set),
        }

        # Call logs
        call_logs = [
            _build_call_log_entry(call, analysis, contact_card)
            for analysis, call, contact_card in rows_for_obj
        ]
        call_logs.sort(key=lambda x: (x["created_at"] or ""), reverse=True)
        item["call_logs"] = call_logs

        if include_company_metrics:
            booked = sum(
                1 for a, _c, _cc in rows_for_obj
                if a.booking_status and str(a.booking_status).lower() == "booked"
            )
            unbooked = count - booked
            total_bookable = booked + unbooked
            booking_rate = round((booked / total_bookable * 100), 2) if total_bookable else None
            item["booked"] = booked
            item["unbooked"] = unbooked
            item["booking_rate"] = booking_rate

            # Booking rate trend: by week
            trend: List[Dict[str, Any]] = []
            if start_dt and end_dt and rows_for_obj:
                week_buckets: Dict[date, List[Tuple[Any, Any, Any]]] = defaultdict(list)
                for a, c, cc in rows_for_obj:
                    if c.created_at:
                        d = c.created_at.date()
                        week_start = d - timedelta(days=d.weekday())
                        week_buckets[week_start].append((a, c, cc))
                for week_start in sorted(week_buckets.keys()):
                    if week_start < start_dt.date() or week_start > end_dt.date():
                        continue
                    week_rows = week_buckets[week_start]
                    w_booked = sum(
                        1 for a, _, _ in week_rows
                        if a.booking_status and str(a.booking_status).lower() == "booked"
                    )
                    w_total = len(week_rows)
                    w_rate = round((w_booked / w_total * 100), 2) if w_total else 0
                    trend.append({
                        "period_start": week_start.isoformat(),
                        "period_end": (week_start + timedelta(days=6)).isoformat(),
                        "booking_rate": w_rate,
                        "booked": w_booked,
                        "unbooked": w_total - w_booked,
                    })
                trend.sort(key=lambda x: x["period_start"])
            item["booking_rate_trend"] = trend

            # Most coaching needs: per user
            user_rows: Dict[Optional[UUID], List[Tuple[Any, Any, Any]]] = defaultdict(list)
            for a, c, cc in rows_for_obj:
                user_rows[c.handled_by_user_id].append((a, c, cc))

            # Fetch users_map if not provided
            if users_map is None:
                u_ids = [uid for uid in user_rows.keys() if uid is not None]
                if u_ids:
                    users_result = await self.session.execute(
                        select(UserORM).where(UserORM.id.in_(u_ids))
                    )
                    users_map = {u.id: u for u in users_result.scalars().all()}
                else:
                    users_map = {}

            most_coaching_needs: List[Dict[str, Any]] = []
            for uid in list(user_rows.keys()):
                u_rows = user_rows[uid]
                u_unbooked = sum(
                    1 for a, _, _ in u_rows
                    if not (a.booking_status and str(a.booking_status).lower() == "booked")
                )
                u_user = users_map.get(uid) if uid else None
                if u_user:
                    u_name = " ".join(
                        filter(None, [u_user.first_name, u_user.last_name])
                    ) or u_user.email or "Unknown"
                else:
                    u_name = "Unknown"
                user_call_logs = [
                    _build_call_log_entry(call, analysis, contact_card)
                    for analysis, call, contact_card in u_rows
                ]
                user_call_logs.sort(key=lambda x: (x["created_at"] or ""), reverse=True)
                most_coaching_needs.append({
                    "user_id": str(uid) if uid else None,
                    "user_name": u_name,
                    "email": u_user.email if u_user else None,
                    "unbooked_count": u_unbooked,
                    "call_logs": user_call_logs,
                })
            most_coaching_needs.sort(key=lambda x: x["unbooked_count"], reverse=True)
            item["most_coaching_needs"] = most_coaching_needs

        return item

    async def get_top_objections(
        self,
        company_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        unbooked_only: bool = False,
    ) -> Dict[str, Any]:
        """
        Get top objections aggregated by company or user.

        When called by company_id (no user_id): returns objections with
        - objection_type, count, affected_leads_count
        - booking_rate, booked, unbooked, booking_rate_trend (start to end date)
        - most_coaching_needs: user details + unbooked count for that objection + call_logs per user
        - call_logs: all call details where that objection occurred (company-wide)

        For objection_type "other", includes a sub_objections array with per-raw-objection breakdown.

        When called by user_id: returns objections with
        - objection_type, count, affected_leads_count
        - call_logs: call details where that objection occurred for that user only
        """
        try:
            from app.infrastructure.database.models.user import UserORM
            from app.domain.objection_classifier import ObjectionClassifier

            # Resolution rules
            if user_id:
                user_result = await self.session.execute(select(UserORM).where(UserORM.id == user_id))
                user = user_result.scalar_one_or_none()
                if not user or not user.company_id:
                    raise ValueError("user_id must belong to a user with a company_id")
                company_id = user.company_id
            elif not company_id:
                raise ValueError("Either company_id or user_id is required")

            # Date range for filtering (call date)
            start_dt = None
            end_dt = None
            if start_date:
                start_dt = datetime.combine(start_date, datetime.min.time())
            if end_date:
                end_dt = datetime.combine(end_date, datetime.max.time())

            # Get analyses with objections, joined with calls and contact_card (exclude existing customer & service not offered)
            # Also include appointments with objections for Sales Reps
            from app.infrastructure.database.models.appointment import AppointmentORM
            
            # Query 1: Calls with call_analyses (existing logic)
            calls_query = (
                select(CallAnalysisORM, CallORM, ContactCardORM)
                .join(CallORM, CallAnalysisORM.call_id == CallORM.id)
                .outerjoin(ContactCardORM, CallORM.contact_card_id == ContactCardORM.id)
                .where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.objections.isnot(None),
                    func.coalesce(func.array_length(CallAnalysisORM.objections, 1), 0) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
            )
            if user_id:
                calls_query = calls_query.where(CallORM.handled_by_user_id == user_id)
            if start_dt is not None:
                calls_query = calls_query.where(CallORM.created_at >= start_dt)
            if end_dt is not None:
                calls_query = calls_query.where(CallORM.created_at <= end_dt)
            if unbooked_only:
                calls_query = calls_query.where(CallAnalysisORM.booking_status == "not_booked")

            calls_results = await self.session.execute(calls_query)
            calls_rows = calls_results.all()
            
            # Query 2: Appointments with objections (for Sales Reps)
            # Appointments can have objections stored directly or via call_analyses
            appointments_query = (
                select(AppointmentORM, CallORM, CallAnalysisORM, ContactCardORM)
                .outerjoin(CallORM, AppointmentORM.interaction_id == CallORM.id)
                .outerjoin(CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id)
                .outerjoin(ContactCardORM, AppointmentORM.contact_card_id == ContactCardORM.id)
                .where(
                    AppointmentORM.company_id == company_id,
                    # Check if objections exist in either appointments or call_analyses
                    (
                        (AppointmentORM.objections.isnot(None)) & 
                        (func.coalesce(func.array_length(AppointmentORM.objections, 1), 0) > 0)
                    ) | (
                        (CallAnalysisORM.objections.isnot(None)) & 
                        (func.coalesce(func.array_length(CallAnalysisORM.objections, 1), 0) > 0)
                    ),
                    # Only apply exclusion filter if call_analyses exists
                    or_(
                        CallAnalysisORM.id.is_(None),
                        _metrics_exclude_existing_and_service_not_offered(),
                    ),
                )
            )
            if user_id:
                # Filter by assigned_rep_id for Sales Reps
                appointments_query = appointments_query.where(AppointmentORM.assigned_rep_id == user_id)
            if start_dt is not None:
                appointments_query = appointments_query.where(AppointmentORM.created_at >= start_dt)
            if end_dt is not None:
                appointments_query = appointments_query.where(AppointmentORM.created_at <= end_dt)
            
            appointments_results = await self.session.execute(appointments_query)
            appointments_rows = appointments_results.all()
            
            # Combine results: convert appointment rows to (analysis, call, contact_card) format
            # For appointments, we'll use appointment objections if call_analyses doesn't exist
            rows = list(calls_rows)
            seen_call_ids = {call.id for _, call, _ in calls_rows if call}
            
            for row in appointments_rows:
                appointment, call, analysis, contact_card = row
                if not appointment:
                    continue
                
                # Skip if we already have this call from calls_rows
                if call and call.id in seen_call_ids:
                    continue
                
                # If appointment has objections directly and no call_analysis, use appointment data
                if appointment.objections and len(appointment.objections) > 0:
                    if not analysis:
                        # Create a synthetic CallAnalysisORM-like object from appointment
                        from types import SimpleNamespace
                        synthetic_analysis = SimpleNamespace(
                            objections=appointment.objections,
                            objection_texts=getattr(appointment, 'objection_texts', appointment.objections),
                            qualification_status=getattr(appointment, 'qualification_status', None),
                            booking_status=getattr(appointment, 'booking_status', None),
                            summary=getattr(appointment, 'summary', None),
                            is_existing_customer=getattr(appointment, 'is_existing_customer', None),
                            service_not_offered_reason=getattr(appointment, 'service_not_offered_reason', None),
                        )
                        # Use call if available, otherwise create a synthetic call from appointment
                        if not call and appointment:
                            synthetic_call = SimpleNamespace(
                                id=appointment.id,  # Use appointment id as call id
                                lead_id=appointment.lead_id,
                                contact_card_id=appointment.contact_card_id,
                                phone_number=None,
                                audio_url=appointment.audio_url,
                                call_type="meeting",
                                duration_seconds=appointment.duration_seconds,
                                created_at=appointment.created_at,
                                transcript=appointment.transcript,
                                handled_by_user_id=appointment.assigned_rep_id,
                            )
                            rows.append((synthetic_analysis, synthetic_call, contact_card))
                        elif call:
                            # Use the real call but synthetic analysis from appointment
                            rows.append((synthetic_analysis, call, contact_card))
                            seen_call_ids.add(call.id)
                    else:
                        # Use existing call_analysis
                        if call:
                            rows.append((analysis, call, contact_card))
                            seen_call_ids.add(call.id)

            # Per objection: list of (analysis, call, contact_card) for building counts and call_logs
            objection_rows: Dict[str, List[Tuple[Any, Any, Any]]] = defaultdict(list)
            objection_leads: Dict[str, set] = defaultdict(set)

            # For "other" sub-grouping: raw_text -> list of (analysis, call, contact_card)
            other_sub_rows: Dict[str, List[Tuple[Any, Any, Any]]] = defaultdict(list)
            other_sub_leads: Dict[str, set] = defaultdict(set)

            for analysis, call, contact_card in rows:
                if not analysis.objections:
                    continue
                classified_pairs = ObjectionClassifier.classify_and_deduplicate_with_raw(analysis.objections)
                for category, raw_text in classified_pairs:
                    if not category or not str(category).strip():
                        continue
                    category_normalized = str(category).strip()
                    objection_rows[category_normalized].append((analysis, call, contact_card))
                    if call.lead_id:
                        objection_leads[category_normalized].add(call.lead_id)

                    # Track sub-grouping for "other"
                    if category_normalized == "other" and raw_text:
                        raw_text_normalized = raw_text.strip()
                        if raw_text_normalized:
                            other_sub_rows[raw_text_normalized].append((analysis, call, contact_card))
                            if call.lead_id:
                                other_sub_leads[raw_text_normalized].add(call.lead_id)

            # Pre-fetch all users for company metrics to avoid repeated queries
            users_map = None
            if not user_id:
                all_user_ids = set()
                for rows_for_obj in objection_rows.values():
                    for _, c, _ in rows_for_obj:
                        if c.handled_by_user_id:
                            all_user_ids.add(c.handled_by_user_id)
                if all_user_ids:
                    users_result = await self.session.execute(
                        select(UserORM).where(UserORM.id.in_(list(all_user_ids)))
                    )
                    users_map = {u.id: u for u in users_result.scalars().all()}
                else:
                    users_map = {}

            # Build response objections list
            include_company = not user_id
            objections_out: List[Dict[str, Any]] = []
            for obj_type in sorted(
                objection_rows.keys(),
                key=lambda k: len(objection_rows[k]),
                reverse=True,
            ):
                rows_for_obj = objection_rows[obj_type]
                leads_set = objection_leads.get(obj_type, set())

                item = await self._build_objection_item(
                    obj_type, rows_for_obj, leads_set,
                    include_company_metrics=include_company,
                    start_dt=start_dt, end_dt=end_dt,
                    users_map=users_map,
                )

                # For "other", add sub_objections array
                if obj_type == "other" and other_sub_rows:
                    sub_objections = []
                    for sub_type in sorted(
                        other_sub_rows.keys(),
                        key=lambda k: len(other_sub_rows[k]),
                        reverse=True,
                    ):
                        sub_rows = other_sub_rows[sub_type]
                        sub_leads = other_sub_leads.get(sub_type, set())
                        sub_item = await self._build_objection_item(
                            sub_type, sub_rows, sub_leads,
                            include_company_metrics=include_company,
                            start_dt=start_dt, end_dt=end_dt,
                            users_map=users_map,
                        )
                        sub_objections.append(sub_item)
                    item["sub_objections"] = sub_objections

                objections_out.append(item)

            response: Dict[str, Any] = {"objections": objections_out}
            if start_date is not None:
                response["start_date"] = start_date.isoformat()
            if end_date is not None:
                response["end_date"] = end_date.isoformat()
            if unbooked_only:
                response["unbooked_only"] = True

            return response

        except Exception as e:
            logger.error(f"Error getting top objections: {e}")
            traceback.print_exc()
            raise
    
    async def get_objection_calls(
        self,
        company_id: UUID,
        objection: str,
        owner_id: Optional[UUID] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get calls filtered by objection type and optionally by CSR owner.
        
        Returns list of calls with:
        - call_id: UUID of the call
        - contact_card: Full contact card object
        - audio_url: URL to call audio recording
        - qualification_status: Qualification status from analysis
        - booking_status: Booking status from analysis
        """
        try:
            # Expand objection filter to include new categories
            from app.domain.objection_classifier import ObjectionClassifier

            # Get the target categories (handles both old and new objection types)
            target_categories = ObjectionClassifier.expand_objection_filter(objection)

            # For backward compatibility, we'll fetch all calls with objections
            # and filter in Python after classification
            # This ensures accurate results with the new classification system
            
            # Fetch all calls with objections for this company
            # We'll filter by classification in Python for accuracy
            query = select(
                CallAnalysisORM,
                CallORM,
                ContactCardORM
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                _metrics_exclude_existing_and_service_not_offered(),
            )
            
            # Add owner_id filter if provided
            if owner_id:
                query = query.where(CallORM.handled_by_user_id == owner_id)
            
            # Execute query
            results = await self.session.execute(query)
            rows = results.all()
            
            # Build response - filter by classified objections
            result = []
            for analysis, call, contact_card in rows:
                # Classify objections and check if any match the target categories
                classified_objections = self._classify_objections_in_analysis(analysis)
                if not any(obj in target_categories for obj in classified_objections):
                    continue

                # Get contact card data
                contact_card_data = None
                if contact_card:
                    contact_card_data = {
                        "id": str(contact_card.id),
                        "company_id": str(contact_card.company_id),
                        "primary_phone": contact_card.primary_phone,
                        "secondary_phone": contact_card.secondary_phone,
                        "email": contact_card.email,
                        "first_name": contact_card.first_name,
                        "last_name": contact_card.last_name,
                        "address": contact_card.address,
                        "city": contact_card.city,
                        "state": contact_card.state,
                        "postal_code": contact_card.postal_code,
                        "property_snapshot": contact_card.property_snapshot,
                        "extra_metadata": contact_card.extra_metadata,
                    }

                result.append({
                    "call_id": str(call.id),
                    "contact_card": contact_card_data,
                    "audio_url": call.audio_url,
                    "qualification_status": analysis.qualification_status,
                    "booking_status": analysis.booking_status,
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting objection calls: {e}")
            traceback.print_exc()
            raise
    
    async def get_calls_by_objection_self(
        self,
        company_id: UUID,
        objection: str,
        user_id: Optional[UUID] = None,
        user_role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive objection details data for the objection details page.
        
        Returns data for three tabs:
        1. Calls: List of calls with that objection (with contact name and recording URL)
        2. Unbooked leads: Leads that are unbooked and have that objection
        3. Most coaching need: CSRs/Sales Reps with unbooked calls for that objection
        
        Args:
            company_id: Company UUID
            objection: Objection type (e.g., 'authority', 'price', 'timing')
            user_id: Optional user ID to filter by (for /self endpoint)
            user_role: Optional user role to determine query strategy ('sales_rep' queries appointments, others query calls)
        
        Returns:
            Dictionary with:
            - calls: List of calls with objection details
            - unbooked_leads: List of unbooked leads with that objection
            - most_coaching_need: List of CSRs/Sales Reps with unbooked calls count
        """
        try:
            from app.infrastructure.database.models.lead import LeadORM
            from app.infrastructure.database.models.user import UserORM
            from app.infrastructure.database.models.appointment import AppointmentORM
            from app.domain.objection_classifier import ObjectionClassifier

            # Expand objection filter to include new categories
            target_categories = ObjectionClassifier.expand_objection_filter(objection)

            # 1. Get calls with objections
            # For Sales Reps: query appointments -> get calls via interaction_id
            # For CSRs/Others: query calls directly via handled_by_user_id
            if user_role == 'sales_rep' and user_id:
                # Query appointments assigned to this sales rep
                # Check objections in both appointments.objections (direct) and call_analyses.objections (via call)
                appointments_query = select(
                    AppointmentORM,
                    CallORM,
                    CallAnalysisORM,
                    ContactCardORM
                ).outerjoin(
                    CallORM, AppointmentORM.interaction_id == CallORM.id
                ).outerjoin(
                    CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
                ).outerjoin(
                    ContactCardORM, AppointmentORM.contact_card_id == ContactCardORM.id
                ).where(
                    AppointmentORM.company_id == company_id,
                    AppointmentORM.assigned_rep_id == user_id,
                    # Check if objections exist in either appointments or call_analyses
                    (
                        (AppointmentORM.objections.isnot(None)) & 
                        (func.array_length(AppointmentORM.objections, 1) > 0)
                    ) | (
                        (CallAnalysisORM.objections.isnot(None)) & 
                        (func.array_length(CallAnalysisORM.objections, 1) > 0)
                    ),
                    # Only apply exclusion filter if call_analyses exists (for appointments without interaction_id, skip this filter)
                    or_(
                        CallAnalysisORM.id.is_(None),  # No call_analysis (appointment-only)
                        _metrics_exclude_existing_and_service_not_offered(),  # Has call_analysis, apply filter
                    ),
                ).order_by(AppointmentORM.created_at.desc())
                
                calls_results = await self.session.execute(appointments_query)
                calls_rows = calls_results.all()
            else:
                # Default: query calls directly (for CSR or company-wide)
                calls_query = select(
                    CallORM,
                    CallAnalysisORM,
                    ContactCardORM
                ).join(
                    CallORM, CallAnalysisORM.call_id == CallORM.id
                ).outerjoin(
                    ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
                ).where(
                    CallAnalysisORM.company_id == company_id,
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
                
                if user_id:
                    calls_query = calls_query.where(CallORM.handled_by_user_id == user_id)
                
                calls_query = calls_query.order_by(CallORM.created_at.desc())
                calls_results = await self.session.execute(calls_query)
                calls_rows = calls_results.all()
            
            
            calls_data = []
            # Handle different row structures: (appointment, call, analysis, contact_card) vs (call, analysis, contact_card)
            for row in calls_rows:
                if len(row) == 4:  # (appointment, call, analysis, contact_card) - Sales Rep query
                    appointment, call, analysis, contact_card = row
                    # For Sales Reps: check objections in appointment first, then call_analyses
                    if appointment and appointment.objections:
                        # Use appointments.objections directly
                        from app.domain.objection_classifier import ObjectionClassifier
                        appointment_objections = ObjectionClassifier.classify_and_deduplicate(appointment.objections)
                        classified_objections = appointment_objections
                    elif analysis:
                        # Fall back to call_analyses.objections
                        classified_objections = self._classify_objections_in_analysis(analysis)
                    else:
                        classified_objections = []
                else:  # (call, analysis, contact_card) - CSR/Default query
                    call, analysis, contact_card = row
                    # Classify objections from call_analyses
                    classified_objections = self._classify_objections_in_analysis(analysis)
                
                # Filter by target categories
                if not any(obj in target_categories for obj in classified_objections):
                    continue

                # Get contact name
                contact_name = None
                if contact_card:
                    if contact_card.first_name and contact_card.last_name:
                        contact_name = f"{contact_card.first_name} {contact_card.last_name}"
                    elif contact_card.first_name:
                        contact_name = contact_card.first_name
                    elif contact_card.last_name:
                        contact_name = contact_card.last_name
                    else:
                        contact_name = contact_card.primary_phone

                # Use appointment audio_url if available (for Sales Reps), otherwise use call audio_url
                audio_url = None
                call_id = None
                phone_number = None
                call_type = None
                duration_seconds = None
                created_at = None
                transcript = None
                summary = None
                
                if len(row) == 4:  # Sales Rep query with appointment
                    appointment = row[0]
                    call = row[1] if len(row) > 1 else None
                    analysis = row[2] if len(row) > 2 else None
                    
                    # Use appointment fields first, fall back to call fields
                    audio_url = appointment.audio_url or (call.audio_url if call else None)
                    call_id = str(call.id) if call else str(appointment.id)  # Use appointment id if no call
                    phone_number = call.phone_number if call else None
                    call_type = call.call_type if call else "meeting"
                    duration_seconds = appointment.duration_seconds or (call.duration_seconds if call else None)
                    created_at = appointment.created_at.isoformat() if appointment.created_at else (call.created_at.isoformat() if call and call.created_at else None)
                    transcript = appointment.transcript or (call.transcript if call else None)
                    summary = appointment.summary or (analysis.summary if analysis else None)
                else:
                    # CSR/Default query
                    call = row[0]
                    analysis = row[1] if len(row) > 1 else None
                    audio_url = call.audio_url
                    call_id = str(call.id)
                    phone_number = call.phone_number
                    call_type = call.call_type
                    duration_seconds = call.duration_seconds
                    created_at = call.created_at.isoformat() if call.created_at else None
                    transcript = call.transcript
                    summary = analysis.summary if analysis else None

                calls_data.append({
                    "id": call_id,
                    "contact_name": contact_name or "Unknown",
                    "call_recording_url": audio_url,  # Use audio_url (from appointment or call)
                    "phone_number": phone_number,
                    "call_type": call_type,
                    "duration_seconds": duration_seconds,
                    "created_at": created_at,
                    "transcript": transcript,
                    "summary": summary,
                })
            
            # 2. Get unbooked leads with that objection
            # Unbooked = leads with status not 'qualified_booked' and not 'closed_won'
            unbooked_statuses = ['new', 'warm', 'hot', 'qualified_unbooked', 'qualified_service_not_offered', 'nurturing']

            # Get leads with their calls and analyses for classification
            unbooked_query = select(
                LeadORM,
                ContactCardORM,
                CallAnalysisORM
            ).join(
                CallORM, CallORM.lead_id == LeadORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).join(
                ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id
            ).where(
                LeadORM.company_id == company_id,
                LeadORM.status.in_(unbooked_statuses),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                _metrics_exclude_existing_and_service_not_offered(),
            )

            unbooked_results = await self.session.execute(unbooked_query)
            unbooked_rows = unbooked_results.all()

            # Filter leads by classified objections and deduplicate
            seen_leads = set()
            unbooked_leads_data = []
            for lead, contact_card, analysis in unbooked_rows:
                # Skip if we've already processed this lead
                if lead.id in seen_leads:
                    continue

                # Classify objections and check if any match target categories
                classified_objections = self._classify_objections_in_analysis(analysis)
                if not any(obj in target_categories for obj in classified_objections):
                    continue

                seen_leads.add(lead.id)
                contact_name = None
                if contact_card:
                    if contact_card.first_name and contact_card.last_name:
                        contact_name = f"{contact_card.first_name} {contact_card.last_name}"
                    elif contact_card.first_name:
                        contact_name = contact_card.first_name
                    elif contact_card.last_name:
                        contact_name = contact_card.last_name
                    else:
                        contact_name = contact_card.primary_phone
                
                unbooked_leads_data.append({
                    "id": str(lead.id),
                    "contact_name": contact_name or "Unknown",
                    "status": lead.status,
                    "deal_status": lead.deal_status,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                })
            
            # 3. Get CSRs/Sales Reps with unbooked calls/appointments for that objection (most coaching need)
            # Show only the same role type as the requesting user (Sales Reps see Sales Reps, CSRs see CSRs)
            if user_role == 'sales_rep':
                # For Sales Reps: query appointments assigned to Sales Reps
                # Check objections in both appointments.objections and call_analyses.objections
                from app.infrastructure.database.models.appointment import AppointmentORM
                rep_unbooked_query = select(
                    UserORM.id,
                    UserORM.first_name,
                    UserORM.last_name,
                    AppointmentORM.id.label('appointment_id'),
                    AppointmentORM,
                    CallAnalysisORM
                ).join(
                    AppointmentORM, AppointmentORM.assigned_rep_id == UserORM.id
                ).outerjoin(
                    CallORM, AppointmentORM.interaction_id == CallORM.id
                ).outerjoin(
                    CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
                ).join(
                    LeadORM, AppointmentORM.lead_id == LeadORM.id
                ).where(
                    UserORM.company_id == company_id,
                    UserORM.role == 'sales_rep',  # Only show Sales Reps
                    UserORM.is_active == True,
                    LeadORM.status.in_(unbooked_statuses),
                    # Check if objections exist in either appointments or call_analyses
                    (
                        (AppointmentORM.objections.isnot(None)) & 
                        (func.array_length(AppointmentORM.objections, 1) > 0)
                    ) | (
                        (CallAnalysisORM.objections.isnot(None)) & 
                        (func.array_length(CallAnalysisORM.objections, 1) > 0)
                    ),
                    _metrics_exclude_existing_and_service_not_offered(),
                )
                # Execute the query
                rep_results = await self.session.execute(rep_unbooked_query)
                rep_rows = rep_results.all()
            elif user_role == 'csr':
                # For CSRs: query calls handled by CSRs
                rep_unbooked_query = select(
                    UserORM.id,
                    UserORM.first_name,
                    UserORM.last_name,
                    CallORM.id.label('call_id'),
                    CallAnalysisORM
                ).join(
                    CallORM, CallORM.handled_by_user_id == UserORM.id
                ).join(
                    CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
                ).join(
                    LeadORM, CallORM.lead_id == LeadORM.id
                ).where(
                    UserORM.company_id == company_id,
                    UserORM.role == 'csr',  # Only show CSRs
                    UserORM.is_active == True,
                    LeadORM.status.in_(unbooked_statuses),
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
                # Execute the query
                rep_results = await self.session.execute(rep_unbooked_query)
                rep_rows = rep_results.all()
            else:
                # For Executives/company-wide: show both CSRs and Sales Reps
                # Query CSRs via calls
                csr_query = select(
                    UserORM.id,
                    UserORM.first_name,
                    UserORM.last_name,
                    CallORM.id.label('call_id'),
                    CallAnalysisORM
                ).join(
                    CallORM, CallORM.handled_by_user_id == UserORM.id
                ).join(
                    CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
                ).join(
                    LeadORM, CallORM.lead_id == LeadORM.id
                ).where(
                    UserORM.company_id == company_id,
                    UserORM.role == 'csr',
                    UserORM.is_active == True,
                    LeadORM.status.in_(unbooked_statuses),
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
                
                # Query Sales Reps via appointments
                from app.infrastructure.database.models.appointment import AppointmentORM
                sales_rep_query = select(
                    UserORM.id,
                    UserORM.first_name,
                    UserORM.last_name,
                    AppointmentORM.id.label('appointment_id'),
                    CallAnalysisORM
                ).join(
                    AppointmentORM, AppointmentORM.assigned_rep_id == UserORM.id
                ).join(
                    CallORM, AppointmentORM.interaction_id == CallORM.id
                ).join(
                    CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
                ).join(
                    LeadORM, AppointmentORM.lead_id == LeadORM.id
                ).where(
                    UserORM.company_id == company_id,
                    UserORM.role == 'sales_rep',
                    UserORM.is_active == True,
                    AppointmentORM.interaction_id.isnot(None),
                    LeadORM.status.in_(unbooked_statuses),
                    CallAnalysisORM.objections.isnot(None),
                    func.array_length(CallAnalysisORM.objections, 1) > 0,
                    _metrics_exclude_existing_and_service_not_offered(),
                )
                
                # Execute both queries and combine results
                csr_results = await self.session.execute(csr_query)
                sales_rep_results = await self.session.execute(sales_rep_query)
                rep_rows = list(csr_results.all()) + list(sales_rep_results.all())

            # Count unbooked calls/appointments per rep after classification
            rep_counts = {}
            for row in rep_rows:
                user_id_val = row[0]
                first_name = row[1]
                last_name = row[2]
                
                # Handle different row structures based on query type
                if user_role == 'sales_rep':
                    # Row structure: (user_id, first_name, last_name, appointment_id, AppointmentORM, CallAnalysisORM)
                    appointment = row[4] if len(row) > 4 else None
                    analysis = row[5] if len(row) > 5 else None
                    
                    # Check objections in appointment first, then call_analyses
                    classified_objections = []
                    if appointment and appointment.objections:
                        from app.domain.objection_classifier import ObjectionClassifier
                        classified_objections = ObjectionClassifier.classify_and_deduplicate(appointment.objections)
                    elif analysis:
                        classified_objections = self._classify_objections_in_analysis(analysis)
                else:
                    # Row structure: (user_id, first_name, last_name, call_id, CallAnalysisORM)
                    analysis = row[-1]  # CallAnalysisORM is the last element
                    classified_objections = self._classify_objections_in_analysis(analysis)
                
                # Check if any objections match target categories
                if not any(obj in target_categories for obj in classified_objections):
                    continue

                # Count this call/appointment for the rep
                if user_id_val not in rep_counts:
                    rep_counts[user_id_val] = {
                        'first_name': first_name,
                        'last_name': last_name,
                        'count': 0
                    }
                rep_counts[user_id_val]['count'] += 1

            # Sort by count descending and build response
            most_coaching_need_data = []
            for user_id_val, data in sorted(rep_counts.items(), key=lambda x: x[1]['count'], reverse=True):
                first_name = data['first_name']
                last_name = data['last_name']
                unbooked_count = data['count']
                name = None
                if first_name and last_name:
                    name = f"{first_name} {last_name}"
                elif first_name:
                    name = first_name
                elif last_name:
                    name = last_name
                else:
                    name = "Unknown"
                
                most_coaching_need_data.append({
                    "csr_id": str(user_id_val),  # Keep field name for backward compatibility
                    "csr_name": name,  # Keep field name for backward compatibility
                    "unbooked_calls": unbooked_count,
                })
            
            return {
                "objection": objection,
                "calls": calls_data,
                "unbooked_leads": unbooked_leads_data,
                "most_coaching_need": most_coaching_need_data,
            }
            
        except Exception as e:
            logger.error(f"Error getting calls by objection self: {e}")
            traceback.print_exc()
            raise
    
    async def get_objection_details(
        self,
        company_id: UUID,
        objection: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive objection details for a single objection.
        
        Returns data for all three tabs:
        1. Unbooked leads: Leads with booking rate improvement and graph data
        2. Most coaching need: CSRs with unbooked calls for that objection
        3. Calls: Call recordings with contact names
        
        Args:
            company_id: Company UUID
            objection: Objection type (e.g., 'authority', 'price', 'timing')
            start_date: Start date for filtering (YYYY-MM-DD, optional)
            end_date: End date for filtering (YYYY-MM-DD, optional)
            user_id: Optional user ID to filter by (for CSR role)
        
        Returns:
            Dictionary with comprehensive objection details including:
            - objection: Objection type
            - unbooked_leads: Tab data with booking rate improvement and graph
            - most_coaching_need: Tab data with CSRs and unbooked calls
            - calls: Tab data with call recordings and contact names
        """
        try:
            from app.infrastructure.database.models.lead import LeadORM
            from app.infrastructure.database.models.user import UserORM
            from app.domain.objection_classifier import ObjectionClassifier

            # Parse dates
            if start_date:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=None)
            else:
                start_dt = datetime.now().replace(tzinfo=None) - timedelta(days=30)

            if end_date:
                end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=None)
            else:
                end_dt = datetime.now().replace(tzinfo=None)

            # Expand objection filter to include new categories
            target_categories = ObjectionClassifier.expand_objection_filter(objection)
            
            unbooked_statuses = ['new', 'warm', 'hot', 'qualified_unbooked', 'qualified_service_not_offered', 'nurturing']

            # 1. UNBOOKED LEADS TAB - Get booking rate improvement and graph data
            # Fetch all qualified leads with objections, then filter by classification in Python
            qualified_leads_query = select(
                LeadORM,
                ContactCardORM,
                CallAnalysisORM
            ).join(
                CallORM, CallORM.lead_id == LeadORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, LeadORM.contact_card_id == ContactCardORM.id
            ).where(
                LeadORM.company_id == company_id,
                LeadORM.created_at >= start_dt,
                LeadORM.created_at <= end_dt,
                LeadORM.status.in_(['qualified_booked', 'qualified_unbooked']),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                _metrics_exclude_existing_and_service_not_offered(),
            )

            if user_id:
                qualified_leads_query = qualified_leads_query.where(CallORM.handled_by_user_id == user_id)

            qualified_results = await self.session.execute(qualified_leads_query)
            qualified_rows_raw = qualified_results.all()

            # Filter by classification in Python
            qualified_rows = []
            seen_lead_ids = set()
            for lead, contact, analysis in qualified_rows_raw:
                # Skip duplicates (same lead may have multiple calls)
                if lead.id in seen_lead_ids:
                    continue

                # Classify objections and check if any match target categories
                classified_objections = self._classify_objections_in_analysis(analysis)
                if any(obj in target_categories for obj in classified_objections):
                    qualified_rows.append((lead, contact))
                    seen_lead_ids.add(lead.id)
            
            # Calculate booking rate improvement
            total_qualified = len(qualified_rows)
            booked_count = sum(1 for lead, contact in qualified_rows if lead.status == 'qualified_booked')
            unbooked_count = sum(1 for lead, contact in qualified_rows if lead.status == 'qualified_unbooked')
            
            # Split into two periods for comparison (using lead created_at for period split)
            mid_date = start_dt + (end_dt - start_dt) / 2
            first_period_booked = sum(1 for lead, contact in qualified_rows 
                                     if lead.status == 'qualified_booked' and lead.created_at and lead.created_at < mid_date)
            first_period_total = sum(1 for lead, contact in qualified_rows 
                                    if lead.created_at and lead.created_at < mid_date)
            second_period_booked = sum(1 for lead, contact in qualified_rows 
                                      if lead.status == 'qualified_booked' and lead.created_at and lead.created_at >= mid_date)
            second_period_total = sum(1 for lead, contact in qualified_rows 
                                     if lead.created_at and lead.created_at >= mid_date)
            
            first_period_rate = (first_period_booked / first_period_total * 100) if first_period_total > 0 else 0
            second_period_rate = (second_period_booked / second_period_total * 100) if second_period_total > 0 else 0
            improvement_percentage = second_period_rate - first_period_rate
            
            # Generate graph data (daily booking rate over time)
            graph_data = []
            current_date = start_dt
            while current_date <= end_dt:
                day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end = day_start + timedelta(days=1)
                
                day_qualified = sum(1 for lead, contact in qualified_rows 
                                  if lead.created_at and day_start <= lead.created_at < day_end)
                day_booked = sum(1 for lead, contact in qualified_rows 
                               if lead.status == 'qualified_booked' and lead.created_at and day_start <= lead.created_at < day_end)
                
                booking_rate = (day_booked / day_qualified * 100) if day_qualified > 0 else 0
                
                graph_data.append({
                    "date": day_start.strftime("%Y-%m-%d"),
                    "booking_rate": round(booking_rate, 2),
                    "qualified_count": day_qualified,
                    "booked_count": day_booked
                })
                
                current_date += timedelta(days=1)
            
            # Get unbooked leads list with name and phone
            unbooked_leads_list = []
            for lead, contact_card in qualified_rows:
                if lead.status == 'qualified_unbooked':
                    contact_name = None
                    if contact_card:
                        first_name = contact_card.first_name or ""
                        last_name = contact_card.last_name or ""
                        contact_name = f"{first_name} {last_name}".strip() or None
                    
                    unbooked_leads_list.append({
                        "id": str(lead.id),
                        "contact_name": contact_name,
                        "phone_number": contact_card.primary_phone if contact_card else None,
                        "status": lead.status,
                        "deal_status": lead.deal_status,
                        "created_at": lead.created_at.isoformat() if lead.created_at else None,
                    })
            
            # 2. MOST COACHING NEED TAB - CSRs with unbooked calls
            # Fetch all CSRs with unbooked calls, then filter by classification in Python
            csr_unbooked_query = select(
                UserORM.id,
                UserORM.first_name,
                UserORM.last_name,
                CallORM.id.label('call_id'),
                CallAnalysisORM
            ).join(
                CallORM, CallORM.handled_by_user_id == UserORM.id
            ).join(
                CallAnalysisORM, CallAnalysisORM.call_id == CallORM.id
            ).join(
                LeadORM, CallORM.lead_id == LeadORM.id
            ).where(
                UserORM.company_id == company_id,
                UserORM.role == 'csr',
                UserORM.is_active == True,
                LeadORM.status.in_(unbooked_statuses),
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                _metrics_exclude_existing_and_service_not_offered(),
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt
            )

            csr_results = await self.session.execute(csr_unbooked_query)
            csr_rows_raw = csr_results.all()

            # Filter by classification in Python and count per CSR
            csr_call_counts = {}
            for user_id_val, first_name, last_name, call_id, analysis in csr_rows_raw:
                # Classify objections and check if any match target categories
                classified_objections = self._classify_objections_in_analysis(analysis)
                if any(obj in target_categories for obj in classified_objections):
                    if user_id_val not in csr_call_counts:
                        csr_call_counts[user_id_val] = {
                            'first_name': first_name,
                            'last_name': last_name,
                            'count': 0
                        }
                    csr_call_counts[user_id_val]['count'] += 1

            # Sort by count descending
            sorted_csrs = sorted(csr_call_counts.items(), key=lambda x: x[1]['count'], reverse=True)

            most_coaching_need_data = []
            for user_id_val, data in sorted_csrs:
                name = None
                if data['first_name'] and data['last_name']:
                    name = f"{data['first_name']} {data['last_name']}"
                elif data['first_name']:
                    name = data['first_name']
                elif data['last_name']:
                    name = data['last_name']
                else:
                    name = "Unknown"

                most_coaching_need_data.append({
                    "csr_id": str(user_id_val),
                    "csr_name": name,
                    "unbooked_calls": data['count'],
                })
            
            # 3. CALLS TAB - Call recordings with contact names
            # Fetch all calls with objections, then filter by classification in Python
            calls_query = select(
                CallORM,
                CallAnalysisORM,
                ContactCardORM
            ).join(
                CallORM, CallAnalysisORM.call_id == CallORM.id
            ).outerjoin(
                ContactCardORM, CallORM.contact_card_id == ContactCardORM.id
            ).where(
                CallAnalysisORM.company_id == company_id,
                CallAnalysisORM.objections.isnot(None),
                func.array_length(CallAnalysisORM.objections, 1) > 0,
                _metrics_exclude_existing_and_service_not_offered(),
                CallORM.created_at >= start_dt,
                CallORM.created_at <= end_dt
            )

            if user_id:
                calls_query = calls_query.where(CallORM.handled_by_user_id == user_id)

            calls_query = calls_query.order_by(CallORM.created_at.desc())

            calls_results = await self.session.execute(calls_query)
            calls_rows = calls_results.all()

            # Filter by classification in Python
            calls_data = []
            for call, analysis, contact_card in calls_rows:
                # Classify objections and check if any match target categories
                classified_objections = self._classify_objections_in_analysis(analysis)
                if not any(obj in target_categories for obj in classified_objections):
                    continue

                # Get contact name
                contact_name = None
                if contact_card:
                    first_name = contact_card.first_name or ""
                    last_name = contact_card.last_name or ""
                    contact_name = f"{first_name} {last_name}".strip() or None
                    if not contact_name:
                        contact_name = contact_card.primary_phone

                calls_data.append({
                    "id": str(call.id),
                    "contact_name": contact_name or "Unknown",
                    "call_recording_url": call.audio_url,
                    "phone_number": call.phone_number,
                    "call_type": call.call_type,
                    "duration_seconds": call.duration_seconds,
                    "created_at": call.created_at.isoformat() if call.created_at else None,
                    "transcript": call.transcript,
                    "summary": analysis.summary if analysis else None,
                })
            
            return {
                "objection": objection,
                "unbooked_leads": {
                    "booking_rate_improvement": {
                        "title": "Booking Rate Improvement",
                        "percentage": round(improvement_percentage, 1),
                        "description": f"{round(improvement_percentage, 1)}% Increase in Booking Appointments",
                        "context": "Growth in qualified leads booked from start to end of the selected timeframe.",
                        "current_rate": round(second_period_rate, 1),
                        "previous_rate": round(first_period_rate, 1),
                        "total_qualified": total_qualified,
                        "booked_count": booked_count,
                        "unbooked_count": unbooked_count
                    },
                    "graph_data": graph_data,
                    "leads": unbooked_leads_list
                },
                "most_coaching_need": {
                    "total_csr": len(most_coaching_need_data),
                    "csrs": most_coaching_need_data
                },
                "calls": {
                    "total_calls": len(calls_data),
                    "call_recordings": calls_data
                },
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d")
            }
            
        except Exception as e:
            logger.error(f"Error getting objection details: {e}")
            traceback.print_exc()
            raise
