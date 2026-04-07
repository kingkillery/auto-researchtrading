# Ralph Dual UI Execution Brief

Last updated: 2026-04-06

## Purpose

This document adapts `ralph`, `parallel-ralph`, `ultrawork`, and `ART - Auto Research` to the Auto-Research dual UI campaign.

The campaign goal is to produce:

- a primary chat-first web mission-control surface
- a parallel terminal UI for the same operator jobs

## Execution order

### Stage 1: Freeze the shared operator contract

Do not start parallel implementation until the shared contract is frozen.

Frozen v1 contract:

- primary read model: `/api/dashboard`
- primary control surface: `/api/workbench/control`
- shared operator control plane: `fly_entrypoint.py`
- current auth boundary: `workbench_auth.py`
- capability model:
  - `Overview`
  - `Threads`
  - `Research`
  - `Execution`
  - `Wallet`
  - `Reports`
  - `System`

Reference artifacts:

- `CODEBASE_KNOWLEDGE_GRAPH.json`
- `AUTO_RESEARCH_UI_REDESIGN_SPEC.md`
- `AUTO_RESEARCH_TUI_SPEC.md`
- `docs/auto-research-dual-ui-campaign.md`

### Stage 2: Parallel implementation lanes

After the contract is frozen, split into three lanes:

- `web-ui`
- `terminal-ui`
- `memory-scribe`

Write overlap is not allowed between `web-ui` and `terminal-ui`.

### Stage 3: Integration and selection

After both surfaces work:

- compare operator-task speed
- compare verification clarity
- compare navigation burden
- decide whether one surface wins or both remain supported

## Lane ownership

### Web UI lane

Owns:

- `artifacts/dashboard-generative-ui/`

Does not own:

- TUI files
- backend route changes without explicit need

### Terminal UI lane

Owns:

- new terminal UI files
- strictly necessary TUI dependency/config updates

Does not own:

- web artifact files

### Memory-scribe lane

Owns:

- Obsidian note updates only

Does not own:

- repo code
- repo docs
- implementation files

## Memory-heartbeat protocol

Every implementation lane must return a `memory-heartbeat` to the leader.

Required fields:

- fact learned
- why it matters
- file or surface
- follow-on implication

Rules:

- only stable learnings belong in the heartbeat
- implementation lanes do not write durable memory directly
- the designated memory-scribe lane records heartbeats into Obsidian

## ART context updates

Future Ralph loops should inherit these stable findings:

- the current workbench contract is centered on `/api/dashboard` and `/api/workbench/control`
- `fly_entrypoint.py` remains the control-plane source of truth
- the embedded generative artifact is the correct web replacement target
- the TUI should map the same operator jobs rather than inventing a separate backend model
- Jupiter capability classes should stay distinct across `perps`, `swaps`, `lending`, and `multiply`

## Acceptance checks

### Web UI

- can identify leader, degraded threads, and next action in under 15 seconds
- all mutations still verify through the current control plane

### Terminal UI

- keyboard-first control path works for the same core operator jobs
- every mutation shows one verification step

### Memory / documentation

- durable design/build note exists in `designandbuilding-vault`
- memory-heartbeat entries are concise and stable
