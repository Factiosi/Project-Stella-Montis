"""GDI gamma ramps composed on a saved per-monitor baseline.

g = 1 is the baseline, byte-identical. g > 1 remaps the 256-entry index
`src = 255·(i/255)^(1/g)` on each channel separately so a grey boost cannot
erase calibration or introduce a tint. Drivers reject a ramp that is not
strictly increasing or that moves the endpoints.
"""

from __future__ import annotations

import ctypes
import struct
import winreg
from pathlib import Path

import numpy as np

RAMP_POINTS = 256
CHANNELS = 3
RAMP_WORDS = RAMP_POINTS * CHANNELS
RAMP_SHAPE = (CHANNELS, RAMP_POINTS)
MAGIC = b"PSMG"
VERSION = 1

ICM_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ICM"
ICM_VALUE = "GdiIcmGammaRange"
ICM_FULL_RANGE = 256

gdi32 = ctypes.windll.gdi32
user32 = ctypes.windll.user32
gdi32.CreateDCW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_void_p]
gdi32.CreateDCW.restype = ctypes.c_void_p
gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
gdi32.DeleteDC.restype = ctypes.c_int
gdi32.GetDeviceGammaRamp.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.GetDeviceGammaRamp.restype = ctypes.c_int
gdi32.SetDeviceGammaRamp.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.restype = ctypes.c_int
user32.GetDC.argtypes = [ctypes.c_void_p]
user32.GetDC.restype = ctypes.c_void_p
user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.ReleaseDC.restype = ctypes.c_int


def quantize_gamma(gamma: float) -> float:
    """Quantize to 0.01 — the step at which a new GDI write is worth doing."""
    return round(float(gamma) * 100.0) / 100.0


def compose_ramp(baseline: np.ndarray, gamma: float) -> np.ndarray:
    """Index-remap `baseline` so dark LUT slots sample a brighter baseline index."""
    base = np.ascontiguousarray(baseline, dtype=np.uint16)
    if base.shape != RAMP_SHAPE:
        raise ValueError("Gamma baseline must be 3×256.")
    level = quantize_gamma(gamma)
    if level <= 1.0:
        return base.copy()

    index = np.arange(RAMP_POINTS, dtype=np.float64)
    source = 255.0 * np.power(index / 255.0, 1.0 / level)
    left = np.floor(source).astype(np.int32)
    right = np.minimum(left + 1, RAMP_POINTS - 1)
    mix = source - left
    out = np.empty_like(base)
    for channel in range(CHANNELS):
        samples = base[channel].astype(np.float64)
        values = samples[left] * (1.0 - mix) + samples[right] * mix
        _pin_ends_and_rise(values, samples)
        out[channel] = np.clip(np.rint(values), 0, 65535).astype(np.uint16)
    return out


def _pin_ends_and_rise(values: np.ndarray, samples: np.ndarray) -> None:
    """Pin endpoints to the baseline and force a strict rise. SetDeviceGammaRamp
    rejects anything else."""
    values[0] = samples[0]
    values[-1] = samples[-1]
    if samples[0] >= samples[-1]:
        return
    for point in range(1, RAMP_POINTS):
        if values[point] <= values[point - 1]:
            values[point] = values[point - 1] + 1.0
    if values[-1] > samples[-1]:
        values[-1] = samples[-1]
        for point in range(RAMP_POINTS - 2, -1, -1):
            if values[point] >= values[point + 1]:
                values[point] = values[point + 1] - 1.0
        values[0] = samples[0]


class RampCache:
    """Composed ramps, keyed by quantized gamma for the current baseline."""

    def __init__(self) -> None:
        self._cache: dict[float, np.ndarray] = {}

    def reset(self) -> None:
        self._cache.clear()

    def get(self, baseline: np.ndarray, gamma: float) -> np.ndarray:
        level = quantize_gamma(gamma)
        if level <= 1.0:
            return baseline
        found = self._cache.get(level)
        if found is None:
            found = compose_ramp(baseline, level)
            self._cache[level] = found
        return found


def _open_dc(device_name: str) -> tuple[ctypes.c_void_p, bool]:
    """HDC for `device_name`. Second value is True if the caller must DeleteDC
    (CreateDCW), False if it must ReleaseDC (GetDC fallback)."""
    name = device_name or None
    hdc = gdi32.CreateDCW(name, None, None, None)
    if hdc:
        return hdc, True
    hdc = gdi32.CreateDCW("DISPLAY", name, None, None)
    if hdc:
        return hdc, True
    return user32.GetDC(None), False


def _close_dc(hdc: ctypes.c_void_p, owned: bool) -> None:
    if not hdc:
        return
    if owned:
        gdi32.DeleteDC(hdc)
    else:
        user32.ReleaseDC(None, hdc)


def read_ramp(device_name: str) -> np.ndarray:
    hdc, owned = _open_dc(device_name)
    if not hdc:
        raise OSError(f"Cannot open a device context for {device_name}.")
    buffer = (ctypes.c_ushort * RAMP_WORDS)()
    try:
        if not gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(buffer)):
            raise OSError(f"GetDeviceGammaRamp failed for {device_name}.")
        return np.ctypeslib.as_array(buffer).reshape(RAMP_SHAPE).copy()
    finally:
        _close_dc(hdc, owned)


def write_ramp(device_name: str, ramp: np.ndarray) -> bool:
    packed = np.ascontiguousarray(ramp, dtype=np.uint16)
    if packed.shape != RAMP_SHAPE:
        raise ValueError("Gamma ramp must be 3×256.")
    hdc, owned = _open_dc(device_name)
    if not hdc:
        return False
    buffer = (ctypes.c_ushort * RAMP_WORDS).from_buffer_copy(packed.tobytes())
    try:
        return bool(gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(buffer)))
    finally:
        _close_dc(hdc, owned)


class BaselineStore:
    """On-disk baselines plus a dirty-device marker.

    `mark_dirty` writes the file *before* SetDeviceGammaRamp. After a crash
    `recover` restores that file instead of reading the already-modified LUT.

    Layout, LE: MAGIC, u32 version, u16 dirty-name len, name, u16 count;
    then per device: u16 name len, name, 3×256 u16.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self.baselines: dict[str, np.ndarray] = {}
        self.dirty_device: str | None = None

    def load(self) -> None:
        if not self.path.exists():
            return
        blob = self.path.read_bytes()
        if len(blob) < 10 or blob[:4] != MAGIC:
            return
        version, name_len = struct.unpack_from("<IH", blob, 4)
        if version != VERSION:
            return
        cursor = 10
        if cursor + name_len + 2 > len(blob):
            return
        dirty = blob[cursor : cursor + name_len].decode("utf-8") if name_len else ""
        cursor += name_len
        count = struct.unpack_from("<H", blob, cursor)[0]
        cursor += 2
        baselines: dict[str, np.ndarray] = {}
        for _ in range(count):
            if cursor + 2 > len(blob):
                return
            length = struct.unpack_from("<H", blob, cursor)[0]
            cursor += 2
            if cursor + length + RAMP_WORDS * 2 > len(blob):
                return
            device = blob[cursor : cursor + length].decode("utf-8")
            cursor += length
            words = np.frombuffer(blob[cursor : cursor + RAMP_WORDS * 2], dtype="<u2").copy()
            cursor += RAMP_WORDS * 2
            baselines[device] = words.reshape(RAMP_SHAPE)
        self.baselines = baselines
        self.dirty_device = dirty or None

    def recover(self) -> None:
        """Restore the marked device from disk if a previous run died dirty."""
        device = self.dirty_device
        if not device or device not in self.baselines:
            return
        if write_ramp(device, self.baselines[device]):
            self.dirty_device = None
            self.save()

    def save(self) -> None:
        dirty = (self.dirty_device or "").encode("utf-8")
        parts = [MAGIC, struct.pack("<IH", VERSION, len(dirty)), dirty, struct.pack("<H", len(self.baselines))]
        for device, ramp in self.baselines.items():
            name = device.encode("utf-8")
            parts.extend((struct.pack("<H", len(name)), name, np.ascontiguousarray(ramp, dtype="<u2").tobytes()))
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_bytes(b"".join(parts))
        temporary.replace(self.path)

    def ensure(self, device_name: str) -> np.ndarray:
        """Return the stored baseline, or read and persist GetDeviceGammaRamp once."""
        found = self.baselines.get(device_name)
        if found is not None:
            return found
        ramp = read_ramp(device_name)
        self.baselines[device_name] = ramp
        self.save()
        return ramp

    def mark_dirty(self, device_name: str) -> None:
        if self.dirty_device != device_name:
            self.dirty_device = device_name
            self.save()

    def clear_dirty(self) -> None:
        if self.dirty_device is not None:
            self.dirty_device = None
            self.save()


def icm_range_value() -> int | None:
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ICM_KEY, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, _kind = winreg.QueryValueEx(key, ICM_VALUE)
            return int(value)
    except OSError:
        return None


def try_enable_full_range() -> bool:
    """Set HKLM GdiIcmGammaRange=256. Needs admin once; otherwise False."""
    current = icm_range_value()
    if current is not None and current >= ICM_FULL_RANGE:
        return True
    try:
        access = winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY
        with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, ICM_KEY, 0, access) as key:
            winreg.SetValueEx(key, ICM_VALUE, 0, winreg.REG_DWORD, ICM_FULL_RANGE)
        return True
    except OSError:
        return False
