"""
Phase 3: Sales rep appointments, linked calls/analyses, today's appointments, pending leads.
"""
import uuid, random, json, os
from datetime import datetime, timedelta, timezone, date

import psycopg2, psycopg2.extras

DB_URL = "postgresql://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"

random.seed(77)

STATE    = json.load(open(os.path.join(os.path.dirname(__file__), "apex_seed_state.json")))
COMPANY_ID = STATE["company_id"]
USER_IDS   = STATE["user_ids"]
CONTACTS   = STATE["contact_cards"]

NOW  = datetime.now(timezone.utc)
TODAY = NOW.date()

# ── Sales rep config ─────────────────────────────────────────────────────────
# Each dict defines targets for the rep.
# total_appts, win_count, no_show_count, target_hours (total rec hours),
# avg_deal (for closed_won leads), process_score_avg (sop_compliance 0-1)
SALES_REPS = [
    {
        "email": "tyler.anderson@apexroofing.com",
        "total_appts": 70,  "win_count": 23,  "no_show_count": 7,
        "target_hours": 50, "avg_deal": 18000,"process_avg": 0.72,
    },
    {
        "email": "brandon.wilson@apexroofing.com",
        "total_appts": 80,  "win_count": 40,  "no_show_count": 4,
        "target_hours": 75, "avg_deal": 22000,"process_avg": 0.80,
    },
    {
        "email": "dylan.thompson@apexroofing.com",
        "total_appts": 40,  "win_count": 10,  "no_show_count": 10,
        "target_hours": 30, "avg_deal": 14000,"process_avg": 0.65,
    },
    {
        "email": "austin.martinez@apexroofing.com",
        "total_appts": 100, "win_count": 40,  "no_show_count": 15,
        "target_hours": 80, "avg_deal": 20000,"process_avg": 0.75,
    },
    {
        "email": "chase.robinson@apexroofing.com",
        "total_appts": 30,  "win_count": 9,   "no_show_count": 8,
        "target_hours": 20, "avg_deal": 16000,"process_avg": 0.70,
    },
]
# Team totals: 320 appts, 122 won, 38.1% win rate; 255 hrs total, 47.8 min avg

SOP_STAGES_SALES = [
    "Introduction & Rapport Building",
    "Needs Assessment",
    "Property Inspection",
    "Solution Presentation",
    "Objection Handling",
    "Closing",
    "Follow-Up Scheduling",
]

PHOENIX_ADDRESSES = [
    ("4521 E Camelback Rd", "Phoenix", "AZ", "85018", 33.5095, -112.0130),
    ("7890 W Bell Rd",       "Peoria",  "AZ", "85382", 33.6423, -112.2304),
    ("1234 N Scottsdale Rd", "Scottsdale","AZ","85254",33.5910,-111.9200),
    ("5678 S Gilbert Rd",    "Gilbert", "AZ", "85296", 33.3528, -111.7893),
    ("9012 W Chandler Blvd", "Chandler","AZ", "85226", 33.3062, -111.9844),
    ("3456 E McDowell Rd",   "Phoenix", "AZ", "85008", 33.4809, -112.0130),
    ("6789 N Hayden Rd",     "Scottsdale","AZ","85250",33.5910,-111.8560),
    ("2345 W Baseline Rd",   "Tempe",   "AZ", "85283", 33.3742, -111.9850),
    ("8901 E Ray Rd",        "Mesa",    "AZ", "85212", 33.3309, -111.7200),
    ("4321 N 75th Ave",      "Phoenix", "AZ", "85033", 33.4834, -112.2220),
    ("5432 W Peoria Ave",    "Glendale","AZ", "85302", 33.5800, -112.1930),
    ("6543 S Alma School Rd","Chandler","AZ", "85248", 33.2830, -111.8490),
    ("7654 W Happy Valley Rd","Peoria", "AZ", "85383", 33.7140, -112.2610),
    ("8765 E Shea Blvd",     "Scottsdale","AZ","85260",33.5880,-111.8950),
    ("9876 W Indian School Rd","Phoenix","AZ","85037",33.4976,-112.2440),
    ("1357 N Power Rd",      "Mesa",    "AZ", "85207", 33.4350, -111.6990),
    ("2468 S Rural Rd",      "Tempe",   "AZ", "85282", 33.3900, -111.9260),
    ("3579 W Thunderbird Rd","Phoenix", "AZ", "85053", 33.6140, -112.1840),
    ("4680 E Broadway Blvd", "Tucson",  "AZ", "85711", 32.2228, -110.9072),
    ("5791 N Oracle Rd",     "Tucson",  "AZ", "85704", 32.3038, -110.9832),
]

SERVICES = [
    "Full roof replacement", "Tile roof replacement", "Shingle replacement",
    "Metal roofing installation", "Flat roof replacement", "Storm damage repair",
    "Roof deck repair", "Emergency roof replacement",
]

OBJECTION_CATS_SALES = [
    (5,  "Service Fee Concerns",    ["Too expensive", "Competitors are cheaper", "Can't fit in budget"]),
    (3,  "Customer Needs Time to Decide", ["Need to think about it", "Want to get more quotes"]),
    (4,  "Scheduling Conflicts",    ["Can't schedule right now", "Too busy this month"]),
    (9,  "Other",                   ["HOA restrictions", "Want second opinion"]),
    (1,  "Immediate Service Unavailability", ["Too long of a wait", "Need it done sooner"]),
]


def rand_past_dt(days_ago_min, days_ago_max, hour_min=8, hour_max=17):
    days = random.randint(days_ago_min, days_ago_max)
    h    = random.randint(hour_min, hour_max)
    m    = random.randint(0, 59)
    base = NOW.replace(hour=h, minute=m, second=0, microsecond=0)
    return base - timedelta(days=days)


def make_sop_stages(score):
    n = max(0, min(len(SOP_STAGES_SALES), round(score * len(SOP_STAGES_SALES))))
    sl = SOP_STAGES_SALES[:]
    random.shuffle(sl)
    return sl[:n], sl[n:]


def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor()
    psycopg2.extras.register_uuid()

    contacts_pool = CONTACTS[100:]   # use second half for sales reps
    contact_idx = 0

    for rep in SALES_REPS:
        email       = rep["email"]
        rep_id      = USER_IDS[email]
        total_appts = rep["total_appts"]
        win_count   = rep["win_count"]
        no_show_cnt = rep["no_show_count"]
        lost_count  = total_appts - win_count - no_show_cnt
        target_sec  = rep["target_hours"] * 3600
        avg_dur_sec = target_sec // total_appts
        avg_deal    = rep["avg_deal"]
        proc_avg    = rep["process_avg"]

        print(f"Sales rep {email}: {total_appts} appts, {win_count} won, {no_show_cnt} no-show, {rep['target_hours']}hrs")

        # Outcome pool (shuffled)
        outcomes = (["won"] * win_count +
                    ["no_show"] * no_show_cnt +
                    ["lost"] * lost_count)
        random.shuffle(outcomes)

        # 70% fresh_sales, 30% follow_up_inquiry
        call_types = (["fresh_sales"] * round(total_appts * 0.70) +
                      ["follow_up_inquiry"] * (total_appts - round(total_appts * 0.70)))
        random.shuffle(call_types)

        won_deal_sizes = [round(random.gauss(avg_deal, avg_deal * 0.15), -2) for _ in range(win_count)]
        won_deal_sizes = [max(11000, min(32000, d)) for d in won_deal_sizes]
        won_idx = 0

        for i in range(total_appts):
            c = contacts_pool[contact_idx % len(contacts_pool)]
            contact_idx += 1
            outcome    = outcomes[i]
            call_type  = call_types[i]
            dur_var    = int(avg_dur_sec * random.uniform(0.7, 1.3))
            addr_info  = random.choice(PHOENIX_ADDRESSES)
            appt_dt    = rand_past_dt(1, 43, hour_min=8, hour_max=17)
            appt_end   = appt_dt + timedelta(seconds=dur_var)
            compliance = round(random.gauss(proc_avg, 0.06), 2)
            compliance = max(0.55, min(0.95, compliance))
            sentiment  = round(random.uniform(0.55, 0.90), 2)
            followed, missed = make_sop_stages(compliance)
            service    = random.choice(SERVICES)
            is_won     = (outcome == "won")

            # Deal size for won leads
            deal_size = None
            if is_won and won_idx < len(won_deal_sizes):
                deal_size = won_deal_sizes[won_idx]
                won_idx += 1

            # Create contact card / lead
            lead_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO leads
                  (id, company_id, contact_card_id, status, deal_status,
                   assigned_rep_id, deal_size, extra_metadata, created_at, closed_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                lead_id, COMPANY_ID, c["id"],
                "closed_won" if is_won else ("closed_lost" if outcome == "lost" else "qualified_unbooked"),
                "won" if is_won else ("lost" if outcome == "lost" else "new"),
                rep_id,
                deal_size,
                psycopg2.extras.Json({"source": "sales_rep_appointment"}),
                appt_dt - timedelta(days=random.randint(1,5)),
                appt_dt + timedelta(days=random.randint(0,2)) if is_won else None
            ))

            # Create the "sales meeting" call record
            call_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO calls
                  (id, company_id, contact_card_id, lead_id, phone_number,
                   missed_call, duration_seconds, handled_by_user_id,
                   status, extra_metadata, created_at, answered_at, interaction_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                call_id, COMPANY_ID, c["id"], lead_id, c["phone"],
                False, dur_var, rep_id,
                "completed",
                psycopg2.extras.Json({
                    "type": "sales_meeting",
                    "agent": {"id": rep_id, "name": email.split("@")[0].replace(".", " ").title()},
                }),
                appt_dt, appt_dt + timedelta(seconds=5), "outbound"
            ))

            # Call analysis for process/skills scores
            analysis_id = str(uuid.uuid4())
            bant_n = round(random.uniform(0.6, 0.95), 2) if is_won else round(random.uniform(0.3,0.75),2)
            bant_b = round(random.uniform(0.6, 0.95), 2) if is_won else round(random.uniform(0.2,0.70),2)
            bant_t = round(random.uniform(0.6, 0.95), 2) if is_won else round(random.uniform(0.2,0.70),2)
            bant_a = round(random.uniform(0.7, 0.98), 2) if is_won else round(random.uniform(0.3,0.75),2)
            cur.execute("""
                INSERT INTO call_analyses
                  (id, call_id, company_id, status,
                   qualification_status, booking_status, call_outcome_category,
                   objections, objection_texts, objections_total_count,
                   sop_stages_completed, sop_stages_missed, sop_stages_total,
                   sop_compliance_score, sop_compliance_rate, sop_compliance_confidence,
                   sop_compliance_issues, sop_compliance_positive_behaviors,
                   sentiment_score, summary_confidence_score,
                   bant_need_score, bant_budget_score, bant_timeline_score, bant_authority_score,
                   qualification_overall_score, qualification_confidence_score,
                   appointment_confirmed, appointment_date,
                   service_requested, compliance_target_role,
                   detected_call_type, is_existing_customer,
                   follow_up_required,
                   summary, key_points, action_items, created_at)
                VALUES
                  (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                analysis_id, call_id, COMPANY_ID, "completed",
                "hot" if is_won else "warm", "booked" if is_won else "not_booked",
                "qualified_and_booked" if is_won else "qualified_but_unbooked",
                [], [], 0,
                followed, missed, len(SOP_STAGES_SALES),
                compliance, compliance, round(random.uniform(0.78,0.94),2),
                [] if random.random() > 0.4 else [f"Could improve {random.choice(missed)} stage" if missed else "Follow-up timing"],
                [] if random.random() > 0.5 else [f"Strong {random.choice(followed)} execution" if followed else "Good rapport"],
                sentiment, round(random.uniform(0.80,0.95),2),
                bant_n, bant_b, bant_t, bant_a,
                round((bant_n+bant_b+bant_t+bant_a)/4, 2), round(random.uniform(0.78,0.94),2),
                is_won, appt_dt if is_won else None,
                service, "sales_rep", call_type, False,
                call_type in ["follow_up_inquiry"] and not is_won,
                f"Sales rep met with {c['name']} regarding {service.lower()}. {'Deal closed.' if is_won else 'Follow-up needed.' if outcome=='lost' else 'No show.'}",
                [f"{service} discussion", c['address'].split(',')[1].strip() if ',' in c.get('address','') else 'Phoenix'],
                ["Close the deal" if not is_won else "Schedule installation"],
                appt_dt + timedelta(seconds=dur_var)
            ))

            # Add 60% pricing objections for sales rep calls on ~40% of calls
            if random.random() < 0.40:
                n_obj = random.randint(1, 2)
                for _ in range(n_obj):
                    cat_id, cat_text, obj_list = random.choices(
                        OBJECTION_CATS_SALES,
                        weights=[0.60, 0.15, 0.10, 0.10, 0.05]
                    )[0]
                    cur.execute("""
                        INSERT INTO call_objection_details
                          (id, call_analysis_id, call_id, company_id, user_id,
                           category_id, category_text, objection_text, overcome,
                           severity, confidence_score, created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        str(uuid.uuid4()), analysis_id, call_id, COMPANY_ID, rep_id,
                        cat_id, cat_text, random.choice(obj_list),
                        is_won,
                        random.choice(["medium","medium","high","low"]),
                        round(random.uniform(0.75,0.95),2),
                        appt_dt + timedelta(seconds=dur_var)
                    ))

            # Create the appointment record
            appt_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO appointments
                  (id, company_id, lead_id, contact_card_id,
                   scheduled_start, scheduled_end, location_address,
                   latitude, longitude,
                   outcome, assigned_rep_id, handled_by_user_id,
                   duration_seconds, interaction_id,
                   sop_compliance_score, sop_compliance_rate,
                   sop_stages_completed, sop_stages_missed, sop_stages_total,
                   qualification_status, booking_status,
                   sentiment_score, detected_call_type,
                   service_requested, compliance_target_role,
                   extra_metadata, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                appt_id, COMPANY_ID, lead_id, c["id"],
                appt_dt, appt_end,
                f"{addr_info[0]}, {addr_info[1]}, {addr_info[2]} {addr_info[3]}",
                addr_info[4], addr_info[5],
                outcome, rep_id, rep_id,
                dur_var, call_id,
                compliance, compliance,
                followed, missed, len(SOP_STAGES_SALES),
                "hot" if is_won else "warm",
                "booked" if is_won else "not_booked",
                sentiment, call_type,
                service, "sales_rep",
                psycopg2.extras.Json({"source": "sales_meeting", "call_type": call_type}),
                appt_dt
            ))

        conn.commit()
        print(f"  Committed {total_appts} appts for {email}")

    # ── Today's appointments (Mar 4, 2026) ─────────────────────────────────
    print("Creating today's appointments...")
    today_times = [9, 10, 11, 13, 15, 16]   # hours
    rep_emails_today = [
        "tyler.anderson@apexroofing.com",
        "brandon.wilson@apexroofing.com",
        "dylan.thompson@apexroofing.com",
        "austin.martinez@apexroofing.com",
        "chase.robinson@apexroofing.com",
    ]
    today_addr = PHOENIX_ADDRESSES[:5]

    for idx, rep_email in enumerate(rep_emails_today):
        rep_id  = USER_IDS[rep_email]
        c       = contacts_pool[(contact_idx + idx) % len(contacts_pool)]
        h       = today_times[idx % len(today_times)]
        appt_dt = NOW.replace(hour=h, minute=0, second=0, microsecond=0)
        appt_end = appt_dt + timedelta(hours=1, minutes=random.randint(0,30))
        dur_sec  = int((appt_end - appt_dt).total_seconds())
        addr_info = today_addr[idx]
        service   = random.choice(SERVICES)

        lead_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO leads
              (id, company_id, contact_card_id, status, deal_status,
               assigned_rep_id, deal_size, extra_metadata, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            lead_id, COMPANY_ID, c["id"],
            "qualified_unbooked", "new",
            rep_id, None,
            psycopg2.extras.Json({"source": "today_appointment"}),
            NOW - timedelta(days=random.randint(1,5))
        ))

        call_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO calls
              (id, company_id, contact_card_id, lead_id, phone_number,
               missed_call, duration_seconds, handled_by_user_id,
               status, extra_metadata, created_at, interaction_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            call_id, COMPANY_ID, c["id"], lead_id, c["phone"],
            False, dur_sec, rep_id, "pending",
            psycopg2.extras.Json({"type": "today_appointment"}),
            appt_dt, "outbound"
        ))

        appt_id = str(uuid.uuid4())
        cur.execute("""
            INSERT INTO appointments
              (id, company_id, lead_id, contact_card_id,
               scheduled_start, scheduled_end, location_address,
               latitude, longitude,
               outcome, assigned_rep_id, handled_by_user_id,
               duration_seconds, interaction_id,
               service_requested, extra_metadata, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            appt_id, COMPANY_ID, lead_id, c["id"],
            appt_dt, appt_end,
            f"{addr_info[0]}, {addr_info[1]}, {addr_info[2]} {addr_info[3]}",
            addr_info[4], addr_info[5],
            None, rep_id, rep_id,
            dur_sec, call_id,
            service,
            psycopg2.extras.Json({"source": "today_schedule", "type": "in-person"}),
            NOW - timedelta(days=1)
        ))
        print(f"  Today: {rep_email} @ {h}:00 -> {addr_info[0]}, {addr_info[1]}, AZ")

    conn.commit()

    # ── Pending leads (2-5 per sales rep) ─────────────────────────────────
    print("Creating pending leads per sales rep...")
    pending_services = [
        "Full roof replacement estimate", "Tile roof repair", "Shingle replacement",
        "Storm damage assessment", "Metal roofing quote", "Emergency repair follow-up",
    ]
    for rep in SALES_REPS:
        rep_id = USER_IDS[rep["email"]]
        n_pending = random.randint(2, 5)
        for j in range(n_pending):
            c = contacts_pool[(contact_idx) % len(contacts_pool)]
            contact_idx += 1
            service = random.choice(pending_services)
            deal_est = round(random.uniform(11000, 26000), -2)
            lead_id  = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO leads
                  (id, company_id, contact_card_id, status, deal_status,
                   assigned_rep_id, deal_size, pipeline_stage, extra_metadata, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                lead_id, COMPANY_ID, c["id"],
                "qualified_unbooked", "nurturing",
                rep_id, deal_est,
                random.choice(["proposal_sent","follow_up","negotiation","demo_scheduled"]),
                psycopg2.extras.Json({
                    "service_requested": service,
                    "notes": f"Pending {service.lower()} — requires follow-up",
                    "urgency": random.choice(["high","medium","low"]),
                    "last_contact": (NOW - timedelta(days=random.randint(1,10))).isoformat(),
                }),
                NOW - timedelta(days=random.randint(3,14))
            ))

    conn.commit()
    print("Phase 3 complete. Sales rep data created.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
