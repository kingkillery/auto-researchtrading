from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from paper_engine import PaperTradingEngine
from paper_state import JsonStateStore, default_state_path
from prepare import load_data


def load_strategy(spec: str) -> Any:
    module_name, _, class_name = spec.partition(":")
    if not module_name:
        raise ValueError("strategy spec must look like module:ClassName")
    if not class_name:
        class_name = "Strategy"

    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)
    return strategy_cls()


def snapshot_from_rows(rows: dict[str, Any]) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for symbol, row in rows.items():
        if hasattr(row, "to_dict"):
            snapshot[symbol] = dict(row.to_dict())
        else:
            snapshot[symbol] = dict(row)
    return snapshot


def emit_step(result) -> None:
    if not result.fills:
        return

    print(
        json.dumps(
            {
                "timestamp": result.timestamp,
                "equity": round(result.equity, 2),
                "fills": [
                    {
                        "symbol": fill.symbol,
                        "side": fill.side,
                        "delta": round(fill.delta, 2),
                        "exec_price": round(fill.exec_price, 4),
                        "fee": round(fill.fee, 4),
                        "pnl": round(fill.pnl, 4),
                    }
                    for fill in result.fills
                ],
            }
        )
    )


def run_replay(engine: PaperTradingEngine, split: str, limit: int | None = None) -> None:
    data = load_data(split)
    if not data:
        raise RuntimeError(f"no data available for split={split}")

    timestamps = sorted({timestamp for frame in data.values() for timestamp in frame["timestamp"].tolist()})
    if limit is not None:
        timestamps = timestamps[:limit]

    indexed = {symbol: frame.set_index("timestamp") for symbol, frame in data.items()}

    for timestamp in timestamps:
        rows = {}
        for symbol, frame in indexed.items():
            if timestamp not in frame.index:
                continue
            row = frame.loc[timestamp]
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            rows[symbol] = row

        if not rows:
            continue

        emit_step(engine.step(snapshot_from_rows(rows)))


def run_jsonl_stream(engine: PaperTradingEngine) -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        payload = json.loads(line)
        snapshot = payload["bars"] if "bars" in payload else payload
        emit_step(engine.step(snapshot))


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal paper-trading engine for Strategy.on_bar()")
    parser.add_argument("--strategy", default="strategy:Strategy", help="Strategy import path, e.g. strategy:Strategy")
    parser.add_argument("--state", default=None, help="State file path. Defaults to ~/.cache/autotrader/paper/<strategy>.json")
    parser.add_argument("--replay-split", choices=["train", "val", "test"], default=None, help="Replay a historical split instead of reading JSONL from stdin")
    parser.add_argument("--replay-limit", type=int, default=None, help="Stop replay after N timestamps")
    parser.add_argument("--reset-state", action="store_true", help="Start from a fresh state even if a saved state exists")
    parser.add_argument("--no-save", action="store_true", help="Disable persistence writes")
    args = parser.parse_args()

    strategy = load_strategy(args.strategy)
    state_path = Path(args.state) if args.state else default_state_path(args.strategy)
    state_store = None if args.no_save else JsonStateStore(state_path)

    engine = PaperTradingEngine(strategy, state_store=state_store)
    if not args.reset_state and args.replay_split is None:
        engine.load_state()

    if args.replay_split:
        run_replay(engine, args.replay_split, args.replay_limit)
    else:
        run_jsonl_stream(engine)

    final_portfolio = engine.snapshot_portfolio()
    print(
        json.dumps(
            {
                "final_equity": round(final_portfolio.equity, 2),
                "cash": round(final_portfolio.cash, 2),
                "positions": final_portfolio.positions,
                "state_path": str(state_path),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
