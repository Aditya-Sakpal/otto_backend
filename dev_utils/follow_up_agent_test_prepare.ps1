<#
.SYNOPSIS
  Point 1–2 qualified-unbooked test leads at your phone and optionally reset local SQLite log rows.

.PARAMETER Phone
  Your mobile in E.164, e.g. +15551234567 (required).

.PARAMETER LocalDb
  Path to follow_up.db if you use a non-default location.

.EXAMPLE
  .\follow_up_agent_test_prepare.ps1 -Phone '+15551234567'
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $Phone,

    [string] $LocalDb = ""
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$envFile = Join-Path $root ".env"
$raw = Get-Content $envFile -Raw
if ($raw -notmatch 'DATABASE_URL=(.+)') { throw "DATABASE_URL not found in .env" }
$url = ($Matches[1] -split "`n")[0].Trim().Trim('"')

# Two Q1 leads with call_analyses.summary (same company as first block in COMPANY_CONFIGS).
$contactA = "5017bc07-3586-455a-93ff-3d8ef8a56229"
$contactB = "16b559b5-3308-426e-a54a-0597859abc37"
$leadA = "b0ae4dd6-a5d7-4802-99c6-51dd5314e91f"
$leadB = "00b28e91-5271-4136-a2d8-fbbe3dd96232"

$esc = $Phone.Replace("'", "''")
$sql = @"
BEGIN;
UPDATE contact_cards SET primary_phone = '$esc'
  WHERE id IN ('$contactA'::uuid, '$contactB'::uuid);
UPDATE leads SET created_at = created_at - INTERVAL '30 days', updated_at = NOW()
  WHERE id IN ('$leadA'::uuid, '$leadB'::uuid);
COMMIT;
SELECT id, primary_phone FROM contact_cards WHERE id IN ('$contactA'::uuid, '$contactB'::uuid);
"@

Write-Host "Updating Postgres contact_cards + backdating leads (cadence due)..."
psql $url -v ON_ERROR_STOP=1 -c $sql

if ($LocalDb -and (Test-Path $LocalDb)) {
    Write-Host "Removing follow_up_log rows for test leads in $LocalDb ..."
    sqlite3 $LocalDb "DELETE FROM follow_up_log WHERE lead_id IN ('$leadA','$leadB');"
}

Write-Host @"

Next (one lead at a time — avoids full-queue SMS). From repo backend folder:

  cd `"$($root.Path)\backend`"
  `$env:PYTHONPATH = `"app\agents`"
  `$env:AUTO_EXECUTE = `"true`"
  `$env:DRY_RUN = `"false`"
  python -m contextual_follow_up_agent --lead-id $leadA

Repeat with --lead-id $leadB if needed.

Do NOT leave AUTO_EXECUTE=true in .env if Celery runs the follow-up task on a schedule.
"@
