"""Repository root and the three files the process writes or reads besides the code."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / "assets"

TEMPLATE_PATH = ASSETS / "esc_template.npy"
INI_PATH = ROOT / "PSM.ini"
BASELINE_PATH = ROOT / "psm_baseline.dat"
