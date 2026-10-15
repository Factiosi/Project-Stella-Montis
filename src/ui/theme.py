"""Arc Raiders palette: near-black, cream, one gold, four signal stripes.

Bahnschrift stands in for Barlow (not shipped). JetBrains Mono for HUD digits.
"""

from __future__ import annotations

from collections.abc import Sequence
from tkinter import font as tkfont

BG = "#111111"
SURFACE = "#181818"
SURFACE_HI = "#202020"
RULE = "#2c2c2c"
RULE_SOFT = "#1f1f1f"
CREAM = "#ece2d0"
CREAM_DIM = "#8b8478"
GOLD = "#f1aa1c"
GOLD_HI = "#ffc247"
GOLD_DIM = "#5d4310"
INK = "#111111"
STRIPES = ("#e0442f", "#f1aa1c", "#4fae63", "#3fa9e0")
OVERLAY_GREEN = "#3ddc5a"
# Color-key for WS_EX_LAYERED. Must not appear in drawn pixels.
OVERLAY_KEY = "#010101"

CONTENT_WIDTH = 460

Font = tuple[str, int, str]

_families: dict[str, str] = {}


def _pick(kind: str, candidates: Sequence[str], fallback: str) -> str:
    """First installed family. `tkfont.families()` needs a Tk root."""
    if kind not in _families:
        try:
            installed = set(tkfont.families())
        except RuntimeError:
            installed = set()
        _families[kind] = next((name for name in candidates if name in installed), fallback)
    return _families[kind]


def font_text(size: int, weight: str = "normal") -> Font:
    """UI grotesque."""
    return (_pick("text", ("Bahnschrift", "Segoe UI Variable Text", "Segoe UI"), "Segoe UI"), size, weight)


def font_mono(size: int, weight: str = "normal") -> Font:
    """HUD / numeric mono."""
    return (_pick("mono", ("JetBrains Mono", "Cascadia Mono", "Consolas"), "Courier New"), size, weight)
