"""
Generates an Excel workbook of BEHAVIORAL test cases for the Otto AI Backend.
Interns test exclusively via Postman / Swagger (https://ottoai.shunyalabs.ai/docs).

Each test case description is written as four labelled parts so an intern knows
WHAT the API is for, WHAT the backend should do, and HOW to confirm the response
is actually correct (a 200 status alone does NOT mean the response is right):

  Purpose      - what the feature is for / who uses it
  Backend      - what should happen server-side (DB writes, calcs, side effects)
  Verify       - concrete checks on the RESPONSE BODY / data that prove correctness
  Setup        - anything that must be arranged outside Postman (only when needed)

Columns: No, Test Case Name, Description, Priority, Assigned To, Module, Status, Notes
Cases are split round-robin across Anurag, Devanshi, Kunal.
"""

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

INTERNS = ["Anurag", "Devanshi", "Kunal"]
BASE_URL = "https://ottoai.shunyalabs.ai"


def d(purpose, backend, verify, setup=None):
    """Assemble a labelled, multi-line description cell."""
    parts = [
        f"PURPOSE: {purpose}",
        f"BACKEND SHOULD: {backend}",
        f"VERIFY THE RESPONSE IS CORRECT (200 alone is NOT enough): {verify}",
    ]
    if setup:
        parts.append(f"SETUP (outside Postman): {setup}")
    return "\n\n".join(parts)


# (Module, Name, Description, Priority)
CASES = [
    # ============================ AUTH / SECURITY ============================
    ("Auth", "Health check is public", d(
        "Liveness probe used by load balancers / uptime monitors.",
        "Return a healthy status without requiring any auth. GET / and GET /health are the ONLY endpoints that bypass the X-API-Key guard.",
        "Body contains a status/health indicator (e.g. status:ok or healthy). Send it with NO X-API-Key header and still get 200 — proving these two routes are intentionally public.",
    ), "High"),
    ("Auth", "Protected route rejects missing key", d(
        "Confirms the global auth guard actually protects data endpoints.",
        "Reject any request to a protected route that has no X-API-Key header, before any business logic runs.",
        "Call e.g. GET /api/v1/calls?company_id=<uuid> with NO key -> expect 401/403 and an auth-error message, NOT call data. If you get 200 with data, the guard is broken.",
    ), "High"),
    ("Auth", "Protected route rejects invalid key", d(
        "Confirms the key is validated, not just checked for presence.",
        "Reject a request whose X-API-Key is a random/garbage value.",
        "Expect 401/403. Make sure a WRONG key does not return data — only a correct key should.",
    ), "High"),
    ("Auth", "Signup creates a real account + tokens", d(
        "Public registration; creates the first user + returns login tokens.",
        "Hash the password, create the user (role defaults to SALES_REP, is_active=true), and issue JWT access + refresh tokens carrying user_id/role/company_id claims.",
        "Response has access_token, refresh_token and a user object. Paste the access_token into jwt.io — it must decode and the user_id claim must equal the returned user.id. user.is_active must be true. Re-signup with the SAME email must fail (400/409 duplicate), proving uniqueness is enforced.",
    ), "High"),
    ("Auth", "Login returns valid tokens / rejects bad creds", d(
        "Email+password authentication for existing users.",
        "Validate the password against the stored hash; 401 on wrong password, 403 if the account is inactive; on success issue fresh access+refresh tokens.",
        "On success the returned user.id matches the account, and the decoded JWT claims match. Then login with a WRONG password -> must be 401 (not 200). This proves it actually checks the password, not just the email's existence.",
    ), "High"),
    ("Auth", "Refresh rotates the access token", d(
        "Lets the app get a new access token without re-entering credentials.",
        "Decode the refresh token, confirm it is a refresh (not access) token, load the user, and mint a NEW access token.",
        "Response access_token differs from the original and its decoded 'iat' (issued-at) is later. Sending an invalid/expired refresh token must return 401. A 200 that returns the same/stale token is a bug.",
    ), "Medium"),
    ("Auth", "auth/me returns the caller's identity", d(
        "Lets the client fetch the logged-in user after login.",
        "Resolve the user from the JWT and return their profile.",
        "Returned id must equal the user_id encoded in the token you sent — try a token for user A and confirm you don't get user B. Email/name fields are non-null.",
    ), "Medium"),

    # ============================ USERS ============================
    ("Users", "List users is company-scoped", d(
        "Managers browse users in their company; feeds assignee pickers.",
        "Return users filtered by company_id with skip/limit pagination (default 100, max 1000).",
        "Every returned user.company_id equals the requested company_id (no other tenant's users leak). If you pass role=CSR, every row is a CSR. skip=10&limit=5 returns a different 5 than skip=0.",
    ), "High"),
    ("Users", "List sales reps filters by role", d(
        "CSR/exec views to pick a sales rep.",
        "Return only role=SALES_REP active users for the given company.",
        "EVERY row has role=SALES_REP (not CSR/EXECUTIVE) and the requested company_id. A 200 containing a CSR means the role filter is wrong.",
    ), "Medium"),
    ("Users", "Assignees are deduped + active", d(
        "Populates 'assign to' dropdowns (CSRs + Sales Reps).",
        "Union users across roles [CSR, SALES_REP], drop inactive, and de-duplicate by id.",
        "Every row is_active=true and role in (CSR, SALES_REP). No user id appears twice even if they match multiple roles.",
    ), "Medium"),
    ("Users", "Create user enforces uniqueness", d(
        "Admin onboarding of a user outside signup/invite (EXECUTIVE only).",
        "Hash password, validate company_id exists, reject duplicate email (400), create with is_active=true.",
        "After 201, GET /users/{id} returns the same email/role/company. Re-POST same email -> 400. POST with a non-existent company_id -> 400. POST role='wizard' -> 422. Password must NOT appear anywhere in the response.",
    ), "High"),
    ("Users", "Update user applies partial changes only", d(
        "Edit a user's name/role/active flag (EXECUTIVE only).",
        "Apply only the non-null fields sent; leave omitted fields unchanged; re-hash password if supplied.",
        "Change only first_name -> GET shows new first_name but role/email UNCHANGED. If you update the password, you can then log in with the NEW password (proves the hash actually changed). Unknown user_id -> 404.",
    ), "Medium"),
    ("Users", "Delete user is real + self-delete blocked", d(
        "Hard-delete a user (EXECUTIVE only).",
        "Remove the row; block deleting your own account (400).",
        "After 204, GET /users/{id} -> 404 (row truly gone). Deleting your own user_id -> 400. Deleting a random UUID -> 404.",
    ), "Medium"),
    ("Users", "Deactivate sales rep is a soft delete", d(
        "Remove a rep from active rotation without losing history (EXECUTIVE only).",
        "Set is_active=false (NOT a hard delete); reject if the target isn't a SALES_REP.",
        "Response shows is_active=false; the rep disappears from GET /users/sales-reps (active filter) but the record still exists. Calling on a non-sales-rep -> 400.",
    ), "Medium"),
    ("Users", "Path param must be a UUID", d(
        "Input validation on user id path params.",
        "Reject a non-UUID path segment with 422 before any DB lookup.",
        "GET /users/not-a-uuid -> 422 with a validation message (not 404, not 500).",
    ), "Medium"),

    # ============================ ONBOARDING ============================
    ("Onboarding", "Validate GHL credentials", d(
        "Fail-fast check of GoHighLevel creds during onboarding.",
        "Call GHL with the supplied api_key+location_id; on success return that GHL account's company_id/company_name; 401 if invalid.",
        "With VALID creds: returned company_name matches the real GHL account and company_id is non-empty. With FAKE creds: 401 (not a generic 200). A 200 for fake creds means validation is faked.",
        "Ask the team for sandbox GHL credentials.",
    ), "High"),
    ("Onboarding", "Validate CTM credentials", d(
        "Fail-fast check of Call Tracking Metrics creds.",
        "Verify access_key+secret_key against CTM; return company_id (int) + company_name; 401 if invalid.",
        "Valid -> company_id is an integer and company_name non-empty. Invalid access_key -> 401.",
        "Ask the team for CTM test credentials.",
    ), "Medium"),
    ("Onboarding", "Validate ServiceTitan credentials", d(
        "Fail-fast check of ServiceTitan OAuth creds.",
        "Verify tenant_id+client_id+client_secret; return tenant_id + status; 401 if invalid.",
        "Valid -> returned tenant_id equals what you sent and status indicates success. Invalid client_secret -> 401.",
        "Ask the team for ServiceTitan sandbox creds.",
    ), "Medium"),
    ("Onboarding", "Complete onboarding builds the tenant", d(
        "One-shot company setup: creates company, executive user, integrations, default tenant config, uploads SOPs, returns tokens.",
        "Create company + EXECUTIVE user, store (encrypted) integration creds, create a default tenant config, upload any SOP docs to S3, schedule Shunya SOP processing, and return JWTs. Idempotent on email (re-use existing user).",
        "Returned user.role=EXECUTIVE and company_id is set; tokens decode. THEN GET /tenant-config/{company_id} returns a config (proves the side-effect happened), and GET /users/companies lists the new company. Re-running with the same email returns the SAME user_id but fresh tokens.",
    ), "High"),
    ("Onboarding", "Complete rejects missing required fields", d(
        "Input validation on the onboarding payload.",
        "Reject payloads missing a required field (e.g. company name) with 422 and no partial company created.",
        "422 lists the missing field. Afterwards, confirm NO half-created company exists (GET /users/companies doesn't show a blank one).",
    ), "Medium"),

    # ============================ INVITES ============================
    ("Invites", "Create invitation stores a pending token", d(
        "Executive invites a teammate; emails them an accept link.",
        "Validate company_id + inviter exist, generate a secure random token, set expiry ~3 days out, store status=PENDING, send the invite email (best-effort).",
        "Response status=PENDING, expires_at is ~3 days ahead, and a token is present. Non-existent company_id -> 400. (If you can, confirm the invite email was sent.)",
    ), "High"),
    ("Invites", "Validate token reflects real state", d(
        "Frontend pre-checks the invite before showing the signup form.",
        "Look up the token; reject if accepted/expired; otherwise return the invite details.",
        "Fresh token -> valid=true and invitation.email matches who was invited. A garbage token -> 404/invalid. An already-accepted token -> 400. Proves it checks real state, not just token format.",
    ), "Medium"),
    ("Invites", "Accept invite creates user + consumes token", d(
        "Invited user sets a password and joins the company.",
        "Validate the token, create (or attach) the user with the invite's role+company, flip invitation to ACCEPTED with accepted_at=now.",
        "Response user.company_id == invite's company and user.role == invite's role; invitation.status flips PENDING->ACCEPTED with a fresh accepted_at. You can then log in with the chosen password. Re-using the SAME token must fail (already used).",
    ), "High"),

    # ============================ TENANT CONFIG ============================
    ("Tenant Config", "Create tenant config syncs to Shunya", d(
        "Per-company AI behaviour: qualification thresholds, keywords, service priorities, business hours.",
        "Translate Otto's schema to Shunya's, POST to Shunya, store the response locally with the returned shunya_config_id, version=1, is_active=true.",
        "Response has a non-null shunya_config_id (proves the Shunya call happened), version=1, is_active=true, and the nested sections you sent (e.g. qualification_thresholds) are persisted verbatim. company_id='abc' -> 422 (must be UUID).",
    ), "High"),
    ("Tenant Config", "Get tenant config returns stored values", d(
        "Read a company's AI config (local-first, Shunya fallback).",
        "Return the stored config for company_id; 404 if it exists nowhere.",
        "Returned company_id matches the path and all sections match what was created. Unknown company_id -> 404 (not an empty 200).",
    ), "Medium"),
    ("Tenant Config", "Update tenant config bumps version", d(
        "Edit AI rules for a company.",
        "Apply only non-null fields, increment version, refresh updated_at; 400 if no fields sent; 404 if no config.",
        "After PUT, version increased by exactly 1 and updated_at is newer; the field you changed changed and the ones you omitted did NOT. Empty body -> 400.",
    ), "Medium"),

    # ============================ CALL PROCESSING ============================
    ("Call Processing", "Submit call for processing", d(
        "Core pipeline: send a call's audio to Shunya for transcription, diarization, summary, compliance, objections, BANT.",
        "Validate Shunya is up (503 if not), submit with metadata.agent, create a CallProcessingJob row (status=queued), and return a job_id + status_url.",
        "Response has a job_id, status='queued', and status_url pointing to /call-processing/status/{job_id}. company_id must be a UUID. metadata.agent.id and metadata.agent.name are REQUIRED — omitting them must give 422, not 202.",
        "Get a short sample audio_url + a valid company_id from the team.",
    ), "High"),
    ("Call Processing", "Duplicate call is deduped", d(
        "Prevents re-billing/re-processing the same call.",
        "Block a second submit with the same call_id unless allow_reprocess=true.",
        "First POST -> 202 with job_id. Second POST same call_id -> blocked / returns the existing job (NOT a brand-new job). Then POST with allow_reprocess=true -> accepted. If every duplicate returns a fresh job_id, dedup is broken.",
    ), "High"),
    ("Call Processing", "Poll status transitions to a terminal state", d(
        "Lets clients track async processing.",
        "Fetch live status from Shunya, update the local job row, expose progress + result URLs.",
        "Poll the job_id repeatedly: status moves queued -> processing -> completed (or failed) — it must actually CHANGE, not sit on 'queued' forever. When completed, results.summary_url/chunks_url/transcript_url are populated. Unknown job_id -> 404.",
    ), "High"),
    ("Call Processing", "Summary reflects the real call", d(
        "Shows the AI summary + qualification/BANT/compliance/objections for a processed call.",
        "Return the structured summary from Shunya for that call_id.",
        "The summary TEXT should describe that specific call's content (not generic boilerplate); BANT/score fields are within 0-1; objections is a list of objects (text/severity). Run this only on a call whose status is 'completed'.",
    ), "High"),
    ("Call Processing", "Chunks have speakers + timestamps", d(
        "Transcript segments used for playback and RAG indexing.",
        "Return time-windowed transcript chunks with speaker labels and vector ids.",
        "Each chunk has a non-null speaker label, chronological timestamps within the call duration, and a milvus_id. Empty chunks for a completed call is a bug.",
    ), "Medium"),
    ("Call Processing", "Retry creates a NEW linked job", d(
        "Re-run a failed analysis.",
        "Resubmit to Shunya, create a new job that references the original and increments retry_attempt.",
        "Returned job_id differs from the original; the new job is pollable; retry_attempt incremented. Reusing the old job_id would be wrong.",
        "Ask the team for a failed job_id, or force a failure first with a bad audio_url.",
    ), "Medium"),

    # ============================ CALLS ============================
    ("Calls", "List calls is paginated + scoped", d(
        "Browse a company's calls.",
        "Return calls for company_id with skip/limit.",
        "Every call.company_id matches; skip/limit actually page the results; company_id is required (omit it -> 422).",
    ), "High"),
    ("Calls", "Call logs: summary + analysis_status are honest", d(
        "Main call-log table with filters, search, and per-call analysis state (CL-44).",
        "Compute summary counts over the FULL filtered set (not the page), and set analysis_status from the real CallAnalysis row — not inferred from is_booked.",
        "summary.total_calls equals the total matching BEFORE pagination. When a call's analysis_status is pending/processing, is_booked/is_qualified are null (not false). objection_filter=price returns only calls whose objections array contains 'price'. This catches the exact 'green 200 but wrong data' problem.",
    ), "High"),
    ("Calls", "Get call resolves analysis_status", d(
        "Single call detail.",
        "Return the call plus a derived analysis_status even when the analysis lookup is empty.",
        "analysis_status is always present: 'not_analyzed' when no analysis row, 'completed' when the row exists with blank status, else the raw status. Random UUID -> 404.",
    ), "High"),
    ("Calls", "Create action item from a call", d(
        "Exec assigns a follow-up task tied to a call.",
        "Validate the call exists, create a PendingAction with owner_id=assignee and assigned_by_id=caller, status=pending.",
        "Response assigned_by_id = your user, owner_id = the assignee you set, status=pending (not completed). The new action then shows up in GET /tasks. Unknown call_id -> 404.",
    ), "Medium"),
    ("Calls", "Calls-by-objection is role-aware", d(
        "Coaching view: calls/leads/CSRs for one objection.",
        "Filter calls whose objections contain the objection; scope to the current user for CSR/SALES_REP, company-wide for EXECUTIVE.",
        "Every returned call's objections contain the filter value. As a CSR you see only your own calls; as an EXECUTIVE you see the whole company. Returns three sections (calls, unbooked_leads, coaching_need).",
    ), "Medium"),
    ("Calls", "Objection details respects date range", d(
        "Deep-dive for one objection with booking-rate graph.",
        "Filter by objection + optional user + date range (default 30d).",
        "With start_date/end_date set, every returned call's created_at falls inside the window; coaching_need is sorted by descending unbooked count.",
    ), "Medium"),
    ("Calls", "Retry blocks concurrent analysis", d(
        "Re-analyze an existing call.",
        "Require the call to have an audio_url; reject (409) if analysis is already 'processing'; reset status to pending and resubmit with metadata.agent.",
        "On success processing_job_id is populated and analysis_status='processing'. If analysis is already processing -> 409 (prevents duplicate Shunya jobs). On submit failure -> analysis_status='failed' and processing_job_id is null.",
    ), "Medium"),

    # ============================ CONTACT CARD ============================
    ("Contact Card", "Get contact card by id", d(
        "Customer contact record (name/phone/email/custom fields).",
        "Return the contact card by id; 404 if missing.",
        "Returned id matches; phone_number is consistent; custom_fields (if any) is a JSON object. Invalid UUID -> 422, unknown -> 404.",
    ), "Medium"),
    ("Contact Card", "Get call from contact-card context", d(
        "Opens a call from the contact card screen.",
        "Return the call; if it references a contact_card_id, validate it but do not fail when missing (non-blocking).",
        "The call is returned even if its contact_card_id points to a missing contact (graceful). When the contact exists, contact_card_id is populated.",
    ), "Medium"),

    # ============================ ASK OTTO / RAG ============================
    ("Ask Otto", "RAG ask-otto answers from real data", d(
        "Executive-only company-wide Q&A grounded in call/lead data.",
        "Require the caller to have a company_id (403 otherwise), run RAG over the company's data via Shunya, return an answer + sources.",
        "The answer references actual calls/leads (ask 'how many calls last week?' and sanity-check the number); sources/citations are present. A caller with no company_id -> 403. Generic, source-less answers indicate RAG isn't really running.",
    ), "High"),
    ("Ask Otto", "Create conversation thread", d(
        "Starts a chat thread with Otto.",
        "Create a local conversation row (+ Shunya thread if available); fall back to local-only if Shunya is down.",
        "Response has a local id (always) and a conversation_id; a GET /conversations then lists it. Keep the id for later tests.",
    ), "High"),
    ("Ask Otto", "List conversations is user-scoped + ordered", d(
        "Sidebar of a user's chat threads.",
        "Return the caller's conversations newest-first.",
        "Only YOUR conversations appear (not another user's), ordered by created_at descending; the one you just created is at the top.",
    ), "Medium"),
    ("Ask Otto", "Send message streams an answer (SSE)", d(
        "The core conversational turn; supports Otto's 13 intents.",
        "Store the user message, get an answer from Shunya, store the assistant reply, auto-generate a title on first message, and STREAM the answer as Server-Sent Events.",
        "In Postman watch the streamed SSE chunks arrive incrementally and end with a done event — not one big blob. The answer is relevant to your question. Try several intents ('summarize my calls', 'top objections', 'how is rep X doing') and confirm the answers differ meaningfully. Afterwards GET messages shows both your message and the reply.",
    ), "High"),
    ("Ask Otto", "Get messages returns ordered history", d(
        "Loads a thread's history.",
        "Return all messages oldest-first (Shunya-first, local fallback).",
        "Messages are chronological and roles alternate user->assistant; your earlier message + Otto's reply are both present.",
    ), "Medium"),
    ("Ask Otto", "Rename conversation persists", d(
        "Let users title their threads.",
        "Update the local title + updated_at.",
        "After PATCH, GET the conversation shows the new title and a refreshed updated_at (persisted, not just echoed).",
    ), "Low"),
    ("Ask Otto", "Delete conversation cascades", d(
        "Remove a thread and its messages.",
        "Delete the conversation and its messages (Shunya best-effort).",
        "After 200/204, GET the conversation -> 404 and its messages are gone too.",
    ), "Medium"),

    # ============================ INSIGHTS ============================
    ("Insights", "Generate insights (async job)", d(
        "Weekly company/customer/objection insight generation.",
        "Validate Shunya up (503 if not), submit the job, store an InsightJob row with the week range + flags, return job_id + status.",
        "Response has a job_id and a status like 'queued'; the stored week_start/week_end match what you sent. Then poll status to confirm it progresses.",
    ), "High"),
    ("Insights", "Insight job status updates", d(
        "Track async insight generation.",
        "Fetch status from Shunya and update the local row.",
        "Status transitions queued->processing->completed/failed; timestamps (started_at/completed_at) populate as it progresses; no stale data.",
    ), "Medium"),
    ("Insights", "Current company insight", d(
        "Latest weekly company insight for dashboards.",
        "Return the most recent company insight from Shunya.",
        "Returned data is scoped to the company_id you asked for and reflects the latest generated week. If empty, run /generate first then re-check.",
    ), "High"),
    ("Insights", "Customer insights paginate + filter", d(
        "Per-customer insight list.",
        "Return paginated customer insights with status/priority filters applied server-side.",
        "Returned page/limit match your request and count <= limit; if you filter status/priority every row matches.",
    ), "Medium"),
    ("Insights", "Appointment insights bounded correctly", d(
        "Sentiment / SOP score / objections for one appointment.",
        "Read call_analysis linked to the appointment; 404 if the appointment doesn't exist.",
        "sentiment and sop_score are within 0-1 (or null while pending); objections_found is a list when completed. A genuinely missing appointment -> 404 (not a null-filled 200).",
    ), "Medium"),
    ("Insights", "Objection insights aggregate", d(
        "Company-wide objection breakdown.",
        "Return objection types + frequencies from Shunya.",
        "Objection types match the canonical set (price/timing/authority/...); frequency counts are non-negative integers.",
    ), "Medium"),

    # ============================ METRICS ============================
    ("Metrics", "Company overview KPIs are internally consistent", d(
        "Executive dashboard headline numbers.",
        "Aggregate leads/calls/appointments over the date range (default 30d); conversion_rate = booked/qualified*100 (or close rate for sales reps); revenue = sum of deal sizes.",
        "Sanity-check the math, not just the 200: active_leads <= total_leads, qualified_leads <= active_leads, booked_leads <= qualified_leads, conversion_rate between 0-100. Pass user_id AND company_id together -> only that user's numbers (user takes precedence).",
    ), "High"),
    ("Metrics", "CSR dashboard counts are sane", d(
        "Per-CSR call/lead/appointment stats.",
        "Compute totals, calls_today, avg_call_duration, leads_assigned, appointments_scheduled for the range.",
        "missed_calls <= total_calls; calls_today <= total_calls; avg_call_duration >= 0 (2 decimals); all counts non-negative integers.",
    ), "Medium"),
    ("Metrics", "Missed-calls math checks out", d(
        "Missed-call analysis + recovery.",
        "miss_rate = missed/total*100; picked_up = missed with a lead; booked = missed that became booked; return 10 most recent.",
        "miss_rate is 0-100 and equals missed/total*100; picked_up <= missed; booked <= picked_up; recent_missed_calls length <= 10 and newest-first.",
    ), "Medium"),
    ("Metrics", "Auto-queued leads are priority-ordered", d(
        "CSR work queue ordering.",
        "Return leads ranked hot > warm > new, capped by limit (default 20).",
        "The list leads with 'hot' rows, then 'warm', then 'new'; count <= limit; all rows belong to the company.",
    ), "Low"),
    ("Metrics", "Booking-rate improvement compares periods", d(
        "Shows booking-rate change across two periods.",
        "Per day count qualified vs booked; daily rate = booked/qualified*100; average across days; also a legacy current-vs-previous mode.",
        "Each rate is 0-100; the period average equals the mean of daily rates; improvement_percentage = current - previous. With user_id set, only that rep's leads are counted.",
    ), "Medium"),
    ("Metrics", "Close-rate trends compute won/total", d(
        "Sales close-rate trend.",
        "Daily close rate = won_appointments/total_appointments*100 (won = outcome 'won').",
        "Rates 0-100; only appointments with outcome=='won' count as won; with user_id, scoped to that rep.",
    ), "Medium"),
    ("Metrics", "Bookings summary counts add up", d(
        "Booking status tiles.",
        "Count appointments by status within range + bookings today.",
        "confirmed+pending+cancelled <= total_bookings; bookings_today <= total; all non-negative.",
    ), "Low"),
    ("Metrics", "Top objections ranked + correct rates", d(
        "Objection leaderboard with coaching hints.",
        "Aggregate objections by company/user; compute booking_rate, affected_leads_count, most_coaching_needs.",
        "Sorted by count descending; booking_rate = booked/(booked+unbooked)*100; with unbooked_only=true every call_log has booking_status='not_booked'; respects limit.",
    ), "Medium"),
    ("Metrics", "Objections summary percentages sum right", d(
        "Objection distribution.",
        "Total objections, unique types, top objection, per-type breakdown with percentages.",
        "total_objections = sum of breakdown counts; each percentage = count/total*100; breakdown sorted descending; top_objection == breakdown[0].",
    ), "Low"),
    ("Metrics", "Calls for objection type filtered", d(
        "Drill into calls for one objection.",
        "Return calls whose objections include objection_type, optional owner_id filter.",
        "Every returned call actually has that objection; with owner_id set, all calls were handled by that user; count <= limit.",
    ), "Medium"),
    ("Metrics", "Coaching opportunities = low SOP scores", d(
        "Surfaces calls needing coaching.",
        "Return calls with SOP compliance < 70%, worst first, capped by limit.",
        "Every returned call has sop_compliance_score < 0.7 (or <70%); ordered ascending (lowest first); count <= limit.",
    ), "Medium"),
    ("Metrics", "Most coaching opportunities (bottom CSRs)", d(
        "Lowest-performing CSRs + their top objections.",
        "Find the 5 lowest success-rate CSRs; per CSR list top 3 objections with %unbooked.",
        "At most 5 users, genuinely the lowest rates; each objection pct_unbooked = unbooked/qualified*100; at most 3 objections per CSR.",
    ), "Low"),
    ("Metrics", "Strengths-and-issues merges DB + Shunya", d(
        "Unified rep profile (Shunya coaching categories + Otto metrics).",
        "Merge Shunya coaching profile with Otto DB performance; degrade gracefully if one source is down.",
        "top_weaknesses sorted by count desc; window_start/end cover the requested window; booking_rate/conversion_rate within range; data_sources lists which sources contributed. Missing user_id -> 422.",
    ), "Medium"),
    ("Metrics", "Lead-to-sale conversion math", d(
        "Conversion funnel headline.",
        "converted = closed_won in range; rate = converted/total*100; avg days to close; revenue sum.",
        "converted_leads <= total_leads; conversion_rate = converted/total*100; avg_days_to_conversion >= 0 (or null); revenue = sum of deal sizes for closed_won.",
    ), "Medium"),
    ("Metrics", "Pending-to-booked conversion math", d(
        "Pending leads that became booked.",
        "converted_count of pending->booked; rate; avg days to book.",
        "converted_count <= pending_leads_start; conversion_rate = converted/pending_start*100; avg_days_to_book >= 0.",
    ), "Low"),

    # ============================ LEADS ============================
    ("Leads", "List leads filters/sorts/searches", d(
        "Main lead table.",
        "Filter by status/stage/date/search, sort (created_desc default, name, priority), paginate.",
        "All rows belong to company_id; with a status filter every row matches; search by name/phone returns only matching rows; created_desc really is newest-first; count <= limit. company_id required (omit -> 422).",
    ), "High"),
    ("Leads", "Pipeline view groups by stage", d(
        "Kanban board of leads per stage.",
        "Group leads into the 9 pipeline stages, capped per stage; optional cross-stage search.",
        "All 9 stage keys are present (even if empty); no lead appears in two stages; each stage's count <= cap; the totals reconcile with /leads list. With search, every returned lead matches the terms.",
    ), "High"),
    ("Leads", "Get lead by id", d(
        "Single lead.",
        "Return the lead; 404 if missing.",
        "Returned id matches; status is a valid enum. Unknown UUID -> 404.",
    ), "Medium"),
    ("Leads", "Lead details include analyzed conversations", d(
        "Full lead page with contact, engagement, per-call analysis + phases.",
        "Assemble contact/agent/engagement and all calls newest-first with sentiment/SOP/objections/phases.",
        "conversations are newest-first; sop_compliance_score in 0-1 (or null); sentiment in -1..1; qualification_status/booking_status are valid enums or null; phases object present when Shunya enabled.",
    ), "Medium"),
    ("Leads", "Pipeline-detail 3 tabs gated correctly", d(
        "Lead / Appointment / Result tabbed view.",
        "lead tab always; appointment tab null if no appointment; result tab null until the appointment is conducted.",
        "lead tab non-null; appointment null when none linked; result null when outcome is pending; when outcome=won, result.deal_size matches the lead's deal_size.",
    ), "Medium"),
    ("Leads", "Customer card assembles all tabs", d(
        "Rich customer card (engagement, SOP checklist, comments, follow-ups).",
        "Build header + lead/appointment/result tabs with SOP checklist, sentiment, objections, follow-up tasks.",
        "All three tabs present (or null when N/A); SOP checklist items line up with call analysis phases; overdue follow-up tasks have due_date < today.",
    ), "Medium"),
    ("Leads", "Assign lead updates owner", d(
        "Assign a lead to a sales rep.",
        "Set assigned_rep_id, record last_assignment metadata, return rep name + timestamp.",
        "lead.assigned_rep_id changes to the rep you sent; assigned_rep_name matches that rep; assigned_at is ISO. Re-GET the lead to confirm it persisted. Invalid rep -> 4xx; unknown lead -> 404.",
    ), "High"),
    ("Leads", "Update status persists + audits", d(
        "Change a lead's status.",
        "Update status; when changed by an EXECUTIVE, write an audit row (old/new/by/reason).",
        "After PUT, GET shows the new status (persisted, not just echoed); invalid status value -> 422; when an executive changes it, an audit entry is created.",
    ), "High"),
    ("Leads", "Move-stage is forward-only with side effects", d(
        "Advance a lead through the pipeline.",
        "Reject backward moves; require stage-specific fields (deal_size for won, assigned_rep_id+scheduled_start for booked/appointment); create/update appointments; log the move.",
        "Forward move (e.g. booked->won) succeeds and sets the right status; backward move (won->booked) -> 400 with a clear message; moving to 'won' without deal_size -> error; response flags appointment_created/updated correctly. Confirm the new stage in /leads/pipeline.",
    ), "Medium"),

    # ============================ APPOINTMENTS ============================
    ("Appointments", "List appointments filters work", d(
        "Appointment table with filters.",
        "Filter by rep/lead/date/outcome/search; paginate; enrich with contact + rep.",
        "All rows in the company (or the given lead); with assigned_rep_id every row matches; with outcome filter every row's outcome matches; search matches contact/rep/location; count <= limit.",
    ), "High"),
    ("Appointments", "Past appointments are actually past", d(
        "History view.",
        "Return appointments with scheduled_start < now.",
        "EVERY returned scheduled_start is before now (UTC). A future appointment here is a bug.",
    ), "Medium"),
    ("Appointments", "Upcoming are future + pending + sorted", d(
        "Upcoming agenda.",
        "Return scheduled_start >= now with pending/null outcome, soonest first.",
        "Every row is in the future, outcome is null/pending, and the list is sorted ascending by scheduled_start.",
    ), "Medium"),
    ("Appointments", "Today summary counts reconcile", d(
        "Per-rep day view.",
        "Return today's appointments (UTC) + counts.",
        "Every appointment falls on the requested date; total_today = pending_today + closed_today. Bad date format -> 400.",
    ), "Medium"),
    ("Appointments", "Counts endpoint", d(
        "Header tiles.",
        "Return total_today / pending / closed counts.",
        "All non-negative; total_today >= pending + closed.",
    ), "Low"),
    ("Appointments", "Get appointment with insights", d(
        "Single appointment + AI insights.",
        "Return the appointment enriched with insights; normalize objection strings into objects; 404 if missing.",
        "Insights populated only when analysis exists (else null, not fabricated); objections are objects with category_text/severity/overcome; unknown id -> 404.",
    ), "Medium"),
    ("Appointments", "Appointment context = pre-meeting brief", d(
        "Rep's pre-meeting intelligence.",
        "Assemble appointment + lead + contact + prior CSR calls + previous objections + pending actions + AI briefing (+ phases, + follow-up drafts if manual review on).",
        "previous_objections lists objections from this lead's earlier calls; pending_actions are this lead's pending items; ai_briefing is present; follow_up section appears only when manual review is enabled and drafts exist.",
    ), "Medium"),
    ("Appointments", "Create appointment", d(
        "Book a new appointment.",
        "Create with lead/contact/company/time, outcome defaults to pending.",
        "201 with a UUID id, created_at set, outcome=pending. Missing a required field -> 422.",
    ), "High"),
    ("Appointments", "Reschedule updates times", d(
        "Move an appointment.",
        "Update scheduled_start/end (by appointment_id OR lead_id) and refresh updated_at.",
        "New times reflected and updated_at changes. Exactly one of appointment_id/lead_id required. Unknown -> 404.",
    ), "Medium"),
    ("Appointments", "Update location re-geocodes", d(
        "Change the meeting address.",
        "Update location_address and re-geocode to lat/lng via Google.",
        "location_address updated AND latitude/longitude populated from geocoding (or null if no match); updated_at changes.",
    ), "Medium"),
    ("Appointments", "Update appointment partial", d(
        "Edit appointment fields.",
        "Apply only provided fields; refresh updated_at.",
        "Only the fields you sent changed; updated_at refreshed.",
    ), "Medium"),
    ("Appointments", "Delete appointment", d(
        "Remove an appointment.",
        "Delete the row; 404 if missing.",
        "After 204, GET the id -> 404. Unknown id -> 404.",
    ), "Medium"),

    # ============================ RECORDINGS ============================
    ("Recordings", "Initiate returns a presigned upload URL", d(
        "Mobile app uploads in-person appointment audio to S3.",
        "Validate the appointment, return a presigned S3 PUT URL (expires ~15 min) + s3_key.",
        "upload_url is a presigned PUT (has signature + expiry querystring); s3_key follows the appointment pattern. Unknown appointment -> 404.",
    ), "High"),
    ("Recordings", "Complete triggers analysis + advances pipeline", d(
        "Finalizes the recording and kicks off analysis.",
        "Set audio_url + recording_status=uploaded, move the lead to APPOINTMENT_RAN, assign the rep if needed, submit to Shunya (or mark failed).",
        "status is 'processing' on success (or 'analysis_failed' if Shunya down — NOT a misleading success). Then check the lead moved to APPOINTMENT_RAN and lead.assigned_rep_id matches the appointment's rep. On failure, extra_metadata records the reason.",
    ), "High"),
    ("Recordings", "Analysis state machine is honest", d(
        "Polled by the app to show recording/analysis progress.",
        "Derive recording_state from recording_status+analysis_status; ready=true ONLY when completed; return a presigned playback URL.",
        "ready=true iff analysis_status=completed; when ready=false ALL analysis fields (summary, objections, transcript) are null (not stale/garbage); failure_reason is set when failed; audio_url is a short-lived presigned URL, never a raw private S3 link; sop_compliance_rate within 0-1.",
    ), "Medium"),

    # ============================ FOLLOW-UP ============================
    ("Follow-up", "Approve & send Otto proposal", d(
        "Human approves an AI-proposed follow-up (SMS to lead, or a rep nudge).",
        "Require status=proposed; for sms_to_lead send via Twilio (needs lead phone); for nudge_sales_rep create a pending_action; set status=sent/failed.",
        "On SMS success status=sent and external_message_id is a Twilio SID; on nudge success pending_action_id is set. If the lead has no phone or Twilio is down -> status=failed with error_message (NOT a fake success). A non-proposed follow-up -> 400.",
        "Ask the team for a pending follow_up_id in 'proposed' state (created by the follow-up agent).",
    ), "High"),

    # ============================ SALES REP ============================
    ("Sales Rep", "Appointment follow-ups from analysis", d(
        "Follow-ups needed for an appointment.",
        "Read the appointment's call analysis; return follow_up_required + reason + items.",
        "follow_up_required matches the analysis; follow_ups come from analysis.next_steps; missing appointment/analysis -> 404.",
    ), "Medium"),
    ("Sales Rep", "Work queue ranks tasks correctly", d(
        "Unified rep to-do: tasks + unresolved appointments + pending leads.",
        "Rank tasks by urgency tier then value_score; list past pending appointments and stuck leads with counts.",
        "tasks ordered by urgency tier then value_score desc; unresolved_appointments are all past with outcome=pending; section_counts.tasks equals the summed item counts; an executive can query another rep via owner_id, a rep only sees self.",
    ), "High"),
    ("Sales Rep", "Missed-call recovery ordering", d(
        "Rep callback dashboard.",
        "Segment call_back tasks into pending/completed; pending carry urgency + overdue flags.",
        "pending sorted by urgency then soonest-due; overdue=true exactly when minutes_until_due < 0; completed limited to the lookback window; completed_today_count <= completed list length.",
    ), "Medium"),
    ("Sales Rep", "Pending leads filtered + role-checked", d(
        "Qualified-unbooked / stuck leads for a rep.",
        "Filter by rep, status, urgency_only; sort by last_touched/appointment_date; paginate.",
        "Sorted as requested; status filter exact; urgency_only=true returns only High Urgency; the rep_id must be a SALES_REP (else 400); company isolation holds.",
    ), "Medium"),
    ("Sales Rep", "Exec rep stat math", d(
        "A rep's personal stats for execs.",
        "Aggregate recordings/win_rate/attendance/otto usage over the date range.",
        "win_rate = won/(won+lost+no_show)*100 and is 0-100; attendance excludes no-shows; metrics only count appointments inside the date range; unknown rep -> 404.",
    ), "Medium"),
    ("Sales Rep", "Exec appointment detail", d(
        "Appointment overview for execs.",
        "Join contact + rep + analysis; return status, deal size, SOP stages.",
        "customer_name from contact, sales_rep_name from assigned rep, status = appointment.outcome, sop_stages_completed/missed are lists. Unknown id -> 404.",
    ), "Medium"),
    ("Sales Rep", "Ridealongs list filters", d(
        "Exec ridealong/appointment list.",
        "Filter by date/status/ghost-mode/rep/search; return enriched entries.",
        "Date filter bounds scheduled_start; status filter matches; ghost_mode field matches the rep's setting; multi-word search is ANDed; paginated.",
    ), "Low"),
    ("Sales Rep", "Sales team stats", d(
        "Per-rep team stats.",
        "Return recordings/win_rate/process_score/skills_score/otto usage, top first.",
        "win_rate = won/total*100; process_score & skills_score within 0-100; otto_usage_hours >= 0; paginated.",
    ), "Medium"),
    ("Sales Rep", "Sales rep dashboard composition", d(
        "Main sales dashboard.",
        "Compose ridealongs (<=9), team stats (<=3), objections for the range.",
        "ridealongs_list <= 9, sales_team_stats <= 3, objections sorted by count desc with booking_rate = booked/(booked+unbooked)*100; date filters applied.",
    ), "Medium"),
    ("Sales Rep", "Appointment tasks from analysis", d(
        "Tasks tied to an appointment.",
        "Return action_items/next_steps/pending_actions from the appointment's analysis.",
        "Populated from the analysis; missing appointment/analysis -> 404.",
    ), "Medium"),

    # ============================ TASKS / ACTION CENTER ============================
    ("Tasks", "List tasks: completion rate + summary", d(
        "Task management table.",
        "Filter by status/priority/assignee/search/date; compute completion_rate; paginate.",
        "completion_rate = completed/total*100 (0 if none); summary counts (pending/in_progress/completed/cancelled) sum to total; status filter exact; search matches task text or customer info.",
    ), "High"),
    ("Tasks", "Action center ranks by urgency then value", d(
        "Rep's prioritized feed.",
        "Compose call_back/follow_up/reminder/rehash tasks; rank by urgency tier (overdue>due_now>due_soon>later_today>upcoming>no_due_date) then value_score.",
        "'next' is the top overdue item when overdue exist; tiers assigned correctly by minutes_until_due (overdue <0, due_now 0-60, due_soon 60-480...); within a tier sorted by value_score desc; summary total = sum of group counts. This is where a 200 can hide bad ordering — check the order explicitly.",
    ), "High"),
    ("Tasks", "Rehash scan is idempotent", d(
        "Surfaces missed revenue (qualified-unbooked, stale leads).",
        "Scan for candidates and create pending_action rows for NEW ones only; skip existing.",
        "Response: scanned >= created+cancelled+skipped; created rows appear in the action center; running it AGAIN returns created=0 (idempotent). If the second run keeps creating duplicates, it's broken.",
    ), "Medium"),
    ("Tasks", "Get task detail", d(
        "Single task with assignee + source call.",
        "Return the task with assigned_to/assigned_by info and source_call info.",
        "task id matches; assigned_to.user_id == owner_id; source_call populated when call_id exists; unknown -> 404.",
    ), "Medium"),
    ("Tasks", "Follow-up guidance is grounded", d(
        "AI coaching copy for a follow-up task.",
        "Assemble opening line/talking points/objection responses/SMS draft from the call analysis + Otto data.",
        "say_next fields are populated from real analysis (not blank); context.customer_name matches the source call; sms_draft present only when include_sms=true; sources lists the data actually used.",
    ), "Medium"),
    ("Tasks", "Create task", d(
        "Manual task creation (EXECUTIVE).",
        "Create a PendingAction; assigned_by_id=caller; optional lead/call/appointment links.",
        "201 with created_at=now, owner_id = the assignee, assigned_by_id = you, status as requested. It then shows in GET /tasks. Missing required field -> 422.",
    ), "Medium"),
    ("Tasks", "Update task respects ownership", d(
        "Edit/reassign a task.",
        "Apply provided fields; set assigned_by_id when owner changes; reps/CSRs may edit only their own, execs any.",
        "updated_at refreshed; only sent fields changed; a rep editing someone else's task -> 403; invalid status -> 422; unknown -> 404.",
    ), "Medium"),

    # ============================ COACHING ============================
    ("Coaching", "Coaching dashboard (8 sections)", d(
        "Exec's full coaching view for one rep.",
        "Aggregate team + issues + strengths + progression + peer_benchmark + impact + objections + nudges; some sections proxy Shunya.",
        "team avg compliance is the mean of active reps' scores; each issue's frequency equals its call count; objections overcome_rate = overcome/total*100. If Shunya is down, progression+peer_benchmark come back null while the rest still succeed (graceful) — confirm the page doesn't 500.",
    ), "High"),
    ("Coaching", "Team dashboard trend logic", d(
        "Team-wide coaching summary.",
        "Aggregate TeamStats + per-member summaries; trend = compare first vs second half compliance.",
        "team_size = active users after filters; open_issues = sum of members' issue counts; a member's trend is 'improving' when 2nd-half compliance > 1st-half; search matches name/email; role_filter excludes others.",
    ), "Medium"),
    ("Coaching", "Individual dashboard scoped", d(
        "Single-rep deep dive (no team section).",
        "Same as combined dashboard minus team.",
        "Exactly 7 sections (no team); everything scoped to the user_id.",
    ), "Medium"),
    ("Coaching", "Rep issues grouped + sorted", d(
        "A rep's coaching issues.",
        "Group by issue text, count frequency, attach up to 5 transcript excerpts + 10 call_ids.",
        "Issues sorted by frequency desc; each frequency = matching call count; transcript_evidence <= 5; call_ids <= 10; total_issues = array length.",
    ), "Medium"),
    ("Coaching", "Rep strengths grouped + sorted", d(
        "A rep's strengths.",
        "Group by behavior, count frequency, attach evidence.",
        "Sorted by frequency desc; total_strengths = array length; frequencies match call counts.",
    ), "Medium"),
    ("Coaching", "Rep progression trend window", d(
        "Weekly metric trends from Shunya.",
        "Proxy Shunya progression for the given weeks (4-52) with trend + anomaly flags.",
        "timeframe_weeks == weeks param; weeks_with_data <= timeframe_weeks; overall_confidence in (high/medium/low); improving/declining/stable metric lists are disjoint; weekly_data chronological.",
    ), "Medium"),
    ("Coaching", "Peer benchmark 5 metrics", d(
        "Rep vs team/top performer.",
        "Proxy Shunya; compute rank/percentile/gap_to_top/vs_avg over days window (7-365).",
        "Exactly 5 metrics (compliance_score, booking_rate, objection_handling, rapport_score, script_adherence); rank>=1; percentile 0-100; vs_avg ~= rep_score - peer_average; gap_to_top <= 0 vs top (rep can't beat the top).",
    ), "Medium"),
    ("Coaching", "Rep impact baseline vs post", d(
        "Coaching session outcomes.",
        "List sessions with baseline vs impact scores, improvement_pct, targets_met.",
        "Sorted by coached_at desc; improvement_pct = (mean(impact)-mean(baseline))/mean(baseline)*100; targets_met[m]=true iff impact>=target; overall_improved iff improvement_pct>=0.",
    ), "Medium"),
    ("Coaching", "Rep objections vs team", d(
        "Objection handling per category.",
        "Group by category; compute rep vs team overcome rates.",
        "Sorted by total_count desc; rep_overcome_rate = overcome/total*100; delta_vs_team = rep - team; total_objections = sum of category counts; rates 0-100.",
    ), "Medium"),
    ("Coaching", "Rep nudges generation rules", d(
        "AI coaching nudges for a rep.",
        "Generate from issues(freq>=2 -> immediate), objections(overcome<30% -> pre_call), declining compliance(-> weekly); dedupe; expire after 7 days.",
        "Sorted by priority desc; source in (coaching_issues/objection_history/progression); coaching_issues -> timing=immediate; objection_history -> timing=pre_call; no duplicates.",
    ), "Medium"),
    ("Coaching", "List reps enriched", d(
        "Rep list with role + booking_rate.",
        "Proxy Shunya reps; enrich each with Otto role and booking_rate.",
        "Every rep has a role from the users table; booking_rate = booked/qualified*100 (0 if none) and is 0-100; Shunya down -> 503.",
    ), "Medium"),
    ("Coaching", "Rep profile proxy", d(
        "Full coaching profile.",
        "Proxy Shunya profile for window_days (7-180); force_refresh rebuilds cache (slow).",
        "window_days bounded 7-180; with force_refresh=true expect a slow (30-60s) but valid response; Shunya down -> 503.",
    ), "Medium"),
    ("Coaching", "Create session computes baseline", d(
        "Start a coaching cycle.",
        "Average the rep's last 5 completed analyses into baseline_scores; status=in_progress; 7-day cycle.",
        "baseline_scores = mean of last 5 analyses; status='in_progress'; follow_up_end_date = coached_at + follow_up_days; impact_scores/improvement_pct/targets_met are NULL at creation; targets keys match focus_areas.",
    ), "High"),
    ("Coaching", "List sessions filter + sort", d(
        "Coaching sessions list.",
        "Filter by rep/status; paginate; sort by coached_at desc.",
        "total = matching count; sorted desc; status in (in_progress/completed/stopped); pagination applied.",
    ), "Medium"),
    ("Coaching", "Stop session halts auto-cycle", d(
        "Stop a coaching cycle.",
        "Find the active in_progress cycle in the chain, set status=stopped, don't create the next cycle.",
        "status='stopped'; stopping an already-stopped/completed one -> error/404; NO new child cycle appears afterward; impact_scores preserved; works whether you pass the original or a child cycle id.",
    ), "Medium"),
    ("Coaching", "Session history chain", d(
        "Full cycle history.",
        "Resolve to the root and return original + all cycles.",
        "total_cycles = completed + (1 if active); completed sorted by coached_at desc; cycle_numbers are 1,2,3...; exactly one active in_progress.",
    ), "Medium"),
    ("Coaching", "List nudges per-user read state", d(
        "Smart nudge inbox.",
        "Return nudges with this user's read/dismissed state; filter status/priority/rep.",
        "unread_count = count of unread for YOU; the same nudge can be unread for another exec (per-user state); sorted by created_at desc; filters work.",
    ), "Medium"),
    ("Coaching", "Unread count badge", d(
        "Notification badge.",
        "Count this user's unread nudges only.",
        "unread_count >= 0 and reflects only your unread nudges; matches the count from the list endpoint.",
    ), "Low"),
    ("Coaching", "Mark nudge read decrements count", d(
        "Mark one nudge read.",
        "Set read_status=read + read_at; idempotent; per-user.",
        "After the call, unread-count drops by exactly 1; calling again doesn't error or drop further; another user's state is unchanged.",
    ), "Medium"),
    ("Coaching", "Dismiss nudge hides it", d(
        "Dismiss a nudge.",
        "Set read_status=dismissed + dismissed_at; hide from default list.",
        "Default list count drops by 1; the nudge reappears only with status=dismissed filter; other users unaffected.",
    ), "Medium"),
    ("Coaching", "Mark all read zeroes the count", d(
        "Clear all nudges.",
        "Mark all your unread nudges read; return marked_count.",
        "marked_count = number that were unread; unread-count is 0 afterward; running again returns marked_count=0.",
    ), "Medium"),

    # ============================ GHOST MODE ============================
    ("Ghost Mode", "Status computes effective flag", d(
        "Whether a rep's audio/transcript is hidden from others.",
        "Return company flag, user flag, and effective = user AND company.",
        "effective_ghost_mode = user_ghost_mode_active AND company_ghost_mode_enabled (verify the AND logic with both combinations).",
    ), "Medium"),
    ("Ghost Mode", "User toggle gated by company", d(
        "Rep enables their own ghost mode.",
        "Set the user flag; reject enabling when the company hasn't enabled ghost mode (400).",
        "After enabling (when company allows) user_ghost_mode_active=true and effective recomputes; trying to enable while company flag is off -> 400; disabling always works.",
    ), "Medium"),
    ("Ghost Mode", "Company toggle exec-only", d(
        "Exec enables ghost mode for the company.",
        "Set the company flag; EXECUTIVE only (403 otherwise); don't force-change users' own flags.",
        "company_ghost_mode_enabled matches what you set; a non-exec caller -> 403; existing user flags are preserved.",
    ), "Medium"),

    # ============================ POSTS ============================
    ("Posts", "List posts sorted + scoped", d(
        "Sales-rep social feed.",
        "Return company posts sorted by created_at/likes, paginated.",
        "All posts belong to the company; sort_by + sort_order respected; tags is an array; pagination works.",
    ), "Low"),
    ("Posts", "Create post validates appointment", d(
        "Rep posts with appointment context.",
        "Create with poster_id=caller, likes=0; validate the appointment exists.",
        "201 with poster_id=you, likes=0, created_at=now, note/tags stored exactly; a bad appointment_id -> 400/404; the post then appears in the list.",
    ), "Medium"),
    ("Posts", "Get post by id", d(
        "Single post.",
        "Return by id; 404 if missing.",
        "id matches; unknown -> 404.",
    ), "Low"),
    ("Posts", "Update post edits note/tags only", d(
        "Edit a post.",
        "Update only note/tags; refresh updated_at.",
        "note/tags changed, appointment_id/poster_id unchanged, updated_at refreshed; unknown -> 404.",
    ), "Low"),
    ("Posts", "Like increments by one", d(
        "Like a post.",
        "Increment likes by 1.",
        "likes goes up by exactly 1 per call; unknown post -> 404.",
    ), "Low"),
    ("Posts", "Delete post", d(
        "Remove a post.",
        "Delete by id; return ok.",
        "After delete it's gone from the list; unknown -> 404.",
    ), "Low"),

    # ============================ LEADERBOARDS ============================
    ("Leaderboards", "Leaderboard scoring + ordering", d(
        "Ranks reps by a composite score (win 40%, deal size 35%, attendance 15%, follow-up 10%).",
        "Recalculate, normalize each metric, compute the weighted score, sort desc, support period (all_time or YYYY-MM).",
        "Entries sorted by score descending; rank is sequential 1,2,3...; rank 1 truly has the highest score; all sub-metrics within 0-100; period filter changes the data. A 200 with mis-ordered rows is the failure to catch here.",
    ), "Medium"),

    # ============================ SETTINGS ============================
    ("Settings", "Get settings assembles everything", d(
        "Company settings: integrations + documents + follow-up flag.",
        "Build CRM/VoIP integration status from stored (encrypted) creds, list documents, return the manual-review flag.",
        "CRM/VoIP status='connected' only when a key is actually stored; document URLs appear only when the doc exists; follow_up_manual_review_enabled matches the company setting.",
    ), "Medium"),
    ("Settings", "Toggle follow-up manual review", d(
        "Require human approval before follow-ups send.",
        "Persist the flag on the company.",
        "Response flag matches the body; re-GET /settings confirms it persisted and applies company-wide.",
    ), "Medium"),
    ("Settings", "List integrations count", d(
        "CRM + VoIP integrations.",
        "Return CRM and VoIP as separate entries.",
        "total_count == number of integrations (max 1 CRM + 1 VoIP); status fields correct per provider.",
    ), "Medium"),
    ("Settings", "Get integration by id", d(
        "Single integration.",
        "Return by id + provider_type; validate company match.",
        "id matches and provider_type matches the request; wrong company or missing -> 404; bad provider_type -> 400.",
    ), "Low"),
    ("Settings", "Create integration encrypts keys", d(
        "Connect a CRM/VoIP provider.",
        "Upsert the integration, ENCRYPT api keys at rest, set status=connected when a key is given.",
        "201; the new integration appears in the list; status='connected' when a key was provided; the raw API key must NOT appear in any response (proves encryption-at-rest). ServiceTitan uses its own secret field.",
    ), "Medium"),
    ("Settings", "Update integration", d(
        "Edit integration creds/config.",
        "Update provided fields, re-encrypt keys, recompute status.",
        "Only sent fields change; status flips connected/disconnected based on key presence; keys never returned in plaintext; unknown id -> 404.",
    ), "Medium"),
    ("Settings", "Integration logs capped", d(
        "Sync/error logs.",
        "Return logs from metadata, capped by limit (default 50, max 100).",
        "logs length <= limit; total_count consistent; unknown integration -> 404.",
    ), "Low"),
    ("Settings", "List documents", d(
        "Company documents (reference, SOPs).",
        "Return a DocumentResponse per stored doc with metadata.",
        "total_count = number of documents; document_type in (reference/sop/csr_sop/sales_sop); url + metadata populated from stored data.",
    ), "Medium"),
    ("Settings", "Upload document to S3", d(
        "Upload a reference/SOP file.",
        "Read the file, upload to S3, set the company's doc URL, store metadata (name/type/size/uploaded_at/by).",
        "In Postman use Body > form-data and attach a PDF. Response has an S3 url and size like '2.4 MB'; the doc then appears in GET /documents. Invalid document_type -> 400; S3 down -> 503. A 201 without the doc appearing in the list is a bug.",
    ), "High"),
    ("Settings", "Update document metadata", d(
        "Rename a document.",
        "Update the stored name; keep the URL.",
        "Response shows the new name, URL unchanged, other metadata preserved; missing doc -> 404.",
    ), "Medium"),
    ("Settings", "Delete document", d(
        "Remove a document reference.",
        "Clear the company's doc URL + metadata (S3 object is left in place by design).",
        "After 204 the doc is gone from GET /documents and the URL field is null; missing doc -> 404.",
    ), "Medium"),

    # ============================ MASKED COMMS ============================
    ("Masked Comms", "Register phone sends OTP", d(
        "Rep registers their phone for proxy-number calling/texting.",
        "Normalize to E.164, generate a 6-digit OTP, set ~10-min expiry, send it via Twilio SMS, upsert the rep_phone row.",
        "Response status='otp_sent' and phone_masked hides the middle digits; the rep_phone row stores a code + expiry. (Confirm the SMS arrives if using a real test number.)",
        "Use a team-provided test phone number that can receive SMS.",
    ), "High"),
    ("Masked Comms", "Verify phone only on correct OTP", d(
        "Completes phone verification.",
        "Compare the submitted code (constant-time), check expiry, then mark verified and clear the code.",
        "Correct code -> is_verified=true and the stored code is cleared. WRONG code -> 400 (not verified). Expired code -> 400. Verifying before registering -> 400. A 200 'verified' for a wrong code would be a serious bug.",
    ), "High"),
    ("Masked Comms", "Phone status flags", d(
        "App checks before allowing calls.",
        "Return has_phone + is_verified + masked number.",
        "No record -> has_phone=false,is_verified=false; registered-not-verified -> true/false; verified -> true/true with masked number.",
    ), "Medium"),
    ("Masked Comms", "Update push token", d(
        "Register the device's Expo push token.",
        "Upsert expo_push_token on the rep_phone row even if unverified.",
        "status='updated'; token stored even when is_verified=false.",
    ), "Medium"),
    ("Masked Comms", "List sessions masks numbers", d(
        "Active proxy conversations for the rep.",
        "Return active sessions with the homeowner number masked.",
        "Only status='active' sessions; homeowner phone is masked (only last digits visible); empty list (not 404) when none.",
    ), "Medium"),
    ("Masked Comms", "Session conversation thread", d(
        "Call+SMS history for a session.",
        "Return messages ordered by time with intent labels on inbound SMS.",
        "Pagination works; SMS rows have message_body (calls don't); intent_label/confidence appear only on inbound (homeowner_to_rep) SMS; unknown session -> 404.",
    ), "Medium"),
    ("Masked Comms", "Initiate masked call bridges via Twilio", d(
        "Rep calls homeowner through a proxy number (rep->proxy->homeowner).",
        "Validate session, create a 'call' comm row (status=initiated), dial the rep via Twilio with a bridge URL, return call_sid.",
        "Response call_sid matches Twilio; a masked_communications row is created with comm_type=call, direction=rep_to_homeowner, status=initiated. Unknown session -> 404; Twilio not configured -> 503.",
        "Needs a verified rep phone + an active session.",
    ), "Medium"),
    ("Masked Comms", "Send masked SMS via proxy", d(
        "Rep texts homeowner via the proxy number.",
        "Validate session, create an 'sms' comm row, send via Twilio, return message_sid.",
        "Response message_sid matches Twilio; a masked_communications row stores the body with direction=rep_to_homeowner; body > 1600 chars rejected.",
    ), "Medium"),

    # ============================ WEBHOOKS ============================
    ("Webhooks", "Telephony call-complete ingests a call", d(
        "Inbound webhook from a telephony provider; creates a call in Otto.",
        "Read company_id (payload or X-Company-Id header), parse call metadata, create a Call record, optionally trigger analysis.",
        "Returns success + a call_id; then GET /calls (that company) shows the new call with the phone/audio/type you sent. Missing company_id -> 400. A 200 that doesn't actually create a call is the failure to catch.",
        "Get a sample provider payload from the team/Swagger.",
    ), "High"),
    ("Webhooks", "Shoonya job-complete persists analysis", d(
        "Shunya/Shoonya notifies that analysis finished; Otto stores it.",
        "Only act when job_status=completed; fetch full analysis, create/update CallAnalysis (status=completed), create objection rows + pending actions.",
        "Returns success with a call_id; then GET /call-processing/summary/{call_id} (or the call) shows objections/compliance populated. job_status != completed -> status='ignored'. Missing call_id -> 400. On Shunya fetch failure the call is marked failed and you get a 200 with a warning (not a 500).",
        "Ask the team for a sample Shoonya completion payload.",
    ), "High"),
    ("Webhooks", "GHL messages webhook", d(
        "GoHighLevel call/message events.",
        "Verify the x-wh-signature, identify call events, map location_id->company_id, ingest the call + fetch recording.",
        "Call events create a Call record (check direction/status); non-call events get a quick ack ok=true,isCall=false; a bad/invalid signature -> 401 (when verification is enabled). Invalid JSON -> 400.",
        "Get a sample GHL payload (and whether signature verification is enabled) from the team.",
    ), "Medium"),
    ("Webhooks", "GHL lead-updates webhook", d(
        "GHL contact/appointment/opportunity CRUD sync.",
        "Verify signature, map event type + location_id->company_id, route to the right handler, commit.",
        "Accepted event types return accepted=true and the data syncs (verify via GET leads/appointments); unrecognized types -> ok=true,accepted=false; bad signature -> 401; invalid JSON -> 400.",
    ), "Medium"),
    ("Webhooks", "CTM calls webhook (HMAC)", d(
        "Call Tracking Metrics completed-call webhook.",
        "Verify HMAC-SHA1 x-wh-signature, ensure status answered/completed, ingest call, store audio in S3.",
        "Returns success + call_id + ctm_call_id; the created call's audio_url points to S3 (not CTM); invalid signature -> 401; unknown company -> 400/404; non-answered status -> ignored.",
        "Get a sample CTM payload + signing token from the team.",
    ), "Medium"),
    ("Webhooks", "ServiceTitan calls webhook (worker secret)", d(
        "Batched calls from the ServiceTitan poller.",
        "Validate X-Worker-Secret, map st_tenant_id->company, ingest every call, match agent->rep, store audio.",
        "Wrong/missing X-Worker-Secret -> 401; missing tenant_id -> 400; unknown tenant -> 404; on success a Call row is created per call in the batch.",
        "Get the worker secret + a sample batch payload from the team.",
    ), "Medium"),
    ("Webhooks", "ServiceTitan CRM webhook", d(
        "Batched CRM records (customers/leads/bookings).",
        "Validate worker secret, map tenant, create/update Contacts/Leads/Appointments (ST status -> LeadStatus).",
        "Bad secret -> 401; missing tenant -> 400; on success Contacts and Leads are created with mapped statuses (open->NEW, converted->CLOSED_WON) — verify via GET /leads.",
    ), "Medium"),
    ("Webhooks", "Twilio inbound SMS routing + idempotency", d(
        "Homeowner texts a proxy number.",
        "Validate X-Twilio-Signature, resolve session, classify intent, store comm row, forward to the other party, push-notify, create call_back task if intent=call_me.",
        "Returns TwiML (empty <Response/>); a duplicate MessageSid does NOT forward/notify twice (idempotent); the comm row has an intent_label; a 'call_me' intent creates exactly one call_back PendingAction. Missing From/To -> 400; bad signature -> 403.",
    ), "Medium"),
    ("Webhooks", "Malformed payload fails gracefully", d(
        "Robustness of webhook ingestion.",
        "Reject empty/garbage bodies with a 4xx, never a 500.",
        "POST an empty or broken body to e.g. /webhooks/ctm/calls -> a 4xx error (400/401/422), NOT a 500 stack trace. 500s here mean missing input validation.",
    ), "Medium"),

    # ============================ TWILIO MASKED-COMMS WEBHOOKS ============================
    ("Twilio Webhooks", "Inbound call returns bridge TwiML", d(
        "Twilio voice webhook when someone calls a proxy number.",
        "Validate signature, resolve the session, return TwiML that <Dial>s the other party with recording consent + callbacks.",
        "Body is TwiML containing a <Dial> to the correct bridge number plus recordingStatusCallback; a missing session returns error TwiML with <Say>; invalid signature -> 403.",
    ), "Medium"),
    ("Twilio Webhooks", "Inbound SMS returns empty TwiML", d(
        "Twilio SMS webhook on a proxy number.",
        "Validate signature, classify intent, store + forward, return empty TwiML.",
        "Empty <Response/>; idempotent on MessageSid; bad signature -> 403.",
    ), "Medium"),
    ("Twilio Webhooks", "Call-status updates the record", d(
        "Twilio call status callback.",
        "Update the comm row with final status + duration.",
        "The masked_communications row's call_status and duration_seconds update to the posted values; bad signature -> 403.",
    ), "Low"),
    ("Twilio Webhooks", "Recording-status full pipeline", d(
        "Twilio recording-ready callback.",
        "Download the recording, store in S3, create a Call (sales_call), link it, trigger analysis; idempotent.",
        "The comm row gets recording_url/sid; a Call row is created with the S3 audio_url; if already processed (call_id set) it skips re-processing; bad signature -> 403.",
    ), "Low"),
    ("Twilio Webhooks", "Bridge-call second leg", d(
        "Twilio callback when the rep answers leg one.",
        "Resolve the session and return TwiML <Dial>ing the homeowner.",
        "TwiML <Dial> targets the session's homeowner number with recording callbacks; unknown session -> error TwiML; bad signature -> 403.",
    ), "Medium"),

    # ============================ WEBSOCKET ============================
    ("WebSocket", "Notifications websocket auth + events", d(
        "Real-time push of reminders/alerts to a rep.",
        "Require a JWT in the query param, validate user (active, has company), accept the socket, send connection_established, push notifications, pong on ping.",
        "Use Postman's WebSocket request. With a valid token: it opens, you receive a connection_established message whose user_id/company_id match the token, and ping -> pong. With NO/invalid token it closes with code 4001; inactive user -> 4003; no company -> 4004. Opening successfully without a token is a security bug.",
    ), "Medium"),

    # ============================ CROSS-CUTTING ============================
    ("Cross-cutting", "Swagger lists every endpoint", d(
        "Living API reference for the testers.",
        "Serve the OpenAPI UI at /docs and /redoc with every tagged endpoint.",
        "Both pages load; every module above appears; use Authorize to set X-API-Key. If an endpoint you tested is missing from /docs, flag the doc gap.",
    ), "High"),
    ("Cross-cutting", "Multi-tenant isolation (critical)", d(
        "Guarantees one company can never read another's data.",
        "Scope every query by company; reject or empty cross-tenant access.",
        "Using company A's context, request company B's company_id on calls/leads/metrics/appointments -> you get EMPTY results or 403, NEVER company B's rows. This is the most important 'green-200-but-wrong' check: a 200 returning another tenant's data is a severe leak.",
        "Get two distinct company_ids (and matching keys/users) from the team.",
    ), "High"),
    ("Cross-cutting", "rep_role vs SOP target_role", d(
        "Correct SOP is applied based on the rep's role.",
        "Match the call's rep_role to the SOP whose target_role matches; handle mismatches without crashing.",
        "Process a call with rep_role='sales_rep' while the SOP targets 'customer_rep' (and vice-versa); confirm no 500 and that compliance is scored against the correct SOP (compliance_target_role in the result).",
    ), "Medium"),
    ("Cross-cutting", "Wrong method -> 405", d(
        "HTTP method handling.",
        "Reject unsupported methods with 405.",
        "e.g. DELETE /api/v1/calls -> 405 Method Not Allowed (not 404/500).",
    ), "Low"),
    ("Cross-cutting", "Unknown route -> 404", d(
        "Routing.",
        "Return 404 for undefined paths.",
        "GET /api/v1/does-not-exist -> a clean 404 JSON error.",
    ), "Low"),
    ("Cross-cutting", "Broken JSON -> 4xx not 500", d(
        "Input robustness.",
        "Reject malformed JSON with 400/422.",
        "POST a body with a missing brace to any JSON endpoint -> 422/400 with a parse error, never a 500.",
    ), "Medium"),
]


def build():
    wb = Workbook()
    ws = wb.active
    ws.title = "Test Cases"

    headers = ["No.", "Test Case Name", "Description", "Priority", "Assigned To", "Module", "Status", "Notes"]
    ws.append(headers)

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    prio_fill = {
        "High": PatternFill("solid", fgColor="F8CBAD"),
        "Medium": PatternFill("solid", fgColor="FFE699"),
        "Low": PatternFill("solid", fgColor="C6E0B4"),
    }
    intern_fill = {
        "Anurag": PatternFill("solid", fgColor="DDEBF7"),
        "Devanshi": PatternFill("solid", fgColor="FCE4D6"),
        "Kunal": PatternFill("solid", fgColor="E2EFDA"),
    }

    for col, _ in enumerate(headers, 1):
        c = ws.cell(row=1, column=col)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(vertical="center", horizontal="center", wrap_text=True)
        c.border = border

    for i, (module, name, desc, prio) in enumerate(CASES):
        intern = INTERNS[i % len(INTERNS)]
        ws.append([i + 1, name, desc, prio, intern, module, "Not Started", ""])
        r = ws.max_row
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=col)
            cell.border = border
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        ws.cell(row=r, column=1).alignment = Alignment(vertical="top", horizontal="center")
        pc = ws.cell(row=r, column=4)
        pc.fill = prio_fill.get(prio, PatternFill())
        pc.alignment = Alignment(vertical="top", horizontal="center")
        ac = ws.cell(row=r, column=5)
        ac.fill = intern_fill.get(intern, PatternFill())
        ac.alignment = Alignment(vertical="top", horizontal="center")

    widths = {"A": 6, "B": 34, "C": 110, "D": 10, "E": 12, "F": 16, "G": 13, "H": 26}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:H{ws.max_row}"

    # ---- Read Me ----
    ws2 = wb.create_sheet("Read Me")
    info = [
        ("Otto AI Backend - Behavioral QA Test Plan", True),
        ("", False),
        ("READ THIS FIRST - a 200 OK does NOT mean the response is correct.", True),
        ("Every test's description has 3 parts: PURPOSE (what the API is for),", False),
        ("BACKEND SHOULD (what must happen server-side), and VERIFY (exact checks on the", False),
        ("response body/data that prove it actually worked). Always do the VERIFY checks -", False),
        ("don't stop at the status code. A green 200 with wrong/leaked/stale data is a FAIL.", False),
        ("", False),
        (f"Base URL: {BASE_URL}", False),
        (f"Swagger docs: {BASE_URL}/docs    ReDoc: {BASE_URL}/redoc", False),
        ("", False),
        ("HOW TO TEST (Postman / Swagger only):", True),
        ("1. All endpoints except GET / and GET /health need the 'X-API-Key' header.", False),
        ("   Swagger: click Authorize. Postman: add an X-API-Key header. Ask the lead for the key.", False),
        ("2. company_id must be a valid UUID. Get test company_id(s) + a test user from the team.", False),
        ("3. Call processing requires metadata.agent.id AND metadata.agent.name.", False),
        ("4. Duplicate calls are blocked unless allow_reprocess=true.", False),
        ("5. Async endpoints (call-processing, insights) return a job_id - poll the /status route", False),
        ("   and confirm the status actually CHANGES (queued->processing->completed).", False),
        ("6. File uploads (documents) use Body > form-data with an attached file in Postman.", False),
        ("7. Ask-Otto messages stream Server-Sent Events - watch the chunks arrive incrementally.", False),
        ("8. WebSocket (/ws/notifications) uses Postman's WebSocket request (token in query param).", False),
        ("9. Webhooks need sample payloads (and sometimes signatures/secrets) - ask the team.", False),
        ("", False),
        ("HOW TO LOG RESULTS:", True),
        ("- Status column: Not Started / In Progress / Pass / Fail / Blocked.", False),
        ("- On Fail: in Notes put the HTTP status, WHICH verify-check failed, and the response snippet.", False),
        ("- Save your Postman collection / screenshots for any failure.", False),
        ("- 'Blocked' = you are missing a credential/payload/id; note exactly what you need.", False),
        ("", False),
        ("ASSIGNMENTS: round-robin so each intern covers every module. See the Summary sheet.", True),
    ]
    for idx, (text, is_head) in enumerate(info, 1):
        c = ws2.cell(row=idx, column=1, value=text)
        if is_head:
            c.font = Font(bold=True, size=13 if idx == 1 else 11, color="1F4E78")
    ws2.column_dimensions["A"].width = 105

    # ---- Summary ----
    ws3 = wb.create_sheet("Summary")
    ws3.append(["Intern", "Total Cases", "High", "Medium", "Low"])
    for col in range(1, 6):
        hc = ws3.cell(row=1, column=col)
        hc.fill = header_fill
        hc.font = header_font
        hc.alignment = Alignment(horizontal="center")
    stats = {n: {"total": 0, "High": 0, "Medium": 0, "Low": 0} for n in INTERNS}
    for i, (_, _, _, prio) in enumerate(CASES):
        intern = INTERNS[i % len(INTERNS)]
        stats[intern]["total"] += 1
        stats[intern][prio] += 1
    for n in INTERNS:
        ws3.append([n, stats[n]["total"], stats[n]["High"], stats[n]["Medium"], stats[n]["Low"]])
    ws3.append(["TOTAL", len(CASES),
                sum(s["High"] for s in stats.values()),
                sum(s["Medium"] for s in stats.values()),
                sum(s["Low"] for s in stats.values())])
    for col in range(1, 6):
        ws3.cell(row=ws3.max_row, column=col).font = Font(bold=True)
    for col, w in zip("ABCDE", [14, 12, 8, 10, 8]):
        ws3.column_dimensions[col].width = w

    out = "Otto_Backend_Test_Cases.xlsx"
    wb.save(out)
    print(f"Saved {out} with {len(CASES)} behavioral test cases.")
    for n in INTERNS:
        s = stats[n]
        print(f"  {n}: {s['total']} (High {s['High']}, Medium {s['Medium']}, Low {s['Low']})")


if __name__ == "__main__":
    build()
