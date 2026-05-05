"""
Research-only full-horizon profitability validation.

This wrapper intentionally leaves prepare.py, backtest.py, and benchmarks/
unchanged. It mirrors the fixed backtest loop closely enough to report
processed coverage, then writes durable artifacts for profitability evidence.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prepare


BENCHMARKS = [
    "benchmarks.avellaneda_mm",
    "benchmarks.regime_mm",
    "benchmarks.funding_arb",
    "benchmarks.mean_reversion",
    "benchmarks.momentum_breakout",
]


@dataclass
class ResearchRow:
    name: str
    split: str
    score: float | None
    sharpe: float | None
    total_return_pct: float | None
    max_drawdown_pct: float | None
    num_trades: int
    win_rate_pct: float | None
    profit_factor: float | None
    annual_turnover: float | None
    backtest_seconds: float
    fee_rate: float
    slippage_bps: float
    processed_bars: int
    total_bars: int
    processed_bars_pct: float
    status: str
    error: str = ""


def _total_timestamps(data: dict[str, pd.DataFrame]) -> list[int]:
    all_timestamps: set[int] = set()
    for df in data.values():
        all_timestamps.update(df["timestamp"].tolist())
    return sorted(all_timestamps)


def _run_backtest_with_coverage(strategy: Any, data: dict[str, pd.DataFrame], budget_seconds: float) -> tuple[prepare.BacktestResult, int, int, str]:
    t_start = time.time()
    timestamps = _total_timestamps(data)
    total_bars = len(timestamps)
    processed_bars = 0

    if not timestamps:
        return prepare.BacktestResult(), 0, 0, "invalid"

    indexed = {symbol: df.set_index("timestamp") for symbol, df in data.items()}
    portfolio = prepare.PortfolioState(
        cash=prepare.INITIAL_CAPITAL,
        positions={},
        entry_prices={},
        equity=prepare.INITIAL_CAPITAL,
        timestamp=0,
    )

    equity_curve = [prepare.INITIAL_CAPITAL]
    hourly_returns: list[float] = []
    trade_log: list[tuple[str, str, float, float, float]] = []
    total_volume = 0.0
    prev_equity = prepare.INITIAL_CAPITAL
    history_buffers: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in data}

    for ts in timestamps:
        if time.time() - t_start > budget_seconds:
            break

        portfolio.timestamp = ts
        processed_bars += 1

        bar_data = {}
        for symbol in data:
            if symbol not in indexed or ts not in indexed[symbol].index:
                continue
            row = indexed[symbol].loc[ts]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]

            bar_dict = {
                "timestamp": ts,
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
                "funding_rate": row.get("funding_rate", 0.0),
            }
            history_buffers[symbol].append(bar_dict)
            if len(history_buffers[symbol]) > prepare.LOOKBACK_BARS:
                history_buffers[symbol] = history_buffers[symbol][-prepare.LOOKBACK_BARS:]

            bar_data[symbol] = prepare.BarData(
                symbol=symbol,
                timestamp=ts,
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                funding_rate=row.get("funding_rate", 0.0),
                history=pd.DataFrame(history_buffers[symbol]),
            )

        if not bar_data:
            continue

        unrealized_pnl = 0.0
        for sym, pos_notional in portfolio.positions.items():
            if sym in bar_data:
                current_price = bar_data[sym].close
                entry_price = portfolio.entry_prices.get(sym, current_price)
                if entry_price > 0:
                    price_change = (current_price - entry_price) / entry_price
                    unrealized_pnl += pos_notional * price_change

        portfolio.equity = portfolio.cash + sum(abs(v) for v in portfolio.positions.values()) + unrealized_pnl

        for sym, pos_notional in list(portfolio.positions.items()):
            if sym in bar_data:
                funding_payment = pos_notional * bar_data[sym].funding_rate / 8.0
                portfolio.cash -= funding_payment

        try:
            signals = strategy.on_bar(bar_data, portfolio)
        except Exception:
            signals = []

        for sig in signals or []:
            if sig.symbol not in bar_data:
                continue

            current_price = bar_data[sig.symbol].close
            current_pos = portfolio.positions.get(sig.symbol, 0.0)
            delta = sig.target_position - current_pos

            if abs(delta) < 1.0:
                continue

            new_positions = dict(portfolio.positions)
            new_positions[sig.symbol] = sig.target_position
            total_exposure = sum(abs(v) for v in new_positions.values())
            if total_exposure > portfolio.equity * prepare.MAX_LEVERAGE:
                continue

            slippage = current_price * prepare.SLIPPAGE_BPS / 10000
            exec_price = current_price + slippage if delta > 0 else current_price - slippage
            fee = abs(delta) * prepare.TAKER_FEE
            portfolio.cash -= fee
            total_volume += abs(delta)

            pnl = 0.0
            if sig.target_position == 0:
                if sig.symbol in portfolio.entry_prices:
                    entry = portfolio.entry_prices[sig.symbol]
                    if entry > 0:
                        pnl = current_pos * (exec_price - entry) / entry
                        portfolio.cash += abs(current_pos) + pnl
                    del portfolio.entry_prices[sig.symbol]
                if sig.symbol in portfolio.positions:
                    del portfolio.positions[sig.symbol]
                trade_log.append(("close", sig.symbol, delta, exec_price, pnl))
            else:
                if current_pos == 0:
                    portfolio.cash -= abs(sig.target_position)
                    portfolio.positions[sig.symbol] = sig.target_position
                    portfolio.entry_prices[sig.symbol] = exec_price
                    trade_log.append(("open", sig.symbol, delta, exec_price, 0.0))
                else:
                    old_notional = abs(current_pos)
                    old_entry = portfolio.entry_prices.get(sig.symbol, exec_price)
                    if abs(sig.target_position) < abs(current_pos):
                        reduced = abs(current_pos) - abs(sig.target_position)
                        if old_entry > 0:
                            pnl = (current_pos / abs(current_pos)) * reduced * (exec_price - old_entry) / old_entry
                        portfolio.cash += reduced + pnl
                    elif abs(sig.target_position) > abs(current_pos):
                        added = abs(sig.target_position) - abs(current_pos)
                        portfolio.cash -= added
                        if old_notional + added > 0:
                            portfolio.entry_prices[sig.symbol] = (old_entry * old_notional + exec_price * added) / (old_notional + added)
                    portfolio.positions[sig.symbol] = sig.target_position
                    trade_log.append(("modify", sig.symbol, delta, exec_price, 0.0))

        unrealized_pnl = 0.0
        for sym, pos_notional in portfolio.positions.items():
            if sym in bar_data:
                current_price = bar_data[sym].close
                entry_price = portfolio.entry_prices.get(sym, current_price)
                if entry_price > 0:
                    price_change = (current_price - entry_price) / entry_price
                    unrealized_pnl += pos_notional * price_change

        current_equity = portfolio.cash + sum(abs(v) for v in portfolio.positions.values()) + unrealized_pnl
        equity_curve.append(current_equity)

        if prev_equity > 0:
            hourly_returns.append((current_equity - prev_equity) / prev_equity)
        prev_equity = current_equity

        if current_equity < prepare.INITIAL_CAPITAL * 0.01:
            break

    returns = np.array(hourly_returns) if hourly_returns else np.array([0.0])
    eq = np.array(equity_curve)
    sharpe = (returns.mean() / returns.std()) * np.sqrt(prepare.HOURS_PER_YEAR) if returns.std() > 0 else 0.0
    final_equity = eq[-1] if len(eq) > 0 else prepare.INITIAL_CAPITAL
    total_return_pct = (final_equity - prepare.INITIAL_CAPITAL) / prepare.INITIAL_CAPITAL * 100
    peak = np.maximum.accumulate(eq)
    drawdown = (peak - eq) / np.where(peak > 0, peak, 1)
    max_drawdown_pct = drawdown.max() * 100

    trade_pnls = [t[4] for t in trade_log if t[0] == "close"]
    if trade_pnls:
        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p < 0]
        win_rate_pct = len(wins) / len(trade_pnls) * 100
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1e-10
        profit_factor = gross_profit / gross_loss
    else:
        win_rate_pct = 0.0
        profit_factor = 0.0

    annual_turnover = total_volume * (prepare.HOURS_PER_YEAR / total_bars) if total_bars > 0 else 0.0
    status = "full-horizon" if processed_bars >= total_bars else "time-capped"

    return (
        prepare.BacktestResult(
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
        ),
        processed_bars,
        total_bars,
        status,
    )


def _row_from_result(name: str, split: str, result: prepare.BacktestResult, processed_bars: int, total_bars: int, status: str) -> ResearchRow:
    return ResearchRow(
        name=name,
        split=split,
        score=prepare.compute_score(result),
        sharpe=result.sharpe,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        num_trades=result.num_trades,
        win_rate_pct=result.win_rate_pct,
        profit_factor=result.profit_factor,
        annual_turnover=result.annual_turnover,
        backtest_seconds=result.backtest_seconds,
        fee_rate=prepare.TAKER_FEE,
        slippage_bps=prepare.SLIPPAGE_BPS,
        processed_bars=processed_bars,
        total_bars=total_bars,
        processed_bars_pct=(processed_bars / total_bars * 100.0) if total_bars else 0.0,
        status=status,
    )


def _crash_row(name: str, split: str, fee_rate: float, slippage_bps: float, error: Exception) -> ResearchRow:
    return ResearchRow(
        name=name,
        split=split,
        score=None,
        sharpe=None,
        total_return_pct=None,
        max_drawdown_pct=None,
        num_trades=0,
        win_rate_pct=None,
        profit_factor=None,
        annual_turnover=None,
        backtest_seconds=0.0,
        fee_rate=fee_rate,
        slippage_bps=slippage_bps,
        processed_bars=0,
        total_bars=0,
        processed_bars_pct=0.0,
        status="crashed",
        error=str(error),
    )


def _run_named(name: str, strategy: Any, data: dict[str, pd.DataFrame], split: str, budget_seconds: float) -> ResearchRow:
    print(f"running {name} split={split} budget_seconds={budget_seconds}", flush=True)
    try:
        result, processed_bars, total_bars, status = _run_backtest_with_coverage(strategy, data, budget_seconds)
        row = _row_from_result(name, split, result, processed_bars, total_bars, status)
        score = "NA" if row.score is None else f"{row.score:.6f}"
        print(f"finished {name} score={score} coverage={row.processed_bars_pct:.2f}% status={row.status}", flush=True)
        return row
    except Exception as exc:
        print(f"crashed {name}: {exc}", flush=True)
        return _crash_row(name, split, prepare.TAKER_FEE, prepare.SLIPPAGE_BPS, exc)


def _load_current_strategy(profile: str | None) -> Any:
    original_profile = os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE")
    if profile:
        os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = profile
    try:
        import strategy

        importlib.reload(strategy)
        return strategy.Strategy()
    finally:
        if profile:
            if original_profile is None:
                os.environ.pop("AUTOTRADER_EXPERIMENT_PROFILE", None)
            else:
                os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = original_profile


def _write_csv(path: Path, rows: list[ResearchRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run research-only full-horizon profitability evidence.")
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--budget-seconds", type=float, default=900.0)
    parser.add_argument("--output-dir", default="artifacts/research_full_horizon")
    parser.add_argument("--profile", default=None, help="Optional AUTOTRADER_EXPERIMENT_PROFILE for current strategy.")
    parser.add_argument("--skip-benchmarks", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    data = prepare.load_data(args.split)

    original_fee = prepare.TAKER_FEE
    original_slippage = prepare.SLIPPAGE_BPS
    leaderboard: list[ResearchRow] = []
    cost_stress: list[ResearchRow] = []

    try:
        prepare.TAKER_FEE = 0.0005
        prepare.SLIPPAGE_BPS = 1.0
        current = _run_named("current_strategy", _load_current_strategy(args.profile), data, args.split, args.budget_seconds)
        leaderboard.append(current)

        if not args.skip_benchmarks:
            for module_name in BENCHMARKS:
                short = module_name.split(".")[-1]
                try:
                    mod = importlib.import_module(module_name)
                    leaderboard.append(_run_named(short, mod.Strategy(), data, args.split, args.budget_seconds))
                except Exception as exc:
                    leaderboard.append(_crash_row(short, args.split, prepare.TAKER_FEE, prepare.SLIPPAGE_BPS, exc))

        for label, fee_rate, slippage_bps in [
            ("current_strategy_cost_default", 0.0005, 1.0),
            ("current_strategy_cost_x2", 0.0010, 2.0),
            ("current_strategy_cost_x3", 0.0015, 5.0),
        ]:
            prepare.TAKER_FEE = fee_rate
            prepare.SLIPPAGE_BPS = slippage_bps
            cost_stress.append(_run_named(label, _load_current_strategy(args.profile), data, args.split, args.budget_seconds))
    finally:
        prepare.TAKER_FEE = original_fee
        prepare.SLIPPAGE_BPS = original_slippage

    leaderboard.sort(key=lambda row: row.score if row.score is not None else -999999.0, reverse=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(output_dir / "leaderboard.csv", leaderboard)
    _write_csv(output_dir / "cost_stress.csv", cost_stress)

    summary = {
        "split": args.split,
        "budget_seconds": args.budget_seconds,
        "profile": args.profile or os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE") or "default",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "leaderboard": [asdict(row) for row in leaderboard],
        "cost_stress": [asdict(row) for row in cost_stress],
        "artifacts": {
            "leaderboard_csv": str(output_dir / "leaderboard.csv"),
            "cost_stress_csv": str(output_dir / "cost_stress.csv"),
            "summary_json": str(output_dir / "summary.json"),
        },
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"wrote {output_dir / 'summary.json'}")
    print(f"wrote {output_dir / 'leaderboard.csv'}")
    print(f"wrote {output_dir / 'cost_stress.csv'}")
    print()
    print("leaderboard:")
    for index, row in enumerate(leaderboard, 1):
        score = "NA" if row.score is None else f"{row.score:.6f}"
        ret = "NA" if row.total_return_pct is None else f"{row.total_return_pct:.6f}%"
        print(f"{index:2d}. {row.name:25s} score={score:>12s} ret={ret:>14s} trades={row.num_trades:6d} coverage={row.processed_bars_pct:6.2f}% status={row.status}")


if __name__ == "__main__":
    main()
