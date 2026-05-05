from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from paper_engine import PaperTradingEngine
from paper_state import JsonStateStore
from run_jupiter_live import warmup_paper_history


class _NoopStrategy:
    def on_bar(self, bar_data, portfolio):
        raise AssertionError("warmup must not execute strategy.on_bar")


class PaperWarmupTest(unittest.TestCase):
    def test_warmup_seeds_history_without_trading(self) -> None:
        data = {
            "BTC": pd.DataFrame(
                [
                    self._row(1000, 100.0),
                    self._row(2000, 101.0),
                    self._row(3000, 102.0),
                ]
            ),
            "ETH": pd.DataFrame(
                [
                    self._row(1000, 10.0),
                    self._row(2000, 11.0),
                    self._row(3000, 12.0),
                ]
            ),
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "paper.json"
            engine = PaperTradingEngine(_NoopStrategy(), state_store=JsonStateStore(state_path), history_limit=2)
            with patch("run_jupiter_live.load_data", return_value=data):
                report = warmup_paper_history(engine, split="test", symbols=["BTC", "ETH"], limit=2)

            self.assertEqual("paper_warmup", report["type"])
            self.assertEqual(2, report["seeded_timestamps"])
            self.assertEqual(4, report["seeded_bars"])
            self.assertEqual(3000, report["latest_timestamp"])
            self.assertEqual({"BTC", "ETH"}, set(engine.history_buffers))
            self.assertEqual([2000, 3000], [row["timestamp"] for row in engine.history_buffers["BTC"]])
            self.assertEqual({}, engine.positions)
            self.assertEqual({}, engine.entry_prices)
            self.assertEqual(100000.0, engine.cash)
            self.assertTrue(state_path.exists())

    def _row(self, timestamp: int, close: float) -> dict[str, float | int]:
        return {
            "timestamp": timestamp,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        }


if __name__ == "__main__":
    unittest.main()
