"""tk controls. No ttk — clam/native themes would fight the palette."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Sequence

from ui.theme import (
    BG,
    CONTENT_WIDTH,
    CREAM,
    CREAM_DIM,
    GOLD,
    GOLD_DIM,
    GOLD_HI,
    INK,
    RULE,
    RULE_SOFT,
    SURFACE,
    SURFACE_HI,
    Font,
    font_text,
)


def rule(master: tk.Misc, color: str = RULE_SOFT) -> tk.Frame:
    """1 px hairline."""
    return tk.Frame(master, background=color, height=1)


class Slider(tk.Canvas):
    """Canvas slider bound to a Tk variable. Click, drag, wheel."""

    HEIGHT = 24
    KNOB_W = 8
    KNOB_H = 16

    def __init__(
        self,
        master: tk.Misc,
        from_: float,
        to: float,
        resolution: float,
        variable: tk.Variable,
        command: Callable[[str], None] | None = None,
        width: int = CONTENT_WIDTH,
    ) -> None:
        super().__init__(master, width=width, height=self.HEIGHT, background=SURFACE, highlightthickness=0, bd=0)
        self.from_ = float(from_)
        self.to = float(to)
        self.resolution = float(resolution)
        self.variable = variable
        self.command = command
        self.enabled = True
        self._active = False
        self._hover = False
        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<MouseWheel>", self._wheel)
        self.redraw()

    def _span(self) -> tuple[float, float]:
        pad = self.KNOB_W
        return pad, max(pad + 1, self.winfo_width() - pad)

    def _value_to_x(self, value: float) -> float:
        left, right = self._span()
        frac = (value - self.from_) / (self.to - self.from_) if self.to != self.from_ else 0.0
        return left + frac * (right - left)

    def _x_to_value(self, x: float) -> float:
        left, right = self._span()
        frac = min(1.0, max(0.0, (x - left) / (right - left)))
        return self.from_ + frac * (self.to - self.from_)

    def _quantize(self, value: float) -> float:
        steps = round((value - self.from_) / self.resolution)
        return round(min(self.to, max(self.from_, self.from_ + steps * self.resolution)), 6)

    def get(self) -> float:
        try:
            return float(self.variable.get())
        except (tk.TclError, ValueError):
            return self.from_

    def set(self, value: float, notify: bool = True) -> None:
        value = self._quantize(value)
        if isinstance(self.variable, tk.IntVar):
            self.variable.set(int(round(value)))
        else:
            self.variable.set(value)
        self.redraw()
        if notify and self.command is not None:
            self.command(str(value))

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        mid = self.HEIGHT / 2
        left, right = self._span()
        knob_x = self._value_to_x(self.get())
        lit = self._active or self._hover
        track = RULE if self.enabled else RULE_SOFT
        fill = (GOLD_HI if lit else GOLD) if self.enabled else GOLD_DIM
        knob = GOLD_HI if self._active else (CREAM if self.enabled else CREAM_DIM)
        self.create_line(left, mid, right, mid, fill=track, width=2)
        self.create_line(left, mid, knob_x, mid, fill=fill, width=2)
        self.create_rectangle(
            knob_x - self.KNOB_W / 2,
            mid - self.KNOB_H / 2,
            knob_x + self.KNOB_W / 2,
            mid + self.KNOB_H / 2,
            fill=knob,
            outline=BG,
        )

    def _set_hover(self, inside: bool) -> None:
        self._hover = inside
        self.redraw()

    def _press(self, event: tk.Event) -> None:
        if self.enabled:
            self._active = True
            self.set(self._x_to_value(event.x))

    def _drag(self, event: tk.Event) -> None:
        if self._active:
            self.set(self._x_to_value(event.x))

    def _release(self, _event: tk.Event) -> None:
        if self._active:
            self._active = False
            self.redraw()

    def _wheel(self, event: tk.Event) -> None:
        if self.enabled:
            direction = 1 if event.delta > 0 else -1
            self.set(self.get() + direction * self.resolution)


class FlatButton(tk.Label):
    """Label-as-button. `primary` is gold fill; otherwise cream on a hairline."""

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        primary: bool = False,
        padx: int = 14,
        pady: int = 6,
        font: Font | None = None,
    ) -> None:
        super().__init__(
            master,
            text=text.upper(),
            font=font or font_text(9, "bold"),
            padx=padx,
            pady=pady,
            cursor="hand2",
            highlightthickness=1,
            bd=0,
        )
        self.primary = primary
        self.command = command
        self._paint(False)
        self.bind("<Enter>", lambda _e: self._paint(True))
        self.bind("<Leave>", lambda _e: self._paint(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)

    def set_text(self, text: str) -> None:
        self.configure(text=text.upper())

    def _paint(self, hover: bool) -> None:
        if self.primary:
            color = GOLD_HI if hover else GOLD
            self.configure(background=color, foreground=INK, highlightbackground=color, highlightcolor=color)
        else:
            edge = GOLD if hover else RULE
            self.configure(
                background=SURFACE_HI if hover else SURFACE,
                foreground=GOLD if hover else CREAM,
                highlightbackground=edge,
                highlightcolor=edge,
            )

    def _press(self, _event: tk.Event) -> None:
        if self.primary:
            self.configure(background=GOLD_DIM, foreground=CREAM)
        else:
            self.configure(background=SURFACE_HI, foreground=GOLD_HI)

    def _release(self, event: tk.Event) -> None:
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        self._paint(inside)
        if inside:
            self.command()


class Segmented(tk.Frame):
    """Exclusive cells; selected cell is gold."""

    def __init__(
        self,
        master: tk.Misc,
        options: Sequence[tuple[object, str]],
        variable: tk.Variable,
        command: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, background=RULE, padx=1, pady=1)
        self.variable = variable
        self.command = command
        self._cells: list[tuple[object, tk.Label]] = []
        for index, (value, text) in enumerate(options):
            cell = tk.Label(self, text=text.upper(), font=font_text(9, "bold"), padx=14, pady=5, cursor="hand2", bd=0)
            cell.grid(row=0, column=index, padx=(0 if index == 0 else 1, 0), sticky="nsew")
            cell.bind("<ButtonRelease-1>", lambda _e, v=value: self._choose(v))
            cell.bind("<Enter>", lambda _e, c=cell, v=value: self._hover(c, v, True))
            cell.bind("<Leave>", lambda _e, c=cell, v=value: self._hover(c, v, False))
            self._cells.append((value, cell))
        self.refresh()

    def _selected(self, value: object) -> bool:
        current = self.variable.get()
        if isinstance(self.variable, tk.BooleanVar):
            return bool(current) == bool(value)
        return str(current) == str(value)

    def _hover(self, cell: tk.Label, value: object, inside: bool) -> None:
        if not self._selected(value):
            cell.configure(foreground=CREAM if inside else CREAM_DIM, background=SURFACE_HI if inside else SURFACE)

    def _choose(self, value: object) -> None:
        self.variable.set(value)
        self.refresh()
        if self.command is not None:
            self.command()

    def refresh(self) -> None:
        for value, cell in self._cells:
            if self._selected(value):
                cell.configure(background=GOLD, foreground=INK)
            else:
                cell.configure(background=SURFACE, foreground=CREAM_DIM)


class CheckBox(tk.Frame):
    """Checkbox that traces its BooleanVar, including programmatic sets."""

    BOX = 16

    def __init__(
        self,
        master: tk.Misc,
        text: str,
        variable: tk.BooleanVar,
        command: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, background=SURFACE, cursor="hand2")
        self.variable = variable
        self.command = command
        self._hover = False
        self.box = tk.Canvas(self, width=self.BOX, height=self.BOX, background=SURFACE, highlightthickness=0, bd=0)
        self.box.pack(side=tk.LEFT)
        self.label = tk.Label(self, text=text, font=font_text(10), background=SURFACE, foreground=CREAM)
        self.label.pack(side=tk.LEFT, padx=(10, 0))
        for widget in (self, self.box, self.label):
            widget.bind("<ButtonRelease-1>", self._toggle)
            widget.bind("<Enter>", lambda _e: self._set_hover(True))
            widget.bind("<Leave>", lambda _e: self._set_hover(False))
        variable.trace_add("write", lambda *_args: self.refresh())
        self.refresh()

    def _set_hover(self, inside: bool) -> None:
        self._hover = inside
        self.refresh()

    def _toggle(self, _event: tk.Event) -> None:
        self.variable.set(not bool(self.variable.get()))
        if self.command is not None:
            self.command()

    def refresh(self) -> None:
        on = bool(self.variable.get())
        lit = on or self._hover
        box = self.box
        box.delete("all")
        box.create_rectangle(
            1, 1, self.BOX - 1, self.BOX - 1, fill=GOLD if on else SURFACE_HI, outline=GOLD if lit else RULE
        )
        if on:
            box.create_line(4, 8, 7, 11, 12, 5, fill=INK, width=2, capstyle=tk.ROUND, joinstyle=tk.ROUND)
        self.label.configure(foreground=CREAM if lit else CREAM_DIM)


class TabBar(tk.Frame):
    """Tab titles; active tab has a gold underline."""

    def __init__(self, master: tk.Misc, on_select: Callable[[str], None]) -> None:
        super().__init__(master, background=BG)
        self._on_select = on_select
        self._tabs: dict[str, tuple[tk.Label, tk.Frame]] = {}
        self._current: str | None = None

    def add(self, key: str, title: str) -> None:
        column = len(self._tabs)
        gap = (0 if column == 0 else 22, 0)
        label = tk.Label(
            self,
            text=title.upper(),
            font=font_text(10, "bold"),
            background=BG,
            foreground=CREAM_DIM,
            padx=2,
            pady=6,
            cursor="hand2",
        )
        label.grid(row=0, column=column, padx=gap, sticky="w")
        underline = tk.Frame(self, background=BG, height=2)
        underline.grid(row=1, column=column, padx=gap, sticky="ew")
        label.bind("<ButtonRelease-1>", lambda _e, k=key: self.select(k))
        label.bind("<Enter>", lambda _e, k=key: self._hover(k, True))
        label.bind("<Leave>", lambda _e, k=key: self._hover(k, False))
        self._tabs[key] = (label, underline)
        if self._current is None:
            self.select(key)

    @property
    def current(self) -> str | None:
        return self._current

    def _hover(self, key: str, inside: bool) -> None:
        if key != self._current:
            self._tabs[key][0].configure(foreground=CREAM if inside else CREAM_DIM)

    def select(self, key: str) -> None:
        self._current = key
        for name, (label, underline) in self._tabs.items():
            active = name == key
            label.configure(foreground=CREAM if active else CREAM_DIM)
            underline.configure(background=GOLD if active else BG)
        self._on_select(key)
