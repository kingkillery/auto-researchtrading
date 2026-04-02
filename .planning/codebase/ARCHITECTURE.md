# Architecture

## High-level shape

The repo has three connected layers:

1. Fixed research harness for downloading data, running backtests, and computing scores
2. Strategy and execution layer that turns bars plus portfolio state into target positions
3. Local operator workbench that supervises paper-feed and trainer subprocesses and exposes a small HTTP control plane

## Core research flow

- `prepare.py` owns historical data download, cache layout, shared dataclasses, the backtest engine, and score calculation
- `backtest.py` imports `Strategy` from `strategy.py`, loads validation data through `prepare.py`, runs the fixed hourly evaluation, and prints score metrics
- `run_benchmarks.py` evaluates fixed reference strategies from `benchmarks/`

This makes `strategy.py` the main experimentation seam while the engine and benchmark surfaces stay stable.

## Strategy contract

- `strategy.py` imports `BarData`, `PortfolioState`, and `Signal` from `prepare.py`
- `Strategy.on_bar()` is the decision boundary for both backtests and replay/live-style runners
- The strategy can persist lightweight JSON-safe internal state with `get_state()` and `set_state()`

## Intraday and replay flow

- `backtest_5m.py` reuses the repo’s dataclasses and score semantics while sourcing 5-minute bars from Binance first and Hyperliquid second
- `paper_trade.py` and `paper_engine.py` reuse the same strategy contract for replayed or synthetic live bars
- `paper_state.py` provides JSON persistence for long-running paper sessions

## Workbench architecture

- `fly_entrypoint.py` hosts a `ThreadingHTTPServer`
- It supervises two managed subprocess slots: paper feed and trainer
- The paper slot usually runs `run_jupiter_live.py --execution-mode paper`
- The trainer slot usually runs the continuous validation loop based on `backtest_5m.py`
- `workbench_ctl.py` is only an HTTP client for the workbench API; it does not supervise processes itself

## Control and status flow

- Browser and CLI both call `GET /api/workbench/status` and `POST /api/workbench/control` on the local dashboard
- `fly_entrypoint.py` writes JSON status snapshots under `~/.cache/autotrader/workbench`
- Paper engine state is read from `paper_state.py` storage and rendered into the dashboard payload

## Live execution path

- `run_jupiter_live.py` is the orchestration entrypoint for both paper and guarded live modes
- `jupiter_live_adapter.py` handles public market-data polling and bar synthesis
- `jupiter_execution.py` converts strategy target deltas into CLI-backed Jupiter execution plans
- `external_wallet_bridge.py` is a sidecar review surface for external-wallet JSONL order requests rather than a signer itself

## Recent reliability change

- `fly_entrypoint.py` and `autoresearch_daemon.py` now write status files via unique temp paths plus `os.replace` retries instead of a shared fixed temp file
- This change removes the Windows race that was causing `PermissionError` on `trainer-status.json.tmp`
