"""Session data model and manager for ClaudePulse."""

import json
import os
import time

STATUS_DIR = os.path.expanduser("~/.claude/status")
SESSIONS_DIR = os.path.join(STATUS_DIR, "sessions")
CURRENT_FILE = os.path.join(STATUS_DIR, "current.json")

STATUS_MAP = {
    "starting":          ("#c084fc", "启动中"),
    "idle":              ("#4ade80", "空闲"),
    "running":           ("#60a5fa", "运行中"),
    "waiting_approval":  ("#fb923c", "等待批准"),
    "error":             ("#f87171", "错误"),
    "ended":             ("#9ca3af", "已结束"),
}

STARTING_TIMEOUT = 3    # seconds before "starting" auto-displays as "idle"
ENDED_RETENTION  = 30   # seconds to keep ended sessions in the list
STALE_TIMEOUT    = 1800 # 30 min fallback: mark as ended if PID check fails and no update


class Session:
    __slots__ = ("session_id", "display_name", "project", "status",
                 "tool", "cwd", "last_update", "file_mtime",
                 "starting_since", "ended_at")

    def __init__(self, session_id, display_name="", project="",
                 status="ended", tool="", cwd="",
                 last_update="", file_mtime=0.0):
        self.session_id = session_id
        self.display_name = display_name
        self.project = project
        self.status = status
        self.tool = tool
        self.cwd = cwd
        self.last_update = last_update
        self.file_mtime = file_mtime
        self.starting_since = 0.0
        self.ended_at = 0.0


class SessionManager:
    """Reads session JSON files and tracks changes."""

    def __init__(self):
        self.sessions: dict[str, Session] = {}
        self._mtimes: dict[str, float] = {}

    # -----------------------------------------------------------------
    def load_all(self):
        """Scan the sessions directory.
        Returns (changed_sids, removed_sids).
        """
        os.makedirs(SESSIONS_DIR, exist_ok=True)
        changed = []
        seen = set()

        try:
            for name in os.listdir(SESSIONS_DIR):
                if not name.endswith(".json"):
                    continue
                sid = name[:-5]
                if sid == "unknown" or not sid:  # skip invalid sessions
                    continue
                seen.add(sid)
                path = os.path.join(SESSIONS_DIR, name)

                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if sid in self._mtimes and self._mtimes[sid] == mtime:
                    continue
                self._mtimes[sid] = mtime

                try:
                    with open(path, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                except Exception:
                    continue

                old = self.sessions.get(sid)
                old_status = old.status if old else None

                s = Session(
                    session_id=sid,
                    display_name=data.get("display_name", ""),
                    project=data.get("project", ""),
                    status=data.get("status", "ended"),
                    tool=data.get("tool", ""),
                    cwd=data.get("cwd", ""),
                    last_update=data.get("last_update", ""),
                    file_mtime=mtime)

                if old:
                    s.starting_since = old.starting_since
                    s.ended_at = old.ended_at

                if s.status == "ended" and old_status != "ended":
                    s.ended_at = time.time()
                if s.status != "starting":
                    s.starting_since = 0.0

                self.sessions[sid] = s
                if old_status != s.status or mtime != getattr(old, "file_mtime", 0):
                    changed.append(sid)
        except Exception:
            pass

        removed = [sid for sid in self.sessions if sid not in seen]
        for sid in removed:
            del self.sessions[sid]
            self._mtimes.pop(sid, None)

        return changed, removed

    # -----------------------------------------------------------------
    def effective_status(self, sid: str) -> str:
        s = self.sessions.get(sid)
        if not s:
            return "ended"
        if s.status == "starting" and s.starting_since > 0:
            if time.time() - s.starting_since >= STARTING_TIMEOUT:
                return "idle"
        return s.status

    # -----------------------------------------------------------------
    def auto_transition_starting(self) -> list[str]:
        now = time.time()
        return [sid for sid, s in self.sessions.items()
                if s.status == "starting" and s.starting_since > 0
                and now - s.starting_since >= STARTING_TIMEOUT]

    # -----------------------------------------------------------------
    def get_expired_ended(self) -> list[str]:
        now = time.time()
        return [sid for sid, s in self.sessions.items()
                if s.status == "ended" and s.ended_at > 0
                and (now - s.ended_at) >= ENDED_RETENTION]

    # -----------------------------------------------------------------
    def remove_session(self, sid: str):
        self.sessions.pop(sid, None)
        self._mtimes.pop(sid, None)
        try:
            os.remove(os.path.join(SESSIONS_DIR, f"{sid}.json"))
        except Exception:
            pass

    # -----------------------------------------------------------------
    def refresh_display_name(self, sid: str):
        """Re-read the session name from ~/.claude/sessions metadata
        and update display_name if it has changed (e.g. after /rename).
        """
        s = self.sessions.get(sid)
        if not s:
            return
        CLAUDE_SESSIONS_DIR = os.path.join(
            os.path.expanduser("~"), ".claude", "sessions")
        try:
            for name in os.listdir(CLAUDE_SESSIONS_DIR):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(CLAUDE_SESSIONS_DIR, name),
                              "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                    if meta.get("sessionId") == sid:
                        meta_name = meta.get("name", "")
                        project = s.project
                        if meta_name:
                            new_name = f"{project}-{meta_name}"
                        else:
                            new_name = project
                        if new_name and new_name != s.display_name:
                            s.display_name = new_name
                            # Also update the status file on disk
                            self._write_display_name(sid, new_name)
                        return
                except Exception:
                    pass
        except Exception:
            pass

    def _write_display_name(self, sid: str, display_name: str):
        """Update display_name in the session status file on disk."""
        fpath = os.path.join(SESSIONS_DIR, f"{sid}.json")
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("display_name") != display_name:
                data["display_name"] = display_name
                with open(fpath, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # -----------------------------------------------------------------
    def _get_session_pid(self, sid: str) -> int | None:
        """Look up the PID for a session from ~/.claude/sessions metadata."""
        sd = os.path.join(os.path.expanduser("~"), ".claude", "sessions")
        try:
            for name in os.listdir(sd):
                if not name.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(sd, name), "r", encoding="utf-8") as fh:
                        meta = json.load(fh)
                    if meta.get("sessionId") == sid:
                        return meta.get("pid")
                except Exception:
                    pass
        except Exception:
            pass
        return None

    def _is_pid_running(self, pid: int) -> bool:
        """Check if a Windows process with given PID is alive."""
        import subprocess
        try:
            out = subprocess.check_output(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW") else 0).decode(
                    "utf-8", errors="ignore")
            return str(pid) in out
        except Exception:
            return False

    def get_stale_sessions(self) -> list[str]:
        """Return sessions whose Claude Code process is no longer running.
        PID check first, then fallback to time-based for edge cases."""
        stale = []
        now = time.time()
        for sid, s in self.sessions.items():
            if s.status == "ended":
                continue
            pid = self._get_session_pid(sid)
            if pid is not None:
                # PID found — check if process is alive
                if not self._is_pid_running(pid):
                    stale.append(sid)
            else:
                # No PID metadata — fallback to time check
                if not s.last_update:
                    continue
                try:
                    import datetime
                    ts = s.last_update.replace("Z", "").split(".")[0]
                    dt = datetime.datetime.fromisoformat(ts)
                    if now - dt.timestamp() >= STALE_TIMEOUT:
                        stale.append(sid)
                except Exception:
                    pass
        return stale

    # -----------------------------------------------------------------
    def ordered_sessions(self, tab_order: list[str]) -> list[Session]:
        result = [self.sessions[sid] for sid in tab_order if sid in self.sessions]
        rest = [s for s in self.sessions.values() if s.session_id not in tab_order]
        rest.sort(key=lambda s: s.file_mtime)
        return result + rest
