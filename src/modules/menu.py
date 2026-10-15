"""ESC-button detector for the Arc Raiders inventory / pause menu.

Match is gradient-magnitude correlation against `assets/esc_template.npy`
(39×62 float32), so letter polarity (dark-on-light vs light-on-dark) does
not matter. Exact `KNOWN_BOXES` first; ±SLACK search only when that score
is inconclusive (0.20–0.70).
"""

from __future__ import annotations

import numpy as np

from core.paths import TEMPLATE_PATH

# Inclusive client-space boxes, keyed by PioneerGame client size.
KNOWN_BOXES: dict[tuple[int, int], tuple[int, int, int, int]] = {
    (1920, 1080): (53, 1019, 99, 1049),
    (2560, 1440): (71, 1359, 133, 1398),
}
TEMPLATE_W = 62
TEMPLATE_H = 39
SLACK = 3
CORR_MIN = 0.45

Box = tuple[int, int, int, int]


def load_template() -> np.ndarray:
    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(str(TEMPLATE_PATH))
    return np.load(TEMPLATE_PATH).astype(np.float32)


def button_box(width: int, height: int) -> Box:
    """Known box, or the nearest known size scaled by width and height."""
    exact = KNOWN_BOXES.get((width, height))
    if exact is not None:
        return exact
    ref_w, ref_h = min(KNOWN_BOXES, key=lambda size: abs(size[1] - height))
    x1, y1, x2, y2 = KNOWN_BOXES[(ref_w, ref_h)]
    scale_x, scale_y = width / ref_w, height / ref_h
    left, top = int(round(x1 * scale_x)), int(round(y1 * scale_y))
    return left, top, max(left + 8, int(round(x2 * scale_x))), max(top + 8, int(round(y2 * scale_y)))


def capture_region(
    origin_x: int,
    origin_y: int,
    width: int,
    height: int,
    monitor_left: int,
    monitor_top: int,
) -> tuple[Box, Box]:
    """(monitor grab rect with slack, button box inside that grab)."""
    x1, y1, x2, y2 = button_box(width, height)
    cap_x1, cap_y1 = max(0, x1 - SLACK), max(0, y1 - SLACK)
    cap_x2, cap_y2 = min(width, x2 + SLACK), min(height, y2 + SLACK)
    region = (
        origin_x + cap_x1 - monitor_left,
        origin_y + cap_y1 - monitor_top,
        origin_x + cap_x2 - monitor_left,
        origin_y + cap_y2 - monitor_top,
    )
    local_box = (x1 - cap_x1, y1 - cap_y1, x2 - cap_x1, y2 - cap_y1)
    return region, local_box


def frame_luma(frame: np.ndarray) -> np.ndarray:
    """Rec. 709 luma from BGRA."""
    return 0.2126 * frame[:, :, 2] + 0.7152 * frame[:, :, 1] + 0.0722 * frame[:, :, 0]


def resize_luma(luma: np.ndarray, width: int, height: int) -> np.ndarray:
    """Bilinear resize. Kept in numpy so capture does not depend on PIL."""
    if luma.shape == (height, width):
        return luma
    ys = np.linspace(0, luma.shape[0] - 1, height)
    xs = np.linspace(0, luma.shape[1] - 1, width)
    y0 = np.floor(ys).astype(np.int32)
    x0 = np.floor(xs).astype(np.int32)
    y1 = np.minimum(y0 + 1, luma.shape[0] - 1)
    x1 = np.minimum(x0 + 1, luma.shape[1] - 1)
    wy = (ys - y0).astype(np.float32)[:, None]
    wx = (xs - x0).astype(np.float32)[None, :]
    top = luma[y0][:, x0] * (1.0 - wx) + luma[y0][:, x1] * wx
    bottom = luma[y1][:, x0] * (1.0 - wx) + luma[y1][:, x1] * wx
    return (top * (1.0 - wy) + bottom * wy).astype(np.float32)


def edge_magnitude(luma: np.ndarray) -> np.ndarray:
    if luma.shape != (TEMPLATE_H, TEMPLATE_W):
        luma = resize_luma(luma, TEMPLATE_W, TEMPLATE_H)
    gradient_y, gradient_x = np.gradient(luma)
    return np.hypot(gradient_x, gradient_y).astype(np.float32)


def _correlation(found: np.ndarray, reference: np.ndarray, reference_norm: float) -> float:
    found = found - found.mean()
    denom = float(np.linalg.norm(found) * reference_norm)
    return 0.0 if denom < 1e-6 else float((found * reference).sum() / denom)


def match_patch(luma: np.ndarray, template: np.ndarray) -> float:
    """Normalized correlation of edge magnitudes, exact crop vs template."""
    reference = template - template.mean()
    return _correlation(edge_magnitude(luma), reference, float(np.linalg.norm(reference)))


_EDGE_TEMPLATES: dict[tuple[int, int], list[tuple[int, int, np.ndarray, float]]] = {}


def edge_templates_for(base_w: int, base_h: int, template: np.ndarray) -> list[tuple[int, int, np.ndarray, float]]:
    """Centered, normed templates for every (w, h) in ±2·SLACK of the base box."""
    key = (base_w, base_h)
    cached = _EDGE_TEMPLATES.get(key)
    if cached is not None:
        return cached
    prepared: list[tuple[int, int, np.ndarray, float]] = []
    for height in range(base_h - 2 * SLACK, base_h + 2 * SLACK + 1):
        for width in range(base_w - 2 * SLACK, base_w + 2 * SLACK + 1):
            if width < 8 or height < 8:
                continue
            resized = resize_luma(template, width, height)
            centered = resized - resized.mean()
            norm = float(np.linalg.norm(centered))
            if norm >= 1e-6:
                prepared.append((width, height, centered, norm))
    _EDGE_TEMPLATES[key] = prepared
    return prepared


def search_match(luma: np.ndarray, template: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> float:
    """Best correlation over all boxes whose edges stay within ±SLACK of the seed."""
    frame_h, frame_w = luma.shape
    gradient_y, gradient_x = np.gradient(luma)
    edges = np.hypot(gradient_x, gradient_y).astype(np.float32)
    best = -1.0
    base_w, base_h = x2 - x1, y2 - y1
    for width, height, reference, reference_norm in edge_templates_for(base_w, base_h, template):
        left_from = max(0, x2 - SLACK - width, x1 - SLACK)
        left_to = min(frame_w - width, x2 + SLACK - width, x1 + SLACK)
        top_from = max(0, y2 - SLACK - height, y1 - SLACK)
        top_to = min(frame_h - height, y2 + SLACK - height, y1 + SLACK)
        for top in range(top_from, top_to + 1):
            for left in range(left_from, left_to + 1):
                score = _correlation(edges[top : top + height, left : left + width], reference, reference_norm)
                if score > best:
                    best = score
    return best


def button_visible(frame_bgra: np.ndarray, template: np.ndarray, local_box: Box) -> bool:
    """True if the ESC outline is in `local_box`. Search only if 0.20 < score < 0.70."""
    luma = frame_luma(frame_bgra)
    x1, y1, x2, y2 = local_box
    if x1 < 0 or y1 < 0 or y2 > luma.shape[0] or x2 > luma.shape[1]:
        return False
    score = match_patch(luma[y1:y2, x1:x2], template)
    if 0.20 < score < 0.70:
        score = search_match(luma, template, x1, y1, x2, y2)
    return score >= CORR_MIN
