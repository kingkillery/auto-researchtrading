"""Integration test for StrategyProbe paper feed pipeline."""

import unittest
from pathlib import Path

from paper_engine import PaperTradingEngine
from paper_state import JsonStateStore
from strategy_probe import StrategyProbe


class StrategyProbeIntegrationTest(unittest.TestCase):
    def _make_bar(self, timestamp: int, close: float) -> dict[str, float | int]:
        return {
            "timestamp": timestamp,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1.0,
            "funding_rate": 0.0,
        }

    def test_probe_enters_long_after_drop(self) -> None:
        """StrategyProbe should enter long after a 1-bar BTC drop > 0.035%."""
        probe = StrategyProbe()
        engine = PaperTradingEngine(
            probe,
            state_store=JsonStateStore(Path("/dev/null")),
            symbols=["BTC"],
        )

        base_ts = 1_000_000_000
        all_fills = []

        # Seed 4 flat bars
        for i in range(4):
            r = engine.step({"BTC": self._make_bar(base_ts + i * 300_000, 100.0)})
            all_fills.extend(r.fills)

        # Drop bar — should trigger long entry
        r = engine.step({"BTC": self._make_bar(base_ts + 4 * 300_000, 99.5)})
        all_fills.extend(r.fills)

        opens = [f for f in all_fills if f.symbol == "BTC" and f.side == "open"]
        self.assertTrue(
            len(opens) > 0,
            f"Expected BTC open fill after drop, got all fills: {all_fills}",
        )

        # Verify it's a long (positive delta)
        long_opens = [f for f in opens if f.delta > 0]
        self.assertTrue(
            len(long_opens) > 0,
            f"Expected long entry (positive delta), got: {opens}",
        )

    def test_probe_enters_short_after_rise(self) -> None:
        """StrategyProbe should enter short after a 1-bar BTC rise > 0.035%."""
        probe = StrategyProbe()
        engine = PaperTradingEngine(
            probe,
            state_store=JsonStateStore(Path("/dev/null")),
            symbols=["BTC"],
        )

        base_ts = 2_000_000_000
        all_fills = []

        for i in range(4):
            r = engine.step({"BTC": self._make_bar(base_ts + i * 300_000, 100.0)})
            all_fills.extend(r.fills)

        # Rise bar
        r = engine.step({"BTC": self._make_bar(base_ts + 4 * 300_000, 100.8)})
        all_fills.extend(r.fills)

        opens = [f for f in all_fills if f.symbol == "BTC" and f.side == "open"]
        self.assertTrue(
            len(opens) > 0,
            f"Expected BTC open fill after rise, got all fills: {all_fills}",
        )

        # Verify it's a short (negative delta)
        short_opens = [f for f in opens if f.delta < 0]
        self.assertTrue(
            len(short_opens) > 0,
            f"Expected short entry (negative delta), got: {opens}",
        )

    def test_probe_allows_immediate_reentry(self) -> None:
        """StrategyProbe allows re-entry after 1 bar (cooldown=1 is effectively 0)."""
        probe = StrategyProbe()
        engine = PaperTradingEngine(
            probe,
            state_store=JsonStateStore(Path("/dev/null")),
            symbols=["BTC"],
        )

        base_ts = 3_000_000_000
        for i in range(4):
            engine.step({"BTC": self._make_bar(base_ts + i * 300_000, 100.0)})

        # Enter long
        engine.step({"BTC": self._make_bar(base_ts + 4 * 300_000, 99.5)})

        # Exit via price recovery
        engine.step({"BTC": self._make_bar(base_ts + 5 * 300_000, 100.0)})

        # Re-enter immediately — StrategyProbe COOLDOWN_BARS=1 with < check
        # means (current - exit) < 1 is False, so re-entry is allowed
        result = engine.step({"BTC": self._make_bar(base_ts + 6 * 300_000, 99.5)})
        opens = [f for f in result.fills if f.symbol == "BTC" and f.side == "open"]

        self.assertEqual(
            1, len(opens),
            f"Expected immediate re-entry allowed, got fills: {result.fills}",
        )


if __name__ == "__main__":
    unittest.main()
