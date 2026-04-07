# Repo Tooling

Use this file to map user intent to the correct repo command and expected output.

## Primary docs

- `docs/agent-harness.md`: repo-wide operating contract
- `docs/backtest-5m.md`: 5-minute replay/backtest path
- `docs/jupiter-execution.md`: Jupiter paper/live execution modes and wallet validation
- `docs/sol-baseline-strategy-v1.md`: SOL baseline implementation contract
- `CODEBASE_KNOWLEDGE_GRAPH.json`: machine-readable capability and runtime surface map
- `AUTO_RESEARCH_UI_REDESIGN_SPEC.md`: chat-first web mission-control spec
- `AUTO_RESEARCH_TUI_SPEC.md`: terminal UI spec aligned to the same operator jobs

## Stable operator findings

- The current shared workbench contract should be treated as frozen before parallel UI implementation:
  - primary read model: `/api/dashboard`
  - primary control surface: `/api/workbench/control`
- `fly_entrypoint.py` remains the shared operator control plane.
- `workbench_ctl.py` is only an HTTP client, not a launcher.
- The embedded generative artifact is additive and is the current best target for web recomposition.
- The terminal UI target should map the same operator jobs and verification model, not invent a separate backend contract.
- Keep Jupiter capability boundaries explicit across `perps`, `swaps`, `lending`, and `multiply`.
- The repo checkout is already noisy and partially dirty, so later parallel implementation should use isolated worktrees or branches.

## Tool routing

### Prepare historical data

Use when the user needs fresh cached market data.

```bash
uv run prepare.py
uv run prepare.py --symbols BTC ETH SOL
```

Expected result:

- Data cached under `~/.cache/autotrader/data/`

### Run the official hourly validation harness

Use when the user wants the standard backtest for the current `strategy.py`.

```bash
uv run backtest.py
```

Expected result:

- Console summary for the current strategy score and validation run

Notes:

- This is the official validation surface from the harness docs.
- On this Windows host it remains valid. The fixed harness now falls back to a timer when `signal.SIGALRM` is unavailable.

### Run the benchmark leaderboard

Use when the user wants current strategy context against the fixed benchmarks.

```bash
uv run run_benchmarks.py
```

Expected result:

- Benchmark comparison output in the terminal

### Run the 5-minute replay/backtest surface

Use when the user is validating an intraday idea that does not fit the fixed hourly harness.

```bash
uv run python backtest_5m.py --split val --symbols SOL
uv run python backtest_5m.py --split val --symbols SOL --refresh-data
```

Expected artifacts:

- `artifacts/backtests_5m/<strategy>_<split>/metrics.json`
- `artifacts/backtests_5m/<strategy>_<split>/equity_curve.csv`
- `artifacts/backtests_5m/<strategy>_<split>/trade_log.csv`

### Export the current equity curve

Use when the user wants the current strategy curve as a CSV.

```bash
uv run export_equity.py
```

Expected artifact:

- `equity_curve.csv`

### Export milestone equity curves

Use when the user wants historical strategy milestone curves.

```bash
uv run export_milestones.py
```

Expected result:

- Milestone equity curve outputs as defined by the script

### Generate charts from tabular results

Use when `results.tsv` already exists and the user wants chart output.

```bash
uv run generate_charts.py
```

Precondition:

- `results.tsv` must exist at the repo root

### Replay or paper-trade through the paper engine

Use when the user wants replay or simulated fills instead of the fixed validation harness.

```bash
uv run python paper_trade.py
uv run python run_jupiter_live.py --execution-mode paper
```

### Run or control the local workbench

Use when the user wants the operator workbench surface rather than backtest-only work.

```bash
uv run python fly_entrypoint.py
uv run python workbench_ctl.py status
uv run python workbench_ctl.py start-paper
uv run python workbench_ctl.py stop-paper
uv run python workbench_ctl.py restart-paper
uv run python workbench_ctl.py start-manager
uv run python workbench_ctl.py restart-manager
uv run python workbench_ctl.py stop-manager
uv run python workbench_ctl.py list-experiments
```

Important:

- `workbench_ctl.py` talks to `http://127.0.0.1:8080` by default. If that server is down, control commands fail with connection refused.
- `fly_entrypoint.py` is the launcher. `workbench_ctl.py` does not start the dashboard by itself.

### Recover a stale workbench runtime

Use when `workbench_ctl.py` reports connection refused, `:8080` is not listening, or the dashboard is down while paper/trainer worker processes are still alive.

Checks:

```bash
uv run python workbench_ctl.py status
```

If that fails, verify whether the launcher is gone but repo worker processes remain. On Windows, inspect the repo-specific process tree and confirm whether `run_jupiter_live.py` or `autoresearch_daemon.py` are orphaned.

Recovery rule:

- Restore a single clean workbench instance.
- Do not trust stale `trainer.log` or control state by themselves.
- If the launcher is dead and orphaned repo workers remain, stop those workers first, clear the stale lock at `~/.cache/autotrader/workbench/workbench.lock.json` if needed, then relaunch:

```bash
uv run python fly_entrypoint.py
uv run python workbench_ctl.py status
```

Expected healthy state:

- Dashboard responds on `http://127.0.0.1:8080/`
- `workbench_ctl.py status` returns a running dashboard plus managed paper/trainer state

### Validate or use Jupiter live execution

Read `docs/jupiter-execution.md` first.

Use validation before live mode:

```bash
uv run python run_jupiter_live.py --validate-local-wallet-setup
```

Use live mode only with explicit operator confirmation:

```bash
uv run python run_jupiter_live.py --execution-mode live --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS --live-equity-budget-usd <explicit-usd>
```

Important:

- `jup` CLI and wallet setup are host dependencies outside the repo.
- Local-wallet and external-wallet flows are different trust boundaries.
