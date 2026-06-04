"""
WebSocket routes for real-time notifications.

Provides WebSocket endpoints for clients to receive real-time
notifications about follow-up calls and other events.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from uuid import UUID

from app.core.logging import get_logger
from app.core.security import decode_token, get_user_id_from_token
from app.core.websocket_manager import connection_manager
from app.infrastructure.database.session import AsyncSessionLocal
from app.domain.users.service import UserService

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token")
):
    """
    WebSocket endpoint for receiving real-time notifications.
    
    Connect with: ws://host/api/v1/ws/notifications?token=<jwt_token>
    
    The server will send notifications for:
    - Follow-up call reminders (15 min, 5 min before due)
    - Appointment reminders (day-before, morning-of, one-hour-before)
    - Rehash opportunities (qualified_unbooked, appointment_pending, stale_lead)
    - Other real-time events

    Message format:
    {
        "type": "follow_up_reminder",
        "call_id": "uuid",
        "minutes_until_due": 15,
        "message": "Follow-up call due in 15 minutes",
        "call_info": {...},
        ...
    }

    Appointment reminder message format:
    {
        "type": "appointment_reminder",
        "reminder_kind": "morning_of",   # day_before | morning_of | one_hour_before
        "pending_action_id": "uuid",
        "appointment_id": "uuid",
        "minutes_until_appointment": 120,
        "context_info": {"appointment": {...}},
        "message": "Appointment today at 2:00 PM",
        ...
    }

    Rehash opportunity message format:
    {
        "type": "rehash_opportunity",
        "rehash_category": "qualified_unbooked",  # | appointment_pending | stale_lead
        "pending_action_id": "uuid",
        "lead_id": "uuid",
        "raw_text": "Rehash: qualified lead never booked — reach out to schedule",
        "minutes_until_due": 0,
        ...
    }
    """
    user_id = None
    
    try:
        # Authenticate user from token
        payload = decode_token(token, token_type="access")
        user_id_str = payload.get("sub")
        
        if not user_id_str:
            await websocket.close(code=4001, reason="Invalid token")
            return
        
        user_id = UUID(user_id_str)
        
        # Get user's company_id from database
        async with AsyncSessionLocal() as session:
            user_service = UserService(session)
            user = await user_service.get_by_id(user_id_str)
            
            if not user:
                await websocket.close(code=4001, reason="User not found")
                return
            
            if not user.is_active:
                await websocket.close(code=4003, reason="User inactive")
                return
            
            if not user.company_id:
                await websocket.close(code=4004, reason="User has no company")
                return
            
            company_id = user.company_id
        
        # Accept connection and register
        await connection_manager.connect(websocket, user_id, company_id)
        
        # Send connection confirmation
        await websocket.send_json({
            "type": "connection_established",
            "user_id": str(user_id),
            "company_id": str(company_id),
            "message": "Connected to notification service"
        })
        
        logger.info(
            "WebSocket connection established",
            user_id=str(user_id),
            company_id=str(company_id)
        )
        
        # Keep connection alive and listen for client messages
        while True:
            try:
                # Wait for any client messages (ping/pong, disconnect, etc.)
                data = await websocket.receive_json()
                
                # Handle ping messages
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except WebSocketDisconnect:
                logger.info("Client disconnected", user_id=str(user_id))
                break
            except Exception as e:
                logger.warning(
                    "Error receiving WebSocket message",
                    user_id=str(user_id),
                    error=str(e)
                )
                break
    
    except Exception as e:
        logger.error("WebSocket error", error=str(e))
        try:
            await websocket.close(code=4000, reason="Authentication failed")
        except Exception:
            pass
    
    finally:
        # Clean up connection
        if user_id:
            connection_manager.disconnect(user_id)
