# Quick Cloudflare Tunnel to local Otto backend (port 8001).
# Requires cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/
#
# Usage (from backend/):
#   .\scripts\start_cloudflare_tunnel.ps1
#
# Copy the https://....trycloudflare.com URL, then:
#   python scripts/patch_retell_agent.py --host https://....trycloudflare.com

$ErrorActionPreference = "Stop"
$Port = if ($env:OTTO_PORT) { $env:OTTO_PORT } else { "8001" }
$LocalUrl = "http://127.0.0.1:$Port"

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $fallback = Join-Path $PSScriptRoot "..\tools\cloudflared.exe"
    if (Test-Path $fallback) {
        $cloudflared = @{ Source = (Resolve-Path $fallback).Path }
    }
}

if (-not $cloudflared) {
    Write-Host "cloudflared not found." -ForegroundColor Red
    Write-Host "Install: winget install Cloudflare.cloudflared"
    Write-Host "Or download: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    exit 1
}

Write-Host "Tunneling $LocalUrl -> public HTTPS (trycloudflare.com)" -ForegroundColor Cyan
Write-Host "After URL appears, run:" -ForegroundColor Yellow
Write-Host "  python scripts/patch_retell_agent.py --host https://YOUR-URL.trycloudflare.com" -ForegroundColor Yellow
Write-Host ""

if ($cloudflared.Source) {
    & $cloudflared.Source tunnel --url $LocalUrl
} else {
    cloudflared tunnel --url $LocalUrl
}
