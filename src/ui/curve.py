"""Polyline editor for the influence curve.

X = area share from center, Y = cumulative influence. The first user point
is drawn as a vertical riser (x1, 0)→(x1, y1): that block is a plateau,
not a diagonal from the origin.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable

from core.locale import tr
from modules.weights import MAX_USER_POINTS, Point, normalize_points
from ui.theme import BG, CONTENT_WIDTH, CREAM, CREAM_DIM, GOLD, GOLD_HI, RULE, RULE_SOFT, SURFACE, font_mono

INNER_BLOCK = "#221b0d"


class CurveEditor(tk.Frame):
    SIZE_X = CONTENT_WIDTH - 56
    SIZE_Y = 260
    PAD_L = 40
    PAD_R = 16
    PAD_T = 24
    PAD_B = 40
    HANDLE = 5
    MIN_GAP = 0.5

    def __init__(self, master: tk.Misc, points: list[Point], on_change: Callable[[list[Point]], None]) -> None:
        super().__init__(master, background=SURFACE)
        self._points = normalize_points(points)
        self._on_change = on_change
        self._drag: int | None = None
        self._font = font_mono(8)
        self.canvas = tk.Canvas(
            self,
            width=self.SIZE_X + self.PAD_L + self.PAD_R,
            height=self.SIZE_Y + self.PAD_T + self.PAD_B,
            highlightthickness=0,
            background=SURFACE,
        )
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._move)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<ButtonPress-3>", self._remove)
        self.canvas.bind("<Double-Button-1>", self._add)
        self.redraw()

    @property
    def points(self) -> list[Point]:
        return list(self._points)

    def set_points(self, points: list[Point]) -> None:
        self._points = normalize_points(points)
        self.redraw()

    # --- coordinates -------------------------------------------------------------

    def _to_canvas(self, x_pct: float, y_pct: float) -> tuple[float, float]:
        return (
            self.PAD_L + x_pct / 100.0 * self.SIZE_X,
            self.PAD_T + (1.0 - y_pct / 100.0) * self.SIZE_Y,
        )

    def _to_data(self, cx: float, cy: float) -> tuple[float, float]:
        x_pct = (cx - self.PAD_L) / self.SIZE_X * 100.0
        y_pct = (1.0 - (cy - self.PAD_T) / self.SIZE_Y) * 100.0
        return min(100.0, max(0.0, x_pct)), min(100.0, max(0.0, y_pct))

    # --- drawing -----------------------------------------------------------------

    def redraw(self) -> None:
        canvas = self.canvas
        canvas.delete("all")
        left, top = self.PAD_L, self.PAD_T
        right, bottom = self.PAD_L + self.SIZE_X, self.PAD_T + self.SIZE_Y
        canvas.create_rectangle(left, top, right, bottom, fill=BG, outline="")
        for step in range(0, 101, 25):
            gx, _ = self._to_canvas(step, 0)
            _, gy = self._to_canvas(0, step)
            if 0 < step < 100:
                canvas.create_line(gx, top, gx, bottom, fill=RULE_SOFT)
                canvas.create_line(left, gy, right, gy, fill=RULE_SOFT)
            canvas.create_text(gx, bottom + 10, text=str(step), fill=CREAM_DIM, font=self._font)
            canvas.create_text(left - 8, gy, text=str(step), fill=CREAM_DIM, font=self._font, anchor="e")
        canvas.create_rectangle(left, top, right, bottom, outline=RULE)
        canvas.create_text(right, bottom + 26, text=tr("axis_x"), fill=CREAM_DIM, font=self._font, anchor="e")
        canvas.create_text(left, top - 10, text=tr("axis_y"), fill=CREAM_DIM, font=self._font, anchor="w")

        if self._points:
            x1, y1 = self._points[0]
            bx0, by0 = self._to_canvas(0, y1)
            bx1, by1 = self._to_canvas(x1, 0)
            canvas.create_rectangle(bx0, by0, bx1, by1, fill=INNER_BLOCK, outline="")
            rx, ry0 = self._to_canvas(x1, 0)
            _, ry1 = self._to_canvas(x1, y1)
            canvas.create_line(rx, ry0, rx, ry1, fill=GOLD, width=2)
            nodes = [(x1, y1), *self._points[1:], (100.0, 100.0)]
        else:
            nodes = [(0.0, 0.0), (100.0, 100.0)]
        coords: list[float] = []
        for x_pct, y_pct in nodes:
            coords.extend(self._to_canvas(x_pct, y_pct))
        canvas.create_line(*coords, fill=GOLD, width=2)

        for index, (x_pct, y_pct) in enumerate(self._points):
            cx, cy = self._to_canvas(x_pct, y_pct)
            fill = GOLD_HI if index == self._drag else CREAM
            canvas.create_rectangle(
                cx - self.HANDLE, cy - self.HANDLE, cx + self.HANDLE, cy + self.HANDLE, fill=fill, outline=BG, width=2
            )
            # Label south-east of the handle; the outgoing segment goes up.
            near_edge = x_pct >= 85
            canvas.create_text(
                cx + (-9 if near_edge else 9),
                cy + 6,
                text=f"{x_pct:.0f} / {y_pct:.0f}",
                fill=CREAM,
                anchor="ne" if near_edge else "nw",
                font=self._font,
            )

    # --- interaction -------------------------------------------------------------

    def _hit(self, cx: float, cy: float) -> int | None:
        best = None
        best_dist = (self.HANDLE * 3) ** 2
        for index, (x_pct, y_pct) in enumerate(self._points):
            px, py = self._to_canvas(x_pct, y_pct)
            dist = (px - cx) ** 2 + (py - cy) ** 2
            if dist <= best_dist:
                best, best_dist = index, dist
        return best

    def _press(self, event: tk.Event) -> None:
        self._drag = self._hit(event.x, event.y)
        self.redraw()

    def _move(self, event: tk.Event) -> None:
        if self._drag is None:
            return
        index = self._drag
        points = list(self._points)
        x_pct, y_pct = self._to_data(event.x, event.y)
        lower_x = points[index - 1][0] + self.MIN_GAP if index > 0 else self.MIN_GAP
        upper_x = points[index + 1][0] - self.MIN_GAP if index + 1 < len(points) else 100.0 - self.MIN_GAP
        lower_y = points[index - 1][1] if index > 0 else 0.0
        upper_y = points[index + 1][1] if index + 1 < len(points) else 100.0
        points[index] = (min(upper_x, max(lower_x, x_pct)), min(upper_y, max(lower_y, y_pct)))
        self._points = points
        self.redraw()
        self._on_change(self.points)

    def _release(self, _event: tk.Event) -> None:
        if self._drag is not None:
            self._drag = None
            self._points = normalize_points(self._points)
            self.redraw()
            self._on_change(self.points)

    def _add(self, event: tk.Event) -> None:
        if len(self._points) >= MAX_USER_POINTS or self._hit(event.x, event.y) is not None:
            return
        x_pct, y_pct = self._to_data(event.x, event.y)
        if x_pct <= self.MIN_GAP or x_pct >= 100.0 - self.MIN_GAP:
            return
        self._points = normalize_points([*self._points, (x_pct, y_pct)])
        self.redraw()
        self._on_change(self.points)

    def _remove(self, event: tk.Event) -> None:
        index = self._hit(event.x, event.y)
        if index is None:
            return
        points = list(self._points)
        del points[index]
        self._points = normalize_points(points)
        self._drag = None
        self.redraw()
        self._on_change(self.points)
