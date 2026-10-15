"""Repository root and the files the process reads or writes besides the code.

A source run roots at the directory of `psm.py`. A Nuitka standalone build
roots at the executable: `assets/` and the runtime files are installed beside
it. This is not a onefile build — there `sys.executable` is the temp extract
and the baseline would not survive.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _root() -> Path:
    if "__compiled__" in globals():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


ROOT = _root()
ASSETS = ROOT / "assets"

TEMPLATE_PATH = ASSETS / "esc_template.npy"
ICON_PATH = ASSETS / "icon.ico"
INI_PATH = ROOT / "PSM.ini"
BASELINE_PATH = ROOT / "psm_baseline.dat"
