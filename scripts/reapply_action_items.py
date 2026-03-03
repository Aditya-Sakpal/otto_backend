from pathlib import Path

src = Path(".git_prev_call_service.utf8.py")
dst = Path("app/services/call_service.py")

if not src.exists():
    print("Source not found:", src)
    raise SystemExit(1)

s = src.read_text(encoding="utf-8")

# Ensure isoformat_utc import is present
if "from app.core.datetime_utils import isoformat_utc" not in s:
    # insert after other imports (after app.core.logging)
    s = s.replace("from app.core.logging import get_logger", "from app.core.logging import get_logger\nfrom app.core.datetime_utils import isoformat_utc")

old = "                    # Insert into database\n                    await self.pending_action_repo.create(pending_action)\n                    logger.debug(\n                        \"Pending action created\",\n                        call_id=str(call.id),\n                        action_type=action_type,\n                        due_at=due_at.isoformat() if due_at else None,\n                    )"

new = """                    # Insert into database (primary)
                    created_pending = await self.pending_action_repo.create(pending_action)
                    # Also mirror into action_items for task visibility; non-fatal if it fails
                    try:
                        from sqlalchemy import text
                        import json

                        insert_sql = text(\"\"\"\n+                            INSERT INTO action_items (\n+                                id, company_id, lead_id, call_id, appointment_id,\n+                                action_type, raw_text, status, due_at, priority,\n+                                owner_id, source, extra_metadata, created_at, assigned_by_id\n+                            ) VALUES (\n+                                uuid_generate_v4(), :company_id, :lead_id, :call_id, :appointment_id,\n+                                :action_type, :raw_text, :status, :due_at, :priority,\n+                                :owner_id, :source, :extra_metadata, CURRENT_TIMESTAMP, :assigned_by_id\n+                            )\n+                        \"\"\")

                        await self.session.execute(\n+                            insert_sql,\n+                            {\n+                                \"company_id\": str(call.company_id) if call.company_id else None,\n+                                \"lead_id\": str(call.lead_id) if call.lead_id else None,\n+                                \"call_id\": str(call.id),\n+                                \"appointment_id\": None,\n+                                \"action_type\": action_type,\n+                                \"raw_text\": raw_text,\n+                                \"status\": \"pending\",\n+                                \"due_at\": due_at,\n+                                \"priority\": priority,\n+                                \"owner_id\": str(owner_id) if owner_id else None,\n+                                \"source\": \"shunya\",\n+                                \"extra_metadata\": json.dumps(pending_action.extra_metadata) if pending_action.extra_metadata else None,\n+                                \"assigned_by_id\": None,\n+                            },\n+                        )\n+                    except Exception:\n+                        logger.exception(\"Failed to insert action_item record; continuing\")\n+\n+                    # Log creation using UTC-safe formatting\n+                    try:\n+                        logger.debug(\n+                            \"Pending action created\",\n+                            call_id=str(call.id),\n+                            action_type=action_type,\n+                            due_at=isoformat_utc(due_at) if due_at else None,\n+                        )\n+                    except Exception:\n+                        logger.exception(\"Failed to log pending action creation\")"""

if old in s:
    s = s.replace(old, new)
else:
    print("Could not find exact old snippet; attempting heuristic replace.")
    s = s.replace("await self.pending_action_repo.create(pending_action)", "created_pending = await self.pending_action_repo.create(pending_action)")
    # insert mirror block after created_pending
    s = s.replace("created_pending = await self.pending_action_repo.create(pending_action)\n                    logger.debug(", new + "\n                    logger.debug(")

dst.write_text(s, encoding="utf-8")
print("Wrote", dst)

