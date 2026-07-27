"""
Seed the Otto database with realistic, referentially-coherent demo data.

Builds three home-services tenants (roofing, HVAC, plumbing) with ~6 months of
call history and drives every downstream table off the *same* generated journey
so aggregates (leaderboards, coaching, pipeline counts) agree with the raw rows.

Usage:
    TARGET_SYNC_URL=postgresql+psycopg2://user:pass@host:5432/db \
        python scripts/seed_ottoai_v2.py

The script is deterministic (fixed RNG seed) and idempotent in the sense that it
truncates every table it owns before inserting.
"""
from __future__ import annotations

import os
import pkgutil
import importlib
import random
import sys
import hashlib
from datetime import datetime, timedelta, timezone, date
from uuid import uuid4

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy import JSON as SA_JSON  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB  # noqa: E402

from app.infrastructure.database.base import Base  # noqa: E402
import app.infrastructure.database.models as _models_pkg  # noqa: E402

for _mi in pkgutil.iter_modules(_models_pkg.__path__):
    importlib.import_module("app.infrastructure.database.models." + _mi.name)

from app.core.security import get_password_hash  # noqa: E402

RNG = random.Random(20260727)
NOW = datetime.now(timezone.utc).replace(microsecond=0)
HISTORY_DAYS = 180
DEMO_PASSWORD = "Otto@Demo2026"

T = Base.metadata.tables

# Rows are accumulated per table then bulk-inserted in topological order.
ROWS: dict[str, list[dict]] = {name: [] for name in T}


def add(table: str, **kw):
    ROWS[table].append(kw)
    return kw


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def biz_time(days_ago: float) -> datetime:
    """A timestamp `days_ago` days back, pushed into plausible business hours."""
    base = NOW - timedelta(days=days_ago)
    # Home-services phones ring 7am-6pm local; skew toward late morning.
    hour = RNG.choices(
        [7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19],
        weights=[3, 7, 11, 13, 12, 9, 10, 11, 10, 8, 5, 2, 1],
    )[0]
    dt = base.replace(hour=hour, minute=RNG.randrange(60), second=RNG.randrange(60))
    # Weekends are much quieter - pull most weekend calls back to Friday.
    if dt.weekday() == 5 and RNG.random() < 0.75:
        dt -= timedelta(days=1)
    elif dt.weekday() == 6 and RNG.random() < 0.85:
        dt -= timedelta(days=2)
    # Rounding into business hours can overshoot the present; never emit a future call.
    while dt > NOW:
        dt -= timedelta(days=1)
    return dt


def month_key(dt: datetime) -> str:
    """leaderboard_stats.period_key format used by the app ('YYYY-MM')."""
    return dt.strftime("%Y-%m")


def phone(area: str) -> str:
    """Fictional-but-valid-format US number (555 exchange is reserved for fiction)."""
    return f"+1{area}555{RNG.randrange(1000, 10000)}"


def pick(seq):
    return RNG.choice(seq)


def maybe(p: float) -> bool:
    return RNG.random() < p


def sample(seq, k):
    k = min(k, len(seq))
    return RNG.sample(list(seq), k) if k > 0 else []


def fingerprint(*parts) -> str:
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()[:64]


FIRST_NAMES = [
    "Marcus", "Dana", "Priya", "Tyler", "Rosa", "Ahmed", "Kelsey", "Jordan", "Bianca",
    "Trevor", "Nina", "Omar", "Chelsea", "Devin", "Maya", "Grant", "Lucia", "Peter",
    "Simone", "Kyle", "Fatima", "Brandon", "Elise", "Ravi", "Holly", "Sean", "Adaeze",
    "Wesley", "Camila", "Nathan", "Ingrid", "Darius", "Paula", "Colin", "Yuki", "Reid",
    "Anita", "Gustavo", "Meredith", "Cole", "Tanya", "Emmett", "Sofia", "Blake", "Noor",
    "Damon", "Leah", "Curtis", "Rhea", "Vince", "Georgia", "Malik", "Erin", "Hugo",
]
LAST_NAMES = [
    "Alvarez", "Whitfield", "Nakamura", "Brennan", "Okafor", "Delgado", "Kowalski",
    "Ferris", "Mbeki", "Lindqvist", "Rahman", "Castellano", "Boyd", "Ferreira", "Nash",
    "Ivanova", "Pruitt", "Sandoval", "Halloway", "Chastain", "Novak", "Emerson",
    "Villalobos", "Reyes", "Tran", "Kirkpatrick", "Bhatt", "Cormier", "Ashworth",
    "Duval", "Mercado", "Stoddard", "Achebe", "Lindgren", "Варга", "Petrov", "Quintero",
    "Marchetti", "Draper", "Sylvester", "Cardoso", "Bellamy", "Nguyen", "Ostrowski",
]
LAST_NAMES = [n for n in LAST_NAMES if n.isascii()]

STREETS = [
    "Aspen Grove Ln", "Fielder Ct", "Marigold Way", "N Sherwood Dr", "Bellweather Rd",
    "Copperfield Ave", "Old Mill Rd", "Larkspur Cir", "Tanager St", "Windrow Pl",
    "S Kestrel Blvd", "Juniper Hollow", "Pemberton Ave", "Cedar Bluff Trl", "Halstead St",
    "Quarry Ridge Rd", "Sablewood Dr", "Foxtail Ln", "Braeburn Ct", "Wrenfield Way",
]

LEAD_SOURCES = [
    "Google LSA", "Google Ads", "Organic Search", "Facebook Ads", "Referral",
    "Yelp", "Angi", "Direct Mail", "Repeat Customer", "Nextdoor", "Yard Sign",
]

# --------------------------------------------------------------------------
# Tenant definitions
# --------------------------------------------------------------------------

COMPANIES = [
    {
        "name": "Summit Ridge Roofing & Exteriors",
        "domain": "summitridgeroofing.com",
        "industry": "Roofing & Storm Restoration",
        "city": "Denver", "state": "CO", "area": "720", "tz": "America/Denver",
        "address": "4820 Vasquez Blvd, Unit 12, Denver, CO 80216",
        "lat": 39.7817, "lon": -104.9584,
        "services": ["Roof Replacement", "Storm & Hail Damage", "Roof Repair",
                     "Gutter Replacement", "Siding", "Skylight Repair",
                     "Free Roof Inspection"],
        "not_offered": ["Commercial TPO over 20k sqft", "Solar panel installation",
                        "Interior drywall repair"],
        "deal_range": (7800, 46000),
        "n_leads": 210, "n_csr": 3, "n_rep": 5,
        "crm": "servicetitan", "voip": "callrail",
    },
    {
        "name": "BlueFlame Heating & Air",
        "domain": "blueflamehvac.com",
        "industry": "HVAC",
        "city": "Phoenix", "state": "AZ", "area": "602", "tz": "America/Phoenix",
        "address": "3311 W Earll Dr, Suite 200, Phoenix, AZ 85017",
        "lat": 33.4942, "lon": -112.1301,
        "services": ["AC Repair", "AC Replacement", "Furnace Repair", "Heat Pump Install",
                     "Ductwork & Sealing", "Maintenance Plan", "Indoor Air Quality"],
        "not_offered": ["Swamp cooler service", "Commercial chillers",
                        "Geothermal systems"],
        "deal_range": (3200, 19500),
        "n_leads": 140, "n_csr": 2, "n_rep": 4,
        "crm": "housecallpro", "voip": "callrail",
    },
    {
        "name": "Cascade Plumbing Co.",
        "domain": "cascadeplumbingco.com",
        "industry": "Plumbing",
        "city": "Portland", "state": "OR", "area": "503", "tz": "America/Los_Angeles",
        "address": "1145 SE Grand Ave, Portland, OR 97214",
        "lat": 45.5122, "lon": -122.6607,
        "services": ["Drain Cleaning", "Water Heater Replacement", "Sewer Line Repair",
                     "Repiping", "Leak Detection", "Fixture Install", "Trenchless Sewer"],
        "not_offered": ["Septic tank pumping", "Well pump service",
                        "Irrigation backflow testing"],
        "deal_range": (320, 11500),
        "n_leads": 85, "n_csr": 2, "n_rep": 3,
        "crm": "jobber", "voip": "twilio",
    },
]

# Lead status funnel - weights sum to 100.
STATUS_FUNNEL = [
    ("new", 8), ("warm", 10), ("hot", 7),
    ("qualified_booked", 14), ("qualified_unbooked", 12),
    ("qualified_service_not_offered", 4),
    ("nurturing", 10), ("dormant", 7), ("abandoned", 5),
    ("closed_won", 14), ("closed_lost", 9),
]

STATUS_MAP = {
    # lead.status -> (deal_status, pipeline_stage)
    "new": ("new", None),
    "warm": ("nurturing", "qualified"),
    "hot": ("nurturing", "qualified"),
    "qualified_booked": ("booked", "booked"),
    "qualified_unbooked": ("nurturing", "qualified"),
    "qualified_service_not_offered": ("lost", "service_not_offered"),
    "nurturing": ("nurturing", "qualified"),
    "dormant": ("nurturing", "qualified"),
    "abandoned": ("lost", "unqualified"),
    "closed_won": ("won", "won"),
    "closed_lost": ("lost", "lost"),
}

OBJECTIONS = [
    "immediate_service_unavailability", "phone_connection_issues",
    "customer_needs_time_to_decide", "scheduling_conflicts", "service_fee_concerns",
    "in_person_estimates_only", "inefficient_agent_communication",
    "customer_data_privacy_concerns", "insurance_related",
    "trust_credibility_concerns", "not_the_decision_maker",
    "workmanship_quality_complaints", "other", "service_not_catered",
    "competitor_related_concerns",
]
OBJECTION_IDS = {name: i + 1 for i, name in enumerate(OBJECTIONS)}

OBJECTION_QUOTES = {
    "service_fee_concerns": [
        "Ninety-nine dollars just for somebody to come look at it? That seems steep.",
        "Do I still pay the trip charge if I decide not to move forward?",
        "The last company didn't charge me anything for an estimate.",
    ],
    "customer_needs_time_to_decide": [
        "I want to talk it over with my wife before we schedule anything.",
        "Let me sit on it for a couple days and I'll call you back.",
        "I'm still getting quotes, I don't want to commit yet.",
    ],
    "scheduling_conflicts": [
        "I work until six, there's no way I can do a two-to-four window.",
        "We're out of town until the twelfth.",
        "Do you have anything on a Saturday? Weekdays don't work for me.",
    ],
    "competitor_related_concerns": [
        "I already have two other bids, one of them came in a lot lower.",
        "My neighbor used a different company and was happy with them.",
        "What makes you different from the guys advertising on the radio?",
    ],
    "insurance_related": [
        "I need to know if my insurance is going to cover this before I do anything.",
        "The adjuster hasn't come out yet, should I wait for him?",
        "My deductible is twenty-five hundred, is it even worth filing?",
    ],
    "not_the_decision_maker": [
        "This is really my husband's call, he handles all this stuff.",
        "I'd have to run it by our HOA board first.",
        "I'm just the tenant, you'd need to talk to the property manager.",
    ],
    "trust_credibility_concerns": [
        "How long have you all been in business? I've been burned before.",
        "Are you licensed and bonded in this state?",
        "I've never heard of your company, honestly.",
    ],
    "in_person_estimates_only": [
        "Can't you just give me a ballpark over the phone?",
        "I don't really want somebody coming out just to give a number.",
    ],
    "immediate_service_unavailability": [
        "Three weeks out? I've got water coming in right now.",
        "That's too long, I need someone today.",
    ],
    "workmanship_quality_complaints": [
        "The last crew left nails all over my driveway.",
        "Somebody came out last year and it started leaking again in six months.",
    ],
    "customer_data_privacy_concerns": [
        "Why do you need my email address just to book an appointment?",
        "I'd rather not give out my full address until I know the price.",
    ],
    "phone_connection_issues": [
        "You're breaking up, can you hear me?",
        "Sorry, I'm driving through a canyon, I keep losing you.",
    ],
    "service_not_catered": [
        "So you don't do that at all? Who would I even call?",
    ],
    "inefficient_agent_communication": [
        "I've explained this twice now, is there someone else I can talk to?",
        "I was on hold for eleven minutes before anyone picked up.",
    ],
    "other": [
        "I have three dogs, is that going to be a problem for the crew?",
        "Do you all take payment plans?",
    ],
}

SOP_ALL = ["greeting", "qualification", "presentation", "objection_handling", "close", "follow_up"]

SOP_ISSUES = [
    ("Did not confirm the callback number before ending the call",
     "A wrong or missing callback number is the single most common reason a qualified lead goes cold.",
     "Read the number back digit by digit and ask the caller to confirm it.",
     "\"Let me make sure I have you right - that's 720-555-0142, correct?\"", "greeting"),
    ("Quoted a price range before understanding scope",
     "Anchoring on a number before scoping invites price shopping and kills the in-home visit.",
     "Defer pricing until the inspection is booked; sell the visit, not the number.",
     "\"Pricing really depends on what we find up there - the inspection is free, and you'll get an exact number that day.\"", "presentation"),
    ("Missed the urgency signal when the caller mentioned active water intrusion",
     "Active damage is a same-day dispatch trigger; missing it loses the job to whoever answers next.",
     "Flag any mention of active leaking, no heat, or no water as emergency routing.",
     "\"You've got water coming in right now? Let me get someone out to you today.\"", "qualification"),
    ("Accepted the first 'let me think about it' without a single reframe",
     "One soft close attempt is the difference between a booked inspection and a nurture cycle.",
     "Acknowledge, then offer a low-commitment next step rather than ending the call.",
     "\"Totally fair. The inspection itself is free and there's no obligation - want me to hold Thursday at 10 so you have the option?\"", "objection_handling"),
    ("No specific follow-up commitment was set",
     "'I'll call you back' with no date is functionally the same as never calling back.",
     "Always end with a named day and time window, and log it.",
     "\"I'll give you a ring Tuesday morning between 9 and 11 - does that work?\"", "follow_up"),
    ("Talked over the homeowner three times during the qualification questions",
     "Interruptions during discovery suppress the details you need to price and route the job.",
     "Let the caller finish, then summarize back before your next question.",
     "\"Sorry, go ahead - I want to make sure I get this right.\"", "qualification"),
    ("Did not capture how the caller heard about us",
     "Missing attribution corrupts the marketing spend report for the whole month.",
     "Ask the source question once, early, before the conversation gets technical.",
     "\"Real quick before I forget - how'd you hear about us?\"", "greeting"),
    ("Failed to mention the workmanship warranty when trust was questioned",
     "The warranty is the strongest trust asset available and it went unused against a direct objection.",
     "Pair every credibility objection with the warranty and the licence number.",
     "\"We've been in Denver 18 years, we're fully licensed and bonded, and every roof carries a 10-year workmanship warranty.\"", "objection_handling"),
    ("Let the caller off the phone without confirming the service address",
     "Without an address the job can't be routed or the territory checked.",
     "Confirm the service address before any scheduling talk.",
     "\"And the work would be at the same address, or a different property?\"", "qualification"),
    ("Booked the appointment but never confirmed who would be home",
     "A decision-maker who isn't present turns a sales call into a second trip.",
     "Confirm all decision makers will be present when you set the slot.",
     "\"Will both you and your husband be there? It saves everybody a second visit.\"", "close"),
]

SOP_STRENGTHS = [
    ("Opened with the company name, own name, and an offer to help within four seconds",
     "A crisp branded greeting sets caller expectations and measurably reduces early hang-ups.",
     "greeting"),
    ("Reflected the caller's urgency back before moving to logistics",
     "Matching emotional register early buys permission for the qualification questions that follow.",
     "qualification"),
    ("Used a soft assumptive close with two concrete time slots",
     "Choice-of-two removes the yes/no decision and consistently lifts booking rate.",
     "close"),
    ("Reframed the trip charge as credited toward the repair",
     "Turning a cost objection into a credit removes the loss framing without discounting.",
     "objection_handling"),
    ("Confirmed the full address and callback number back to the caller",
     "Read-back verification is the cheapest possible defence against dead leads.",
     "greeting"),
    ("Proactively surfaced the financing option before price was raised",
     "Leading with payment flexibility prevents sticker shock from ending the call.",
     "presentation"),
    ("Set a named follow-up day and time before hanging up",
     "Specific commitments convert to contact at roughly triple the rate of vague ones.",
     "follow_up"),
    ("Asked what the homeowner had already tried before offering a diagnosis",
     "Discovery before prescription builds credibility and shortens the on-site visit.",
     "qualification"),
    ("Named the workmanship warranty and licence status unprompted",
     "Volunteering credentials pre-empts the trust objection entirely.",
     "objection_handling"),
    ("Summarised next steps in one sentence at the end of the call",
     "A clean recap reduces no-shows and inbound 'what did we agree' callbacks.",
     "close"),
]


# --------------------------------------------------------------------------
# Transcript generation
# --------------------------------------------------------------------------

INTAKE_REASONS = {
    "Roofing & Storm Restoration": [
        ("hail damage from the storm a couple weeks back", "roof replacement"),
        ("a brown stain spreading on the upstairs ceiling", "roof repair"),
        ("shingles all over the front yard after the wind", "roof repair"),
        ("gutters pulling away from the fascia", "gutter replacement"),
        ("a roof that's about twenty-two years old", "roof replacement"),
        ("water coming in around the skylight", "skylight repair"),
    ],
    "HVAC": [
        ("an AC unit blowing warm air since yesterday", "ac repair"),
        ("a system that's short cycling every ten minutes", "ac repair"),
        ("a nineteen-year-old unit that finally quit", "ac replacement"),
        ("one bedroom that never gets cold", "ductwork & sealing"),
        ("a furnace making a grinding noise on startup", "furnace repair"),
        ("wanting to get on a maintenance plan before summer", "maintenance plan"),
    ],
    "Plumbing": [
        ("a kitchen sink that backs up every time the dishwasher runs", "drain cleaning"),
        ("no hot water since this morning", "water heater replacement"),
        ("a wet spot in the yard that won't dry out", "sewer line repair"),
        ("low pressure everywhere in the house", "repiping"),
        ("a toilet that keeps running", "fixture install"),
        ("roots in the main line again", "trenchless sewer"),
    ],
}


SOURCE_REPLIES = [
    "Google, I think.",
    "My neighbor recommended you all.",
    "I saw your truck in the neighborhood.",
    "You came up first when I searched.",
]
SLOT_REPLIES = [
    "Thursday morning works.",
    "Let's do Friday afternoon.",
    "Thursday, the earlier the better.",
]
DEFER_REPLIES = [
    "Yeah, that's fine.",
    "Sure, give me a call.",
    "I'll probably know more by then.",
]


def make_transcript(co, csr_name, caller_name, reason, booked, objs, missed=False):
    """Build a plausible multi-turn CSR intake transcript."""
    if missed:
        return None
    lines = [
        f"CSR: Thanks for calling {co['name']}, this is {csr_name}, how can I help you today?",
        f"Caller: Hi, yeah, this is {caller_name}. I've got {reason[0]} and I wanted to see about getting somebody out.",
        "CSR: Absolutely, sorry you're dealing with that. Let me grab a few details and we'll get you taken care of.",
        f"Caller: Sure.",
        "CSR: And is this at your home address, or a different property?",
        "Caller: It's my house, yeah.",
        "CSR: Perfect. And what's the best number to reach you if we get disconnected?",
        "Caller: This one is fine.",
        "CSR: Great. Can I ask how you heard about us?",
    ]
    lines.append("Caller: " + pick(SOURCE_REPLIES))

    for o in objs:
        quote = pick(OBJECTION_QUOTES.get(o, OBJECTION_QUOTES["other"]))
        lines.append(f"Caller: {quote}")
        lines.append(f"CSR: {pick(_objection_response(o, co))}")

    if booked:
        lines += [
            "CSR: I've got Thursday morning between nine and eleven, or Friday afternoon two to four. Which works better?",
            "Caller: " + pick(SLOT_REPLIES),
            "CSR: You're all set. You'll get a text confirmation in a few minutes, and the tech will call about thirty minutes out.",
            "Caller: Sounds good, thank you.",
            "CSR: Thank you for calling, we'll see you then.",
        ]
    else:
        lines += [
            "CSR: No problem at all. Would it be alright if I followed up with you early next week?",
            "Caller: " + pick(DEFER_REPLIES),
            "CSR: Perfect, I'll reach out Tuesday morning. Thanks for calling.",
        ]
    return "\n".join(lines)


def _objection_response(o, co):
    return {
        "service_fee_concerns": [
            "That's a fair question - the diagnostic fee gets credited straight back toward the repair if you move forward with us.",
            "I hear you. It covers the tech's time on site, and it comes off the total if we do the work.",
        ],
        "customer_needs_time_to_decide": [
            "Totally reasonable. The inspection itself is free and there's no obligation - I can hold a slot so you have the option.",
            "Of course. Would it help to have the numbers in hand while you talk it over?",
        ],
        "scheduling_conflicts": [
            "No problem, we do have early morning slots starting at seven, and limited Saturday availability.",
            "Let me see what we have outside normal hours for you.",
        ],
        "competitor_related_concerns": [
            f"Good - you should get a few bids. What I'd say is our estimate is itemized so you can compare line for line.",
            "Happy to be one of them. We'll give you a written scope so it's an apples-to-apples comparison.",
        ],
        "insurance_related": [
            "We work with adjusters all the time. Our inspector can document everything and meet the adjuster on site if you want.",
            "We can do a free damage assessment first so you know whether filing even makes sense.",
        ],
        "not_the_decision_maker": [
            "Makes sense - would it work to set something up when you're both available?",
            "No problem, I can send the details over so you have them to share.",
        ],
        "trust_credibility_concerns": [
            f"Completely fair. We've been serving {co['city']} for years, we're licensed and bonded, and the work carries a written warranty.",
            "I get it. I can send you our licence number and a few recent references in your area.",
        ],
        "in_person_estimates_only": [
            "I wish I could, but a number over the phone would just be a guess. The visit is free and you'll get an exact figure.",
        ],
        "immediate_service_unavailability": [
            "Let me check the emergency board - if there's active damage we prioritise that.",
        ],
        "workmanship_quality_complaints": [
            "That's not acceptable and I'm sorry. Let me note that and have a supervisor follow up with you directly.",
        ],
        "customer_data_privacy_concerns": [
            "Only for the confirmation and the invoice - we don't sell or share it, and I can skip the email if you'd rather.",
        ],
        "phone_connection_issues": [
            "I've got you now. If we drop I'll call you right back on this number.",
        ],
        "service_not_catered": [
            "We don't handle that one in-house, but I can point you to a couple of shops that do.",
        ],
        "inefficient_agent_communication": [
            "I apologise for that - let me get this sorted for you right now.",
        ],
        "other": [
            "Not a problem at all, I'll make a note of it on the work order.",
        ],
    }.get(o, ["Understood, let me make a note of that."])


def make_sales_transcript(co, rep_name, caller_name, service, outcome):
    lines = [
        f"Rep: Hi {caller_name}, {rep_name} with {co['name']} - thanks for having me out.",
        "Homeowner: Come on in.",
        f"Rep: So walk me through what's been going on with the {service.lower()}.",
        "Homeowner: It's been getting worse over the last few months, honestly.",
        "Rep: Okay. Let me take a look and get some measurements, then I'll walk you through what I'm seeing.",
        "Homeowner: How long does that usually take?",
        "Rep: About twenty minutes, and then we'll sit down and go over options together.",
        "Rep: Alright - here's what I found, and I took photos of everything so you can see it yourself.",
    ]
    if outcome == "won":
        lines += [
            "Homeowner: That's more than I was hoping, but it makes sense seeing the pictures.",
            "Rep: I hear you. We do have financing - a lot of folks go with the 12-month no-interest option.",
            "Homeowner: What's the soonest you could start?",
            "Rep: We could get you on the schedule for the week after next.",
            "Homeowner: Let's do it.",
            "Rep: Excellent. I'll get the paperwork started and you'll have the schedule confirmation by tomorrow.",
        ]
    elif outcome == "lost":
        lines += [
            "Homeowner: I appreciate the detail, but that's over what the other company quoted.",
            "Rep: Can I ask what their scope covered? Sometimes the difference is in the decking or the underlayment.",
            "Homeowner: I'd have to look. Either way I think we're going to go the other direction.",
            "Rep: Understood. I'll leave the itemized quote with you - it's good for thirty days if anything changes.",
            "Homeowner: Thanks for coming out.",
        ]
    else:
        lines += [
            "Homeowner: This is a lot to take in. I need to talk to my wife before we decide anything.",
            "Rep: Absolutely. I'll email you the full quote with the photos tonight.",
            "Rep: Would it be alright if I checked back in on Monday?",
            "Homeowner: Yeah, Monday's fine.",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------

def build():
    all_user_period_stats: dict[tuple, dict] = {}

    for co in COMPANIES:
        cid = uuid4()
        co["id"] = cid
        co_created = NOW - timedelta(days=HISTORY_DAYS + RNG.randrange(60, 400))

        add("companies",
            id=cid, name=co["name"], phone_number=phone(co["area"]),
            address=co["address"],
            reference_doc_url=f"https://docs.gomotto.ai/{co['domain']}/reference-guide.pdf",
            sop_doc_url=f"https://docs.gomotto.ai/{co['domain']}/sop-master.pdf",
            csr_sop_doc_url=f"https://docs.gomotto.ai/{co['domain']}/sop-csr-v4.pdf",
            sales_sop_doc_url=f"https://docs.gomotto.ai/{co['domain']}/sop-sales-v3.pdf",
            follow_up_manual_review_enabled=maybe(0.5),
            extra_metadata={
                "timezone": co["tz"], "industry": co["industry"],
                "website": f"https://www.{co['domain']}",
                "onboarded_at": co_created.isoformat(),
                "crew_count": RNG.randrange(3, 14),
                "avg_ticket_usd": round(sum(co["deal_range"]) / 2, 2),
            })

        add("company_integrations",
            id=uuid4(), company_id=cid,
            location_id=f"loc_{RNG.randrange(100000, 999999)}",
            crm_provider=co["crm"],
            crm_api_encrypted_key="enc:v1:" + uuid4().hex,
            crm_company_id=str(RNG.randrange(100000, 999999)),
            voip_provider=co["voip"],
            voip_api_encrypted_key="enc:v1:" + uuid4().hex,
            voip_access_key_encrypted="enc:v1:" + uuid4().hex,
            voip_company_id=str(RNG.randrange(100000, 999999)),
            st_tenant_id=str(RNG.randrange(1000000, 9999999)) if co["crm"] == "servicetitan" else None,
            st_client_id=("cid." + uuid4().hex[:20]) if co["crm"] == "servicetitan" else None,
            st_client_secret_encrypted=("enc:v1:" + uuid4().hex) if co["crm"] == "servicetitan" else None,
            recording_disclosure_enabled=True,
            extra_metadata={"sync_enabled": True, "last_sync_at": (NOW - timedelta(hours=RNG.randrange(1, 20))).isoformat(),
                            "webhook_verified": True})

        add("tenant_configs",
            id=uuid4(), company_id=cid, company_name=co["name"],
            shunya_config_id=f"cfg_{co['domain'].split('.')[0]}_{RNG.randrange(1000, 9999)}",
            qualification_thresholds={"min_overall_score": 0.62, "bant_need": 0.55,
                                      "bant_budget": 0.45, "bant_timeline": 0.5,
                                      "bant_authority": 0.5, "hot_lead_score": 0.82},
            service_prioritization={s: i + 1 for i, s in enumerate(co["services"])},
            custom_keywords={"urgent": ["leaking now", "no heat", "no water", "flooding", "active leak"],
                             "high_value": ["full replacement", "whole house", "repipe", "new system"],
                             "disqualify": co["not_offered"]},
            qualification_rules={"require_address": True, "require_decision_maker": False,
                                 "min_call_duration_seconds": 45,
                                 "auto_deprioritize_existing_customer": False,
                                 "service_area_radius_miles": 45},
            business_hours={d: {"open": "07:00", "close": "18:00"} for d in
                            ["monday", "tuesday", "wednesday", "thursday", "friday"]}
                           | {"saturday": {"open": "08:00", "close": "14:00"},
                              "sunday": {"open": None, "close": None}},
            service_area={"center": {"lat": co["lat"], "lon": co["lon"]},
                          "radius_miles": 45, "primary_city": co["city"],
                          "state": co["state"]},
            industry=co["industry"], primary_services=co["services"],
            version=RNG.randrange(2, 6), is_active=True,
            created_at=co_created, updated_at=NOW - timedelta(days=RNG.randrange(1, 30)))

        # ---------------- users ----------------
        used_names = set()

        def new_name():
            while True:
                fn, ln = pick(FIRST_NAMES), pick(LAST_NAMES)
                if (fn, ln) not in used_names:
                    used_names.add((fn, ln))
                    return fn, ln

        pw = get_password_hash(DEMO_PASSWORD)
        execs, csrs, reps = [], [], []

        fn, ln = new_name()
        owner_id = uuid4()
        add("users", id=owner_id, email=f"{fn.lower()}.{ln.lower()}@{co['domain']}",
            password_hash=pw, role="executive", is_active=True, first_name=fn, last_name=ln,
            company_id=cid, created_at=co_created,
            extra_metadata={"title": "Owner / General Manager", "seat": "admin",
                            "notifications": {"daily_digest": True, "nudges": True}})
        execs.append({"id": owner_id, "name": f"{fn} {ln}", "role": "executive"})

        for _ in range(co["n_csr"]):
            fn, ln = new_name()
            uid = uuid4()
            add("users", id=uid, email=f"{fn.lower()}.{ln.lower()}@{co['domain']}",
                password_hash=pw, role="csr", is_active=maybe(0.93), first_name=fn, last_name=ln,
                company_id=cid, created_at=co_created + timedelta(days=RNG.randrange(1, 120)),
                extra_metadata={"title": "Customer Service Representative",
                                "shift": pick(["7am-4pm", "8am-5pm", "9am-6pm"]),
                                "seat": "standard"})
            csrs.append({"id": uid, "name": f"{fn} {ln}", "role": "csr"})

        for _ in range(co["n_rep"]):
            fn, ln = new_name()
            uid = uuid4()
            add("users", id=uid, email=f"{fn.lower()}.{ln.lower()}@{co['domain']}",
                password_hash=pw, role="sales_rep", is_active=maybe(0.95), first_name=fn, last_name=ln,
                company_id=cid, created_at=co_created + timedelta(days=RNG.randrange(1, 150)),
                extra_metadata={"title": pick(["Project Consultant", "Comfort Advisor",
                                               "Sales Representative", "Senior Estimator"]),
                                "seat": "standard",
                                "territory": pick(["North", "South", "East", "West", "Metro"])})
            reps.append({"id": uid, "name": f"{fn} {ln}", "role": "sales_rep"})

            rp_id = uuid4()
            verified = maybe(0.85)
            add("rep_phones", id=rp_id, user_id=uid, phone_number=phone(co["area"]),
                is_verified=verified, is_primary=True,
                verification_code=None if verified else f"{RNG.randrange(100000, 999999)}",
                verification_expires_at=None if verified else NOW + timedelta(minutes=10),
                verified_at=NOW - timedelta(days=RNG.randrange(5, 200)) if verified else None,
                expo_push_token=f"ExponentPushToken[{uuid4().hex[:22]}]" if maybe(0.7) else None,
                extra_metadata={"device": pick(["iPhone 15", "iPhone 14 Pro", "Pixel 8", "Galaxy S24"])},
                created_at=co_created + timedelta(days=RNG.randrange(1, 150)))

        staff = execs + csrs + reps

        # ---------------- invitations ----------------
        for _ in range(RNG.randrange(2, 5)):
            fn2, ln2 = new_name()
            status = RNG.choices(["pending", "accepted", "expired"], weights=[5, 3, 2])[0]
            created = NOW - timedelta(days=RNG.randrange(1, 90))
            add("invitations", id=uuid4(),
                email=f"{fn2.lower()}.{ln2.lower()}@{co['domain']}", company_id=cid,
                inviter_id=owner_id, token=uuid4().hex + uuid4().hex[:8],
                role=pick(["csr", "sales_rep"]), status=status,
                expires_at=created + timedelta(days=7), created_at=created,
                accepted_at=created + timedelta(hours=RNG.randrange(1, 70)) if status == "accepted" else None)

        # ---------------- proxy numbers ----------------
        proxy_pool = []
        for i in range(max(4, co["n_rep"] + 2)):
            pid = uuid4()
            proxy_pool.append(pid)
            add("proxy_numbers", id=pid, company_id=cid, phone_number=phone(co["area"]),
                twilio_sid="PN" + uuid4().hex[:30], friendly_name=f"{co['city']} Proxy {i + 1}",
                is_active=True, is_assigned=False, capabilities_sms=True, capabilities_voice=True,
                region=co["state"], last_released_at=None,
                extra_metadata={"pool": "primary", "purchased_at": (co_created + timedelta(days=30)).isoformat()},
                created_at=co_created + timedelta(days=30))

        # ---------------- leads & journeys ----------------
        statuses = [s for s, w in STATUS_FUNNEL for _ in range(w)]
        proxy_used: set[tuple] = set()
        proxy_cursor = 0

        for _ in range(co["n_leads"]):
            status = pick(statuses)
            deal_status, pipeline = STATUS_MAP[status]

            fn, ln = pick(FIRST_NAMES), pick(LAST_NAMES)
            cust = f"{fn} {ln}"
            cc_id = uuid4()
            cust_phone = phone(co["area"])
            addr = f"{RNG.randrange(100, 9999)} {pick(STREETS)}"
            lat = co["lat"] + RNG.uniform(-0.28, 0.28)
            lon = co["lon"] + RNG.uniform(-0.32, 0.32)

            add("contact_cards", id=cc_id, company_id=cid, primary_phone=cust_phone,
                secondary_phone=phone(co["area"]) if maybe(0.22) else None,
                email=f"{fn.lower()}.{ln.lower()}{RNG.randrange(1, 99)}@{pick(['gmail.com', 'yahoo.com', 'outlook.com', 'icloud.com'])}"
                      if maybe(0.82) else None,
                first_name=fn, last_name=ln, address=addr, city=co["city"], state=co["state"],
                postal_code=str(RNG.randrange(80000, 80299) if co["state"] == "CO" else
                                RNG.randrange(85001, 85099) if co["state"] == "AZ" else
                                RNG.randrange(97201, 97299)),
                latitude=round(lat, 6), longitude=round(lon, 6),
                property_snapshot={
                    "year_built": RNG.randrange(1948, 2021),
                    "sqft": RNG.randrange(1050, 4600),
                    "stories": pick([1, 1, 2, 2, 3]),
                    "roof_type": pick(["Asphalt Shingle", "Tile", "Metal", "Flat/TPO"]),
                    "owner_occupied": maybe(0.88),
                    "est_value_usd": RNG.randrange(240000, 1150000),
                },
                extra_metadata={"do_not_text": maybe(0.06), "preferred_contact": pick(["phone", "text", "email"])})

            lead_id = uuid4()
            first_touch = RNG.uniform(2, HISTORY_DAYS)
            lead_created = biz_time(first_touch)
            source = pick(LEAD_SOURCES)
            rep = pick(reps)
            reason = pick(INTAKE_REASONS[co["industry"]])
            service = reason[1]

            assigned = rep["id"] if status not in ("new",) else (rep["id"] if maybe(0.4) else None)
            deal_size = None
            closed_at = None
            if status == "closed_won":
                deal_size = round(RNG.uniform(*co["deal_range"]), 2)
                closed_at = lead_created + timedelta(days=RNG.uniform(3, 40))
            elif status == "closed_lost":
                closed_at = lead_created + timedelta(days=RNG.uniform(2, 35))
            elif status in ("qualified_booked",) and maybe(0.6):
                deal_size = round(RNG.uniform(*co["deal_range"]), 2)  # quoted, not closed

            if closed_at and closed_at > NOW:
                closed_at = NOW - timedelta(hours=RNG.randrange(1, 48))

            add("leads", id=lead_id, company_id=cid, contact_card_id=cc_id, status=status,
                deal_status=deal_status, pipeline_stage=pipeline, assigned_rep_id=assigned,
                deal_size=deal_size, closed_at=closed_at, lead_source=source,
                extra_metadata={"service_requested": service, "campaign": pick(
                    ["spring-storm-2026", "summer-tuneup", "evergreen", "brand-search", None]),
                    "first_touch_channel": "phone"},
                created_at=lead_created,
                updated_at=(closed_at or lead_created) + timedelta(hours=RNG.randrange(1, 60)))

            # The app sources sum_deal_value from closed_won leads bucketed by
            # closed_at (not from the appointment), so mirror that here.
            if status == "closed_won" and closed_at and assigned:
                k = (assigned, cid, month_key(closed_at))
                st = all_user_period_stats.setdefault(
                    k, {"won": 0, "resolved": 0, "value": 0.0, "no_show": 0})
                st["value"] += deal_size or 0.0

            # ---- inbound intake call ----
            csr = pick(csrs)
            n_obj = RNG.choices([0, 1, 2, 3], weights=[22, 38, 28, 12])[0]
            objs = sample(OBJECTIONS, n_obj)
            booked = status in ("qualified_booked", "closed_won", "closed_lost") or \
                (status == "hot" and maybe(0.3))
            is_missed = status in ("abandoned", "new") and maybe(0.45)
            svc_not_offered = status == "qualified_service_not_offered"
            if svc_not_offered:
                objs = list({*objs, "service_not_catered"})

            call_id = uuid4()
            dur = 0 if is_missed else RNG.randrange(65, 640)
            transcript = make_transcript(co, csr["name"], cust, reason, booked, objs, is_missed)
            scope = "out" if (svc_not_offered or maybe(0.06)) else "in"

            add("calls", id=call_id, company_id=cid, contact_card_id=cc_id, lead_id=lead_id,
                phone_number=cust_phone, call_type="missed_call" if is_missed else "csr_call",
                missed_call=is_missed, transcript=transcript,
                audio_url=None if is_missed else
                    f"https://otto-audio.s3.us-east-1.amazonaws.com/{cid}/calls/{call_id}.mp3",
                duration_seconds=dur, handled_by_user_id=None if is_missed else csr["id"],
                interaction_type="call",
                extra_metadata={"provider": co["voip"], "provider_call_id": uuid4().hex[:18],
                                "direction": "inbound", "ring_seconds": RNG.randrange(4, 30),
                                "recording_consent": True},
                created_at=lead_created,
                updated_at=lead_created + timedelta(minutes=RNG.randrange(2, 45)),
                answered_at=None if is_missed else lead_created + timedelta(seconds=RNG.randrange(3, 25)),
                answered_by_display=None if is_missed else csr["name"],
                lead_source=source, scope=scope)

            # ---- analysis for answered, in-scope calls ----
            analysis_id = None
            if not is_missed:
                done = SOP_ALL[:RNG.randrange(2, 7)]
                missed_stages = [s for s in SOP_ALL if s not in done]
                rate = round(len(done) / len(SOP_ALL), 3)
                sentiment = round(RNG.uniform(0.15, 0.95) if booked else RNG.uniform(-0.35, 0.7), 3)
                analysis_id = uuid4()

                q_score = round(RNG.uniform(0.55, 0.96) if status not in ("abandoned", "qualified_service_not_offered")
                                else RNG.uniform(0.08, 0.5), 3)
                add("call_analyses", id=analysis_id, call_id=call_id, company_id=cid,
                    status="completed",
                    qualification_status=("qualified" if q_score >= 0.62 else "unqualified")
                        if not svc_not_offered else "service_not_offered",
                    booking_status="booked" if booked else "not_booked",
                    objections=objs, objection_texts=[pick(OBJECTION_QUOTES.get(o, ["-"])) for o in objs],
                    objections_total_count=len(objs),
                    sop_stages_completed=done, sop_stages_missed=missed_stages,
                    sop_stages_total=len(SOP_ALL),
                    sop_compliance_score=round(rate * 100, 1), sop_compliance_rate=rate,
                    sop_compliance_confidence=round(RNG.uniform(0.72, 0.98), 3),
                    sop_compliance_issues=[SOP_ISSUES[i][0] for i in sample(range(len(SOP_ISSUES)), RNG.randrange(0, 3))],
                    sop_compliance_positive_behaviors=[SOP_STRENGTHS[i][0] for i in sample(range(len(SOP_STRENGTHS)), RNG.randrange(1, 4))],
                    compliance_target_role="csr", sentiment_score=sentiment,
                    summary=(f"{cust} called about {reason[0]}. "
                             + ("Appointment booked. " if booked else "No appointment set. ")
                             + (f"Raised {len(objs)} objection(s): {', '.join(objs)}. " if objs else "No objections raised. ")
                             + f"CSR {csr['name']} completed {len(done)} of {len(SOP_ALL)} SOP stages."),
                    key_points=[f"Service requested: {service}",
                                f"Property in {co['city']}, {co['state']}",
                                f"Lead source: {source}"] + ([f"Objection: {objs[0]}"] if objs else []),
                    action_items=(["Send confirmation text", "Add to route for assigned tech"] if booked
                                  else ["Follow up Tuesday morning", "Send pricing overview by email"]),
                    next_steps=(["Confirm 24h before appointment"] if booked
                                else ["Attempt second contact within 48 hours"]),
                    # Must be List[PendingActionDetail] - see app/domain/models/analysis.py
                    pending_actions=([] if booked else [{
                        "type": pick(["follow_up_call", "send_info", "callback"]),
                        "owner": "customer_rep",
                        "raw_text": f"Follow up with {cust} about the {service}.",
                        "due_at": (lead_created + timedelta(days=RNG.randrange(1, 6))).isoformat(),
                        "confidence": round(RNG.uniform(0.6, 0.97), 2),
                        "contact_method": pick(["phone", "sms", "email"]),
                    }]),
                    summary_confidence_score=round(RNG.uniform(0.7, 0.99), 3),
                    bant_need_score=round(RNG.uniform(0.3, 0.99), 3),
                    bant_budget_score=round(RNG.uniform(0.15, 0.95), 3),
                    bant_timeline_score=round(RNG.uniform(0.2, 0.98), 3),
                    bant_authority_score=round(RNG.uniform(0.25, 0.99), 3),
                    qualification_overall_score=q_score,
                    qualification_confidence_score=round(RNG.uniform(0.65, 0.97), 3),
                    call_outcome_category=("appointment_booked" if booked else
                                           "service_not_offered" if svc_not_offered else
                                           pick(["callback_requested", "price_shopping", "info_only", "no_answer_followup"])),
                    appointment_confirmed=booked,
                    appointment_date=(lead_created + timedelta(days=RNG.randrange(1, 12))) if booked else None,
                    appointment_type=pick(["in_home_estimate", "diagnostic_visit", "inspection"]) if booked else None,
                    appointment_timezone=co["tz"] if booked else None,
                    appointment_time_confidence=round(RNG.uniform(0.8, 0.99), 3) if booked else None,
                    preferred_time_window=pick(["9am-11am", "2pm-4pm", "8am-10am", "Anytime weekday"]),
                    appointment_intent="schedule" if booked else pick(["undecided", "shopping", "none"]),
                    original_appointment_datetime=None, new_requested_time=None,
                    service_requested=service,
                    service_not_offered_reason=pick(co["not_offered"]) if svc_not_offered else None,
                    service_address_raw=f"{addr}, {co['city']}, {co['state']}",
                    service_address_structured={"street": addr, "city": co["city"],
                                                "state": co["state"], "country": "US"},
                    address_confidence=round(RNG.uniform(0.7, 0.99), 3),
                    customer_name=cust, customer_name_confidence=round(RNG.uniform(0.8, 0.99), 3),
                    decision_makers=[cust] + ([f"{pick(FIRST_NAMES)} {ln}"] if maybe(0.3) else []),
                    urgency_signals=sample(["active leak", "no cooling", "no hot water",
                                            "insurance deadline", "closing on house",
                                            "guests arriving"], RNG.randrange(0, 3)),
                    budget_indicators=sample(["mentioned financing", "cash buyer",
                                              "insurance claim", "comparing 3 bids",
                                              "price sensitive"], RNG.randrange(0, 3)),
                    follow_up_required=not booked,
                    follow_up_reason=None if booked else pick(
                        ["Customer needs to consult spouse", "Waiting on insurance adjuster",
                         "Comparing competitor bids", "Requested callback next week"]),
                    detected_call_type="csr_call", is_existing_customer=maybe(0.18),
                    is_deprioritized=svc_not_offered or maybe(0.05),
                    service_wait_time_weeks=RNG.randrange(0, 5) if maybe(0.3) else None,
                    applied_rules=sample(["require_address", "service_area_radius_miles",
                                          "min_call_duration_seconds", "auto_qualify_hot"],
                                         RNG.randrange(1, 4)),
                    property_details={"year_built": RNG.randrange(1950, 2020),
                                      "stories": pick([1, 2]), "sqft": RNG.randrange(1100, 4200)},
                    customer_details={"name": cust, "phone": cust_phone,
                                      "preferred_contact": pick(["phone", "text"])},
                    scope=scope,
                    raw_analysis={"model": "otto-intel-v5.9", "version": "5.9.2",
                                  "tokens": RNG.randrange(1800, 9000),
                                  "latency_ms": RNG.randrange(900, 6400)},
                    extra_metadata={"reprocessed": maybe(0.1)},
                    created_at=lead_created + timedelta(minutes=RNG.randrange(3, 25)),
                    updated_at=lead_created + timedelta(minutes=RNG.randrange(26, 90)))

                for o in objs:
                    add("call_objection_details", id=uuid4(), call_analysis_id=analysis_id,
                        call_id=call_id, company_id=cid, user_id=csr["id"],
                        category_id=OBJECTION_IDS[o], category_text=o.replace("_", " ").title(),
                        objection_text=pick(OBJECTION_QUOTES.get(o, ["-"])),
                        overcome=booked or maybe(0.35),
                        severity=RNG.choices(["low", "medium", "high"], weights=[3, 5, 2])[0],
                        confidence_score=round(RNG.uniform(0.6, 0.98), 3),
                        created_at=lead_created + timedelta(minutes=RNG.randrange(5, 30)))

                for i in sample(range(len(SOP_ISSUES)), RNG.randrange(0, 3)):
                    issue, why, fix, ex, metric = SOP_ISSUES[i]
                    add("coaching_issues", id=uuid4(), call_analysis_id=analysis_id,
                        call_id=call_id, company_id=cid, user_id=csr["id"], issue=issue,
                        severity=RNG.choices(["low", "medium", "high", "critical"],
                                             weights=[3, 5, 3, 1])[0],
                        why_it_matters=why, how_to_fix=fix, example_language=ex,
                        transcript_evidence=(transcript or "").split("\n")[RNG.randrange(0, 6)]
                            if transcript else None,
                        related_sop_metric=metric,
                        created_at=lead_created + timedelta(minutes=RNG.randrange(5, 40)))

                for i in sample(range(len(SOP_STRENGTHS)), RNG.randrange(1, 4)):
                    beh, why, metric = SOP_STRENGTHS[i]
                    add("coaching_strengths", id=uuid4(), call_analysis_id=analysis_id,
                        call_id=call_id, company_id=cid, user_id=csr["id"], behavior=beh,
                        why_effective=why,
                        transcript_evidence=(transcript or "").split("\n")[0] if transcript else None,
                        related_sop_metric=metric,
                        created_at=lead_created + timedelta(minutes=RNG.randrange(5, 40)))

                # processing job for a subset
                if maybe(0.55):
                    jstatus = RNG.choices(["completed", "completed", "completed", "processing", "failed"],
                                          weights=[6, 6, 6, 1, 1])[0]
                    started = lead_created + timedelta(minutes=2)
                    add("call_processing_jobs", id=uuid4(), company_id=cid, call_id=call_id,
                        shunya_job_id="job_" + uuid4().hex[:20], status=jstatus,
                        progress_percent=100 if jstatus == "completed" else
                            (RNG.randrange(20, 90) if jstatus == "processing" else RNG.randrange(10, 70)),
                        current_step=None if jstatus == "completed" else
                            pick(["transcription", "diarization", "analysis", "rag_indexing"]),
                        steps_completed=["ingest", "transcription", "diarization", "analysis", "summary"]
                            if jstatus == "completed" else ["ingest", "transcription"],
                        steps_remaining=[] if jstatus == "completed" else ["analysis", "summary"],
                        steps_failed=["analysis"] if jstatus == "failed" else [],
                        started_at=started,
                        completed_at=started + timedelta(seconds=RNG.randrange(40, 400))
                            if jstatus == "completed" else None,
                        failed_at=started + timedelta(seconds=RNG.randrange(20, 200))
                            if jstatus == "failed" else None,
                        estimated_completion=started + timedelta(minutes=5),
                        duration_seconds=RNG.randrange(40, 400) if jstatus == "completed" else None,
                        summary_url=f"https://otto-artifacts.s3.us-east-1.amazonaws.com/{call_id}/summary.json"
                            if jstatus == "completed" else None,
                        chunks_url=f"https://otto-artifacts.s3.us-east-1.amazonaws.com/{call_id}/chunks.json"
                            if jstatus == "completed" else None,
                        transcript_url=f"https://otto-artifacts.s3.us-east-1.amazonaws.com/{call_id}/transcript.json"
                            if jstatus == "completed" else None,
                        job_metadata={"engine": "deepgram-nova-3", "language": "en-US",
                                      "speakers": 2},
                        error={"code": "ANALYSIS_TIMEOUT", "message": "Model call exceeded 60s budget"}
                            if jstatus == "failed" else None,
                        retry_available=jstatus == "failed", retry_attempt=1 if jstatus == "failed" else 0,
                        original_job_id=None, skip_rag_indexing=False, skip_summary_generation=False,
                        priority=RNG.choices(["normal", "high", "low"], weights=[8, 2, 1])[0],
                        extra_metadata={"queue": "default"},
                        created_at=lead_created + timedelta(minutes=1),
                        updated_at=lead_created + timedelta(minutes=8))

            # ---- status history chain ----
            chain = ["new"]
            if status != "new":
                if pipeline in ("qualified", "booked", "won", "lost", "appointment", "appointment_ran"):
                    chain.append("warm")
                if status in ("hot", "qualified_booked", "closed_won", "closed_lost"):
                    chain.append("hot")
                chain.append(status)
            prev = None
            t_cursor = lead_created
            for s in chain:
                if prev == s:
                    continue
                t_cursor += timedelta(hours=RNG.uniform(1, 96))
                if t_cursor > NOW:
                    t_cursor = NOW - timedelta(minutes=RNG.randrange(5, 600))
                add("lead_status_changes", id=uuid4(), lead_id=lead_id, company_id=cid,
                    changed_by_user_id=(csr["id"] if s in ("new", "warm") else (assigned or rep["id"])),
                    old_status=prev, new_status=s,
                    old_deal_status=STATUS_MAP.get(prev, (None, None))[0] if prev else None,
                    new_deal_status=STATUS_MAP[s][0],
                    reason=pick(["Auto-set from call analysis", "Rep updated after site visit",
                                 "Customer requested callback", "Contract signed",
                                 "Lost to competitor pricing", "No contact after 3 attempts",
                                 "Qualified during intake call", None]),
                    created_at=t_cursor)
                prev = s

            # ---- appointment ----
            appt_id = None
            if booked or status in ("closed_won", "closed_lost"):
                past = status in ("closed_won", "closed_lost") or maybe(0.55)
                if past:
                    # Must land strictly between the intake call and now.
                    earliest = lead_created + timedelta(hours=6)
                    latest = NOW - timedelta(hours=3)
                    if earliest >= latest:
                        earliest = latest - timedelta(hours=2)
                    sched = earliest + timedelta(
                        seconds=RNG.uniform(0, (latest - earliest).total_seconds()))
                else:
                    sched = NOW + timedelta(days=RNG.uniform(0.5, 18))
                sched = sched.replace(hour=pick([8, 9, 10, 11, 13, 14, 15, 16]),
                                      minute=pick([0, 30]), second=0, microsecond=0)
                # Snapping to a business hour can cross back over either boundary.
                if sched <= lead_created:
                    sched += timedelta(days=1)
                if past and sched > NOW:
                    sched -= timedelta(days=1)

                if status == "closed_won":
                    outcome = "won"
                elif status == "closed_lost":
                    outcome = RNG.choices(["lost", "no_show"], weights=[8, 2])[0]
                elif not past:
                    outcome = "pending"
                else:
                    outcome = RNG.choices(["pending", "rescheduled", "no_show"], weights=[5, 3, 2])[0]

                appt_id = uuid4()
                a_done = SOP_ALL[:RNG.randrange(3, 7)]
                a_missed = [s for s in SOP_ALL if s not in a_done]
                a_objs = sample(OBJECTIONS, RNG.randrange(0, 3))
                has_recording = past and outcome in ("won", "lost") and maybe(0.75)
                a_trans = make_sales_transcript(co, rep["name"], cust, service, outcome) if has_recording else None

                add("appointments", id=appt_id, company_id=cid, lead_id=lead_id,
                    contact_card_id=cc_id, scheduled_start=sched,
                    scheduled_end=sched + timedelta(minutes=pick([60, 90, 120])),
                    location_address=f"{addr}, {co['city']}, {co['state']}",
                    latitude=round(lat, 6), longitude=round(lon, 6), outcome=outcome,
                    assigned_rep_id=assigned or rep["id"], interaction_id=call_id,
                    audio_url=f"https://otto-audio.s3.us-east-1.amazonaws.com/{cid}/appts/{appt_id}.mp3"
                        if has_recording else None,
                    transcript=a_trans,
                    duration_seconds=RNG.randrange(1500, 5400) if has_recording else None,
                    summary=(f"In-home {service} consultation with {cust}. Outcome: {outcome}."
                             + (f" Deal value ${deal_size:,.0f}." if deal_size and outcome == "won" else ""))
                        if past else None,
                    objections=a_objs,
                    objection_texts=[pick(OBJECTION_QUOTES.get(o, ["-"])) for o in a_objs],
                    objections_total_count=len(a_objs),
                    qualification_status="qualified", booking_status="booked",
                    handled_by_user_id=assigned or rep["id"],
                    extra_metadata={"crm_job_id": str(RNG.randrange(100000, 999999)),
                                    "confirmed_24h": maybe(0.8),
                                    "reminder_sent": maybe(0.85)},
                    sop_stages_completed=a_done, sop_stages_missed=a_missed,
                    sop_stages_total=len(SOP_ALL),
                    sop_compliance_score=round(len(a_done) / len(SOP_ALL) * 100, 1),
                    sop_compliance_rate=round(len(a_done) / len(SOP_ALL), 3),
                    sop_compliance_confidence=round(RNG.uniform(0.7, 0.97), 3),
                    sop_compliance_issues=[SOP_ISSUES[i][0] for i in sample(range(len(SOP_ISSUES)), RNG.randrange(0, 3))],
                    sop_compliance_positive_behaviors=[SOP_STRENGTHS[i][0] for i in sample(range(len(SOP_STRENGTHS)), RNG.randrange(1, 3))],
                    compliance_target_role="sales_rep",
                    sentiment_score=round(RNG.uniform(0.4, 0.95) if outcome == "won"
                                          else RNG.uniform(-0.4, 0.55), 3),
                    key_points=[f"Service: {service}", f"Rep: {rep['name']}",
                                f"Outcome: {outcome}"],
                    action_items=(["Submit signed contract to ops", "Order materials"]
                                  if outcome == "won" else
                                  ["Send itemized quote by email", "Follow up in 3 days"]),
                    next_steps=(["Schedule install crew"] if outcome == "won"
                                else ["Re-engage in 30-day nurture"]),
                    pending_actions_data={"count": 1, "primary": "follow_up"} if outcome != "won" else {"count": 0},
                    recording_status="available" if has_recording else ("none" if not past else "pending"),
                    analysis_status="completed" if has_recording else "not_started",
                    shunya_job_id=("job_" + uuid4().hex[:20]) if has_recording else None,
                    created_at=lead_created + timedelta(hours=RNG.randrange(1, 20)),
                    updated_at=sched + timedelta(hours=RNG.randrange(1, 40)) if past else None)

                # Leaderboard accumulation, using the same definitions as
                # LeaderboardRepository.recalculate_stats: total_resolved counts
                # won + lost + no_show, bucketed by the appointment month.
                if outcome in ("won", "lost", "no_show"):
                    k = ((assigned or rep["id"]), cid, month_key(sched))
                    st = all_user_period_stats.setdefault(
                        k, {"won": 0, "resolved": 0, "value": 0.0, "no_show": 0})
                    st["resolved"] += 1
                    if outcome == "won":
                        st["won"] += 1
                    elif outcome == "no_show":
                        st["no_show"] += 1

                # posts on some appointments
                if past and maybe(0.16):
                    add("posts", id=uuid4(), appointment_id=appt_id,
                        poster_id=pick(staff)["id"],
                        note=pick([
                            "Great agenda-setting on this one - worth listening to the first three minutes.",
                            "Textbook objection handling around the financing question at 14:20.",
                            "Homeowner brought up the competitor quote twice; nice recovery.",
                            "Sharing this as the reference call for the new hires.",
                            "Watch how the close is framed here - two options, no open-ended ask.",
                        ]),
                        tags=pick(["agenda_setting", "objection_handling", None]),
                        likes=RNG.randrange(0, 14),
                        created_at=sched + timedelta(days=RNG.randrange(1, 6)),
                        updated_at=None)

            # ---- sales / follow-up calls ----
            for _ in range(RNG.choices([0, 1, 2, 3], weights=[38, 34, 20, 8])[0]):
                fc_id = uuid4()
                fdays = max(0.2, first_touch - RNG.uniform(0.5, first_touch * 0.9))
                fdt = biz_time(fdays)
                is_sales = booked and maybe(0.5)
                fmissed = maybe(0.18)
                add("calls", id=fc_id, company_id=cid, contact_card_id=cc_id, lead_id=lead_id,
                    phone_number=cust_phone,
                    call_type="missed_call" if fmissed else ("sales_call" if is_sales else "csr_call"),
                    missed_call=fmissed,
                    transcript=None if fmissed else make_transcript(
                        co, (rep if is_sales else csr)["name"], cust, reason, maybe(0.3),
                        sample(OBJECTIONS, RNG.randrange(0, 2))),
                    audio_url=None if fmissed else
                        f"https://otto-audio.s3.us-east-1.amazonaws.com/{cid}/calls/{fc_id}.mp3",
                    duration_seconds=0 if fmissed else RNG.randrange(40, 480),
                    handled_by_user_id=None if fmissed else (rep["id"] if is_sales else csr["id"]),
                    interaction_type="call",
                    extra_metadata={"provider": co["voip"], "direction": pick(["outbound", "inbound"]),
                                    "provider_call_id": uuid4().hex[:18]},
                    created_at=fdt, updated_at=fdt + timedelta(minutes=5),
                    answered_at=None if fmissed else fdt + timedelta(seconds=RNG.randrange(3, 20)),
                    answered_by_display=None if fmissed else (rep if is_sales else csr)["name"],
                    lead_source=source, scope="in")

            # ---- pending actions / action items ----
            n_actions = RNG.choices([0, 1, 2], weights=[35, 45, 20])[0]
            for _ in range(n_actions):
                atype = pick(["follow_up", "call_back", "send_quote", "appointment_reminder", "rehash"])
                astatus = RNG.choices(["pending", "in_progress", "completed", "cancelled", "converted"],
                                      weights=[9, 3, 7, 2, 2])[0]
                due = NOW + timedelta(days=RNG.uniform(-25, 16))
                owner = assigned or rep["id"]
                pa_id = uuid4()
                common = dict(
                    company_id=cid, lead_id=lead_id, call_id=call_id, appointment_id=appt_id,
                    action_type=atype,
                    raw_text=pick([
                        f"Call {cust} back Tuesday morning about the {service}.",
                        f"Email the itemized quote to {cust}.",
                        f"Confirm the appointment window with {cust} 24 hours ahead.",
                        f"Re-engage {cust} - went quiet after the estimate.",
                        f"Check whether {cust}'s insurance adjuster has been out yet.",
                    ]),
                    status=astatus, due_at=due,
                    priority=RNG.choices([1, 2, 3], weights=[3, 5, 3])[0],
                    owner_id=owner, assigned_by_id=pick(staff)["id"],
                    source=RNG.choices(["shunya", "manual", "system"], weights=[7, 2, 2])[0],
                    extra_metadata={"generated_by": "otto-intel-v5.9",
                                    "channel": pick(["phone", "sms", "email"])},
                    created_at=lead_created + timedelta(hours=RNG.randrange(1, 48)),
                    updated_at=NOW - timedelta(days=RNG.uniform(0, 12)))
                add("pending_actions", id=pa_id, **common)
                if maybe(0.55):
                    add("action_items", id=uuid4(), **common)

                # ---- follow-up otto messages ----
                if atype in ("follow_up", "rehash") and maybe(0.5):
                    q = "appointment_ran" if appt_id else "qualified_unbooked"
                    fstatus = RNG.choices(["sent", "pending", "proposed", "scheduled", "failed", "dormant"],
                                          weights=[8, 4, 3, 3, 1, 1])[0]
                    sched_at = NOW + timedelta(days=RNG.uniform(-20, 10))
                    if fstatus == "sent":
                        # A delivered message cannot be scheduled for the future.
                        sched_at = NOW - timedelta(days=RNG.uniform(0.2, 20))
                    is_rep_nudge = maybe(0.35)
                    add("follow_up_otto", id=uuid4(), lead_id=lead_id, company_id=cid,
                        message_content=(
                            f"Hi {fn}, it's {rep['name']} with {co['name']}. Just circling back on the "
                            f"{service} we talked about - happy to answer anything that came up. "
                            f"Want me to hold a slot this week?"
                            if not is_rep_nudge else
                            f"{rep['name']}: {cust} has gone quiet since the {service} estimate. "
                            f"Last contact was {RNG.randrange(4, 21)} days ago. Recommend a call today."),
                        action_type="nudge_sales_rep" if is_rep_nudge else "sms_to_lead",
                        opening_line=(f"Lead the call by referencing the {service} scope you walked "
                                      f"through on site.") if is_rep_nudge else None,
                        objections=[{"objection": o.replace("_", " "),
                                     "suggested_response": pick(_objection_response(o, co))}
                                    for o in (objs[:2] or ["customer_needs_time_to_decide"])]
                            if is_rep_nudge else None,
                        key_talking_points=[
                            "Estimate is valid for 30 days",
                            "Financing available at 0% for 12 months",
                            f"Crew availability opens up in {RNG.randrange(1, 4)} weeks",
                        ] if is_rep_nudge else None,
                        close_approach=("Offer two concrete windows rather than asking if they're "
                                        "still interested.") if is_rep_nudge else None,
                        external_message_id=("SM" + uuid4().hex[:30]) if fstatus == "sent" else None,
                        pending_action_id=pa_id,
                        scheduled_at=sched_at,
                        sent_at=sched_at if fstatus == "sent" and sched_at <= NOW else None,
                        status=fstatus,
                        error_message="Twilio 21610: recipient has opted out"
                            if fstatus == "failed" else None,
                        ai_reasoning={
                            "why_now": pick([
                                "Lead has been silent for 9 days following a completed estimate.",
                                "Third attempt in cadence; prior two went unanswered.",
                                "Appointment ran but no decision was recorded.",
                            ]),
                            "confidence": round(RNG.uniform(0.6, 0.95), 2),
                            "signals": sample(["no_reply_7d", "estimate_delivered", "high_deal_value",
                                               "competitor_mentioned", "seasonal_urgency"], 2),
                        },
                        queue_type=q, attempt_number=RNG.randrange(1, 4),
                        assigned_rep_id=owner,
                        created_at=sched_at - timedelta(days=RNG.uniform(0.2, 3)),
                        updated_at=None)

            # ---- masked communications (proxy) ----
            if appt_id and maybe(0.45):
                key = (lead_id, assigned or rep["id"])
                if key not in proxy_used:
                    proxy_used.add(key)
                    pn_id = proxy_pool[proxy_cursor % len(proxy_pool)]
                    proxy_cursor += 1
                    sess_id = uuid4()
                    s_status = "closed" if status in ("closed_won", "closed_lost") else "active"
                    rep_ph = phone(co["area"])
                    proxy_ph = next(r["phone_number"] for r in ROWS["proxy_numbers"] if r["id"] == pn_id)
                    s_created = lead_created + timedelta(hours=RNG.randrange(2, 30))
                    add("proxy_sessions", id=sess_id, company_id=cid, lead_id=lead_id,
                        rep_user_id=assigned or rep["id"], proxy_number_id=pn_id,
                        homeowner_phone=cust_phone, rep_phone=rep_ph, status=s_status,
                        closed_reason=("deal_won" if status == "closed_won" else
                                       "deal_lost" if status == "closed_lost" else None),
                        extra_metadata={"opened_by": "system", "trigger": "appointment_booked"},
                        created_at=s_created,
                        closed_at=closed_at if s_status == "closed" else None,
                        updated_at=None)

                    for i in range(RNG.randrange(2, 7)):
                        ctype = RNG.choices(["sms", "call"], weights=[7, 3])[0]
                        homeowner_first = maybe(0.45)
                        direction = "homeowner_to_rep" if homeowner_first else "rep_to_homeowner"
                        mdt = s_created + timedelta(hours=RNG.uniform(1, 200))
                        if mdt > NOW:
                            mdt = NOW - timedelta(hours=RNG.uniform(1, 40))
                        add("masked_communications", id=uuid4(), session_id=sess_id,
                            company_id=cid, lead_id=lead_id, comm_type=ctype, direction=direction,
                            from_number=cust_phone if homeowner_first else rep_ph,
                            to_number=proxy_ph, proxy_number=proxy_ph,
                            twilio_call_sid=("CA" + uuid4().hex[:30]) if ctype == "call" else None,
                            duration_seconds=RNG.randrange(20, 700) if ctype == "call" else None,
                            call_status=pick(["completed", "completed", "no-answer", "busy"])
                                if ctype == "call" else None,
                            recording_url=(f"https://api.twilio.com/2010-04-01/Recordings/RE{uuid4().hex[:30]}")
                                if ctype == "call" and maybe(0.6) else None,
                            recording_sid=("RE" + uuid4().hex[:30]) if ctype == "call" and maybe(0.6) else None,
                            audio_url=None, call_id=None,
                            twilio_message_sid=("SM" + uuid4().hex[:30]) if ctype == "sms" else None,
                            message_body=(pick([
                                "Hi, this is about the estimate from yesterday - is the price negotiable at all?",
                                "Running about 10 minutes late, sorry!",
                                "Can we move Thursday to Friday morning instead?",
                                "Just sent the signed contract over, let me know you got it.",
                                "Do I need to move the cars out of the driveway?",
                                "Thanks for coming out today, we'll talk it over tonight.",
                                "Following up on the quote - any questions I can answer?",
                            ]) if ctype == "sms" else None),
                            extra_metadata={"twilio_status": "delivered" if ctype == "sms" else "completed"},
                            is_homeowner_reply=homeowner_first,
                            source_metadata={"webhook": "twilio", "received_at": mdt.isoformat()},
                            intent_label=pick(["pricing_question", "reschedule_request",
                                               "confirmation", "logistics", "decision_pending",
                                               "positive_signal"]) if ctype == "sms" else None,
                            confidence_score=round(RNG.uniform(0.55, 0.97), 3) if ctype == "sms" else None,
                            created_at=mdt)

        # ---------------- coaching sessions ----------------
        coach_sessions = []
        for r in csrs + reps:
            for cyc in range(1, RNG.randrange(2, 4)):
                sid = uuid4()
                coached = NOW - timedelta(days=RNG.uniform(5, 150))
                fdays = pick([14, 21, 30])
                ended = coached + timedelta(days=fdays)
                complete = ended < NOW
                improved = maybe(0.62) if complete else None
                pct = round(RNG.uniform(-14, 38), 2) if complete else None
                focus = sample(["greeting", "qualification", "objection_handling", "close",
                                "follow_up", "booking_rate", "call_control"], RNG.randrange(1, 4))
                base = {f: round(RNG.uniform(38, 72), 1) for f in focus}
                add("coaching_sessions", id=sid, company_id=cid, rep_user_id=r["id"],
                    coach_user_id=owner_id, focus_areas=focus,
                    targets={f: round(base[f] + RNG.uniform(8, 22), 1) for f in focus},
                    baseline_scores=base,
                    status="completed" if complete else "in_progress",
                    follow_up_days=fdays,
                    follow_up_end_date=ended,
                    impact_scores={f: round(base[f] + RNG.uniform(-6, 26), 1) for f in focus}
                        if complete else None,
                    overall_improved=improved, improvement_pct=pct,
                    targets_met={f: maybe(0.55) for f in focus} if complete else None,
                    notes=pick([
                        "Strong rapport, but consistently skips the read-back on callback numbers.",
                        "Booking rate is fine; the gap is in handling the 'need to think about it' objection.",
                        "Reviewed three calls together. Agreed to run the two-option close on every intake.",
                        "Follow-up discipline improved a lot this cycle. Next focus is pricing conversations.",
                        None,
                    ]),
                    coached_at=coached, created_at=coached,
                    updated_at=ended if complete else None,
                    cycle_number=cyc, parent_session_id=None,
                    auto_created=maybe(0.3))
                coach_sessions.append((sid, r, coached))

        # link cycle 2+ sessions to their predecessor
        by_rep: dict = {}
        for sid, r, coached in coach_sessions:
            by_rep.setdefault(r["id"], []).append((sid, coached))
        for uid, lst in by_rep.items():
            lst.sort(key=lambda x: x[1])
            for i in range(1, len(lst)):
                for row in ROWS["coaching_sessions"]:
                    if row["id"] == lst[i][0]:
                        row["parent_session_id"] = lst[i - 1][0]

        # ---------------- smart nudges ----------------
        nudge_specs = [
            ("critical_decline", "critical", "Booking rate dropped sharply",
             "booking_rate", -1),
            ("metric_decline", "high", "SOP compliance slipping", "sop_compliance_rate", -1),
            ("metric_improvement", "positive", "Objection handling improving",
             "objection_overcome_rate", 1),
            ("recurring_issue", "high", "Same coaching issue for the third week",
             "callback_number_capture", -1),
            ("objection_weakness", "high", "Struggling with price objections",
             "price_objection_overcome_rate", -1),
            ("coaching_target_met", "positive", "Coaching target reached",
             "close_rate", 1),
            ("cycle_summary", "medium", "Coaching cycle wrapped up", None, 0),
        ]
        company_calls = [r["id"] for r in ROWS["calls"] if r["company_id"] == cid]
        for r in csrs + reps:
            for _ in range(RNG.randrange(1, 4)):
                ntype, prio, title, metric, direction = pick(nudge_specs)
                prev_v = round(RNG.uniform(28, 78), 1) if metric else None
                if metric:
                    delta = RNG.uniform(6, 26) * (1 if direction > 0 else -1)
                    curr_v = round(max(0.0, min(100.0, prev_v + delta)), 1)
                    change = round(((curr_v - prev_v) / prev_v) * 100, 1) if prev_v else None
                else:
                    curr_v = change = None
                src_session = pick([s[0] for s in coach_sessions if s[1]["id"] == r["id"]] or [None])
                nid = uuid4()
                created = NOW - timedelta(days=RNG.uniform(0.5, 45))
                add("smart_nudges", id=nid, company_id=cid, rep_user_id=r["id"],
                    rep_name=r["name"], nudge_type=ntype, priority=prio,
                    title=f"{r['name']}: {title}",
                    message=(
                        f"{r['name']}'s {metric.replace('_', ' ')} moved from {prev_v}% to {curr_v}% "
                        f"over the last two weeks ({change:+.1f}%). "
                        + ("Worth a conversation this week." if direction < 0
                           else "Worth recognising in the team huddle.")
                        if metric else
                        f"The {RNG.randrange(14, 31)}-day coaching cycle for {r['name']} has closed. "
                        f"Review the impact scores and decide whether to open another cycle."),
                    metric_name=metric, previous_value=prev_v, current_value=curr_v,
                    change_pct=change,
                    window_description=pick(["Last 14 days vs prior 14", "This week vs last week",
                                             "Cycle to date"]),
                    source_call_ids=[str(c) for c in sample(company_calls, RNG.randrange(1, 4))],
                    source_session_id=src_session,
                    extra_data={"sample_size": RNG.randrange(8, 60),
                                "statistically_significant": maybe(0.6)},
                    fingerprint=fingerprint(r["id"], ntype, metric or "", RNG.randrange(1, 5)),
                    created_at=created,
                    expires_at=created + timedelta(days=30))

                for u in sample(execs + [x for x in reps if x["id"] != r["id"]], RNG.randrange(0, 3)):
                    read_at = created + timedelta(hours=RNG.uniform(1, 90))
                    if read_at > NOW:
                        read_at = NOW - timedelta(minutes=RNG.randrange(5, 500))
                    st = RNG.choices(["read", "dismissed"], weights=[7, 3])[0]
                    add("smart_nudge_reads", id=uuid4(), nudge_id=nid, user_id=u["id"],
                        status=st, read_at=read_at,
                        dismissed_at=read_at + timedelta(minutes=RNG.randrange(1, 200))
                            if st == "dismissed" else None)

        # ---------------- ask otto ----------------
        QA = [
            ("Which reps had the biggest drop in booking rate this month?",
             "Across the last 30 days, two reps are trending down. The larger drop is roughly 14 "
             "points versus the prior period, concentrated in calls where a price objection came "
             "up in the first two minutes. The pattern is objection timing, not call volume - "
             "total intake calls are flat."),
            ("What are our top objections on unbooked calls?",
             "On unbooked calls the top three are: needing time to decide (about a third), "
             "scheduling conflicts, and service fee concerns. Fee concerns are the most "
             "recoverable - calls where the credit-back framing was used booked at a noticeably "
             "higher rate."),
            ("How many qualified leads never got a follow-up call?",
             "There is a cohort of qualified-but-unbooked leads with no outbound attempt logged "
             "after the intake call. Most are more than seven days old, which puts them past the "
             "window where re-contact usually converts."),
            ("Which lead source is producing the best close rate?",
             "Referral and repeat-customer leads close at the highest rate by a wide margin, "
             "though they are a small share of volume. Paid search drives the most volume but "
             "closes materially lower, and its cost per booked job is the highest of the set."),
            ("Summarize what went wrong on the calls we lost last week.",
             "The common thread is the close. In the majority of lost calls the SOP close stage "
             "was either skipped or reduced to an open-ended 'let me know'. Where two concrete "
             "time windows were offered instead, the outcome flipped more often than not."),
            ("Are we missing calls outside business hours?",
             "Yes - a meaningful share of missed calls land between 6pm and 8pm on weekdays and "
             "Saturday mornings. Those callers rarely appear again in the data, which suggests "
             "they are reaching a competitor rather than calling back."),
        ]
        for _ in range(RNG.randrange(4, 9)):
            conv_id = uuid4()
            u = pick(execs + reps)
            started = NOW - timedelta(days=RNG.uniform(0.2, 60))
            q, a = pick(QA)
            add("ask_otto_conversations", id=conv_id, company_id=cid, user_id=u["id"],
                shunya_conversation_id="conv_" + uuid4().hex[:20],
                title=q[:80],
                context={"scope": "company", "date_range_days": pick([7, 14, 30, 90]),
                         "filters": {"role": pick(["csr", "sales_rep", "all"])}},
                extra_metadata={"client": pick(["web", "mobile"]), "model": "otto-intel-v5.9"},
                created_at=started, updated_at=started + timedelta(minutes=RNG.randrange(1, 40)))

            turns = [(q, a)]
            if maybe(0.55):
                turns.append(pick([t for t in QA if t[0] != q]))
            t0 = started
            for uq, ua in turns:
                add("ask_otto_messages", id=uuid4(), conversation_id=conv_id,
                    shunya_message_id="msg_" + uuid4().hex[:20], role="user", content=uq,
                    message_metadata={"tokens": RNG.randrange(10, 40)}, created_at=t0)
                t0 += timedelta(seconds=RNG.randrange(3, 25))
                add("ask_otto_messages", id=uuid4(), conversation_id=conv_id,
                    shunya_message_id="msg_" + uuid4().hex[:20], role="assistant", content=ua,
                    message_metadata={"tokens": RNG.randrange(120, 500),
                                      "sources": RNG.randrange(3, 25),
                                      "latency_ms": RNG.randrange(800, 5200)},
                    created_at=t0)
                t0 += timedelta(seconds=RNG.randrange(20, 400))

        # ---------------- insight jobs ----------------
        for w in range(RNG.randrange(4, 9)):
            ws = (NOW - timedelta(days=7 * (w + 1))).date()
            ws = ws - timedelta(days=ws.weekday())
            jstatus = RNG.choices(["completed", "completed", "completed", "failed", "running"],
                                  weights=[7, 7, 7, 1, 1])[0]
            started = datetime.combine(ws + timedelta(days=7), datetime.min.time(),
                                       tzinfo=timezone.utc) + timedelta(hours=2)
            add("insight_jobs", id=uuid4(), company_id=cid,
                shunya_job_id="ins_" + uuid4().hex[:20],
                week_start=ws, week_end=ws + timedelta(days=6),
                company_ids=[str(cid)],
                insight_types=sample(["objection_trends", "sop_compliance", "rep_performance",
                                      "lead_source_roi", "missed_opportunity", "coaching_targets"],
                                     RNG.randrange(2, 5)),
                status=jstatus, force_regenerate=maybe(0.1), include_inactive_customers=maybe(0.2),
                started_at=started,
                completed_at=started + timedelta(minutes=RNG.randrange(3, 40))
                    if jstatus == "completed" else None,
                failed_at=started + timedelta(minutes=RNG.randrange(1, 15))
                    if jstatus == "failed" else None,
                results={"insights_generated": RNG.randrange(4, 22),
                         "calls_analyzed": RNG.randrange(40, 260),
                         "top_objection": pick(OBJECTIONS),
                         "avg_sop_compliance": round(RNG.uniform(0.48, 0.88), 3)}
                    if jstatus == "completed" else None,
                error={"code": "UPSTREAM_TIMEOUT", "message": "Insight worker exceeded 15m budget"}
                    if jstatus == "failed" else None,
                extra_metadata={"triggered_by": pick(["cron", "manual"])},
                created_at=started - timedelta(minutes=5),
                updated_at=started + timedelta(minutes=40))

    # ---------------- leaderboard stats (derived from real outcomes) ----------------
    for (uid, cid, pkey), st in all_user_period_stats.items():
        add("leaderboard_stats", user_id=uid, company_id=cid, period_key=pkey,
            won_count=st["won"], total_resolved=st["resolved"],
            sum_deal_value=round(st["value"], 2), no_show_count=st["no_show"])


# --------------------------------------------------------------------------
# Persist
# --------------------------------------------------------------------------

def main():
    url = os.environ["TARGET_SYNC_URL"]
    engine = create_engine(url, future=True)

    print("Generating...")
    build()

    order = [t.name for t in Base.metadata.sorted_tables]

    # One statement so Postgres resolves the FK graph itself.
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE " +
                          ", ".join(f'"{n}"' for n in order) + " CASCADE;"))

    total = 0
    with engine.begin() as conn:
        for name in order:
            rows = ROWS[name]
            if not rows:
                continue
            tbl = T[name]
            # SQLAlchemy renders Python None into a JSON/JSONB column as JSON
            # `null`, not SQL NULL - so `col IS NULL` would be false and
            # jsonb_typeof() would return 'null'. Drop the key instead, which
            # leaves the column unset and therefore genuinely NULL.
            jcols = {c.name for c in tbl.columns
                     if isinstance(c.type, (SA_JSON, PG_JSONB)) and c.default is None}
            rows = [{k: v for k, v in r.items() if not (k in jcols and v is None)}
                    for r in rows]
            # executemany requires a uniform key set, and omitting a key is how a
            # column falls back to its server/Python default - so group by key set
            # rather than padding everything out to NULL.
            groups: dict[frozenset, list[dict]] = {}
            for r in rows:
                groups.setdefault(frozenset(r), []).append(r)
            for payload in groups.values():
                for i in range(0, len(payload), 500):
                    conn.execute(tbl.insert(), payload[i:i + 500])
            total += len(rows)
            print(f"  {name:<28} {len(rows):>6}")

    print(f"\nTotal rows inserted: {total}")

    # The leaderboard endpoint defaults to period='all_time'. Rather than
    # reimplement that aggregation, run the application's own recalculator so
    # the stored rows match production behaviour exactly.
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from app.infrastructure.repositories.leaderboard import LeaderboardRepository

    async def recalc():
        aurl = url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        aeng = create_async_engine(aurl, connect_args={"statement_cache_size": 0})
        Session = async_sessionmaker(aeng, expire_on_commit=False)
        with engine.connect() as c:
            ids = [r[0] for r in c.execute(text("select id from companies")).fetchall()]
        for company_id in ids:
            async with Session() as s:
                await LeaderboardRepository(s).recalculate_stats(company_id)
                await s.commit()
        await aeng.dispose()

    asyncio.run(recalc())
    with engine.connect() as c:
        n = c.execute(text(
            "select count(*) from leaderboard_stats where period_key='all_time'")).scalar()
        tot = c.execute(text("select count(*) from leaderboard_stats")).scalar()
    print(f"  leaderboard_stats recalculated via app code: {tot} rows ({n} all_time)")

    print(f"Demo login password for every seeded user: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
