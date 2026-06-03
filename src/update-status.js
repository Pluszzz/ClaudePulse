const fs = require("fs");
const path = require("path");
const os = require("os");

const STATUS_DIR = path.join(os.homedir(), ".claude", "status");
const SESSIONS_DIR = path.join(STATUS_DIR, "sessions");
const CURRENT_FILE = path.join(STATUS_DIR, "current.json");
const CLAUDE_SESSIONS_DIR = path.join(os.homedir(), ".claude", "sessions");

// Maps hook event name to status
const EVENT_STATUS = {
  SessionStart: "starting",
  UserPromptSubmit: "running",
  PreToolUse: "running",
  PostToolUseFailure: "error",
  PermissionRequest: "waiting_approval",
  Stop: "idle",
  SessionEnd: "ended",
};

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
    setTimeout(() => resolve(data), 500);
  });
}

/**
 * Look up the session name (set via /rename) from ~/.claude/sessions/.
 * Files are named {pid}.json and contain sessionId + name.
 */
function findSessionName(sessionId) {
  if (!sessionId) return "";
  try {
    const files = fs.readdirSync(CLAUDE_SESSIONS_DIR);
    for (const file of files) {
      if (!file.endsWith(".json")) continue;
      try {
        const data = JSON.parse(
          fs.readFileSync(path.join(CLAUDE_SESSIONS_DIR, file), "utf8")
        );
        if (data.sessionId === sessionId) {
          return data.name || "";
        }
      } catch {}
    }
  } catch {}
  return "";
}

async function main() {
  const raw = await readStdin();
  let input = {};
  try {
    input = raw ? JSON.parse(raw) : {};
  } catch {}

  const event = input.hook_event_name || "";
  const status = EVENT_STATUS[event] || "running";
  const toolName = input.tool_name || "";
  const cwd = input.cwd || "";
  const sessionId = input.session_id || "";

  // Skip events without a valid session_id
  if (!sessionId || sessionId === "unknown") {
    process.exit(0);
  }

  // Look up session display name
  const sessionName = findSessionName(sessionId);

  // Read previous state for this session to preserve fields
  const sessionFile = path.join(SESSIONS_DIR, `${sessionId}.json`);
  let prev = {};
  try {
    prev = JSON.parse(fs.readFileSync(sessionFile, "utf8"));
  } catch {}

  // Build display name: {project}-{name} if renamed, else just {project}
  const project = cwd ? path.basename(cwd) : prev.project || "";
  let displayName;
  if (sessionName) {
    displayName = `${project}-${sessionName}`;
  } else if (prev.display_name && status !== "starting") {
    displayName = prev.display_name;
  } else {
    // No rename name: use project name only.
    // Deduplicate: if another session already uses this name, append a counter.
    displayName = project;
    try {
      const existing = fs.readdirSync(SESSIONS_DIR)
        .filter(f => f.endsWith(".json") && f !== `${sessionId}.json`);
      const usedNames = [];
      for (const ef of existing) {
        try {
          const ed = JSON.parse(fs.readFileSync(path.join(SESSIONS_DIR, ef), "utf8"));
          usedNames.push(ed.display_name || "");
        } catch {}
      }
      let candidate = displayName;
      let counter = 2;
      while (usedNames.includes(candidate)) {
        candidate = `${displayName} (${counter})`;
        counter++;
      }
      displayName = candidate;
    } catch {}
  }

  const entry = {
    session_id: sessionId,
    display_name: displayName,
    project: project || prev.project || "",
    status: status,
    tool: status === "idle" || status === "starting" || status === "ended"
      ? ""
      : toolName || prev.tool || "",
    cwd: cwd || prev.cwd || "",
    last_update: new Date().toISOString(),
  };

  // Write per-session file
  fs.mkdirSync(SESSIONS_DIR, { recursive: true });
  fs.writeFileSync(sessionFile, JSON.stringify(entry, null, 2));

  // Update active session pointer
  const current = {
    active_session: sessionId,
    last_update: new Date().toISOString(),
  };
  fs.writeFileSync(CURRENT_FILE, JSON.stringify(current, null, 2));

  process.exit(0);
}

main().catch(() => process.exit(0));
