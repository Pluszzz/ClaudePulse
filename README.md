# ClaudePulse

[English](README.md) | [简体中文](README.zh-CN.md)

A tiny always-on-top status monitor for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).  
See what Claude is doing at a glance — running a tool, waiting for your approval, idle, or crashed.

Supports **multiple concurrent Claude Code sessions** with a tabbed UI.

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![qt](https://img.shields.io/badge/Qt-PySide6-green)

## Dual-mode design

**Compact circle** (shown when mouse is elsewhere):

```
         ╭──────────╮
        ╱            ╲
       │  ●  Running   │
       │  myproject    │
        ╲            ╱
         ╰──────────╯
    120×120 circle · always on top
```

**Full window** (shown when mouse hovers over the circle):

```
┌──────────────────────────────────────────┐
│ ClaudePulse                    ─  ×      │
├────────┬─────────────────────────────────┤
│ ● Proj │ ●  Running                      │
│ ● App  │ Bash                            │
│ ● API  │ myproject-feature               │
└────────┴─────────────────────────────────┘
```

Hover over the circle — it mask-expands (100ms) into the full window. Move the mouse away — it mask-collapses back into the circle. Both windows stay center-aligned during the transition for a seamless effect.

### Half-circle dock

When the full window touches a screen edge (left / right / top), the compact circle auto-docks as a **half-circle** attached to that edge:

| Edge | Shape | Size | Shows |
|------|-------|------|-------|
| Left | ◗ right-half visible | 60×120 | Status only |
| Right | ◖ left-half visible | 60×120 | Status only |
| Top | ◔ bottom-half visible | 120×60 | Status + name |

Drag the full window to any screen edge and move the mouse away to see it. Multi-monitor aware.

## Status indicators

| Status | Color | Meaning |
|--------|-------|---------|
| ● Idle | Green | Waiting for your input |
| ● Running | Blue | Executing a tool |
| ● Waiting Approval | Orange | Permission dialog shown |
| ● Error | Red | Tool execution failed |
| ● Starting | Purple | Session starting (auto → idle after 3s) |
| ● Ended | Gray | Session ended (removed after 30s) |

Both the compact circle and the full window **flash 3 times** on status change (overlay or border mode, configurable).

## Features

- **Always on top** — stays visible over other windows
- **Dual-mode** — compact 120×120 circle when idle, full window on hover
- **Half-circle dock** — auto-attaches to screen edges (left / right / top)
- **Smooth mask animation** — 100ms expand/collapse, center-aligned
- **Multi-session tabs** — each Claude Code session gets a vertical tab on the left
- **Auto-switch on change** — when a session's status changes, the UI jumps to it
- **Flash on both views** — compact circle and full window both flash; overlay or border mode
- **Adjustable opacity** — via tray → Settings (default 75%)
- **System tray** — icon always visible, color matches current session status; Settings in tray menu
- **Native resize** — grab any edge or corner to resize the full window
- **Drag to reorder tabs** — swap session order by dragging
- **Auto-height** — window grows with sessions, caps at 600px
- **Marquee scrolling** — long session names scroll horizontally in the compact circle
- **Clickable title** — "ClaudePulse" opens the GitHub repo
- **Single instance** — launching twice won't open a second window
- **Multi-monitor** — correctly detects and docks to any screen
- **Persistent config** — position, size, splitter ratio, opacity, flash settings all remembered

## How it works

```
Claude Code hooks ──▶ update-status.js ──▶ ~/.claude/status/sessions/{id}.json
                                                      │
ClaudePulse ──▶ polls every 500ms ◀───────────────────┘
```

The hook script listens to 7 Claude Code lifecycle events (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`, `PermissionRequest`, `PostToolUseFailure`, `SessionEnd`) and writes each session's state to a JSON file. The GUI polls those files and renders accordingly.

## Installation

### One-click installer

Download and unzip, then **double-click `install.bat`**.

Or via command line:

```bash
git clone https://github.com/Pluszzz/ClaudePulse.git
cd ClaudePulse
install.bat
```

The installer will:
1. Check Node.js environment
2. Download `ClaudePulse.exe` from GitHub Releases (~47 MB, one-time)
3. Deploy the hook script and configure `settings.json`
4. Let you choose which terminal(s) to auto-start with (CMD / PowerShell)
5. Done — open a **new terminal** and type `claude`

### Manual setup

If you prefer to configure manually:

```bash
# Download the exe from Releases and place it in ~/.claude/hooks/
mkdir -p ~/.claude/hooks
cp src/update-status.js ~/.claude/hooks/update-status.js
```

Then add hooks to `~/.claude/settings.json`, set up auto-start in your terminal pointing to `~/.claude/hooks/ClaudePulse.exe`, or run directly:

```bash
~/.claude/hooks/ClaudePulse.exe
```

### Dev mode (run from source)

```bash
pip install PySide6
python src/main.py
```

## Build from source

```bash
pip install pyinstaller PySide6
pyinstaller --onefile --windowed --name "ClaudePulse" src/main.py
```

Output: `dist/ClaudePulse.exe`

## Dependencies

**For end users:**
- Node.js — for the hook script
- **Nothing else** — the exe is self-contained

**For developers:**
- Python 3.10+
- PySide6 — Qt GUI framework
- PyInstaller — for building the exe

## Project structure

```
ClaudePulse/
├── src/
│   ├── main.py              ← Qt GUI entry point
│   ├── session_manager.py   ← data layer (reads session JSON)
│   └── update-status.js     ← Claude Code hook
├── install.bat              ← one-click installer
├── ClaudePulse.spec         ← PyInstaller build spec
├── LICENSE
├── README.md
├── README.zh-CN.md
└── .gitignore
```

## License

MIT © Pluszzz
