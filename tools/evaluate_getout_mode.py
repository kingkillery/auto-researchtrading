"""
Evaluate low-balance strategy behavior without modifying the fixed harness.

This script reuses prepare.load_data/run_backtest/compute_score while
temporarily overriding prepare.INITIAL_CAPITAL per run.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import prepare


@dataclass
class EvalRow:
    profile: str
    capital: float
    score: float
    sharpe: float
    total_return_pct: float
    max_drawdown_pct: float
    num_trades: int
    win_rate_pct: float
    profit_factor: float
    annual_turnover: float


def run_eval(profile: str, capital: float, split: str) -> EvalRow:
    original_capital = prepare.INITIAL_CAPITAL
    original_profile = os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE")
    try:
        prepare.INITIAL_CAPITAL = float(capital)
        os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = profile

        import strategy

        importlib.reload(strategy)
        data = prepare.load_data(split)
        result = prepare.run_backtest(strategy.Strategy(), data)
        score = prepare.compute_score(result)
        return EvalRow(
            profile=profile,
            capital=float(capital),
            score=score,
            sharpe=result.sharpe,
            total_return_pct=result.total_return_pct,
            max_drawdown_pct=result.max_drawdown_pct,
            num_trades=result.num_trades,
            win_rate_pct=result.win_rate_pct,
            profit_factor=result.profit_factor,
            annual_turnover=result.annual_turnover,
        )
    finally:
        prepare.INITIAL_CAPITAL = original_capital
        if original_profile is None:
            os.environ.pop("AUTOTRADER_EXPERIMENT_PROFILE", None)
        else:
            os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = original_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate getout mode at low balances.")
    parser.add_argument("--split", default="val", choices=["train", "val", "test"])
    parser.add_argument("--capitals", nargs="+", type=float, default=[40.0, 50.0, 60.0])
    parser.add_argument("--profiles", nargs="+", default=["default", "getout_mode"])
    args = parser.parse_args()

    rows: list[EvalRow] = []
    for profile in args.profiles:
        for capital in args.capitals:
            rows.append(run_eval(profile=profile, capital=capital, split=args.split))

    rows.sort(key=lambda row: (row.capital, row.score), reverse=False)
    for row in rows:
        print(
            f"profile={row.profile:12} capital={row.capital:6.2f} "
            f"score={row.score:10.6f} sharpe={row.sharpe:10.6f} "
            f"ret={row.total_return_pct:10.6f} dd={row.max_drawdown_pct:8.6f} "
            f"trades={row.num_trades:6d} win={row.win_rate_pct:8.3f} "
            f"pf={row.profit_factor:8.3f} turnover={row.annual_turnover:14.2f}"
        )


if __name__ == "__main__":
    main()
