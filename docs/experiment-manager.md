# Experiment Manager

This repo now treats multi-thread Jupiter research as a message-based local
control plane instead of a single trainer loop.

## Runtime surfaces

- `uv run python experiment_manager.py`
  Runs the local experiment manager for the 10 fixed Jupiter paper threads.
- `uv run python workbench_ctl.py list-experiments`
  Lists the current thread states from the workbench API.
- `uv run python workbench_ctl.py start-experiment --experiment-id <id>`
- `uv run python workbench_ctl.py pause-experiment --experiment-id <id>`
- `uv run python workbench_ctl.py resume-experiment --experiment-id <id>`
- `uv run python workbench_ctl.py restart-experiment --experiment-id <id>`
- `uv run python workbench_ctl.py stop-experiment --experiment-id <id>`

## Message contracts

The manager persists three local message surfaces under
`~/.cache/autotrader/workbench/`:

- `experiments-control.json`
  Desired state for the manager and each thread.
- `experiments-status.json`
  Current snapshot for the manager plus all thread states.
- `experiments-events.jsonl`
  Append-only event stream for starts, completes, pauses, restarts, stops, and
  degraded runs.

The control shape is:

```json
{
  "manager": { "desired_state": "running" },
  "experiments": {
    "perps-trend-follow": {
      "desired_state": "running",
      "restart_nonce": 0
    }
  }
}
```

Each experiment snapshot includes:

- `id`
- `state`
- `desired_state`
- `iteration`
- `hypothesis`
- `objective`
- `symbols`
- `last_metrics`
- `last_started_at`
- `last_completed_at`
- `last_error`
- `degraded`
- `degraded_reasons`

Each event row includes:

- `timestamp`
- `type`
- `experiment_id`
- `payload`

## Fixed manifest

The default 10-thread registry lives in
[`docs/jupiter_experiment_threads.json`](/C:/Dev/Desktop-Projects/Auto-Research-Trading/docs/jupiter_experiment_threads.json).

Each entry defines:

- `id`
- `hypothesis`
- `objective`
- `symbols`
- `paper_budget_usd`
- `split`
- `search_space`

## Current limitation

The manager currently uses repeated `backtest_5m.py` runs as the per-thread
evaluation loop. That keeps the implementation inside the repo's existing
Python validation surface while the message contracts, isolated thread control,
and workbench integration stabilize.
