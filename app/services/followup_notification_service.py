"""
Follow-up notification service.

Checks pending actions and sends notifications
to sales reps when follow-up calls are due.
"""
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.websocket_manager import connection_manager
from app.infrastructure.database.models.pending_action import PendingActionORM
from app.infrastructure.database.models.user import UserORM
from app.infrastructure.database.models.call import CallORM
from app.infrastructure.database.models.contact import ContactCardORM
from app.domain.enums import UserRole, PendingActionStatus

logger = get_logger(__name__)

# EST timezone
EST = ZoneInfo("America/New_York")

# Notification thresholds in minutes
NOTIFICATION_THRESHOLDS = [15, 5]  # Notify at 15 min and 5 min before due


class FollowUpNotificationService:
    """
    Service for checking and sending follow-up notifications.

    Scans call_analyses for pending follow-up calls and notifies
    relevant sales reps via WebSocket.

    Scans pending_actions table for pending actions and notifies
    relevant users via WebSocket.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Track sent notifications to avoid duplicates
        # Key: f"{pending_action_id}:{threshold}"
        self._sent_notifications: set[str] = set()

    async def check_and_notify(self) -> int:
        """
        Check all pending follow-ups and send notifications.

        Check all pending actions and send notifications.

        Returns:
            Number of notifications sent
        """
        total_sent = 0

        try:
            # Get current time in EST
            now_est = datetime.now(EST)
            logger.debug("Checking follow-ups", current_time_est=now_est.isoformat())

            # Query all call_analyses with pending_actions
            query = select(CallAnalysisORM).where(
                CallAnalysisORM.pending_actions.isnot(None)
            # Get current time in UTC (stored in DB as UTC)
            now_utc = datetime.now(ZoneInfo("UTC"))
            logger.debug("Checking follow-ups", current_time_utc=now_utc.isoformat())

            # Query all pending actions with due_at set
            query = select(PendingActionORM).where(
                and_(
                    PendingActionORM.status == PendingActionStatus.PENDING.value,
                    PendingActionORM.due_at.isnot(None)
                )
            )
            result = await self.db.execute(query)
            analyses = result.scalars().all()

            for analysis in analyses:
                notifications_sent = await self._process_analysis(analysis, now_est)
            pending_actions = result.scalars().all()

            for action in pending_actions:
                notifications_sent = await self._process_action(action, now_utc)
                total_sent += notifications_sent

            if total_sent > 0:
                logger.info("Follow-up notifications sent", count=total_sent)

        except Exception as e:
            logger.error("Error checking follow-ups", error=str(e))

        return total_sent

    async def _process_analysis(self, analysis: CallAnalysisORM, now_est: datetime) -> int:

    async def _process_action(self, action: PendingActionORM, now_utc: datetime) -> int:
        """
        Process a single call analysis for follow-up notifications.

        Process a single pending action for follow-up notifications.

        Args:
            analysis: The call analysis record
            now_est: Current time in EST

            action: The pending action record
            now_utc: Current time in UTC

        Returns:
            Number of notifications sent
        """
        notifications_sent = 0

        if not analysis.pending_actions:

        if not action.due_at:
            return 0

        for idx, action_str in enumerate(analysis.pending_actions):
            try:
                # Parse JSON string to dict
                action = json.loads(action_str)

                # Check if it's a follow_up_call
                if action.get("type") != "follow_up_call":
                    continue

                # Check if due_at exists
                due_at_str = action.get("due_at")
                if not due_at_str:
                    continue

                # Parse due_at (assumed to be in EST)
                due_at = self._parse_due_at(due_at_str)
                if not due_at:
                    continue

                # Calculate minutes until due
                minutes_until_due = (due_at - now_est).total_seconds() / 60

                # Check each threshold
                for threshold in NOTIFICATION_THRESHOLDS:
                    if 0 < minutes_until_due <= threshold:
                        notification_key = f"{analysis.id}:{idx}:{threshold}"

                        # Skip if already notified for this threshold
                        if notification_key in self._sent_notifications:
                            continue

                        # Send notification
                        sent = await self._send_notification(
                            analysis=analysis,
                            action=action,
                            minutes_until_due=int(minutes_until_due),
                            threshold=threshold
                        )

                        if sent:
                            self._sent_notifications.add(notification_key)
                            notifications_sent += 1

                        # Only send one threshold notification per check cycle
                        break

            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse pending action",
                    analysis_id=str(analysis.id),
                    index=idx,
                    error=str(e)
                )
            except Exception as e:
                logger.error(
                    "Error processing pending action",
                    analysis_id=str(analysis.id),
                    index=idx,
                    error=str(e)
                )


        try:
            # due_at is stored in UTC
            due_at_utc = action.due_at

            # Calculate minutes until due
            minutes_until_due = (due_at_utc - now_utc).total_seconds() / 60

            # Check each threshold
            for threshold in NOTIFICATION_THRESHOLDS:
                if 0 < minutes_until_due <= threshold:
                    notification_key = f"{action.id}:{threshold}"

                    # Skip if already notified for this threshold
                    if notification_key in self._sent_notifications:
                        continue

                    # Send notification
                    sent = await self._send_notification(
                        action=action,
                        minutes_until_due=int(minutes_until_due),
                        threshold=threshold
                    )

                    if sent:
                        self._sent_notifications.add(notification_key)
                        notifications_sent += 1

                    # Only send one threshold notification per check cycle
                    break

        except Exception as e:
            logger.error(
                "Error processing pending action",
                action_id=str(action.id),
                error=str(e)
            )

        return notifications_sent

    def _parse_due_at(self, due_at_str: str) -> Optional[datetime]:
        """
        Parse due_at string to datetime in EST.

        Args:
            due_at_str: Due at string (various formats)

        Returns:
            Parsed datetime in EST or None
        """
        if not due_at_str or due_at_str == "null":
            return None

        # Normalize short timezone offsets like -05 to -05:00
        import re
        normalized_str = due_at_str
        # Match patterns like -05 or +05 at the end (short offset without minutes)
        short_tz_match = re.search(r'([+-])(\d{2})$', due_at_str)
        if short_tz_match:
            # Convert -05 to -05:00
            normalized_str = due_at_str[:-3] + short_tz_match.group(1) + short_tz_match.group(2) + ":00"

        # Try various formats
        formats = [
            "%Y-%m-%d %H:%M:%S%z",       # 2026-01-15 22:30:00-05:00
            "%Y-%m-%d %H:%M:%S",          # 2026-01-15 22:30:00
            "%Y-%m-%dT%H:%M:%S%z",        # ISO format with timezone
            "%Y-%m-%dT%H:%M:%S",          # ISO format without timezone
            "%Y-%m-%d %H:%M:%S.%f%z",     # With microseconds
            "%Y-%m-%dT%H:%M:%S.%f%z",     # ISO with microseconds
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(normalized_str, fmt)
                # If no timezone, assume EST
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=EST)
                return dt
            except ValueError:
                continue

        logger.warning("Could not parse due_at", due_at_str=due_at_str)
        return None


    async def _send_notification(
        self,
        action: PendingActionORM,
        minutes_until_due: int,
        threshold: int
    ) -> bool:
        """
        Send notification to relevant users based on contact_method.

        - contact_method="phone" → notify CSR users
        - contact_method="appointment" → notify SALES_REP users

        Send notification to relevant users.

        If owner_id is set, notify that user. Otherwise, determine based on action_type:
        - appointment-related → notify SALES_REP users
        - call-related → notify CSR users

        Args:
            action: The pending action record
            minutes_until_due: Minutes until the follow-up is due
            threshold: Which threshold triggered this notification

        Returns:
            True if at least one notification was sent
        """
        company_id = analysis.company_id
        contact_method = action.get("contact_method", "phone")

        # Route to appropriate users based on contact_method
        if contact_method == "appointment":
            user_ids = await self._get_users_by_role(company_id, UserRole.SALES_REP)
            target_role = "sales_rep"
        else:
            # Default to CSR for "phone" and other contact methods
            user_ids = await self._get_users_by_role(company_id, UserRole.CSR)
            target_role = "csr"

        company_id = action.company_id

        # Determine target users
        if action.owner_id:
            # Notify specific owner
            user_ids = [action.owner_id]
            target_role = "owner"
        else:
            # Determine role based on action_type or call_id/appointment_id
            if action.appointment_id:
                # Appointment recording → notify sales reps
                user_ids = await self._get_users_by_role(company_id, UserRole.SALES_REP)
                target_role = "sales_rep"
            elif action.call_id:
                # Call recording → notify CSRs
                user_ids = await self._get_users_by_role(company_id, UserRole.CSR)
                target_role = "csr"
            else:
                # Default to CSR
                user_ids = await self._get_users_by_role(company_id, UserRole.CSR)
                target_role = "csr"

        if not user_ids:
            logger.debug(
                "No users found for company",
                company_id=str(company_id),
                target_role=target_role
            )
            return False

        # Get additional context (call info, contact info)
        call_info = await self._get_call_info(analysis.call_id)


        # Get additional context (call/appointment info)
        context_info = await self._get_context_info(action)

        # Build notification payload
        notification = {
            "type": "follow_up_reminder",
            "pending_action_id": str(action.id),
            "company_id": str(company_id),
            "lead_id": str(action.lead_id) if action.lead_id else None,
            "call_id": str(action.call_id) if action.call_id else None,
            "appointment_id": str(action.appointment_id) if action.appointment_id else None,
            "due_at": action.due_at.isoformat() if action.due_at else None,
            "minutes_until_due": minutes_until_due,
            "threshold": threshold,
            "action_type": action.action_type,
            "raw_text": action.raw_text,
            "priority": action.priority,
            "context_info": context_info,
            "message": f"Pending action due in {minutes_until_due} minutes: {action.raw_text or action.action_type}",
            "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
        }

        # Send to target users
        sent_count = await connection_manager.send_to_users(user_ids, notification)

        logger.info(
            "Sent follow-up notification",
            company_id=str(company_id),
            action_id=str(action.id),
            minutes_until_due=minutes_until_due,
            target_role=target_role,
            users_notified=sent_count,
            total_users=len(user_ids)
        )

        return sent_count > 0


    async def _get_context_info(self, action: PendingActionORM) -> Optional[dict]:
        """
        Get context information (call/appointment) for the action.

        Args:
            action: The pending action record

        Returns:
            Dict with context info or None
        """
        context_info = {}

        try:
            # Get call info if available
            if action.call_id:
                call_info = await self._get_call_info(action.call_id)
                if call_info:
                    context_info["call"] = call_info

            # TODO: Get appointment info if action.appointment_id is set
            # For now, we'll just include call info

            return context_info if context_info else None

        except Exception as e:
            logger.error("Failed to get context info", action_id=str(action.id), error=str(e))
            return None

    async def _get_users_by_role(self, company_id: UUID, role: UserRole) -> list[UUID]:
        """
        Get all active user IDs for a company with a specific role.

        Args:
            company_id: The company UUID
            role: The user role to filter by

        Returns:
            List of user UUIDs with the specified role
        """
        # Convert enum to string value for comparison (ORM stores role as string)
        role_value = role.value if isinstance(role, UserRole) else role
        query = select(UserORM.id).where(
            and_(
                UserORM.company_id == company_id,
                UserORM.role == role_value,
                UserORM.is_active == True
            )
        )
        result = await self.db.execute(query)
        return [row[0] for row in result.fetchall()]

    async def _get_call_info(self, call_id: UUID) -> Optional[dict]:
        """
        Get call and contact information for context.

        Args:
            call_id: The call UUID

        Returns:
            Dict with call info or None
        """
        try:
            query = select(CallORM).where(CallORM.id == call_id)
            result = await self.db.execute(query)
            call = result.scalar_one_or_none()

            if not call:
                return None

            call_info = {
                "phone_number": call.phone_number,
                "call_type": call.call_type,
                "created_at": call.created_at.isoformat() if call.created_at else None
            }

            # Get contact info if available
            if call.contact_card_id:
                contact_query = select(ContactCardORM).where(
                    ContactCardORM.id == call.contact_card_id
                )
                contact_result = await self.db.execute(contact_query)
                contact = contact_result.scalar_one_or_none()

                if contact:
                    call_info["contact"] = {
                        "first_name": contact.first_name,
                        "last_name": contact.last_name,
                        "primary_phone": contact.primary_phone,
                        "email": contact.email
                    }

            return call_info

        except Exception as e:
            logger.error("Failed to get call info", call_id=str(call_id), error=str(e))
            return None

    def clear_sent_notifications(self) -> None:
        """Clear the sent notifications cache."""
        self._sent_notifications.clear()


# Global notification tracker (to persist across scheduler runs)
_sent_notifications_cache: set[str] = set()


async def check_follow_ups(db: AsyncSession) -> int:
    """
    Standalone function to check follow-ups.
    Uses global cache for tracking sent notifications.

    Args:
        db: Database session

    Returns:
        Number of notifications sent
    """
    service = FollowUpNotificationService(db)
    service._sent_notifications = _sent_notifications_cache

    result = await service.check_and_notify()

    # Update global cache
    _sent_notifications_cache.update(service._sent_notifications)

    return result
