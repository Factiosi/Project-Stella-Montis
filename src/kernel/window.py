"""Win32: locate PioneerGame.exe, its monitor, overlay styles.

Process memory is not read. Enumeration is by exe name and visible client size.
"""

from __future__ import annotations

import contextlib
import ctypes
from ctypes import wintypes

PROCESS_NAME = "PioneerGame.exe"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011
MONITOR_DEFAULTTONEAREST = 2
TH32CS_SNAPPROCESS = 0x00000002

Rect = tuple[int, int, int, int]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]


def enable_dpi_awareness() -> None:
    """Per-monitor DPI so GetClientRect / ClientToScreen return pixels, not DIPs."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        with contextlib.suppress(AttributeError, OSError):
            user32.SetProcessDPIAware()


def game_pids() -> list[int]:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        return []
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    found: list[int] = []
    try:
        ok = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == PROCESS_NAME.lower():
                found.append(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    return found


def game_window() -> tuple[int, int, int, int, int] | None:
    """Largest visible client ≥ 640×480: (screen_x, screen_y, w, h, hwnd)."""
    pids = set(game_pids())
    if not pids:
        return None
    found: list[tuple[int, int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if int(pid.value) not in pids:
            return True
        rect = RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
            return True
        width, height = int(rect.right), int(rect.bottom)
        if width < 640 or height < 480:
            return True
        origin = POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
            return True
        found.append((int(origin.x), int(origin.y), width, height, int(hwnd)))
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        return None
    return max(found, key=lambda item: item[2] * item[3])


def is_foreground(hwnd: int) -> bool:
    """True if the foreground HWND is `hwnd` or another window of the same PID."""
    foreground = int(user32.GetForegroundWindow() or 0)
    if foreground == int(hwnd):
        return True
    foreground_pid = wintypes.DWORD()
    window_pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground, ctypes.byref(foreground_pid))
    user32.GetWindowThreadProcessId(int(hwnd), ctypes.byref(window_pid))
    return bool(window_pid.value) and foreground_pid.value == window_pid.value


def _monitor_info(hwnd: int) -> MONITORINFOEXW | None:
    info = MONITORINFOEXW()
    info.cbSize = ctypes.sizeof(MONITORINFOEXW)
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    return info


def monitor_device(hwnd: int) -> str:
    """GDI device name under `hwnd`, e.g. `\\\\.\\DISPLAY1`."""
    info = _monitor_info(hwnd)
    return info.szDevice.split("\x00", 1)[0] if info is not None else ""


def monitor_rect(hwnd: int) -> Rect | None:
    """Monitor bounds in virtual-screen pixels, or None."""
    info = _monitor_info(hwnd)
    if info is None:
        return None
    rect = info.rcMonitor
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def make_overlay(hwnd: int, exclude_from_capture: bool = True) -> None:
    """Layered, click-through, no-activate, tool window. Optional WDA_EXCLUDEFROMCAPTURE
    so Desktop Duplication does not sample this HWND."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    style |= WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    if exclude_from_capture:
        user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
