"""
Read-only paper wallet reconciliation report.

This reports paper trading profit only. It does not imply spendable real profit.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paper_state import JsonStateStore, default_state_path
from prepare import INITIAL_CAPITAL


def _load_state(path: Path) -> dict[str, Any]:
    payload = JsonStateStore(path).load()
    if not payload:
        raise SystemExit(f"paper wallet state not found: {path}")
    return payload


def _report(payload: dict[str, Any], path: Path, initial_capital: float) -> dict[str, Any]:
    engine = payload.get("engine", {})
    equity = float(engine.get("equity", initial_capital))
    cash = float(engine.get("cash", initial_capital))
    positions = {str(symbol): float(value) for symbol, value in engine.get("positions", {}).items()}
    gross_exposure = sum(abs(value) for value in positions.values())
    has_open_positions = bool(positions)
    paper_profit = equity - initial_capital
    paper_cash_delta = cash - initial_capital
    paper_return_pct = (paper_profit / initial_capital * 100.0) if initial_capital else 0.0

    return {
        "claim_scope": "paper trading profit",
        "spendable_real_profit": False,
        "realization_basis": "mark_to_market_equity" if has_open_positions else "closed_or_flat_equity",
        "state_path": str(path),
        "timestamp": int(engine.get("timestamp", 0)),
        "initial_capital": initial_capital,
        "equity": equity,
        "cash": cash,
        "positions": positions,
        "has_open_positions": has_open_positions,
        "gross_exposure": gross_exposure,
        "paper_trading_profit": paper_profit,
        "paper_cash_delta": paper_cash_delta,
        "paper_return_pct": paper_return_pct,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Report paper-wallet PnL without implying real spendable profit.")
    parser.add_argument("--state", default=None, help="Paper state file. Defaults to strategy_Strategy.json (or profiled variant).")
    parser.add_argument("--strategy-spec", default="strategy:Strategy", help="Strategy spec used for default paper state path.")
    parser.add_argument("--profile", default=None, help="Strategy profile name. When set and --state is not set, resolves to a profile-specific state file.")
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    if args.state:
        state_path = Path(args.state).expanduser()
    else:
        base = default_state_path(args.strategy_spec)
        if args.profile:
            safe_profile = "".join(
                char if char.isalnum() or char in {"-", "_"} else "_"
                for char in args.profile.strip().lower()
            )
            state_path = base.with_name(f"{base.stem}_{safe_profile}{base.suffix}")
        else:
            state_path = base
    report = _report(_load_state(state_path), state_path, args.initial_capital)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return

    print(f"claim_scope:          {report['claim_scope']}")
    print(f"spendable_real_profit:{str(report['spendable_real_profit']).lower()}")
    print(f"state_path:           {report['state_path']}")
    print(f"timestamp:            {report['timestamp']}")
    print(f"initial_capital:      {report['initial_capital']:.2f}")
    print(f"equity:               {report['equity']:.2f}")
    print(f"cash:                 {report['cash']:.2f}")
    print(f"paper_cash_delta:     {report['paper_cash_delta']:.2f}")
    print(f"has_open_positions:   {str(report['has_open_positions']).lower()}")
    print(f"gross_exposure:       {report['gross_exposure']:.2f}")
    print(f"realization_basis:    {report['realization_basis']}")
    print(f"paper_trading_profit: {report['paper_trading_profit']:.2f}")
    print(f"paper_return_pct:     {report['paper_return_pct']:.6f}")


if __name__ == "__main__":
    main()
