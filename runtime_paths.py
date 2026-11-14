"""Keep installed user data separate from bundled application files."""

import os
import sys
from pathlib import Path


FROZEN = bool(getattr(sys, "frozen", False))
PACKAGE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
if FROZEN:
    local_app_data = os.environ.get("LOCALAPPDATA")
    DATA_DIR = (Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local") / "红烧box"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PACKAGE_DIR / "ms-playwright")
else:
    DATA_DIR = PACKAGE_DIR
