"""Weight mask for the sampling circle.

Curve points are (x, y) in percent: x = area share from the center,
y = cumulative influence inside that area. Ends are pinned at (0, 0) and
(100, 100). Pixel weight is the polyline slope dy/dx at u = (d/R)^2, so
the first segment (0, 0)→(x1, y1) is a plateau of density y1/x1.

The grid covers the circle's bounding square and is independent of game
resolution. Recompute only when the points change.
"""

from __future__ import annotations

import numpy as np

GRID = 96
MAX_USER_POINTS = 4

Point = tuple[float, float]

PRESETS: dict[str, list[Point]] = {
    "classic": [(50.0, 70.0)],  # 70% of influence inside 50% of area
    "center": [(50.0, 100.0)],  # zero weight past the inner half
    "flat": [],  # constant slope 1
}
DEFAULT_PRESET = "classic"


def normalize_points(points: list[Point] | tuple[Point, ...]) -> list[Point]:
    """At most four points; x in (0, 100), both axes non-decreasing, Δx ≥ 0.5."""
    cleaned: list[Point] = []
    for raw in points:
        try:
            x_val, y_val = float(raw[0]), float(raw[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not (np.isfinite(x_val) and np.isfinite(y_val)):
            continue
        cleaned.append((min(99.5, max(0.5, x_val)), min(100.0, max(0.0, y_val))))
    cleaned.sort(key=lambda item: item[0])

    result: list[Point] = []
    last_x, last_y = 0.0, 0.0
    for x_val, y_val in cleaned[:MAX_USER_POINTS]:
        x_val = max(x_val, last_x + 0.5)
        if x_val > 99.5:
            break
        y_val = max(y_val, last_y)
        result.append((x_val, y_val))
        last_x, last_y = x_val, y_val
    return result


def full_curve(points: list[Point]) -> tuple[np.ndarray, np.ndarray]:
    """Nodes including pinned ends, in 0..1."""
    xs = [0.0, *(p[0] for p in points), 100.0]
    ys = [0.0, *(p[1] for p in points), 100.0]
    return np.asarray(xs, dtype=np.float64) / 100.0, np.asarray(ys, dtype=np.float64) / 100.0


def curve_slope(points: list[Point], u: np.ndarray) -> np.ndarray:
    """Segment slope at each u in 0..1."""
    xs, ys = full_curve(points)
    slopes = np.diff(ys) / np.diff(xs)
    u = np.clip(np.asarray(u, dtype=np.float64), 0.0, 1.0)
    idx = np.clip(np.searchsorted(xs, u, side="right") - 1, 0, len(slopes) - 1)
    return np.maximum(slopes[idx], 0.0)


def curve_value(points: list[Point], u: np.ndarray) -> np.ndarray:
    """Polyline Y at each u in 0..1."""
    xs, ys = full_curve(points)
    u = np.clip(np.asarray(u, dtype=np.float64), 0.0, 1.0)
    return np.interp(u, xs, ys)


def _area_shares() -> tuple[np.ndarray, np.ndarray]:
    coords = (np.arange(GRID, dtype=np.float64) + 0.5) / GRID * 2.0 - 1.0
    x_pos, y_pos = np.meshgrid(coords, coords)
    u = x_pos * x_pos + y_pos * y_pos
    return u, u < 1.0


def circle_weights(points: list[Point]) -> np.ndarray:
    """GRID×GRID mask, sum 1, zero outside the unit disk."""
    u, inside = _area_shares()
    weights = np.zeros((GRID, GRID), dtype=np.float64)
    weights[inside] = curve_slope(points, u[inside])
    total = float(weights.sum())
    if total <= 0.0:
        weights[inside] = 1.0
        total = float(weights.sum())
    return (weights / total).astype(np.float32)


def inner_share(points: list[Point], area_fraction: float) -> float:
    """Influence mass inside `area_fraction` of the disk. For checks, not the loop."""
    u, _inside = _area_shares()
    return float(circle_weights(points)[u <= area_fraction].sum())
