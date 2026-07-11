"""
Populates 4 appointments with provided audio URLs, summaries, and
GPT-4o-derived analysis for company_id d8e4f2a1-...
New DB: ec2-100-30-18-12
"""

import json, os, psycopg2
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Secrets come from the environment (see .env.example). Never hardcode keys here.
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
DB_URL = os.environ["DATABASE_URL"]
COMPANY_ID = "d8e4f2a1-3b5c-4d6e-9f0a-1b2c3d4e5f6a"

client = OpenAI(api_key=OPENAI_API_KEY)

AUDIO_DATA = [
    {
        "url": "https://pub-0d05beffe4df48109a9b7182cfc00427.r2.dev/WhatsApp%20Audio%202026-03-18%20at%204.11.42%20AM.mp4",
        "summary": "A roofing sales rep visited a homeowner to assess a leaking roof built in 1995, finding severely deteriorated 30-pound felt paper underlayment that needed full replacement. The rep walked the homeowner through how a roofing system works, explained that insurance wouldn't cover the damage since it's wear and tear rather than storm damage, and positioned the company against both budget \"chuck in the truck\" operators and large premium companies like State 48 and Lions Roofing. After building trust through credentials (licensed, bonded, insured, ROC-registered, 620+ five-star reviews, brick-and-mortar office), the rep presented two underlayment options and the homeowner settled on the premium \"diamond package\" high-temp underlayment with a 25-year craftsmanship and 50-year manufacturer warranty, priced at $25,000. The homeowner wanted to finance around $500/month but was hesitant to commit as it was his first estimate, wanting to gather two more before deciding. The call ended with the rep attempting to overcome that objection by drawing analogies to car pricing to show that comparable companies wouldn't vary much on price.",
    },
    {
        "url": "https://pub-0d05beffe4df48109a9b7182cfc00427.r2.dev/WhatsApp%20Audio%202026-03-17%20at%2011.07.33%20PM.mp4",
        "summary": "A roofing sales rep visited a homeowner to assess a leaking roof built in 1995, finding severely deteriorated 30-pound felt paper underlayment that needed full replacement. The rep walked the homeowner through how a roofing system works, explained that insurance wouldn't cover the damage since it's wear and tear rather than storm damage, and positioned the company against both budget \"chuck in the truck\" operators and large premium companies like State 48 and Lions Roofing. After building trust through credentials (licensed, bonded, insured, ROC-registered, 620+ five-star reviews, brick-and-mortar office), the rep presented two underlayment options and the homeowner settled on the premium \"diamond package\" high-temp underlayment with a 25-year craftsmanship and 50-year manufacturer warranty, priced at $25,000. The homeowner wanted to finance around $500/month but was hesitant to commit as it was his first estimate, wanting to gather two more before deciding. The call ended with the rep attempting to overcome that objection by drawing analogies to car pricing to show that comparable companies wouldn't vary much on price.",
    },
    {
        "url": "https://pub-0d05beffe4df48109a9b7182cfc00427.r2.dev/WhatsApp%20Audio%202026-03-05%20at%201.49.52%20PM.mp4",
        "summary": "A roofing sales rep (Cole) visited homeowner Ben, who recently purchased a home built in 2002 with a failing roof and an active leak. Cole inspected the roof, confirmed the underlayment is past its lifespan, and presented three packages ranging from about $25,600 to $29,650, along with financing options including an 18-month no-interest plan. Ben shared that he'd already received quotes from other roofers ($20,800 and ~$26,000) and has one more estimate coming, so he declined to commit on the spot but expressed interest in the top-tier diamond package. The two also chatted casually about Ben's vitamin business, his home renovation plans, family, and Arizona sports before agreeing to follow up by phone later in the week.",
    },
    {
        "url": "https://pub-0d05beffe4df48109a9b7182cfc00427.r2.dev/WhatsApp%20Audio%202026-03-18%20at%204.12.08%20AM.mp4",
        "summary": "The sales rep (Lee) visited a home near a golf course to assess a roof leak that had caused water damage above the master bathroom sink. The homeowner explained the leak likely resulted from golf ball impacts, and that insurance had already sent an adjuster. Lee inspected the damage, recommended repairing the entire right side of the roof rather than isolating the small section, and presented three package options with varying warranties (10, 15, and 25 years). He also provided full roof replacement pricing at the homeowner's request, applying a military discount. The homeowner's girlfriend (Bri/Brentanna), who owns the property, was not present but will review the emailed quotes and coordinate with their insurer before deciding next steps. Lee planned to photograph the roof before leaving and agreed to follow up in a couple of weeks.",
    },
]


def analyze(summary: str) -> dict:
    print(f"  Analyzing with GPT-4o...")
    prompt = f"""You are analyzing a home services (roofing) in-person sales appointment summary.

Summary:
\"\"\"{summary}\"\"\"

Return a JSON object with ALL of these fields populated realistically based on the summary:
{{
  "key_points": ["max 5 key points from the appointment"],
  "action_items": ["specific action items for the sales rep"],
  "next_steps": ["next steps agreed upon"],
  "service_requested": "specific roofing service described",
  "customer_name": "customer first name if mentioned, else null",
  "sentiment_score": <float 0.0-1.0, 0=very negative, 1=very positive>,
  "booking_status": "not_booked",
  "outcome": "lost",
  "call_outcome_category": "follow_up_needed",
  "qualification_status": "qualified",
  "qualification_overall_score": <float 0.6-0.9>,
  "qualification_confidence_score": <float 0.7-0.95>,
  "follow_up_required": true,
  "follow_up_reason": "specific reason follow-up is needed",
  "urgency_signals": ["urgency signals mentioned e.g. active leak, water damage"],
  "budget_indicators": ["budget signals e.g. financing interest, price discussed"],
  "is_existing_customer": false,
  "objections": ["slugs from: customer_needs_time_to_decide, service_fee_concerns, scheduling_conflicts, other"],
  "bant_need_score": <float 0.7-1.0>,
  "bant_budget_score": <float 0.4-0.8>,
  "bant_timeline_score": <float 0.4-0.8>,
  "bant_authority_score": <float 0.4-0.9>,
  "sop_compliance_score": <float 0.6-0.95>,
  "sop_compliance_rate": <float 0.6-0.95>,
  "sop_compliance_confidence": <float 0.7-0.95>,
  "sop_stages_completed": ["intro", "needs_assessment", "product_presentation", "pricing_discussion"],
  "sop_stages_missed": ["closing"],
  "sop_compliance_positive_behaviors": ["positive behaviors observed"],
  "sop_compliance_issues": ["compliance issues if any"],
  "detected_call_type": "outbound",
  "is_deprioritized": false,
  "priority_score": <float 0.5-0.9>,
  "summary_confidence_score": 0.88,
  "appointment_intent": "estimate",
  "property_details": {{"year_built": <year if mentioned>, "roof_condition": "deteriorated", "has_active_leak": true}},
  "customer_details": {{"financing_interest": true, "decision_timeline": "gathering_multiple_estimates"}}
}}

Return ONLY valid JSON, no markdown, no explanation.
"""
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


def get_appointment_ids(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id FROM appointments
            WHERE company_id = %s AND audio_url IS NULL
            ORDER BY created_at DESC
        """, (COMPANY_ID,))
        return [row[0] for row in cur.fetchall()]


def update_appointment(conn, appt_id, data: dict, analysis: dict):
    objections = analysis.get("objections", [])
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE appointments SET
                audio_url                          = %s,
                recording_status                   = 'completed',
                analysis_status                    = 'completed',
                summary                            = %s,
                key_points                         = %s,
                action_items                       = %s,
                next_steps                         = %s,
                service_requested                  = %s,
                customer_name                      = %s,
                sentiment_score                    = %s,
                booking_status                     = %s,
                outcome                            = %s,
                call_outcome_category              = %s,
                qualification_status               = %s,
                qualification_overall_score        = %s,
                qualification_confidence_score     = %s,
                follow_up_required                 = %s,
                follow_up_reason                   = %s,
                urgency_signals                    = %s,
                budget_indicators                  = %s,
                is_existing_customer               = %s,
                objections                         = %s,
                objections_total_count             = %s,
                bant_need_score                    = %s,
                bant_budget_score                  = %s,
                bant_timeline_score                = %s,
                bant_authority_score               = %s,
                sop_compliance_score               = %s,
                sop_compliance_rate                = %s,
                sop_compliance_confidence          = %s,
                sop_stages_completed               = %s,
                sop_stages_missed                  = %s,
                sop_stages_total                   = %s,
                sop_compliance_positive_behaviors  = %s,
                sop_compliance_issues              = %s,
                detected_call_type                 = %s,
                is_deprioritized                   = %s,
                priority_score                     = %s,
                summary_confidence_score           = %s,
                appointment_intent                 = %s,
                property_details                   = %s,
                customer_details                   = %s,
                updated_at                         = NOW()
            WHERE id = %s AND company_id = %s
        """, (
            data["url"],
            data["summary"],
            analysis.get("key_points", []),
            analysis.get("action_items", []),
            analysis.get("next_steps", []),
            analysis.get("service_requested"),
            analysis.get("customer_name"),
            analysis.get("sentiment_score", 0.6),
            analysis.get("booking_status", "not_booked"),
            analysis.get("outcome", "lost"),
            analysis.get("call_outcome_category", "follow_up_needed"),
            analysis.get("qualification_status", "qualified"),
            analysis.get("qualification_overall_score", 0.7),
            analysis.get("qualification_confidence_score", 0.85),
            analysis.get("follow_up_required", True),
            analysis.get("follow_up_reason"),
            analysis.get("urgency_signals", []),
            analysis.get("budget_indicators", []),
            analysis.get("is_existing_customer", False),
            objections,
            len(objections),
            analysis.get("bant_need_score", 0.8),
            analysis.get("bant_budget_score", 0.6),
            analysis.get("bant_timeline_score", 0.6),
            analysis.get("bant_authority_score", 0.6),
            analysis.get("sop_compliance_score", 0.75),
            analysis.get("sop_compliance_rate", 0.75),
            analysis.get("sop_compliance_confidence", 0.85),
            analysis.get("sop_stages_completed", []),
            analysis.get("sop_stages_missed", []),
            len(analysis.get("sop_stages_completed", [])) + len(analysis.get("sop_stages_missed", [])),
            analysis.get("sop_compliance_positive_behaviors", []),
            analysis.get("sop_compliance_issues", []),
            analysis.get("detected_call_type", "outbound"),
            analysis.get("is_deprioritized", False),
            analysis.get("priority_score", 0.7),
            analysis.get("summary_confidence_score", 0.88),
            analysis.get("appointment_intent", "estimate"),
            json.dumps(analysis.get("property_details", {})),
            json.dumps(analysis.get("customer_details", {})),
            str(appt_id),
            COMPANY_ID,
        ))
    conn.commit()


def main():
    conn = psycopg2.connect(DB_URL)
    print("Connected to DB.")

    # Step 1: Pre-analyze all 4 summaries once
    print("Pre-analyzing 4 summaries with GPT-4o...")
    analyses = []
    for i, data in enumerate(AUDIO_DATA):
        print(f"  Analyzing summary {i+1}/4...")
        analyses.append(analyze(data["summary"]))
    print("Analysis complete.\n")

    # Step 2: Get all remaining appointments
    appt_ids = get_appointment_ids(conn)
    print(f"Found {len(appt_ids)} appointments to populate.\n")

    # Step 3: Cycle through audio data and update all appointments
    total = len(appt_ids)
    for i, appt_id in enumerate(appt_ids):
        idx = i % 4  # cycle through the 4 audio entries
        data = AUDIO_DATA[idx]
        analysis = analyses[idx]
        update_appointment(conn, appt_id, data, analysis)
        if (i + 1) % 50 == 0 or (i + 1) == total:
            print(f"  Progress: {i+1}/{total} updated...")

    conn.close()
    print(f"\n=== Done: {total} appointments populated ===")


if __name__ == "__main__":
    main()
