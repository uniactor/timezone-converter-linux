#!/usr/bin/python3
"""Desktop time-zone widget for Ubuntu.

Berlin and Shanghai are loaded by default. Other cities can be added or
removed, and the widget itself can be pinned to the desktop or taken off it.
"""

import os
import sys

if sys.executable != "/usr/bin/python3":
    try:
        import gi  # noqa: F401
    except ModuleNotFoundError:
        if os.path.exists("/usr/bin/python3"):
            os.execv("/usr/bin/python3", ["/usr/bin/python3", *sys.argv])

import ctypes
import json
import traceback
import uuid
from ctypes import (
    POINTER,
    Structure,
    Union,
    byref,
    c_char_p,
    c_int,
    c_long,
    c_uint,
    c_ulong,
    c_void_p,
    sizeof,
)
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango

try:
    gi.require_version("GdkX11", "4.0")
    from gi.repository import GdkX11
except (ValueError, ImportError):
    GdkX11 = None

from cities import MAX_CITIES, search_places
from clockfmt import ahead_text, day_note, fmt_date, fmt_gmt, fmt_rel, local_at, mechanism_name, season_label

APP_ID = "com.toolkit.TimezoneDesk"
ASSET_DIR = Path(__file__).resolve().parent
SCRIPT_PATH = Path(__file__).absolute()
CSS_PATH = ASSET_DIR / "style.css"
ICON_PATH = ASSET_DIR / "icon.svg"
CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "timezone-desk"
CONFIG_PATH = CONFIG_DIR / "config.json"
AUTOSTART_PATH = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "timezone-desk.desktop"

DEFAULT_CITIES = [
    {"id": "berlin", "label": "柏林", "tz": "Europe/Berlin"},
    {"id": "shanghai", "label": "上海", "tz": "Asia/Shanghai"},
]


def _excepthook(exc_type, exc, tb):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with (CONFIG_DIR / "error.log").open("a", encoding="utf-8") as handle:
            traceback.print_exception(exc_type, exc, tb, file=handle)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc, tb)


sys.excepthook = _excepthook


def _quote(path: Path) -> str:
    text = str(path)
    if any(char in text for char in " \t\"'"):
        return "'" + text.replace("'", "'\\''") + "'"
    return text


def desktop_entry(script: Path, icon: Path, autostart: bool) -> str:
    extra = "X-GNOME-Autostart-enabled=true\nX-GNOME-Autostart-Delay=2\n" if autostart else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        "Name=时区\n"
        "GenericName=时区转换\n"
        "Comment=在桌面上转换柏林、上海和其他城市的时间\n"
        f"Exec=/usr/bin/python3 {_quote(script)}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;Clock;\n"
        "Keywords=时区;timezone;clock;柏林;上海;\n"
        "StartupNotify=false\n"
        f"StartupWMClass={APP_ID}\n"
        f"{extra}"
    )


def autostart_enabled() -> bool:
    if not AUTOSTART_PATH.exists():
        return False
    text = AUTOSTART_PATH.read_text(encoding="utf-8", errors="ignore")
    return "X-GNOME-Autostart-enabled=false" not in text


def enable_autostart() -> None:
    AUTOSTART_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUTOSTART_PATH.write_text(desktop_entry(SCRIPT_PATH, ICON_PATH, True), encoding="utf-8")


def remove_autostart() -> None:
    AUTOSTART_PATH.unlink(missing_ok=True)


def _valid_zone(name: str) -> bool:
    try:
        ZoneInfo(name)
    except Exception:
        return False
    return True


def load_config() -> dict:
    config = {
        "stack": "above",
        "x": None,
        "y": None,
        "live": True,
        "moment": None,
        "cities": [dict(city) for city in DEFAULT_CITIES],
    }
    try:
        stored = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return config
    if not isinstance(stored, dict):
        return config
    stack = stored.get("stack")
    if stack in {"below", "above"}:
        config["stack"] = stack
    for key in ("x", "y"):
        value = stored.get(key)
        if isinstance(value, (int, float)):
            config[key] = int(value)
    config["live"] = bool(stored.get("live", True))
    moment = stored.get("moment")
    if isinstance(moment, str):
        try:
            parsed = datetime.fromisoformat(moment)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            config["moment"] = parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            pass
    cities = []
    seen = set()
    for item in stored.get("cities") or []:
        if not isinstance(item, dict):
            continue
        label = item.get("label")
        tz_name = item.get("tz")
        if not isinstance(label, str) or not label.strip() or not isinstance(tz_name, str):
            continue
        if not _valid_zone(tz_name):
            continue
        city_id = item.get("id")
        if not isinstance(city_id, str) or not city_id or city_id in seen:
            city_id = uuid.uuid4().hex[:8]
        seen.add(city_id)
        cities.append({"id": city_id, "label": label.strip(), "tz": tz_name})
        if len(cities) >= MAX_CITIES:
            break
    if cities:
        config["cities"] = cities
    return config


class X11Desk:
    """Keep an undecorated window on the Ubuntu desktop via EWMH."""

    def __init__(self):
        self._x = ctypes.CDLL("libX11.so.6")
        self._ready = False
        self._atoms: dict[bytes, int] = {}
        self._setup()

    def _setup(self) -> None:
        atom = c_ulong
        window = c_ulong

        class Data(Union):
            _fields_ = [("l", c_long * 5)]

        class ClientEvent(Structure):
            _fields_ = [
                ("type", c_int),
                ("serial", c_ulong),
                ("send_event", c_int),
                ("display", c_void_p),
                ("window", window),
                ("message_type", atom),
                ("format", c_int),
                ("data", Data),
            ]

        class XEvent(Union):
            _fields_ = [("xclient", ClientEvent), ("pad", ctypes.c_byte * 192)]

        self._event_type = XEvent
        xlib = self._x
        xlib.XOpenDisplay.restype = c_void_p
        xlib.XOpenDisplay.argtypes = [c_char_p]
        xlib.XInternAtom.restype = atom
        xlib.XInternAtom.argtypes = [c_void_p, c_char_p, c_int]
        xlib.XSendEvent.restype = c_int
        xlib.XSendEvent.argtypes = [c_void_p, window, c_int, c_long, POINTER(XEvent)]
        xlib.XFlush.argtypes = [c_void_p]
        xlib.XRootWindow.restype = window
        xlib.XRootWindow.argtypes = [c_void_p, c_int]
        xlib.XDefaultScreen.restype = c_int
        xlib.XDefaultScreen.argtypes = [c_void_p]
        xlib.XTranslateCoordinates.restype = c_int
        xlib.XTranslateCoordinates.argtypes = [
            c_void_p,
            window,
            window,
            c_int,
            c_int,
            POINTER(c_int),
            POINTER(c_int),
            POINTER(window),
        ]
        xlib.XQueryPointer.restype = c_int
        xlib.XQueryPointer.argtypes = [
            c_void_p,
            window,
            POINTER(window),
            POINTER(window),
            POINTER(c_int),
            POINTER(c_int),
            POINTER(c_int),
            POINTER(c_int),
            POINTER(c_uint),
        ]
        self._dpy = xlib.XOpenDisplay(None)
        if not self._dpy:
            return
        self._root = xlib.XRootWindow(self._dpy, xlib.XDefaultScreen(self._dpy))
        self._ready = True

    def xid(self, window: Gtk.Window) -> int | None:
        if GdkX11 is None:
            return None
        surface = window.get_surface()
        if surface is None:
            return None
        try:
            return int(GdkX11.X11Surface.get_xid(surface))
        except Exception:
            return None

    def _atom(self, name: bytes) -> int:
        cached = self._atoms.get(name)
        if cached is None:
            cached = int(self._x.XInternAtom(self._dpy, name, False))
            self._atoms[name] = cached
        return cached

    def _client(self, xid: int, message: bytes, values: list[int]) -> None:
        if not self._ready:
            return
        event = self._event_type()
        ctypes.memset(byref(event), 0, sizeof(event))
        event.xclient.type = 33
        event.xclient.send_event = 1
        event.xclient.display = self._dpy
        event.xclient.window = xid
        event.xclient.message_type = self._atom(message)
        event.xclient.format = 32
        for index, value in enumerate(values[:5]):
            event.xclient.data.l[index] = value
        mask = (1 << 19) | (1 << 20)
        self._x.XSendEvent(self._dpy, self._root, False, mask, byref(event))
        self._x.XFlush(self._dpy)

    def _state(self, xid: int, add: bool, first: bytes, second: bytes | None = None) -> None:
        self._client(
            xid,
            b"_NET_WM_STATE",
            [1 if add else 0, self._atom(first), self._atom(second) if second else 0, 1, 0],
        )

    def apply(self, window: Gtk.Window, stack: str) -> None:
        xid = self.xid(window)
        if xid is None:
            return
        surface = window.get_surface()
        try:
            surface.set_skip_taskbar_hint(True)
            surface.set_skip_pager_hint(True)
        except Exception:
            pass
        self._state(xid, True, b"_NET_WM_STATE_STICKY", b"_NET_WM_STATE_SKIP_TASKBAR")
        self._state(xid, True, b"_NET_WM_STATE_SKIP_PAGER")
        if stack == "above":
            self._state(xid, False, b"_NET_WM_STATE_BELOW")
            self._state(xid, True, b"_NET_WM_STATE_ABOVE")
        else:
            self._state(xid, False, b"_NET_WM_STATE_ABOVE")
            self._state(xid, True, b"_NET_WM_STATE_BELOW")

    def move(self, window: Gtk.Window, x: int, y: int, width: int, height: int) -> None:
        xid = self.xid(window)
        if xid is None:
            return
        flags = 10 | (1 << 8) | (1 << 9) | (1 << 12)
        self._client(xid, b"_NET_MOVERESIZE_WINDOW", [flags, int(x), int(y), int(width), int(height)])

    def pointer(self) -> tuple[int, int]:
        if not self._ready:
            return 0, 0
        root_ret, child = c_ulong(), c_ulong()
        rx, ry, wx, wy, mask = c_int(), c_int(), c_int(), c_int(), c_uint()
        self._x.XQueryPointer(
            self._dpy, self._root, byref(root_ret), byref(child), byref(rx), byref(ry), byref(wx), byref(wy), byref(mask)
        )
        return rx.value, ry.value

    def start_move(self, window: Gtk.Window) -> None:
        xid = self.xid(window)
        if xid is None:
            return
        rx, ry = self.pointer()
        # 8 = _NET_WM_MOVERESIZE_MOVE, button 1, source = application
        self._client(xid, b"_NET_WM_MOVERESIZE", [rx, ry, 8, 1, 1])

    def origin(self, window: Gtk.Window) -> tuple[int, int] | None:
        xid = self.xid(window)
        if xid is None or not self._ready:
            return None
        rx, ry, child = c_int(), c_int(), c_ulong()
        self._x.XTranslateCoordinates(self._dpy, xid, self._root, 0, 0, byref(rx), byref(ry), byref(child))
        return rx.value, ry.value


def _clear(widget: Gtk.Widget) -> None:
    while (child := widget.get_first_child()) is not None:
        widget.remove(child)


def _set_text(widget: Gtk.Widget, value: str) -> None:
    if widget.get_label() != value:
        widget.set_label(value)


class CityRow(Gtk.Box):
    def __init__(self, city: dict, on_time, on_remove, on_primary):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.city = city
        self.add_css_class("city-row")

        self.remove_btn = Gtk.Button(label="−")
        self.remove_btn.set_has_frame(False)
        self.remove_btn.add_css_class("remove")
        self.remove_btn.set_valign(Gtk.Align.CENTER)
        self.remove_btn.set_tooltip_text("移除这个地点")
        self.remove_btn.connect("clicked", lambda *_args: on_remove(city["id"]))
        self.revealer = Gtk.Revealer()
        self.revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_RIGHT)
        self.revealer.set_transition_duration(160)
        self.revealer.set_child(self.remove_btn)
        self.append(self.revealer)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        text.set_hexpand(True)
        top = Gtk.Box(spacing=8)
        self.name = Gtk.Label(xalign=0, hexpand=True)
        self.name.add_css_class("city-name")
        self.offset = Gtk.Label(xalign=1)
        top.append(self.name)
        top.append(self.offset)

        self.time_btn = Gtk.Button(label="00:00")
        self.time_btn.set_has_frame(False)
        self.time_btn.add_css_class("time")
        self.time_btn.set_halign(Gtk.Align.START)
        self.time_btn.set_tooltip_text("点击设定这个地点的时间，其他地点会一起换算")
        self.time_btn.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        self.time_btn.connect("clicked", lambda *_args: on_time(self))

        self.meta = Gtk.Label(xalign=0)
        self.meta.add_css_class("meta")
        self.primary_btn = Gtk.Button(label="设为基准")
        self.primary_btn.set_has_frame(False)
        self.primary_btn.add_css_class("linkish")
        self.primary_btn.set_halign(Gtk.Align.START)
        self.primary_btn.set_tooltip_text("用这个地点计算和其他城市的时差")
        self.primary_btn.connect("clicked", lambda *_args: on_primary(city["id"]))
        self.primary_btn.set_visible(False)

        text.append(top)
        text.append(self.time_btn)
        text.append(self.meta)
        text.append(self.primary_btn)
        self.append(text)

    def sync(self, moment: datetime, editing: bool, is_primary: bool, primary_local: datetime, can_remove: bool) -> None:
        local = local_at(self.city["tz"], moment)
        local_off = local.utcoffset() or timedelta(0)
        primary_off = primary_local.utcoffset() or timedelta(0)
        _set_text(self.time_btn, local.strftime("%H:%M"))
        _set_text(self.name, self.city["label"])
        season = season_label(local)
        dst = f" · {season}" if season else ""
        _set_text(self.meta, f"{fmt_date(local)} · {fmt_gmt(local_off)}{dst}")
        if is_primary:
            _set_text(self.offset, "基准")
            self.offset.set_css_classes(["offset-base"])
        else:
            note = day_note(local, primary_local)
            rel = fmt_rel(local_off - primary_off)
            _set_text(self.offset, rel if not note else f"{rel}  {note}")
            self.offset.set_css_classes(["offset"])
        self.revealer.set_reveal_child(editing and can_remove)
        self.primary_btn.set_visible(editing and not is_primary)


class DeltaSep(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.set_margin_top(8)
        self.set_margin_bottom(8)
        self.label = Gtk.Label()
        self.label.add_css_class("delta")
        for index in range(2):
            line = Gtk.Box()
            line.add_css_class("hairline")
            line.set_hexpand(True)
            line.set_valign(Gtk.Align.CENTER)
            line.set_size_request(-1, 1)
            if index == 0:
                self.append(line)
                self.append(self.label)
            else:
                self.append(line)

    def set_text(self, text: str) -> None:
        _set_text(self.label, text)


class DeskWindow(Gtk.ApplicationWindow):
    def __init__(self, app: Adw.Application, x11: X11Desk):
        super().__init__(application=app, title="时区")
        self.x11 = x11
        self.add_css_class("desk")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_opacity(0)

        self.config = load_config()
        self.cities = self.config["cities"]
        self.stack = self.config["stack"]
        self.live = bool(self.config.get("live", True))
        self.moment = datetime.now(timezone.utc)
        if not self.live and self.config.get("moment"):
            self.moment = datetime.fromisoformat(self.config["moment"])
        self.edit_mode = False
        self.rows: list[CityRow] = []
        self.delta: DeltaSep | None = None
        self._placed = False
        self._save_cache = None
        self._toast_id = 0
        self._editor_id = None
        self._editor_dirty = False
        self._editor_was_live = True
        self._others_cache = None
        self._rebuilding = False
        self._menu_refreshers = []

        self._build()
        self._apply_scheme()
        Adw.StyleManager.get_default().connect("notify::dark", self._apply_scheme)
        self.connect("realize", lambda *_args: self.x11.apply(self, self.stack))
        self.connect("map", lambda *_args: self._settle())
        self.connect("close-request", self._on_close)
        GLib.timeout_add(500, self._on_tick)
        GLib.timeout_add(1000, self._remember_position)
        self._rebuild()
        self.set_visible(True)

    def _build(self) -> None:
        self.glass = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.glass.add_css_class("glass")

        header = Gtk.Box(spacing=4)
        self.dot = Gtk.Box()
        self.dot.add_css_class("live-dot")
        self.dot.set_size_request(8, 8)
        self.dot.set_valign(Gtk.Align.CENTER)
        self.title = Gtk.Label(xalign=0, hexpand=True)
        self.title.add_css_class("title")
        self.title.set_cursor(Gdk.Cursor.new_from_name("grab"))
        self.now_btn = Gtk.Button(label="现在")
        self.now_btn.set_has_frame(False)
        self.now_btn.add_css_class("now")
        self.now_btn.set_tooltip_text("回到当前时间")
        self.now_btn.connect("clicked", lambda *_args: self._resume_live())
        self.done_btn = Gtk.Button(label="完成")
        self.done_btn.set_has_frame(False)
        self.done_btn.add_css_class("done")
        self.done_btn.set_visible(False)
        self.done_btn.connect("clicked", lambda *_args: self._set_edit(False))
        self.add_btn = self._glyph_button("+", "添加地点", "add-glyph", self._open_add)
        self.menu_btn = self._glyph_button("•••", "更多", "menu-glyph", self._toggle_menu)
        header.append(self.dot)
        header.append(self.title)
        header.append(self.now_btn)
        header.append(self.done_btn)
        header.append(self.add_btn)
        header.append(self.menu_btn)

        self.toast_rev = Gtk.Revealer()
        self.toast_rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self.toast_rev.set_transition_duration(140)
        self.toast = Gtk.Label(xalign=0)
        self.toast.add_css_class("toast")
        self.toast_rev.set_child(self.toast)

        self.city_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.city_scroll = Gtk.ScrolledWindow()
        self.city_scroll.add_css_class("city-scroll")
        self.city_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.city_scroll.set_propagate_natural_height(True)
        self.city_scroll.set_max_content_height(540)
        self.city_scroll.set_margin_top(8)
        self.city_scroll.set_child(self.city_box)

        self.glass.append(header)
        self.glass.append(self.toast_rev)
        self.glass.append(self.city_scroll)

        canvas = Gtk.Box()
        canvas.add_css_class("canvas")
        canvas.append(self.glass)
        self.set_child(canvas)
        self._moving = False
        drag = Gtk.GestureDrag()
        drag.set_button(1)
        drag.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.glass.add_controller(drag)

        click = Gtk.GestureClick()
        click.set_button(3)
        click.connect("pressed", lambda *_args: self._toggle_menu())
        self.glass.add_controller(click)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._on_key)
        self.add_controller(keys)

        self._build_editor()
        self._build_add_popover()
        self._build_menu()

    def _interactive_at(self, x: float, y: float) -> bool:
        widget = self.glass.pick(x, y, Gtk.PickFlags.DEFAULT)
        while widget is not None and widget is not self.glass:
            if isinstance(widget, (Gtk.Button, Gtk.Entry)):
                return True
            widget = widget.get_parent()
        return False

    def _on_drag_begin(self, gesture, x, y) -> None:
        self._moving = False
        if self._interactive_at(x, y):
            gesture.set_state(Gtk.EventSequenceState.DENIED)

    def _on_drag_update(self, gesture, dx, dy) -> None:
        if self._moving:
            return
        if abs(dx) < 8 and abs(dy) < 8:
            return
        if not self._begin_native_move(gesture):
            return
        self._moving = True
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)

    def _begin_native_move(self, gesture) -> bool:
        surface = self.get_surface()
        if surface is None:
            return False
        sequence = gesture.get_current_sequence()
        event = gesture.get_last_event(sequence)
        device = event.get_device() if event is not None else None
        if device is not None and hasattr(surface, "begin_move"):
            _ok, x, y = event.get_position()
            surface.begin_move(device, gesture.get_current_button(), x, y, event.get_time())
            return True
        self.x11.start_move(self)
        return True

    def _on_drag_end(self, _gesture, _dx, _dy) -> None:
        self._moving = False

    def _glyph_button(self, label: str, tooltip: str, css: str, callback) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.set_has_frame(False)
        button.add_css_class("ghost")
        button.add_css_class(css)
        button.set_tooltip_text(tooltip)
        button.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        button.connect("clicked", callback)
        return button

    def _symbol_button(self, label: str, callback, css: str = "step") -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.set_has_frame(False)
        button.add_css_class(css)
        button.set_cursor(Gdk.Cursor.new_from_name("pointer"))
        button.connect("clicked", lambda *_args: callback())
        return button

    def _bind_scroll(self, widget: Gtk.Widget, on_delta) -> None:
        flags = Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE
        scroll = Gtk.EventControllerScroll.new(flags)
        def on_scroll(_controller, _dx, dy):
            if dy == 0:
                return False
            on_delta(-1 if dy > 0 else 1)
            return True
        scroll.connect("scroll", on_scroll)
        widget.add_controller(scroll)

    def _step_column(self, caption: str, on_delta):
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row = Gtk.Box(spacing=4)
        row.set_halign(Gtk.Align.CENTER)
        value = Gtk.Label(label="00")
        value.add_css_class("step-value")
        value.set_width_chars(2)
        value.set_xalign(0.5)
        row.append(self._symbol_button("−", lambda: on_delta(-1)))
        row.append(value)
        row.append(self._symbol_button("+", lambda: on_delta(1)))
        caption_label = Gtk.Label(label=caption)
        caption_label.add_css_class("meta")
        column.append(row)
        column.append(caption_label)
        self._bind_scroll(column, on_delta)
        return column, value

    def _build_editor(self) -> None:
        self.editor = Gtk.Popover()
        self.editor.add_css_class("menu-pop")
        self.editor.connect("closed", self._on_editor_closed)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        root.set_margin_start(4)
        root.set_margin_end(4)
        root.set_margin_top(2)
        root.set_margin_bottom(2)
        root.set_size_request(268, -1)
        self.editor.set_child(root)

        self.editor_title = Gtk.Label()
        self.editor_title.add_css_class("editor-title")
        root.append(self.editor_title)

        date_row = Gtk.Box(spacing=8)
        date_row.set_halign(Gtk.Align.CENTER)
        previous_day = self._symbol_button("‹", lambda: self._bump_day(-1), "chevron")
        previous_day.set_tooltip_text("前一天")
        self.date_value = Gtk.Label()
        self.date_value.add_css_class("date-value")
        self.date_value.set_width_chars(12)
        next_day = self._symbol_button("›", lambda: self._bump_day(1), "chevron")
        next_day.set_tooltip_text("后一天")
        date_row.append(previous_day)
        date_row.append(self.date_value)
        date_row.append(next_day)
        root.append(date_row)

        clocks = Gtk.Box(spacing=18)
        clocks.set_halign(Gtk.Align.CENTER)
        hour_box, self.hour_value = self._step_column("时", self._bump_hour)
        minute_box, self.minute_value = self._step_column("分", self._bump_minute)
        clocks.append(hour_box)
        clocks.append(minute_box)
        root.append(clocks)

        self.result_title = Gtk.Label(label="同时刻")
        self.result_title.add_css_class("meta")
        root.append(self.result_title)
        self.others = Gtk.Label()
        self.others.add_css_class("others")
        self.others.set_justify(Gtk.Justification.CENTER)
        self.others.set_xalign(0.5)
        root.append(self.others)

        actions = Gtk.Box(spacing=8)
        actions.set_halign(Gtk.Align.CENTER)
        now = Gtk.Button(label="现在")
        now.set_has_frame(False)
        now.add_css_class("editor-action")
        now.connect("clicked", lambda *_args: self._resume_live(close_editor=True))
        done = Gtk.Button(label="完成")
        done.set_has_frame(False)
        done.add_css_class("editor-action")
        done.connect("clicked", lambda *_args: self.editor.popdown())
        actions.append(now)
        actions.append(done)
        root.append(actions)

    def _build_add_popover(self) -> None:
        self.add_pop = Gtk.Popover()
        self.add_pop.add_css_class("menu-pop")
        self.add_pop.set_parent(self.add_btn)
        self.add_pop.connect("show", lambda *_args: GLib.idle_add(self.search.grab_focus))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(280, -1)
        self.search = Gtk.Entry()
        self.search.add_css_class("search")
        self.search.set_placeholder_text("搜索城市、拼音或时区")
        self.search.connect("changed", lambda *_args: self._rebuild_places())
        self.search.connect("activate", lambda *_args: self._activate_first_place())
        box.append(self.search)
        self.place_list = Gtk.ListBox()
        self.place_list.add_css_class("places")
        self.place_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self.place_list.connect("row-activated", self._on_place_activated)
        scroll = Gtk.ScrolledWindow()
        scroll.add_css_class("place-scroll")
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(320)
        scroll.set_child(self.place_list)
        box.append(scroll)
        self.empty = Gtk.Label(label="没有匹配的地点")
        self.empty.add_css_class("meta")
        self.empty.set_margin_bottom(6)
        self.empty.set_visible(False)
        box.append(self.empty)
        self.add_pop.set_child(box)

    def _build_menu(self) -> None:
        self.menu_pop = Gtk.Popover()
        self.menu_pop.add_css_class("menu-pop")
        self.menu_pop.set_parent(self.menu_btn)
        self.menu_pop.connect("show", lambda *_args: self._refresh_menu())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(214, -1)
        box.append(self._menu_button("添加地点", self._open_add_from_menu))
        box.append(self._menu_button("编辑地点", self._toggle_edit_from_menu))
        box.append(self._menu_sep())
        box.append(self._menu_check("实时时钟", lambda: self.live, self._set_live, "关闭后时间停住，方便换算"))
        box.append(self._menu_check("始终置顶", lambda: self.stack == "above", self._set_above, "关闭后贴在桌面，其他窗口可以盖住它"))
        box.append(self._menu_check("登录时加载", autostart_enabled, self._set_autostart, "登录后自动出现在桌面"))
        box.append(self._menu_sep())
        box.append(self._menu_button("从桌面移除", self._confirm_remove, danger=True))
        self.menu_pop.set_child(box)

    def _menu_button(self, label: str, callback, danger: bool = False) -> Gtk.Button:
        button = Gtk.Button(label=label)
        button.set_has_frame(False)
        button.add_css_class("menu-item")
        if danger:
            button.add_css_class("danger")
        button.set_hexpand(True)
        button.get_child().set_xalign(0)
        button.connect("clicked", lambda *_args: callback())
        return button

    def _menu_check(self, label: str, getter, setter, tooltip: str) -> Gtk.Button:
        button = Gtk.Button()
        button.set_has_frame(False)
        button.add_css_class("menu-item")
        button.set_hexpand(True)
        button.set_tooltip_text(tooltip)
        box = Gtk.Box(spacing=8)
        text = Gtk.Label(label=label, xalign=0, hexpand=True)
        mark = Gtk.Label(label="✓")
        mark.add_css_class("check")
        box.append(text)
        box.append(mark)
        button.set_child(box)

        def refresh():
            mark.set_visible(bool(getter()))

        button.connect("clicked", lambda *_args: setter(not getter()) or refresh())
        self._menu_refreshers.append(refresh)
        refresh()
        return button

    def _menu_sep(self) -> Gtk.Separator:
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.add_css_class("menu-sep")
        return separator

    def _refresh_menu(self) -> None:
        for refresh in self._menu_refreshers:
            refresh()

    def _thin_sep(self) -> Gtk.Box:
        line = Gtk.Box()
        line.add_css_class("hairline")
        line.set_size_request(-1, 1)
        line.set_margin_top(8)
        line.set_margin_bottom(8)
        return line

    def _rebuild(self) -> None:
        self._rebuilding = True
        if self.editor.get_parent() is not None:
            if self.editor.get_visible():
                self.editor.popdown()
            self.editor.unparent()
        _clear(self.city_box)
        self.rows = []
        self.delta = None
        for index, city in enumerate(self.cities):
            if index == 1:
                self.delta = DeltaSep()
                self.city_box.append(self.delta)
            elif index > 1:
                self.city_box.append(self._thin_sep())
            row = CityRow(city, self._open_editor, self._remove_city, self._make_primary)
            self.city_box.append(row)
            self.rows.append(row)
        self._rebuilding = False
        self._sync()

    def _sync(self) -> None:
        if not self.cities:
            return
        primary = self.cities[0]
        primary_local = local_at(primary["tz"], self.moment)
        if len(self.cities) > 1:
            _set_text(self.title, f"{primary['label']}  →  {self.cities[1]['label']}")
        else:
            _set_text(self.title, primary["label"])
        if self.live:
            self.dot.remove_css_class("paused")
            self.dot.set_tooltip_text("实时")
        else:
            self.dot.add_css_class("paused")
            self.dot.set_tooltip_text("已暂停，显示的是设定时间")
        self.now_btn.set_visible(not self.live)
        can_remove = len(self.cities) > 1
        for row in self.rows:
            row.sync(self.moment, self.edit_mode, row.city["id"] == primary["id"], primary_local, can_remove)
        if self.delta is not None and len(self.cities) > 1:
            second = self.cities[1]
            second_local = local_at(second["tz"], self.moment)
            gap = ahead_text(
                primary["label"],
                primary_local.utcoffset() or timedelta(0),
                second["label"],
                second_local.utcoffset() or timedelta(0),
            )
            mechanism = mechanism_name(primary["tz"], second["tz"], self.moment)
            self.delta.set_text(f"{mechanism} · {gap}" if mechanism else gap)
        self._sync_editor()

    def _editor_city(self):
        for city in self.cities:
            if city["id"] == self._editor_id:
                return city
        return None

    def _current_local(self):
        city = self._editor_city()
        if city is None:
            return None
        tzinfo = ZoneInfo(city["tz"])
        return self.moment.astimezone(tzinfo), tzinfo, city

    def _sync_editor(self) -> None:
        if not self.editor.get_visible():
            return
        current = self._current_local()
        if current is None:
            return
        local, _tzinfo, city = current
        season = season_label(local)
        title = f"设定{city['label']}时间"
        if season:
            title = f"{title} · {season}"
        _set_text(self.editor_title, title)
        _set_text(self.date_value, fmt_date(local))
        _set_text(self.hour_value, f"{local.hour:02d}")
        _set_text(self.minute_value, f"{local.minute:02d}")
        markup = self._others_markup(city["id"])
        self.result_title.set_visible(bool(markup))
        self.others.set_visible(bool(markup))
        if markup != self._others_cache:
            self._others_cache = markup
            if markup:
                self.others.set_markup(markup)

    def _others_markup(self, current_id: str) -> str:
        lines = []
        hidden = 0
        for city in self.cities:
            if city["id"] == current_id:
                continue
            if len(lines) >= 4:
                hidden += 1
                continue
            local = local_at(city["tz"], self.moment)
            name = GLib.markup_escape_text(city["label"])
            season = season_label(local)
            extra = f" · {season}" if season else ""
            lines.append(f"{name}  <b>{local:%H:%M}</b>  <span alpha='42000'>{fmt_date(local)}{extra}</span>")
        if hidden:
            lines.append(f"<span alpha='42000'>还有 {hidden} 个地点</span>")
        return "\n".join(lines)

    def _set_local(self, tzinfo, date, hour: int, minute: int) -> None:
        try:
            updated = datetime.combine(date, time(hour, minute), tzinfo=tzinfo)
            self.moment = updated.astimezone(timezone.utc)
        except Exception:
            traceback.print_exc()
            return
        self._editor_dirty = True
        self.live = False
        self._persist()
        self._sync()

    def _bump_day(self, delta: int) -> None:
        current = self._current_local()
        if current is None:
            return
        local, tzinfo, _city = current
        self._set_local(tzinfo, local.date() + timedelta(days=delta), local.hour, local.minute)

    def _bump_hour(self, delta: int) -> None:
        current = self._current_local()
        if current is None:
            return
        local, tzinfo, _city = current
        day_delta, hour = divmod(local.hour + delta, 24)
        self._set_local(tzinfo, local.date() + timedelta(days=day_delta), hour, local.minute)

    def _bump_minute(self, delta: int) -> None:
        current = self._current_local()
        if current is None:
            return
        local, tzinfo, _city = current
        day_delta, minutes = divmod(local.hour * 60 + local.minute + delta, 24 * 60)
        hour, minute = divmod(minutes, 60)
        self._set_local(tzinfo, local.date() + timedelta(days=day_delta), hour, minute)

    def _open_editor(self, row: CityRow) -> None:
        self._editor_id = row.city["id"]
        self._editor_dirty = False
        self._editor_was_live = self.live
        self._others_cache = None
        parent = self.editor.get_parent()
        if parent is not row.time_btn:
            if parent is not None:
                self.editor.unparent()
            self.editor.set_parent(row.time_btn)
        self.menu_pop.popdown()
        self.add_pop.popdown()
        self.editor.popup()
        self._sync_editor()

    def _on_editor_closed(self, *_args) -> None:
        if self._rebuilding:
            return
        if not self._editor_dirty and self._editor_was_live:
            self.live = True
            self.moment = datetime.now(timezone.utc)
        self._persist()
        self._sync()

    def _resume_live(self, close_editor: bool = False) -> None:
        self.live = True
        self._editor_dirty = False
        self._editor_was_live = True
        self.moment = datetime.now(timezone.utc)
        self._persist()
        self._sync()
        if close_editor and self.editor.get_visible():
            self.editor.popdown()

    def _set_live(self, live: bool) -> None:
        if live:
            self._resume_live()
        else:
            self.live = False
            self._persist()
            self._sync()

    def _set_edit(self, editing: bool) -> None:
        self.edit_mode = editing
        self.done_btn.set_visible(editing)
        self.menu_btn.set_visible(not editing)
        self._sync()

    def _toggle_edit_from_menu(self) -> None:
        self.menu_pop.popdown()
        self._set_edit(not self.edit_mode)

    def _remove_city(self, city_id: str) -> None:
        if len(self.cities) <= 1:
            return
        self.cities = [city for city in self.cities if city["id"] != city_id]
        self._persist()
        self._rebuild()

    def _make_primary(self, city_id: str) -> None:
        index = next(i for i, city in enumerate(self.cities) if city["id"] == city_id)
        city = self.cities.pop(index)
        self.cities.insert(0, city)
        self._persist()
        self._rebuild()

    def _add_city(self, place) -> None:
        if any(city["label"] == place.label and city["tz"] == place.tz for city in self.cities):
            return
        if len(self.cities) >= MAX_CITIES:
            self._toast(f"最多添加 {MAX_CITIES} 个地点")
            return
        self.cities.append({"id": uuid.uuid4().hex[:8], "label": place.label, "tz": place.tz})
        self._persist()
        self._rebuild()

    def _toast(self, text: str) -> None:
        self.toast.set_label(text)
        self.toast_rev.set_reveal_child(True)
        if self._toast_id:
            GLib.source_remove(self._toast_id)
        self._toast_id = GLib.timeout_add(1800, self._hide_toast)

    def _hide_toast(self) -> bool:
        self.toast_rev.set_reveal_child(False)
        self._toast_id = 0
        return False

    def _rebuild_places(self) -> None:
        _clear(self.place_list)
        places = search_places(self.search.get_text())
        self.empty.set_visible(not places)
        for place in places:
            self.place_list.append(self._place_row(place))

    def _place_row(self, place) -> Gtk.ListBoxRow:
        row = Gtk.ListBoxRow()
        row.place = place
        added = any(city["label"] == place.label and city["tz"] == place.tz for city in self.cities)
        row.added = added
        wrap = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        top = Gtk.Box(spacing=8)
        title = Gtk.Label(label=place.label, xalign=0, hexpand=True)
        title.add_css_class("place-title")
        title.set_ellipsize(Pango.EllipsizeMode.END)
        try:
            offset = fmt_gmt(local_at(place.tz, datetime.now(timezone.utc)).utcoffset())
        except Exception:
            offset = ""
        off = Gtk.Label(label=offset)
        off.add_css_class("meta")
        top.append(title)
        top.append(off)
        subtitle = f"{place.region} · 已添加" if added else f"{place.region} · {place.en}"
        sub = Gtk.Label(label=subtitle, xalign=0)
        sub.add_css_class("meta")
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        wrap.append(top)
        wrap.append(sub)
        row.set_child(wrap)
        row.set_sensitive(not added)
        return row

    def _on_place_activated(self, _listbox, row) -> None:
        if getattr(row, "added", False):
            return
        self._add_city(row.place)
        self.search.set_text("")
        self.add_pop.popdown()

    def _activate_first_place(self) -> None:
        row = self.place_list.get_row_at_index(0)
        if row is not None and not getattr(row, "added", False):
            self._on_place_activated(self.place_list, row)

    def _open_add(self, *_args) -> None:
        self.menu_pop.popdown()
        if self.editor.get_visible():
            self.editor.popdown()
        self.search.set_text("")
        self._rebuild_places()
        self.add_pop.popup()

    def _open_add_from_menu(self) -> None:
        self._open_add()

    def _toggle_menu(self, *_args) -> None:
        if self.menu_pop.get_visible():
            self.menu_pop.popdown()
        else:
            self.add_pop.popdown()
            self.menu_pop.popup()

    def _set_above(self, above: bool) -> None:
        self.stack = "above" if above else "below"
        self.x11.apply(self, self.stack)
        self._persist()

    def _set_autostart(self, enabled: bool) -> None:
        if enabled:
            enable_autostart()
        else:
            remove_autostart()

    def _confirm_remove(self) -> None:
        self.menu_pop.popdown()
        dialog = Gtk.AlertDialog()
        dialog.set_modal(True)
        dialog.set_message("从桌面移除时区插件？")
        dialog.set_detail("插件会关闭，并取消登录时自动加载。")
        dialog.set_buttons(["取消", "移除"])
        dialog.set_cancel_button(0)
        dialog.set_default_button(0)
        dialog.choose(self, None, self._on_remove_chosen)

    def _on_remove_chosen(self, dialog, result) -> None:
        try:
            index = dialog.choose_finish(result)
        except Exception:
            return
        if index == 1:
            remove_autostart()
            self.close()

    def _on_key(self, _controller, keyval, _keycode, _state) -> bool:
        if keyval != Gdk.KEY_Escape or not self.edit_mode:
            return False
        if self.editor.get_visible() or self.add_pop.get_visible() or self.menu_pop.get_visible():
            return False
        self._set_edit(False)
        return True

    def _apply_scheme(self, *_args) -> None:
        if Adw.StyleManager.get_default().get_dark():
            self.add_css_class("macos-dark")
        else:
            self.remove_css_class("macos-dark")

    def _capture(self) -> None:
        self.config["cities"] = self.cities
        self.config["stack"] = self.stack
        self.config["live"] = self.live
        if self.live:
            self.config["moment"] = None
        else:
            self.config["moment"] = self.moment.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _persist(self) -> None:
        self._capture()
        self._save()

    def _save(self) -> None:
        payload = {
            "stack": self.config.get("stack", "above"),
            "x": self.config.get("x"),
            "y": self.config.get("y"),
            "live": bool(self.config.get("live", True)),
            "moment": self.config.get("moment"),
            "cities": self.config.get("cities", []),
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if text == self._save_cache:
            return
        self._save_cache = text
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        temporary = CONFIG_PATH.with_suffix(".json.tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(CONFIG_PATH)

    def _primary_geometry(self):
        display = self.get_display()
        primary = display.get_primary_monitor()
        if primary is not None:
            return primary.get_geometry()
        monitors = display.get_monitors()
        if monitors.get_n_items():
            return monitors.get_item(0).get_geometry()
        rect = Gdk.Rectangle()
        rect.x = 0
        rect.y = 0
        rect.width = 1920
        rect.height = 1080
        return rect

    def _clamp(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        monitors = self.get_display().get_monitors()
        best = None
        best_area = -1
        for index in range(monitors.get_n_items()):
            geo = monitors.get_item(index).get_geometry()
            overlap_w = max(0, min(x + width, geo.x + geo.width) - max(x, geo.x))
            overlap_h = max(0, min(y + height, geo.y + geo.height) - max(y, geo.y))
            area = overlap_w * overlap_h
            if area > best_area:
                best_area = area
                best = geo
        if best is None:
            return int(x), int(y)
        x = min(max(int(x), best.x + 8), best.x + best.width - 80)
        y = min(max(int(y), best.y + 36), best.y + best.height - 80)
        return x, y

    def _default_xy(self, width: int, height: int) -> tuple[int, int]:
        geo = self._primary_geometry()
        return self._clamp(geo.x + max(geo.width - width - 12, 0), geo.y + 48, width, height)

    def _settle(self, tries: int = 0) -> bool:
        if self._placed:
            return False
        width, height = self.get_width(), self.get_height()
        if self.x11.xid(self) is None or width < 20:
            if tries < 40:
                GLib.timeout_add(30, self._settle, tries + 1)
            else:
                self.set_opacity(1)
            return False
        self.x11.apply(self, self.stack)
        saved_x, saved_y = self.config.get("x"), self.config.get("y")
        if saved_x is None or saved_y is None:
            x, y = self._default_xy(width, height)
        else:
            x, y = self._clamp(int(saved_x), int(saved_y), width, height)
        self.x11.move(self, x, y, width, height)
        self.config["x"], self.config["y"] = x, y
        self._placed = True
        self._save()
        GLib.timeout_add(80, self._reveal)
        GLib.timeout_add(450, self._reapply_hints)
        return False

    def _reveal(self) -> bool:
        self.set_opacity(1)
        return False

    def _reapply_hints(self) -> bool:
        self.x11.apply(self, self.stack)
        return False

    def _remember_position(self) -> bool:
        if not self._placed:
            return True
        origin = self.x11.origin(self)
        if origin is None:
            return True
        x, y = origin
        if self.config.get("x") != x or self.config.get("y") != y:
            self.config["x"], self.config["y"] = x, y
            self._save()
        return True

    def _on_tick(self) -> bool:
        try:
            if self.live and not (self.editor.get_visible() and self._editor_dirty):
                now = datetime.now(timezone.utc)
                if now.strftime("%Y%m%d%H%M") != self.moment.strftime("%Y%m%d%H%M") or self.editor.get_visible():
                    self.moment = now
                    self._sync()
                elif self.moment.minute == now.minute and self.moment.hour == now.hour and self.moment.date() == now.date():
                    self.moment = now
        except Exception:
            traceback.print_exc()
        return True

    def _on_close(self, *_args) -> bool:
        origin = self.x11.origin(self) if self._placed else None
        if origin is not None:
            self.config["x"], self.config["y"] = origin
        self._persist()
        for popover in (self.menu_pop, self.add_pop, self.editor):
            parent = popover.get_parent()
            if parent is not None:
                popover.unparent()
        app = self.get_application()
        if app is not None:
            GLib.idle_add(app.quit)
        return False


def load_css() -> None:
    if not CSS_PATH.exists():
        print(f"缺少样式文件：{CSS_PATH}", file=sys.stderr)
        return
    provider = Gtk.CssProvider()

    def on_error(_provider, _section, error):
        print(f"CSS: {error.message}", file=sys.stderr)

    provider.connect("parsing-error", on_error)
    provider.load_from_path(str(CSS_PATH))
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_USER)


class DeskApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.x11 = X11Desk()
        self._pending_quit = False
        self._pending_remove = False

    def do_startup(self):
        Adw.Application.do_startup(self)
        GLib.set_prgname(APP_ID)
        load_css()

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        self._pending_remove = "--remove" in args
        self._pending_quit = self._pending_remove or "--quit" in args
        self.activate()
        return 0

    def do_activate(self):
        if self._pending_quit:
            remove = self._pending_remove
            self._pending_quit = False
            self._pending_remove = False
            if remove:
                remove_autostart()
            window = self.props.active_window
            if window is not None:
                window.close()
            else:
                self.quit()
            return
        window = self.props.active_window
        if window is None:
            DeskWindow(self, self.x11)
        else:
            window.present()


def main() -> int:
    app = DeskApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
