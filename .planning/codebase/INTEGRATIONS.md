# Integrations

## Market data providers

### CryptoCompare

- Used by `prepare.py` for primary hourly OHLCV history
- No repo-managed API credential is required for the default path

### Hyperliquid

- Used by `prepare.py` for funding history and hourly fallback candles
- Used by `backtest_5m.py` as the fallback 5-minute candle source
- Also defines the market context the research harness is targeting

### Binance

- Used by `backtest_5m.py` as the first-choice 5-minute candle source through Binance Vision data APIs

## Execution and account surfaces

### Jupiter CLI

- Live execution in `run_jupiter_live.py` depends on the external `jup` CLI described in `docs/jupiter-execution.md`
- `jupiter_execution.py` builds and submits order plans through that CLI for local-wallet mode

### External wallet bridge

- `external_wallet_bridge.py` consumes JSONL order requests emitted by `run_jupiter_live.py --wallet-mode external`
- This is a review/handoff surface, not a full signer implementation

## Local HTTP surface

### Workbench dashboard

- `fly_entrypoint.py` serves the local dashboard on `http://127.0.0.1:8080/`
- Browser UI and `workbench_ctl.py` both use this HTTP API
- Primary endpoints are `/api/dashboard`, `/api/workbench/status`, and `/api/workbench/control`

## Filesystem integration points

- Historical cache: `~/.cache/autotrader/data`
- Workbench state and logs: `~/.cache/autotrader/workbench`
- Live state root: `~/.cache/autotrader/live`
- Default paper/live strategy state paths come from `paper_state.py`

## Operational assumptions

- The repo assumes outbound network access for first-time data fetches and for live/paper market polling
- Live mode assumes host-level wallet and CLI setup outside the repo
- The workbench is local-only; there is no evidence of a production-hosted dashboard contract in the repo itself
