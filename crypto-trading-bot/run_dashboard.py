#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> None:
    app_path = ROOT / "dashboard" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.address",
        "0.0.0.0",
        "--server.port",
        "8501",
        "--browser.gatherUsageStats",
        "false",
    ]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
