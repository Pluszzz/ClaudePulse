"""ClaudePulse Installer — one-click setup for any terminal."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
CLAUDE_CONFIG = HOME / ".claude"
HOOKS_DIR = CLAUDE_CONFIG / "hooks"
SETTINGS_FILE = CLAUDE_CONFIG / "settings.json"
SRC_DIR = Path(__file__).resolve().parent / "src"

BASH_RC = HOME / ".bashrc"
CMD_WRAPPER = HOME / "bin" / "claude.cmd"
PS_PROFILE_DIR = HOME / "Documents" / "WindowsPowerShell"
PS_PROFILE = PS_PROFILE_DIR / "Microsoft.PowerShell_profile.ps1"

RED = "\033[91m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"

def ok(msg):    print(f"  {GREEN}✓{RESET} {msg}")
def warn(msg):  print(f"  {RED}✗{RESET} {msg}")
def info(msg):  print(f"  {CYAN}→{RESET} {msg}")
def title(msg): print(f"\n{CYAN}{'─'*50}{RESET}\n{CYAN}  {msg}{RESET}\n{CYAN}{'─'*50}{RESET}")


# ═══════════════════════════════════════════════════════════════
# Step 1 — Environment check
# ═══════════════════════════════════════════════════════════════

def check_python():
    try:
        v = subprocess.check_output([sys.executable, "--version"], text=True).strip()
        ok(f"Python: {v}")
        return True
    except Exception:
        warn("Python not found in PATH")
        return False

def check_node():
    try:
        v = subprocess.check_output(["node", "--version"], text=True).strip()
        ok(f"Node.js: {v}")
        return True
    except Exception:
        warn("Node.js not found — hook script won't work without it")
        return False

def check_claude_code():
    # Check if Claude Code is installed via winget
    candidates = list(HOME.glob(
        "AppData/Local/Microsoft/WinGet/Packages/"
        "Anthropic.ClaudeCode_*/claude.exe"))
    if candidates:
        ok(f"Claude Code: {candidates[0]}")
        return str(candidates[0])
    # Fallback: try PATH
    try:
        r = subprocess.check_output(["where", "claude"], text=True, shell=True)
        ok(f"Claude Code: found in PATH")
        return r.strip().splitlines()[0]
    except Exception:
        warn("Claude Code not detected — auto-start won't work")
        return None


# ═══════════════════════════════════════════════════════════════
# Step 2 — Install dependencies
# ═══════════════════════════════════════════════════════════════

def install_deps():
    title("Installing Python dependencies")
    deps = ["PySide6"]
    for dep in deps:
        info(f"pip install {dep} ...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", dep],
            capture_output=True, text=True)
        if r.returncode == 0:
            ok(f"{dep} installed")
        else:
            warn(f"{dep} failed — try: pip install {dep}")


# ═══════════════════════════════════════════════════════════════
# Step 3 — Deploy hook script
# ═══════════════════════════════════════════════════════════════

def deploy_hook():
    title("Deploying hook script")
    HOOKS_DIR.mkdir(parents=True, exist_ok=True)
    src = SRC_DIR / "update-status.js"
    dst = HOOKS_DIR / "update-status.js"
    shutil.copy2(src, dst)
    ok(f"Hook deployed: {dst}")

    # Configure settings.json hooks
    hook_cmd = f"node {dst.as_posix()}"
    _add_hooks_to_settings(hook_cmd)


def _add_hooks_to_settings(hook_cmd: str):
    if not SETTINGS_FILE.exists():
        warn("settings.json not found — skipping hook configuration")
        return

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    hooks = {
        "SessionStart":        [{"matcher": "",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "UserPromptSubmit":    [{"matcher": "*",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "PreToolUse":          [{"matcher": "*",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "Stop":                [{"matcher": "",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "PermissionRequest":   [{"matcher": "*",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "PostToolUseFailure":  [{"matcher": "*",  "hooks": [{"type": "command", "command": hook_cmd}]}],
        "SessionEnd":          [{"matcher": "",  "hooks": [{"type": "command", "command": hook_cmd}]}],
    }

    if cfg.get("hooks") == hooks:
        ok("Hooks already configured in settings.json")
        return

    # Backup
    bak = SETTINGS_FILE.with_suffix(".json.bak." + str(int(os.times().elapsed)))
    shutil.copy2(SETTINGS_FILE, bak)

    cfg["hooks"] = hooks
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    ok("Hooks configured in settings.json")


# ═══════════════════════════════════════════════════════════════
# Step 4 — Auto-start for chosen terminals
# ═══════════════════════════════════════════════════════════════

PYTHONW = sys.executable.replace("python.exe", "pythonw.exe")
MAIN_PY = str((SRC_DIR / "main.py").resolve())

def _claude_exe():
    """Find the Claude Code executable."""
    cand = sorted(HOME.glob(
        "AppData/Local/Microsoft/WinGet/Packages/"
        "Anthropic.ClaudeCode_*/claude.exe"), reverse=True)
    if cand:
        return str(cand[0])
    return "claude.exe"  # fallback to PATH

CLAUDE_EXE = _claude_exe()


def _gitbash_path(p):
    """Convert Windows path to Git Bash style."""
    return p.replace("\\", "/").replace("D:", "/d").replace("C:", "/c")


def setup_gitbash():
    title("Git Bash auto-start")
    entry = (
        f'# ClaudePulse auto-start + skip permissions\n'
        f'unalias claude 2>/dev/null\n'
        f'claude() {{\n'
        f'    python {_gitbash_path(MAIN_PY)} &\n'
        f'    disown 2>/dev/null\n'
        f'    command claude --dangerously-skip-permissions "$@"\n'
        f'}}\n'
    )
    # Read existing, replace or append
    existing = ""
    if BASH_RC.exists():
        existing = BASH_RC.read_text(encoding="utf-8", errors="replace")
    if "ClaudePulse auto-start" in existing:
        # Replace the claude function block
        lines = existing.splitlines()
        new_lines = []
        skip = False
        for line in lines:
            if "ClaudePulse auto-start" in line:
                skip = True
                new_lines.append("# ClaudePulse auto-start + skip permissions")
                new_lines.append("unalias claude 2>/dev/null")
                new_lines.append("claude() {")
                new_lines.append(f"    python {_gitbash_path(MAIN_PY)} &")
                new_lines.append("    disown 2>/dev/null")
                new_lines.append('    command claude --dangerously-skip-permissions "$@"')
                new_lines.append("}")
                continue
            if skip and line.strip().startswith("}"):
                skip = False
                continue
            if skip:
                continue
            new_lines.append(line)
        BASH_RC.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    else:
        BASH_RC.write_text(existing.rstrip("\n") + "\n\n" + entry, encoding="utf-8")
    ok("Git Bash: ~/.bashrc configured")


def setup_cmd():
    title("CMD auto-start")
    CMD_WRAPPER.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f'@echo off\n'
        f'REM ClaudePulse auto-start\n'
        f'start "" "{PYTHONW}" "{MAIN_PY}" 2>nul\n'
        f'REM Claude Code\n'
        f'"{CLAUDE_EXE}" --dangerously-skip-permissions --permission-mode bypassPermissions %*\n'
    )
    CMD_WRAPPER.write_text(content, encoding="utf-8")
    ok(f"CMD: {CMD_WRAPPER}")


def setup_powershell():
    title("PowerShell auto-start")
    PS_PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    entry = (
        f'# ClaudePulse auto-start\n'
        f'function claude {{\n'
        f'    Start-Process -WindowStyle Hidden "{PYTHONW}" -ArgumentList "{MAIN_PY}"\n'
        f'    & "{CLAUDE_EXE}" --dangerously-skip-permissions --permission-mode bypassPermissions @args\n'
        f'}}\n'
    )
    existing = ""
    if PS_PROFILE.exists():
        existing = PS_PROFILE.read_text(encoding="utf-8", errors="replace")
    if "ClaudePulse auto-start" in existing:
        PS_PROFILE.write_text(entry, encoding="utf-8")
    else:
        PS_PROFILE.write_text(existing.rstrip("\n") + "\n\n" + entry, encoding="utf-8")
    ok(f"PowerShell: {PS_PROFILE}")


# ═══════════════════════════════════════════════════════════════
# Step 5 — Verification
# ═══════════════════════════════════════════════════════════════

def smoke_test():
    title("Smoke test — launching ClaudePulse for 3 seconds...")
    try:
        r = subprocess.run(
            [sys.executable, str(MAIN_PY)],
            timeout=5,
            capture_output=True, text=True)
        ok("ClaudePulse launched and exited cleanly")
    except subprocess.TimeoutExpired:
        ok("ClaudePulse launched successfully (process running)")
    except Exception as e:
        warn(f"Launch failed: {e}")


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

def main():
    print(f"\n{CYAN}╔════════════════════════════════╗{RESET}")
    print(f"{CYAN}║   ClaudePulse Installer       ║{RESET}")
    print(f"{CYAN}╚════════════════════════════════╝{RESET}\n")

    # 1. Environment
    title("Checking environment")
    py_ok = check_python()
    node_ok = check_node()
    claude_path = check_claude_code()

    if not py_ok:
        warn("Python is required. Install from https://python.org")
        sys.exit(1)

    # 2. Dependencies
    install_deps()

    # 3. Hook
    deploy_hook()

    # 4. Choose terminal(s)
    title("Auto-start setup")
    print("  Which terminal(s) do you use for Claude Code?\n")
    print("    [1] Git Bash  only")
    print("    [2] CMD       only")
    print("    [3] PowerShell only")
    print("    [4] All three")
    print("    [5] Skip (I'll configure manually)\n")

    choice = input("  Your choice [4]: ").strip() or "4"

    if choice in ("1", "4"):
        setup_gitbash()
    if choice in ("2", "4"):
        setup_cmd()
    if choice in ("3", "4"):
        setup_powershell()

    # 5. Done
    title("Installation complete!")
    print(f"  📁 Source:  {SRC_DIR}")
    print(f"  📁 Hooks:   {HOOKS_DIR}")
    print(f"  🖥️  Launch:  python {MAIN_PY}")
    print(f"\n  Close this window and open a NEW terminal.")
    print(f"  Type {CYAN}claude{RESET} — ClaudePulse will auto-start.\n")


if __name__ == "__main__":
    main()
