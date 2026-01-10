"""
WebSocket connection manager.

Manages WebSocket connections for real-time notifications.
Tracks connections by user_id for targeted messaging.
"""
from typing import Dict, Optional
from uuid import UUID
from fastapi import WebSocket
from app.core.logging import get_logger

logger = get_logger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections.
    
    Maintains a registry of active connections mapped by user_id.
    Supports sending messages to specific users or broadcasting.
    """
    
    def __init__(self):
        # Map user_id -> WebSocket connection
        self._connections: Dict[UUID, WebSocket] = {}
        # Map user_id -> company_id (for company-wide broadcasts)
        self._user_companies: Dict[UUID, UUID] = {}
    
    async def connect(self, websocket: WebSocket, user_id: UUID, company_id: UUID) -> None:
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: The WebSocket connection
            user_id: The user's UUID
            company_id: The user's company UUID
        """
        await websocket.accept()
        self._connections[user_id] = websocket
        self._user_companies[user_id] = company_id
        logger.info(
            "WebSocket connected",
            user_id=str(user_id),
            company_id=str(company_id),
            total_connections=len(self._connections)
        )
    
    def disconnect(self, user_id: UUID) -> None:
        """
        Remove a WebSocket connection.
        
        Args:
            user_id: The user's UUID
        """
        if user_id in self._connections:
            del self._connections[user_id]
        if user_id in self._user_companies:
            del self._user_companies[user_id]
        logger.info(
            "WebSocket disconnected",
            user_id=str(user_id),
            total_connections=len(self._connections)
        )
    
    async def send_to_user(self, user_id: UUID, message: dict) -> bool:
        """
        Send a message to a specific user.
        
        Args:
            user_id: Target user's UUID
            message: Message dictionary to send
            
        Returns:
            True if message was sent, False if user not connected
        """
        websocket = self._connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
                logger.debug("Message sent to user", user_id=str(user_id))
                return True
            except Exception as e:
                logger.error(
                    "Failed to send WebSocket message",
                    user_id=str(user_id),
                    error=str(e)
                )
                # Remove dead connection
                self.disconnect(user_id)
                return False
        return False
    
    async def send_to_users(self, user_ids: list[UUID], message: dict) -> int:
        """
        Send a message to multiple users.
        
        Args:
            user_ids: List of target user UUIDs
            message: Message dictionary to send
            
        Returns:
            Number of users who received the message
        """
        sent_count = 0
        for user_id in user_ids:
            if await self.send_to_user(user_id, message):
                sent_count += 1
        return sent_count
    
    async def broadcast_to_company(self, company_id: UUID, message: dict) -> int:
        """
        Broadcast a message to all connected users in a company.
        
        Args:
            company_id: Target company UUID
            message: Message dictionary to send
            
        Returns:
            Number of users who received the message
        """
        sent_count = 0
        for user_id, user_company_id in self._user_companies.items():
            if user_company_id == company_id:
                if await self.send_to_user(user_id, message):
                    sent_count += 1
        return sent_count
    
    def get_connected_users_for_company(self, company_id: UUID) -> list[UUID]:
        """
        Get list of connected user IDs for a company.
        
        Args:
            company_id: Target company UUID
            
        Returns:
            List of connected user UUIDs
        """
        return [
            user_id for user_id, user_company_id in self._user_companies.items()
            if user_company_id == company_id
        ]
    
    def is_connected(self, user_id: UUID) -> bool:
        """
        Check if a user is currently connected.
        
        Args:
            user_id: The user's UUID
            
        Returns:
            True if user is connected
        """
        return user_id in self._connections
    
    @property
    def connection_count(self) -> int:
        """Get total number of active connections."""
        return len(self._connections)


# Global connection manager instance
connection_manager = ConnectionManager()
