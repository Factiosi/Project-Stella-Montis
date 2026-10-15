"""Click-through overlay of the sampling circle on the game's monitor.

WS_EX_TRANSPARENT | WS_EX_NOACTIVATE keep PioneerGame.exe foreground.
WDA_EXCLUDEFROMCAPTURE keeps the rings out of our own DXGI grab.
Inner dashed rings: radius R·√(x/100) for each curve point x.
No game → primary screen, same circle math, so the control still previews.
"""

from __future__ import annotations

import math
import tkinter as tk

from daemon.engine import Engine, circle_rect
from kernel.window import make_overlay, monitor_rect, user32
from modules.weights import Point
from ui.theme import OVERLAY_GREEN, OVERLAY_KEY, font_mono

Rect = tuple[int, int, int, int]


class CircleOverlay:
    TICK_MS = 250

    def __init__(self, master: tk.Tk, engine: Engine, exclude_from_capture: bool = True) -> None:
        self.master = master
        self.engine = engine
        self.exclude_from_capture = exclude_from_capture
        self.window: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.diameter_pct = 90
        self.points: list[Point] = []
        self._after: str | None = None
        self._drawn: tuple | None = None

    @property
    def visible(self) -> bool:
        return self.window is not None

    def configure(self, diameter_pct: int, points: list[Point]) -> None:
        self.diameter_pct = int(diameter_pct)
        self.points = list(points)
        if self.visible:
            self._tick(reschedule=False)

    def show(self) -> None:
        if self.window is not None:
            return
        window = tk.Toplevel(self.master)
        window.withdraw()
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        window.attributes("-transparentcolor", OVERLAY_KEY)
        window.configure(background=OVERLAY_KEY)
        canvas = tk.Canvas(window, background=OVERLAY_KEY, highlightthickness=0, bd=0)
        canvas.pack(fill=tk.BOTH, expand=True)
        self.window, self.canvas = window, canvas
        self._drawn = None
        self._tick(reschedule=False)
        window.update_idletasks()
        # Tk wraps Toplevel in a frame; GetParent is the HWND SetWindowLongW needs.
        hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
        make_overlay(int(hwnd), self.exclude_from_capture)
        window.deiconify()
        self._schedule()

    def hide(self) -> None:
        if self._after is not None:
            self.master.after_cancel(self._after)
            self._after = None
        if self.window is not None:
            self.window.destroy()
            self.window = self.canvas = None
            self._drawn = None

    def _schedule(self) -> None:
        self._after = self.master.after(self.TICK_MS, self._tick)

    def _target(self) -> tuple[Rect, Rect]:
        """(monitor virtual-screen rect, circle in that monitor's coords)."""
        view = self.engine.game_view()
        screen = monitor_rect(view.hwnd) if view is not None else None
        if view is None or screen is None:
            width, height = self.master.winfo_screenwidth(), self.master.winfo_screenheight()
            return (0, 0, width, height), circle_rect(0, 0, width, height, 0, 0, self.diameter_pct)
        circle = circle_rect(
            view.origin_x,
            view.origin_y,
            view.width,
            view.height,
            view.monitor_left,
            view.monitor_top,
            self.diameter_pct,
        )
        return screen, circle

    def _tick(self, reschedule: bool = True) -> None:
        if self.window is None or self.canvas is None:
            return
        screen, circle = self._target()
        key = (screen, circle, tuple(self.points))
        if key != self._drawn:
            self._draw(screen, circle)
            self._drawn = key
        if reschedule:
            self._schedule()

    def _draw(self, screen: Rect, circle: Rect) -> None:
        window, canvas = self.window, self.canvas
        assert window is not None and canvas is not None
        left, top, right, bottom = screen
        window.geometry(f"{right - left}x{bottom - top}+{left}+{top}")
        canvas.delete("all")
        x1, y1, x2, y2 = circle
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        radius = (x2 - x1) / 2
        label = font_mono(10, "bold")
        canvas.create_oval(x1, y1, x2, y2, outline=OVERLAY_GREEN, width=3)
        canvas.create_text(cx, y1 - 14, text="100", fill=OVERLAY_GREEN, font=label)
        for x_pct, _y_pct in self.points:
            inner = radius * math.sqrt(max(0.0, x_pct) / 100.0)
            if inner < 2:
                continue
            canvas.create_oval(
                cx - inner, cy - inner, cx + inner, cy + inner, outline=OVERLAY_GREEN, width=2, dash=(8, 6)
            )
            canvas.create_text(cx, cy - inner - 12, text=f"{x_pct:.0f}", fill=OVERLAY_GREEN, font=label)
        tick = 10
        canvas.create_line(cx - tick, cy, cx + tick, cy, fill=OVERLAY_GREEN, width=2)
        canvas.create_line(cx, cy - tick, cx, cy + tick, fill=OVERLAY_GREEN, width=2)
