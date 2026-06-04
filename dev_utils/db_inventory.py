"""Direct Postgres inventory for staging validation matrix."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
COMPANY = os.environ.get("OTTO_COMPANY_ID", "ce9091df-db37-4e7e-877c-2ed0cf2f4c37")


def sync_url() -> str:
    url = os.environ["DATABASE_URL"]
    url = re.sub(r"^postgresql\+asyncpg", "postgresql", url)
    return url


def q(cur, sql: str, params=()):
    cur.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return [dict(zip(cols, r)) for r in rows]


def main() -> None:
    conn = psycopg2.connect(sync_url())
    cur = conn.cursor()
    report: dict = {"company_id": COMPANY}

    report["leads"] = q(
        cur,
        "SELECT COUNT(*) AS total FROM leads WHERE company_id = %s",
        (COMPANY,),
    )[0]

    report["appointments"] = q(
        cur,
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE audio_url IS NOT NULL AND audio_url <> '') AS with_audio_url,
               COUNT(*) FILTER (WHERE assigned_rep_id IS NOT NULL) AS with_assigned_rep
        FROM appointments WHERE company_id = %s
        """,
        (COMPANY,),
    )[0]

    report["appointments_by_analysis_status"] = q(
        cur,
        """
        SELECT COALESCE(analysis_status::text, 'null') AS analysis_status, COUNT(*) AS cnt
        FROM appointments WHERE company_id = %s
        GROUP BY 1 ORDER BY cnt DESC
        """,
        (COMPANY,),
    )

    report["calls"] = q(
        cur,
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE missed_call = true) AS missed,
               COUNT(*) FILTER (WHERE audio_url IS NOT NULL AND audio_url <> '') AS with_audio
        FROM calls WHERE company_id = %s
        """,
        (COMPANY,),
    )[0]

    report["calls_by_type"] = q(
        cur,
        """
        SELECT COALESCE(call_type::text, 'null') AS call_type, COUNT(*) AS cnt
        FROM calls WHERE company_id = %s
        GROUP BY 1 ORDER BY cnt DESC LIMIT 10
        """,
        (COMPANY,),
    )

    report["pending_actions"] = q(
        cur,
        """
        SELECT COUNT(*) AS total_pending,
               COUNT(*) FILTER (WHERE due_at IS NOT NULL) AS with_due_at,
               COUNT(*) FILTER (WHERE owner_id IS NOT NULL) AS with_owner,
               COUNT(*) FILTER (WHERE appointment_id IS NOT NULL) AS with_appointment_id
        FROM pending_actions
        WHERE company_id = %s AND status = 'pending'
        """,
        (COMPANY,),
    )[0]

    report["pending_actions_by_type"] = q(
        cur,
        """
        SELECT COALESCE(action_type::text, 'null') AS action_type, COUNT(*) AS cnt
        FROM pending_actions
        WHERE company_id = %s AND status = 'pending'
        GROUP BY 1 ORDER BY cnt DESC LIMIT 15
        """,
        (COMPANY,),
    )

    report["recordings_on_calls"] = q(
        cur,
        """
        SELECT COUNT(*) AS calls_with_audio,
               COUNT(*) FILTER (WHERE transcript IS NOT NULL AND transcript <> '') AS with_transcript
        FROM calls WHERE company_id = %s AND audio_url IS NOT NULL AND audio_url <> ''
        """,
        (COMPANY,),
    )[0]

    report["recordings_on_appointments"] = q(
        cur,
        """
        SELECT COUNT(*) AS appointments_with_audio,
               COUNT(*) FILTER (WHERE recording_status IS NOT NULL) AS with_recording_status,
               COUNT(*) FILTER (WHERE analysis_status IS NOT NULL) AS with_analysis_status
        FROM appointments WHERE company_id = %s
        """,
        (COMPANY,),
    )[0]

    report["appointment_recording_status"] = q(
        cur,
        """
        SELECT COALESCE(recording_status, 'null') AS recording_status, COUNT(*) AS cnt
        FROM appointments WHERE company_id = %s
        GROUP BY 1 ORDER BY cnt DESC
        """,
        (COMPANY,),
    )

    report["call_processing_jobs"] = q(
        cur,
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE status = 'completed') AS completed,
               COUNT(*) FILTER (WHERE status = 'failed') AS failed,
               COUNT(*) FILTER (WHERE status IN ('queued','running')) AS in_progress
        FROM call_processing_jobs WHERE company_id = %s
        """,
        (COMPANY,),
    )[0]

    report["call_analyses"] = q(
        cur,
        """
        SELECT COUNT(*) AS total,
               COUNT(*) FILTER (WHERE property_details IS NOT NULL AND property_details::text NOT IN ('null','{}','')) AS with_property_details,
               COUNT(*) FILTER (WHERE service_requested IS NOT NULL AND service_requested <> '') AS with_service_requested,
               COUNT(*) FILTER (WHERE summary IS NOT NULL AND summary <> '') AS with_summary,
               COUNT(*) FILTER (WHERE ca.status = 'completed') AS completed
        FROM call_analyses ca
        JOIN calls c ON c.id = ca.call_id
        WHERE c.company_id = %s
        """,
        (COMPANY,),
    )[0]

    report["call_analyses_by_status"] = q(
        cur,
        """
        SELECT COALESCE(ca.status, 'null') AS status, COUNT(*) AS cnt
        FROM call_analyses ca
        JOIN calls c ON c.id = ca.call_id
        WHERE c.company_id = %s
        GROUP BY 1 ORDER BY cnt DESC
        """,
        (COMPANY,),
    )

    report["leads_by_status"] = q(
        cur,
        """
        SELECT COALESCE(status::text, 'null') AS status, COUNT(*) AS cnt
        FROM leads WHERE company_id = %s
        GROUP BY 1 ORDER BY cnt DESC LIMIT 10
        """,
        (COMPANY,),
    )

    report["missed_calls_without_callback_task"] = q(
        cur,
        """
        SELECT COUNT(*) AS cnt FROM calls c
        WHERE c.company_id = %s AND c.missed_call = true
          AND NOT EXISTS (
            SELECT 1 FROM pending_actions pa
            WHERE pa.call_id = c.id AND pa.action_type = 'call_back' AND pa.status = 'pending'
          )
        """,
        (COMPANY,),
    )[0]

    report["appointments_without_follow_up_task"] = q(
        cur,
        """
        SELECT COUNT(*) AS cnt FROM appointments a
        WHERE a.company_id = %s
          AND NOT EXISTS (
            SELECT 1 FROM pending_actions pa
            WHERE pa.appointment_id = a.id AND pa.action_type = 'follow_up' AND pa.status = 'pending'
          )
        """,
        (COMPANY,),
    )[0]

    report["pending_last_30d"] = q(
        cur,
        "SELECT COUNT(*) AS total FROM pending_actions WHERE company_id=%s AND status='pending' AND created_at >= NOW()-INTERVAL '30 days'",
        (COMPANY,),
    )[0]

    report["call_back_by_source"] = q(
        cur,
        """
        SELECT COALESCE(source, 'null') AS source, COUNT(*) AS cnt
        FROM pending_actions WHERE company_id=%s AND action_type='call_back'
        GROUP BY 1 ORDER BY cnt DESC
        """,
        (COMPANY,),
    )

    report["qualified_unbooked_leads"] = q(
        cur,
        "SELECT COUNT(*) AS total FROM leads WHERE company_id=%s AND status='qualified_unbooked'",
        (COMPANY,),
    )[0]

    report["smart_nudges"] = q(
        cur,
        "SELECT COUNT(*) AS total FROM smart_nudges WHERE company_id=%s",
        (COMPANY,),
    )[0]

    cur.close()
    conn.close()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
