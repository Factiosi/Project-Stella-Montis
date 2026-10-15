"""Repository root and the files the process reads or writes besides the code.

Source runs root at the directory of `psm.py`; settings and the baseline sit
there too. A Nuitka standalone build roots at the executable directory for
read-only `assets/`, sets the process cwd there before Tk starts (shell
shortcuts often leave cwd on System32), and keeps writable state under
`%LOCALAPPDATA%\\Project Stella Montis`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _is_compiled() -> bool:
    if globals().get("__compiled__") is not None:
        return True
    main = sys.modules.get("__main__")
    if main is not None and getattr(main, "__compiled__", None) is not None:
        return True
    exe = Path(sys.executable)
    return exe.suffix.lower() == ".exe" and "python" not in exe.name.lower()


def _install_root() -> Path:
    return Path(sys.executable).resolve().parent


def _source_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _root() -> Path:
    if _is_compiled():
        return _install_root()
    return _source_root()


def _writable_root() -> Path:
    if _is_compiled():
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "Project Stella Montis"
    return _root()


def prepare_install_layout() -> None:
    """Call before Tk on a frozen build: cwd beside the exe, state dir exists."""
    if not _is_compiled():
        return
    os.chdir(_root())
    _writable_root().mkdir(parents=True, exist_ok=True)


ROOT = _root()
ASSETS = ROOT / "assets"

TEMPLATE_PATH = ASSETS / "esc_template.npy"
ICON_PATH = ASSETS / "icon.ico"
INI_PATH = _writable_root() / "PSM.ini"
BASELINE_PATH = _writable_root() / "psm_baseline.dat"
