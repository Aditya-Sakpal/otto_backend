"""
Seed coaching data for Apex Roofing (d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a).

Populates:
1. coaching_issues - for Issues tab & Smart Nudges
2. coaching_strengths - for Strengths tab
3. coaching_sessions - for Impact tab
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID
import asyncpg

COMPANY_ID = 'd8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a'
EXECUTIVE_ID = '7970e248-d6c6-472b-89f4-ca5f7c6f9940'

# ── Issue templates (roofing CSR / sales context) ────────────────────────────
ISSUE_TEMPLATES = [
    {
        "issue": "Failed to ask qualifying questions about roof age and condition",
        "severity": "high",
        "why_it_matters": "Without understanding roof age and condition, reps cannot accurately assess urgency or recommend appropriate services, leading to mismatched proposals and lost deals.",
        "how_to_fix": "Always ask about roof age, last inspection date, and any visible damage within the first 2 minutes of the call. Use the checklist: age, material, leaks, insurance status.",
        "example_language": "I'd like to understand your roof a bit better. How old is your current roof, and have you noticed any leaks or missing shingles?",
        "related_sop_metric": "Discovery Questions",
    },
    {
        "issue": "Did not confirm appointment details before ending the call",
        "severity": "high",
        "why_it_matters": "Unconfirmed appointments lead to no-shows and wasted technician time. Confirming date, time, and address reduces cancellations by 40%.",
        "how_to_fix": "Before ending any call where an appointment is scheduled, repeat the date, time, address, and what the homeowner should expect. Ask for verbal confirmation.",
        "example_language": "Just to confirm, we have you scheduled for Tuesday at 10 AM at 1234 Main St. Our inspector will arrive in a marked Apex Roofing truck. Does that work for you?",
        "related_sop_metric": "Appointment Confirmation",
    },
    {
        "issue": "Missed opportunity to address price objection with value framing",
        "severity": "high",
        "why_it_matters": "Price is the #1 objection in roofing sales. Without a value-based response, prospects default to choosing the cheapest option, reducing close rates.",
        "how_to_fix": "When price comes up, pivot to value: warranty length, material quality, crew experience, and total cost of ownership. Use the 'cost of waiting' framework.",
        "example_language": "I understand cost is important. What sets us apart is our 25-year warranty and GAF-certified installers. Many homeowners find that investing in quality now saves thousands in repairs later.",
        "related_sop_metric": "Objection Handling",
    },
    {
        "issue": "Rushed through the greeting without building rapport",
        "severity": "medium",
        "why_it_matters": "The first 30 seconds set the tone. Skipping rapport leads to defensive homeowners who are less likely to share their real needs or commit to an appointment.",
        "how_to_fix": "Spend 15-30 seconds on a warm greeting. Use the homeowner's name, reference their neighborhood, or acknowledge the weather. Show genuine interest before diving into business.",
        "example_language": "Hi Mrs. Johnson! Thanks for calling Apex Roofing. How are you doing today? I see you're calling from the Scottsdale area — beautiful neighborhood!",
        "related_sop_metric": "Greeting & Rapport",
    },
    {
        "issue": "Did not explain the inspection process clearly",
        "severity": "medium",
        "why_it_matters": "Homeowners who don't understand what happens during an inspection are more likely to cancel. Clear expectations reduce anxiety and build trust.",
        "how_to_fix": "Walk through the inspection process: who comes, how long it takes, what they'll check, and when the homeowner gets the report. Set expectations for next steps.",
        "example_language": "Our certified inspector will spend about 45 minutes examining your roof, attic, and gutters. They'll take photos and provide a detailed report within 24 hours with any recommendations.",
        "related_sop_metric": "Process Explanation",
    },
    {
        "issue": "Failed to capture homeowner's email for follow-up",
        "severity": "medium",
        "why_it_matters": "Without email, follow-up is limited to phone calls only. Email allows sending proposals, educational content, and automated reminders that improve conversion rates.",
        "how_to_fix": "Ask for email early in the call as part of standard information gathering. Frame it as helpful: 'so we can send you the inspection details and any special offers.'",
        "example_language": "What's the best email to reach you at? We'll send your appointment confirmation and a quick guide on what to expect during the inspection.",
        "related_sop_metric": "Information Gathering",
    },
    {
        "issue": "Did not mention warranty or guarantee during the sales pitch",
        "severity": "medium",
        "why_it_matters": "Warranties are a key differentiator in roofing. Homeowners are 60% more likely to choose a contractor who proactively mentions warranty coverage.",
        "how_to_fix": "Mention the warranty within the first 5 minutes of discussing services. Differentiate between workmanship warranty and manufacturer warranty.",
        "example_language": "All our installations come with a 10-year workmanship warranty on top of the manufacturer's 25-year material warranty. That means you're covered from every angle.",
        "related_sop_metric": "Value Proposition",
    },
    {
        "issue": "Talked over the customer during objection handling",
        "severity": "high",
        "why_it_matters": "Interrupting customers during objections makes them feel unheard and escalates resistance. Active listening reduces objection persistence by 35%.",
        "how_to_fix": "Let the customer finish their objection completely. Pause for 2 seconds. Acknowledge their concern before responding. Use 'I understand' or 'That's a great point.'",
        "example_language": "[Pause] I completely understand your concern about the cost. That's actually something a lot of our homeowners bring up, and here's what we've found...",
        "related_sop_metric": "Active Listening",
    },
    {
        "issue": "No urgency created around storm damage timeline",
        "severity": "medium",
        "why_it_matters": "Insurance claims for storm damage have strict filing deadlines. Not communicating urgency can result in homeowners missing their claim window and losing coverage.",
        "how_to_fix": "When storm damage is mentioned, immediately inform about typical insurance timelines and the risk of further damage from delays. Create honest urgency.",
        "example_language": "With recent storm damage, it's important to get an inspection soon. Most insurance policies have a filing window, and waiting can lead to secondary damage that isn't covered.",
        "related_sop_metric": "Urgency & Timeline",
    },
    {
        "issue": "Failed to ask about insurance coverage for the repair",
        "severity": "medium",
        "why_it_matters": "Many roofing jobs are insurance-covered. Not asking about insurance means missing opportunities to position Apex as an insurance-friendly contractor.",
        "how_to_fix": "For any repair or replacement call, ask if the homeowner has filed or plans to file an insurance claim. Offer to help navigate the process.",
        "example_language": "Have you had a chance to check with your insurance? We work with all major carriers and can help walk you through the claims process to make it as smooth as possible.",
        "related_sop_metric": "Insurance Discussion",
    },
]

# ── Strength templates ────────────────────────────────────────────────────────
STRENGTH_TEMPLATES = [
    {
        "behavior": "Excellent rapport building with personalized greeting",
        "why_effective": "Using the homeowner's name and referencing their specific situation creates immediate trust and makes them more receptive to scheduling an appointment.",
        "related_sop_metric": "Greeting & Rapport",
    },
    {
        "behavior": "Strong value framing when discussing pricing",
        "why_effective": "Proactively addressing cost by framing it in terms of long-term value, warranty coverage, and quality materials reduces price resistance significantly.",
        "related_sop_metric": "Value Proposition",
    },
    {
        "behavior": "Thorough discovery questions about roof condition",
        "why_effective": "Asking detailed questions about roof age, material, and visible issues demonstrates expertise and allows the rep to tailor their recommendation.",
        "related_sop_metric": "Discovery Questions",
    },
    {
        "behavior": "Clear and confident appointment confirmation",
        "why_effective": "Repeating all appointment details and setting expectations for the visit reduces no-shows and builds homeowner confidence in the process.",
        "related_sop_metric": "Appointment Confirmation",
    },
    {
        "behavior": "Empathetic response to customer concerns",
        "why_effective": "Acknowledging the homeowner's frustration or worry before offering solutions makes them feel heard and increases willingness to proceed with the appointment.",
        "related_sop_metric": "Active Listening",
    },
    {
        "behavior": "Proactive mention of financing options",
        "why_effective": "Bringing up financing before the customer asks about cost removes a major barrier and shows that Apex is customer-focused and accessible.",
        "related_sop_metric": "Value Proposition",
    },
    {
        "behavior": "Effective use of social proof and testimonials",
        "why_effective": "Mentioning satisfied customers in the same neighborhood or similar projects builds credibility and leverages the power of community trust.",
        "related_sop_metric": "Objection Handling",
    },
    {
        "behavior": "Smooth transition from inquiry to appointment booking",
        "why_effective": "Naturally guiding the conversation from addressing the homeowner's questions to proposing a specific appointment time shows confidence and keeps momentum.",
        "related_sop_metric": "Appointment Confirmation",
    },
]

# ── Transcript evidence samples ──────────────────────────────────────────────
ISSUE_EVIDENCE = [
    "Rep: 'So when would you like us to come out?' Customer: 'Well, I'm not sure...' Rep: 'How about Tuesday?' — No qualifying questions were asked before jumping to scheduling.",
    "Rep ended the call with 'Alright, we'll see you then' without confirming the date, time, or address of the appointment.",
    "Customer: 'That seems really expensive.' Rep: 'Well, that's our price.' — No attempt to frame the value or discuss warranty coverage.",
    "Rep: 'Hi, this is Apex Roofing, how can I help you?' — Immediately jumped into business without greeting by name or building any rapport.",
    "Rep said 'Someone will come out and look at it' without explaining who would come, how long it takes, or what they'd inspect.",
    "Rep never asked for email. The only follow-up method captured was the phone number already on file.",
    "During the 12-minute call, warranty was never mentioned despite discussing a full roof replacement.",
    "Customer was mid-sentence explaining their concern when the rep started talking about available dates.",
    "Customer mentioned hail damage from last week's storm but rep did not discuss urgency or insurance timelines.",
    "Customer mentioned their roof was damaged in a storm but rep never asked if they had homeowner's insurance.",
]

STRENGTH_EVIDENCE = [
    "Rep: 'Hi Mrs. Garcia! Thanks for calling Apex Roofing. I see you're in the Chandler area — we've done a lot of work in your neighborhood. How can I help you today?'",
    "Rep: 'I understand the investment is significant. What you're getting is not just a new roof, but 25 years of peace of mind with our industry-leading warranty.'",
    "Rep: 'Before we schedule anything, let me ask — how old is your roof? Have you noticed any leaks, missing shingles, or water stains on your ceiling?'",
    "Rep: 'Perfect, so we're all set for Thursday at 2 PM at 5678 Oak Drive. Our inspector Jake will be there in an Apex truck. He'll spend about 45 minutes and you'll get a report within 24 hours.'",
    "Rep: 'I completely understand your concern — dealing with a leaky roof is stressful, especially with the recent storms. Let me see what we can do to help you right away.'",
    "Rep: 'We also offer flexible financing options if you'd like to spread the cost over time. Many of our homeowners take advantage of our 0% interest for 12 months program.'",
    "Rep: 'Actually, we just completed a similar project for the Hendersons on your street. They were really happy with the result — I can share their testimonial if you'd like.'",
    "Rep seamlessly moved from answering questions about materials to: 'It sounds like a great fit for your home. I have Tuesday or Thursday open this week — which works better for you?'",
]


async def seed():
    conn = await asyncpg.connect('postgres://u3us7scpstukqr:p2db3284707c55154b174ff79a0c91afa2d2e63087f44cdc1038627da983f888d@c5cqb8h0eop3g3.cluster-czrs8kj4isg7.us-east-1.rds.amazonaws.com:5432/dcmep4gk3l4f2n')

    cid = COMPANY_ID

    # Get all users (excluding executive)
    users = await conn.fetch(
        "SELECT id, first_name, last_name, role FROM users WHERE company_id = $1 AND role != 'executive'",
        cid
    )
    print(f"Found {len(users)} team members")

    # Get calls + analyses per user (recent 30 days)
    calls_by_user = {}
    for user in users:
        rows = await conn.fetch("""
            SELECT c.id as call_id, ca.id as analysis_id, c.created_at
            FROM calls c
            JOIN call_analyses ca ON ca.call_id = c.id
            WHERE c.company_id = $1 AND c.handled_by_user_id = $2
            ORDER BY c.created_at DESC
        """, cid, user['id'])
        calls_by_user[str(user['id'])] = rows
        print(f"  {user['first_name']} {user['last_name']}: {len(rows)} calls with analyses")

    # ═══════════════════════════════════════════════════════════════════════════
    # 1. SEED COACHING ISSUES
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Seeding coaching_issues ---")
    issues_count = 0

    for user in users:
        uid = str(user['id'])
        user_calls = calls_by_user[uid]
        if not user_calls:
            continue

        # Each user gets 5-10 different issue types, each repeated across 1-5 calls
        num_issue_types = random.randint(5, min(8, len(ISSUE_TEMPLATES)))
        selected_issues = random.sample(ISSUE_TEMPLATES, num_issue_types)

        for issue_tmpl in selected_issues:
            # How many calls show this issue (1-5 for frequency-based aggregation)
            frequency = random.randint(1, 5)
            selected_calls = random.sample(user_calls, min(frequency, len(user_calls)))

            for call_row in selected_calls:
                evidence = random.choice(ISSUE_EVIDENCE)
                await conn.execute("""
                    INSERT INTO coaching_issues
                    (id, call_analysis_id, call_id, company_id, user_id, issue, severity,
                     why_it_matters, how_to_fix, example_language, transcript_evidence,
                     related_sop_metric, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                """,
                    str(uuid4()),
                    call_row['analysis_id'],
                    call_row['call_id'],
                    cid,
                    user['id'],
                    issue_tmpl['issue'],
                    issue_tmpl['severity'],
                    issue_tmpl['why_it_matters'],
                    issue_tmpl['how_to_fix'],
                    issue_tmpl['example_language'],
                    evidence,
                    issue_tmpl['related_sop_metric'],
                    call_row['created_at'] + timedelta(minutes=random.randint(5, 30)),
                )
                issues_count += 1

    print(f"  Inserted {issues_count} coaching issues")

    # ═══════════════════════════════════════════════════════════════════════════
    # 2. SEED COACHING STRENGTHS
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Seeding coaching_strengths ---")
    strengths_count = 0

    for user in users:
        uid = str(user['id'])
        user_calls = calls_by_user[uid]
        if not user_calls:
            continue

        # Each user gets 4-7 different strength types
        num_strength_types = random.randint(4, min(7, len(STRENGTH_TEMPLATES)))
        selected_strengths = random.sample(STRENGTH_TEMPLATES, num_strength_types)

        for strength_tmpl in selected_strengths:
            frequency = random.randint(2, 6)
            selected_calls = random.sample(user_calls, min(frequency, len(user_calls)))

            for call_row in selected_calls:
                evidence = random.choice(STRENGTH_EVIDENCE)
                await conn.execute("""
                    INSERT INTO coaching_strengths
                    (id, call_analysis_id, call_id, company_id, user_id, behavior,
                     why_effective, transcript_evidence, related_sop_metric, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                """,
                    str(uuid4()),
                    call_row['analysis_id'],
                    call_row['call_id'],
                    cid,
                    user['id'],
                    strength_tmpl['behavior'],
                    strength_tmpl['why_effective'],
                    evidence,
                    strength_tmpl['related_sop_metric'],
                    call_row['created_at'] + timedelta(minutes=random.randint(5, 30)),
                )
                strengths_count += 1

    print(f"  Inserted {strengths_count} coaching strengths")

    # ═══════════════════════════════════════════════════════════════════════════
    # 3. SEED COACHING SESSIONS (Impact tab)
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Seeding coaching_sessions ---")
    sessions_count = 0

    focus_area_options = [
        ["compliance_score", "booking_rate"],
        ["compliance_score", "rapport_score"],
        ["booking_rate", "rapport_score"],
        ["compliance_score"],
        ["booking_rate"],
        ["compliance_score", "booking_rate", "rapport_score"],
    ]

    for user in users:
        # Each rep gets 2-4 coaching sessions at different dates
        num_sessions = random.randint(2, 4)

        for i in range(num_sessions):
            focus = random.choice(focus_area_options)
            coached_at = datetime.now(timezone.utc) - timedelta(days=random.randint(5, 60))
            follow_up_days = random.choice([7, 14, 21])
            follow_up_end = coached_at + timedelta(days=follow_up_days)

            # Generate realistic baseline scores
            baseline = {}
            targets = {}
            for area in focus:
                if area == "compliance_score":
                    base_val = round(random.uniform(0.55, 0.80), 3)
                    targets[area] = round(min(base_val + random.uniform(0.05, 0.15), 1.0), 3)
                elif area == "booking_rate":
                    base_val = round(random.uniform(0.30, 0.65), 3)
                    targets[area] = round(min(base_val + random.uniform(0.05, 0.15), 1.0), 3)
                elif area == "rapport_score":
                    base_val = round(random.uniform(0.60, 0.85), 3)
                    targets[area] = round(min(base_val + random.uniform(0.05, 0.10), 1.0), 3)
                baseline[area] = base_val

            # Determine session status and impact
            is_completed = follow_up_end < datetime.now(timezone.utc)
            status = "completed" if is_completed else "in_progress"

            impact_scores = None
            overall_improved = None
            improvement_pct = None
            targets_met = None
            notes_options = [
                "Focused on discovery question techniques. Rep showed good receptiveness to feedback.",
                "Reviewed call recordings together. Identified pattern of rushing through rapport building.",
                "Practiced objection handling role-play scenarios. Rep improved significantly by end of session.",
                "Discussed appointment confirmation script. Rep committed to using the checklist approach.",
                "Reviewed SOP compliance gaps. Created action plan for next two weeks.",
                "Worked on value framing techniques. Rep responded well to the 'cost of waiting' framework.",
                "One-on-one session focused on active listening skills. Practiced pause technique.",
                "Covered insurance discussion flow. Rep now comfortable asking about coverage.",
            ]

            if is_completed:
                impact_scores = {}
                targets_met_dict = {}
                improvements = []
                for area in focus:
                    # Some areas improve, some don't
                    if random.random() < 0.7:  # 70% chance of improvement
                        impact_val = round(baseline[area] + random.uniform(0.03, 0.15), 3)
                        impact_val = min(impact_val, 1.0)
                    else:
                        impact_val = round(baseline[area] + random.uniform(-0.05, 0.02), 3)
                        impact_val = max(impact_val, 0.0)
                    impact_scores[area] = impact_val
                    targets_met_dict[area] = impact_val >= targets[area]
                    improvements.append(impact_val - baseline[area])

                targets_met = targets_met_dict
                avg_improvement = sum(improvements) / len(improvements) if improvements else 0
                overall_improved = avg_improvement > 0
                improvement_pct = round(avg_improvement * 100, 1)

            import json
            await conn.execute("""
                INSERT INTO coaching_sessions
                (id, company_id, rep_user_id, coach_user_id, focus_areas, targets,
                 baseline_scores, status, follow_up_days, follow_up_end_date,
                 impact_scores, overall_improved, improvement_pct, targets_met,
                 notes, coached_at, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            """,
                str(uuid4()),
                cid,
                user['id'],
                EXECUTIVE_ID,
                focus,
                json.dumps(targets),
                json.dumps(baseline),
                status,
                follow_up_days,
                follow_up_end,
                json.dumps(impact_scores) if impact_scores else None,
                overall_improved,
                improvement_pct,
                json.dumps(targets_met) if targets_met else None,
                random.choice(notes_options),
                coached_at,
                coached_at,
            )
            sessions_count += 1

    print(f"  Inserted {sessions_count} coaching sessions")

    # ═══════════════════════════════════════════════════════════════════════════
    # VERIFY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n--- Verification ---")
    for table in ['coaching_issues', 'coaching_strengths', 'coaching_sessions']:
        count = await conn.fetchval(f'SELECT count(*) FROM {table} WHERE company_id = $1', cid)
        print(f"  {table}: {count} rows")

    # Check per-user distribution
    for user in users:
        issues = await conn.fetchval('SELECT count(*) FROM coaching_issues WHERE user_id = $1', user['id'])
        strengths = await conn.fetchval('SELECT count(*) FROM coaching_strengths WHERE user_id = $1', user['id'])
        sessions = await conn.fetchval('SELECT count(*) FROM coaching_sessions WHERE rep_user_id = $1', user['id'])
        print(f"  {user['first_name']} {user['last_name']}: {issues} issues, {strengths} strengths, {sessions} sessions")

    await conn.close()
    print("\nDone!")


if __name__ == '__main__':
    asyncio.run(seed())
