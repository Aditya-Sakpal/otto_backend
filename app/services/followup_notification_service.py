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
from app.infrastructure.database.models.appointment import AppointmentORM
from app.infrastructure.repositories.pending_action import PendingActionRepository
from app.infrastructure.repositories.rep_phone import RepPhoneRepository
from app.infrastructure.integrations.expo_push import get_expo_push_client
from app.domain.enums import UserRole, PendingActionStatus
from app.core.config import settings

logger = get_logger(__name__)

# EST timezone
EST = ZoneInfo("America/New_York")

# Notification thresholds in minutes
NOTIFICATION_THRESHOLDS = [15, 5]  # Notify at 15 min and 5 min before due

# Appointment reminder action type (rows materialized by appointment_reminder_service)
APPOINTMENT_REMINDER_ACTION_TYPE = "appointment_reminder"

# Rehash action type (rows materialized by rehash_service)
REHASH_ACTION_TYPE = "rehash"


def generic_task_reminder_eligible(due_at, now_utc) -> bool:
    """True if a generic task is inside its fire window: due_at <= now < due_at+grace.

    Replaces the old future-only `0 < minutes_until_due <= threshold` check. Firing
    AT/AFTER due (within a grace window) makes the single reminder survive process
    downtime through the window — it fires once on recovery. Combined with a DB
    notified_at marker, this is restart- and multi-replica-safe.
    """
    if due_at is None:
        return False
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=ZoneInfo("UTC"))
    grace = timedelta(minutes=settings.GENERIC_TASK_REMINDER_GRACE_MINUTES)
    return due_at <= now_utc < due_at + grace


class FollowUpNotificationService:
    """
    Service for checking and sending follow-up notifications.

    Scans pending_actions table for pending actions and notifies
    relevant users via WebSocket.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Track sent notifications to avoid duplicates
        # Key: f"{pending_action_id}:{threshold}"
        self._sent_notifications: set[str] = set()
        # Push delivery (reuses existing Expo infra + stored rep tokens).
        self._rep_phone_repo = RepPhoneRepository(db)
        self._expo_push = get_expo_push_client()

    async def check_and_notify(self) -> int:
        """
        Check all pending actions and send notifications.

        Returns:
            Number of notifications sent
        """
        total_sent = 0

        try:
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
            pending_actions = result.scalars().all()

            for action in pending_actions:
                notifications_sent = await self._process_action(action, now_utc)
                total_sent += notifications_sent

            if total_sent > 0:
                logger.info("Follow-up notifications sent", count=total_sent)

        except Exception as e:
            logger.error("Error checking follow-ups", error=str(e))

        return total_sent

    async def _process_action(self, action: PendingActionORM, now_utc: datetime) -> int:
        """
        Process a single pending action for follow-up notifications.

        Args:
            action: The pending action record
            now_utc: Current time in UTC

        Returns:
            Number of notifications sent
        """
        notifications_sent = 0

        if not action.due_at:
            return 0

        # Appointment reminders use grace-window firing + DB-backed idempotency
        # instead of the 15/5-min pre-due thresholds.
        if action.action_type == APPOINTMENT_REMINDER_ACTION_TYPE:
            return await self._process_appointment_reminder(action, now_utc)

        # Rehash opportunities use the same grace-window + DB idempotency pattern.
        if action.action_type == REHASH_ACTION_TYPE:
            return await self._process_rehash(action, now_utc)

        # Generic tasks (call_back / follow_up / post-meeting) now use the SAME
        # DB-backed, grace-window pattern as reminders/rehash — restart-,
        # downtime-, and multi-replica-safe. The reminder is stamped on the row
        # (extra_metadata.notified_at) WITHOUT changing the task's status.
        try:
            meta = action.extra_metadata or {}
            if meta.get("notified_at"):
                return 0  # already reminded — DB source of truth (survives restart)

            if not generic_task_reminder_eligible(action.due_at, now_utc):
                return 0  # before due, or past the grace window

            minutes_until_due = int((action.due_at - now_utc).total_seconds() / 60)
            sent = await self._send_notification(
                action=action,
                minutes_until_due=minutes_until_due,
                threshold=0,
            )
            if sent:
                repo = PendingActionRepository(self.db)
                await repo.mark_task_notified(action.id, datetime.now(ZoneInfo("UTC")))
                notifications_sent += 1

        except Exception as e:
            logger.error(
                "Error processing pending action",
                action_id=str(action.id),
                error=str(e)
            )

        return notifications_sent

    async def _process_appointment_reminder(
        self,
        action: PendingActionORM,
        now_utc: datetime,
    ) -> int:
        """Fire an appointment reminder during its grace window, once.

        Eligible when due_at <= now < due_at + GRACE and extra_metadata.notified_at
        is absent. After a successful send, persist notified_at + status=completed so
        restarts and repeated ticks never double-send.
        """
        try:
            meta = action.extra_metadata or {}
            if meta.get("notified_at"):
                return 0

            due_at_utc = action.due_at
            grace = timedelta(minutes=settings.APPOINTMENT_REMINDER_GRACE_MINUTES)
            if not (due_at_utc <= now_utc < due_at_utc + grace):
                return 0

            scheduled_start = self._reminder_scheduled_start(action, meta)
            minutes_until_appointment = None
            if scheduled_start is not None:
                minutes_until_appointment = int(
                    (scheduled_start - now_utc).total_seconds() / 60
                )

            sent = await self._send_notification(
                action=action,
                minutes_until_due=0,
                threshold=0,
                reminder_kind=meta.get("reminder_kind"),
                minutes_until_appointment=minutes_until_appointment,
            )

            if sent:
                repo = PendingActionRepository(self.db)
                await repo.mark_appointment_reminder_notified(
                    action.id, datetime.now(ZoneInfo("UTC"))
                )
                return 1
            return 0

        except Exception as e:
            logger.error(
                "Error processing appointment reminder",
                action_id=str(action.id),
                error=str(e),
            )
            return 0

    @staticmethod
    def _reminder_scheduled_start(
        action: PendingActionORM, meta: dict
    ) -> Optional[datetime]:
        """Resolve appointment scheduled_start from metadata for the payload."""
        raw = meta.get("scheduled_start")
        if not raw:
            return None
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt
        except (ValueError, TypeError):
            return None

    async def _process_rehash(
        self,
        action: PendingActionORM,
        now_utc: datetime,
    ) -> int:
        """Fire a rehash opportunity during its grace window, once.

        Same restart-safe pattern as appointment reminders: eligible when
        due_at <= now < due_at + REHASH grace and extra_metadata.notified_at is
        absent; on success persist notified_at + status=completed.
        """
        try:
            meta = action.extra_metadata or {}
            if meta.get("notified_at"):
                return 0

            due_at_utc = action.due_at
            grace = timedelta(minutes=settings.REHASH_NOTIFICATION_GRACE_MINUTES)
            if not (due_at_utc <= now_utc < due_at_utc + grace):
                return 0

            sent = await self._send_notification(
                action=action,
                minutes_until_due=0,
                threshold=0,
                rehash_category=meta.get("rehash_category"),
            )

            if sent:
                repo = PendingActionRepository(self.db)
                await repo.mark_rehash_notified(action.id, datetime.now(ZoneInfo("UTC")))
                return 1
            return 0

        except Exception as e:
            logger.error(
                "Error processing rehash opportunity",
                action_id=str(action.id),
                error=str(e),
            )
            return 0

    async def _send_notification(
        self,
        action: PendingActionORM,
        minutes_until_due: int,
        threshold: int,
        reminder_kind: Optional[str] = None,
        minutes_until_appointment: Optional[int] = None,
        rehash_category: Optional[str] = None,
    ) -> bool:
        """
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
        company_id = action.company_id

        # Determine target users
        if action.owner_id:
            # Notify specific owner
            user_ids = [action.owner_id]
            target_role = "owner"
        else:
            # Determine role based on action_type or call_id/appointment_id
            if action.action_type == REHASH_ACTION_TYPE:
                # Rehash is rep revenue work → notify sales reps
                user_ids = await self._get_users_by_role(company_id, UserRole.SALES_REP)
                target_role = "sales_rep"
            elif action.appointment_id:
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

        # Get additional context (call/appointment info)
        context_info = await self._get_context_info(action)

        is_reminder = action.action_type == APPOINTMENT_REMINDER_ACTION_TYPE
        is_rehash = action.action_type == REHASH_ACTION_TYPE

        if is_reminder:
            notif_type = "appointment_reminder"
        elif is_rehash:
            notif_type = "rehash_opportunity"
        else:
            notif_type = "follow_up_reminder"

        if is_reminder:
            message = action.raw_text or "Appointment reminder"
        elif is_rehash:
            message = action.raw_text or "Rehash opportunity"
        else:
            message = f"Pending action due in {minutes_until_due} minutes: {action.raw_text or action.action_type}"

        # Build notification payload
        notification = {
            "type": notif_type,
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
            "message": message,
            "timestamp": datetime.now(ZoneInfo("UTC")).isoformat()
        }

        if is_reminder:
            notification["reminder_kind"] = reminder_kind
            notification["minutes_until_appointment"] = minutes_until_appointment

        if is_rehash:
            notification["rehash_category"] = rehash_category

        # Send to target users (WebSocket — primary, authoritative transport).
        sent_count = await connection_manager.send_to_users(user_ids, notification)

        # Best-effort parallel push to the SAME recipients (reaches reps whose
        # app isn't actively connected). Additive: never affects the WebSocket
        # result, idempotency, or routing.
        push_attempted = await self._send_push(user_ids, notification, message)

        logger.info(
            "Sent follow-up notification",
            company_id=str(company_id),
            action_id=str(action.id),
            minutes_until_due=minutes_until_due,
            target_role=target_role,
            users_notified=sent_count,
            push_attempted=push_attempted,
            total_users=len(user_ids)
        )

        return sent_count > 0

    async def _send_push(self, user_ids, notification: dict, message: str) -> int:
        """Dispatch an Expo push to each recipient that has a registered token.

        Best-effort and fully isolated: a missing token skips that user; any Expo
        error is swallowed so push never affects WebSocket delivery, the return
        value, or idempotency. Returns the number of push dispatches attempted.
        """
        attempted = 0
        title = self._push_title(notification)
        for uid in user_ids:
            try:
                rep_phone = await self._rep_phone_repo.get_by_user(uid)
                token = getattr(rep_phone, "expo_push_token", None) if rep_phone else None
                if not token:
                    continue  # graceful fallback: WebSocket already attempted
                await self._expo_push.send_push(
                    expo_push_token=token,
                    title=title,
                    body=message,
                    data={
                        "type": notification.get("type"),
                        "pending_action_id": notification.get("pending_action_id"),
                        "appointment_id": notification.get("appointment_id"),
                        "lead_id": notification.get("lead_id"),
                    },
                )
                attempted += 1
            except Exception as e:
                logger.warning(
                    "Push dispatch failed (non-fatal; WebSocket unaffected)",
                    user_id=str(uid),
                    error=str(e),
                )
        return attempted

    @staticmethod
    def _push_title(notification: dict) -> str:
        """Human title per notification type."""
        return {
            "appointment_reminder": "Appointment reminder",
            "rehash_opportunity": "Re-engagement opportunity",
            "follow_up_reminder": "Task reminder",
        }.get(notification.get("type"), "Otto notification")

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

            if action.appointment_id:
                appointment_info = await self._get_appointment_info(action.appointment_id)
                if appointment_info:
                    context_info["appointment"] = appointment_info

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
        query = select(UserORM.id).where(
            and_(
                UserORM.company_id == company_id,
                UserORM.role == role,
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

    async def _get_appointment_info(self, appointment_id: UUID) -> Optional[dict]:
        """Get appointment and contact information for notification context."""
        try:
            query = select(AppointmentORM).where(AppointmentORM.id == appointment_id)
            result = await self.db.execute(query)
            appointment = result.scalar_one_or_none()
            if not appointment:
                return None

            appointment_info = {
                "appointment_id": str(appointment.id),
                "scheduled_start": appointment.scheduled_start.isoformat() if appointment.scheduled_start else None,
                "scheduled_end": appointment.scheduled_end.isoformat() if appointment.scheduled_end else None,
                "location_address": appointment.location_address,
                "outcome": appointment.outcome,
            }

            if appointment.contact_card_id:
                contact_query = select(ContactCardORM).where(
                    ContactCardORM.id == appointment.contact_card_id
                )
                contact_result = await self.db.execute(contact_query)
                contact = contact_result.scalar_one_or_none()
                if contact:
                    appointment_info["contact"] = {
                        "first_name": contact.first_name,
                        "last_name": contact.last_name,
                        "primary_phone": contact.primary_phone,
                        "email": contact.email,
                    }

            return appointment_info

        except Exception as e:
            logger.error(
                "Failed to get appointment info",
                appointment_id=str(appointment_id),
                error=str(e),
            )
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
