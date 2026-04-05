# Agent Harness

This repo is a backtest-first trading research harness. The goal for agents is to keep the repository legible, reproducible, and safe to iterate on without inventing hidden workflow.

## Repo Map

- `strategy.py` - the only strategy surface intended for experiment edits.
- `prepare.py` - fixed data download, caching, backtest engine, and score calculation.
- `backtest.py` - validation entrypoint for the current strategy.
- `backtest_5m.py` - dedicated 5-minute validation surface for intraday strategies.
- `run_benchmarks.py` - compares the five reference strategies.
- `benchmarks/` - fixed benchmark implementations.
- `export_equity.py` - exports the current strategy equity curve to CSV.
- `export_milestones.py` - exports milestone equity curves by swapping in historical strategies.
- `generate_charts.py` - builds the chart set from `results.tsv`.
- `README.md`, `program.md`, `STRATEGIES.md` - narrative context, experiment rules, and strategy history.

## Runtime / Deploy Entrypoints

- `uv run prepare.py` downloads and caches historical data.
- `uv run prepare.py --symbols BTC ETH SOL` downloads a subset of symbols.
- `uv run backtest.py` runs the current `strategy.py` on validation data.
- `uv run python backtest_5m.py --split val --symbols SOL` runs the canonical 5-minute validation path and writes artifacts under `artifacts/backtests_5m/`.
- `uv run run_benchmarks.py` runs the benchmark leaderboard.
- `uv run export_equity.py` writes `equity_curve.csv` for the current strategy.
- `uv run export_milestones.py` writes milestone equity curves.
- `uv run generate_charts.py` renders charts from `results.tsv`.
- `uv run python paper_trade.py` replays historical data or consumes JSONL bars through the paper engine.
- `uv run python run_jupiter_live.py --execution-mode paper` runs the live Jupiter market-data feed into the paper engine.
- `uv run python fly_entrypoint.py` launches the local workbench UI plus the managed paper-feed and experiment-manager processes.
- `uv run python workbench_ctl.py status|start-paper|stop-paper|restart-paper|start-manager|restart-manager|stop-manager|list-experiments` controls the managed workbench processes from the CLI.
- `uv run python run_jupiter_live.py --validate-local-wallet-setup` checks whether the local-wallet Jupiter path is ready on the current machine.
- `uv run python run_jupiter_live.py --execution-mode live ...` runs the guarded Jupiter execution path. Read `docs/jupiter-execution.md` before using it.

There is still no always-on in-repo deployment target. The Jupiter live runner is an operator-invoked process, not a resident trading daemon.

## Env Contract

- Python 3.10+.
- `uv` is the preferred runner.
- No API keys are required for the current backtest/data-prep flow.
- Jupiter live execution depends on the external `jup` CLI and its wallet/key configuration.
- Historical data is cached at `~/.cache/autotrader/data/`.
- `results.tsv` is expected at the repo root when generating charts.
- Network access is required for `prepare.py` the first time data is fetched.

## Validation Checklist

- Confirm the repo still has a single mutable strategy surface: `strategy.py`.
- Confirm the entrypoint commands above still match the current scripts.
- For strategy changes, run `uv run backtest.py` and compare the score to baseline.
- For intraday strategy validation, run `uv run python backtest_5m.py --split val --symbols SOL` and inspect `metrics.json`, `equity_curve.csv`, and `trade_log.csv` in the run artifact directory.
- For broader strategy changes, run `uv run run_benchmarks.py` as a second check.
- If a doc references a path or command, verify it exists in the repo before shipping.

## Known Constraints

- `prepare.py`, `backtest.py`, and `benchmarks/` are fixed harness files.
- Backtests are time-bounded to about 120 seconds by the engine.
- The scoring function penalizes low trade count, excessive drawdown, and turnover.
- The historical validation window is fixed; do not assume access to test data during normal iteration.
- The canonical 5-minute backtest currently sources OHLCV from Binance first and Hyperliquid second; see `docs/backtest-5m.md` before changing interval assumptions.
- `generate_charts.py` and `export_milestones.py` contain hardcoded filesystem assumptions and are not portable as-is across all hosts.
- This repo is still optimized for offline research first. The Jupiter live path is intentionally explicit, guarded, and narrower than the paper/backtest surface.
- The local-wallet live path depends on a working Jupiter CLI command plus a configured key. The repo validator is the required readiness check before starting live mode.
