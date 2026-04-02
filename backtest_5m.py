"""
5-minute validation surface for strategies that are designed around intraday
replay instead of the fixed hourly harness.

This intentionally leaves prepare.py and backtest.py untouched. It reuses the
repo's portfolio semantics, scoring function, and dataclasses while making the
bar interval explicit and interval-aware.

Usage:
    uv run python backtest_5m.py --split val
    uv run python backtest_5m.py --split val --symbols SOL
    uv run python backtest_5m.py --split val --refresh-data
"""

from __future__ import annotations

import argparse
import importlib
import json
import math
import os
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

from prepare import (
    CACHE_DIR,
    DATA_DIR,
    HL_INFO_URL,
    INITIAL_CAPITAL,
    LOOKBACK_BARS,
    MAX_LEVERAGE,
    SLIPPAGE_BPS,
    SYMBOLS,
    TAKER_FEE,
    TEST_END,
    TEST_START,
    TIME_BUDGET,
    TRAIN_END,
    TRAIN_START,
    VAL_END,
    VAL_START,
    BarData,
    BacktestResult,
    PortfolioState,
    Signal,
    _download_hl_funding,
    compute_score,
)


INTERVAL = "5m"
INTERVAL_MS = 5 * 60 * 1000
FUNDING_WINDOW_MS = 8 * 60 * 60 * 1000
BARS_PER_YEAR = int((365 * 24 * 60) / 5)
DEFAULT_CHUNK_MS = 7 * 24 * 60 * 60 * 1000
BINANCE_MAX_BARS = 1000
BINANCE_KLINES_URL = "https://data-api.binance.vision/api/v3/klines"
OUTPUT_ROOT = Path("artifacts") / "backtests_5m"

SPLITS = {
    "train": (TRAIN_START, TRAIN_END),
    "val": (VAL_START, VAL_END),
    "test": (TEST_START, TEST_END),
}


def load_strategy(spec: str) -> Any:
    module_name, _, class_name = spec.partition(":")
    if not module_name or not class_name:
        raise ValueError("strategy spec must look like module:ClassName")

    module = importlib.import_module(module_name)
    try:
        strategy_cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ValueError(f"strategy class not found: {spec}") from exc
    return strategy_cls()


def default_symbols() -> list[str]:
    trade_symbol = os.environ.get("AUTOTRADER_TRADE_SYMBOL")
    if trade_symbol:
        return [trade_symbol.upper()]
    return ["SOL"]


def post_hl_with_retry(body: dict[str, Any], *, attempts: int = 6) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.post(HL_INFO_URL, json=body, timeout=30)
            if response.status_code != 429:
                response.raise_for_status()
                return response

            retry_after = response.headers.get("Retry-After")
            sleep_seconds = float(retry_after) if retry_after else min(2 ** attempt, 30)
            time.sleep(sleep_seconds)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 30))

    raise RuntimeError(f"Hyperliquid request failed after {attempts} attempts") from last_error


def get_with_retry(url: str, params: dict[str, Any], *, attempts: int = 6) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code not in {429, 418}:
                response.raise_for_status()
                return response

            retry_after = response.headers.get("Retry-After")
            sleep_seconds = float(retry_after) if retry_after else min(2 ** attempt, 30)
            time.sleep(sleep_seconds)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(min(2 ** attempt, 30))

    raise RuntimeError(f"GET {url} failed after {attempts} attempts") from last_error


def parse_date_bounds(split: str) -> tuple[int, int]:
    start_str, end_str = SPLITS[split]
    start_ms = int(pd.Timestamp(start_str, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(end_str, tz="UTC").timestamp() * 1000)
    return start_ms, end_ms


def full_dataset_bounds() -> tuple[int, int]:
    start_ms = int(pd.Timestamp(TRAIN_START, tz="UTC").timestamp() * 1000)
    end_ms = int(pd.Timestamp(TEST_END, tz="UTC").timestamp() * 1000)
    return start_ms, end_ms


def cache_path(symbol: str) -> Path:
    return Path(DATA_DIR) / f"{symbol}_{INTERVAL}.parquet"


def expected_coverage(path: Path, start_ms: int, end_ms: int) -> bool:
    if not path.exists():
        return False

    existing = pd.read_parquet(path, columns=["timestamp"])
    if existing.empty:
        return False

    min_ts = int(existing["timestamp"].min())
    max_ts = int(existing["timestamp"].max())
    return min_ts <= start_ms and max_ts >= (end_ms - INTERVAL_MS)


def download_binance_candles(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    market_symbol = f"{symbol}USDT"
    all_rows: list[dict[str, float | int]] = []
    current = start_ms

    while current < end_ms:
        params = {
            "symbol": market_symbol,
            "interval": INTERVAL,
            "startTime": current,
            "endTime": end_ms,
            "limit": BINANCE_MAX_BARS,
        }
        response = get_with_retry(BINANCE_KLINES_URL, params)
        payload = response.json()

        if not payload:
            break

        for row in payload:
            all_rows.append(
                {
                    "timestamp": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
            )

        current = int(payload[-1][0]) + INTERVAL_MS
        time.sleep(0.1)

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    frame = pd.DataFrame(all_rows)
    return frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def download_hl_interval_candles(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    all_rows: list[dict[str, float | int]] = []
    current = start_ms

    while current < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {
                "coin": symbol,
                "interval": INTERVAL,
                "startTime": current,
                "endTime": min(current + DEFAULT_CHUNK_MS, end_ms),
            },
        }
        response = post_hl_with_retry(body)
        payload = response.json()

        if not payload:
            current += DEFAULT_CHUNK_MS
            time.sleep(0.2)
            continue

        for row in payload:
            all_rows.append(
                {
                    "timestamp": int(row["t"]),
                    "open": float(row["o"]),
                    "high": float(row["h"]),
                    "low": float(row["l"]),
                    "close": float(row["c"]),
                    "volume": float(row["v"]),
                }
            )

        current = int(payload[-1]["t"]) + INTERVAL_MS
        time.sleep(0.2)

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    frame = pd.DataFrame(all_rows)
    return frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def download_interval_candles(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    candles = download_binance_candles(symbol, start_ms, end_ms)
    if not candles.empty:
        return candles
    return download_hl_interval_candles(symbol, start_ms, end_ms)


def merge_funding(frame: pd.DataFrame, symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    funding = _download_hl_funding(symbol, start_ms, end_ms)
    result = frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    if not funding.empty:
        funding = funding.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
        result = pd.merge_asof(result, funding, on="timestamp", direction="backward")
    if "funding_rate" not in result.columns:
        result["funding_rate"] = 0.0
    result["funding_rate"] = result["funding_rate"].fillna(0.0)
    return result


def ensure_5m_data(symbols: list[str], refresh: bool = False) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    start_ms, end_ms = full_dataset_bounds()

    for symbol in symbols:
        path = cache_path(symbol)
        if not refresh and expected_coverage(path, start_ms, end_ms):
            continue

        print(f"Downloading {INTERVAL} candles for {symbol}...")
        candles = download_interval_candles(symbol, start_ms, end_ms)
        if candles.empty:
            raise RuntimeError(f"no {INTERVAL} candles returned for {symbol}")

        merged = merge_funding(candles, symbol, start_ms, end_ms)
        merged.to_parquet(path, index=False)
        print(f"Saved {len(merged)} {INTERVAL} bars to {path}")


def load_5m_data(split: str, symbols: list[str]) -> dict[str, pd.DataFrame]:
    start_ms, end_ms = parse_date_bounds(split)
    result: dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        path = cache_path(symbol)
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        mask = (frame["timestamp"] >= start_ms) & (frame["timestamp"] < end_ms)
        split_frame = frame.loc[mask].reset_index(drop=True)
        if not split_frame.empty:
            result[symbol] = split_frame

    return result


def run_backtest_5m(strategy: Any, data: dict[str, pd.DataFrame]) -> tuple[BacktestResult, list[int]]:
    t_start = time.time()
    all_timestamps = set()
    for frame in data.values():
        all_timestamps.update(frame["timestamp"].tolist())
    timestamps = sorted(all_timestamps)

    if not timestamps:
        return BacktestResult(), []

    indexed = {symbol: frame.set_index("timestamp") for symbol, frame in data.items()}
    portfolio = PortfolioState(
        cash=INITIAL_CAPITAL,
        positions={},
        entry_prices={},
        equity=INITIAL_CAPITAL,
        timestamp=0,
    )

    equity_curve = [INITIAL_CAPITAL]
    equity_timestamps = [timestamps[0]]
    interval_returns: list[float] = []
    trade_log: list[tuple[str, str, float, float, float]] = []
    total_volume = 0.0
    prev_equity = INITIAL_CAPITAL
    history_buffers = {symbol: [] for symbol in data}
    funding_scale = INTERVAL_MS / FUNDING_WINDOW_MS

    for ts in timestamps:
        if (time.time() - t_start) > TIME_BUDGET:
            print(f"Stopped early after hitting the {TIME_BUDGET}s time budget.")
            break

        portfolio.timestamp = ts
        bar_data: dict[str, BarData] = {}
        for symbol in data:
            if ts not in indexed[symbol].index:
                continue

            row = indexed[symbol].loc[ts]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]

            history_buffers[symbol].append(
                {
                    "timestamp": ts,
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "funding_rate": float(row.get("funding_rate", 0.0)),
                }
            )
            if len(history_buffers[symbol]) > LOOKBACK_BARS:
                history_buffers[symbol] = history_buffers[symbol][-LOOKBACK_BARS:]

            bar_data[symbol] = BarData(
                symbol=symbol,
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                funding_rate=float(row.get("funding_rate", 0.0)),
                history=pd.DataFrame(history_buffers[symbol]),
            )

        if not bar_data:
            continue

        unrealized_pnl = 0.0
        for symbol, pos_notional in portfolio.positions.items():
            if symbol not in bar_data:
                continue
            current_price = bar_data[symbol].close
            entry_price = portfolio.entry_prices.get(symbol, current_price)
            if entry_price > 0:
                price_change = (current_price - entry_price) / entry_price
                unrealized_pnl += pos_notional * price_change

        portfolio.equity = portfolio.cash + sum(abs(value) for value in portfolio.positions.values()) + unrealized_pnl

        for symbol, pos_notional in list(portfolio.positions.items()):
            if symbol not in bar_data:
                continue
            portfolio.cash -= pos_notional * bar_data[symbol].funding_rate * funding_scale

        try:
            signals = strategy.on_bar(bar_data, portfolio) or []
        except Exception:
            signals = []

        for signal in signals:
            if signal.symbol not in bar_data:
                continue

            current_price = bar_data[signal.symbol].close
            current_pos = portfolio.positions.get(signal.symbol, 0.0)
            delta = signal.target_position - current_pos
            if abs(delta) < 1.0:
                continue

            new_positions = dict(portfolio.positions)
            new_positions[signal.symbol] = signal.target_position
            total_exposure = sum(abs(value) for value in new_positions.values())
            if total_exposure > portfolio.equity * MAX_LEVERAGE:
                continue

            slippage = current_price * SLIPPAGE_BPS / 10000.0
            exec_price = current_price + slippage if delta > 0 else current_price - slippage
            fee = abs(delta) * TAKER_FEE
            portfolio.cash -= fee
            total_volume += abs(delta)

            if signal.target_position == 0:
                pnl = 0.0
                if signal.symbol in portfolio.entry_prices:
                    entry = portfolio.entry_prices[signal.symbol]
                    if entry > 0:
                        pnl = current_pos * (exec_price - entry) / entry
                        portfolio.cash += abs(current_pos) + pnl
                    portfolio.entry_prices.pop(signal.symbol, None)
                portfolio.positions.pop(signal.symbol, None)
                trade_log.append(("close", signal.symbol, delta, exec_price, pnl))
            else:
                if current_pos == 0:
                    portfolio.cash -= abs(signal.target_position)
                    portfolio.positions[signal.symbol] = signal.target_position
                    portfolio.entry_prices[signal.symbol] = exec_price
                    trade_log.append(("open", signal.symbol, delta, exec_price, 0.0))
                else:
                    old_notional = abs(current_pos)
                    old_entry = portfolio.entry_prices.get(signal.symbol, exec_price)
                    pnl = 0.0

                    if abs(signal.target_position) < abs(current_pos):
                        reduced = abs(current_pos) - abs(signal.target_position)
                        if old_entry > 0:
                            pnl = (current_pos / abs(current_pos)) * reduced * (exec_price - old_entry) / old_entry
                        portfolio.cash += reduced + pnl
                    elif abs(signal.target_position) > abs(current_pos):
                        added = abs(signal.target_position) - abs(current_pos)
                        portfolio.cash -= added
                        if old_notional + added > 0:
                            portfolio.entry_prices[signal.symbol] = (
                                (old_entry * old_notional) + (exec_price * added)
                            ) / (old_notional + added)

                    portfolio.positions[signal.symbol] = signal.target_position
                    trade_log.append(("modify", signal.symbol, delta, exec_price, pnl))

        unrealized_pnl = 0.0
        for symbol, pos_notional in portfolio.positions.items():
            if symbol not in bar_data:
                continue
            current_price = bar_data[symbol].close
            entry_price = portfolio.entry_prices.get(symbol, current_price)
            if entry_price > 0:
                price_change = (current_price - entry_price) / entry_price
                unrealized_pnl += pos_notional * price_change

        current_equity = portfolio.cash + sum(abs(value) for value in portfolio.positions.values()) + unrealized_pnl
        equity_curve.append(current_equity)
        equity_timestamps.append(ts)

        if prev_equity > 0:
            interval_returns.append((current_equity - prev_equity) / prev_equity)
        prev_equity = current_equity

        if current_equity < INITIAL_CAPITAL * 0.01:
            break

    returns = np.array(interval_returns) if interval_returns else np.array([0.0])
    equity = np.array(equity_curve)
    sharpe = (returns.mean() / returns.std()) * math.sqrt(BARS_PER_YEAR) if returns.std() > 0 else 0.0
    final_equity = float(equity[-1]) if len(equity) else INITIAL_CAPITAL
    total_return_pct = ((final_equity - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100.0
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / np.where(peak > 0, peak, 1.0)
    max_drawdown_pct = float(drawdown.max() * 100.0) if len(drawdown) else 0.0

    close_trade_pnls = [entry[4] for entry in trade_log if entry[0] == "close"]
    if close_trade_pnls:
        wins = [pnl for pnl in close_trade_pnls if pnl > 0]
        losses = [pnl for pnl in close_trade_pnls if pnl < 0]
        win_rate_pct = (len(wins) / len(close_trade_pnls)) * 100.0
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 1e-10
        profit_factor = gross_profit / gross_loss
    else:
        win_rate_pct = 0.0
        profit_factor = 0.0

    annual_turnover = total_volume * (BARS_PER_YEAR / len(timestamps)) if timestamps else 0.0

    result = BacktestResult(
        sharpe=sharpe,
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        num_trades=len(trade_log),
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor,
        annual_turnover=annual_turnover,
        backtest_seconds=time.time() - t_start,
        equity_curve=equity_curve,
        trade_log=trade_log,
    )
    return result, equity_timestamps


def default_output_dir(strategy_spec: str, split: str) -> Path:
    safe_strategy = strategy_spec.replace(":", "_").replace("/", "_")
    return OUTPUT_ROOT / f"{safe_strategy}_{split}"


def write_artifacts(
    output_dir: Path,
    *,
    strategy_spec: str,
    split: str,
    symbols: list[str],
    result: BacktestResult,
    score: float,
    equity_timestamps: list[int],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    metrics = {
        "interval": INTERVAL,
        "split": split,
        "strategy": strategy_spec,
        "experiment_id": os.environ.get("AUTOTRADER_EXPERIMENT_ID", ""),
        "experiment_profile": os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE", "default"),
        "symbols": symbols,
        "score": score,
        "sharpe": result.sharpe,
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "num_trades": result.num_trades,
        "win_rate_pct": result.win_rate_pct,
        "profit_factor": result.profit_factor,
        "annual_turnover": result.annual_turnover,
        "backtest_seconds": result.backtest_seconds,
        "final_equity": result.equity_curve[-1] if result.equity_curve else INITIAL_CAPITAL,
        "cache_dir": CACHE_DIR,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    equity_frame = pd.DataFrame(
        {
            "timestamp": equity_timestamps[: len(result.equity_curve)],
            "equity": result.equity_curve,
        }
    )
    equity_frame.to_csv(output_dir / "equity_curve.csv", index=False)

    trades = pd.DataFrame(
        result.trade_log,
        columns=["event", "symbol", "delta", "exec_price", "pnl"],
    )
    trades.to_csv(output_dir / "trade_log.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="5-minute replay/backtest surface for intraday strategy validation")
    parser.add_argument("--strategy", default="strategy:Strategy", help="Strategy import path, e.g. strategy:Strategy")
    parser.add_argument("--split", choices=sorted(SPLITS), default="val", help="Historical split to evaluate")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to load. Defaults to AUTOTRADER_TRADE_SYMBOL or SOL")
    parser.add_argument("--refresh-data", action="store_true", help=f"Redownload cached {INTERVAL} candles before running")
    parser.add_argument("--output-dir", default=None, help="Directory for metrics.json, equity_curve.csv, and trade_log.csv")
    args = parser.parse_args()

    symbols = [symbol.upper() for symbol in (args.symbols or default_symbols())]
    ensure_5m_data(symbols, refresh=args.refresh_data)
    data = load_5m_data(args.split, symbols)
    if not data:
        raise RuntimeError(f"no {INTERVAL} data available for split={args.split} and symbols={symbols}")

    strategy = load_strategy(args.strategy)
    result, equity_timestamps = run_backtest_5m(strategy, data)
    score = compute_score(result)

    output_dir = Path(args.output_dir) if args.output_dir else default_output_dir(args.strategy, args.split)
    write_artifacts(
        output_dir,
        strategy_spec=args.strategy,
        split=args.split,
        symbols=symbols,
        result=result,
        score=score,
        equity_timestamps=equity_timestamps,
    )

    print(f"interval:           {INTERVAL}")
    print(f"split:              {args.split}")
    print(f"experiment_id:      {os.environ.get('AUTOTRADER_EXPERIMENT_ID', '')}")
    print(f"experiment_profile: {os.environ.get('AUTOTRADER_EXPERIMENT_PROFILE', 'default')}")
    print(f"symbols:            {', '.join(symbols)}")
    print(f"score:              {score:.6f}")
    print(f"sharpe:             {result.sharpe:.6f}")
    print(f"total_return_pct:   {result.total_return_pct:.6f}")
    print(f"max_drawdown_pct:   {result.max_drawdown_pct:.6f}")
    print(f"num_trades:         {result.num_trades}")
    print(f"win_rate_pct:       {result.win_rate_pct:.6f}")
    print(f"profit_factor:      {result.profit_factor:.6f}")
    print(f"annual_turnover:    {result.annual_turnover:.2f}")
    print(f"backtest_seconds:   {result.backtest_seconds:.2f}")
    print(f"artifacts:          {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
