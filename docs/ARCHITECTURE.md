# Architecture

One thread besides the window. It runs the loop in `src/daemon/engine.py` and owns everything that touches the screen.

## The loop

```text
every 10 ms
  paused?                        → restore baseline, publish PAUSED
  every 0.5 s (or window gone)   → find PioneerGame.exe's largest visible window
  no window?                     → restore baseline, close capture, publish NO_GAME
  not foreground?                → restore baseline, publish UNFOCUSED
  monitor changed?               → reopen capture on that monitor, read HDR flag
  due for a menu check           → grab the ESC button rectangle
  due for a brightness sample    → grab the circle as a 96×96 grid
  in menu?                       → target 1.00, publish MENU
  manual?                        → target manual gamma
  every 20 ms                    → glide one step towards the target, write the ramp, publish RAID
```

Timing is driven by `perf_counter`, not by sleeps: a late frame does not become a jump because the glide caps `dt` at 50 ms.

## Capture (`kernel/capture.py`)

Desktop Duplication through dxcam's internals, one `AcquireNextFrame` per sample. Two things leave video memory:

- the circle, reduced on the GPU by a compute-shader box filter into a 96×96 RGBA grid (36 KB), or, in CPU mode, copied as its bounding square and box-averaged in numpy;
- the ESC button rectangle, copied one-to-one (a few KB).

The full frame is never read back. Rotated monitors are handled by mapping rectangles into texture space and rotating the small results back.

## Menu detection (`modules/menu.py`)

The ESC button in the lower-left corner is compared by outline (gradient magnitude) against `assets/esc_template.npy`, so it works on bright and dark backgrounds alike. The exact box for 1080p and 1440p is known; other sizes scale the nearest. A ±3 px search runs only when the exact match is inconclusive. `MenuLatch` enters the menu on the first sighting and leaves after two misses.

## Brightness → gamma (`modules/weights.py`, `daemon/engine.py`)

The circle's grid is dotted with a weight mask built from the influence curve: X is the share of area from the center, Y the cumulative share of influence; the weight of a pixel is the slope of the polyline at its own area share. The weighted luma maps linearly to a target: ceiling at black, floor at luma ≥ 0.5. `adopt_target` ignores changes smaller than the threshold; the first frame is compared against the floor so a bright scene cannot lock in a boost.

## Gamma (`kernel/gamma.py`)

`g = 1` is the monitor's own ramp, saved on first contact. For `g > 1` the same index remap `255·(i/255)^(1/g)` is applied to each channel of the baseline, which keeps the calibration and avoids a colour cast. Ramps are quantized to 0.01 and cached. The baseline file carries a dirty marker written before each ramp write; a crashed run is repaired on the next start. If the driver rejects a ramp, the last accepted level becomes the ceiling until a setting changes.

## Window (`src/ui/`)

Plain tk with custom-drawn controls. The daemon publishes a `Status` (state, gamma, flags, error key); the window turns it into text in the active language. The green overlay is a separate click-through, non-activating toplevel that is excluded from screen capture, so the sampler never sees it.
