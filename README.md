# ClaudePulse

A tiny always-on-top status monitor for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).  
See what Claude is doing at a glance — running a tool, waiting for your approval, idle, or crashed.

![ClaudePulse](https://img.shields.io/badge/platform-Windows-blue) ![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## What it shows

```
┌──────────────────────────┐
│ ● 运行中           ┌─┐┌─┐│  ← status dot + minimize / close
│                  └─┘└─┘│
│              [●═══] 85% │  ← draggable opacity slider
│ Bash                     │  ← active tool name
└──────────────────────────┘
```

| Status | Color | Meaning |
|--------|-------|---------|
| ● 空闲 | Green | Waiting for your input |
| ● 运行中 | Blue | Executing a tool |
| ● 等待批准 | Orange | Permission dialog shown |
| ● 错误 | Red | Tool execution failed |
| ● 启动中 | Purple | Session starting |
| ● 已结束 | Gray | Session ended |

The window border **flashes the new color 3 times** on every status change.

## Features

- **Always on top** — stays visible over other windows
- **Adjustable opacity** — drag the slider or scroll the mouse wheel (20%–100%)
- **System tray** — click **─** to minimize to tray; tray icon color matches the current status
- **Drag to move** — grab anywhere on the top bar area
- **Single instance** — launching it twice won't open a second window
- **Position & opacity memory** — restores last settings on restart

## How it works

```
Claude Code hooks ──▶ update-status.js ──▶ ~/.claude/status/current.json
                                                     │
ClaudePulse window ──▶ polls every 500ms ◀───────────┘
```

The hook script listens to 6 Claude Code lifecycle events (`SessionStart`, `PreToolUse`, `Stop`, `PermissionRequest`, `PostToolUseFailure`, `SessionEnd`) and writes the current state to a JSON file. The GUI window polls that file and renders accordingly.

## Installation

### 1. Download

Download `ClaudePulse.exe` from the [Releases](https://github.com/YOUR_USERNAME/ClaudePulse/releases) page.

### 2. Configure Claude Code hooks

Add this to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "PostToolUseFailure": [
      {
        "matcher": "*",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ],
    "SessionEnd": [
      {
        "matcher": "",
        "hooks": [{
          "type": "command",
          "command": "node /c/Users/YOURNAME/.claude/hooks/update-status.js"
        }]
      }
    ]
  }
}
```

### 3. Auto-start with Claude Code

**Git Bash** — add to `~/.bashrc`:

```bash
claude() {
    (nohup "C:/Users/YOURNAME/.claude/hooks/dist/ClaudePulse.exe" >/dev/null 2>&1 &)
    command claude "$@"
}
```

**PowerShell** — add to `$PROFILE`:

```powershell
function claude {
    Start-Process -WindowStyle Hidden "C:\Users\YOURNAME\.claude\hooks\dist\ClaudePulse.exe"
    & "C:\Users\YOURNAME\AppData\Roaming\npm\claude.cmd" @args
}
```

### 4. Place the hook script

Copy `src/update-status.js` to `~/.claude/hooks/update-status.js`.

### 5. Run

Start Claude Code normally (`claude`) — the monitor window will launch automatically.

## Build from source

```bash
pip install pystray pillow pyinstaller
pyinstaller --onefile --windowed --name "ClaudePulse" \
  --hidden-import pystray --hidden-import PIL --hidden-import PIL.Image \
  --hidden-import PIL.ImageDraw src/claude_pulse.py
```

Output: `dist/ClaudePulse.exe`

## Dependencies

- Python 3.10+
- `pystray` — system tray integration
- `Pillow` — tray icon rendering
- Node.js (for the hook script only)

## License

MIT
