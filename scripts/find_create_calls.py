from pathlib import Path

text = Path("app/services/call_service.py").read_text(encoding="utf-8")
lines = text.splitlines()
for i, line in enumerate(lines):
    if "create(" in line and "pending_action" in ''.join(lines[i-3:i+4]):
        print("Context around line", i+1)
        for j in range(max(0, i-3), min(len(lines), i+4)):
            print(f"{j+1:4d}: {lines[j]}")
        print()

