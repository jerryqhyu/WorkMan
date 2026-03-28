# TODOS

## agentpm serve --port flag

**What:** Make the listening port configurable via `--port` CLI arg and `AGENTPM_PORT` env var.
**Why:** Port 8765 will conflict with other local services. Hardcoding it is a silent failure mode for local dev tools.
**Pros:** No user friction on port conflicts; simple one-parameter CLI change.
**Cons:** Minimal — one argparse parameter.
**Context:** The `agentpm-server` entry point in `pyproject.toml` calls `main:main`. Add `--port` there. Print the URL on startup so users know which port they're on.
**Depends on / blocked by:** None.

## Approval gate — browser tab title + favicon when pending

**What:** When one or more approval requests are pending, update `document.title` to `"(N) AgentPM — approval needed"` and swap the favicon to an amber-dot variant. Reset both when all approvals are resolved.
**Why:** The approval gate has a 30-minute expiry. A user who switches to another browser tab has no ambient signal that an agent is blocked and counting down. They could return to find the run timed out and canceled.
**Pros:** Passive, non-intrusive. Browsers display tab title even when minimized. Zero server changes needed.
**Cons:** Requires an amber favicon asset (`favicon-alert.png` or SVG). Favicon swap is slightly tricky to reset reliably on tab focus.
**Context:** `document.title` update is 3 lines of React (useEffect on `pendingApprovals.length`). Favicon: add `<link id="favicon" rel="icon">` to `index.html` and update `href` from React. Standard pattern used by Gmail, GitHub, etc.
**Depends on / blocked by:** Approval banner implementation (must ship first).
