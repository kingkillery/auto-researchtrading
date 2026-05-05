# Agent Harness

This repo is a backtest-first trading research harness. The goal for agents is to keep the repository legible, reproducible, and safe to iterate on without inventing hidden workflow.

Profit is real only when net money is realized in a controlled wallet and is available to reinvest or spend. Backtest, sandbox, and score outputs are evidence, not profit. Paper wallet gains may be called `paper trading profit` only when clearly scoped to paper trading; they are not spendable real profit.

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
- `uv run python tools/research_full_horizon.py` runs the research-only full-horizon profitability leaderboard and current-strategy cost stress, writing artifacts under `artifacts/research_full_horizon/`.
- `uv run python backtest_5m.py --split val --symbols SOL` runs the canonical 5-minute validation path and writes artifacts under `artifacts/backtests_5m/`.
- `uv run run_benchmarks.py` runs the benchmark leaderboard.
- `uv run export_equity.py` writes `equity_curve.csv` for the current strategy.
- `uv run export_milestones.py` writes milestone equity curves.
- `uv run generate_charts.py` renders charts from `results.tsv`.
- `uv run python paper_trade.py` replays historical data or consumes JSONL bars through the paper engine.
- `uv run python run_jupiter_live.py --execution-mode paper` runs the live Jupiter market-data feed into the paper engine. Add `--paper-warmup-split val --paper-warmup-bars 500` to seed indicator history from cached bars before live bars arrive; warmup does not execute historical trades.
- `uv run python tools/paper_wallet_report.py` reports paper-wallet equity and `paper trading profit` without implying spendable real profit.
- `uv run python fly_entrypoint.py` launches the local workbench UI plus the managed paper-feed and experiment-manager processes. By default the managed paper feed requests `BTC ETH SOL` to match the default multi-asset strategy; set `WORKBENCH_SYMBOLS='SOL'` for SOL-only operator runs. Set `WORKBENCH_PAPER_PROFILE='trend_following'` or another profile name to run the paper feed on a specific strategy profile; when `STATE_PATH` is not set, profiled paper runs use a profile-specific state file. Set `WORKBENCH_PAPER_WARMUP_SPLIT='val'` and optionally `WORKBENCH_PAPER_WARMUP_BARS='500'` to seed paper indicator history without executing historical trades.
- `uv run python workbench_ctl.py status|start-paper|stop-paper|restart-paper|start-manager|restart-manager|stop-manager|list-experiments` controls the managed workbench processes from the CLI.
- `uv run python run_jupiter_live.py --validate-local-wallet-setup` checks whether the local-wallet Jupiter path is ready on the current machine.
- `uv run python run_jupiter_live.py --execution-mode live ...` runs the guarded Jupiter execution path. Read `docs/jupiter-execution.md` before using it.
- `node tools/jupiter-lend-advanced/repay_with_collateral_max_withdraw.mjs --preview` builds the advanced Jupiter Lend borrow-close plan without signing. Read `docs/jupiter-execution.md` before using it.
- `node tools/jupiter-perps-loans/jlp_loan_cashout.mjs --preview` previews the public Perps JLP loan cashout flow without signing. Read `docs/jupiter-execution.md` before using it.

There is still no always-on in-repo deployment target. The Jupiter live runner is an operator-invoked process, not a resident trading daemon.

For local operator runs, the workbench should stay on `127.0.0.1:8080` unless `WORKBENCH_PORT` is set explicitly. Ambient `PORT` values from unrelated shells should not move the local control plane.

## Env Contract

- Python 3.10+.
- `uv` is the preferred runner.
- No API keys are required for the current backtest/data-prep flow.
- Jupiter live execution depends on the external `jup` CLI and its wallet/key configuration.
- The advanced borrow helper under `tools/jupiter-lend-advanced/` uses isolated Node dependencies and a direct Solana keypair path rather than Jupiter CLI key management.
- The Perps JLP loan helper under `tools/jupiter-perps-loans/` uses the public Perps REST API plus a direct Solana keypair path rather than the repo's perps runner or Jupiter CLI key management.
- Fly workbench auth uses `WORKBENCH_AUTH_REQUIRED`, `WORKBENCH_AUTH_SESSION_SECRET`, and `WORKBENCH_AUTH_USERS_JSON`.
- A Fly deployment must set `WORKBENCH_AUTH_SESSION_SECRET` and `WORKBENCH_AUTH_USERS_JSON` as secrets before launch because `fly.toml` enables auth.
- `RESET_STATE=1` resets both the dashboard paper engine and the managed paper feed when launching `fly_entrypoint.py`.
- Historical data is cached at `~/.cache/autotrader/data/`.
- `results.tsv` is expected at the repo root when generating charts.
- Network access is required for `prepare.py` the first time data is fetched.

## Validation Checklist

- Confirm the repo still has a single mutable strategy surface: `strategy.py`.
- Confirm the entrypoint commands above still match the current scripts.
- For strategy changes, run `uv run backtest.py` and compare the score to baseline.
- For profitability-improvement claims, run `uv run python tools/research_full_horizon.py`, map the result to `docs/profitability-research-loop.md`, and state which evidence gates remain unknown.
- For intraday strategy validation, run `uv run python backtest_5m.py --split val --symbols SOL` and inspect `metrics.json`, `equity_curve.csv`, and `trade_log.csv` in the run artifact directory.
- For broader strategy changes, run `uv run run_benchmarks.py` as a second check.
- For Fly workbench packaging changes, run `uv run python -m unittest tests.test_fly_docker_contract`.
- For Fly auth changes, run `uv run python -m unittest tests.test_fly_auth`.
- For Fly workbench packaging changes, update `docs/fly-runtime-manifest.json` in the same change whenever runtime files, runtime directories, or repo-local managed scripts change.
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
