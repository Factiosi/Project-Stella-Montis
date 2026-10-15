"""Settings dataclass, clamp bounds, and the `[psm]` INI next to the entry point."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import INI_PATH
from modules.weights import DEFAULT_PRESET, PRESETS, Point, normalize_points

GAMMA_RANGE = (1.0, 4.0)
THRESHOLD_MAX = 0.40
CAPTURE_MS_RANGE = (16, 200)
MENU_MS_MAX = 500
DIAMETER_RANGE = (50, 100)

INI_SECTION = "psm"


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


@dataclass
class Settings:
    gamma_max: float = 1.8
    gamma_min: float = 1.0
    manual: bool = False
    manual_gamma: float = 1.0
    threshold: float = 0.05
    capture_ms: int = 80
    menu_ms: int = 500
    diameter_pct: int = 90
    compute: str = "gpu"
    curve: list[Point] = field(default_factory=lambda: list(PRESETS[DEFAULT_PRESET]))

    def clamped(self) -> Settings:
        """Return a copy with every field inside its declared range."""
        gamma_max = _clamp(float(self.gamma_max), *GAMMA_RANGE)
        gamma_min = _clamp(float(self.gamma_min), GAMMA_RANGE[0], gamma_max)
        capture_ms = int(_clamp(int(self.capture_ms), *CAPTURE_MS_RANGE))
        return Settings(
            gamma_max=gamma_max,
            gamma_min=gamma_min,
            manual=bool(self.manual),
            manual_gamma=_clamp(float(self.manual_gamma), *GAMMA_RANGE),
            threshold=_clamp(float(self.threshold), 0.0, THRESHOLD_MAX),
            capture_ms=capture_ms,
            menu_ms=int(_clamp(int(self.menu_ms), capture_ms, MENU_MS_MAX)),
            diameter_pct=int(_clamp(int(self.diameter_pct), *DIAMETER_RANGE)),
            compute="cpu" if str(self.compute).lower() == "cpu" else "gpu",
            curve=normalize_points(self.curve),
        )


def parse_curve(text: str) -> list[Point]:
    """Parse `x:y` pairs; skip tokens that are not two floats."""
    points: list[Point] = []
    for chunk in text.replace(";", " ").split():
        left, _, right = chunk.partition(":")
        if not right:
            continue
        try:
            points.append((float(left), float(right)))
        except ValueError:
            continue
    return normalize_points(points)


def format_curve(points: list[Point]) -> str:
    return " ".join(f"{x:.1f}:{y:.1f}" for x, y in points)


def load_settings(path: Path = INI_PATH) -> Settings:
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")
    section = parser[INI_SECTION] if parser.has_section(INI_SECTION) else {}
    defaults = Settings()

    def number(key: str, default: float) -> float:
        try:
            return float(section.get(key, str(default)))
        except (TypeError, ValueError):
            return default

    def flag(key: str, default: bool) -> bool:
        return section.get(key, "1" if default else "0").strip().lower() in {"1", "true", "yes", "on"}

    curve_text = section.get("curve", "")
    return Settings(
        gamma_max=number("gamma_max", defaults.gamma_max),
        gamma_min=number("gamma_min", defaults.gamma_min),
        manual=flag("manual", defaults.manual),
        manual_gamma=number("manual_gamma", defaults.manual_gamma),
        threshold=number("threshold", defaults.threshold),
        capture_ms=int(number("capture_ms", defaults.capture_ms)),
        menu_ms=int(number("menu_ms", defaults.menu_ms)),
        diameter_pct=int(number("diameter_pct", defaults.diameter_pct)),
        compute=section.get("compute", defaults.compute),
        curve=parse_curve(curve_text) if curve_text else list(defaults.curve),
    ).clamped()


def save_settings(settings: Settings, path: Path = INI_PATH) -> None:
    current = settings.clamped()
    parser = configparser.ConfigParser()
    parser[INI_SECTION] = {
        "gamma_max": f"{current.gamma_max:.2f}",
        "gamma_min": f"{current.gamma_min:.2f}",
        "manual": "1" if current.manual else "0",
        "manual_gamma": f"{current.manual_gamma:.2f}",
        "threshold": f"{current.threshold:.2f}",
        "capture_ms": str(current.capture_ms),
        "menu_ms": str(current.menu_ms),
        "diameter_pct": str(current.diameter_pct),
        "compute": current.compute,
        "curve": format_curve(current.curve),
    }
    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)
