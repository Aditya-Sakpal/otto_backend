from pathlib import Path

p = Path("app/services/call_service.py")
if not p.exists():
    print("call_service.py not found")
    raise SystemExit(1)

s = p.read_text(encoding="utf-8")
needle = "await self.pending_action_repo.create(pending_action)"
pos = s.find(needle)
if pos == -1:
    print("pattern not found")
    raise SystemExit(1)

# find logger.debug block that follows
dbg_pos = s.find("logger.debug(", pos)
if dbg_pos == -1:
    print("logger.debug block not found after create; aborting")
    raise SystemExit(1)

# find end of debug call (look for the closing parenthesis on its own indented line)
end_marker = "\n                    )\n"
end_idx = s.find(end_marker, dbg_pos)
if end_idx == -1:
    # fallback: find next occurrence of ")\n" after dbg_pos
    end_idx = s.find(")\n", dbg_pos)
    if end_idx == -1:
        print("could not find end of debug call")
        raise SystemExit(1)
    end_idx += 2
else:
    end_idx += len(end_marker)

start_idx = pos

new_block = (
    "created_pending = await self.pending_action_repo.create(pending_action)\n"
    "                    # Mirror into action_items table for visibility (non-fatal)\n"
    "                    try:\n"
    "                        from sqlalchemy import text\n"
    "                        import json\n\n"
    "                        insert_sql = text(\n"
    "                            \"\"\"\n"
    "                            INSERT INTO action_items (\n"
    "                                id, company_id, lead_id, call_id, appointment_id,\n"
    "                                action_type, raw_text, status, due_at, priority,\n"
    "                                owner_id, source, extra_metadata, created_at, assigned_by_id\n"
    "                            ) VALUES (\n"
    "                                uuid_generate_v4(), :company_id, :lead_id, :call_id, :appointment_id,\n"
    "                                :action_type, :raw_text, :status, :due_at, :priority,\n"
    "                                :owner_id, :source, :extra_metadata, CURRENT_TIMESTAMP, :assigned_by_id\n"
    "                            )\n"
    "                            \"\"\"\n"
    "                        )\n\n"
    "                        await self.session.execute(\n"
    "                            insert_sql,\n"
    "                            {\n"
    "                                \"company_id\": str(call.company_id) if call.company_id else None,\n"
    "                                \"lead_id\": str(call.lead_id) if call.lead_id else None,\n"
    "                                \"call_id\": str(call.id),\n"
    "                                \"appointment_id\": None,\n"
    "                                \"action_type\": action_type,\n"
    "                                \"raw_text\": raw_text,\n"
    "                                \"status\": \"pending\",\n"
    "                                \"due_at\": due_at,\n"
    "                                \"priority\": priority,\n"
    "                                \"owner_id\": str(owner_id) if owner_id else None,\n"
    "                                \"source\": \"shunya\",\n"
    "                                \"extra_metadata\": json.dumps(pending_action.extra_metadata) if pending_action.extra_metadata else None,\n"
    "                                \"assigned_by_id\": None,\n"
    "                            },\n"
    "                        )\n"
    "                    except Exception:\n"
    "                        logger.exception(\"Failed to insert action_item record; continuing\")\n\n"
    "                    # Log creation using UTC-safe formatter\n"
    "                    try:\n"
    "                        logger.debug(\n"
    "                            \"Pending action created\",\n"
    "                            call_id=str(call.id),\n"
    "                            action_type=action_type,\n"
    "                            due_at=isoformat_utc(due_at) if due_at else None,\n"
    "                        )\n"
    "                    except Exception:\n"
    "                        logger.exception(\"Failed to log pending action creation\")\n"
)

new_s = s[:start_idx] + new_block + s[end_idx:]
p.write_text(new_s, encoding="utf-8")
print("Inserted action_items mirror block into call_service.py")

