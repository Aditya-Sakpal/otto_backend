#!/usr/bin/env python3
"""Patch AUTO_RETELL_AGENT.json for local Retell import (ngrok host + secrets)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "AUTO_RETELL_AGENT.json"
DEFAULT_OUT = ROOT / "docs" / "AUTO_RETELL_AGENT.local.json"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
        load_dotenv(ROOT.parent / ".env")
    except ImportError:
        pass


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Patch Retell agent JSON for local import")
    parser.add_argument("--host", required=True, help="Public HTTPS base URL, e.g. https://abc.ngrok-free.app")
    parser.add_argument("--secret", default=os.getenv("VOICE_AGENT_SECRET", ""), help="X-Voice-Agent-Secret value")
    parser.add_argument(
        "--company-id",
        default=os.getenv("VOICE_AGENT_DEFAULT_COMPANY_ID", ""),
        help="Default company UUID for retell_llm_dynamic_variables",
    )
    parser.add_argument("--output", default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    if not args.secret:
        print("Warning: VOICE_AGENT_SECRET not set; tools will use empty secret header", file=sys.stderr)

    placeholder_markers = ("YOUR.ngrok", "YOUR-REAL", "example.ngrok", "placeholder")
    if any(m.lower() in host.lower() for m in placeholder_markers):
        print(
            f"Error: --host looks like a placeholder ({host}). "
            "Start Cloudflare tunnel or ngrok and pass the real HTTPS URL.",
            file=sys.stderr,
        )
        return 1

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    raw = json.dumps(data)
    raw = raw.replace("https://AUTO_HOST", host)
    raw = raw.replace("REPLACE_WITH_SHARED_SECRET", args.secret)
    if args.company_id:
        raw = raw.replace("REPLACE_WITH_COMPANY_UUID", args.company_id)
        raw = raw.replace("{{company_id}}", args.company_id)
    out = json.loads(raw)
    out_path = Path(args.output)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
