"""Desktop Duplication: circle → 96×96 luma grid, ESC box → BGRA crop.

The full frame stays in video memory. GPU path: compute-shader box filter
into a UAV, then a 36 KB staging read. CPU path: CopySubresourceRegion of
the circle square, then `box_average`.

D3D11 calls dxcam does not wrap (CS, UAV, Map) go through raw vtable
slots. Pass comtypes pointers into CopyResource / CopySubresourceRegion
as-is — `cast(..., POINTER(ID3D11Resource))` access-violates.
"""

from __future__ import annotations

import ctypes
from collections.abc import Callable
from ctypes import wintypes
from typing import Any, cast

import comtypes
import numpy as np

comtypes.CoInitialize()

from dxcam._libs.d3d11 import (  # noqa: E402
    D3D11_BOX,
    D3D11_CPU_ACCESS_READ,
    D3D11_TEXTURE2D_DESC,
    D3D11_USAGE_DEFAULT,
    D3D11_USAGE_DYNAMIC,
    D3D11_USAGE_STAGING,
    DXGI_FORMAT_B8G8R8A8_UNORM,
    ID3D11Multithread,
    ID3D11Texture2D,
)
from dxcam._libs.dxgi import (  # noqa: E402
    DXGI_ERROR_ACCESS_LOST,
    DXGI_ERROR_WAIT_TIMEOUT,
    DXGI_MAPPED_RECT,
    DXGI_OUTDUPL_FRAME_INFO,
    IDXGIResource,
    IDXGISurface,
)
from dxcam.core.dxgi_duplicator import DXGIDuplicator  # noqa: E402
from dxcam.core.dxgi_errors import com_error_hresult_u32, hresult_u32  # noqa: E402

from modules.weights import GRID  # noqa: E402

DXGI_FORMAT_R8G8B8A8_UNORM = 28
D3D11_BIND_UNORDERED_ACCESS = 0x80
D3D11_BIND_CONSTANT_BUFFER = 0x4
D3D11_CPU_ACCESS_WRITE = 0x10000
D3D11_MAP_WRITE_DISCARD = 4
D3D11_UAV_DIMENSION_TEXTURE2D = 4
DXGI_MAP_READ = 1
TIMEOUT_CODE = hresult_u32(DXGI_ERROR_WAIT_TIMEOUT)
LOST_CODE = hresult_u32(DXGI_ERROR_ACCESS_LOST)

# ID3D11Device vtable slots.
VT_CREATE_BUFFER = 3
VT_CREATE_SRV = 7
VT_CREATE_UAV = 8
VT_CREATE_COMPUTE_SHADER = 18
# ID3D11DeviceContext vtable slots.
VT_MAP = 14
VT_UNMAP = 15
VT_DISPATCH = 41
VT_CS_SET_SRV = 67
VT_CS_SET_UAV = 68
VT_CS_SET_SHADER = 69
VT_CS_SET_CB = 71

Rect = tuple[int, int, int, int]

SHADER = f"""
Texture2D<float4> Source : register(t0);
RWTexture2D<float4> Destination : register(u0);

cbuffer Params : register(b0) {{
    uint OriginX;
    uint OriginY;
    uint SourceWidth;
    uint SourceHeight;
}};

[numthreads(8, 8, 1)]
void main(uint3 id : SV_DispatchThreadID) {{
    if (id.x >= {GRID} || id.y >= {GRID}) return;
    uint x0 = OriginX + (id.x * SourceWidth) / {GRID};
    uint x1 = OriginX + ((id.x + 1) * SourceWidth) / {GRID};
    uint y0 = OriginY + (id.y * SourceHeight) / {GRID};
    uint y1 = OriginY + ((id.y + 1) * SourceHeight) / {GRID};
    if (x1 <= x0) x1 = x0 + 1;
    if (y1 <= y0) y1 = y0 + 1;
    float4 sum = 0;
    uint count = 0;
    [loop]
    for (uint y = 0; y < 48; y++) {{
        uint sy = y0 + y;
        if (sy >= y1) break;
        [loop]
        for (uint x = 0; x < 48; x++) {{
            uint sx = x0 + x;
            if (sx >= x1) break;
            sum += Source[uint2(sx, sy)];
            count++;
        }}
    }}
    Destination[id.xy] = sum / max(count, 1);
}}
"""


class ID3DBlob(comtypes.IUnknown):
    _iid_ = comtypes.GUID("{8BA5FB08-5195-40e2-AC58-0D989C3A0102}")
    _methods_ = [
        comtypes.STDMETHOD(ctypes.c_void_p, "GetBufferPointer"),
        comtypes.STDMETHOD(ctypes.c_size_t, "GetBufferSize"),
    ]


class D3D11_BUFFER_DESC(ctypes.Structure):
    _fields_ = [
        ("ByteWidth", wintypes.UINT),
        ("Usage", wintypes.UINT),
        ("BindFlags", wintypes.UINT),
        ("CPUAccessFlags", wintypes.UINT),
        ("MiscFlags", wintypes.UINT),
        ("StructureByteStride", wintypes.UINT),
    ]


class D3D11_UNORDERED_ACCESS_VIEW_DESC(ctypes.Structure):
    _fields_ = [
        ("Format", wintypes.UINT),
        ("ViewDimension", wintypes.UINT),
        ("MipSlice", wintypes.UINT),
        ("FirstArraySlice", wintypes.UINT),
        ("ArraySize", wintypes.UINT),
    ]


class D3D11_MAPPED_SUBRESOURCE(ctypes.Structure):
    _fields_ = [
        ("pData", ctypes.c_void_p),
        ("RowPitch", wintypes.UINT),
        ("DepthPitch", wintypes.UINT),
    ]


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class _DisplayHeader(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
    ]


class _SourceName(ctypes.Structure):
    _fields_ = [
        ("header", _DisplayHeader),
        ("viewGdiDeviceName", wintypes.WCHAR * 32),
    ]


class _AdvancedColor(ctypes.Structure):
    _fields_ = [
        ("header", _DisplayHeader),
        ("value", wintypes.UINT),
        ("colorEncoding", wintypes.UINT),
        ("bitsPerColorChannel", wintypes.UINT),
    ]


class _PathSource(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class _PathTarget(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshNumerator", wintypes.UINT),
        ("refreshDenominator", wintypes.UINT),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class _PathInfo(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", _PathSource),
        ("targetInfo", _PathTarget),
        ("flags", wintypes.UINT),
    ]


def _vfunc(com_ptr: Any, index: int, restype: Any, argtypes: list[Any]) -> Callable[..., Any]:
    """Bind vtable slot `index`. The IUnknown `this` is prepended on each call."""
    table = ctypes.cast(com_ptr, ctypes.POINTER(ctypes.c_void_p))[0]
    function = ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))[index]
    call = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)(function)
    this = ctypes.cast(com_ptr, ctypes.c_void_p)

    def invoke(*args: Any) -> Any:
        return call(this, *args)

    return invoke


def _check(hr: int, action: str) -> None:
    code = int(hr) & 0xFFFFFFFF
    if code >= 0x80000000:
        raise RuntimeError(f"{action}: 0x{code:08X}")


def _release(pointer: ctypes.c_void_p | None) -> None:
    """IUnknown::Release on a raw pointer from `_vfunc`, not a comtypes wrapper."""
    if not pointer:
        return
    address = pointer.value if isinstance(pointer, ctypes.c_void_p) else int(pointer)
    if not address:
        return
    table = ctypes.cast(address, ctypes.POINTER(ctypes.c_void_p))[0]
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
        ctypes.cast(table, ctypes.POINTER(ctypes.c_void_p))[2]
    )
    release(address)


def compile_shader() -> bytes:
    compiler = ctypes.WinDLL("d3dcompiler_47")
    compiler.D3DCompile.argtypes = [
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.POINTER(ID3DBlob)),
        ctypes.POINTER(ctypes.POINTER(ID3DBlob)),
    ]
    compiler.D3DCompile.restype = ctypes.HRESULT
    source = SHADER.encode("ascii")
    buffer = ctypes.create_string_buffer(source)
    code = ctypes.POINTER(ID3DBlob)()
    errors = ctypes.POINTER(ID3DBlob)()
    result = compiler.D3DCompile(
        buffer,
        len(source),
        b"circle_box.hlsl",
        None,
        None,
        b"main",
        b"cs_5_0",
        1 << 15,
        0,
        ctypes.byref(code),
        ctypes.byref(errors),
    )
    if int(result) < 0:
        text = ""
        if errors:
            text = ctypes.string_at(errors.GetBufferPointer(), errors.GetBufferSize()).decode("utf-8", "replace")
        raise RuntimeError(f"Box-filter shader failed to compile: {text}")
    return ctypes.string_at(code.GetBufferPointer(), code.GetBufferSize())


def memory_box(region: Rect, rotation: int, surface: tuple[int, int]) -> Rect | None:
    """Map a screen-space rect into the unrotated DXGI texture."""
    left, top, right, bottom = region
    width, height = surface
    if rotation == 90:
        left, top, right, bottom = top, height - right, bottom, height - left
    elif rotation == 180:
        left, top, right, bottom = width - right, height - bottom, width - left, height - top
    elif rotation == 270:
        left, top, right, bottom = width - bottom, left, width - top, right
    left = max(0, min(width, int(left)))
    top = max(0, min(height, int(top)))
    right = max(0, min(width, int(right)))
    bottom = max(0, min(height, int(bottom)))
    if right - left < 2 or bottom - top < 2:
        return None
    return left, top, right, bottom


def orient_screen(image: np.ndarray, rotation: int) -> np.ndarray:
    """Rotate a texture-space array back to screen orientation."""
    if rotation == 90:
        return np.rot90(image, axes=(1, 0))
    if rotation == 180:
        return np.rot90(image, k=2)
    if rotation == 270:
        return np.rot90(image, axes=(0, 1))
    return image


def hdr_enabled(device_name: str) -> bool:
    """True if Advanced Color is on. GDI ramps are then usually a no-op."""
    try:
        return _hdr_enabled(device_name)
    except (OSError, ValueError):
        return False


def _hdr_enabled(device_name: str) -> bool:
    user32 = ctypes.windll.user32
    path_count = wintypes.UINT()
    mode_count = wintypes.UINT()
    if user32.GetDisplayConfigBufferSizes(2, ctypes.byref(path_count), ctypes.byref(mode_count)) != 0:
        return False
    paths = (_PathInfo * path_count.value)()
    modes = (ctypes.c_byte * (mode_count.value * 64))()
    if user32.QueryDisplayConfig(2, ctypes.byref(path_count), paths, ctypes.byref(mode_count), modes, None) != 0:
        return False
    wanted = device_name.casefold()
    for index in range(path_count.value):
        path = paths[index]
        name = _SourceName()
        name.header.type = 1
        name.header.size = ctypes.sizeof(_SourceName)
        name.header.adapterId = path.sourceInfo.adapterId
        name.header.id = path.sourceInfo.id
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(name)) != 0:
            continue
        if name.viewGdiDeviceName.split("\x00", 1)[0].casefold() != wanted:
            continue
        color = _AdvancedColor()
        color.header.type = 9
        color.header.size = ctypes.sizeof(_AdvancedColor)
        color.header.adapterId = path.targetInfo.adapterId
        color.header.id = path.targetInfo.id
        if user32.DisplayConfigGetDeviceInfo(ctypes.byref(color)) != 0:
            return False
        return bool(color.value & 0x2)
    return False


def _find_output(device_name: str) -> tuple[Any, Any, str]:
    import dxcam

    factory = dxcam.__factory
    wanted = device_name.casefold()
    for device, outputs in zip(factory.devices, factory.outputs, strict=True):
        for output in outputs:
            output.update_desc()
            name = str(output.devicename).split("\x00", 1)[0]
            if name.casefold() == wanted:
                return device, output, name
    raise RuntimeError(f"Monitor {device_name} is not among the DXGI outputs.")


class _Staging:
    """Staging texture + DXGI surface, rebuilt only when size changes."""

    def __init__(self) -> None:
        self.texture: Any = None
        self.surface: Any = None
        self.size = (0, 0)

    def release(self) -> None:
        if self.texture is not None:
            self.texture.Release()
        self.texture = None
        self.surface = None
        self.size = (0, 0)


class CaptureSession:
    """One DXGI output. `compute` is `gpu` (CS box filter) or `cpu` (numpy)."""

    def __init__(self, compute: str = "gpu") -> None:
        self.compute = "cpu" if str(compute).lower() == "cpu" else "gpu"
        self.hdr = False
        self._device_name = ""
        self._device: Any = None
        self._output: Any = None
        self._context: Any = None
        self._dup: DXGIDuplicator | None = None
        self._shader = ctypes.c_void_p()
        self._params = ctypes.c_void_p()
        self._grid_tex: Any = None
        self._grid_uav = ctypes.c_void_p()
        self._grid = _Staging()
        self._esc = _Staging()
        self._square = _Staging()
        self._primed = False
        self._protected = False
        self._dispatch: Callable[..., Any] | None = None
        self._bind_shader: Callable[..., Any] | None = None
        self._bind_srv: Callable[..., Any] | None = None
        self._bind_uav: Callable[..., Any] | None = None
        self._bind_cb: Callable[..., Any] | None = None
        self._map: Callable[..., Any] | None = None
        self._unmap: Callable[..., Any] | None = None
        self._create_srv: Callable[..., Any] | None = None

    @property
    def is_open(self) -> bool:
        return self._dup is not None

    @property
    def rotation(self) -> int:
        return 0 if self._output is None else int(self._output.rotation_angle)

    @property
    def surface_size(self) -> tuple[int, int]:
        if self._output is None:
            return (0, 0)
        self._output.update_desc()
        width, height = self._output.surface_size
        return int(width), int(height)

    def open(self, device_name: str) -> None:
        if self._device_name == device_name and self._dup is not None:
            return
        self.close()
        device, output, name = _find_output(device_name)
        self._protect(device.device)
        self._device = device
        self._output = output
        self._context = device.im_context
        self._device_name = name
        self.hdr = hdr_enabled(name)
        if self.compute == "gpu":
            self._build_gpu()
        self._dup = DXGIDuplicator(output=output, device=device)
        self._primed = False

    def close(self) -> None:
        if self._dup is not None:
            self._dup.release()
            self._dup = None
        for pointer in (self._shader, self._params, self._grid_uav):
            _release(pointer)
        self._shader = ctypes.c_void_p()
        self._params = ctypes.c_void_p()
        self._grid_uav = ctypes.c_void_p()
        if self._grid_tex is not None:
            self._grid_tex.Release()
            self._grid_tex = None
        for staging in (self._grid, self._esc, self._square):
            staging.release()
        self._device_name = ""
        self._device = None
        self._output = None
        self._context = None

    def grab(
        self, circle: Rect | None, esc: Rect | None, timeout_ms: int
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """One AcquireNextFrame. Returns (96×96 luma 0..1 | None, ESC BGRA | None)."""
        if self._dup is None:
            raise RuntimeError("Capture is not open.")
        if not self._acquire(timeout_ms):
            return None, None
        try:
            if not self._primed:
                # First AcquireNextFrame after DuplicateOutput is black. Drop it.
                self._primed = True
                if self._dup is not None:
                    self._dup.release_frame()
                if not self._acquire(timeout_ms):
                    return None, None
            if circle is None:
                grid = None
            elif self.compute == "gpu":
                grid = self._downsample_gpu(circle)
            else:
                grid = self._downsample_cpu(circle)
            button = self._copy_esc(esc) if esc is not None else None
            return grid, button
        finally:
            if self._dup is not None and not self._dup.release_frame():
                self._reopen()

    # --- duplication -----------------------------------------------------------

    def _protect(self, device: Any) -> None:
        if self._protected:
            return
        multithread = device.QueryInterface(ID3D11Multithread)
        multithread.SetMultithreadProtected(True)
        self._protected = True

    def _reopen(self) -> None:
        name, device, output = self._device_name, self._device, self._output
        if self._dup is not None:
            self._dup.release()
            self._dup = None
        if device is None or output is None or not name:
            return
        try:
            output.update_desc()
            self._dup = DXGIDuplicator(output=output, device=device)
            self._primed = False
        except comtypes.COMError:
            self._dup = None

    def _acquire(self, timeout_ms: int) -> bool:
        if self._dup is None:
            return False
        if self._dup._frame_held and not self._dup.release_frame():
            self._reopen()
            return False
        info = DXGI_OUTDUPL_FRAME_INFO()
        resource = ctypes.POINTER(IDXGIResource)()
        try:
            self._dup.duplicator.AcquireNextFrame(max(0, int(timeout_ms)), ctypes.byref(info), ctypes.byref(resource))
        except comtypes.COMError as error:
            code = com_error_hresult_u32(error)
            if code == TIMEOUT_CODE:
                return False
            if code == LOST_CODE:
                self._reopen()
                return False
            raise
        self._dup._frame_held = True
        try:
            self._dup.texture = cast(Any, resource).QueryInterface(ID3D11Texture2D)
        except comtypes.COMError:
            self._dup.release_frame()
            return False
        return True

    # --- GPU path --------------------------------------------------------------

    def _build_gpu(self) -> None:
        assert self._device is not None and self._context is not None
        device = self._device.device
        context = self._context

        bytecode = compile_shader()
        code_buf = ctypes.create_string_buffer(bytecode)
        create_shader = _vfunc(
            device,
            VT_CREATE_COMPUTE_SHADER,
            ctypes.HRESULT,
            [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        shader = ctypes.c_void_p()
        _check(create_shader(code_buf, len(bytecode), None, ctypes.byref(shader)), "CreateComputeShader")
        self._shader = shader

        desc = D3D11_BUFFER_DESC()
        desc.ByteWidth = 16
        desc.Usage = D3D11_USAGE_DYNAMIC
        desc.BindFlags = D3D11_BIND_CONSTANT_BUFFER
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE
        create_buffer = _vfunc(
            device,
            VT_CREATE_BUFFER,
            ctypes.HRESULT,
            [ctypes.POINTER(D3D11_BUFFER_DESC), ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        params = ctypes.c_void_p()
        _check(create_buffer(ctypes.byref(desc), None, ctypes.byref(params)), "CreateBuffer")
        self._params = params

        self._grid_tex = self._texture(
            GRID, GRID, D3D11_USAGE_DEFAULT, D3D11_BIND_UNORDERED_ACCESS, 0, DXGI_FORMAT_R8G8B8A8_UNORM
        )
        view = D3D11_UNORDERED_ACCESS_VIEW_DESC()
        view.Format = DXGI_FORMAT_R8G8B8A8_UNORM
        view.ViewDimension = D3D11_UAV_DIMENSION_TEXTURE2D
        view.MipSlice = 0
        create_uav = _vfunc(
            device,
            VT_CREATE_UAV,
            ctypes.HRESULT,
            [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )
        uav = ctypes.c_void_p()
        _check(
            create_uav(ctypes.cast(self._grid_tex, ctypes.c_void_p), ctypes.byref(view), ctypes.byref(uav)),
            "CreateUnorderedAccessView",
        )
        self._grid_uav = uav

        self._grid.texture = self._texture(
            GRID, GRID, D3D11_USAGE_STAGING, 0, D3D11_CPU_ACCESS_READ, DXGI_FORMAT_R8G8B8A8_UNORM
        )
        self._grid.surface = self._grid.texture.QueryInterface(IDXGISurface)
        self._grid.size = (GRID, GRID)

        self._dispatch = _vfunc(context, VT_DISPATCH, None, [wintypes.UINT, wintypes.UINT, wintypes.UINT])
        self._bind_shader = _vfunc(context, VT_CS_SET_SHADER, None, [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT])
        self._bind_srv = _vfunc(
            context, VT_CS_SET_SRV, None, [wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)]
        )
        self._bind_uav = _vfunc(
            context,
            VT_CS_SET_UAV,
            None,
            [wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p],
        )
        self._bind_cb = _vfunc(
            context, VT_CS_SET_CB, None, [wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)]
        )
        self._map = _vfunc(
            context,
            VT_MAP,
            ctypes.HRESULT,
            [ctypes.c_void_p, wintypes.UINT, wintypes.UINT, wintypes.UINT, ctypes.POINTER(D3D11_MAPPED_SUBRESOURCE)],
        )
        self._unmap = _vfunc(context, VT_UNMAP, None, [ctypes.c_void_p, wintypes.UINT])
        self._create_srv = _vfunc(
            device,
            VT_CREATE_SRV,
            ctypes.HRESULT,
            [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)],
        )

    def _texture(self, width: int, height: int, usage: int, bind: int, cpu: int, fmt: int) -> Any:
        assert self._device is not None
        desc = D3D11_TEXTURE2D_DESC()
        desc.Width = width
        desc.Height = height
        desc.MipLevels = 1
        desc.ArraySize = 1
        desc.Format = fmt
        desc.SampleDesc.Count = 1
        desc.SampleDesc.Quality = 0
        desc.Usage = usage
        desc.BindFlags = bind
        desc.CPUAccessFlags = cpu
        texture = ctypes.POINTER(ID3D11Texture2D)()
        self._device.device.CreateTexture2D(ctypes.byref(desc), None, ctypes.byref(texture))
        return texture

    def _downsample_gpu(self, circle: Rect) -> np.ndarray | None:
        assert self._dup is not None and self._context is not None
        assert (
            self._create_srv
            and self._bind_shader
            and self._bind_srv
            and self._bind_uav
            and self._bind_cb
            and self._dispatch
        )
        box = memory_box(circle, self.rotation, self.surface_size)
        if box is None:
            return None
        left, top, right, bottom = box
        self._write_params(left, top, right - left, bottom - top)
        source = ctypes.c_void_p()
        _check(
            self._create_srv(ctypes.cast(self._dup.texture, ctypes.c_void_p), None, ctypes.byref(source)),
            "CreateShaderResourceView",
        )
        try:
            self._bind_shader(self._shader, None, 0)
            self._bind_srv(0, 1, ctypes.byref(source))
            self._bind_uav(0, 1, ctypes.byref(self._grid_uav), None)
            self._bind_cb(0, 1, ctypes.byref(self._params))
            self._dispatch(GRID // 8, GRID // 8, 1)
            null = ctypes.c_void_p()
            self._bind_uav(0, 1, ctypes.byref(null), None)
            self._bind_srv(0, 1, ctypes.byref(null))
            self._context.CopyResource(self._grid.texture, self._grid_tex)
            return self._read_grid()
        finally:
            _release(source)

    def _write_params(self, origin_x: int, origin_y: int, width: int, height: int) -> None:
        assert self._map and self._unmap
        mapped = D3D11_MAPPED_SUBRESOURCE()
        _check(self._map(self._params, 0, D3D11_MAP_WRITE_DISCARD, 0, ctypes.byref(mapped)), "Map")
        try:
            values = (ctypes.c_uint * 4)(origin_x, origin_y, width, height)
            ctypes.memmove(mapped.pData, values, 16)
        finally:
            self._unmap(self._params, 0)

    def _read_grid(self) -> np.ndarray:
        rect = DXGI_MAPPED_RECT()
        self._grid.surface.Map(ctypes.byref(rect), DXGI_MAP_READ)
        try:
            raw = ctypes.string_at(rect.pBits, rect.Pitch * GRID)
        finally:
            self._grid.surface.Unmap()
        rows = np.frombuffer(raw, dtype=np.uint8).reshape(GRID, rect.Pitch)
        pixels = rows[:, : GRID * 4].reshape(GRID, GRID, 4)
        # UAV is RGBA; BGRA desktop pixels were converted by the shader.
        luma = (0.2126 * pixels[:, :, 0] + 0.7152 * pixels[:, :, 1] + 0.0722 * pixels[:, :, 2]) / 255.0
        return orient_screen(luma.astype(np.float32), self.rotation)

    # --- CPU path --------------------------------------------------------------

    def _copy_rect(self, screen_box: Rect, staging: _Staging) -> np.ndarray | None:
        """Copy `screen_box` 1:1 to staging. Result is BGRA, screen-oriented."""
        assert self._dup is not None and self._context is not None
        box = memory_box(screen_box, self.rotation, self.surface_size)
        if box is None:
            return None
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        self._ensure_staging(staging, width, height)
        region = D3D11_BOX(left, top, 0, right, bottom, 1)
        self._context.CopySubresourceRegion(staging.texture, 0, 0, 0, 0, self._dup.texture, 0, ctypes.byref(region))
        rect = DXGI_MAPPED_RECT()
        staging.surface.Map(ctypes.byref(rect), DXGI_MAP_READ)
        try:
            raw = ctypes.string_at(rect.pBits, rect.Pitch * height)
        finally:
            staging.surface.Unmap()
        rows = np.frombuffer(raw, dtype=np.uint8).reshape(height, rect.Pitch)
        pixels = rows[:, : width * 4].reshape(height, width, 4)
        return orient_screen(pixels, self.rotation)

    def _copy_esc(self, esc: Rect) -> np.ndarray | None:
        pixels = self._copy_rect(esc, self._esc)
        return None if pixels is None else pixels.copy()

    def _downsample_cpu(self, circle: Rect) -> np.ndarray | None:
        """Same integer box edges as the CS, on a BGRA staging copy."""
        pixels = self._copy_rect(circle, self._square)
        if pixels is None:
            return None
        luma = (
            0.2126 * pixels[:, :, 2].astype(np.float32)
            + 0.7152 * pixels[:, :, 1].astype(np.float32)
            + 0.0722 * pixels[:, :, 0].astype(np.float32)
        )
        return box_average(luma, GRID) / 255.0

    def _ensure_staging(self, staging: _Staging, width: int, height: int) -> None:
        if staging.size == (width, height) and staging.texture is not None:
            return
        staging.release()
        staging.texture = self._texture(
            width, height, D3D11_USAGE_STAGING, 0, D3D11_CPU_ACCESS_READ, DXGI_FORMAT_B8G8R8A8_UNORM
        )
        staging.surface = staging.texture.QueryInterface(IDXGISurface)
        staging.size = (width, height)


def box_average(luma: np.ndarray, grid: int) -> np.ndarray:
    """Mean of each integer block. Edges: `(i * dim) // grid`, same as the CS."""
    height, width = luma.shape
    if height < grid or width < grid:
        ys = (np.arange(grid) * height) // grid
        xs = (np.arange(grid) * width) // grid
        return luma[ys][:, xs].astype(np.float32)
    row_edges = (np.arange(grid + 1) * height) // grid
    col_edges = (np.arange(grid + 1) * width) // grid
    row_sum = np.add.reduceat(luma, row_edges[:-1], axis=0)
    cell_sum = np.add.reduceat(row_sum, col_edges[:-1], axis=1)
    counts = np.diff(row_edges)[:, None] * np.diff(col_edges)[None, :]
    return (cell_sum / counts).astype(np.float32)
