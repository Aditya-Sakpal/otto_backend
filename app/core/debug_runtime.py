from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4


_DEBUG_LOG_PATH = Path(__file__).resolve().parents[3] / "debug-55652f.log"
_SESSION_ID = "55652f"


def emit_debug_log(
    *,
    hypothesis_id: str,
    location: str,
    message: str,
    data: Optional[dict[str, Any]] = None,
    run_id: str = "run1",
) -> None:
    """Append one NDJSON debug event for runtime hypothesis testing."""
    payload = {
        "sessionId": _SESSION_ID,
        "id": f"log_{int(time.time() * 1000)}_{uuid4().hex[:8]}",
        "timestamp": int(time.time() * 1000),
        "runId": run_id,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
    }
    try:
        with _DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        # Never impact request/task behavior due to debug logging.
        pass
