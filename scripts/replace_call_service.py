from pathlib import Path
import shutil

src = Path("app/services/call_service_fixed.py")
dst = Path("app/services/call_service.py")
if not src.exists():
    print("Source fixed file not found:", src)
else:
    shutil.copyfile(src, dst)
    print("Copied", src, "to", dst)

