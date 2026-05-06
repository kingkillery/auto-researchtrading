"""Avellaneda-Stoikov inspired mean-reversion — adapted for hourly bars."""
import math
import numpy as np
from prepare import Signal, PortfolioState, BarData

POSITION_SIZE_PCT = 0.05
MAX_HOLD_BARS = 24
STOP_LOSS_PCT = 0.015
PROFIT_TARGET_PCT = 0.008
EMA_PERIOD = 12
ACTIVE_SYMBOLS = ["BTC", "ETH", "SOL"]

class Strategy:
    def __init__(self):
        self.entry_prices = {}
        self.bars_held = {}

    def on_bar(self, bar_data: dict, portfolio: PortfolioState) -> list:
        signals = []
        equity = portfolio.equity if portfolio.equity > 0 else portfolio.cash

        for symbol in ACTIVE_SYMBOLS:
            if symbol not in bar_data:
                continue
            bd = bar_data[symbol]
            if len(bd.history) < EMA_PERIOD + 2:
                continue

            closes = bd.history["close"].values
            ema_val = np.mean(closes[-EMA_PERIOD:])
            mid = bd.close
            current_pos = portfolio.positions.get(symbol, 0.0)
            size = equity * POSITION_SIZE_PCT
            target = current_pos

            # Mean-reversion: deviation from EMA
            dev = (mid - ema_val) / ema_val if ema_val > 0 else 0

            if current_pos == 0:
                # Enter when price deviates from EMA
                if dev < -STOP_LOSS_PCT:
                    target = size  # price below EMA → buy
                elif dev > STOP_LOSS_PCT:
                    target = -size  # price above EMA → sell
            else:
                self.bars_held[symbol] = self.bars_held.get(symbol, 0) + 1
                entry = self.entry_prices.get(symbol, mid)
                pnl = (mid - entry) / entry
                if current_pos < 0:
                    pnl = -pnl

                # Exit on profit target, stop loss, or max hold
                if pnl > PROFIT_TARGET_PCT:
                    target = 0.0
                elif pnl < -STOP_LOSS_PCT:
                    target = 0.0
                elif self.bars_held.get(symbol, 0) >= MAX_HOLD_BARS:
                    target = 0.0
                elif abs(dev) < 0.001:
                    target = 0.0  # price returned to EMA

            if abs(target - current_pos) > 1.0:
                signals.append(Signal(symbol=symbol, target_position=target))
                if target != 0 and current_pos == 0:
                    self.entry_prices[symbol] = mid
                    self.bars_held[symbol] = 0
                elif target == 0:
                    self.entry_prices.pop(symbol, None)
                    self.bars_held.pop(symbol, None)

        return signals
