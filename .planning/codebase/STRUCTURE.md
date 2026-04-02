# Structure

## Root layout

- `strategy.py`: current mutable strategy implementation
- `prepare.py`: fixed backtest/data harness
- `backtest.py`: fixed hourly validation entrypoint
- `backtest_5m.py`: 5-minute validation and artifact writer
- `run_benchmarks.py`: benchmark comparison runner
- `run_jupiter_live.py`: paper/live market-feed runner
- `fly_entrypoint.py`: local dashboard and subprocess supervisor
- `workbench_ctl.py`: CLI control client for the workbench server

## Runtime and execution modules

- `paper_engine.py`: paper execution loop and fills
- `paper_state.py`: JSON persistence helpers for paper/live state
- `paper_trade.py`: replay and paper-trading entrypoint
- `jupiter_execution.py`: order planning and CLI-backed live execution
- `jupiter_live_adapter.py`: public market-data adapter and bar aggregation
- `external_wallet_bridge.py`: external-wallet request review bridge
- `autoresearch_daemon.py`: autonomous experiment loop and status tracking

## Reporting and exports

- `export_equity.py`: current strategy equity export
- `export_milestones.py`: milestone equity export
- `generate_charts.py`: chart generation from result tables
- `charts/`: generated chart outputs
- `artifacts/`: 5-minute backtests and other generated outputs

## Fixed benchmark set

- `benchmarks/avellaneda_mm.py`
- `benchmarks/funding_arb.py`
- `benchmarks/mean_reversion.py`
- `benchmarks/momentum_breakout.py`
- `benchmarks/regime_mm.py`

## Docs and operator guidance

- `docs/agent-harness.md`: repo rules for agents
- `docs/backtest-5m.md`: intraday validation workflow
- `docs/jupiter-execution.md`: live execution guardrails and setup
- `docs/sol-baseline-strategy-v1.md`: strategy-specific baseline notes
- `docs/integration-status-2026-04-01.md`: integration snapshot and sequencing notes

## Non-source repo content

- `assets/`: branding and dashboard assets
- `.agents/`: repo-local skills and agent resources
- `.gstack/`: local gstack state
- root TSV/CSV/log files: experiment outputs and local workbench artifacts

## Layout characteristics

- Most operational entrypoints live at repo root rather than under a package directory
- Research outputs, runtime logs, and source files share the root, so the repo is optimized for local operator use more than library packaging
