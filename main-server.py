#!/usr/bin/env python3
import sys
import os
import subprocess
import socket
import time
import json
import threading
import asyncio
import math
import websockets

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QFrame,
    QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QObject,
    QPropertyAnimation,
    QEasingCurve,
    QTimer,
    Property,
    QPointF,
    QRectF,
    QRect,
)
from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QBrush,
    QPalette,
    QLinearGradient,
    QFont,
    QFontMetrics,
)

from evdev import UInput, ecodes as e, AbsInfo


def check_root():
    if os.geteuid() != 0:
        cmd = [
            "pkexec",
            "env",
            f'DISPLAY={os.environ.get("DISPLAY", ":0")}',
            f'XAUTHORITY={os.environ.get("XAUTHORITY", "")}',
            sys.executable,
            os.path.abspath(sys.argv[0]),
        ]
        try:
            subprocess.check_call(cmd)
        except subprocess.CalledProcessError:
            pass
        sys.exit(0)


check_root()

BROADCAST_PORT = 5000
WEBSOCKET_PORT = 8080
DEVICE_NAME = "Microsoft X-Box 360 pad"

ABS_RANGE_STICK = AbsInfo(
    value=0, min=-32768, max=32767, fuzz=16, flat=128, resolution=0
)
ABS_RANGE_TRIGGER = AbsInfo(value=0, min=0, max=255, fuzz=0, flat=0, resolution=0)
ABS_RANGE_DPAD = AbsInfo(value=0, min=-1, max=1, fuzz=0, flat=0, resolution=0)

CAPABILITIES = {
    e.EV_KEY: [
        e.BTN_SOUTH,
        e.BTN_EAST,
        e.BTN_NORTH,
        e.BTN_WEST,
        e.BTN_TL,
        e.BTN_TR,
        e.BTN_SELECT,
        e.BTN_START,
        e.BTN_MODE,
        e.BTN_THUMBL,
        e.BTN_THUMBR,
    ],
    e.EV_ABS: [
        (e.ABS_X, ABS_RANGE_STICK),
        (e.ABS_Y, ABS_RANGE_STICK),
        (e.ABS_RX, ABS_RANGE_STICK),
        (e.ABS_RY, ABS_RANGE_STICK),
        (e.ABS_Z, ABS_RANGE_TRIGGER),
        (e.ABS_RZ, ABS_RANGE_TRIGGER),
        (e.ABS_HAT0X, ABS_RANGE_DPAD),
        (e.ABS_HAT0Y, ABS_RANGE_DPAD),
    ],
}

BUTTON_MAP = {
    "BTN_A": e.BTN_SOUTH,
    "BTN_B": e.BTN_EAST,
    "BTN_X": e.BTN_WEST,
    "BTN_Y": e.BTN_NORTH,
    "BTN_NORTH": e.BTN_NORTH,
    "BTN_SOUTH": e.BTN_SOUTH,
    "BTN_EAST": e.BTN_EAST,
    "BTN_WEST": e.BTN_WEST,
    "BTN_TL": e.BTN_TL,
    "BTN_TR": e.BTN_TR,
    "BTN_SELECT": e.BTN_SELECT,
    "BTN_START": e.BTN_START,
    "BTN_MODE": e.BTN_MODE,
    "BTN_THUMBL": e.BTN_THUMBL,
    "BTN_THUMBR": e.BTN_THUMBR,
}

try:
    ui = UInput(
        CAPABILITIES,
        name=DEVICE_NAME,
        vendor=0x045E,
        product=0x028E,
        version=0x110,
        bustype=0x03,
    )
except Exception as ex:
    print(f"UInput error: {ex}")
    sys.exit(1)


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


class ServerSignals(QObject):
    stage_update = Signal(str)
    log_entry = Signal(str, str, str)


class ServerThread(QThread):
    def __init__(self, signals: ServerSignals):
        super().__init__()
        self._signals = signals
        self._is_running = True
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        threading.Thread(target=self._broadcast_presence, daemon=True).start()

        local_ip = get_local_ip()
        self._signals.stage_update.emit("wifi")
        time.sleep(0.3)
        self._signals.stage_update.emit("ws")
        time.sleep(0.3)
        self._signals.stage_update.emit("uinput")
        self._signals.log_entry.emit(
            "network", "Server Active", f"{local_ip}:{WEBSOCKET_PORT}"
        )

        start_server = websockets.serve(self._handle_client, "0.0.0.0", WEBSOCKET_PORT)
        self._loop.run_until_complete(start_server)
        self._loop.run_forever()

    def _broadcast_presence(self):
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        payload = json.dumps(
            {
                "name": "Xbox 360 Controller",
                "ip": get_local_ip(),
                "port": WEBSOCKET_PORT,
                "type": "volant_server",
            }
        ).encode()
        while self._is_running:
            try:
                udp.sendto(payload, ("<broadcast>", BROADCAST_PORT))
                time.sleep(2)
            except Exception:
                time.sleep(5)

    async def _handle_client(self, websocket):
        client_ip = websocket.remote_address[0]
        self._signals.stage_update.emit("device")
        self._signals.log_entry.emit("connect", "Client Connected", client_ip)
        try:
            async for message in websocket:
                data = json.loads(message)
                code_str = data.get("code")
                value = int(data.get("value", 0))
                msg_type = data.get("type")
                if msg_type == "key":
                    code = BUTTON_MAP.get(code_str) or (
                        getattr(e, code_str, None) if hasattr(e, code_str) else None
                    )
                    if code is not None:
                        ui.write(e.EV_KEY, code, value)
                        ui.syn()
                elif msg_type == "abs" and hasattr(e, code_str):
                    code = getattr(e, code_str)
                    normalized = (
                        int((value / 255.0) * 32767)
                        if code in (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY)
                        else value
                    )
                    ui.write(e.EV_ABS, code, normalized)
                    ui.syn()
        except Exception:
            pass
        finally:
            self._signals.log_entry.emit("disconnect", "Client Disconnected", client_ip)

    def stop(self):
        self._is_running = False
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)


# ── Design tokens — neutral dark/white only ───────────────────────────────────
BG = "#1e1e20"
SURFACE = "#2a2a2c"
BORDER = "#363638"
TEXT_PRIMARY = "#efefef"
TEXT_MUTED = "#666668"
TEXT_DIM = "#3e3e40"
LINE_COLOR = "#303032"

# Single accent: off-white for active states
ACTIVE_STROKE = QColor("#d0d0d2")
IDLE_STROKE = QColor("#3e3e40")
ACTIVE_LABEL = QColor("#efefef")
IDLE_LABEL = QColor("#444446")

DOT_CONNECT = QColor("#c8c8ca")
DOT_DISCONNECT = QColor("#666668")
DOT_NETWORK = QColor("#909092")
DOT_NEUTRAL = QColor("#3e3e40")

DOT_D = 14
RAIL_X = 20
GUTTER = 48


# ── Single connection icon — no background fill, just stroke ─────────────────
class ConnectionIcon(QWidget):
    def __init__(self, label: str, icon_type: str, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon_type = icon_type
        self._progress = 0.0  # 0.0 → 1.0, drives all visuals
        self._phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick)
        self.setFixedSize(64, 72)

        self._anim = QPropertyAnimation(self, b"progress", self)
        self._anim.setDuration(700)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, v: float):
        self._progress = v
        self.update()

    progress = Property(float, get_progress, set_progress)

    def activate(self):
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._pulse_timer.start(30)

    def deactivate(self):
        self._pulse_timer.stop()
        self._anim.setStartValue(self._progress)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _tick(self):
        self._phase = (self._phase + 0.045) % (2 * math.pi)
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2.0
        cy = 28.0
        t = self._progress
        pulse = 0.5 + 0.5 * math.sin(self._phase)

        # stroke color: lerp idle → active
        idle_v = 0x3E
        active_v = 0xD0
        val = int(idle_v + (active_v - idle_v) * t)
        stroke = QColor(val, val, val + 2)

        stroke_w = 1.2 + 0.6 * t
        p.setPen(QPen(stroke, stroke_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.setBrush(Qt.NoBrush)

        p.save()
        p.translate(cx - 12, cy - 12)
        self._draw_icon(p, stroke)
        p.restore()

        label_v = int(0x44 + (0xEF - 0x44) * t)
        lc = QColor(label_v, label_v, label_v + 2)
        p.setPen(lc)
        font = QFont("Inter", 9)
        p.setFont(font)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self._label)
        p.drawText(int(cx - tw / 2), int(cy + 28 + 14), self._label)

    def _draw_icon(self, p: QPainter, stroke: QColor):
        t = self._icon_type
        p.setBrush(Qt.NoBrush)
        if t == "device":
            p.drawRoundedRect(QRectF(5, 1, 14, 22), 2.5, 2.5)
            p.setBrush(QBrush(stroke))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(12, 19.5), 1.1, 1.1)
            p.setPen(QPen(stroke, p.pen().widthF(), Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
        elif t == "wifi":
            for r in [3.0, 6.5, 10.0]:
                p.drawArc(
                    QRectF(12 - r, 13 - r, r * 2, r * 2), int(210 * 16), int(120 * 16)
                )
            p.setBrush(QBrush(stroke))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(12, 20.8), 1.2, 1.2)
            p.setPen(QPen(stroke, p.pen().widthF(), Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
        elif t == "ws":
            p.drawEllipse(QRectF(2, 2, 20, 20))
            p.drawLine(QPointF(12, 2), QPointF(12, 22))
            p.drawLine(QPointF(2, 12), QPointF(22, 12))
            p.drawArc(QRectF(6, 2, 12, 20), int(0), int(180 * 16))
            p.drawArc(QRectF(6, 2, 12, 20), int(180 * 16), int(180 * 16))
        elif t == "uinput":
            p.drawRoundedRect(QRectF(2, 7, 20, 10), 2, 2)
            p.drawLine(QPointF(5.5, 12), QPointF(8.5, 12))
            p.drawLine(QPointF(7, 10.5), QPointF(7, 13.5))
            p.setBrush(QBrush(stroke))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(15.0, 11.5), 0.9, 0.9)
            p.drawEllipse(QPointF(17.5, 11.5), 0.9, 0.9)
            p.setBrush(Qt.NoBrush)


# ── Animated rail between icons ───────────────────────────────────────────────
class ConnectionRail(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._fill = 0.0
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._anim = QPropertyAnimation(self, b"fill", self)
        self._anim.setDuration(600)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def get_fill(self) -> float:
        return self._fill

    def set_fill(self, v: float):
        self._fill = v
        self.update()

    fill = Property(float, get_fill, set_fill)

    def animate_to(self, target: float):
        self._anim.setStartValue(self._fill)
        self._anim.setEndValue(max(0.0, min(1.0, target)))
        self._anim.start()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        p.setBrush(QBrush(QColor(TEXT_DIM)))
        p.setPen(Qt.NoPen)
        p.drawRect(0, 0, w, 1)
        if self._fill > 0:
            filled_w = max(1, int(w * self._fill))
            p.setBrush(QBrush(QColor(ACTIVE_STROKE)))
            p.drawRect(0, 0, filled_w, 1)


# ── Pulsing status dot ────────────────────────────────────────────────────────
class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._color = QColor(TEXT_DIM)
        self._is_active = False
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setFixedSize(22, 22)

    def set_active(self, color: QColor, active: bool):
        self._color = color
        self._is_active = active
        if active:
            self._timer.start(30)
        else:
            self._timer.stop()
        self.update()

    def _tick(self):
        self._phase = (self._phase + 0.05) % (2 * math.pi)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = self.width() / 2.0
        if self._is_active:
            pulse = 0.5 + 0.5 * math.sin(self._phase)
            halo = QColor(self._color)
            halo.setAlphaF(0.18 * pulse)
            p.setBrush(QBrush(halo))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(c, c), 7, 7)
        p.setBrush(QBrush(self._color))
        p.setPen(Qt.NoPen)
        p.drawEllipse(QPointF(c, c), 3.5, 3.5)


# ── Connection panel ──────────────────────────────────────────────────────────
# Boot order: wifi → ws → uinput → device (only on client connect)
BOOT_ORDER = ["wifi", "ws", "uinput"]
ALL_STAGES = ["device", "wifi", "ws", "uinput"]
STAGE_LABELS = {
    "device": "Device",
    "wifi": "Wi-Fi",
    "ws": "WebSocket",
    "uinput": "UInput",
}
STAGE_ORDER = ["device", "wifi", "ws", "uinput"]


class ConnectionPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._active: set[str] = set()
        self._sessions = 0
        self._build()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        card = QFrame()
        card.setObjectName("CP")
        card.setStyleSheet(
            f"""
            QFrame#CP {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 16px;
            }}
        """
        )
        outer.addWidget(card)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(16, 14, 16, 14)
        inner.setSpacing(12)

        # ── header ────────────────────────────────────────────────────────────
        hrow = QHBoxLayout()
        hrow.setSpacing(0)

        name = QLabel("Xbox 360 Controller")
        name.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:13px; font-weight:500; background:transparent;"
        )
        hrow.addWidget(name)
        hrow.addStretch()

        self._session_lbl = QLabel("")
        self._session_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; background:transparent;"
        )
        hrow.addWidget(self._session_lbl, alignment=Qt.AlignRight | Qt.AlignVCenter)
        inner.addLayout(hrow)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{BORDER}; border:none;")
        inner.addWidget(sep)

        # ── icons + rails ─────────────────────────────────────────────────────
        icon_row = QWidget()
        icon_row.setStyleSheet("background:transparent;")
        il = QHBoxLayout(icon_row)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(0)

        self._icons: dict[str, ConnectionIcon] = {}
        self._rails: list[ConnectionRail] = []

        for i, stage in enumerate(STAGE_ORDER):
            icon = ConnectionIcon(STAGE_LABELS[stage], stage)
            self._icons[stage] = icon
            il.addWidget(icon, alignment=Qt.AlignHCenter)
            if i < len(STAGE_ORDER) - 1:
                rail = ConnectionRail()
                self._rails.append(rail)
                il.addWidget(rail, alignment=Qt.AlignVCenter)

        inner.addWidget(icon_row)

        # ── status row ────────────────────────────────────────────────────────
        srow = QHBoxLayout()
        srow.setSpacing(7)
        self._dot = StatusDot()
        self._status_lbl = QLabel("Initializing")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent;"
        )
        srow.addWidget(self._dot)
        srow.addWidget(self._status_lbl)
        srow.addStretch()
        inner.addLayout(srow)

    def activate_stage(self, stage: str):
        if stage in self._active:
            return
        self._active.add(stage)
        self._icons[stage].activate()

        idx = STAGE_ORDER.index(stage)
        for rail_i, rail in enumerate(self._rails):
            left_stage = STAGE_ORDER[rail_i]
            right_stage = STAGE_ORDER[rail_i + 1]
            if left_stage in self._active and right_stage in self._active:
                rail.animate_to(1.0)

        self._refresh_status(stage)

    def _refresh_status(self, last: str):
        messages = {
            "wifi": ("Scanning network", False),
            "ws": (f"Listening  :{WEBSOCKET_PORT}", True),
            "uinput": ("Ready — waiting for device", True),
            "device": ("Client connected", True),
        }
        text, active = messages.get(last, ("Initializing", False))
        color = QColor(ACTIVE_STROKE) if active else QColor(TEXT_DIM)
        self._dot.set_active(color, active)
        self._status_lbl.setText(text)
        c = TEXT_PRIMARY if active else TEXT_MUTED
        self._status_lbl.setStyleSheet(
            f"color:{c}; font-size:11px; background:transparent;"
        )

    def on_client_connected(self, ip: str):
        self._sessions += 1
        self._session_lbl.setText(
            f"{self._sessions} session{'s' if self._sessions != 1 else ''}"
        )
        self._dot.set_active(QColor(ACTIVE_STROKE), True)
        self._status_lbl.setText(f"Connected  ·  {ip}")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; background:transparent;"
        )

    def on_client_disconnected(self):
        self._icons["device"].deactivate()
        self._active.discard("device")
        for rail_i, rail in enumerate(self._rails):
            left = STAGE_ORDER[rail_i]
            right = STAGE_ORDER[rail_i + 1]
            if left == "uinput" or right == "device" or left == "device":
                rail.animate_to(0.0 if right == "device" or left == "device" else 1.0)
        self._dot.set_active(QColor(TEXT_DIM), False)
        self._status_lbl.setText("Idle — waiting for device")
        self._status_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:11px; background:transparent;"
        )


# ── Timeline ──────────────────────────────────────────────────────────────────
class _DotMarker(QWidget):
    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(GUTTER)
        self.setMinimumHeight(DOT_D + 20)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cy, r = self.height() // 2, DOT_D // 2
        halo = QColor(self._color)
        halo.setAlpha(25)
        p.setBrush(QBrush(halo))
        p.setPen(Qt.NoPen)
        pad = 4
        p.drawEllipse(RAIL_X - r - pad, cy - r - pad, (r + pad) * 2, (r + pad) * 2)
        p.setBrush(QBrush(self._color))
        p.drawEllipse(RAIL_X - r, cy - r, DOT_D, DOT_D)


class _RailLine(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(GUTTER)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, _e):
        p = QPainter(self)
        pen = QPen(QColor(LINE_COLOR), 1)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(RAIL_X, 0, RAIL_X, self.height())


class TimelineRow(QWidget):
    def __init__(
        self, timestamp: str, title: str, subtitle: str, dot_color: QColor, parent=None
    ):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(_DotMarker(dot_color), 0, Qt.AlignTop)

        card = QFrame()
        card.setObjectName("TLC")
        card.setStyleSheet(
            f"""
            QFrame#TLC {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 11px;
            }}
        """
        )
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 9, 12, 9)
        cl.setSpacing(2)

        tl = QLabel(timestamp)
        tl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; font-family:monospace; background:transparent; border:none;"
        )
        ttl = QLabel(title)
        ttl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:12px; font-weight:500; background:transparent; border:none;"
        )
        cl.addWidget(tl)
        cl.addWidget(ttl)

        if subtitle:
            sl = QLabel(subtitle)
            sl.setStyleSheet(
                f"color:{TEXT_MUTED}; font-size:11px; background:transparent; border:none;"
            )
            sl.setWordWrap(True)
            cl.addWidget(sl)

        row.addWidget(card)
        row.addSpacing(2)
        self._anim: QPropertyAnimation | None = None

    def animate_in(self):
        self._anim = QPropertyAnimation(self, b"maximumHeight", self)
        self._anim.setDuration(380)
        self._anim.setStartValue(0)
        self._anim.setEndValue(self.sizeHint().height() + 4)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.setMaximumHeight(0)
        self._anim.finished.connect(lambda: self.setMaximumHeight(16777215))
        self._anim.start(QPropertyAnimation.DeleteWhenStopped)


class TimelineBody(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._count = 0
        self._rail = _RailLine(self)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 6, 0, 6)
        self._layout.setSpacing(6)
        self._layout.addStretch()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._rail.setGeometry(0, 0, GUTTER, self.height())
        self._rail.lower()

    def append_row(self, timestamp: str, title: str, subtitle: str, dot_color: QColor):
        row = TimelineRow(timestamp, title, subtitle, dot_color)
        stretch = self._layout.takeAt(self._layout.count() - 1)
        self._layout.addWidget(row)
        self._layout.addItem(stretch)
        delay = min(self._count * 45, 240)
        self._count += 1
        QTimer.singleShot(delay, row.animate_in)


# ── Main window ───────────────────────────────────────────────────────────────
class VolantWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Volant Server")
        self.setMinimumSize(380, 520)
        self.resize(390, 520)
        self._apply_style()
        self._build_ui()
        self._start_server()

    def _apply_style(self):
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget {{
                background: {BG};
                color: {TEXT_PRIMARY};
                font-family: 'Inter', 'SF Pro Text', 'Segoe UI', sans-serif;
            }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{
                background: transparent; width: 3px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER}; border-radius: 2px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """
        )

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 18, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Volant Server")
        title.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:16px; font-weight:600; letter-spacing:-0.3px;"
        )
        layout.addWidget(title)

        self._conn_panel = ConnectionPanel()
        layout.addWidget(self._conn_panel)

        log_lbl = QLabel("Log")
        log_lbl.setStyleSheet(
            f"color:{TEXT_MUTED}; font-size:10px; letter-spacing:0.5px;"
        )
        layout.addWidget(log_lbl)

        self._timeline = TimelineBody()
        self._timeline.setStyleSheet("background:transparent;")

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(self._timeline)
        self._scroll.setStyleSheet("background:transparent;")
        layout.addWidget(self._scroll, stretch=1)

        stop = QPushButton("Stop Server")
        stop.setCursor(Qt.PointingHandCursor)
        stop.setFixedHeight(40)
        stop.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_MUTED};
                border: 1px solid {BORDER};
                border-radius: 10px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                border-color: #888;
                color: {TEXT_PRIMARY};
            }}
            QPushButton:pressed {{
                background: rgba(255,255,255,0.04);
            }}
        """
        )
        stop.clicked.connect(self._on_stop)
        layout.addWidget(stop)
        self.setCentralWidget(root)

    def _start_server(self):
        self._signals = ServerSignals()
        self._signals.stage_update.connect(self._on_stage)
        self._signals.log_entry.connect(self._on_log)
        self._server = ServerThread(self._signals)
        self._server.start()

    def _on_stage(self, stage: str):
        self._conn_panel.activate_stage(stage)

    def _on_log(self, entry_type: str, title: str, detail: str):
        color_map = {
            "network": DOT_NETWORK,
            "connect": DOT_CONNECT,
            "disconnect": DOT_DISCONNECT,
        }
        dot_color = color_map.get(entry_type, DOT_NEUTRAL)
        self._timeline.append_row(time.strftime("%H:%M"), title, detail, dot_color)

        if entry_type == "connect":
            self._conn_panel.on_client_connected(detail)
        elif entry_type == "disconnect":
            self._conn_panel.on_client_disconnected()

        QTimer.singleShot(60, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        bar = self._scroll.verticalScrollBar()
        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(300)
        anim.setEndValue(bar.maximum())
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start(QPropertyAnimation.DeleteWhenStopped)

    def _on_stop(self):
        self._server.stop()
        ui.close()
        self.close()

    def closeEvent(self, event):
        self._server.stop()
        ui.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("Volant Server")

    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(BG))
    pal.setColor(QPalette.WindowText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Base, QColor(SURFACE))
    pal.setColor(QPalette.Text, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Button, QColor(SURFACE))
    pal.setColor(QPalette.ButtonText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.Highlight, QColor("#3a3a3c"))
    pal.setColor(QPalette.HighlightedText, QColor(TEXT_PRIMARY))
    app.setPalette(pal)

    win = VolantWindow()
    win.show()
    sys.exit(app.exec())
