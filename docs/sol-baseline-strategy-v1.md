# SOL Baseline Strategy V1

Last reviewed: 2026-03-27

## Goal

Define the first baseline strategy for SOL that fits the current
`Auto-Research-Trading` harness without requiring new market structure, new
venues, or new execution infrastructure.

This baseline exists to answer one question:

Can the repo produce a simple, reproducible SOL entry/exit model on hourly bars
that survives walk-forward evaluation after fees, slippage, and funding?

## Scope

- Tradable asset: `SOL`
- Context assets: `BTC`, `ETH`
- Primary timeframe: `1h`
- Current harness shape:
  - the repo is backtest-first
  - `strategy.py` is the only mutable strategy surface for v1
  - `prepare.py`, `backtest.py`, and `benchmarks/` stay fixed

## Runtime Surfaces

- Historical backtest smoke check: `uv run backtest.py`
- Optional benchmark check: `uv run run_benchmarks.py`
- Strategy implementation surface: `strategy.py` only

Paper compatibility is a later integration concern. `paper_engine.py` and
`run_jupiter_live.py` are not the primary v1 implementation target.

## Non-Goals

- No live exchange execution
- No order book or microstructure logic
- No prediction-market dependency
- No multi-venue logic
- No claim of arbitrage
- No 15m / 4h expansion in v1

## Why This Baseline

The current harness already supports hourly OHLCV plus funding for `BTC`, `ETH`,
and `SOL`. The first strategy should fit that reality instead of inventing a new
runtime.

The baseline should also preserve the user's stated intuition:

- `RSI(8)` should matter
- entries should prefer consolidation followed by directional release
- complexity should stay low enough to audit and remove if it does not improve
  out-of-sample results

## Strategy Name

`SOL_H1_COMPRESSION_BREAKOUT_V1`

## Implementation Contract

- Implement v1 in `strategy.py` only.
- Use `Strategy.on_bar(self, bar_data, portfolio)` as the sole decision surface.
- The harness supplies a multi-symbol bar stream. The strategy may read `SOL`,
  `BTC`, and `ETH`, but it must emit orders for `SOL` only.
- Emit `prepare.Signal(symbol="SOL", target_position=<signed USD notional>, order_type="market")`.
- `BTC` and `ETH` must never emit orders.
- Do not modify `prepare.py`, `backtest.py`, or `benchmarks/`.
- If `get_state()` / `set_state()` are added later, they must remain JSON-safe
  and compatible with `paper_engine.py`.

## High-Level Model

This is a single-instrument trading strategy over a multi-symbol hourly,
bar-close input stream.

- Trade `SOL` only.
- Use `BTC` and `ETH` only as context vetoes.
- Use one regime gate.
- Use one entry engine.
- Use one exit engine.
- Use fixed sizing.

## Inputs

For `SOL`:

- `close`
- `high`
- `low`
- `volume`
- `funding_rate`

For `BTC` and `ETH`:

- `close`

## Indicators

### SOL indicators

- `RSI(8)`
- `EMA(20)`
- `EMA(72)`
- `ATR(14)`
- `rolling_high_4`: highest high of the prior 4 completed bars
- `rolling_low_4`: lowest low of the prior 4 completed bars
- `volume_median_8`: median volume of the prior 8 completed bars
- `compression_ratio`: `ATR(14) / close`
- `compression_percentile_72`: percentile of the current `compression_ratio`
  against the prior 72 completed bars

### BTC and ETH context indicators

- `EMA(72)`
- `RSI(8)`

## Regime Gate

The strategy may only open a new position if `SOL` is in one of these two states.

### Bullish consolidation

True when all conditions hold:

- `SOL close > SOL EMA(72)`
- `SOL RSI(8) >= 52`
- `compression_percentile_72 <= 35`
- `BTC` is not strongly bearish
- `ETH` is not strongly bearish

`BTC` or `ETH` is strongly bearish when:

- `close < EMA(72)` and `RSI(8) < 45`

### Bearish distribution

True when all conditions hold:

- `SOL close < SOL EMA(72)`
- `SOL RSI(8) <= 48`
- `compression_percentile_72 <= 35`
- `BTC` is not strongly bullish
- `ETH` is not strongly bullish

`BTC` or `ETH` is strongly bullish when:

- `close > EMA(72)` and `RSI(8) > 55`

### Neutral

If neither state is true, the strategy may not open a new position.

## Entry Engine

### Long entry

Open long only if the current bar closes and all conditions hold:

- regime is `bullish_consolidation`
- `SOL close > rolling_high_4`
- `SOL RSI(8)` crossed above `50` on the current bar or previous bar
- current volume is greater than or equal to `volume_median_8`
- no current SOL position is open

### Short entry

Open short only if the current bar closes and all conditions hold:

- regime is `bearish_distribution`
- `SOL close < rolling_low_4`
- `SOL RSI(8)` crossed below `50` on the current bar or previous bar
- current volume is greater than or equal to `volume_median_8`
- no current SOL position is open

## Exit Engine

### Initial risk

- Set initial stop at `1.5 x ATR(14)` from entry.
- No pyramiding.
- Only one SOL position at a time.

### Exit evaluation order

Evaluate exits in this order:

1. stop loss
2. max hold
3. RSI / EMA invalidation
4. opposite-signal reversal

If a stop, time exit, or RSI / EMA invalidation fires on a bar, set
`target_position = 0` and do not reverse until a later bar.

If no risk exit fires, a valid opposite regime may reverse directly to `+size`
or `-size` on that close.

### Long exit conditions

- bar-close stop loss breach
- max hold of `24` completed hourly bars
- `SOL close < SOL EMA(20)`
- `SOL RSI(8) < 45`
- valid short signal on a later bar close

### Short exit conditions

- bar-close stop loss breach
- max hold of `24` completed hourly bars
- `SOL close > SOL EMA(20)`
- `SOL RSI(8) > 55`
- valid long signal on a later bar close

## Position Sizing

- Base notional target: `8%` of current equity
- One open SOL position max
- No pyramiding
- No Kelly sizing in v1
- No overlay-driven size change in baseline-only mode

## Funding Treatment

The harness already applies funding to open positions.

In v1, funding is allowed as a measured result and read-only data field, but it
must not directly change entry, exit, or sizing decisions. This avoids mixing
"carry" and "direction" in the first baseline.

## State Contract

V1 does not require a custom persisted strategy schema.

- In-memory attributes inside `Strategy` are acceptable for the baseline.
- If explicit `get_state()` / `set_state()` methods are added later, they must:
  - be JSON-safe
  - include a `schema_version`
  - remain compatible with `paper_engine.py`

## Acceptance Criteria

- The strategy reads `SOL`, `BTC`, and `ETH` from the bar stream.
- The strategy emits orders for `SOL` only.
- The strategy produces signals on hourly bar close only.
- The strategy uses exactly one regime gate, one entry engine, and one exit
  engine.
- The strategy survives the current backtest harness without modifying
  `prepare.py`, `backtest.py`, or `benchmarks/`.
- The strategy is auditable in a single strategy file.

## Evaluation Rules

### Required workflow

- Validation smoke: `uv run backtest.py`
- Benchmark sanity check after material strategy changes:
  `uv run run_benchmarks.py`
- Full walk-forward evaluation:
  - load each split with `prepare.load_data(split)`
  - run each split with `prepare.run_backtest(strategy, data)`
  - report metrics for `train`, `val`, and `test` separately

### Fixed split windows

- `train`: `2023-06-01` to `2024-06-30`
- `val`: `2024-07-01` to `2025-03-31`
- `test`: `2025-04-01` to `2025-12-31`

### Harness hard cutoffs

The strategy must satisfy the current `compute_score()` hard cutoffs:

- `num_trades >= 10`
- `max_drawdown_pct <= 50`
- `final_equity >= 0.5 * initial_capital`

### Secondary metrics

Track these on each split:

- score
- Sharpe
- max drawdown
- number of trades
- win rate
- profit factor
- annual turnover

## What To Test Before Any Overlay

1. Baseline performance on `train`, `val`, and `test`
2. Sensitivity to small threshold changes
3. Long-only, short-only, and combined behavior
4. Trade concentration by regime
5. Failure behavior during trendless periods

## Follow-On Work

After this baseline is stable, the next layer is not more indicators. The next
layer is an external overlay that can only:

- block trades
- reduce size
- boost size modestly
- force a full exit

That overlay belongs outside the baseline strategy definition.
