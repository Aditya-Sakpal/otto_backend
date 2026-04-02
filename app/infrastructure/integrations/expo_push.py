"""
Expo Push Notifications client.

Sends server-initiated push notifications to the React Native mobile app
via the Expo Push API. Used to alert reps when homeowners call or text
their proxy number.

Follows the same singleton pattern as ShoonyaClient / TwilioClient.
"""
from typing import Optional, Dict, Any, List
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class ExpoPushClient:
    """Client for the Expo Push Notifications API."""

    def __init__(self):
        self._http_client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    async def send_push(
        self,
        expo_push_token: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        sound: str = "default",
        badge: Optional[int] = None,
        category_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a single push notification via Expo.

        Args:
            expo_push_token: The recipient's Expo push token (ExponentPushToken[xxx])
            title: Notification title
            body: Notification body text
            data: Optional JSON payload for the app to handle on tap
            sound: Sound name (default: "default")
            badge: Optional badge count
            category_id: Optional notification category for action buttons
        """
        if not expo_push_token or not expo_push_token.startswith("ExponentPushToken"):
            logger.warning(
                "Invalid or missing Expo push token — skipping notification",
                token=expo_push_token,
            )
            return {"status": "skipped", "reason": "invalid_token"}

        payload: Dict[str, Any] = {
            "to": expo_push_token,
            "title": title,
            "body": body,
            "sound": sound,
        }
        if data:
            payload["data"] = data
        if badge is not None:
            payload["badge"] = badge
        if category_id:
            payload["categoryId"] = category_id

        try:
            response = await self._http_client.post(
                EXPO_PUSH_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            result = response.json()
            logger.info(
                "Sent Expo push notification",
                token=expo_push_token[:30],
                title=title,
            )
            return result
        except httpx.HTTPError as e:
            logger.error(
                "Failed to send Expo push notification",
                error=str(e),
                token=expo_push_token[:30],
            )
            return {"status": "error", "error": str(e)}

    async def send_bulk(
        self, notifications: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Send multiple push notifications in one request.

        Each item in notifications should be a dict with:
        to, title, body, and optionally data, sound, badge.
        """
        try:
            response = await self._http_client.post(
                EXPO_PUSH_URL,
                json=notifications,
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            return response.json().get("data", [])
        except httpx.HTTPError as e:
            logger.error("Failed to send bulk Expo push", error=str(e))
            return []


# Singleton
_expo_push_client: Optional[ExpoPushClient] = None


def get_expo_push_client() -> ExpoPushClient:
    """Get or create the global ExpoPushClient instance."""
    global _expo_push_client
    if _expo_push_client is None:
        _expo_push_client = ExpoPushClient()
    return _expo_push_client
