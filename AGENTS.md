# Stella Montis

A single desktop program: it watches the screen while Arc Raiders is in front and drives the monitor's gamma ramp. This file is about working inside this repository.

## Hard limits

- Display only. The program reads pixels through Desktop Duplication and writes `SetDeviceGammaRamp`. It never reads game memory, hooks, injects, or sends input. A change that crosses this line is not accepted, however convenient.
- Smoothness is the product. The displayed gamma moves by a bounded step every 20 ms (`MAX_SLEW` in `src/daemon/engine.py`). Nothing may write a ramp outside `Applicator`.
- The baseline is sacred. The monitor's own ramp is saved before the first write (`psm_baseline.dat`) and restored on exit, on pause, on focus loss and after a crash. Any new code path that writes a ramp must go through `BaselineStore.mark_dirty`.
- The game is never required for the window to open. Every state the daemon can be in has a `State` and a string in both languages.

## Structure

One program. Code lives under `src/`. The root holds the entry, this file, and the docs — nothing that belongs in a package.

```text
psm.py              entry: puts src/ on sys.path, enables DPI awareness, opens the window
src/core/           paths, Settings and PSM.ini, interface strings (locale.py)
src/kernel/         the OS boundary: window.py (Win32), gamma.py (GDI ramps), capture.py (DXGI + D3D11)
src/modules/        menu.py (ESC detector), weights.py (influence curve → weight grid)
src/daemon/         engine.py: the loop, State/Status, glide, Applicator
src/ui/             theme.py, widgets.py, curve.py, overlay.py, app.py
assets/             esc_template.npy — the ESC outline template (39×62 float32); icon.ico — window and executable icon
docs/               ARCHITECTURE.md
```

Layers import downwards only: `ui → daemon → modules/kernel → core`. `core` imports nothing from the others except `modules.weights` for the curve type.

`PSM.ini` and `psm_baseline.dat` are runtime state next to `psm.py`. They are not committed.

## How to continue

- New behaviour that the user sees gets a key in `core/locale.py` for both `en` and `ru`. No literal UI strings in `ui/`.
- A new setting goes into `Settings` with a bound in `clamped()`, then into `load_settings`/`save_settings`, then into the window. The daemon reads settings only through `self._settings` under the lock.
- The daemon publishes state through `Engine._publish`; the window formats it in `App._render`. Do not put text in the daemon.
- Capture is fragile by nature. Pass comtypes pointers straight into `CopyResource`/`CopySubresourceRegion`; casting them to `POINTER(ID3D11Resource)` crashes. The first frame after `DuplicateOutput` is black and is skipped.
- The window is plain `tk`, no `ttk`. Controls live in `ui/widgets.py`; a new control goes there, not into `app.py`.
- The look is the game's: near-black surfaces, cream text, one gold accent, four signal stripes, Bahnschrift and JetBrains Mono.
- Comments and docstrings are English. They record contracts and traps, not a narration of the next line.

## Verify

There is no test suite. Before handing over:

- `python psm.py` opens the window, the status reads "Game not running", closing it leaves the gamma ramp byte-identical to before.
- With the game in a raid, the status reads "In raid" and the gamma glides rather than jumps; opening the inventory reads "In menu" and glides back to 1.00.
- Both compute modes sample the same circle (GPU grid vs CPU grid correlate at 1.0).

Scratch scripts and screenshots stay outside the repository.

## Version

The manifest is `pyproject.toml`. The number there is `1.0.0`. A release commit is `Release 1.0.0` on `main`, with the tag `v1.0.0`. Work commits do not carry a version number. The Nuitka tree is `build/psm.dist`; `installer/setup.iss` packages it and is not run from here.

## What not to bring back

The original sketches (`menu_watch.py`, `learn_esc.py`), the compiled `PSM.exe`, logs, screenshots of the menu, `__pycache__`. History lives in git.
