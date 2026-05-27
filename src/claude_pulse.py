import json
import os
import sys
import tkinter as tk
from pathlib import Path

STATUS_FILE = os.path.expanduser("~/.claude/status/current.json")
CONFIG_FILE = os.path.expanduser("~/.claude/status/window-config.json")

STATUS_MAP = {
    "starting":          ("#c084fc", "启动中"),
    "idle":              ("#4ade80", "空闲"),
    "running":           ("#60a5fa", "运行中"),
    "waiting_approval":  ("#fb923c", "等待批准"),
    "error":             ("#f87171", "错误"),
    "ended":             ("#9ca3af", "已结束"),
}

TRAY_AVAILABLE = False
pystray = None
Image = None
ImageDraw = None
try:
    import pystray as _pystray
    from PIL import Image as _Image, ImageDraw as _ImageDraw
    pystray = _pystray
    Image = _Image
    ImageDraw = _ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    pass

# ── helpers ──────────────────────────────────────────────

def load_config():
    defaults = {"opacity": 0.85, "x": None, "y": None}
    try:
        with open(CONFIG_FILE, "r") as f:
            return {**defaults, **json.load(f)}
    except Exception:
        return defaults

def save_config(opacity, x, y):
    try:
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump({"opacity": opacity, "x": x, "y": y}, f)
    except Exception:
        pass

def read_status():
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {"status": "ended", "tool": "", "project": ""}

def make_tray_icon(color="#6C7086"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([6, 6, 58, 58], fill=color)
    r, g, b = _hex_to_rgb(color)
    lighter = _clamp_rgb(r + 60, g + 60, b + 60)
    draw.ellipse([20, 20, 44, 44], fill=lighter)
    draw.ellipse([26, 14, 32, 20], fill="white")
    return img

def _hex_to_rgb(hx):
    hx = hx.lstrip("#")
    return tuple(int(hx[i : i + 2], 16) for i in (0, 2, 4))

def _clamp_rgb(r, g, b):
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

# ── custom draggable slider ──────────────────────────────

SLIDER_TRACK = "#33334a"
SLIDER_FILL = "#45475a"
SLIDER_THUMB = "#a6adc8"
SLIDER_THUMB_HOT = "#ffffff"
SLIDER_THUMB_R = 5

class OpacitySlider(tk.Frame):
    def __init__(self, parent, width=90, height=16, initial=85, on_change=None):
        super().__init__(parent, bg=BG, bd=0, highlightthickness=0)
        self._on_change = on_change
        self._value = initial
        self._sw = width
        self._sh = height
        self._dragging = False

        self.canvas = tk.Canvas(
            self, width=width, height=height,
            bg=BG, highlightthickness=0, bd=0,
        )
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self.draw()

    def draw(self):
        self.canvas.delete("all")
        margin = 6
        track_y = self._sh // 2
        track_x0 = margin
        track_x1 = self._sw - margin
        r = 3

        self.canvas.create_rectangle(
            track_x0, track_y - r, track_x1, track_y + r,
            fill=SLIDER_TRACK, outline="",
            tags="track_bg",
        )

        frac = (self._value - 10) / 90
        fill_x = track_x0 + frac * (track_x1 - track_x0)
        self.canvas.create_rectangle(
            track_x0, track_y - r, fill_x, track_y + r,
            fill=SLIDER_FILL, outline="",
            tags="track_fill",
        )

        self._thumb_x = fill_x
        self._thumb_y = track_y
        self.canvas.create_oval(
            fill_x - SLIDER_THUMB_R, track_y - SLIDER_THUMB_R,
            fill_x + SLIDER_THUMB_R, track_y + SLIDER_THUMB_R,
            fill=SLIDER_THUMB, outline="",
            tags="thumb",
        )

    def _pos_to_value(self, x):
        margin = 6
        track_len = self._sw - 2 * margin
        frac = max(0, min(1, (x - margin) / track_len))
        return int(10 + frac * 90)

    def _set_value(self, val):
        val = max(10, min(100, val))
        if val != self._value:
            self._value = val
            self.draw()
            if self._on_change:
                self._on_change(val)

    def _on_click(self, event):
        self._dragging = True
        self._set_value(self._pos_to_value(event.x))

    def _on_drag(self, event):
        if self._dragging:
            self._set_value(self._pos_to_value(event.x))

    def _on_release(self, event):
        self._dragging = False

    def set_value(self, val):
        self._value = val
        self.draw()

    @property
    def value(self):
        return self._value

# ── main window ──────────────────────────────────────────

BG = "#1e1e2e"
FG_DIM = "#a6adc8"
FG_WHITE = "#ffffff"
BORDER = "#45475a"
BTN_BG = "#2a2a3a"

class StatusWindow:
    def __init__(self):
        self.config = load_config()
        self._opacity = self.config["opacity"]

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self._opacity)
        self.root.configure(bg=BG)

        self.W = 220
        self.H = 80

        x = self.config.get("x")
        y = self.config.get("y")
        if x is None:
            x = self.root.winfo_screenwidth() - self.W - 20
        if y is None:
            y = 20
        self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")

        self._build_ui()
        self._bind_events()

        self._last_status = None
        self._flash_after = None

        self.tray_icon = None
        if TRAY_AVAILABLE:
            self._setup_tray()

        self.root.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.poll_status()

    # ── UI ──────────────────────────────────────────────

    def _build_ui(self):
        # Outer frame (border)
        self.frame = tk.Frame(
            self.root, bg=BG, bd=1, relief="solid",
            highlightbackground=BORDER, highlightthickness=1,
        )
        self.frame.pack(fill="both", expand=True)

        # ── Row 1: status + buttons ──
        self.row1 = tk.Frame(self.frame, bg=BG, height=28)
        self.row1.pack(fill="x", side="top")
        self.row1.pack_propagate(False)

        self.status_label = tk.Label(
            self.row1, text="● 空闲", font=("Microsoft YaHei UI", 11, "bold"),
            fg="#4ade80", bg=BG, anchor="w", padx=12,
        )
        self.status_label.pack(side="left", fill="y")

        # Buttons container (right side)
        btn_area = tk.Frame(self.row1, bg=BG)
        btn_area.pack(side="right", padx=6, pady=5)

        # Close button
        self.close_btn_frame = tk.Frame(
            btn_area, bg=BTN_BG, bd=1, relief="solid",
            highlightbackground=BORDER, highlightthickness=1,
            width=24, height=20,
        )
        self.close_btn_frame.pack(side="right", padx=(4, 0))
        self.close_btn_frame.pack_propagate(False)

        self.close_btn = tk.Label(
            self.close_btn_frame, text="×",
            font=("Microsoft YaHei UI", 11, "bold"),
            fg=FG_DIM, bg=BTN_BG,
        )
        self.close_btn.pack(fill="both", expand=True)

        # Minimize button
        self.min_btn_frame = tk.Frame(
            btn_area, bg=BTN_BG, bd=1, relief="solid",
            highlightbackground=BORDER, highlightthickness=1,
            width=24, height=20,
        )
        self.min_btn_frame.pack(side="right", padx=0)
        self.min_btn_frame.pack_propagate(False)

        self.min_btn = tk.Label(
            self.min_btn_frame, text="─",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg=FG_DIM, bg=BTN_BG,
        )
        self.min_btn.pack(fill="both", expand=True)

        # ── Row 2: opacity slider (right-aligned) ──
        row2 = tk.Frame(self.frame, bg=BG, height=24)
        row2.pack(fill="x", side="top")
        row2.pack_propagate(False)

        tk.Label(row2, text="", bg=BG).pack(side="left", fill="x", expand=True)

        self.pct_label = tk.Label(
            row2, text=f"{int(self._opacity*100)}%",
            font=("Microsoft YaHei UI", 7),
            fg=FG_DIM, bg=BG, width=4, anchor="e",
        )
        self.pct_label.pack(side="right", padx=(0, 2))

        self.slider = OpacitySlider(
            row2, width=90, height=16,
            initial=int(self._opacity * 100),
            on_change=self._on_slider_change,
        )
        self.slider.pack(side="right", padx=(0, 10))

        # ── Row 3: sub info ──
        row3 = tk.Frame(self.frame, bg=BG)
        row3.pack(fill="x", side="top")

        self.sub_label = tk.Label(
            row3, text="", font=("Microsoft YaHei UI", 8),
            fg=FG_DIM, bg=BG, anchor="w", padx=14,
        )
        self.sub_label.pack(fill="x")

    # ── events ──────────────────────────────────────────

    def _bind_events(self):
        drag_targets = (
            self.frame, self.status_label, self.sub_label, self.row1,
        )
        for w in drag_targets:
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)
            w.bind("<ButtonRelease-1>", self._end_drag)
            w.bind("<Button-3>", self._show_menu)

        # Minimize button — press/release behavior
        self.min_btn.bind("<Button-1>", self._min_press)
        self.min_btn.bind("<ButtonRelease-1>", self._min_release)
        self.min_btn.bind("<Enter>", self._min_enter)
        self.min_btn.bind("<Leave>", self._min_leave)
        self.min_btn_frame.bind("<Enter>", self._min_enter)
        self.min_btn_frame.bind("<Leave>", self._min_leave)

        # Close button — press/release behavior
        self.close_btn.bind("<Button-1>", self._close_press)
        self.close_btn.bind("<ButtonRelease-1>", self._close_release)
        self.close_btn.bind("<Enter>", self._close_enter)
        self.close_btn.bind("<Leave>", self._close_leave)
        self.close_btn_frame.bind("<Enter>", self._close_enter)
        self.close_btn_frame.bind("<Leave>", self._close_leave)

        # Right-click menu
        self.menu = tk.Menu(self.root, tearoff=0)
        self.menu.add_command(label="隐藏到托盘", command=self.hide_to_tray)
        self.menu.add_separator()
        self.menu.add_command(label="退出", command=self.quit_app)

    # ── minimize button ─────────────────────────────────

    def _min_enter(self, event):
        self.min_btn.config(fg=FG_WHITE)
        self.min_btn_frame.configure(highlightbackground=FG_WHITE)

    def _min_leave(self, event):
        self.min_btn.config(fg=FG_DIM)
        self.min_btn_frame.configure(highlightbackground=BORDER)

    def _min_press(self, event):
        self.min_btn_frame.configure(bg="#1a1a2a")
        self.min_btn.config(bg="#1a1a2a")

    def _min_release(self, event):
        self.min_btn_frame.configure(bg=BTN_BG)
        self.min_btn.config(bg=BTN_BG)
        # Only trigger if cursor is still within the button frame
        x, y = event.x_root, event.y_root
        fx = self.min_btn_frame.winfo_rootx()
        fy = self.min_btn_frame.winfo_rooty()
        fw = self.min_btn_frame.winfo_width()
        fh = self.min_btn_frame.winfo_height()
        if fx <= x <= fx + fw and fy <= y <= fy + fh:
            self.hide_to_tray()

    # ── close button ────────────────────────────────────

    def _close_enter(self, event):
        self.close_btn.config(fg="#f87171")
        self.close_btn_frame.configure(highlightbackground="#f87171")

    def _close_leave(self, event):
        self.close_btn.config(fg=FG_DIM)
        self.close_btn_frame.configure(highlightbackground=BORDER)

    def _close_press(self, event):
        self.close_btn_frame.configure(bg="#1a1a2a")
        self.close_btn.config(bg="#1a1a2a")

    def _close_release(self, event):
        self.close_btn_frame.configure(bg=BTN_BG)
        self.close_btn.config(bg=BTN_BG)
        x, y = event.x_root, event.y_root
        fx = self.close_btn_frame.winfo_rootx()
        fy = self.close_btn_frame.winfo_rooty()
        fw = self.close_btn_frame.winfo_width()
        fh = self.close_btn_frame.winfo_height()
        if fx <= x <= fx + fw and fy <= y <= fy + fh:
            self.quit_app()

    # ── tray ────────────────────────────────────────────

    def _setup_tray(self):
        icon_img = make_tray_icon("#6C7086")
        menu = pystray.Menu(
            pystray.MenuItem("显示/隐藏", self.toggle_visible, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", self.quit_app),
        )
        self.tray_icon = pystray.Icon(
            "claude_status", icon_img, "Claude Code Status", menu,
        )

    # ── drag ────────────────────────────────────────────

    def _start_drag(self, event):
        self._dx = event.x
        self._dy = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + (event.x - self._dx)
        y = self.root.winfo_y() + (event.y - self._dy)
        self.root.geometry(f"+{x}+{y}")

    def _end_drag(self, event):
        save_config(self._opacity, self.root.winfo_x(), self.root.winfo_y())

    def _show_menu(self, event):
        self.menu.post(event.x_root, event.y_root)

    # ── opacity ─────────────────────────────────────────

    def _on_slider_change(self, pct):
        self._opacity = pct / 100
        self.root.attributes("-alpha", self._opacity)
        self.pct_label.config(text=f"{pct}%")

    def set_opacity(self, value):
        self._opacity = value
        pct = int(value * 100)
        self.slider.set_value(pct)
        self.pct_label.config(text=f"{pct}%")
        self.root.attributes("-alpha", value)
        save_config(value, self.root.winfo_x(), self.root.winfo_y())

    # ── actions ─────────────────────────────────────────

    def hide_to_tray(self):
        if TRAY_AVAILABLE and self.tray_icon:
            self.root.withdraw()
            self.tray_icon.run_detached()
        else:
            self.root.iconify()

    def toggle_visible(self):
        if self.root.state() in ("withdrawn", "iconic"):
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
        else:
            self.root.withdraw()

    def quit_app(self):
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.quit()
        self.root.destroy()
        sys.exit(0)

    # ── flash ──────────────────────────────────────────

    def _flash_border(self, color, count):
        if count >= 6:
            self.frame.configure(highlightbackground=BORDER)
            return
        if count % 2 == 0:
            self.frame.configure(highlightbackground=color)
        else:
            self.frame.configure(highlightbackground=BORDER)
        self._flash_after = self.root.after(1000, self._flash_border, color, count + 1)

    # ── polling ─────────────────────────────────────────

    def poll_status(self):
        try:
            data = read_status()
        except Exception:
            data = {"status": "ended", "tool": "", "project": ""}

        status = data.get("status", "ended")
        color, label = STATUS_MAP.get(status, ("#9ca3af", "未知"))
        tool = data.get("tool", "")

        self.status_label.config(text=f"● {label}", fg=color)

        # Flash border on status change
        if status != self._last_status:
            self._last_status = status
            self._flash_border(color, 0)

        if status == "running" and tool:
            sub = tool
        elif status == "running":
            sub = "思考中..."
        elif status == "waiting_approval" and tool:
            sub = "需批准: " + tool
        elif status == "error":
            sub = "失败: " + tool if tool else "发生错误"
        elif status == "starting":
            sub = "正在启动..."
        else:
            sub = ""

        self.sub_label.config(text=sub)

        if TRAY_AVAILABLE and self.tray_icon:
            try:
                self.tray_icon.icon = make_tray_icon(color)
            except Exception:
                pass

        self.root.after(500, self.poll_status)


# ── single instance check ──────────────────────────────

LOCK_FILE = os.path.expanduser("~/.claude/status/window.lock")

def _check_running():
    """Return True if another instance is already running."""
    try:
        with open(LOCK_FILE, "r") as f:
            old_pid = int(f.read().strip())
        # Check if the process still exists
        import subprocess
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {old_pid}", "/NH", "/FO", "CSV"],
            stderr=subprocess.DEVNULL,
        ).decode("utf-8", errors="ignore")
        if str(old_pid) in out:
            return True
    except Exception:
        pass
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

# ── entry ────────────────────────────────────────────────

def main():
    if _check_running():
        print("Status window is already running.", file=sys.stderr)
        sys.exit(0)
    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    _write_lock()
    try:
        StatusWindow().root.mainloop()
    finally:
        _remove_lock()

if __name__ == "__main__":
    main()
