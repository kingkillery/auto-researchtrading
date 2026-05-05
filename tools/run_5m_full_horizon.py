import sys
sys.path.insert(0, r"C:\dev\Desktop-Projects\Auto-Research-Trading")

# Patch TIME_BUDGET before importing backtest_5m
import prepare
prepare.TIME_BUDGET = 3600  # 1 hour for full-horizon

import os
os.environ["AUTOTRADER_EXPERIMENT_PROFILE"] = "regime_switching"

from backtest_5m import main
main()
