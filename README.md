# ClaudePulse

A tiny always-on-top status monitor for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).  
See what Claude is doing at a glance — running a tool, waiting for your approval, idle, or crashed.

Supports **multiple concurrent Claude Code sessions** with a tabbed UI.

![platform](https://img.shields.io/badge/platform-Windows-blue)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![qt](https://img.shields.io/badge/Qt-PySide6-green)

## What it shows

```
┌──────────────────────────────────────────┐
│ ClaudePulse                    ─  ×      │
├────────┬─────────────────────────────────┤
│ ● Proj │ ● 运行中                        │
│ ● App  │ Bash                            │
│ ● API  │ D:\CodeWork\...                  │
│        │                           [齿轮] │
└────────┴─────────────────────────────────┘
```

| Status | Color | Meaning |
|--------|-------|---------|
| ● 空闲 | Green | Waiting for your input |
| ● 运行中 | Blue | Executing a tool |
| ● 等待批准 | Orange | Permission dialog shown |
| ● 错误 | Red | Tool execution failed |
| ● 启动中 | Purple | Session starting (auto → idle after 3s) |
| ● 已结束 | Gray | Session ended (removed after 30s) |

The window border **flashes 3 times** on every status change and auto-switches to that session's tab.

## Features

- **Always on top** — stays visible over other windows
- **Multi-session tabs** — each Claude Code session gets a vertical tab on the left
- **Auto-switch on change** — when a session's status changes, the UI jumps to it
- **Adjustable opacity** — via settings gear menu (default 75%)
- **System tray** — icon always visible, color matches current session status
- **Native resize** — grab any edge or corner to resize (Qt handles this properly)
- **Drag to reorder tabs** — swap session order by dragging
- **Auto-height** — window grows with sessions, caps at 600px then tabs scroll
- **Clickable title** — "ClaudePulse" opens the GitHub repo
- **Single instance** — launching twice won't open a second window
- **Position & opacity memory** — restores last settings on restart

## How it works

```
Claude Code hooks ──▶ update-status.js ──▶ ~/.claude/status/sessions/{id}.json
                                                      │
ClaudePulse window ──▶ polls every 500ms ◀────────────┘
```

The hook script listens to 7 Claude Code lifecycle events (`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `Stop`, `PermissionRequest`, `PostToolUseFailure`, `SessionEnd`) and writes each session's state to a JSON file. The GUI polls those files and renders accordingly.

## Installation

### 1. Requirements

- Python 3.10+
- Node.js (for the hook script)
- Git Bash / CMD / PowerShell on Windows

### 2. Install dependencies

```bash
pip install PySide6 pystray Pillow
```

> **PySide6** is the Qt GUI framework (~150 MB). `pystray` + `Pillow` are for system tray integration.

### 3. Clone and set up hooks

```bash
git clone https://github.com/Pluszzz/ClaudePulse.git
mkdir -p ~/.claude/hooks
cp ClaudePulse/src/update-status.js ~/.claude/hooks/update-status.js
```

### 4. Configure Claude Code hooks

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "UserPromptSubmit": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOUR_USERNAME/.claude/hooks/update-status.js"
        }]
      }
    ]
  }
}
```

> Replace `YOUR_USERNAME` with your Windows username. Use forward slashes.

### 5. Auto-start with Claude Code

**Git Bash** — add to `~/.bashrc`:

```bash
claude() {
    (python /d/CodeWork/ClaudePulse/ClaudePulse/src/main.py &) 2>/dev/null
    command claude --dangerously-skip-permissions "$@"
}
```

**PowerShell** — add to `$PROFILE`:

```powershell
function claude {
    Start-Process -WindowStyle Hidden pythonw -ArgumentList "D:\CodeWork\ClaudePulse\ClaudePulse\src\main.py"
    & "C:\Users\YOUR_USERNAME\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe" --dangerously-skip-permissions --permission-mode bypassPermissions @args
}
```

**CMD** — edit `C:\Users\YOUR_USERNAME\bin\claude.cmd`:

```batch
@echo off
start "" pythonw D:\CodeWork\ClaudePulse\ClaudePulse\src\main.py 2>nul
"C:\Users\YOUR_USERNAME\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe" --dangerously-skip-permissions --permission-mode bypassPermissions %*
```

### 6. Run manually

```bash
python D:/CodeWork/ClaudePulse/ClaudePulse/src/main.py
```

Or start Claude Code normally — the monitor window will launch automatically if you set up auto-start.

## Build from source

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "ClaudePulse" \
  --hidden-import PySide6 --hidden-import pystray --hidden-import PIL \
  src/main.py
```

Output: `dist/ClaudePulse.exe`

## Dependencies

- Python 3.10+
- **PySide6** — Qt GUI framework
- **pystray** — system tray integration (optional, GUI falls back gracefully)
- **Pillow** — tray icon rendering (optional)
- Node.js — for the hook script only

## Project structure

```
ClaudePulse/
├── src/
│   ├── main.py              ← Qt GUI entry point
│   ├── session_manager.py   ← data layer (reads session JSON)
│   └── update-status.js     ← Claude Code hook (unchanged)
├── README.md
└── .gitignore
```

## License

MIT
