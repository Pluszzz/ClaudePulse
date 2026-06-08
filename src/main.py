"""ClaudePulse — Qt6 multi-session status monitor for Claude Code."""
import json
import os
import sys
import time
import webbrowser

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QPointF, QSize, QPropertyAnimation, QEasingCurve,
    QRect, QRectF, Signal, QSequentialAnimationGroup, QPauseAnimation
)
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QMouseEvent,
    QAction, QIcon, QFontMetrics, QCursor, QPainterPath, QRegion
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QDialog,
    QSystemTrayIcon, QMenu, QStyledItemDelegate, QStyle,
    QStyleOption, QSlider, QPushButton, QFrame, QSpacerItem,
    QSizePolicy, QAbstractItemView, QSplitter,
    QGraphicsOpacityEffect
)

from session_manager import SessionManager, STATUS_MAP, STARTING_TIMEOUT, ENDED_RETENTION

# ── Constants ───────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.claude/status/window-config.json")
CURRENT_FILE = os.path.expanduser("~/.claude/status/current.json")
LOCK_FILE   = os.path.expanduser("~/.claude/status/window.lock")
GITHUB_URL  = "https://github.com/Pluszzz/ClaudePulse"
POLL_MS     = 500
FLASH_DURATION = 200

TITLE_H    = 28
TAB_W      = 120
TAB_ITEM_H = 30
MIN_W      = 320
MIN_H      = 140
MAX_H      = 600
COMPACT_W  = 120
COMPACT_H  = 120
DEFAULT_OPACITY = 0.75

C_BG         = "#1e1e2e"
C_TAB_BG     = "#181825"
C_TAB_ACTIVE = "#2a2a3a"
C_TITLE_BG   = "#181825"
C_WHITE      = "#ffffff"
C_DIM        = "#a6adc8"
C_MUTED      = "#585b70"
C_BORDER     = "#45475a"
C_HOVER      = "#f87171"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def load_config():
    defaults = {"opacity": DEFAULT_OPACITY, "x": None, "y": None,
                "tabOrder": [], "flashMode": "border", "flashBorderWidth": 4}
    try:
        with open(CONFIG_FILE, "r") as f:
            return {**defaults, **json.load(f)}
    except Exception:
        return defaults

def save_config(opacity, x, y, tabOrder, width=None, height=None,
                splitterSizes=None, flashMode=None, flashBorderWidth=None):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        data = {"opacity": opacity, "x": x, "y": y, "tabOrder": tabOrder}
        if width is not None:           data["width"] = width
        if height is not None:          data["height"] = height
        if splitterSizes is not None:   data["splitterSizes"] = splitterSizes
        if flashMode is not None:       data["flashMode"] = flashMode
        if flashBorderWidth is not None: data["flashBorderWidth"] = flashBorderWidth
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Compact Window — independent circular overlay
# ═══════════════════════════════════════════════════════════════

class CompactWindow(QWidget):
    """Standalone frameless circular window.
    Supports docking to screen edges as a half-circle:
      - None : full 120×120 circle
      - "left" / "right" : 60×120 half-circle on side edge
      - "top" : 120×60 half-circle on top edge
    Uses WA_TranslucentBackground + QPainter.setOpacity for:
      - Anti-aliased circle edges (per-pixel alpha)
      - User-controlled opacity (no conflict with setWindowOpacity)"""
    hovered  = Signal()
    unhovered = Signal()

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(COMPACT_W, COMPACT_H)
        self.setCursor(Qt.PointingHandCursor)

        self._opacity = DEFAULT_OPACITY
        self._dock = None         # None | "left" | "right" | "top"
        self._dragging = False
        self._drag_pos = QPoint()
        self._session_name = ""
        self._marquee_anim = None

        # Flash
        self._flash_color: QColor | None = None
        self._flash_count = 0
        self._flash_mode = "border"
        self._flash_border_w = 4
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)

        # Centered text block
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        self._inner = QWidget()
        self._inner.setStyleSheet("background:transparent;")
        inner_layout = QVBoxLayout(self._inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(6)
        inner_layout.setAlignment(Qt.AlignCenter)

        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self.status_lbl.setStyleSheet("background:transparent; border:none;")
        self.status_lbl.setAlignment(Qt.AlignCenter)
        inner_layout.addWidget(self.status_lbl)

        self._name_container = QWidget()
        self._name_container.setFixedSize(100, 20)
        self._name_container.setStyleSheet("background:transparent; border:none;")
        self.name_lbl = QLabel("")
        self.name_lbl.setFont(QFont("Microsoft YaHei UI", 8))
        self.name_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent; border:none;")
        self.name_lbl.setParent(self._name_container)
        inner_layout.addWidget(self._name_container, 0, Qt.AlignCenter)

        outer.addWidget(self._inner)

    # ── Public API ─────────────────────────────────────────

    def set_opacity(self, val):
        self._opacity = val
        self.update()

    def set_flash_settings(self, mode, border_w):
        self._flash_mode = mode
        self._flash_border_w = border_w

    def start_flash(self, color_hex):
        self._flash_color = QColor(color_hex)
        self._flash_count = 0
        self._flash_timer.start(FLASH_DURATION)

    def _flash_tick(self):
        self._flash_count += 1
        if self._flash_count >= 7:
            self._flash_timer.stop()
            self._flash_color = None
        self.update()

    def set_status(self, color_hex, text):
        self.status_lbl.setText(f'<span style="color:{color_hex};">● {text}</span>')

    def set_session_name(self, name):
        if self._session_name == name:
            return
        self._session_name = name
        self.name_lbl.setText(name)
        self.name_lbl.adjustSize()
        self._stop_marquee()
        QTimer.singleShot(200, self._check_marquee)

    def set_dock(self, edge):
        """Attach to screen edge as half-circle.
        edge: None (full circle), "left", "right", or "top"."""
        if self._dock == edge:
            return
        self._dock = edge
        if edge == "left" or edge == "right":
            self.setFixedSize(COMPACT_W // 2, COMPACT_H)
            self._name_container.hide()
            self.status_lbl.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        elif edge == "top":
            self.setFixedSize(COMPACT_W, COMPACT_H // 2)
            self._name_container.show()
            self.status_lbl.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        else:
            self.setFixedSize(COMPACT_W, COMPACT_H)
            self._name_container.show()
            self.status_lbl.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self._stop_marquee()
        QTimer.singleShot(200, self._check_marquee)  # re-center after resize
        self.update()

    def dock(self):
        return self._dock

    # ── Full-circle center in screen coords ────────────────

    def full_circle_center(self):
        """Screen coords of the full circle center (used for expand alignment)."""
        geo = self.geometry()
        if self._dock == "left":
            return QPoint(geo.x(), geo.y() + COMPACT_H // 2)
        elif self._dock == "right":
            return QPoint(geo.x() + COMPACT_W // 2, geo.y() + COMPACT_H // 2)
        elif self._dock == "top":
            return QPoint(geo.x() + COMPACT_W // 2, geo.y())
        else:
            return geo.center()

    # ── Marquee ────────────────────────────────────────────

    def _check_marquee(self):
        if self._dock in ("left", "right"):
            return  # no name shown in side-dock
        cw = self._name_container.width()
        tw = self.name_lbl.sizeHint().width()
        if tw > cw and self._session_name:
            self._start_marquee(cw, tw)
        else:
            x = max(0, (cw - tw) // 2)
            self.name_lbl.move(x, 2)

    def _start_marquee(self, container_w, text_w):
        self._stop_marquee()
        dx = text_w - container_w + 16
        dur = max(2500, dx * 18)

        a1 = QPropertyAnimation(self.name_lbl, b"pos")
        a1.setDuration(dur); a1.setStartValue(QPoint(0, 2))
        a1.setEndValue(QPoint(-dx, 2))
        a1.setEasingCurve(QEasingCurve.InOutCubic)

        a2 = QPropertyAnimation(self.name_lbl, b"pos")
        a2.setDuration(dur); a2.setStartValue(QPoint(-dx, 2))
        a2.setEndValue(QPoint(0, 2))
        a2.setEasingCurve(QEasingCurve.InOutCubic)

        self._marquee_anim = QSequentialAnimationGroup(self)
        self._marquee_anim.addAnimation(a1)
        self._marquee_anim.addAnimation(QPauseAnimation(1200))
        self._marquee_anim.addAnimation(a2)
        self._marquee_anim.addAnimation(QPauseAnimation(1200))
        self._marquee_anim.setLoopCount(-1)
        self._marquee_anim.start()

    def _stop_marquee(self):
        if self._marquee_anim:
            self._marquee_anim.stop()
            self._marquee_anim = None
        self.name_lbl.move(0, 2)

    # ── Drag to move ───────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self.move(self.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    # ── Hover ──────────────────────────────────────────────

    def enterEvent(self, event):
        super().enterEvent(event)
        self.hovered.emit()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.unhovered.emit()

    # ── Paint ──────────────────────────────────────────────

    def paintEvent(self, event):
        """Draw circle / half-circle at current opacity.
        For docked edges the full circle is painted but only the
        visible half inside the window rect appears (clipped)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setOpacity(self._opacity)

        r = 59  # radius, 1px inset for border
        w, h = self.width(), self.height()
        if self._dock == "left":
            cx, cy = 0, h // 2           # right half visible (arc → right)
        elif self._dock == "right":
            cx, cy = w, h // 2           # left half visible (arc ← left)
        elif self._dock == "top":
            cx, cy = w // 2, 0           # bottom half visible (arc ↓ down)
        else:
            cx, cy = w // 2, h // 2      # full circle

        # Flash effect
        flash_on = (self._flash_color and self._flash_color.isValid()
                    and self._flash_count % 2 == 1)
        if flash_on:
            if self._flash_mode == "overlay":
                painter.setBrush(self._flash_color)
                painter.setPen(Qt.NoPen)
            else:  # border
                painter.setBrush(QColor(C_BG))
                painter.setPen(QPen(self._flash_color, self._flash_border_w))
        else:
            painter.setBrush(QColor(C_BG))
            painter.setPen(QPen(QColor(C_BORDER), 1))

        painter.drawEllipse(QPointF(cx, cy), r, r)


# ═══════════════════════════════════════════════════════════════
# Title Bar
# ═══════════════════════════════════════════════════════════════

class TitleBar(QWidget):
    minimizeClicked = Signal()
    closeClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(TITLE_H)
        self.setStyleSheet(f"background:{C_TITLE_BG};")
        self._dragging = False
        self._drag_pos = QPoint()
        self._click_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(0)

        self.title_lbl = QLabel("ClaudePulse")
        self.title_lbl.setFont(QFont("Microsoft YaHei UI", 9, QFont.Bold))
        self.title_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        self.title_lbl.setCursor(Qt.PointingHandCursor)
        self.title_lbl.mousePressEvent = self._lbl_press
        self.title_lbl.mouseReleaseEvent = self._lbl_release
        self.title_lbl.enterEvent = lambda e: self.title_lbl.setStyleSheet(
            f"color:{C_WHITE}; background:transparent;")
        self.title_lbl.leaveEvent = lambda e: self.title_lbl.setStyleSheet(
            f"color:{C_DIM}; background:transparent;")
        layout.addWidget(self.title_lbl)
        layout.addStretch()

        self.min_btn = self._btn("─", 9)
        self.min_btn.clicked.connect(self.minimizeClicked.emit)
        self.min_btn.setFixedSize(24, 24)
        layout.addWidget(self.min_btn)

        self.close_btn = self._btn("×", 11)
        self.close_btn.clicked.connect(self.closeClicked.emit)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet(
            f"QPushButton {{ color:{C_DIM}; background:transparent; border:none; font-weight:bold; font-size:14px; }}"
            f"QPushButton:hover {{ color:{C_HOVER}; }}")
        layout.addWidget(self.close_btn)

    def _btn(self, text, size):
        b = QPushButton(text)
        b.setFont(QFont("Microsoft YaHei UI", size, QFont.Bold))
        b.setStyleSheet(
            f"QPushButton {{ color:{C_DIM}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ color:{C_WHITE}; }}")
        b.setCursor(Qt.PointingHandCursor)
        return b

    def _lbl_press(self, event):
        self._click_pos = event.globalPosition().toPoint()

    def _lbl_release(self, event):
        delta = event.globalPosition().toPoint() - self._click_pos
        if delta.manhattanLength() < 4:
            webbrowser.open(GITHUB_URL)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            win = self.window()
            delta = event.globalPosition().toPoint() - self._drag_pos
            win.move(win.pos() + delta)
            self._drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False


# ═══════════════════════════════════════════════════════════════
# Tab Item Delegate
# ═══════════════════════════════════════════════════════════════

class TabDelegate(QStyledItemDelegate):
    def __init__(self, get_eff_status, parent=None):
        super().__init__(parent)
        self._eff = get_eff_status

    def paint(self, painter: QPainter, option: QStyleOption, index):
        painter.save()
        rect = option.rect
        sid = index.data(Qt.UserRole)
        eff = self._eff(sid) if sid else "ended"
        color_hex, _ = STATUS_MAP.get(eff, ("#9ca3af", ""))
        is_sel = option.state & QStyle.State_Selected
        bg = QColor(C_TAB_ACTIVE) if is_sel else QColor(C_TAB_BG)
        painter.fillRect(rect, bg)
        if is_sel:
            painter.fillRect(QRect(rect.x(), rect.y() + 4, 2, rect.height() - 8),
                             QColor(color_hex))
        dot_r = 5
        cx, cy = rect.x() + 10, rect.y() + rect.height() // 2
        painter.setPen(Qt.NoPen); painter.setBrush(QColor(color_hex))
        painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)
        label = index.data(Qt.DisplayRole) or ""
        painter.setPen(QColor(C_WHITE if is_sel else C_DIM))
        painter.setFont(QFont("Microsoft YaHei UI", 9))
        painter.drawText(QRect(rect.x() + 22, rect.y(), rect.width() - 28, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, label)
        painter.setPen(QColor("#2a2a3a"))
        painter.drawLine(rect.x() + 8, rect.bottom(), rect.x() + rect.width() - 8, rect.bottom())
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(TAB_W, TAB_ITEM_H)


# ═══════════════════════════════════════════════════════════════
# Settings Dialog
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    def __init__(self, parent, opacity, flash_mode, flash_border_w, on_change):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._cb = on_change
        self._flash_mode = flash_mode
        self._flash_border_w = flash_border_w
        self.setFixedSize(220, 160)
        self.setStyleSheet(f"background:{C_BG}; border:1px solid {C_BORDER};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)

        title = QLabel("设置")
        title.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        title.setStyleSheet(f"color:{C_WHITE}; border:none;")
        layout.addWidget(title)

        row1 = QHBoxLayout(); row1.setSpacing(4)
        lbl = QLabel("透明度"); lbl.setFont(QFont("Microsoft YaHei UI", 8))
        lbl.setStyleSheet(f"color:{C_DIM}; border:none;"); row1.addWidget(lbl)
        self._pct = QLabel(f"{int(opacity * 100)}%"); self._pct.setFixedWidth(36)
        self._pct.setFont(QFont("Microsoft YaHei UI", 8))
        self._pct.setStyleSheet(f"color:{C_DIM}; border:none;")
        self._pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s1 = QSlider(Qt.Horizontal); s1.setRange(20, 100)
        s1.setValue(int(opacity * 100)); s1.setFixedWidth(90)
        s1.valueChanged.connect(lambda v: self._on_opacity(v))
        s1.setStyleSheet(
            f"QSlider::groove:horizontal {{ height:4px; background:{C_BORDER}; border-radius:2px; border:none; }}"
            f"QSlider::handle:horizontal {{ background:{C_DIM}; width:10px; margin:-4px 0; border-radius:5px; border:none; }}")
        row1.addWidget(s1); row1.addWidget(self._pct)
        layout.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(4)
        lbl2 = QLabel("闪烁方式"); lbl2.setFont(QFont("Microsoft YaHei UI", 8))
        lbl2.setStyleSheet(f"color:{C_DIM}; border:none;"); row2.addWidget(lbl2)
        from PySide6.QtWidgets import QComboBox
        self._flash_combo = QComboBox()
        self._flash_combo.addItem("全背景", "overlay")
        self._flash_combo.addItem("边框", "border")
        self._flash_combo.setCurrentIndex(0 if flash_mode == "overlay" else 1)
        self._flash_combo.setFont(QFont("Microsoft YaHei UI", 8))
        self._flash_combo.setFixedWidth(70)
        self._flash_combo.setStyleSheet(
            f"QComboBox {{ color:{C_WHITE}; background:{C_TAB_ACTIVE}; border:1px solid {C_BORDER}; padding:2px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ color:{C_WHITE}; background:{C_TAB_ACTIVE}; selection-background:{C_BORDER}; }}")
        self._flash_combo.currentIndexChanged.connect(self._on_flash_mode)
        row2.addWidget(self._flash_combo); row2.addStretch()
        layout.addLayout(row2)

        row3 = QHBoxLayout(); row3.setSpacing(4)
        lbl3 = QLabel("边框宽度"); lbl3.setFont(QFont("Microsoft YaHei UI", 8))
        lbl3.setStyleSheet(f"color:{C_DIM}; border:none;"); row3.addWidget(lbl3)
        self._bw_pct = QLabel(f"{flash_border_w}px"); self._bw_pct.setFixedWidth(30)
        self._bw_pct.setFont(QFont("Microsoft YaHei UI", 8))
        self._bw_pct.setStyleSheet(f"color:{C_DIM}; border:none;")
        self._bw_pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        s3 = QSlider(Qt.Horizontal); s3.setRange(2, 20)
        s3.setValue(flash_border_w); s3.setFixedWidth(90)
        s3.valueChanged.connect(lambda v: self._on_border_w(v))
        s3.setStyleSheet(
            f"QSlider::groove:horizontal {{ height:4px; background:{C_BORDER}; border-radius:2px; border:none; }}"
            f"QSlider::handle:horizontal {{ background:{C_DIM}; width:10px; margin:-4px 0; border-radius:5px; border:none; }}")
        s3.setEnabled(flash_mode == "border"); self._bw_slider = s3
        row3.addWidget(s3); row3.addWidget(self._bw_pct)
        layout.addLayout(row3)

    def _on_opacity(self, val):
        self._pct.setText(f"{val}%")
        if self._cb: self._cb(opacity=val / 100.0)

    def _on_flash_mode(self, idx):
        self._flash_mode = "overlay" if idx == 0 else "border"
        self._bw_slider.setEnabled(self._flash_mode == "border")
        if self._cb: self._cb(flash_mode=self._flash_mode)

    def _on_border_w(self, val):
        self._flash_border_w = val
        self._bw_pct.setText(f"{val}px")
        if self._cb: self._cb(flash_border_w=val)

    def show_centered(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.center().x() - self.width() // 2
        y = screen.center().y() - self.height() // 2
        self.move(x, y)
        self.show()

    def event(self, event):
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.WindowDeactivate:
            self.close()
        return super().event(event)


# ═══════════════════════════════════════════════════════════════
# Main Window (full view only — compact is separate CompactWindow)
# ═══════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setMinimumSize(MIN_W, MIN_H)
        self.setMaximumHeight(MAX_H)

        self.manager = SessionManager()
        self.config = load_config()
        self._opacity = self.config["opacity"]
        self._tab_order = self.config.get("tabOrder", [])
        self._flash_mode = self.config.get("flashMode", "border")
        self._flash_border_w = self.config.get("flashBorderWidth", 6)
        self._selected_sid = ""
        self._last_statuses: dict[str, str] = {}
        self._user_resized = False
        self._user_resize_until = 0.0
        self._resizing = False
        self._compact_mode = True          # start compact
        self._transitioning = False        # lock during animation
        self._lock_expanded = False        # prevent collapse during settings
        self._saved_full_geo: QRect | None = None
        self._settings_dlg: SettingsDialog | None = None
        self._expand_deadline = 0.0        # cooldown after expand

        self.setWindowOpacity(self._opacity)
        self._init_full_geometry()
        self._build_ui()
        self.setVisible(False)  # start hidden; compact window is shown instead

        # ── Compact window (independent circular overlay) ──
        self._compact = CompactWindow()
        self._compact.set_opacity(self._opacity)
        self._compact.set_flash_settings(self._flash_mode, self._flash_border_w)
        self._compact.hovered.connect(self._on_compact_hovered)
        self._compact.unhovered.connect(self._on_compact_unhovered)

        # ── Tray ───────────────────────────────────────────
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("ClaudePulse")
        self._update_tray_icon("#6C7086")
        self.tray.activated.connect(self._on_tray_activate)
        self._build_tray_menu()
        self.tray.show()

        # ── Poll ───────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)

        # ── Hover check (backup for missed events) ─────────
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_timer.start(200)

        # ── Flash ──────────────────────────────────────────
        self._flash_count = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)
        self._flash_color = QColor(C_BORDER)

        # Show compact circle at startup
        self._compact.set_dock(None)
        self._place_compact_near_full()
        self._compact.show()

    # ── Tray menu ──────────────────────────────────────────

    def _build_tray_menu(self):
        m = QMenu()
        m.addAction("显示/隐藏", self.toggle_visible)
        m.addSeparator()
        m.addAction("设置", self._open_settings)
        m.addSeparator()
        m.addAction("退出", self.quit_app)
        self.tray.setContextMenu(m)

    # ── Screen helper ──────────────────────────────────────

    def _get_screen(self):
        """Return the QScreen for this window (multi-monitor aware)."""
        # Find screen that contains saved full-geometry center, or compact center
        if self._saved_full_geo and self._saved_full_geo.isValid():
            pt = self._saved_full_geo.center()
        elif self._compact.isVisible():
            pt = self._compact.full_circle_center()
        else:
            return QApplication.primaryScreen()
        for s in QApplication.screens():
            if s.availableGeometry().contains(pt):
                return s
        return QApplication.primaryScreen()

    # ── Geometry ───────────────────────────────────────────

    def _init_full_geometry(self):
        try:
            sd = os.path.expanduser("~/.claude/status/sessions")
            n = len([f for f in os.listdir(sd) if f.endswith(".json")])
        except Exception:
            n = 0
        n = max(n, 1)
        w = self.config.get("width", MIN_W)
        if not isinstance(w, int) or w < MIN_W:
            w = MIN_W
        h = min(TITLE_H + max(TAB_ITEM_H * n + 8, MIN_H - TITLE_H), MAX_H)
        h = max(h, 150)
        saved_h = self.config.get("height", 0)
        if isinstance(saved_h, int) and saved_h > h:
            h = saved_h
        x = self.config.get("x")
        y = self.config.get("y")
        if x is None:
            screen = self._get_screen().availableGeometry()
            x = screen.right() - w - 20
        if y is None:
            y = 40
        self._saved_full_geo = QRect(x, y, w, h)
        self.setGeometry(self._saved_full_geo)

    def _place_compact_near_full(self):
        """Position compact circle centered on saved full-window position."""
        if self._saved_full_geo and self._saved_full_geo.isValid():
            cx = self._saved_full_geo.center().x()
            cy = self._saved_full_geo.center().y()
        else:
            screen = self._get_screen().availableGeometry()
            cx = screen.right() - COMPACT_W - 20
            cy = 100
        geo = QRect(0, 0, COMPACT_W, COMPACT_H)
        geo.moveCenter(QPoint(cx, cy))
        self._compact.setGeometry(geo)

    # ── Build UI (full window) ─────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background:{C_BG};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_bar = TitleBar()
        self.title_bar.minimizeClicked.connect(self.hide_to_tray)
        self.title_bar.closeClicked.connect(self.quit_app)
        root.addWidget(self.title_bar)

        sep = QFrame(); sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C_BORDER}; border:none;")
        root.addWidget(sep)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background:{C_BORDER}; width:2px; }}")
        self.splitter.setHandleWidth(3)

        # Tab list
        self.tab_list = QListWidget()
        self.tab_list.setMinimumWidth(60)
        self.tab_list.setStyleSheet(
            f"QListWidget {{ background:{C_TAB_BG}; border:none; outline:none; }}"
            f"QListWidget::item {{ padding:0; border:none; }}")
        self.tab_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.tab_list.setDefaultDropAction(Qt.MoveAction)
        self.tab_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab_list.setSpacing(0)
        self._tab_delegate = TabDelegate(lambda sid: self.manager.effective_status(sid))
        self.tab_list.setItemDelegate(self._tab_delegate)
        self.tab_list.currentRowChanged.connect(self._on_tab_changed)
        self.tab_list.model().rowsMoved.connect(self._on_rows_moved)
        self.splitter.addWidget(self.tab_list)

        # Content area
        self.content = QWidget()
        self.content.setStyleSheet(f"background:{C_BG};")
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(14, 10, 14, 8); cl.setSpacing(6)

        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        self.status_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        cl.addWidget(self.status_lbl)

        self.tool_lbl = QLabel("")
        self.tool_lbl.setFont(QFont("Microsoft YaHei UI", 9))
        self.tool_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        cl.addWidget(self.tool_lbl)

        self.session_name_lbl = QLabel("")
        self.session_name_lbl.setFont(QFont("Microsoft YaHei UI", 8))
        self.session_name_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        cl.addWidget(self.session_name_lbl)

        cl.addStretch()
        self.splitter.addWidget(self.content)

        saved_sizes = self.config.get("splitterSizes", [TAB_W, 200])
        self.splitter.setSizes(saved_sizes)
        self.splitter.setStretchFactor(0, 1); self.splitter.setStretchFactor(1, 1)
        self.splitter.splitterMoved.connect(self._save_splitter)

        root.addWidget(self.splitter, 1)

        # Event filter for edge resize
        for w in [central, self.title_bar, self.tab_list, self.content,
                  self.splitter, self.tab_list.viewport(),
                  self.status_lbl, self.tool_lbl, self.session_name_lbl]:
            w.installEventFilter(self)
            w.setMouseTracking(True)
        self.setMouseTracking(True)

    # ── Edge resize ────────────────────────────────────────

    CURSORS = {
        "e": Qt.SizeHorCursor, "w": Qt.SizeHorCursor,
        "s": Qt.SizeVerCursor, "n": Qt.SizeVerCursor,
        "se": Qt.SizeFDiagCursor, "nw": Qt.SizeFDiagCursor,
        "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    }

    def _edge_test(self, global_pos):
        local = self.mapFromGlobal(global_pos)
        b = 8; x, y = local.x(), local.y()
        w, h = self.width(), self.height()
        if 0 <= y <= b and 0 <= x <= b:           return "nw"
        if 0 <= y <= b and w - b <= x <= w:       return "ne"
        if h - b <= y <= h and 0 <= x <= b:       return "sw"
        if h - b <= y <= h and w - b <= x <= w:   return "se"
        if 0 <= y <= b:                           return "n"
        if h - b <= y <= h:                       return "s"
        if 0 <= x <= b:                           return "w"
        if w - b <= x <= w:                       return "e"
        return None

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        t = event.type()
        if t == QEvent.MouseMove:
            gpos = (event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition') else event.globalPos())
            if self._resizing:
                new_ev = QMouseEvent(QEvent.MouseMove, self.mapFromGlobal(gpos), gpos,
                                     Qt.NoButton, event.buttons(), event.modifiers())
                self.mouseMoveEvent(new_ev)
            else:
                d = self._edge_test(gpos)
                self.setCursor(self.CURSORS.get(d, Qt.ArrowCursor))
        elif t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            gpos = (event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition') else event.globalPos())
            d = self._edge_test(gpos)
            if d:
                self._resizing = True; self._resize_dir = d
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = gpos
                return True
        elif t == QEvent.MouseButtonRelease and self._resizing:
            if event.button() == Qt.LeftButton:
                self._resizing = False; self.setCursor(Qt.ArrowCursor)
                self._save_full_config()
                return True
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geo); d = self._resize_dir
            if "e" in d: geo.setRight(max(geo.left() + MIN_W, geo.right() + delta.x()))
            if "w" in d: geo.setLeft(min(geo.right() - MIN_W, geo.left() + delta.x()))
            if "s" in d: geo.setBottom(max(geo.top() + MIN_H, geo.bottom() + delta.y()))
            if "n" in d: geo.setTop(min(geo.bottom() - MIN_H, geo.top() + delta.y()))
            if geo != self.geometry():
                self._user_resized = True
                self._user_resize_until = time.time() + 5
                self.setGeometry(geo)
            return
        super().mouseMoveEvent(event)

    # ── Compact ↔ Full coordination ────────────────────────

    def _on_compact_hovered(self):
        """Compact circle hovered → cross-fade to full window."""
        if self._transitioning or self._lock_expanded:
            return
        self._expand()

    def _on_compact_unhovered(self):
        """Compact circle unhovered — no action.
        The hover timer handles full→compact."""
        pass

    def _check_hover(self):
        """Periodic cursor-position check as fallback for missed events."""
        if self._transitioning or self._lock_expanded:
            return
        gpos = QCursor.pos()
        on_compact = (self._compact.isVisible() and
                      self._compact.rect().contains(
                          self._compact.mapFromGlobal(gpos)))
        on_full = (self.isVisible() and
                   self.rect().contains(self.mapFromGlobal(gpos)))

        if on_compact and self._compact_mode:
            self._expand()
        elif not on_full and not on_compact and not self._compact_mode:
            if time.time() > self._expand_deadline:
                self._collapse()

    # ── Mask-expand / mask-collapse animations ──────────────

    def _make_mask_anim(self, duration, start_val, end_val, easing, mask_fn):
        """Create a QVariantAnimation that updates the window mask each frame.
        Mask aliasing (1-bit) is invisible during fast motion."""
        from PySide6.QtCore import QVariantAnimation
        anim = QVariantAnimation()
        anim.setDuration(duration)
        anim.setStartValue(start_val)
        anim.setEndValue(end_val)
        anim.setEasingCurve(easing)
        anim.valueChanged.connect(mask_fn)
        return anim

    def _expand(self):
        """Mask-animate from circle → full rectangle.
        Hides the compact circle, shows full window behind an expanding mask."""
        if self._transitioning or not self._compact_mode:
            return
        self._transitioning = True
        self._compact_mode = False

        # Position full window centered on the full-circle center
        circle_center = self._compact.full_circle_center()
        if self._saved_full_geo and self._saved_full_geo.isValid():
            target = QRect(self._saved_full_geo)
        else:
            target = QRect(self.geometry())
        target.moveCenter(circle_center)
        # Clamp to screen
        screen = self._get_screen().availableGeometry()
        if target.left() < screen.left():    target.moveLeft(screen.left())
        if target.right() > screen.right():  target.moveRight(screen.right())
        if target.top() < screen.top():      target.moveTop(screen.top())
        if target.bottom() > screen.bottom(): target.moveBottom(screen.bottom())
        self.setGeometry(target)
        self._compact.hide()

        # Circle center in window-local coords
        cx = target.width() // 2
        cy = target.height() // 2
        r0 = COMPACT_W // 2  # compact circle radius

        def update_mask(t):
            """t: 0=circle → 1=full rectangle.
            Interpolates ellipse from circle size to window-filling size."""
            w = self.width(); h = self.height()
            ew = r0 * 2 + (w - r0 * 2) * t
            eh = r0 * 2 + (h - r0 * 2) * t
            path = QPainterPath()
            path.addEllipse(QRectF(cx - ew / 2, cy - eh / 2, ew, eh))
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        update_mask(0.0)
        self.show()
        self.raise_()
        self.activateWindow()

        anim = self._make_mask_anim(100, 0.0, 1.0, QEasingCurve.OutCubic, update_mask)
        anim.finished.connect(self._on_expand_done)
        anim.start()
        self._trans_anim = anim

    def _on_expand_done(self):
        self.clearMask()
        self._transitioning = False
        self._saved_full_geo = QRect(self.geometry())
        self._expand_deadline = time.time() + 0.5
        self._refresh_content()
        self._rebuild_tabs()

    def _detect_dock_edge(self):
        """Return None, "left", "right", or "top" if full window
        touches a screen edge (within 12px threshold)."""
        if not self._saved_full_geo:
            return None
        screen = self._get_screen().availableGeometry()
        g = self._saved_full_geo
        th = 12
        if abs(g.left() - screen.left()) <= th:   return "left"
        if abs(g.right() - screen.right()) <= th:  return "right"
        if abs(g.top() - screen.top()) <= th:      return "top"
        return None

    def _collapse(self):
        """Mask-animate full → circle, then show half/full circle at dock edge."""
        if self._transitioning or self._compact_mode:
            return
        self._transitioning = True
        self._saved_full_geo = QRect(self.geometry())

        cx = self.width() // 2
        cy = self.height() // 2
        r0 = COMPACT_W // 2

        def update_mask(t):
            w = self.width(); h = self.height()
            ew = r0 * 2 + (w - r0 * 2) * t
            eh = r0 * 2 + (h - r0 * 2) * t
            path = QPainterPath()
            path.addEllipse(QRectF(cx - ew / 2, cy - eh / 2, ew, eh))
            self.setMask(QRegion(path.toFillPolygon().toPolygon()))

        update_mask(1.0)
        anim = self._make_mask_anim(100, 1.0, 0.0, QEasingCurve.InCubic, update_mask)
        anim.finished.connect(self._on_collapse_done)
        anim.start()
        self._trans_anim = anim

    def _on_collapse_done(self):
        self.hide()
        self.clearMask()

        # Detect dock edge and position half/full circle
        edge = self._detect_dock_edge()
        self._compact.set_dock(edge)
        screen = self._get_screen().availableGeometry()
        full_center = self._saved_full_geo.center()

        if edge == "left":
            x = screen.left()
            y = max(screen.top(), min(screen.bottom() - COMPACT_H, full_center.y() - COMPACT_H // 2))
        elif edge == "right":
            x = screen.right() - COMPACT_W // 2
            y = max(screen.top(), min(screen.bottom() - COMPACT_H, full_center.y() - COMPACT_H // 2))
        elif edge == "top":
            x = max(screen.left(), min(screen.right() - COMPACT_W, full_center.x() - COMPACT_W // 2))
            y = screen.top()
        else:
            x = full_center.x() - COMPACT_W // 2
            y = full_center.y() - COMPACT_H // 2

        self._compact.move(x, y)
        self._compact.show()

        self._transitioning = False
        self._compact_mode = True
        self._refresh_content()

    def _show_full_direct(self):
        """Show full window immediately, no animation (used by settings)."""
        if self.isVisible():
            return
        self._compact.hide()
        self._compact_mode = False
        self.clearMask()
        # Position centered on circle center, clamp to screen
        circle_ctr = self._compact.full_circle_center()
        if self._saved_full_geo and self._saved_full_geo.isValid():
            target = QRect(self._saved_full_geo)
        else:
            target = QRect(self.geometry())
        target.moveCenter(circle_ctr)
        screen = self._get_screen().availableGeometry()
        if target.left() < screen.left():    target.moveLeft(screen.left())
        if target.right() > screen.right():  target.moveRight(screen.right())
        if target.top() < screen.top():      target.moveTop(screen.top())
        self.setGeometry(target)
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_content()
        self._rebuild_tabs()

    # ── Auto-height ────────────────────────────────────────

    def _auto_height(self):
        if self._compact_mode or not self.isVisible():
            return
        if self._user_resized and time.time() < self._user_resize_until:
            n = max(len(self.manager.sessions), 1)
            if TITLE_H + 1 + min(max(TAB_ITEM_H * n + 8, MIN_H - TITLE_H),
                                 MAX_H - TITLE_H) <= self.height():
                return
            self._user_resized = False
        n = max(len(self.manager.sessions), 1)
        body_h = max(TAB_ITEM_H * n + 8, MIN_H - TITLE_H - 1)
        body_h = min(body_h, MAX_H - TITLE_H - 1)
        target_h = TITLE_H + 1 + body_h
        if target_h != self.height():
            self.resize(self.width(), target_h)

    # ── Tray ────────────────────────────────────────────────

    def _update_tray_icon(self, color_hex):
        try:
            from PySide6.QtGui import QPixmap
            pm = QPixmap(16, 16); pm.fill(Qt.transparent)
            p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing)
            p.setBrush(QColor(color_hex)); p.setPen(Qt.NoPen)
            p.drawEllipse(2, 2, 12, 12); p.end()
            self.tray.setIcon(QIcon(pm))
        except Exception:
            pass

    def hide_to_tray(self):
        self._compact.hide()
        self.hide()

    def toggle_visible(self):
        if self._compact.isVisible() or self.isVisible():
            self._compact.hide()
            self.hide()
        else:
            self._place_compact_near_full()
            self._compact.show()

    def _on_tray_activate(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visible()

    def quit_app(self):
        self._compact.hide()
        self.tray.hide()
        QApplication.quit()

    # ── Settings ────────────────────────────────────────────

    def _open_settings(self):
        if self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.close()
            self._settings_dlg = None
            self._lock_expanded = False
            return
        self._lock_expanded = True
        self._show_full_direct()
        self._settings_dlg = SettingsDialog(
            self, self._opacity, self._flash_mode, self._flash_border_w,
            self._on_settings_changed)
        self._settings_dlg.finished.connect(self._on_settings_closed)
        self._settings_dlg.show_centered()

    def _on_settings_closed(self):
        self._settings_dlg = None
        self._lock_expanded = False

    def _save_splitter(self, pos, index):
        self._save_full_config()

    def _save_full_config(self):
        if self._compact_mode or not self.isVisible():
            return
        geo = self.geometry()
        save_config(self._opacity, geo.x(), geo.y(), self._tab_order,
                    geo.width(), geo.height(), self.splitter.sizes(),
                    flashMode=self._flash_mode,
                    flashBorderWidth=self._flash_border_w)

    def _on_settings_changed(self, opacity=None, flash_mode=None,
                             flash_border_w=None):
        if opacity is not None:
            self._opacity = opacity
            self.setWindowOpacity(opacity)
            self._compact.set_opacity(opacity)
        if flash_mode is not None:
            self._flash_mode = flash_mode
            self._compact.set_flash_settings(flash_mode, self._flash_border_w)
        if flash_border_w is not None:
            self._flash_border_w = flash_border_w
            self._compact.set_flash_settings(self._flash_mode, flash_border_w)
        self._save_full_config()

    # ── Flash ───────────────────────────────────────────────

    def _start_flash(self, color_hex):
        self._flash_color = QColor(color_hex)
        self._flash_count = 0
        self._flash_timer.start(FLASH_DURATION)

    def _flash_tick(self):
        self._flash_count += 1
        if self._flash_count >= 7:
            self._flash_timer.stop()
            if self._flash_mode == "overlay":
                if hasattr(self, '_flash_overlay') and self._flash_overlay:
                    self._flash_overlay.hide()
            elif self._flash_mode == "border":
                self.setStyleSheet("")
            return
        if self._flash_mode == "overlay":
            self._flash_tick_overlay()
        elif self._flash_mode == "border":
            self._flash_tick_border()

    def _flash_tick_overlay(self):
        if not hasattr(self, '_flash_overlay') or not self._flash_overlay:
            self._flash_overlay = QWidget(self)
            self._flash_overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        if self._flash_count % 2 == 1:
            self._flash_overlay.setStyleSheet(f"background:{self._flash_color.name()};")
            self._flash_overlay.setGeometry(0, 0, self.width(), self.height())
            self._flash_overlay.show(); self._flash_overlay.raise_()
        else:
            self._flash_overlay.hide()

    def _flash_border_strips(self):
        if hasattr(self, '_border_strips'):
            return
        self._border_strips = []
        for _ in range(4):
            f = QFrame(self); f.setAttribute(Qt.WA_TransparentForMouseEvents)
            f.hide(); self._border_strips.append(f)

    def _flash_tick_border(self):
        self._flash_border_strips()
        top, bottom, left, right = self._border_strips
        if self._flash_count % 2 == 1:
            w = self._flash_border_w; c = self._flash_color.name()
            wh, ht = self.width(), self.height()
            ss = f"background:{c}; border:none;"
            top.setStyleSheet(ss);    top.setGeometry(0, 0, wh, w); top.show()
            bottom.setStyleSheet(ss); bottom.setGeometry(0, ht - w, wh, w); bottom.show()
            left.setStyleSheet(ss);   left.setGeometry(0, 0, w, ht); left.show()
            right.setStyleSheet(ss);  right.setGeometry(wh - w, 0, w, ht); right.show()
            top.raise_(); bottom.raise_(); left.raise_(); right.raise_()
        else:
            for s in self._border_strips:
                s.hide()

    # ── Tab interactions ────────────────────────────────────

    def _on_tab_changed(self, row):
        if row < 0 or row >= self.tab_list.count():
            return
        item = self.tab_list.item(row)
        sid = item.data(Qt.UserRole)
        if sid and sid != self._selected_sid:
            self._selected_sid = sid
            self._refresh_content()

    def _on_rows_moved(self, parent, start, end, dest, row):
        sids = [self.tab_list.item(i).data(Qt.UserRole)
                for i in range(self.tab_list.count())]
        self._tab_order = sids
        self._save_full_config()

    # ── Refresh ─────────────────────────────────────────────

    def _rebuild_tabs(self):
        self.tab_list.blockSignals(True)
        sessions = self.manager.ordered_sessions(self._tab_order)
        old_sel = self._selected_sid
        new_rows = {s.session_id: i for i, s in enumerate(sessions)}
        new_sel_row = new_rows.get(old_sel, 0) if sessions else -1
        self.tab_list.clear()
        for s in sessions:
            item = QListWidgetItem(s.display_name or s.project or s.session_id[:8])
            item.setData(Qt.UserRole, s.session_id)
            item.setSizeHint(QSize(TAB_W, TAB_ITEM_H))
            self.tab_list.addItem(item)
        if sessions:
            self.tab_list.setCurrentRow(new_sel_row if new_sel_row >= 0 else 0)
            if self._selected_sid not in new_rows:
                self._selected_sid = self.tab_list.currentItem().data(Qt.UserRole)
        else:
            self._selected_sid = ""
        self.tab_list.blockSignals(False)

    def _refresh_content(self):
        sid = self._selected_sid
        s = self.manager.sessions.get(sid)
        eff = self.manager.effective_status(sid) if s else "ended"
        color_hex, label = STATUS_MAP.get(eff, ("#9ca3af", "未知"))
        session_name = s.display_name if s else ""

        # Full view
        self.status_lbl.setText(f"● {label}")
        self.status_lbl.setStyleSheet(f"color:{color_hex}; background:transparent; font-weight:bold;")
        self.tool_lbl.setText(s.tool if s else "")
        self.session_name_lbl.setText(session_name)

        # Compact circle
        self._compact.set_status(color_hex, label)
        self._compact.set_session_name(session_name)

    # ── Poll ────────────────────────────────────────────────

    def _poll(self):
        try:
            changed, removed = self.manager.load_all()
        except Exception:
            changed, removed = [], []

        now = time.time()

        if not self._selected_sid and self.manager.sessions:
            active_sid = None
            try:
                with open(CURRENT_FILE, "r") as f:
                    active_sid = json.load(f).get("active_session", "")
            except Exception:
                pass
            sessions = self.manager.ordered_sessions(self._tab_order)
            if active_sid and active_sid in self.manager.sessions:
                self._selected_sid = active_sid
            elif sessions:
                self._selected_sid = sessions[0].session_id

        for sid in changed:
            s = self.manager.sessions.get(sid)
            if not s: continue
            old = self._last_statuses.get(sid, "")
            if old != s.status:
                self._selected_sid = sid
                self._refresh_content()
                if not self._compact_mode:
                    self._rebuild_tabs()
                col, _ = STATUS_MAP.get(s.status, ("#9ca3af", ""))
                self._start_flash(col)
                self._compact.start_flash(col)
                self._update_tray_icon(col)
            self._last_statuses[sid] = s.status
            if s.status == "starting" and s.starting_since == 0:
                s.starting_since = now

        for sid in removed:
            self._last_statuses.pop(sid, None)

        if self.manager.auto_transition_starting():
            self._refresh_content()
            if not self._compact_mode:
                self._rebuild_tabs()

        if changed or removed or not self._last_statuses:
            for sid in self.manager.get_stale_sessions():
                s = self.manager.sessions.get(sid)
                if s:
                    s.status = "ended"; s.ended_at = now
                    self._last_statuses[sid] = "ended"

        for sid in self.manager.get_expired_ended():
            self.manager.remove_session(sid)
            self._last_statuses.pop(sid, None)
            if sid == self._selected_sid:
                self._selected_sid = ""

        if not self.manager.sessions:
            self.quit_app()
            return

        if self._selected_sid not in self.manager.sessions:
            sl = self.manager.ordered_sessions(self._tab_order)
            if sl:
                self._selected_sid = sl[0].session_id

        for sid in list(self.manager.sessions.keys()):
            self.manager.refresh_display_name(sid)

        if not self._compact_mode:
            self._rebuild_tabs()
        self._refresh_content()
        self._auto_height()

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()

    def leaveEvent(self, event):
        """Full-window leave → collapse to compact (debounced by _check_hover)."""
        super().leaveEvent(event)


# ═══════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════

def _check_running():
    try:
        with open(LOCK_FILE, "r") as f:
            old_pid = f.read().strip()
        import subprocess
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {old_pid}", "/NH", "/FO", "CSV"],
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
            if hasattr(subprocess, "CREATE_NO_WINDOW") else 0).decode(
                "utf-8", errors="ignore")
        return old_pid in out
    except Exception:
        return False

def _write_lock():
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def _remove_lock():
    try:
        os.remove(LOCK_FILE)
    except Exception:
        pass

def main():
    if _check_running():
        print("ClaudePulse is already running.", file=sys.stderr)
        sys.exit(0)
    os.makedirs(os.path.expanduser("~/.claude/status/sessions"), exist_ok=True)
    _write_lock()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    w = MainWindow()
    try:
        app.exec()
    finally:
        _remove_lock()

if __name__ == "__main__":
    main()
