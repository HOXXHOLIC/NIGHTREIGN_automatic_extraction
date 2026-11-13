"""截图区域修正工具

用途
----
为自动化 OCR 程序修改 config.yaml 中 mss_config 的截图区域。

设计约定
--------
* config.yaml 与 fix_tool.exe 位于同一目录。
* 坐标是虚拟桌面的“绝对物理像素”，副屏可以产生负数。
* 只修改 mss_config 里的 12 个数字，保留 YAML 注释、缩进、空行、换行符。
* 标定时请把游戏切换为无边框窗口化；保存后请重新启动自动化程序。

打包
----
pyinstaller --onefile --windowed --name fix_tool fix_tool.py
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import tempfile
import time
import traceback
from ctypes import wintypes
from dataclasses import dataclass

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox

import mss
import yaml
from PIL import Image, ImageTk


APP_TITLE = "截图区域修正工具"
AUTO_MONITOR = "自动（跟随游戏窗口）"
CONFIG_NAME = "config.yaml"
PNG_NAME = "region.png"
MIN_REGION = 4          # 小于这个尺寸的选区没有意义，直接拒绝
COUNTDOWN_SECONDS = 5


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

def get_base_path() -> str:
    """返回 fix_tool 所在目录（打包后是 exe 目录，源码运行时是脚本目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    if hasattr(sys, "_MEIPASS"):  # noinspection PyProtectedMember
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_PATH = get_base_path()
CONFIG_PATH = os.path.join(BASE_PATH, CONFIG_NAME)
PNG_PATH = os.path.join(BASE_PATH, PNG_NAME)


# ---------------------------------------------------------------------------
# Win32 / DPI
# ---------------------------------------------------------------------------

IS_WINDOWS = sys.platform == "win32"

user32 = None
kernel32 = None
shcore = None
shell32 = None

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
    except OSError:
        shcore = None
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    except OSError:
        shell32 = None


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


HWND_TOPMOST = wintypes.HWND(-1) if IS_WINDOWS else None
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010
MONITOR_DEFAULTTONEAREST = 2
GA_ROOT = 2
ERROR_ALREADY_EXISTS = 183

if IS_WINDOWS:
    if hasattr(user32, "SetProcessDpiAwarenessContext"):
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
    user32.SetProcessDPIAware.argtypes = []
    user32.SetProcessDPIAware.restype = wintypes.BOOL
    if hasattr(user32, "GetDpiForSystem"):
        user32.GetDpiForSystem.argtypes = []
        user32.GetDpiForSystem.restype = wintypes.UINT
    user32.MessageBoxW.argtypes = [
        wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT,
    ]
    user32.MessageBoxW.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND

    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    if shcore is not None:
        shcore.GetProcessDpiAwareness.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
        ]
        shcore.GetProcessDpiAwareness.restype = ctypes.c_long
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long

    if shell32 is not None:
        shell32.IsUserAnAdmin.argtypes = []
        shell32.IsUserAnAdmin.restype = wintypes.BOOL


def message_box(text: str, title: str = APP_TITLE, error: bool = True) -> None:
    """不依赖 Tk 的消息框，用于 Tk 创建之前/之后兜底。"""
    if IS_WINDOWS and user32 is not None:
        flags = 0x10 if error else 0x40
        try:
            user32.MessageBoxW(None, text, title, flags)
            return
        except Exception:
            pass
    try:
        print(f"{title}: {text}", file=sys.stderr)
    except Exception:
        pass


def get_dpi_awareness() -> int:
    """0=unaware, 1=system, 2=per-monitor; -1=未知。"""
    if shcore is None:
        return -1
    value = ctypes.c_int()
    try:
        if shcore.GetProcessDpiAwareness(None, ctypes.byref(value)) == 0:
            return value.value
    except Exception:
        pass
    return -1


def enable_dpi_awareness() -> int:
    """在创建任何 Tk 窗口之前声明 Per-Monitor V2。"""
    if not IS_WINDOWS:
        return -1

    current = get_dpi_awareness()
    if current in (1, 2):
        return current

    # Windows 10 1703+：Per-Monitor V2
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return get_dpi_awareness()
    except Exception:
        pass

    # Windows 8.1+：Per-Monitor V1
    if shcore is not None:
        try:
            if shcore.SetProcessDpiAwareness(2) == 0:
                return get_dpi_awareness()
        except Exception:
            pass

    # 最后兜底：System Aware
    try:
        if user32.SetProcessDPIAware():
            value = get_dpi_awareness()
            return 1 if value == -1 else value
    except Exception:
        pass

    return get_dpi_awareness()


def get_system_dpi() -> int:
    if not IS_WINDOWS or user32 is None:
        return 96
    try:
        return int(user32.GetDpiForSystem())
    except Exception:
        return 96


def acquire_single_instance():
    """返回句柄；None 表示已有实例；0 表示无法创建（不阻止运行）。"""
    if not IS_WINDOWS or kernel32 is None:
        return 0
    try:
        handle = kernel32.CreateMutexW(
            None, False, "Local\\FixRegionTool_SingleInstance",
        )
        if not handle:
            return 0
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return None
        return handle
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# 显示器与窗口几何
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Monitor:
    index: int
    left: int
    top: int
    width: int
    height: int
    name: str = ""
    is_primary: bool = False

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def as_dict(self) -> dict:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    def label(self) -> str:
        text = f"[{self.index}] {self.width}×{self.height} @ ({self.left},{self.top})"
        if self.is_primary:
            text += "  主屏"
        return text


def enumerate_monitors() -> list[Monitor]:
    """用 mss 枚举物理显示器；[0] 是所有屏的并集，跳过。"""
    with mss.MSS() as sct:
        raw = list(sct.monitors[1:])
    if not raw:
        raise RuntimeError("没有检测到显示器。")

    result: list[Monitor] = []
    for i, item in enumerate(raw, start=1):
        left = int(item["left"])
        top = int(item["top"])
        width = int(item["width"])
        height = int(item["height"])
        result.append(Monitor(
            index=i,
            left=left,
            top=top,
            width=width,
            height=height,
            name=str(item.get("name", "")),
            is_primary=bool(item.get(
                "is_primary", left == 0 and top == 0,
            )),
        ))
    return result


def monitor_from_hwnd(hwnd, monitors: list[Monitor]) -> Monitor | None:
    """返回窗口所在显示器；找不到时用 Win32 的矩形构造一个。"""
    if not hwnd:
        return None
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
        return None

    rect = info.rcMonitor
    geometry = (
        int(rect.left),
        int(rect.top),
        int(rect.right) - int(rect.left),
        int(rect.bottom) - int(rect.top),
    )
    for monitor in monitors:
        if (monitor.left, monitor.top, monitor.width, monitor.height) == geometry:
            return monitor

    return Monitor(
        index=0,
        left=geometry[0],
        top=geometry[1],
        width=geometry[2],
        height=geometry[3],
        is_primary=bool(info.dwFlags & 1),
    )


def is_own_window(hwnd, root: tk.Tk) -> bool:
    """前台窗口是不是本工具自己（含子窗口）。"""
    if not hwnd:
        return True
    try:
        own = int(root.wm_frame(), 16)
    except Exception:
        return False
    if hwnd == own:
        return True
    try:
        return user32.GetAncestor(hwnd, GA_ROOT) == own
    except Exception:
        return False


def place_window(hwnd: int, monitor: Monitor) -> None:
    """把窗口精确放到显示器的物理像素矩形上。"""
    ok = user32.SetWindowPos(
        hwnd,
        HWND_TOPMOST,
        monitor.left,
        monitor.top,
        monitor.width,
        monitor.height,
        SWP_SHOWWINDOW | SWP_NOACTIVATE,
    )
    if not ok:
        raise OSError(
            f"SetWindowPos 失败（错误码 {ctypes.get_last_error()}）",
        )


def client_metrics(hwnd: int) -> tuple[tuple[int, int], tuple[int, int]]:
    """返回 (客户区宽高, 客户区左上角的屏幕坐标)。"""
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetClientRect 失败")
    point = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise OSError("ClientToScreen 失败")
    return (
        (int(rect.right) - int(rect.left), int(rect.bottom) - int(rect.top)),
        (int(point.x), int(point.y)),
    )


# ---------------------------------------------------------------------------
# 配置：读取、逐行替换、原子写入
# ---------------------------------------------------------------------------

class ConfigError(Exception):
    pass


MODE_INFO = {
    "1": ("relic", "遗物"),
    "2": ("dmark", "暗痕"),
    "3": ("start", "请按任一按钮"),
}

PREFIX_FIELDS = {
    "relic": ("relic_x", "relic_y", "relic_width", "relic_height"),
    "dmark": ("dmark_x", "dmark_y", "dmark_width", "dmark_height"),
    "start": ("start_x", "start_y", "start_width", "start_height"),
}

ALL_FIELDS = {
    field for fields in PREFIX_FIELDS.values() for field in fields
}

REGION_FIELD = {
    "x": "left",
    "y": "top",
    "width": "width",
    "height": "height",
}

MSS_HEADER_RE = re.compile(
    r"^(?P<indent>[ \t]*)mss_config[ \t]*:[ \t]*(?:#.*)?(?P<eol>\r?\n?)\Z",
)


def key_line_re(field: str) -> re.Pattern:
    return re.compile(
        r"^(?P<indent>[ \t]*)(?P<key>" + re.escape(field) + r")"
        r"(?P<sep>[ \t]*:[ \t]*)"
        r"(?P<quote>[\"']?)(?P<value>[-+]?\d+)(?P=quote)"
        r"(?P<rest>[ \t]*(?:#.*)?)(?P<eol>\r?\n?)\Z",
    )


def load_config(path: str = CONFIG_PATH) -> tuple[dict, str, bytes]:
    """读取并校验配置，返回 (解析后的 dict, 文本, 原始 bytes)。"""
    if not os.path.isfile(path):
        raise ConfigError(
            f"找不到配置文件：\n{path}\n\n"
            "请把 config.yaml 放在 fix_tool.exe 同一目录。",
        )
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError as exc:
        raise ConfigError(f"读取配置失败：\n{exc}") from exc

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ConfigError(
            "config.yaml 不是 UTF-8 编码，请用 UTF-8 保存后再试。",
        ) from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML 解析失败：\n{exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError("config.yaml 的顶层必须是键值映射。")

    mss_cfg = data.get("mss_config")
    if not isinstance(mss_cfg, dict):
        raise ConfigError("config.yaml 缺少 mss_config 段。")

    for prefix, fields in PREFIX_FIELDS.items():
        for field in fields:
            if field not in mss_cfg:
                raise ConfigError(f"mss_config 缺少 {field}。")
            value = mss_cfg[field]
            if isinstance(value, bool) or not isinstance(value, int):
                raise ConfigError(f"mss_config.{field} 必须是整数，当前是 {value!r}。")
            if field.endswith("_width") or field.endswith("_height"):
                if value <= 0:
                    raise ConfigError(f"mss_config.{field} 必须大于 0，当前是 {value}。")

    return data, text, raw


def get_region(data: dict, mode: str) -> dict:
    prefix = MODE_INFO[mode][0]
    mss_cfg = data["mss_config"]
    return {
        "left": int(mss_cfg[f"{prefix}_x"]),
        "top": int(mss_cfg[f"{prefix}_y"]),
        "width": int(mss_cfg[f"{prefix}_width"]),
        "height": int(mss_cfg[f"{prefix}_height"]),
    }


def validate_region(region: dict) -> None:
    for name in ("left", "top", "width", "height"):
        value = region.get(name)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"区域 {name} 必须是整数。")
    if region["width"] < MIN_REGION or region["height"] < MIN_REGION:
        raise ConfigError(
            f"选区太小（{region['width']}×{region['height']}），"
            f"至少需要 {MIN_REGION}×{MIN_REGION}。",
        )


def region_outside(monitors: list[Monitor], region: dict) -> bool:
    """区域是否完全落在某一块显示器内。"""
    for monitor in monitors:
        if (
            monitor.left <= region["left"]
            and region["left"] + region["width"] <= monitor.right
            and monitor.top <= region["top"]
            and region["top"] + region["height"] <= monitor.bottom
        ):
            return False
    return True


def _validate_new_config(
    old_data: dict, new_data: dict, mode: str, region: dict,
) -> None:
    """替换后重新解析，确认只改了目标区域的 4 个值。"""
    if not isinstance(new_data, dict):
        raise ConfigError("替换后解析结果不再是映射，已中止。")
    if set(old_data) != set(new_data):
        raise ConfigError("替换后顶层 section 发生变化，已中止。")

    for key in old_data:
        if key != "mss_config" and old_data[key] != new_data[key]:
            raise ConfigError(f"替换后 {key} 段发生变化，已中止。")

    old_mss = old_data["mss_config"]
    new_mss = new_data.get("mss_config")
    if not isinstance(new_mss, dict) or set(old_mss) != set(new_mss):
        raise ConfigError("替换后 mss_config 的键发生变化，已中止。")

    expected = {name: get_region(old_data, name) for name in MODE_INFO}
    expected[mode] = {
        "left": int(region["left"]),
        "top": int(region["top"]),
        "width": int(region["width"]),
        "height": int(region["height"]),
    }

    for name, (prefix, _) in MODE_INFO.items():
        for field in PREFIX_FIELDS[prefix]:
            suffix = field.rsplit("_", 1)[1]
            want = expected[name][REGION_FIELD[suffix]]
            got = new_mss[field]
            if isinstance(got, bool) or not isinstance(got, int) or got != want:
                raise ConfigError(
                    f"替换后 mss_config.{field} = {got!r}，预期 {want}，已中止。",
                )

    for key, value in old_mss.items():
        if key not in ALL_FIELDS and new_mss[key] != value:
            raise ConfigError(f"替换后 mss_config.{key} 发生变化，已中止。")


def build_updated_text(
    text: str, data: dict, mode: str, region: dict,
) -> tuple[str, dict]:
    """逐行替换目标区域的 4 个数字，保留注释/缩进/空行/换行符。"""
    if mode not in MODE_INFO:
        raise ConfigError(f"未知模式：{mode}")
    validate_region(region)

    prefix = MODE_INFO[mode][0]
    fields = PREFIX_FIELDS[prefix]
    lines = text.splitlines(keepends=True)

    headers = []
    for index, line in enumerate(lines):
        match = MSS_HEADER_RE.fullmatch(line)
        if match:
            headers.append((index, match))
    if len(headers) != 1:
        raise ConfigError(
            f"config.yaml 中 mss_config 顶层键出现 {len(headers)} 次，无法安全替换。",
        )
    header_index, header_match = headers[0]
    if header_match.group("indent"):
        raise ConfigError("mss_config 必须是顶层键。")

    # 找到 mss_config 块的结束位置：下一个顶格的非注释行
    block_end = header_index + 1
    while block_end < len(lines):
        line = lines[block_end]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            block_end += 1
            continue
        indent = len(line) - len(line.lstrip(" \t"))
        if indent == 0:
            break
        block_end += 1

    for field in fields:
        pattern = key_line_re(field)
        matches = []
        for index in range(header_index + 1, block_end):
            match = pattern.fullmatch(lines[index])
            if match:
                matches.append((index, match))

        if len(matches) != 1:
            raise ConfigError(
                f"mss_config 中 {field} 出现 {len(matches)} 次，无法安全替换。",
            )

        index, match = matches[0]
        suffix = field.rsplit("_", 1)[1]
        value = region[REGION_FIELD[suffix]]
        lines[index] = (
            match.group("indent")
            + match.group("key")
            + match.group("sep")
            + match.group("quote")
            + str(int(value))
            + match.group("quote")
            + match.group("rest")
            + match.group("eol")
        )

    new_text = "".join(lines)
    try:
        new_data = yaml.safe_load(new_text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"替换后 YAML 解析失败：\n{exc}") from exc

    _validate_new_config(data, new_data, mode, region)
    return new_text, new_data


def write_config_atomic(path: str, raw: bytes, new_text: str) -> None:
    """先备份原文件，再写临时文件并原子替换。"""
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    payload = (b"\xef\xbb\xbf" if has_bom else b"") + new_text.encode("utf-8")
    backup_path = path + ".bak"
    temp_path = path + ".tmp"

    try:
        with open(backup_path, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as exc:
        raise ConfigError(f"备份配置失败：\n{exc}") from exc

    try:
        with open(temp_path, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except OSError as exc:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass
        raise ConfigError(f"写入配置失败：\n{exc}") from exc


def save_region_to_config(path: str, mode: str, region: dict) -> dict:
    data, text, raw = load_config(path)
    new_text, new_data = build_updated_text(text, data, mode, region)
    write_config_atomic(path, raw, new_text)
    return new_data


def check_writable(path: str) -> bool:
    try:
        with tempfile.NamedTemporaryFile(
            dir=path, prefix=".fix_tool_", delete=True,
        ):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# 全屏框选层
# ---------------------------------------------------------------------------

class ScreenSelector:
    """在目标显示器上铺一层冻结截图，返回绝对坐标选区。"""

    def __init__(
        self,
        parent: tk.Tk,
        monitor: Monitor,
        bg_img: Image.Image,
        mode_label: str,
    ):
        self.parent = parent
        self.monitor = monitor
        self.bg_img = bg_img
        self.mode_label = mode_label

        self.top: tk.Toplevel | None = None
        self.canvas: tk.Canvas | None = None
        self.rect = None
        self.start_x: int | None = None
        self.start_y: int | None = None
        self.pending: tuple[int, int, int, int] | None = None
        self.result: dict | None = None
        self.error: str | None = None
        self.closed = False
        self.origin = (monitor.left, monitor.top)

        self._old_report = getattr(parent, "report_callback_exception", None)
        try:
            parent.report_callback_exception = self._on_tk_error
        except Exception:
            pass

        try:
            self._build()
        except Exception:
            self.error = traceback.format_exc()
            self._close()

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def _build(self) -> None:
        monitor = self.monitor
        self.top = tk.Toplevel(self.parent)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

        # 目标屏可能比主屏大，先放宽 Tk 的最大尺寸限制
        self.top.maxsize(monitor.width, monitor.height)
        self.top.geometry(
            f"{monitor.width}x{monitor.height}+0+0",
        )

        self.canvas = tk.Canvas(
            self.top,
            width=monitor.width,
            height=monitor.height,
            highlightthickness=0,
            bd=0,
            cursor="cross",
            bg="black",
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.bg_photo = ImageTk.PhotoImage(self.bg_img)
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor=tk.NW)

        width, height = monitor.width, monitor.height
        self.mask_top = self.canvas.create_rectangle(
            0, 0, width, height,
            fill="white", stipple="gray50", outline="",
        )
        self.mask_bottom = self.canvas.create_rectangle(
            0, 0, 0, 0,
            fill="white", stipple="gray50", outline="",
        )
        self.mask_left = self.canvas.create_rectangle(
            0, 0, 0, 0,
            fill="white", stipple="gray50", outline="",
        )
        self.mask_right = self.canvas.create_rectangle(
            0, 0, 0, 0,
            fill="white", stipple="gray50", outline="",
        )

        self.top.update_idletasks()
        self.hwnd = int(self.top.wm_frame(), 16)
        place_window(self.hwnd, monitor)
        self.top.update()

        try:
            self.top.attributes("-alpha", 1.0)
        except tk.TclError:
            pass
        self.top.lift()
        try:
            self.top.focus_force()
        except tk.TclError:
            pass
        self.canvas.focus_set()
        try:
            self.top.grab_set()
        except tk.TclError:
            pass

        try:
            self._verify_geometry()
        except RuntimeError:
            # 跨不同 DPI 的显示器时，Tk 处理 WM_DPICHANGED 后可能把窗口
            # 改回它建议的尺寸；这里再精确放置一次并重新校验。
            place_window(self.hwnd, self.monitor)
            self.top.update_idletasks()
            self.top.update()
            self._verify_geometry()

        self._bind()
        self._show_hint(
            f"拖拽框选【{self.mode_label}】    Esc/右键取消",
        )

    def _verify_geometry(self) -> None:
        monitor = self.monitor
        (client_width, client_height), (origin_x, origin_y) = client_metrics(
            self.hwnd,
        )
        if (client_width, client_height) != (monitor.width, monitor.height):
            raise RuntimeError(
                f"覆盖层尺寸异常：{client_width}×{client_height}，"
                f"显示器是 {monitor.width}×{monitor.height}。\n"
                "这通常是 DPI 缩放或显示器布局变化导致的，已停止，未写配置。",
            )
        if (origin_x, origin_y) != (monitor.left, monitor.top):
            raise RuntimeError(
                f"覆盖层位置异常：({origin_x},{origin_y})，"
                f"显示器是 ({monitor.left},{monitor.top})。\n"
                "已停止，未写配置。",
            )
        if self.bg_img.size != (monitor.width, monitor.height):
            raise RuntimeError(
                f"截图尺寸异常：{self.bg_img.size}，"
                f"显示器是 ({monitor.width},{monitor.height})。\n"
                "已停止，未写配置。",
            )
        self.origin = (origin_x, origin_y)

    def _bind(self) -> None:
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._cancel)
        self.top.bind("<Escape>", self._cancel)
        self.top.bind("<Alt-F4>", self._cancel)
        self.top.bind("<Return>", self._confirm)
        self.top.bind("<KP_Enter>", self._confirm)
        self.top.bind("<r>", self._reselect)
        self.top.bind("<R>", self._reselect)
        self.top.protocol("WM_DELETE_WINDOW", self._cancel)

    # ------------------------------------------------------------------
    # 绘制
    # ------------------------------------------------------------------

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(self.monitor.width, int(x))),
            max(0, min(self.monitor.height, int(y))),
        )

    def _normalize(
        self, ax: int, ay: int, bx: int, by: int,
    ) -> tuple[int, int, int, int]:
        ax, ay = self._clamp(ax, ay)
        bx, by = self._clamp(bx, by)
        return min(ax, bx), min(ay, by), max(ax, bx), max(ay, by)

    def _update_masks(self, x1: int, y1: int, x2: int, y2: int) -> None:
        width, height = self.monitor.width, self.monitor.height
        self.canvas.coords(self.mask_top, 0, 0, width, y1)
        self.canvas.coords(self.mask_bottom, 0, y2, width, height)
        self.canvas.coords(self.mask_left, 0, y1, x1, y2)
        self.canvas.coords(self.mask_right, x2, y1, width, y2)

    def _show_hint(self, text: str) -> None:
        self.canvas.delete("hint")
        self.canvas.create_text(
            13, 11, text=text, anchor=tk.NW, fill="black",
            font=("Microsoft YaHei UI", -16), tags="hint",
        )
        self.canvas.create_text(
            12, 10, text=text, anchor=tk.NW, fill="#ffff66",
            font=("Microsoft YaHei UI", -16), tags="hint",
        )

    def _show_info(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.canvas.delete("info")
        absolute_x = self.origin[0] + x1
        absolute_y = self.origin[1] + y1
        text = f"{x2 - x1} × {y2 - y1}    @ ({absolute_x}, {absolute_y})"
        self.canvas.create_text(
            13, 39, text=text, anchor=tk.NW, fill="black",
            font=("Consolas", -16), tags="info",
        )
        self.canvas.create_text(
            12, 38, text=text, anchor=tk.NW, fill="#ffff66",
            font=("Consolas", -16), tags="info",
        )

    def _reset_selection(self) -> None:
        if self.rect is not None:
            self.canvas.delete(self.rect)
            self.rect = None
        self.start_x = None
        self.start_y = None
        self.pending = None
        width, height = self.monitor.width, self.monitor.height
        self.canvas.coords(self.mask_top, 0, 0, width, height)
        self.canvas.coords(self.mask_bottom, 0, 0, 0, 0)
        self.canvas.coords(self.mask_left, 0, 0, 0, 0)
        self.canvas.coords(self.mask_right, 0, 0, 0, 0)
        self.canvas.delete("info")

    # ------------------------------------------------------------------
    # 鼠标/键盘
    # ------------------------------------------------------------------

    def _on_press(self, event) -> None:
        if self.closed:
            return
        self.pending = None
        self.canvas.delete("info")
        self.start_x, self.start_y = self._clamp(event.x, event.y)
        self._update_masks(
            self.start_x, self.start_y, self.start_x, self.start_y,
        )
        if self.rect is not None:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline="#00ff66", width=2, dash=(6, 3),
        )
        self._show_hint(
            f"拖拽框选【{self.mode_label}】    Esc/右键取消",
        )
        try:
            self.top.focus_force()
        except tk.TclError:
            pass

    def _on_drag(self, event) -> None:
        if self.closed or self.start_x is None or self.start_y is None:
            return
        x1, y1, x2, y2 = self._normalize(
            self.start_x, self.start_y, event.x, event.y,
        )
        self._update_masks(x1, y1, x2, y2)
        if self.rect is not None:
            self.canvas.coords(self.rect, x1, y1, x2, y2)
        self._show_info(x1, y1, x2, y2)

    def _on_release(self, event) -> None:
        if self.closed or self.start_x is None or self.start_y is None:
            return
        x1, y1, x2, y2 = self._normalize(
            self.start_x, self.start_y, event.x, event.y,
        )
        self.start_x = None
        self.start_y = None

        width, height = x2 - x1, y2 - y1
        if width < MIN_REGION or height < MIN_REGION:
            self._show_hint(
                f"选区太小（{width}×{height}），请重新拖拽；Esc/右键取消",
            )
            self._reset_selection()
            return

        self.pending = (x1, y1, x2, y2)
        if self.rect is not None:
            self.canvas.coords(self.rect, x1, y1, x2, y2)
        self._show_hint("Enter 确认    R 重选    Esc/右键取消")
        self._show_info(x1, y1, x2, y2)

    def _reselect(self, event=None) -> None:
        if self.closed:
            return
        self._reset_selection()
        self._show_hint(
            f"拖拽框选【{self.mode_label}】    Esc/右键取消",
        )

    def _confirm(self, event=None) -> None:
        if self.closed or self.pending is None:
            return
        x1, y1, x2, y2 = self.pending
        try:
            crop = self.bg_img.crop((x1, y1, x2, y2))
            crop.save(PNG_PATH, "PNG")
        except Exception:
            self.error = traceback.format_exc()
            self._close()
            return

        self.result = {
            "left": self.origin[0] + x1,
            "top": self.origin[1] + y1,
            "width": x2 - x1,
            "height": y2 - y1,
        }
        self._close()

    def _cancel(self, event=None) -> None:
        if self.closed:
            return
        self.result = None
        self._close()

    def _on_tk_error(self, exc, value, tb) -> None:
        self.error = "".join(traceback.format_exception(exc, value, tb))
        self._close()

    def _close(self) -> None:
        if self.closed:
            return
        self.closed = True

        if self.parent is not None and self._old_report is not None:
            try:
                self.parent.report_callback_exception = self._old_report
            except Exception:
                pass

        if self.top is not None:
            try:
                if self.top.winfo_exists():
                    try:
                        self.top.grab_release()
                    except tk.TclError:
                        pass
                    self.top.destroy()
            except tk.TclError:
                pass


# ---------------------------------------------------------------------------
# 主窗口
# ---------------------------------------------------------------------------

class App:
    def __init__(self, data: dict, monitors: list[Monitor]):
        self.data = data
        self.monitors = monitors
        self.regions = {mode: get_region(data, mode) for mode in MODE_INFO}
        self.monitor_map = {monitor.label(): monitor for monitor in monitors}

        self.busy = False
        self.closing = False
        self.after_id = None
        self.countdown_left = 0
        self.selector: ScreenSelector | None = None

        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._on_tk_error

        self._setup_fonts()
        self._build_ui()
        self._refresh_labels()
        self.status_var.set(self._warning_text() or "就绪")
        self._center_window()
        self.root.lift()
        try:
            self.root.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 界面
    # ------------------------------------------------------------------

    def _setup_fonts(self) -> None:
        try:
            for name in (
                "TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
            ):
                try:
                    tkfont.nametofont(name).configure(
                        family="Microsoft YaHei UI", size=10,
                    )
                except tk.TclError:
                    pass
        except Exception:
            pass

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)

        main = ttk.Frame(self.root, padding=12)
        main.grid(row=0, column=0, sticky="nsew")
        main.columnconfigure(1, weight=1)

        ttk.Label(
            main,
            text=f"配置：{CONFIG_PATH}",
            wraplength=640,
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Label(main, text="显示器：").grid(
            row=1, column=0, sticky="w",
        )
        self.monitor_var = tk.StringVar(
            master=self.root, value=AUTO_MONITOR,
        )
        self.monitor_combo = ttk.Combobox(
            main,
            textvariable=self.monitor_var,
            state="readonly",
            width=46,
            values=[AUTO_MONITOR] + list(self.monitor_map),
        )
        self.monitor_combo.grid(
            row=1, column=1, columnspan=2, sticky="we", pady=(0, 8),
        )

        ttk.Label(
            main,
            text="提示：请将游戏设为无边框窗口化；修改后需重启自动化程序。",
            wraplength=640,
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 8))

        ttk.Separator(main, orient="horizontal").grid(
            row=3, column=0, columnspan=3, sticky="we", pady=(0, 8),
        )

        self.coord_labels: dict[str, ttk.Label] = {}
        self.edit_buttons: dict[str, ttk.Button] = {}

        for row, (mode, (_, name)) in enumerate(MODE_INFO.items(), start=4):
            ttk.Label(main, text=name, width=14, anchor="w").grid(
                row=row, column=0, sticky="w", pady=4,
            )
            coord = ttk.Label(
                main, text="", width=30, anchor="w",
                font=("Consolas", 10),
            )
            coord.grid(row=row, column=1, sticky="w", pady=4)
            button = ttk.Button(
                main, text="修改", width=8,
                command=lambda m=mode: self._on_modify(m),
            )
            button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=4)
            self.coord_labels[mode] = coord
            self.edit_buttons[mode] = button

        self.status_var = tk.StringVar(master=self.root, value="就绪")
        self.status_label = ttk.Label(
            main,
            textvariable=self.status_var,
            wraplength=640,
            justify="left",
            anchor="w",
        )
        self.status_label.grid(
            row=8, column=0, columnspan=3, sticky="we", pady=(12, 8),
        )

        bottom = ttk.Frame(main)
        bottom.grid(row=9, column=0, columnspan=3, sticky="e")
        ttk.Button(
            bottom, text="环境信息", command=self._show_env_info,
        ).pack(side="left", padx=(0, 8))
        self.exit_button = ttk.Button(
            bottom, text="退出", command=self._on_close,
        )
        self.exit_button.pack(side="left")

    def _refresh_labels(self) -> None:
        for mode, (_, _name) in MODE_INFO.items():
            region = self.regions[mode]
            text = (
                f"{region['left']}, {region['top']}    "
                f"{region['width']} × {region['height']}"
            )
            self.coord_labels[mode].configure(text=text)

    def _warning_text(self) -> str:
        bad = [
            name
            for mode, (_, name) in MODE_INFO.items()
            if region_outside(self.monitors, self.regions[mode])
        ]
        if bad:
            return (
                "注意：" + "、".join(bad)
                + " 区域超出当前显示器范围，请重新标定。"
            )
        return ""

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for button in self.edit_buttons.values():
            button.configure(state=state)
        self.monitor_combo.configure(
            state="readonly" if enabled else "disabled",
        )

    def _center_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        self.root.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    # 修改流程
    # ------------------------------------------------------------------

    def _on_modify(self, mode: str) -> None:
        if self.busy or self.closing:
            return
        self.busy = True
        self._set_controls_enabled(False)
        self.countdown_left = COUNTDOWN_SECONDS
        self._tick(mode)

    def _tick(self, mode: str) -> None:
        if self.closing:
            return
        if self.countdown_left > 0:
            self.status_var.set(
                f"{self.countdown_left} 秒后开始，请切换到游戏...",
            )
            self.countdown_left -= 1
            self.after_id = self.root.after(
                1000, lambda: self._tick(mode),
            )
        else:
            self.after_id = None
            self._begin_selection(mode)

    def _target_monitor(self) -> Monitor | None:
        choice = self.monitor_var.get()
        if choice != AUTO_MONITOR:
            return self.monitor_map.get(choice)

        hwnd = user32.GetForegroundWindow()
        if is_own_window(hwnd, self.root):
            return None
        return monitor_from_hwnd(hwnd, self.monitors)

    def _begin_selection(self, mode: str) -> None:
        monitor = self._target_monitor()
        if monitor is None:
            self._reset_busy(
                "未检测到游戏窗口在前台，请切换到游戏后重试。",
            )
            messagebox.showwarning(
                APP_TITLE,
                "倒计时结束时前台不是游戏窗口。\n"
                "请先切换到游戏，再点“修改”。",
                parent=self.root,
            )
            return

        self.status_var.set(
            f"目标显示器：{monitor.label()}，正在抓取画面...",
        )
        self.root.update_idletasks()

        selector = None
        error = None

        self.root.withdraw()
        self.root.update()
        try:
            time.sleep(0.15)
            self.root.update()
            with mss.MSS() as sct:
                shot = sct.grab(monitor.as_dict())
            bg_img = Image.frombytes("RGB", shot.size, shot.rgb)
            if bg_img.size != (monitor.width, monitor.height):
                raise RuntimeError(
                    f"抓取尺寸异常：{bg_img.size}，"
                    f"显示器是 ({monitor.width},{monitor.height})。",
                )

            selector = ScreenSelector(
                self.root, monitor, bg_img, MODE_INFO[mode][1],
            )
            if selector.error:
                raise RuntimeError(selector.error)
            if selector.top is None or not selector.top.winfo_exists():
                raise RuntimeError("覆盖层已经关闭。")

            self.selector = selector
            self.root.wait_window(selector.top)
        except Exception as exc:
            error = str(exc)
            if selector is not None:
                try:
                    selector._close()
                except Exception:
                    pass
        finally:
            self.selector = None
            try:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
            except tk.TclError:
                pass

        if self.closing:
            return

        if error is not None:
            self._show_error("框选失败", error)
            self._reset_busy("框选失败，配置未修改。")
            return

        if selector is None or selector.result is None:
            if selector is not None and selector.error:
                self._show_error("框选失败", selector.error)
                self._reset_busy("框选失败，配置未修改。")
            else:
                self._reset_busy("已取消，配置未修改。")
            return

        try:
            new_data = save_region_to_config(
                CONFIG_PATH, mode, selector.result,
            )
        except Exception as exc:
            self._show_error("保存失败", f"{exc}\n\n配置未修改。")
            self._reset_busy("保存失败，配置未修改。")
            return

        self.data = new_data
        self.regions = {
            name: get_region(new_data, name) for name in MODE_INFO
        }
        self._refresh_labels()
        self._set_controls_enabled(True)
        self.busy = False

        warning = self._warning_text()
        status = "已保存。请重新启动自动化程序使配置生效。"
        if warning:
            status += "  " + warning
        self.status_var.set(status)
        messagebox.showinfo(
            APP_TITLE,
            "配置已保存。\n请重新启动自动化程序使配置生效。",
            parent=self.root,
        )

    def _reset_busy(self, status: str) -> None:
        self.busy = False
        self.selector = None
        try:
            if self.root.winfo_exists():
                self._set_controls_enabled(True)
                if not self.closing:
                    self.status_var.set(status)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # 其他回调
    # ------------------------------------------------------------------

    def _show_error(self, title: str, text: str) -> None:
        try:
            messagebox.showerror(f"{APP_TITLE} - {title}", text, parent=self.root)
        except Exception:
            message_box(text, title)

    def _show_env_info(self) -> None:
        try:
            tk_dpi = self.root.winfo_fpixels("1i")
        except Exception:
            tk_dpi = "?"
        is_admin = "?"
        if shell32 is not None:
            try:
                is_admin = "是" if shell32.IsUserAnAdmin() else "否"
            except Exception:
                is_admin = "?"
        lines = [
            f"配置：{CONFIG_PATH}",
            f"DPI awareness：{get_dpi_awareness()}",
            f"System DPI：{get_system_dpi()}",
            f"Tk screen：{self.root.winfo_screenwidth()}×{self.root.winfo_screenheight()}",
            f"Tk DPI：{tk_dpi}",
            f"管理员：{is_admin}",
            "",
            "显示器：",
        ]
        lines.extend(monitor.label() for monitor in self.monitors)
        messagebox.showinfo(
            f"{APP_TITLE} - 环境信息",
            "\n".join(lines),
            parent=self.root,
        )

    def _on_tk_error(self, exc, value, tb) -> None:
        text = "".join(traceback.format_exception(exc, value, tb))
        try:
            messagebox.showerror(APP_TITLE, text, parent=self.root)
        except Exception:
            message_box(text)

    def _on_close(self) -> None:
        self.closing = True
        if self.after_id is not None:
            try:
                self.root.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        try:
            self.root.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

_MUTEX_HANDLE = 0


def main() -> int:
    global _MUTEX_HANDLE

    if not IS_WINDOWS:
        message_box("fix_tool 仅支持 Windows。")
        return 1

    mutex = acquire_single_instance()
    if mutex is None:
        message_box("fix_tool 已经在运行。")
        return 0
    _MUTEX_HANDLE = mutex

    awareness = enable_dpi_awareness()
    if awareness < 1:
        message_box(
            "无法启用 DPI 感知。\n\n"
            "为避免写入错误坐标，程序已停止。\n"
            "请确认系统为 Windows 10/11，并关闭兼容性设置中的"
            "“替代高 DPI 缩放行为”。",
        )
        return 1

    if not check_writable(BASE_PATH):
        message_box(
            f"fix_tool 所在目录不可写：\n{BASE_PATH}\n\n"
            "请把 fix_tool.exe 和 config.yaml 放到可写的文件夹。",
        )
        return 1

    try:
        monitors = enumerate_monitors()
    except Exception as exc:
        message_box(f"枚举显示器失败：\n{exc}")
        return 1

    try:
        data, _text, _raw = load_config(CONFIG_PATH)
    except Exception as exc:
        message_box(str(exc))
        return 1

    try:
        app = App(data, monitors)
    except Exception as exc:
        message_box(f"启动失败：\n{exc}\n\n{traceback.format_exc()}")
        return 1

    try:
        app.root.mainloop()
    except Exception as exc:
        message_box(f"运行失败：\n{exc}\n\n{traceback.format_exc()}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
