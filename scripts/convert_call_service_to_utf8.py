from pathlib import Path

src = Path("app/services/call_service.py")
if not src.exists():
    print("Source missing", src)
    raise SystemExit(1)

try:
    text = src.read_text(encoding="utf-8")
    # if this succeeds and contains NULs, fallthrough to try utf-16-le
    if "\\x00" in text[:100]:
        raise UnicodeError("Detected NULs in utf-8 read, will try utf-16-le")
except Exception:
    text = src.read_text(encoding="utf-16-le")
    print("Read using utf-16-le")

src.write_text(text, encoding="utf-8")
print("Converted call_service.py to utf-8")

