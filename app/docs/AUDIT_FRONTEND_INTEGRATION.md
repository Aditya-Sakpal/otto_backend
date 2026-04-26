# Frontend Work — Audit Fixes

What the frontend team needs to change to finish the audit fixes. The backend is already live on stage.

Nothing in the API has been removed or renamed. Everything new is optional. If you do nothing, the app keeps working like before. Doing the steps below makes it work better.

---

## Nothing to do — confirmed with product

These three items looked like frontend bugs in the audit but are intentional. Skip them:

- **#12** — "None Detected" text shown when a lead has no objection. Planned. Keep as is.
- **#17, #24** — "Unknown Lead" / "Unknown Customer" shown when the name is null. Planned. Keep as is.

## Blocked — needs product decision

- **#14, #17, #18** — the audit mentions a "Pending" column on the pipeline board. There is no `"pending"` stage in the pipeline config or the backend `PipelineStage` enum today. If product wants a Pending column, @Aditya Sakpal has to update the enum and `PIPELINE_CONFIG` first. Don't add UI for it yet.

---

## New fields the API sends

### `analysis_status` — tells you if the AI analysis is ready

Every call or appointment response now has an `analysis_status` field. It can be one of:

- `"completed"` — data is good, render normally
- `"pending"` or `"processing"` — AI is still running, show a spinner
- `"failed"` — AI failed, show a retry button
- `"not_analyzed"` or `null` — no analysis exists yet

Where to read it:

| Endpoint | Path in the response |
|---|---|
| `GET /calls/logs` | each item in `calls[]` |
| `GET /calls/{id}` | top level |
| `GET /appointments` and `GET /appointments/{id}` | top level |
| `GET /recordings/{id}/analysis` | top level (was already there) |

### Appointment quality flags

Appointments now tell you when the data is questionable. Check these keys inside `extra_metadata`:

```json
{
  "extra_metadata": {
    "time_quality": "low_confidence",
    "location_quality": "low",
    "analysis_failure": {
      "source": "...",
      "detail": "...",
      "recorded_at": "..."
    }
  }
}
```

- `time_quality: "low_confidence"` — the time is odd (like 1 AM). Show a warning.
- `location_quality: "low"` — the address is missing or just a state. Show "Address needed".
- `analysis_failure` — only set when the sales-audio analysis failed. Use `detail` in the retry message.

All three keys are optional. Check before reading.

---

## Things that changed in the API

### `GET /recordings/{id}/analysis` now returns 200 for failed
Before: 404 on anything that wasn't `completed`.
Now:
- `completed` → 200 with full data (same as before)
- `failed` → **200 with null fields and `analysis_status: "failed"`** (new)
- `pending` / `processing` / missing → 404 (same as before)

So when you get a 200, check `analysis_status` before rendering.

### `POST /recordings/complete` can return `"failed"`
The `status` field in the response can now be `"failed"` when Shoonya couldn't take the job. Handle it the same way you'd handle any error — show a retry button.

### Cross-tenant requests get 403
If something sends a `company_id` that doesn't belong to the user, `/metrics/*` and `/users/sales-reps` return 403. This should not happen in normal flows, but add basic 403 handling just in case.

### `is_booked` and `is_qualified` can be `null`
In Call Logs these used to always be `true` or `false`. Now they can be `null` when the analysis hasn't run yet. The simple check `log.is_booked ? "Yes" : "No"` still works (null reads as "No"). A better UI uses `analysis_status` — see the Call Logs section below.

### Appointment `location_address` can be `null`
Instead of showing "AZ, US" as a fake address, low-quality addresses are now `null`. Show "Address needed" when this happens.

### Appointments can auto-switch from pending to no_show
If an appointment was scheduled more than 24 hours ago and has no recording, the outcome auto-changes from `"pending"` to `"no_show"`. You don't have to do anything. Just know it happens.

---

## Retry endpoints — wire these to your "Retry analysis" buttons

When `analysis_status === "failed"` on a call or appointment, the frontend can re-submit the audio for analysis by calling one of these:

### `POST /api/v1/recordings/{appointment_id}/retry`

Use this on the Appointments list row and on the Recording Analysis page. No request body needed.

**Responses:**

| HTTP | When | Body |
|---|---|---|
| `202` | Re-submitted to Shoonya | `{ appointment_id, analysis_status: "processing", processing_job_id }` |
| `202` | Shoonya rejected the re-submission immediately | `{ appointment_id, analysis_status: "failed", processing_job_id: null }` — show another retry |
| `404` | Appointment not found, or has no `audio_url` to retry against | error |
| `409` | Appointment is already `analysis_status === "processing"` — don't call again | error |
| `503` | Shoonya service is down — surface "Analysis service unavailable, try later" | error |
| `403` | Caller doesn't belong to the appointment's tenant (should not happen in normal flows) | error |

After a 202, poll `GET /api/v1/appointments/{id}` (or `/recordings/{id}/analysis` once complete) to watch `analysis_status` transition to `"completed"`.

### `POST /api/v1/calls/{call_id}/retry`

Use this on the Call Logs row (or call detail page) when `analysis_status === "failed"`. No request body.

**Responses** — same matrix as recordings retry, with `call_id` in place of `appointment_id`:

| HTTP | When | Body |
|---|---|---|
| `202` | Re-submitted | `{ call_id, analysis_status: "processing", processing_job_id }` |
| `202` | Shoonya rejected immediately | `{ call_id, analysis_status: "failed", processing_job_id: null }` |
| `404` | Call not found or has no `audio_url` | error |
| `409` | Analysis already in progress | error |
| `503` | Shoonya down | error |
| `403` | Cross-tenant | error |

After a 202, poll `GET /api/v1/calls/{id}` or refresh the Call Logs list — `analysis_status` will flip to `"completed"` (or back to `"failed"`) when Shoonya finishes.

### Recommended UX for the button

```tsx
async function handleRetry(id: string, kind: "recording" | "call") {
  const path = kind === "recording"
    ? `/api/v1/recordings/${id}/retry`
    : `/api/v1/calls/${id}/retry`;
  const res = await apiClient.post(path);
  if (res.status === 202) {
    // analysis_status will be "processing" or "failed" — use the body
    updateLocalRow(id, res.data);
  } else if (res.status === 409) {
    toast("Analysis already in progress. Give it a moment.");
  } else if (res.status === 503) {
    toast("Analysis service is temporarily down. Try again later.");
  } else if (res.status === 404) {
    toast("Nothing to retry — no audio was uploaded for this record.");
  }
}
```

---

## What to add on each page

### Call Logs page

In the Booked column, replace:
```tsx
log.is_booked ? "Yes" : "No"
```
with something like:
```tsx
log.analysis_status === "failed"     ? <Badge>Analysis failed</Badge>
: log.analysis_status !== "completed" ? <Badge>Analyzing…</Badge>
: log.is_booked                        ? <Badge>Yes</Badge>
:                                        <Badge>No</Badge>
```

In the Objections column, when `log.analysis_status === "failed"`, show "Analysis failed" instead of "No objections".

### Appointments List page

For each row:
- If `extra_metadata?.time_quality === "low_confidence"` → show a small warning next to the time. Tooltip: "Time may be wrong. Please check."
- If `location_address` is `null` and `extra_metadata?.location_quality === "low"` → show "Address needed" in the address column.
- If `analysis_status === "failed"` → show a "Retry analysis" button. Use `extra_metadata?.analysis_failure?.detail` in the message.

Nothing to do for #36, #37, or #39 — the data is now correct on its own.

### Recording Analysis page

When you get a 200 response:
- If `analysis_status === "failed"` → show "Retry analysis". Don't render the null fields as if they were real data. Optionally show `extra_metadata.analysis_failure.detail` for debug.
- If `analysis_status === "completed"` → render as before.

When you get a 404, keep the spinner like today.

---

## Checklist

- [x] Fix date format (#41)
- [x] Remove fake reps on empty team (#46)
- [ ] Build a shared "analysis state" pill that maps `analysis_status` to a label
- [ ] Use that pill in the Call Logs Booked and Objections columns
- [ ] Handle 200-with-failed on `GET /recordings/{id}/analysis`
- [ ] Handle `status: "failed"` on `POST /recordings/complete`
- [ ] Add warning icons for `time_quality` and `location_quality` on the Appointments list
- [ ] Wire "Retry analysis" button to `POST /api/v1/recordings/{id}/retry` on appointment rows / recording page
- [ ] Wire "Retry analysis" button to `POST /api/v1/calls/{id}/retry` on call log rows / call detail
- [ ] Handle 409 / 503 / 404 on both retry endpoints with user-visible messages
