# 5-Minute Replay / Backtest Surface

`backtest_5m.py` is the parallel validation path for intraday strategies that are not well represented by the fixed hourly harness.

It does not replace `prepare.py` or `backtest.py`. It reuses the same strategy contract, portfolio semantics, and score function, but downloads and evaluates 5-minute candles instead of hourly candles.

## Why It Exists

- The fixed harness in `prepare.py` and `backtest.py` is hourly only.
- The VWAP + 9 EMA pullback strategy is a 5-minute idea.
- Changing the fixed hourly harness would violate repo guardrails.

## Command

```bash
uv run python backtest_5m.py --split val --symbols SOL
```

Optional refresh if the 5-minute cache is stale or missing:

```bash
uv run python backtest_5m.py --split val --symbols SOL --refresh-data
```

## Defaults

- Interval: `5m`
- Split: `val`
- Symbols: `AUTOTRADER_TRADE_SYMBOL` if set, otherwise `SOL`
- Cache path: `~/.cache/autotrader/data/<SYMBOL>_5m.parquet`
- Artifact path: `artifacts/backtests_5m/<strategy>_<split>/`

## Artifacts

Each run writes:

- `metrics.json`
- `equity_curve.csv`
- `trade_log.csv`

These are intended for inspection and charting, not as replacements for the existing hourly outputs.

## Notes

- Funding is merged from Hyperliquid funding history and scaled to 5-minute bars.
- Historical 5-minute OHLCV currently comes from Binance's public market-data API because the Hyperliquid candle API does not return the repo's older 2024-2025 intraday window.
- Sharpe and turnover annualization are recalculated for a 5-minute cadence.
- The fixed `compute_score()` function is still used, so 5-minute runs are directionally comparable to the repo's existing score semantics even though the data cadence differs.
- The fixed `uv run backtest.py` path still exists for the official hourly harness and now falls back to a timer when `signal.SIGALRM` is unavailable.
