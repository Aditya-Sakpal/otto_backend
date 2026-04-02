from pathlib import Path

p = Path("app/services/call_service.py")
text = p.read_text(encoding="utf-8")
for i, line in enumerate(text.splitlines()):
    if "pending_action" in line or "pending_action_repo" in line:
        start = max(0, i-5)
        end = min(len(text.splitlines()), i+6)
        print("---- Match at line", i+1, "----")
        for j in range(start, end):
            print(f"{j+1:5d}: {text.splitlines()[j]}")
        print()

