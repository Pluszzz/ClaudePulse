"""ClaudePulse hook — tiny standalone exe, no console, no Qt.
Built with: pyinstaller --onefile --windowed --name cp-hook src/cp-hook.py"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = os.path.expanduser("~")
STATUS_DIR = os.path.join(HOME, ".claude", "status")
SESSIONS_DIR = os.path.join(STATUS_DIR, "sessions")
CURRENT_FILE = os.path.join(STATUS_DIR, "current.json")
CLAUDE_SESSIONS_DIR = os.path.join(HOME, ".claude", "sessions")

EVENT_STATUS = {
    "SessionStart": "starting", "UserPromptSubmit": "running",
    "PreToolUse": "running", "PostToolUseFailure": "error",
    "PermissionRequest": "waiting_approval",
    "Stop": "idle", "SessionEnd": "ended",
}


def find_session_name(sid: str) -> str:
    if not sid:
        return ""
    try:
        for fn in os.listdir(CLAUDE_SESSIONS_DIR):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(CLAUDE_SESSIONS_DIR, fn), "r", encoding="utf-8") as f:
                    d = json.load(f)
                if d.get("sessionId") == sid:
                    return d.get("name", "")
            except Exception:
                pass
    except Exception:
        pass
    return ""


def main():
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""
    try:
        inp = json.loads(raw) if raw else {}
    except Exception:
        return

    sid = inp.get("session_id", "")
    if not sid or sid == "unknown":
        return

    status = EVENT_STATUS.get(inp.get("hook_event_name", ""), "running")
    tool_name = inp.get("tool_name", "")
    cwd = inp.get("cwd", "")

    # Read previous state
    sf = os.path.join(SESSIONS_DIR, f"{sid}.json")
    prev = {}
    try:
        with open(sf, "r", encoding="utf-8") as f:
            prev = json.load(f)
    except Exception:
        pass

    project = Path(cwd).name if cwd else prev.get("project", "")

    sname = find_session_name(sid)
    if sname:
        display_name = f"{project}-{sname}"
    elif prev.get("display_name") and status != "starting":
        display_name = prev["display_name"]
    else:
        display_name = project
        try:
            existing = [f for f in os.listdir(SESSIONS_DIR)
                        if f.endswith(".json") and f != f"{sid}.json"]
            used = []
            for ef in existing:
                try:
                    with open(os.path.join(SESSIONS_DIR, ef), "r", encoding="utf-8") as f:
                        used.append(json.load(f).get("display_name", ""))
                except Exception:
                    pass
            cand, n = display_name, 2
            while cand in used:
                cand = f"{display_name} ({n})"; n += 1
            display_name = cand
        except Exception:
            pass

    entry = {
        "session_id": sid,
        "display_name": display_name,
        "project": project or prev.get("project", ""),
        "status": status,
        "tool": ("" if status in ("idle", "starting", "ended")
                 else tool_name or prev.get("tool", "")),
        "cwd": cwd or prev.get("cwd", ""),
        "last_update": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(sf, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)

    with open(CURRENT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "active_session": sid,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
