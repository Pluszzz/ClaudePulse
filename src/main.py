"""ClaudePulse — Qt6 multi-session status monitor for Claude Code."""
import json
import os
import sys
import time
import webbrowser
from pathlib import Path

from PySide6.QtCore import (
    Qt, QTimer, QPoint, QSize, QPropertyAnimation, QEasingCurve,
    QRect, Signal
)
from PySide6.QtGui import (
    QColor, QPainter, QBrush, QPen, QFont, QMouseEvent,
    QAction, QIcon
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QDialog,
    QSystemTrayIcon, QMenu, QStyledItemDelegate, QStyle,
    QStyleOption, QSlider, QPushButton, QFrame, QSpacerItem,
    QSizePolicy, QAbstractItemView, QSplitter
)

from session_manager import SessionManager, STATUS_MAP, STARTING_TIMEOUT, ENDED_RETENTION

# ── Constants ───────────────────────────────────────────────
CONFIG_FILE = os.path.expanduser("~/.claude/status/window-config.json")
CURRENT_FILE = os.path.expanduser("~/.claude/status/current.json")
LOCK_FILE = os.path.expanduser("~/.claude/status/window.lock")
GITHUB_URL = "https://github.com/Pluszzz/ClaudePulse"
POLL_MS = 500
FLASH_DURATION = 200  # ms per flash tick

TITLE_H = 28
TAB_W = 120
TAB_ITEM_H = 30
MIN_W = 320
MIN_H = 140
MAX_H = 600
DEFAULT_OPACITY = 0.75

C_BG       = "#1e1e2e"
C_TAB_BG   = "#181825"
C_TAB_ACTIVE = "#2a2a3a"
C_TITLE_BG = "#181825"
C_WHITE    = "#ffffff"
C_DIM      = "#a6adc8"
C_MUTED    = "#585b70"
C_BORDER   = "#45475a"
C_HOVER    = "#f87171"


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def load_config():
    defaults = {"opacity": DEFAULT_OPACITY, "x": None, "y": None, "tabOrder": []}
    try:
        with open(CONFIG_FILE, "r") as f:
            return {**defaults, **json.load(f)}
    except Exception:
        return defaults

def save_config(opacity, x, y, tabOrder, width=None, height=None, splitterSizes=None):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        data = {"opacity": opacity, "x": x, "y": y, "tabOrder": tabOrder}
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        if splitterSizes is not None:
            data["splitterSizes"] = splitterSizes
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


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

        # ClaudePulse label
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

        # Minimize button
        self.min_btn = self._make_btn("─", 9)
        self.min_btn.clicked.connect(self.minimizeClicked.emit)
        self.min_btn.setFixedSize(24, 24)
        layout.addWidget(self.min_btn)

        # Close button
        self.close_btn = self._make_btn("×", 11)
        self.close_btn.clicked.connect(self.closeClicked.emit)
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setStyleSheet(
            f"QPushButton {{ color:{C_DIM}; background:transparent; border:none; font-weight:bold; font-size:14px; }}"
            f"QPushButton:hover {{ color:{C_HOVER}; }}")
        layout.addWidget(self.close_btn)

    def _make_btn(self, text, size):
        btn = QPushButton(text)
        btn.setFont(QFont("Microsoft YaHei UI", size, QFont.Bold))
        btn.setStyleSheet(
            f"QPushButton {{ color:{C_DIM}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ color:{C_WHITE}; }}")
        btn.setCursor(Qt.PointingHandCursor)
        return btn

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
# Tab Item Delegate (custom paint for colored dot)
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

        # background
        bg = QColor(C_TAB_ACTIVE) if is_sel else QColor(C_TAB_BG)
        painter.fillRect(rect, bg)

        # left accent bar
        if is_sel:
            painter.fillRect(QRect(rect.x(), rect.y() + 4, 2, rect.height() - 8),
                             QColor(color_hex))

        # dot
        dot_r = 5
        cx = rect.x() + 10
        cy = rect.y() + rect.height() // 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color_hex))
        painter.drawEllipse(QPoint(cx, cy), dot_r, dot_r)

        # text
        label = index.data(Qt.DisplayRole) or ""
        txt_color = C_WHITE if is_sel else C_DIM
        painter.setPen(QColor(txt_color))
        font = QFont("Microsoft YaHei UI", 9)
        painter.setFont(font)
        text_rect = QRect(rect.x() + 22, rect.y(), rect.width() - 28, rect.height())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, label)

        # separator
        painter.setPen(QColor("#2a2a3a"))
        painter.drawLine(rect.x() + 8, rect.bottom(), rect.x() + rect.width() - 8,
                         rect.bottom())

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(TAB_W, TAB_ITEM_H)


# ═══════════════════════════════════════════════════════════════
# Settings Dialog
# ═══════════════════════════════════════════════════════════════

class SettingsDialog(QDialog):
    def __init__(self, parent, opacity, on_change):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self._cb = on_change
        self.setFixedSize(200, 80)
        self.setStyleSheet(f"background:{C_BG}; border:1px solid {C_BORDER};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)

        title = QLabel("设置")
        title.setFont(QFont("Microsoft YaHei UI", 10, QFont.Bold))
        title.setStyleSheet(f"color:{C_WHITE}; border:none;")
        layout.addWidget(title)

        row = QHBoxLayout()
        lbl = QLabel("透明度")
        lbl.setFont(QFont("Microsoft YaHei UI", 8))
        lbl.setStyleSheet(f"color:{C_DIM}; border:none;")
        row.addWidget(lbl)

        self._pct = QLabel(f"{int(opacity * 100)}%")
        self._pct.setFont(QFont("Microsoft YaHei UI", 8))
        self._pct.setStyleSheet(f"color:{C_DIM}; border:none;")
        self._pct.setFixedWidth(36)
        self._pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(20, 100)
        self._slider.setValue(int(opacity * 100))
        self._slider.setFixedWidth(100)
        self._slider.valueChanged.connect(self._on_slide)
        self._slider.setStyleSheet(
            f"QSlider::groove:horizontal {{ height:4px; background:{C_BORDER}; border-radius:2px; border:none; }}"
            f"QSlider::handle:horizontal {{ background:{C_DIM}; width:10px; margin:-4px 0; border-radius:5px; border:none; }}"
        )

        row.addWidget(self._slider)
        row.addWidget(self._pct)
        layout.addLayout(row)

    def _on_slide(self, val):
        self._pct.setText(f"{val}%")
        if self._cb:
            self._cb(val / 100.0)

    def show_at(self, parent_pos, parent_size):
        x = parent_pos.x() + parent_size.width() - 220
        y = parent_pos.y() + parent_size.height() + 4
        self.move(x, y)
        self.show()

    def event(self, event):
        """Close dialog when focus is lost (clicked outside)."""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.WindowDeactivate:
            self.close()
        return super().event(event)


# ═══════════════════════════════════════════════════════════════
# Main Window
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
        self._selected_sid = ""
        self._last_statuses: dict[str, str] = {}
        self._user_resized = False
        self._user_resize_until = 0.0
        self._resizing = False
        self._settings_dlg: SettingsDialog | None = None

        self.setWindowOpacity(self._opacity)
        self._init_geometry()
        self._build_ui()

        # Tray
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("ClaudePulse")
        self._update_tray_icon("#6C7086")
        self.tray.activated.connect(self._on_tray_activate)
        tray_menu = QMenu()
        tray_menu.addAction("显示/隐藏", self.toggle_visible)
        tray_menu.addSeparator()
        tray_menu.addAction("退出", self.quit_app)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        # Timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(POLL_MS)

        # Flash
        self._flash_count = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_tick)
        self._flash_color = QColor(C_BORDER)

    # ── Geometry ────────────────────────────────────────────

    def _init_geometry(self):
        try:
            sd = os.path.expanduser("~/.claude/status/sessions")
            n = len([f for f in os.listdir(sd) if f.endswith(".json")])
        except Exception:
            n = 0
        n = max(n, 1)
        # Use saved width or default
        w = self.config.get("width", MIN_W)
        if not isinstance(w, int) or w < MIN_W:
            w = MIN_W
        h = min(TITLE_H + max(TAB_ITEM_H * n + 8, MIN_H - TITLE_H), MAX_H)
        h = max(h, 150)
        # Use saved height if taller (user may have manually resized)
        saved_h = self.config.get("height", 0)
        if isinstance(saved_h, int) and saved_h > h:
            h = saved_h
        x = self.config.get("x")
        y = self.config.get("y")
        if x is None:
            screen = QApplication.primaryScreen().availableGeometry()
            x = screen.right() - w - 20
        if y is None:
            y = 40
        self.setGeometry(x, y, w, h)

    # ── Build UI ────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background:{C_BG};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar()
        self.title_bar.minimizeClicked.connect(self.hide_to_tray)
        self.title_bar.closeClicked.connect(self.quit_app)
        root.addWidget(self.title_bar)

        # Separator
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{C_BORDER}; border:none;")
        root.addWidget(sep)

        # Body with splitter
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setStyleSheet(f"QSplitter::handle {{ background:{C_BORDER}; width:2px; }}")
        self.splitter.setHandleWidth(3)

        # Tab list
        self.tab_list = QListWidget()
        self.tab_list.setMinimumWidth(60)
        self.tab_list.setStyleSheet(
            f"QListWidget {{ background:{C_TAB_BG}; border:none; outline:none; }}"
            f"QListWidget::item {{ padding:0; border:none; }}"
        )
        self.tab_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tab_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.tab_list.setDefaultDropAction(Qt.MoveAction)
        self.tab_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tab_list.setSpacing(0)
        self._tab_delegate = TabDelegate(
            lambda sid: self.manager.effective_status(sid))
        self.tab_list.setItemDelegate(self._tab_delegate)
        self.tab_list.currentRowChanged.connect(self._on_tab_changed)
        self.tab_list.model().rowsMoved.connect(self._on_rows_moved)
        self.splitter.addWidget(self.tab_list)

        # Content area
        self.content = QWidget()
        self.content.setStyleSheet(f"background:{C_BG};")
        cl = QVBoxLayout(self.content)
        cl.setContentsMargins(14, 14, 14, 8)
        cl.setSpacing(6)

        self.status_lbl = QLabel("")
        self.status_lbl.setFont(QFont("Microsoft YaHei UI", 12, QFont.Bold))
        self.status_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        cl.addWidget(self.status_lbl)

        self.tool_lbl = QLabel("")
        self.tool_lbl.setFont(QFont("Microsoft YaHei UI", 9))
        self.tool_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
        cl.addWidget(self.tool_lbl)

        self.cwd_lbl = QLabel("")
        self.cwd_lbl.setFont(QFont("Microsoft YaHei UI", 7))
        self.cwd_lbl.setStyleSheet(f"color:{C_MUTED}; background:transparent;")
        cl.addWidget(self.cwd_lbl)

        cl.addStretch()

        # Gear button
        gear_layout = QHBoxLayout()
        gear_layout.addStretch()
        self.gear_btn = QPushButton("⚙")
        self.gear_btn.setFont(QFont("Segoe UI Symbol", 10))
        self.gear_btn.setFixedSize(24, 24)
        self.gear_btn.setCursor(Qt.PointingHandCursor)
        self.gear_btn.setStyleSheet(
            f"QPushButton {{ color:{C_MUTED}; background:transparent; border:none; }}"
            f"QPushButton:hover {{ color:{C_WHITE}; }}")
        self.gear_btn.clicked.connect(self._toggle_settings)
        gear_layout.addWidget(self.gear_btn)
        cl.addLayout(gear_layout)

        self.splitter.addWidget(self.content)
        # Restore saved splitter ratio or use defaults
        saved_sizes = self.config.get("splitterSizes", [TAB_W, 200])
        self.splitter.setSizes(saved_sizes)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        # Save splitter sizes when moved
        self.splitter.splitterMoved.connect(self._save_splitter)

        root.addWidget(self.splitter, 1)

        # Install event filter on all child widgets to catch edge cursor
        for w in [central, self.title_bar, self.tab_list, self.content,
                  self.splitter, self.tab_list.viewport(), self.status_lbl,
                  self.tool_lbl, self.cwd_lbl, self.gear_btn]:
            w.installEventFilter(self)
            w.setMouseTracking(True)
        self.setMouseTracking(True)

    # ── Edge resize ─────────────────────────────────────────
    # Uses eventFilter to catch mouse moves on ALL child widgets,
    # not just the MainWindow itself.

    CURSORS = {
        "e": Qt.SizeHorCursor,  "w": Qt.SizeHorCursor,
        "s": Qt.SizeVerCursor,  "n": Qt.SizeVerCursor,
        "se": Qt.SizeFDiagCursor, "nw": Qt.SizeFDiagCursor,
        "ne": Qt.SizeBDiagCursor, "sw": Qt.SizeBDiagCursor,
    }

    def _edge_test(self, global_pos):
        """Returns resize direction string or None.
        Uses global screen coords — works regardless of which child
        widget the mouse is over."""
        local = self.mapFromGlobal(global_pos)
        b = 8
        x, y = local.x(), local.y()
        w, h = self.width(), self.height()
        nL = 0 <= x <= b; nR = w - b <= x <= w
        nT = 0 <= y <= b; nB = h - b <= y <= h
        if nT and nL: return "nw"
        if nT and nR: return "ne"
        if nB and nL: return "sw"
        if nB and nR: return "se"
        if nT: return "n"
        if nB: return "s"
        if nL: return "w"
        if nR: return "e"
        return None

    def eventFilter(self, obj, event):
        """Intercept mouse events from ALL child widgets."""
        from PySide6.QtCore import QEvent
        t = event.type()

        if t == QEvent.MouseMove:
            gpos = (event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition')
                    else event.globalPos())
            if self._resizing:
                # Forward to mouseMoveEvent for actual resize
                new_event = QMouseEvent(
                    QEvent.MouseMove,
                    self.mapFromGlobal(gpos), gpos,
                    Qt.NoButton, event.buttons(), event.modifiers())
                self.mouseMoveEvent(new_event)
            else:
                d = self._edge_test(gpos)
                self.setCursor(self.CURSORS.get(d, Qt.ArrowCursor))

        elif t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            gpos = (event.globalPosition().toPoint()
                    if hasattr(event, 'globalPosition')
                    else event.globalPos())
            d = self._edge_test(gpos)
            if d:
                self._resizing = True
                self._resize_dir = d
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = gpos
                return True

        elif t == QEvent.MouseButtonRelease and self._resizing:
            if event.button() == Qt.LeftButton:
                self._resizing = False
                self.setCursor(Qt.ArrowCursor)
                self._save_full_config()
                return True

        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Only used while actively resizing (dragging an edge)."""
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._resize_start_pos
            geo = QRect(self._resize_start_geo)
            d = self._resize_dir
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

    # ── Resize window auto-height ───────────────────────────

    def _auto_height(self):
        if self._user_resized and time.time() < self._user_resize_until:
            n = max(len(self.manager.sessions), 1)
            needed = TITLE_H + 1 + min(
                max(TAB_ITEM_H * n + 8, MIN_H - TITLE_H), MAX_H - TITLE_H)
            if needed <= self.height():
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
            pm = QPixmap(16, 16)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor(color_hex))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(2, 2, 12, 12)
            painter.end()
            self.tray.setIcon(QIcon(pm))
        except Exception:
            pass

    def hide_to_tray(self):
        self.hide()

    def toggle_visible(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def _on_tray_activate(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.toggle_visible()

    def quit_app(self):
        self.tray.hide()
        QApplication.quit()

    # ── Settings ────────────────────────────────────────────

    def _toggle_settings(self):
        if self._settings_dlg and self._settings_dlg.isVisible():
            self._settings_dlg.close()
            self._settings_dlg = None
            return
        self._settings_dlg = SettingsDialog(self, self._opacity, self._on_opacity)
        self._settings_dlg.show_at(self.pos(), self.size())

    def _save_splitter(self, pos, index):
        self._save_full_config()

    def _save_full_config(self):
        save_config(
            self._opacity, self.x(), self.y(), self._tab_order,
            self.width(), self.height(), self.splitter.sizes())

    def _on_opacity(self, val):
        self._opacity = val
        self.setWindowOpacity(val)
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
            self.setStyleSheet("")
            return
        if self._flash_count % 2 == 1:
            self.setStyleSheet(
                f"QMainWindow {{ border:2px solid {self._flash_color.name()}; }}")
        else:
            self.setStyleSheet("")

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
        """Tab drag-reorder: sync tab_order list."""
        sids = []
        for i in range(self.tab_list.count()):
            item = self.tab_list.item(i)
            sids.append(item.data(Qt.UserRole))
        self._tab_order = sids
        self._save_full_config()

    # ── Refresh ─────────────────────────────────────────────

    def _rebuild_tabs(self):
        self.tab_list.blockSignals(True)
        sessions = self.manager.ordered_sessions(self._tab_order)
        old_sel = self._selected_sid

        # Preserve current row if possible
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
        if not s:
            self.status_lbl.setText("")
            self.status_lbl.setStyleSheet(f"color:{C_DIM}; background:transparent;")
            self.tool_lbl.setText(""); self.cwd_lbl.setText("")
            return
        eff = self.manager.effective_status(sid)
        color_hex, label = STATUS_MAP.get(eff, ("#9ca3af", "未知"))
        self.status_lbl.setText(f"● {label}")
        self.status_lbl.setStyleSheet(f"color:{color_hex}; background:transparent; font-weight:bold;")
        self.tool_lbl.setText(s.tool or "")
        self.cwd_lbl.setText(s.cwd or "")

    # ── Poll ────────────────────────────────────────────────

    def _poll(self):
        try:
            changed, removed = self.manager.load_all()
        except Exception:
            changed, removed = [], []

        now = time.time()

        # First-load: pick active session
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

        # Status changes
        for sid in changed:
            s = self.manager.sessions.get(sid)
            if not s: continue
            old = self._last_statuses.get(sid, "")
            if old != s.status:
                self._selected_sid = sid
                self._refresh_content()
                self._rebuild_tabs()
                col, _ = STATUS_MAP.get(s.status, ("#9ca3af", ""))
                self._start_flash(col)
                self._update_tray_icon(col)
            self._last_statuses[sid] = s.status
            if s.status == "starting" and s.starting_since == 0:
                s.starting_since = now

        # Removed externally
        for sid in removed:
            self._last_statuses.pop(sid, None)

        # Auto-idle
        if self.manager.auto_transition_starting():
            self._refresh_content()
            self._rebuild_tabs()

        # Expired ended
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

        # Refresh display names (picks up /rename changes)
        for sid in list(self.manager.sessions.keys()):
            self.manager.refresh_display_name(sid)

        self._rebuild_tabs()
        self._refresh_content()
        self._auto_height()

    def closeEvent(self, event):
        event.ignore()
        self.hide_to_tray()


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
            stderr=subprocess.DEVNULL).decode("utf-8", errors="ignore")
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
    w.show()
    try:
        app.exec()
    finally:
        _remove_lock()

if __name__ == "__main__":
    main()
