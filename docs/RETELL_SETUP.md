# Otto AI Receptionist — Retell Setup

Connect Retell.ai to Otto for inbound AI receptionist calls (lead intake, booking, follow-ups).

## Prerequisites

- Retell account: [dashboard.retellai.com](https://dashboard.retellai.com)
- Otto backend running locally or deployed
- Public HTTPS URL — **Cloudflare Tunnel** (recommended) or ngrok for local dev

## Environment variables

Add to `backend/.env`:

```env
VOICE_AGENT_SECRET=your-long-random-secret
VOICE_AGENT_DEFAULT_COMPANY_ID=ce9091df-db37-4e7e-877c-2ed0cf2f4c37
RETELL_API_KEY=key_...
RETELL_AGENT_COMPANY_MAP={}
```

## 1. Start Otto backend

```powershell
cd backend
uvicorn app.main:app --reload --port 8001
```

Keep this terminal open.

## 2. Cloudflare Tunnel (recommended)

### Install `cloudflared` (one time)

**Windows — PowerShell (run as your user):**

```powershell
# Option A: winget
winget install Cloudflare.cloudflared

# Option B: direct download
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\bin" | Out-Null
Invoke-WebRequest `
  -Uri "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe" `
  -OutFile "$env:USERPROFILE\bin\cloudflared.exe"
# Add $env:USERPROFILE\bin to PATH, then reopen terminal
```

### Start quick tunnel (no Cloudflare account required)

In a **second terminal**:

```powershell
cd backend
.\scripts\start_cloudflare_tunnel.ps1
```

Or manually:

```powershell
cloudflared tunnel --url http://127.0.0.1:8001
```

Copy the HTTPS URL from the output, e.g.:

```text
https://random-words-here.trycloudflare.com
```

**Important:** This URL changes every time you restart the tunnel. Re-run the patch script after each restart.

### Verify tunnel before Retell

```powershell
$host = "https://random-words-here.trycloudflare.com"
Invoke-WebRequest `
  -Uri "$host/api/v1/voice-agent/get_current_date?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37" `
  -Headers @{"X-Voice-Agent-Secret"="otto-retell-voice-agent-dev-secret-change-me"} `
  -UseBasicParsing
```

Expect **200** and JSON `{"datetime":"..."}` — not HTML.

## 3. Patch agent JSON for import

Use your **real** Cloudflare URL (not a placeholder):

```powershell
cd backend
python scripts/patch_retell_agent.py --host https://random-words-here.trycloudflare.com
```

Output: `docs/AUTO_RETELL_AGENT.local.json`

## 4. Import into Retell

1. Retell Dashboard → **Agents** → **Import from JSON**
2. Upload `docs/AUTO_RETELL_AGENT.local.json`
3. **Publish** the agent
4. Confirm **Dynamic variables** include `company_id` (set by patch script)
5. Copy the **agent_id** for webhook mapping if needed

## 5. Post-call webhook

In Retell agent settings, set webhook URL:

```
https://YOUR-URL.trycloudflare.com/api/v1/webhooks/retell/call-ended
```

Retell sends `X-Retell-Signature`; Otto verifies with `RETELL_API_KEY`.

## 6. Test

### API smoke test

```powershell
Invoke-WebRequest `
  -Uri "https://YOUR-URL.trycloudflare.com/api/v1/voice-agent/get_current_date?company_id=ce9091df-db37-4e7e-877c-2ed0cf2f4c37" `
  -Headers @{"X-Voice-Agent-Secret"="otto-retell-voice-agent-dev-secret-change-me"} `
  -UseBasicParsing
```

### Retell LLM Playground

1. Open agent → **Test LLM** → Manual chat
2. Disable mock functions when backend is up
3. Say: *"Hi, I'm John, my tile roof is leaking — can we book Thursday at 10?"*
4. Watch tool calls return HTTP 200 in Retell logs

### Verify in Otto

After a test call:

- New **lead** with `lead_source = voice_agent`
- **Contact card** `property_snapshot` (if property path ran)
- **Appointment** (if booked)
- **pending_actions** row for rep follow-up
- **follow_up_otto** proposed draft (async)

## API reference

All tools use header `X-Voice-Agent-Secret` and base path `/api/v1/voice-agent/`:

| Tool | Method | Path |
|------|--------|------|
| search_lead | POST | `/search_lead` |
| create_lead | POST | `/create_lead` |
| get_customer_history | POST | `/get_customer_history` |
| save_property_details | POST | `/save_property_details` |
| update_lead | POST | `/update_lead` |
| get_current_date | GET | `/get_current_date?company_id=` |
| get_available_slots | GET | `/get_available_slots?company_id=&date=` |
| create_appointment | POST | `/create_appointment` |
| create_pending_action | POST | `/create_pending_action` |
| generate_followup | POST | `/generate_followup` |
| surface_next_actions | POST | `/surface_next_actions` |
| send_sms | POST | `/send_sms` |
| send_email | POST | `/send_email` |
| save_call_summary | POST | `/save_call_summary` |
| save_recording_analysis | POST | `/save_recording_analysis` |

Post-call ingest (preferred for transcripts): `POST /api/v1/webhooks/retell/call-ended`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 401 on tools | Match `X-Voice-Agent-Secret` to `.env` |
| 404 HTML from tunnel | Use real `trycloudflare.com` URL; re-run patch script (not `YOUR-REAL.ngrok-free.app`) |
| 404 on tools | Re-run patch script after tunnel URL changes |
| Empty `company_id` | Set `retell_llm_dynamic_variables` or pass in tool args |
| No slots | Configure `tenant_config.business_hours` for the company |
| SMS skipped | Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_SYSTEM_NUMBER` |

## Tests

```powershell
cd backend
pytest app/tests/test_voice_agent.py -q
```
