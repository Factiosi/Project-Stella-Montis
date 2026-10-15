"""Foreground loop: locate the game, classify menu vs raid, slew the ramp.

Capture intervals are user-set. Displayed gamma is written only by
`Applicator`, at most MAX_SLEW per second, dt capped at MAX_GLIDE_DT so a
stall cannot become a jump.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np

from core.paths import BASELINE_PATH
from core.settings import Settings
from kernel.gamma import BaselineStore, RampCache, quantize_gamma, try_enable_full_range, write_ramp
from kernel.window import game_window, is_foreground, monitor_device, monitor_rect, user32
from modules.menu import button_visible, capture_region, load_template
from modules.weights import GRID, Point, circle_weights

MAX_SLEW = 0.8  # gamma units / s
APPLY_INTERVAL = 0.02
MAX_GLIDE_DT = 0.05  # clamp; a hung frame must not dump the whole slew
WINDOW_SCAN_INTERVAL = 0.5
# Luma at or above this maps to gamma_min. Sun + character in frame sits here.
BRIGHT_LUMA = 0.50
MENU_EXIT_MISSES = 2  # consecutive ESC misses before leaving the menu

Rect = tuple[int, int, int, int]


class State(Enum):
    NO_GAME = "no_game"
    UNFOCUSED = "unfocused"
    PAUSED = "paused"
    MENU = "menu"
    RAID = "raid"
    ERROR = "error"


@dataclass(frozen=True)
class Status:
    """Published snapshot. Errors are a locale key plus its format argument."""

    state: State
    gamma: float = 1.0
    manual: bool = False
    hdr: bool = False
    rejected: float | None = None
    error_key: str = ""
    error_value: str = ""


@dataclass(frozen=True)
class GameView:
    """Cached game client and its monitor, valid between window scans."""

    hwnd: int
    origin_x: int
    origin_y: int
    width: int
    height: int
    device: str
    monitor_left: int
    monitor_top: int


def glide(current: float, target: float, dt: float) -> float:
    """Move `current` toward `target` by at most MAX_SLEW * min(dt, MAX_GLIDE_DT)."""
    if dt <= 0.0:
        return current
    limit = MAX_SLEW * min(dt, MAX_GLIDE_DT)
    delta = target - current
    if abs(delta) <= limit:
        return target
    return current + limit if delta > 0.0 else current - limit


def adopt_target(held: float | None, candidate: float, threshold: float, floor: float) -> float:
    """Hold `held` until `candidate` differs by ≥ `threshold`.

    `held is None` anchors to `floor`, not to the first candidate — otherwise
    a bright opening frame locks a boost before any raid sample exists.
    """
    anchor = floor if held is None else held
    if threshold <= 0.0 or abs(candidate - anchor) >= threshold:
        return candidate
    return anchor


def target_gamma(luma: float, gamma_min: float, gamma_max: float) -> float:
    """gamma_max at luma 0, gamma_min at luma ≥ BRIGHT_LUMA, linear in between."""
    floor = min(gamma_min, gamma_max)
    ceiling = max(gamma_max, floor)
    level = min(1.0, max(0.0, luma))
    darkness = 0.0 if level >= BRIGHT_LUMA else (BRIGHT_LUMA - level) / BRIGHT_LUMA
    return floor + (ceiling - floor) * darkness


def circle_rect(
    origin_x: int,
    origin_y: int,
    width: int,
    height: int,
    monitor_left: int,
    monitor_top: int,
    diameter_pct: int = 90,
) -> Rect:
    """Axis-aligned square of the sampling circle, client-centered, monitor pixels."""
    side = int(round(diameter_pct / 100.0 * height))
    side = max(GRID, min(side, width, height))
    left = origin_x + (width - side) // 2 - monitor_left
    top = origin_y + (height - side) // 2 - monitor_top
    return int(left), int(top), int(left + side), int(top + side)


class MenuLatch:
    """Menu on first ESC hit; raid only after MENU_EXIT_MISSES consecutive misses."""

    def __init__(self) -> None:
        self.in_menu = True
        self._absent = 0

    def see(self, visible: bool) -> bool:
        if visible:
            self.in_menu = True
            self._absent = 0
        else:
            self._absent += 1
            if self._absent >= MENU_EXIT_MISSES:
                self.in_menu = False
        return self.in_menu


class Applicator:
    """Sole writer of SetDeviceGammaRamp. Tracks slew, last good, driver rejects."""

    def __init__(self, store: BaselineStore) -> None:
        self.store = store
        self.cache = RampCache()
        self.current = 1.0
        self.written = 1.0
        self.good = 1.0
        self.ceiling: float | None = None
        self.rejected: float | None = None
        self._glide_at: float | None = None
        self._lock = threading.Lock()

    def reset_motion(self) -> None:
        with self._lock:
            self.current = 1.0
            self.written = 1.0
            self._glide_at = None
            self.cache.reset()

    def restore(self, device: str) -> bool:
        with self._lock:
            return self._restore(device)

    def _restore(self, device: str) -> bool:
        if self.written <= 1.0 and self.current <= 1.0 and self.store.dirty_device is None:
            self.current = self.written = 1.0
            return True
        if not write_ramp(device, self.store.ensure(device)):
            return False
        self.store.clear_dirty()
        self.current = self.written = self.good = 1.0
        self.rejected = None
        self._glide_at = None
        return True

    def follow(self, device: str, target: float, now: float) -> float:
        with self._lock:
            return self._follow(device, target, now)

    def _follow(self, device: str, target: float, now: float) -> float:
        if self.ceiling is not None:
            target = min(target, self.ceiling)
        target = max(1.0, target)
        dt = APPLY_INTERVAL if self._glide_at is None else now - self._glide_at
        self._glide_at = now
        self.current = glide(self.current, target, dt)
        level = quantize_gamma(self.current)
        if level <= 1.0:
            self._restore(device)
            return 1.0
        if level == self.written:
            return level
        ramp = self.cache.get(self.store.ensure(device), level)
        self.store.mark_dirty(device)
        if write_ramp(device, ramp):
            self.written = self.good = level
            self.rejected = None
            return level
        # SetDeviceGammaRamp failed. Freeze at last good; cap later targets.
        self.rejected = level
        self.ceiling = self.good
        self.current = self.good
        return self.good


class Engine:
    def __init__(self, settings: Settings, baseline_path: Path = BASELINE_PATH) -> None:
        self._settings = settings.clamped()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = Status(State.NO_GAME)
        self._view: GameView | None = None
        self._paused = False
        self._stopped = False
        self.full_range = try_enable_full_range()
        self.hdr = False
        self.store = BaselineStore(baseline_path)
        self.store.load()
        self.store.recover()
        self._applicator = Applicator(self.store)
        self._monitor = ""
        self._weights = circle_weights(self._settings.curve)
        self._weight_curve: list[Point] = list(self._settings.curve)

    # --- control -----------------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="psm-gamma", daemon=False)
            self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._restore_known()
        self._stopped = True

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self._paused = bool(paused)

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def update_settings(self, settings: Settings) -> None:
        with self._lock:
            previous = self._settings
            self._settings = settings.clamped()
            if self._settings.gamma_max != previous.gamma_max or self._settings.manual_gamma != previous.manual_gamma:
                self._applicator.ceiling = None

    def snapshot(self) -> Status:
        with self._lock:
            return self._status

    def game_view(self) -> GameView | None:
        """Last GameView, or None. Used by the overlay, not by capture."""
        with self._lock:
            return self._view

    # --- internals ---------------------------------------------------------------

    def _publish(
        self, state: State, gamma: float = 1.0, *, manual: bool = False, error: tuple[str, str] | None = None
    ) -> None:
        key, value = error if error is not None else ("", "")
        status = Status(
            state=state,
            gamma=gamma,
            manual=manual,
            hdr=self.hdr,
            rejected=self._applicator.rejected,
            error_key=key,
            error_value=value,
        )
        with self._lock:
            self._status = status

    def _set_view(self, view: GameView | None) -> None:
        with self._lock:
            self._view = view

    def _restore_known(self) -> None:
        device = self._monitor or self.store.dirty_device
        if device:
            self._applicator.restore(device)

    def _release_capture(self, session: object) -> None:
        close = getattr(session, "close", None)
        if close is not None and self._monitor:
            close()
            self._monitor = ""

    def _locate_game(self, previous: GameView | None) -> GameView | None:
        window = game_window()
        if window is None:
            return None
        origin_x, origin_y, width, height, hwnd = window
        if previous is not None:
            known = (previous.hwnd, previous.origin_x, previous.origin_y, previous.width, previous.height)
            if known == (hwnd, origin_x, origin_y, width, height):
                return previous
        device = monitor_device(hwnd)
        screen = monitor_rect(hwnd)
        if not device or screen is None:
            return None
        return GameView(hwnd, origin_x, origin_y, width, height, device, screen[0], screen[1])

    def _loop(self) -> None:
        import comtypes

        comtypes.CoInitialize()
        from kernel.capture import CaptureSession

        try:
            template = load_template()
        except OSError as error:
            self._publish(State.ERROR, error=("error_no_template", str(error)))
            return

        session = CaptureSession(self._settings.compute)
        latch = MenuLatch()
        view: GameView | None = None
        next_scan = next_menu = next_sample = next_apply = 0.0
        aimed = 1.0
        held: float | None = None

        def idle(state: State, wait: float) -> None:
            nonlocal aimed, held
            self._restore_known()
            self._applicator.reset_motion()
            aimed, held = 1.0, None
            self._publish(state)
            self._stop.wait(wait)

        try:
            while not self._stop.is_set():
                now = time.perf_counter()
                if self.is_paused():
                    idle(State.PAUSED, 0.1)
                    continue

                if view is None or now >= next_scan or not user32.IsWindow(view.hwnd):
                    located = self._locate_game(view)
                    if located is not view:
                        self._set_view(located)
                    view = located
                    next_scan = now + WINDOW_SCAN_INTERVAL
                if view is None:
                    self._release_capture(session)
                    latch = MenuLatch()
                    idle(State.NO_GAME, 0.3)
                    continue
                if not is_foreground(view.hwnd):
                    idle(State.UNFOCUSED, 0.05)
                    continue

                with self._lock:
                    settings = self._settings
                device = view.device

                if session.compute != settings.compute and session.is_open:
                    session.close()
                    session = CaptureSession(settings.compute)
                if device != self._monitor or not session.is_open:
                    if self._monitor and self._monitor != device:
                        self._applicator.restore(self._monitor)
                        self._applicator.reset_motion()
                    try:
                        session.open(device)
                    except Exception as error:  # COMError, DXGI, driver — not one type.
                        self._publish(State.ERROR, self._applicator.current, error=("error_capture_open", str(error)))
                        self._stop.wait(0.5)
                        continue
                    self._monitor = device
                    self.hdr = session.hdr

                if settings.curve != self._weight_curve:
                    self._weights = circle_weights(settings.curve)
                    self._weight_curve = list(settings.curve)

                want_menu = now >= next_menu
                want_circle = not latch.in_menu and not settings.manual and now >= next_sample
                if want_menu or want_circle:
                    try:
                        esc_region, local_box = capture_region(
                            view.origin_x,
                            view.origin_y,
                            view.width,
                            view.height,
                            view.monitor_left,
                            view.monitor_top,
                        )
                        circle = circle_rect(
                            view.origin_x,
                            view.origin_y,
                            view.width,
                            view.height,
                            view.monitor_left,
                            view.monitor_top,
                            settings.diameter_pct,
                        )
                        grid, button = session.grab(
                            circle if want_circle else None,
                            esc_region if want_menu else None,
                            settings.capture_ms,
                        )
                    except Exception as error:
                        self._publish(State.ERROR, self._applicator.current, error=("error_capture", str(error)))
                        self._stop.wait(0.3)
                        continue
                    if want_menu and button is not None:
                        latch.see(button_visible(button, template, local_box))
                        next_menu = now + settings.menu_ms / 1000.0
                    if want_circle and grid is not None:
                        luma = float(np.dot(grid.ravel(), self._weights.ravel()))
                        candidate = target_gamma(luma, settings.gamma_min, settings.gamma_max)
                        held = adopt_target(held, candidate, settings.threshold, settings.gamma_min)
                        aimed = held
                        next_sample = now + settings.capture_ms / 1000.0
                    elif want_circle:
                        next_sample = now + 0.05

                if latch.in_menu:
                    held, aimed = None, 1.0
                elif settings.manual:
                    held, aimed = None, settings.manual_gamma

                if now >= next_apply:
                    shown = self._applicator.follow(device, aimed, now)
                    next_apply = now + APPLY_INTERVAL
                    state = State.MENU if latch.in_menu else State.RAID
                    self._publish(state, shown, manual=settings.manual and not latch.in_menu)
                self._stop.wait(0.01)
        finally:
            self._set_view(None)
            self._restore_known()
            session.close()
