"""
Standalone probe strategy for live paper-fill verification.

This is intentionally simple: a BTC-only mean-reversion scalper designed
to produce frequent trades for testing the paper execution pipeline.
It is NOT a research candidate and should never be promoted to live.
"""

import os
import numpy as np
from prepare import Signal, PortfolioState, BarData

SYMBOL = "BTC"
POSITION_PCT = 0.005
COOLDOWN_BARS = 1
MIN_ENTRY_NOTIONAL = 50.0
TAKE_PROFIT_PCT = 0.0012
HARD_STOP_PCT = 0.0015
ATR_STOP_MULT = 1.0
ATR_LOOKBACK = 24
ENTRY_THRESHOLD = 0.00035
MAX_BAR_GAP_MS = 300_000


def _calc_atr(history, lookback):
    if len(history) < lookback + 1:
        return None
    highs = history["high"].values[-lookback:]
    lows = history["low"].values[-lookback:]
    closes = history["close"].values[-(lookback + 1) : -1]
    tr = np.maximum(
        highs - lows,
        np.maximum(np.abs(highs - closes), np.abs(lows - closes)),
    )
    return np.mean(tr)


class StrategyProbe:
    """Simple probe strategy for paper trading fill verification."""

    def __init__(self):
        self.entry_prices = {}
        self.peak_prices = {}
        self.atr_at_entry = {}
        self.exit_bar = {}
        self.bar_count = 0

    def on_bar(self, bar_data, portfolio):
        signals = []
        equity = portfolio.equity if portfolio.equity > 0 else portfolio.cash
        self.bar_count += 1

        if SYMBOL not in bar_data:
            return signals

        bd = bar_data[SYMBOL]
        if len(bd.history) < 4:
            return signals

        closes = bd.history["close"].values
        timestamps = bd.history["timestamp"].values
        mid = bd.close

        # Require regular bar cadence (no large gaps)
        recent_gaps = np.diff(timestamps[-4:])
        if len(recent_gaps) != 3 or np.max(recent_gaps) > MAX_BAR_GAP_MS:
            return signals

        # Mean-reversion signal on 1-bar return
        live_ret = (closes[-1] - closes[-2]) / closes[-2]
        bullish = live_ret < -ENTRY_THRESHOLD
        bearish = live_ret > ENTRY_THRESHOLD

        in_cooldown = (self.bar_count - self.exit_bar.get(SYMBOL, -999)) < COOLDOWN_BARS

        size = equity * POSITION_PCT
        current_pos = portfolio.positions.get(SYMBOL, 0.0)
        target = current_pos

        if current_pos == 0:
            if not in_cooldown:
                if bullish:
                    proposed = size
                    target = proposed if proposed >= MIN_ENTRY_NOTIONAL else 0.0
                elif bearish:
                    proposed = -size
                    target = proposed if abs(proposed) >= MIN_ENTRY_NOTIONAL else 0.0
        else:
            # ATR trailing stop
            atr = _calc_atr(bd.history, ATR_LOOKBACK)
            if atr is None:
                atr = self.atr_at_entry.get(SYMBOL, mid * 0.02)

            if SYMBOL not in self.peak_prices:
                self.peak_prices[SYMBOL] = mid

            if current_pos > 0:
                self.peak_prices[SYMBOL] = max(self.peak_prices[SYMBOL], mid)
                stop = self.peak_prices[SYMBOL] - ATR_STOP_MULT * atr
                if mid < stop:
                    target = 0.0
            else:
                self.peak_prices[SYMBOL] = min(self.peak_prices[SYMBOL], mid)
                stop = self.peak_prices[SYMBOL] + ATR_STOP_MULT * atr
                if mid > stop:
                    target = 0.0

            # Take profit / hard stop
            if SYMBOL in self.entry_prices:
                entry = self.entry_prices[SYMBOL]
                pnl = (mid - entry) / entry
                if current_pos < 0:
                    pnl = -pnl
                if pnl < -HARD_STOP_PCT:
                    target = 0.0
                elif pnl > TAKE_PROFIT_PCT:
                    target = 0.0

        if abs(target - current_pos) > 1.0:
            signals.append(Signal(symbol=SYMBOL, target_position=target))
            if target != 0 and current_pos == 0:
                self.entry_prices[SYMBOL] = mid
                self.peak_prices[SYMBOL] = mid
                self.atr_at_entry[SYMBOL] = _calc_atr(bd.history, ATR_LOOKBACK) or mid * 0.02
            elif target == 0:
                self.entry_prices.pop(SYMBOL, None)
                self.peak_prices.pop(SYMBOL, None)
                self.atr_at_entry.pop(SYMBOL, None)
                self.exit_bar[SYMBOL] = self.bar_count

        return signals
