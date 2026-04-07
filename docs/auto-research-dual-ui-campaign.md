# Auto-Research Dual UI Campaign

Last updated: 2026-04-06

## Shared contract

The campaign must freeze the shared operator contract before any parallel UI implementation starts.

Frozen v1 sources of truth:

- primary read model: `/api/dashboard`
- primary control surface: `/api/workbench/control`
- shared operator control plane: `fly_entrypoint.py`
- current auth boundary: `workbench_auth.py`

Parallelization rule:

- do not start parallel implementation until this shared contract is frozen

## Domains

### Foundation

- freeze operator vocabulary
- freeze capability navigation
- freeze acceptance criteria
- freeze verification language
- update ART with stable findings
- record campaign memory in Obsidian

### Web mission-control UI

- primary target
- replaces the current embedded generative surface with a chat-first mission-control composition

### Terminal UI

- parallel target
- built in Python `Textual` + `Rich`
- uses Charmbracelet as a design reference language, not the default implementation stack

### Non-design spec lane

- ACA-reviewed docs and harness updates
- campaign tracking artifacts
- memory-heartbeat aggregation

## Shared user jobs

- understand the room fast
- control experiment threads
- inspect execution readiness
- review wallet handoffs
- browse reports and system state

## Acceptance comparison

Both UI surfaces should be judged on:

- time to identify leader
- time to identify degraded threads
- time to execute one intervention
- verification clarity after action
- risk clarity for execution-related surfaces

## Memory-heartbeat rule

Every implementation lane should return a `memory-heartbeat` to the leader.

The heartbeat must contain:

- fact learned
- why it matters
- file or surface affected
- follow-on implication

Only the designated memory-scribe lane writes these into durable notes.
