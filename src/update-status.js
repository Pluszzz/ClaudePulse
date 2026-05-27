const fs = require("fs");
const path = require("path");
const os = require("os");

const STATUS_FILE = path.join(os.homedir(), ".claude", "status", "current.json");

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
    // Timeout after 500ms in case stdin never ends
    setTimeout(() => resolve(data), 500);
  });
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

  // Read existing status to preserve fields
  let prev = {};
  try {
    prev = JSON.parse(fs.readFileSync(STATUS_FILE, "utf8"));
  } catch {}

  const project =
    cwd
      ? path.basename(cwd)
      : prev.project || "";

  const entry = {
    status,
    tool: status === "idle" || status === "starting" || status === "ended" ? "" : toolName || prev.tool || "",
    project: project || prev.project || "",
    session_id: sessionId || prev.session_id || "",
    last_update: new Date().toISOString(),
  };

  fs.mkdirSync(path.dirname(STATUS_FILE), { recursive: true });
  fs.writeFileSync(STATUS_FILE, JSON.stringify(entry, null, 2));
  process.exit(0);
}

main().catch(() => process.exit(0));
