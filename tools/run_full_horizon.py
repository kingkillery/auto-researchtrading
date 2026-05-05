"""
Deterministic full-horizon backtest wrapper.

Patches prepare.TIME_BUDGET to a large value so the backtest
runs to completion on all bars. This eliminates the score
variance caused by wall-clock truncation.

Usage:
    uv run python tools/run_full_horizon.py [--profile PROFILE]

Example:
    uv run python tools/run_full_horizon.py --profile regime_switching
"""

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# Patch TIME_BUDGET before importing backtest
import prepare

original_budget = prepare.TIME_BUDGET
prepare.TIME_BUDGET = 7200  # 2 hours — enough for full data

from backtest import main as backtest_main


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full-horizon backtest without time budget truncation.")
    parser.add_argument("--profile", default=None, help="AUTOTRADER_EXPERIMENT_PROFILE value")
    args = parser.parse_args()

    if args.profile:
        os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = args.profile

    print(f"TIME_BUDGET patched: {original_budget}s -> {prepare.TIME_BUDGET}s")
    print("Running full-horizon backtest...")

    return backtest_main()


if __name__ == "__main__":
    raise SystemExit(main())
