# Trade Postmortems

Use this log to capture execution outcomes, classify the primary driver, and encode one concrete guardrail per distinct failure or success pattern.

Recommended minimum fields per entry:

- UTC timestamp
- snapshot
- primary driver
- what worked
- what failed
- new guardrail

## 2026-04-07T07:45:11.630Z - Auto-Research postmortem

### Snapshot
- UTC timestamp: 2026-04-07T07:45:11.630Z
- Paper equity: $100,015
- Leader thread: perps-trend-follow
- Active / degraded / failed: 10 / 0 / 0
- Selected thread: perps-trend-follow
- Thread state: running
- Thread score: 20.44

### Primary driver
- Operational

### What worked
The workbench recovered cleanly once the local launcher was brought back to the intended operator port and the control plane stayed readable.

### What failed
A stale local PORT environment variable pushed the launcher onto an unexpected port, so the room looked dead even though the process was alive.

### New guardrail
Keep local launches pinned to 127.0.0.1:8080 unless WORKBENCH_PORT is set explicitly, and let the CLI discover the active lock-file port automatically.

### Recommended follow-through
- Append this entry to docs/trade_postmortems.md
- Add the guardrail to AGENTS.md, a skill, or code if it should become enforceable
- Re-run the relevant verification command before the next live-sensitive action

## 2026-04-07T07:45:18.713Z - Auto-Research postmortem

### Snapshot
- UTC timestamp: 2026-04-07T07:45:18.713Z
- Paper equity: $100,015
- Leader thread: perps-trend-follow
- Active / degraded / failed: 10 / 0 / 0
- Selected thread: perps-trend-follow
- Thread state: running
- Thread score: 20.44

### Primary driver
- Operational

### What worked
The workbench recovered cleanly once the local launcher was brought back to the intended operator port and the control plane stayed readable.

### What failed
A stale local PORT environment variable pushed the launcher onto an unexpected port, so the room looked dead even though the process was alive.

### New guardrail
Keep local launches pinned to 127.0.0.1:8080 unless WORKBENCH_PORT is set explicitly, and let the CLI discover the active lock-file port automatically.

### Recommended follow-through
- Append this entry to docs/trade_postmortems.md
- Add the guardrail to AGENTS.md, a skill, or code if it should become enforceable
- Re-run the relevant verification command before the next live-sensitive action

## 2026-04-07T08:00:00Z - Duplicate save regression test

### Snapshot
- UTC timestamp: 2026-04-07T08:00:00Z

### Primary driver
- Operational

### What worked
- First save should append.

### What failed
- Second save should not append the same entry again.

### New guardrail
- Backend dedupe should suppress consecutive identical entries.

## 2026-04-07T08:10:00Z - Duplicate save regression test 2

### Snapshot
- UTC timestamp: 2026-04-07T08:10:00Z

### Primary driver
- Operational

