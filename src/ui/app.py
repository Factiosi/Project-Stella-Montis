"""Settings window. Formats `Status`; does not write ramps."""

from __future__ import annotations

import signal
import tkinter as tk
from collections.abc import Callable

from core.locale import tr
from core.settings import (
    CAPTURE_MS_RANGE,
    DIAMETER_RANGE,
    GAMMA_RANGE,
    MENU_MS_MAX,
    THRESHOLD_MAX,
    Settings,
    load_settings,
    save_settings,
)
from daemon.engine import Engine, State, Status
from modules.weights import PRESETS, Point
from ui.curve import CurveEditor
from ui.overlay import CircleOverlay
from ui.theme import BG, CONTENT_WIDTH, CREAM, CREAM_DIM, GOLD, RULE, STRIPES, SURFACE, font_mono, font_text
from ui.widgets import CheckBox, FlatButton, Segmented, Slider, TabBar, rule

REFRESH_MS = 100

STATE_KEYS = {
    State.NO_GAME: "state_no_game",
    State.UNFOCUSED: "state_unfocused",
    State.PAUSED: "state_paused",
    State.MENU: "state_menu",
    State.RAID: "state_raid",
    State.ERROR: "state_error",
}
PRESET_KEYS = {"classic": "preset_classic", "center": "preset_center", "flat": "preset_flat"}


class App(tk.Tk):
    def __init__(self, start_engine: bool = True) -> None:
        super().__init__()
        self.title("Stella Montis")
        self.resizable(False, False)
        self.configure(background=BG)
        self._settings = load_settings()
        self.engine = Engine(self._settings)
        self.overlay = CircleOverlay(self, self.engine)
        self._user_paused = False
        self._pages: dict[str, tk.Frame] = {}
        self._refresh_after: str | None = None
        self._closing = False
        self._build()
        self._push()
        self.protocol("WM_DELETE_WINDOW", self._close)
        if start_engine:
            self.engine.start()
            self._refresh_after = self.after(REFRESH_MS, self._refresh)

    # --- layout ------------------------------------------------------------------

    def _build(self) -> None:
        outer = tk.Frame(self, background=BG, padx=22, pady=18)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        row = 0

        head = tk.Frame(outer, background=BG)
        head.grid(row=row, column=0, sticky="ew")
        tk.Label(head, text="STELLA MONTIS", font=font_text(17, "bold"), background=BG, foreground=CREAM).pack(
            side=tk.LEFT
        )
        stripes = tk.Frame(head, background=BG)
        stripes.pack(side=tk.LEFT, padx=(12, 0), pady=(6, 0))
        for color in STRIPES:
            tk.Frame(stripes, background=color, width=12, height=3).pack(side=tk.LEFT, padx=(0, 3))
        tk.Label(head, text=tr("header_tag"), font=font_mono(8), background=BG, foreground=CREAM_DIM).pack(
            side=tk.RIGHT, pady=(8, 0)
        )
        row += 1

        status_row = tk.Frame(outer, background=BG)
        status_row.grid(row=row, column=0, sticky="ew", pady=(14, 0))
        tk.Label(status_row, text=tr("status_label"), font=font_mono(8), background=BG, foreground=CREAM_DIM).pack(
            side=tk.LEFT
        )
        self.status = tk.Label(status_row, text="", font=font_mono(10, "bold"), background=BG, foreground=GOLD)
        self.status.pack(side=tk.LEFT, padx=(14, 0))
        self.gamma_readout = tk.Label(status_row, text="", font=font_mono(10), background=BG, foreground=CREAM)
        self.gamma_readout.pack(side=tk.RIGHT)
        self.manual_tag = tk.Label(status_row, text="", font=font_mono(8), background=BG, foreground=CREAM_DIM)
        self.manual_tag.pack(side=tk.RIGHT, padx=(0, 10))
        row += 1

        self.note = tk.Label(
            outer,
            text="",
            font=font_text(9),
            background=BG,
            foreground=CREAM_DIM,
            wraplength=CONTENT_WIDTH + 20,
            justify=tk.LEFT,
            anchor="w",
        )
        self.note.grid(row=row, column=0, sticky="ew", pady=(4, 0))
        row += 1
        rule(outer, RULE).grid(row=row, column=0, sticky="ew", pady=(6, 0))
        row += 1

        self.tabs = TabBar(outer, self._show_page)
        self.tabs.grid(row=row, column=0, sticky="ew", pady=(12, 0))
        row += 1
        rule(outer, RULE).grid(row=row, column=0, sticky="ew")
        row += 1

        self.page_host = tk.Frame(outer, background=SURFACE)
        self.page_host.grid(row=row, column=0, sticky="nsew")
        self.page_host.columnconfigure(0, weight=1)
        row += 1
        self._build_gamma_tab()
        self._build_circle_tab()
        self._build_poll_tab()
        for key, title_key in (("gamma", "tab_gamma"), ("circle", "tab_circle"), ("poll", "tab_poll")):
            self.tabs.add(key, tr(title_key))

        self.pause_button = FlatButton(
            outer, tr("pause"), self._toggle_pause, primary=True, pady=10, font=font_text(11, "bold")
        )
        self.pause_button.grid(row=row, column=0, sticky="ew", pady=(16, 0))
        self._render(self.engine.snapshot())

    def _page(self, key: str) -> tk.Frame:
        page = tk.Frame(self.page_host, background=SURFACE, padx=16, pady=10)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=1)
        self._pages[key] = page
        return page

    def _show_page(self, key: str) -> None:
        self._pages[key].tkraise()

    def _row(
        self,
        page: tk.Frame,
        row: int,
        title: str,
        variable: tk.Variable,
        start: float,
        end: float,
        resolution: float,
        callback: Callable[[str], None],
        last: bool = False,
    ) -> tuple[tk.Label, Slider]:
        """Title + live value + slider. Hairline after unless `last`."""
        head = tk.Frame(page, background=SURFACE)
        head.grid(row=row, column=0, sticky="ew", pady=(8, 2))
        tk.Label(head, text=title, font=font_text(10), background=SURFACE, foreground=CREAM).pack(side=tk.LEFT)
        value = tk.Label(
            head, text=self._format(variable.get(), resolution), font=font_mono(10), background=SURFACE, foreground=GOLD
        )
        value.pack(side=tk.RIGHT)
        slider = Slider(page, start, end, resolution, variable, callback)
        slider.grid(row=row + 1, column=0, sticky="ew")
        if not last:
            rule(page).grid(row=row + 2, column=0, sticky="ew", pady=(8, 0))
        return value, slider

    def _build_gamma_tab(self) -> None:
        page = self._page("gamma")
        s = self._settings
        self.max_var = tk.DoubleVar(value=s.gamma_max)
        self.min_var = tk.DoubleVar(value=s.gamma_min)
        self.threshold_var = tk.DoubleVar(value=s.threshold)
        self.manual_var = tk.BooleanVar(value=s.manual)
        self.manual_gamma_var = tk.DoubleVar(value=s.manual_gamma)

        self.max_value, self.max_scale = self._row(
            page, 0, tr("gamma_max"), self.max_var, *GAMMA_RANGE, 0.01, self._on_max
        )
        self.min_value, self.min_scale = self._row(
            page, 3, tr("gamma_min"), self.min_var, *GAMMA_RANGE, 0.01, self._on_min
        )
        self.threshold_value, _ = self._row(
            page, 6, tr("threshold"), self.threshold_var, 0.0, THRESHOLD_MAX, 0.01, self._on_threshold
        )

        head = tk.Frame(page, background=SURFACE)
        head.grid(row=9, column=0, sticky="ew", pady=(10, 2))
        tk.Label(head, text=tr("mode"), font=font_text(10), background=SURFACE, foreground=CREAM).pack(side=tk.LEFT)
        self.manual_value = tk.Label(
            head, text=f"{s.manual_gamma:.2f}", font=font_mono(10), background=SURFACE, foreground=GOLD
        )
        self.manual_value.pack(side=tk.RIGHT)
        self.manual_switch = Segmented(
            head, ((False, tr("mode_auto")), (True, tr("mode_manual"))), self.manual_var, self._on_manual_toggle
        )
        self.manual_switch.pack(side=tk.LEFT, padx=(14, 0))
        self.manual_scale = Slider(page, *GAMMA_RANGE, 0.01, self.manual_gamma_var, self._on_manual_gamma)
        self.manual_scale.grid(row=10, column=0, sticky="ew", pady=(4, 0))
        self._sync_manual_state()

    def _build_circle_tab(self) -> None:
        page = self._page("circle")
        self.diameter_var = tk.IntVar(value=self._settings.diameter_pct)
        self.diameter_value, _ = self._row(
            page, 0, tr("diameter"), self.diameter_var, *DIAMETER_RANGE, 1, self._on_diameter, last=True
        )
        self.overlay_var = tk.BooleanVar(value=False)
        self.overlay_check = CheckBox(page, tr("show_overlay"), self.overlay_var, self._on_overlay)
        self.overlay_check.grid(row=2, column=0, sticky="w", pady=(10, 0))
        rule(page).grid(row=3, column=0, sticky="ew", pady=(10, 0))

        head = tk.Frame(page, background=SURFACE)
        head.grid(row=4, column=0, sticky="ew", pady=(10, 6))
        tk.Label(head, text=tr("curve"), font=font_text(10), background=SURFACE, foreground=CREAM).pack(side=tk.LEFT)
        presets = tk.Frame(head, background=SURFACE)
        presets.pack(side=tk.RIGHT)
        for key, title_key in PRESET_KEYS.items():
            FlatButton(presets, tr(title_key), lambda k=key: self._apply_preset(k), padx=10, pady=4).pack(
                side=tk.LEFT, padx=(6, 0)
            )
        self.curve_editor = CurveEditor(page, self._settings.curve, self._on_curve)
        self.curve_editor.grid(row=5, column=0, sticky="w")
        tk.Label(
            page,
            text=tr("curve_hint"),
            font=font_text(9),
            background=SURFACE,
            foreground=CREAM_DIM,
            wraplength=CONTENT_WIDTH,
            justify=tk.LEFT,
        ).grid(row=6, column=0, sticky="w", pady=(2, 0))

    def _build_poll_tab(self) -> None:
        page = self._page("poll")
        self.capture_var = tk.IntVar(value=self._settings.capture_ms)
        self.menu_var = tk.IntVar(value=self._settings.menu_ms)
        self.capture_value, _ = self._row(
            page, 0, tr("capture_ms"), self.capture_var, *CAPTURE_MS_RANGE, 1, self._on_capture
        )
        self.menu_value, self.menu_scale = self._row(
            page, 3, tr("menu_ms"), self.menu_var, CAPTURE_MS_RANGE[0], MENU_MS_MAX, 1, self._on_menu
        )
        head = tk.Frame(page, background=SURFACE)
        head.grid(row=6, column=0, sticky="ew", pady=(10, 2))
        tk.Label(head, text=tr("compute"), font=font_text(10), background=SURFACE, foreground=CREAM).pack(side=tk.LEFT)
        self.compute_var = tk.StringVar(value=self._settings.compute)
        self.compute_switch = Segmented(
            page, (("gpu", tr("compute_gpu")), ("cpu", tr("compute_cpu"))), self.compute_var, self._push
        )
        self.compute_switch.grid(row=7, column=0, sticky="w", pady=(6, 0))
        tk.Label(
            page,
            text=tr("compute_hint"),
            font=font_text(9),
            background=SURFACE,
            foreground=CREAM_DIM,
            wraplength=CONTENT_WIDTH,
            justify=tk.LEFT,
        ).grid(row=8, column=0, sticky="w", pady=(12, 4))

    @staticmethod
    def _format(value: float, resolution: float) -> str:
        return str(int(round(float(value)))) if resolution >= 1 else f"{float(value):.2f}"

    # --- handlers ----------------------------------------------------------------

    def _on_max(self, value: str) -> None:
        self.max_value.configure(text=f"{float(value):.2f}")
        if self.min_var.get() > float(value):
            self.min_var.set(float(value))
            self.min_value.configure(text=f"{float(value):.2f}")
            self.min_scale.redraw()
        self._push()

    def _on_min(self, value: str) -> None:
        capped = min(float(value), float(self.max_var.get()))
        if capped != float(value):
            self.min_var.set(capped)
            self.min_scale.redraw()
        self.min_value.configure(text=f"{capped:.2f}")
        self._push()

    def _on_threshold(self, value: str) -> None:
        self.threshold_value.configure(text=f"{float(value):.2f}")
        self._push()

    def _on_manual_toggle(self) -> None:
        self._sync_manual_state()
        self._push()

    def _on_manual_gamma(self, value: str) -> None:
        self.manual_value.configure(text=f"{float(value):.2f}")
        self._push()

    def _sync_manual_state(self) -> None:
        enabled = bool(self.manual_var.get())
        self.manual_scale.set_enabled(enabled)
        self.manual_value.configure(foreground=GOLD if enabled else CREAM_DIM)
        self.manual_switch.refresh()

    def _on_diameter(self, value: str) -> None:
        self.diameter_value.configure(text=str(int(float(value))))
        self._push()

    def _on_overlay(self) -> None:
        if self.overlay_var.get():
            self.overlay.configure(int(self.diameter_var.get()), self.curve_editor.points)
            self.overlay.show()
        else:
            self.overlay.hide()

    def _on_curve(self, _points: list[Point]) -> None:
        self._push()

    def _apply_preset(self, key: str) -> None:
        self.curve_editor.set_points(list(PRESETS[key]))
        self._push()

    def _on_capture(self, value: str) -> None:
        capture = int(float(value))
        self.capture_value.configure(text=str(capture))
        if int(self.menu_var.get()) < capture:
            self.menu_var.set(capture)
            self.menu_value.configure(text=str(capture))
            self.menu_scale.redraw()
        self._push()

    def _on_menu(self, value: str) -> None:
        menu = max(int(float(value)), int(self.capture_var.get()))
        if menu != int(float(value)):
            self.menu_var.set(menu)
            self.menu_scale.redraw()
        self.menu_value.configure(text=str(menu))
        self._push()

    def _toggle_pause(self) -> None:
        self._user_paused = not self._user_paused
        self.engine.set_paused(self._user_paused)
        self.pause_button.set_text(tr("resume") if self._user_paused else tr("pause"))

    # --- state -------------------------------------------------------------------

    def _collect(self) -> Settings:
        return Settings(
            gamma_max=float(self.max_var.get()),
            gamma_min=float(self.min_var.get()),
            manual=bool(self.manual_var.get()),
            manual_gamma=float(self.manual_gamma_var.get()),
            threshold=float(self.threshold_var.get()),
            capture_ms=int(self.capture_var.get()),
            menu_ms=int(self.menu_var.get()),
            diameter_pct=int(self.diameter_var.get()),
            compute=self.compute_var.get(),
            curve=self.curve_editor.points,
        ).clamped()

    def _push(self) -> None:
        self._settings = self._collect()
        self.engine.update_settings(self._settings)
        self.overlay.configure(self._settings.diameter_pct, self._settings.curve)
        save_settings(self._settings)

    def _render(self, status: Status) -> None:
        self.status.configure(text=tr(STATE_KEYS[status.state]).upper())
        show_gamma = status.state in (State.MENU, State.RAID)
        self.gamma_readout.configure(text=f"γ {status.gamma:.2f}" if show_gamma else "")
        self.manual_tag.configure(text=tr("tag_manual") if status.manual and show_gamma else "")
        notes: list[str] = []
        if status.state is State.ERROR and status.error_key:
            notes.append(tr(status.error_key, value=status.error_value))
        if status.rejected is not None:
            notes.append(tr("note_rejected", value=f"{status.rejected:.2f}"))
        if status.hdr:
            notes.append(tr("note_hdr"))
        if not self.engine.full_range:
            notes.append(tr("note_full_range"))
        self.note.configure(text="  ".join(notes))

    def _refresh(self) -> None:
        if not self.winfo_exists():
            return
        self._render(self.engine.snapshot())
        self._refresh_after = self.after(REFRESH_MS, self._refresh)

    def report_callback_exception(self, exc: type[BaseException], val: BaseException, tb) -> None:
        # Ctrl+C lands in whatever `after` is running; Tk would print a stack.
        if issubclass(exc, KeyboardInterrupt):
            self._close()
            return
        super().report_callback_exception(exc, val, tb)

    def _close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._refresh_after is not None:
            try:
                self.after_cancel(self._refresh_after)
            except tk.TclError:
                pass
            self._refresh_after = None
        if self.winfo_exists():
            save_settings(self._collect())
        self.overlay.hide()
        self.engine.stop()
        if self.winfo_exists():
            self.destroy()


def run() -> None:
    app = App(start_engine=True)
    # SIGINT during Tcl's C loop does not raise until the next Python callback.
    signal.signal(signal.SIGINT, lambda *_: app.after(0, app._close))
    try:
        app.mainloop()
    except KeyboardInterrupt:
        app._close()
