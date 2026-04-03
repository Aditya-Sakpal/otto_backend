"""
Script to populate KPI stats data for Ankit Rai (ankitrai@gomotto.com)
Company ID: ce9091df-db37-4e7e-877c-2ed0cf2f4c37

Run: python populate_ankit_kpi.py
"""
import asyncio
import ssl
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ── Config ──────────────────────────────────────────────────────────
DATABASE_URL = "postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"

COMPANY_ID = "ce9091df-db37-4e7e-877c-2ed0cf2f4c37"
USER_EMAIL = "ankitrai@gomotto.com"
# ────────────────────────────────────────────────────────────────────


def normalize_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def main():
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    engine = create_async_engine(
        normalize_url(DATABASE_URL),
        connect_args={"ssl": ssl_ctx, "statement_cache_size": 0},
    )

    now = datetime.now(timezone.utc)

    async with engine.begin() as conn:
        # ── Step 0: Get Ankit's user ID ─────────────────────────────
        row = await conn.execute(
            text("SELECT id FROM users WHERE email = :email"),
            {"email": USER_EMAIL},
        )
        user_row = row.fetchone()
        if not user_row:
            print(f"ERROR: User {USER_EMAIL} not found!")
            return
        user_id = str(user_row[0])
        print(f"Found user: {user_id}")

        # ── Step 1: Get or create contact cards for leads ───────────
        # Grab an existing contact card for this company
        row = await conn.execute(
            text(
                "SELECT id FROM contact_cards WHERE company_id = :cid LIMIT 3"
            ),
            {"cid": COMPANY_ID},
        )
        contact_cards = [str(r[0]) for r in row.fetchall()]
        if len(contact_cards) < 3:
            print(f"WARNING: Only {len(contact_cards)} contact cards found. Creating dummy ones.")
            for _ in range(3 - len(contact_cards)):
                cc_id = str(uuid.uuid4())
                await conn.execute(
                    text(
                        """INSERT INTO contact_cards (id, company_id, phone_number, created_at)
                           VALUES (:id, :cid, :phone, :ts)"""
                    ),
                    {
                        "id": cc_id,
                        "cid": COMPANY_ID,
                        "phone": f"+1555{uuid.uuid4().hex[:7]}",
                        "ts": now,
                    },
                )
                contact_cards.append(cc_id)

        cc1, cc2, cc3 = contact_cards[0], contact_cards[1], contact_cards[2]

        # ── Step 2: Create Leads (closed_won with deal_size) ────────
        lead_ids = [str(uuid.uuid4()) for _ in range(5)]
        leads_data = [
            {"id": lead_ids[0], "cc": cc1, "deal": 5000.0, "days_ago": 3, "status": "closed_won"},
            {"id": lead_ids[1], "cc": cc2, "deal": 8500.0, "days_ago": 7, "status": "closed_won"},
            {"id": lead_ids[2], "cc": cc3, "deal": 3200.0, "days_ago": 12, "status": "closed_won"},
            {"id": lead_ids[3], "cc": cc1, "deal": 6000.0, "days_ago": 18, "status": "closed_won"},
            {"id": lead_ids[4], "cc": cc2, "deal": 4500.0, "days_ago": 22, "status": "closed_won"},
        ]
        for ld in leads_data:
            await conn.execute(
                text(
                    """INSERT INTO leads (id, company_id, contact_card_id, status, deal_size,
                       assigned_rep_id, created_at)
                       VALUES (:id, :cid, :cc, :status, :deal, :uid, :ts)"""
                ),
                {
                    "id": ld["id"],
                    "cid": COMPANY_ID,
                    "cc": ld["cc"],
                    "status": ld["status"],
                    "deal": ld["deal"],
                    "uid": user_id,
                    "ts": now - timedelta(days=ld["days_ago"]),
                },
            )
        print(f"Created {len(leads_data)} leads (closed_won, avg deal ~$5440)")

        # ── Step 3: Create Calls linked to leads ────────────────────
        call_ids = [str(uuid.uuid4()) for _ in range(5)]
        for i, (call_id, lead_id) in enumerate(zip(call_ids, lead_ids)):
            await conn.execute(
                text(
                    """INSERT INTO calls (id, company_id, lead_id, phone_number,
                       handled_by_user_id, duration_seconds, missed_call, created_at)
                       VALUES (:id, :cid, :lid, :phone, :uid, :dur, false, :ts)"""
                ),
                {
                    "id": call_id,
                    "cid": COMPANY_ID,
                    "lid": lead_id,
                    "phone": f"+1555000{i:04d}",
                    "uid": user_id,
                    "dur": 300 + i * 60,
                    "ts": now - timedelta(days=leads_data[i]["days_ago"]),
                },
            )
        print(f"Created {len(call_ids)} calls")

        # ── Step 4: Create Call Analyses (follow_up + fresh_sales) ──
        for i, call_id in enumerate(call_ids):
            await conn.execute(
                text(
                    """INSERT INTO call_analyses (id, call_id, company_id, status,
                       follow_up_required, detected_call_type,
                       qualification_status, booking_status, created_at)
                       VALUES (:id, :cid2, :cid, 'completed', :fu, :dct, 'hot', 'booked', :ts)"""
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid2": call_id,
                    "cid": COMPANY_ID,
                    "fu": True,  # follow_up_required = true for all
                    "dct": "fresh_sales",  # first touch / cold outreach
                    "ts": now - timedelta(days=leads_data[i]["days_ago"]),
                },
            )
        print(f"Created {len(call_ids)} call analyses (follow_up=true, detected=fresh_sales)")

        # ── Step 5: Create Appointments (win rate + attendance + first touch) ─
        # 8 appointments: 5 won, 2 lost, 1 no_show → win_rate=62.5%, attendance=87.5%
        appt_data = [
            {"lead": lead_ids[0], "cc": cc1, "call": call_ids[0], "outcome": "won", "days_ago": 3},
            {"lead": lead_ids[1], "cc": cc2, "call": call_ids[1], "outcome": "won", "days_ago": 7},
            {"lead": lead_ids[2], "cc": cc3, "call": call_ids[2], "outcome": "won", "days_ago": 12},
            {"lead": lead_ids[3], "cc": cc1, "call": call_ids[3], "outcome": "won", "days_ago": 18},
            {"lead": lead_ids[4], "cc": cc2, "call": call_ids[4], "outcome": "won", "days_ago": 22},
            {"lead": lead_ids[0], "cc": cc1, "call": None, "outcome": "lost", "days_ago": 5},
            {"lead": lead_ids[1], "cc": cc2, "call": None, "outcome": "lost", "days_ago": 14},
            {"lead": lead_ids[2], "cc": cc3, "call": None, "outcome": "no_show", "days_ago": 20},
        ]
        for appt in appt_data:
            await conn.execute(
                text(
                    """INSERT INTO appointments (id, company_id, lead_id, contact_card_id,
                       scheduled_start, outcome, assigned_rep_id, interaction_id, created_at)
                       VALUES (:id, :cid, :lid, :cc, :ss, :outcome, :uid, :iid, :ts)"""
                ),
                {
                    "id": str(uuid.uuid4()),
                    "cid": COMPANY_ID,
                    "lid": appt["lead"],
                    "cc": appt["cc"],
                    "ss": now - timedelta(days=appt["days_ago"]),
                    "outcome": appt["outcome"],
                    "uid": user_id,
                    "iid": appt["call"],  # interaction_id links to call for first touch
                    "ts": now - timedelta(days=appt["days_ago"]),
                },
            )
        print(f"Created {len(appt_data)} appointments (5 won, 2 lost, 1 no_show)")

        # ── Step 6: Create AskOtto conversations + messages (Usage) ─
        for conv_idx in range(3):
            conv_id = str(uuid.uuid4())
            conv_ts = now - timedelta(days=conv_idx * 5 + 1)
            await conn.execute(
                text(
                    """INSERT INTO ask_otto_conversations (id, company_id, user_id, title, created_at)
                       VALUES (:id, :cid, :uid, :title, :ts)"""
                ),
                {
                    "id": conv_id,
                    "cid": COMPANY_ID,
                    "uid": user_id,
                    "title": f"Sales coaching session {conv_idx + 1}",
                    "ts": conv_ts,
                },
            )
            # Add messages spread over ~45 minutes each conversation
            for msg_idx in range(6):
                role = "user" if msg_idx % 2 == 0 else "assistant"
                await conn.execute(
                    text(
                        """INSERT INTO ask_otto_messages (id, conversation_id, role, content, created_at)
                           VALUES (:id, :cid, :role, :content, :ts)"""
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "cid": conv_id,
                        "role": role,
                        "content": f"Message {msg_idx + 1} in conversation {conv_idx + 1}",
                        "ts": conv_ts + timedelta(minutes=msg_idx * 8),
                    },
                )
        print("Created 3 AskOtto conversations with messages (~2h 15m total usage)")

    await engine.dispose()
    print("\n✅ Done! KPI summary for Ankit:")
    print("   • Usage:      ~2h 15m")
    print("   • Attendance:  87.5% (7/8 showed up)")
    print("   • Deal Size:   ~$5,440 avg")
    print("   • Follow-ups:  1x per deal")
    print("   • Win Rate:    62.5% (5/8 resolved)")
    print("   • First Touch: 100% (5/5 fresh_sales won)")


if __name__ == "__main__":
    asyncio.run(main())
