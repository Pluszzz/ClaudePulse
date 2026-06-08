"""Claude Code hook — reads event JSON from stdin, writes status file.
Run with pythonw.exe to avoid console-window flash on Windows."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "status")
SESSIONS_DIR = os.path.join(STATUS_DIR, "sessions")
CURRENT_FILE = os.path.join(STATUS_DIR, "current.json")
CLAUDE_SESSIONS_DIR = os.path.join(os.path.expanduser("~"), ".claude", "sessions")

EVENT_STATUS = {
    "SessionStart":       "starting",
    "UserPromptSubmit":   "running",
    "PreToolUse":         "running",
    "PostToolUseFailure": "error",
    "PermissionRequest":  "waiting_approval",
    "Stop":               "idle",
    "SessionEnd":         "ended",
}


def find_session_name(session_id: str) -> str:
    """Look up the session name (set via /rename) from ~/.claude/sessions/."""
    if not session_id:
        return ""
    try:
        for fname in os.listdir(CLAUDE_SESSIONS_DIR):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(CLAUDE_SESSIONS_DIR, fname),
                          "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if data.get("sessionId") == session_id:
                    return data.get("name", "")
            except Exception:
                pass
    except Exception:
        pass
    return ""


def main():
    # Read JSON from stdin (Claude Code pipes hook event data)
    try:
        raw = sys.stdin.read()
    except Exception:
        raw = ""

    try:
        inp = json.loads(raw) if raw else {}
    except Exception:
        inp = {}

    event = inp.get("hook_event_name", "")
    status = EVENT_STATUS.get(event, "running")
    tool_name = inp.get("tool_name", "")
    cwd = inp.get("cwd", "")
    session_id = inp.get("session_id", "")

    # Skip events without a valid session_id
    if not session_id or session_id == "unknown":
        return

    session_name = find_session_name(session_id)

    # Read previous state to preserve fields
    session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    prev = {}
    try:
        with open(session_file, "r", encoding="utf-8") as fh:
            prev = json.load(fh)
    except Exception:
        pass

    project = Path(cwd).name if cwd else prev.get("project", "")

    # Build display name
    if session_name:
        display_name = f"{project}-{session_name}"
    elif prev.get("display_name") and status != "starting":
        display_name = prev["display_name"]
    else:
        display_name = project
        # Deduplicate
        try:
            existing = [f for f in os.listdir(SESSIONS_DIR)
                        if f.endswith(".json") and f != f"{session_id}.json"]
            used = []
            for ef in existing:
                try:
                    with open(os.path.join(SESSIONS_DIR, ef),
                              "r", encoding="utf-8") as fh:
                        used.append(json.load(fh).get("display_name", ""))
                except Exception:
                    pass
            candidate = display_name
            counter = 2
            while candidate in used:
                candidate = f"{display_name} ({counter})"
                counter += 1
            display_name = candidate
        except Exception:
            pass

    entry = {
        "session_id": session_id,
        "display_name": display_name,
        "project": project or prev.get("project", ""),
        "status": status,
        "tool": ("" if status in ("idle", "starting", "ended")
                 else tool_name or prev.get("tool", "")),
        "cwd": cwd or prev.get("cwd", ""),
        "last_update": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(session_file, "w", encoding="utf-8") as fh:
        json.dump(entry, fh, ensure_ascii=False, indent=2)

    current = {
        "active_session": session_id,
        "last_update": datetime.now(timezone.utc).isoformat(),
    }
    with open(CURRENT_FILE, "w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
