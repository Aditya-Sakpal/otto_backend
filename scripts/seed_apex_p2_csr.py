"""
Phase 2: CSR calls, call_analyses, leads, call_objection_details, CSR appointments.
"""
import uuid, random, json, os
from datetime import datetime, timedelta, timezone

import psycopg2, psycopg2.extras

DB_URL = "postgresql://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n"

random.seed(99)

STATE = json.load(open(os.path.join(os.path.dirname(__file__), "apex_seed_state.json")))
COMPANY_ID = STATE["company_id"]
USER_IDS   = STATE["user_ids"]
CONTACTS   = STATE["contact_cards"]

NOW = datetime.now(timezone.utc)

# CSR user IDs in order
CSR_EMAILS = [
    "sarah.mitchell@apexroofing.com",
    "jennifer.brooks@apexroofing.com",
    "ashley.carter@apexroofing.com",
    "nicole.davis@apexroofing.com",
    "rachel.evans@apexroofing.com",
]
CSR_IDS = [USER_IDS[e] for e in CSR_EMAILS]

# CTM-style agent IDs for CSRs (stored in calls.extra_metadata.agent)
CTM_IDS = {
    "sarah.mitchell@apexroofing.com":   "USRAPEX001SARAH0000000000000001",
    "jennifer.brooks@apexroofing.com":  "USRAPEX002JENNIFER000000000002",
    "ashley.carter@apexroofing.com":    "USRAPEX003ASHLEY00000000000003",
    "nicole.davis@apexroofing.com":     "USRAPEX004NICOLE00000000000004",
    "rachel.evans@apexroofing.com":     "USRAPEX005RACHEL00000000000005",
}
CSR_NAMES = {
    "sarah.mitchell@apexroofing.com":  "Sarah Mitchell",
    "jennifer.brooks@apexroofing.com": "Jennifer Brooks",
    "ashley.carter@apexroofing.com":   "Ashley Carter",
    "nicole.davis@apexroofing.com":    "Nicole Davis",
    "rachel.evans@apexroofing.com":    "Rachel Evans",
}

# Objection categories from schema
OBJECTION_CATS = [
    (5,  "Service Fee Concerns"),       # 60% of objections = pricing
    (4,  "Scheduling Conflicts"),
    (3,  "Customer Needs Time to Decide"),
    (1,  "Immediate Service Unavailability"),
    (9,  "Other"),
    (7,  "Inefficient Agent Communication"),
    (10, "Service Not Catered"),
]

OBJECTION_TEXTS = {
    5:  ["That seems really expensive", "Is there a discount available?",
         "I can't afford that right now", "Other companies are cheaper",
         "The price is too high for my budget", "Can we get a better rate?"],
    4:  ["I can't be available this week", "We're out of town until next month",
         "That time doesn't work for me", "I need to check with my spouse"],
    3:  ["Let me think about it", "I need more time to decide",
         "I want to get a few more quotes first", "Not sure yet"],
    1:  ["Are you available this week?", "I need someone ASAP",
         "How long is your wait time?"],
    9:  ["I have some concerns", "I'm not sure about this",
         "I need to talk to my HOA"],
    7:  ["I couldn't understand what you said", "Can you explain that again?"],
    10: ["You don't do flat roofs?", "We have a metal roof"],
}

SOP_STAGES_ALL = [
    "Greeting & Introduction",
    "Needs Assessment",
    "Property Details Collection",
    "Appointment Scheduling",
    "Confirmation & Next Steps",
    "Objection Handling",
    "Budget Discussion",
]

SERVICES = [
    "Roof repair", "Full roof replacement", "Shingle replacement",
    "Tile roof repair", "Flat roof repair", "Emergency roof repair",
    "Roof inspection", "Storm damage repair",
]

AZ_ADDRESSES = [
    "4521 E Camelback Rd, Phoenix, AZ 85018",
    "7890 W Bell Rd, Peoria, AZ 85382",
    "1234 N Scottsdale Rd, Scottsdale, AZ 85254",
    "5678 S Gilbert Rd, Gilbert, AZ 85296",
    "9012 W Chandler Blvd, Chandler, AZ 85226",
    "3456 E McDowell Rd, Phoenix, AZ 85008",
    "6789 N Hayden Rd, Scottsdale, AZ 85250",
    "2345 W Baseline Rd, Tempe, AZ 85283",
    "8901 E Ray Rd, Mesa, AZ 85212",
    "4321 N 75th Ave, Phoenix, AZ 85033",
    "5432 W Peoria Ave, Glendale, AZ 85302",
    "6543 S Alma School Rd, Chandler, AZ 85248",
]

def rand_past_dt(days_ago_min, days_ago_max, hour_min=8, hour_max=18):
    days = random.randint(days_ago_min, days_ago_max)
    h = random.randint(hour_min, hour_max)
    m = random.randint(0, 59)
    return NOW - timedelta(days=days, hours=NOW.hour - h, minutes=NOW.minute - m)

def make_call_metadata(csr_email, csr_name, phone, ctm_id, missed):
    return {
        "direction": "inbound",
        "status": "no answer" if missed else "answered",
        "call_status": "no answer" if missed else "answered",
        "tracking_number": "+14805559100",
        "tracking_label": "Apex Roofing Main Line",
        "source": "Apex Roofing Main Line",
        "duration": random.randint(30, 60) if missed else random.randint(120, 600),
        "talk_time": 0 if missed else random.randint(90, 480),
        "agent": None if missed else {
            "id": ctm_id,
            "name": csr_name,
            "email": csr_email,
            "pic_url": f"/api/v1/accounts/999999/users/{ctm_id}/pic_url",
        },
    }

def make_sop_stages(compliance_score):
    n_total = 7
    n_followed = round(compliance_score * n_total)
    n_followed = max(0, min(n_total, n_followed))
    shuffled = SOP_STAGES_ALL[:]
    random.shuffle(shuffled)
    followed = shuffled[:n_followed]
    missed = shuffled[n_followed:]
    return followed, missed

def main():
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur  = conn.cursor()
    psycopg2.extras.register_uuid()

    contacts_pool = CONTACTS[:]
    random.shuffle(contacts_pool)

    # ── Plan per CSR ──────────────────────────────────────────────────────────
    # qualified per csr: 26,25,24,24,21 = 120
    # booked per csr:    17,18,17,17,17 = 86
    # "recent" (last 7d) handled: 6,6,5,6,5 = 28; booked: 5,5,4,5,4 = 23
    csr_plan = [
        {"email": "sarah.mitchell@apexroofing.com",   "hist_handled": 46, "hist_qualified": 20, "hist_booked": 12,  "rec_handled": 6, "rec_booked": 5},
        {"email": "jennifer.brooks@apexroofing.com",  "hist_handled": 44, "hist_qualified": 19, "hist_booked": 13,  "rec_handled": 6, "rec_booked": 5},
        {"email": "ashley.carter@apexroofing.com",    "hist_handled": 40, "hist_qualified": 19, "hist_booked": 13,  "rec_handled": 5, "rec_booked": 4},
        {"email": "nicole.davis@apexroofing.com",     "hist_handled": 42, "hist_qualified": 20, "hist_booked": 12,  "rec_handled": 6, "rec_booked": 5},
        {"email": "rachel.evans@apexroofing.com",     "hist_handled": 35, "hist_qualified": 16, "hist_booked": 11,  "rec_handled": 5, "rec_booked": 4},
    ]
    # Total historical: 207 handled, 94 qualified, 61 booked
    # Total recent:      28 handled, 23 booked
    # Overall: 235 answered, 120 qualified (51%), 84 booked (72% of qual)
    # Leads from answered calls: ~150 (some calls not qualifying)

    all_leads = []
    contact_idx = 0

    for plan in csr_plan:
        email    = plan["email"]
        csr_id   = USER_IDS[email]
        ctm_id   = CTM_IDS[email]
        csr_name = CSR_NAMES[email]
        hist_h   = plan["hist_handled"]
        hist_q   = plan["hist_qualified"]
        hist_b   = plan["hist_booked"]
        rec_h    = plan["rec_handled"]
        rec_b    = plan["rec_booked"]

        print(f"CSR {csr_name}: hist={hist_h} handled/{hist_q} qual/{hist_b} booked | recent={rec_h} handled/{rec_b} booked")

        # ── Missed calls (mix of recent and historical) ────────────────────
        # Total missed per CSR: ~7 (5 CSRs * 7 ≈ 35 ≈ 34)
        for i in range(7):
            c = contacts_pool[contact_idx % len(contacts_pool)]
            contact_idx += 1
            is_recent = (i < 2)   # ~2 recent missed per CSR
            call_dt = rand_past_dt(0, 6) if is_recent else rand_past_dt(7, 42)
            call_id = str(uuid.uuid4())
            cur.execute("""
                INSERT INTO calls
                  (id, company_id, contact_card_id, phone_number, missed_call,
                   duration_seconds, status, extra_metadata, created_at, answered_at,
                   interaction_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                call_id, COMPANY_ID, c["id"], c["phone"], True,
                random.randint(20, 60), "pending",
                psycopg2.extras.Json(make_call_metadata(email, csr_name, c["phone"], ctm_id, True)),
                call_dt, None, "inbound"
            ))

        # ── Historical answered calls ──────────────────────────────────────
        qualified_sofar = 0
        booked_sofar    = 0
        for i in range(hist_h):
            c = contacts_pool[contact_idx % len(contacts_pool)]
            contact_idx += 1
            call_dt  = rand_past_dt(7, 42)
            call_id  = str(uuid.uuid4())
            dur      = random.randint(120, 600)
            service  = random.choice(SERVICES)

            # Determine qualification and booking status
            is_qualified = qualified_sofar < hist_q
            if is_qualified:
                is_booked = booked_sofar < hist_b
            else:
                is_booked = False

            qual_status = random.choice(["hot","warm"]) if is_qualified else random.choice(["cold","unqualified"])
            book_status = "booked" if is_booked else ("not_booked" if is_qualified else "not_booked")
            outcome_cat = "qualified_and_booked" if is_booked else ("qualified_but_unbooked" if is_qualified else "unqualified")
            compliance  = round(random.uniform(0.65, 0.85), 2)
            sentiment   = round(random.uniform(0.6, 0.9), 2)
            bant_need   = round(random.uniform(0.6, 0.95), 2) if is_qualified else round(random.uniform(0.1, 0.4), 2)
            bant_budget = round(random.uniform(0.5, 0.90), 2) if is_qualified else round(random.uniform(0.1, 0.4), 2)
            bant_time   = round(random.uniform(0.5, 0.90), 2) if is_qualified else round(random.uniform(0.1, 0.4), 2)
            bant_auth   = round(random.uniform(0.7, 0.95), 2) if is_qualified else round(random.uniform(0.2, 0.5), 2)
            overall_q   = round((bant_need+bant_budget+bant_time+bant_auth)/4, 2)
            appt_dt     = call_dt + timedelta(days=random.randint(2, 10)) if is_booked else None
            addr        = random.choice(AZ_ADDRESSES) if is_booked else None
            followed, missed_stages = make_sop_stages(compliance)

            cur.execute("""
                INSERT INTO calls
                  (id, company_id, contact_card_id, phone_number, missed_call,
                   duration_seconds, handled_by_user_id, status, extra_metadata,
                   created_at, answered_at, interaction_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                call_id, COMPANY_ID, c["id"], c["phone"], False,
                dur, csr_id, "completed",
                psycopg2.extras.Json(make_call_metadata(email, csr_name, c["phone"], ctm_id, False)),
                call_dt, call_dt + timedelta(seconds=5), "inbound"
            ))

            # Lead
            lead_id = str(uuid.uuid4())
            lead_status_map = {
                "qualified_and_booked": "qualified_booked",
                "qualified_but_unbooked": "qualified_unbooked",
                "unqualified": "abandoned",
            }
            deal_s = round(random.uniform(11000, 26000), -2) if is_booked else None
            cur.execute("""
                INSERT INTO leads
                  (id, company_id, contact_card_id, status, deal_status,
                   assigned_rep_id, deal_size, extra_metadata, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                lead_id, COMPANY_ID, c["id"],
                lead_status_map[outcome_cat],
                "booked" if is_booked else "nurturing",
                None, deal_s,
                psycopg2.extras.Json({"created_from_call": call_id}),
                call_dt + timedelta(seconds=10)
            ))
            # Update call with lead_id
            cur.execute("UPDATE calls SET lead_id=%s WHERE id=%s", (lead_id, call_id))

            # Call analysis
            analysis_id = str(uuid.uuid4())
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
                   summary, key_points, action_items, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                analysis_id, call_id, COMPANY_ID, "completed",
                qual_status, book_status, outcome_cat,
                [], [], 0,
                followed, missed_stages, len(SOP_STAGES_ALL),
                compliance, compliance, round(random.uniform(0.75, 0.92), 2),
                [], [],
                sentiment, round(random.uniform(0.80, 0.95), 2),
                bant_need, bant_budget, bant_time, bant_auth,
                overall_q, round(random.uniform(0.75, 0.92), 2),
                is_booked, appt_dt,
                service, "customer_rep",
                "new_inquiry", False,
                f"Customer called about {service.lower()}. {'Appointment booked.' if is_booked else 'Follow-up required.'}",
                [f"{service} inquiry", "Phoenix area", f"Budget: {'available' if is_qualified else 'unclear'}"],
                ["Send estimate" if is_booked else "Follow up with customer"],
                call_dt + timedelta(seconds=30)
            ))

            # Objections (on ~35% of answered calls)
            if random.random() < 0.35:
                n_obj = random.randint(1, 2)
                for _ in range(n_obj):
                    # 60% pricing objections
                    if random.random() < 0.60:
                        cat_id, cat_text = 5, "Service Fee Concerns"
                    else:
                        cat_id, cat_text = random.choice(OBJECTION_CATS[1:])
                    obj_text = random.choice(OBJECTION_TEXTS.get(cat_id, ["General concern"]))
                    cur.execute("""
                        INSERT INTO call_objection_details
                          (id, call_analysis_id, call_id, company_id, user_id,
                           category_id, category_text, objection_text, overcome,
                           severity, confidence_score, created_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        str(uuid.uuid4()), analysis_id, call_id, COMPANY_ID, csr_id,
                        cat_id, cat_text, obj_text,
                        random.choice([True, True, False]),
                        random.choice(["low","medium","medium","high"]),
                        round(random.uniform(0.75, 0.95), 2),
                        call_dt + timedelta(seconds=30)
                    ))

            # Appointment (for booked leads)
            if is_booked:
                appt_id = str(uuid.uuid4())
                appt_end = appt_dt + timedelta(hours=1)
                cur.execute("""
                    INSERT INTO appointments
                      (id, company_id, lead_id, contact_card_id,
                       scheduled_start, scheduled_end, location_address,
                       outcome, assigned_rep_id, extra_metadata, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    appt_id, COMPANY_ID, lead_id, c["id"],
                    appt_dt, appt_end, addr,
                    None, None,
                    psycopg2.extras.Json({"created_from_call": call_id, "source": "call_analysis"}),
                    call_dt + timedelta(seconds=30)
                ))
                all_leads.append({"lead_id": lead_id, "contact_card_id": c["id"], "appt_id": appt_id})

            if is_qualified:
                qualified_sofar += 1
            if is_booked:
                booked_sofar += 1

        # ── Recent answered calls (last 7 days) ───────────────────────────
        rec_booked_count = 0
        for i in range(rec_h):
            c = contacts_pool[contact_idx % len(contacts_pool)]
            contact_idx += 1
            call_dt  = rand_past_dt(0, 6)
            call_id  = str(uuid.uuid4())
            dur      = random.randint(180, 500)
            service  = random.choice(SERVICES)
            is_booked = rec_booked_count < rec_b
            is_qualified = is_booked or random.random() < 0.7

            qual_status = random.choice(["hot","warm"]) if is_qualified else "cold"
            book_status = "booked" if is_booked else "not_booked"
            outcome_cat = "qualified_and_booked" if is_booked else ("qualified_but_unbooked" if is_qualified else "unqualified")
            compliance  = round(random.uniform(0.65, 0.85), 2)
            sentiment   = round(random.uniform(0.65, 0.90), 2)
            bant_need   = round(random.uniform(0.65, 0.95), 2) if is_qualified else round(random.uniform(0.1,0.4),2)
            bant_budget = round(random.uniform(0.55, 0.90), 2) if is_qualified else round(random.uniform(0.1,0.4),2)
            bant_time   = round(random.uniform(0.55, 0.90), 2) if is_qualified else round(random.uniform(0.1,0.4),2)
            bant_auth   = round(random.uniform(0.70, 0.95), 2) if is_qualified else round(random.uniform(0.2,0.5),2)
            overall_q   = round((bant_need+bant_budget+bant_time+bant_auth)/4, 2)
            appt_dt     = call_dt + timedelta(days=random.randint(2, 7)) if is_booked else None
            addr        = random.choice(AZ_ADDRESSES) if is_booked else None
            followed, missed_stages = make_sop_stages(compliance)

            cur.execute("""
                INSERT INTO calls
                  (id, company_id, contact_card_id, phone_number, missed_call,
                   duration_seconds, handled_by_user_id, status, extra_metadata,
                   created_at, answered_at, interaction_type)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                call_id, COMPANY_ID, c["id"], c["phone"], False,
                dur, csr_id, "completed",
                psycopg2.extras.Json(make_call_metadata(email, csr_name, c["phone"], ctm_id, False)),
                call_dt, call_dt + timedelta(seconds=5), "inbound"
            ))

            lead_id = str(uuid.uuid4())
            deal_s  = round(random.uniform(11000, 26000), -2) if is_booked else None
            cur.execute("""
                INSERT INTO leads
                  (id, company_id, contact_card_id, status, deal_status,
                   assigned_rep_id, deal_size, extra_metadata, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                lead_id, COMPANY_ID, c["id"],
                "qualified_booked" if is_booked else ("qualified_unbooked" if is_qualified else "abandoned"),
                "booked" if is_booked else "nurturing",
                None, deal_s,
                psycopg2.extras.Json({"created_from_call": call_id}),
                call_dt + timedelta(seconds=10)
            ))
            cur.execute("UPDATE calls SET lead_id=%s WHERE id=%s", (lead_id, call_id))

            analysis_id = str(uuid.uuid4())
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
                   summary, key_points, action_items, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                analysis_id, call_id, COMPANY_ID, "completed",
                qual_status, book_status, outcome_cat,
                [], [], 0,
                followed, missed_stages, len(SOP_STAGES_ALL),
                compliance, compliance, round(random.uniform(0.75,0.92),2),
                [], [],
                sentiment, round(random.uniform(0.80,0.95),2),
                bant_need, bant_budget, bant_time, bant_auth,
                overall_q, round(random.uniform(0.75,0.92),2),
                is_booked, appt_dt,
                service, "customer_rep", "new_inquiry", False,
                f"Customer called about {service.lower()}. {'Appointment booked.' if is_booked else 'Follow-up required.'}",
                [f"{service} inquiry", "Phoenix area"],
                ["Send estimate" if is_booked else "Follow up"],
                call_dt + timedelta(seconds=30)
            ))

            if random.random() < 0.30:
                cat_id = 5 if random.random() < 0.60 else random.choice([4,3,1,9])[0] if random.random() < 0.5 else 4
                cat_text = {5:"Service Fee Concerns",4:"Scheduling Conflicts",3:"Customer Needs Time to Decide",1:"Immediate Service Unavailability",9:"Other"}.get(cat_id,"Other")
                cur.execute("""
                    INSERT INTO call_objection_details
                      (id, call_analysis_id, call_id, company_id, user_id,
                       category_id, category_text, objection_text, overcome, severity, confidence_score, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    str(uuid.uuid4()), analysis_id, call_id, COMPANY_ID, csr_id,
                    cat_id, cat_text, random.choice(OBJECTION_TEXTS.get(cat_id, ["General concern"])),
                    random.choice([True,True,False]), random.choice(["low","medium","high"]),
                    round(random.uniform(0.75,0.95),2), call_dt + timedelta(seconds=30)
                ))

            if is_booked:
                appt_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO appointments
                      (id, company_id, lead_id, contact_card_id,
                       scheduled_start, scheduled_end, location_address,
                       outcome, assigned_rep_id, extra_metadata, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    appt_id, COMPANY_ID, lead_id, c["id"],
                    appt_dt, appt_dt + timedelta(hours=1), addr,
                    None, None,
                    psycopg2.extras.Json({"created_from_call": call_id, "source": "call_analysis"}),
                    call_dt + timedelta(seconds=30)
                ))
                rec_booked_count += 1

        conn.commit()
        print(f"  Committed CSR {csr_name}")

    print(f"Phase 2 complete. CSR data created.")
    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
