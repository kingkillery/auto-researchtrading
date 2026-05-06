"""Avellaneda-Stoikov inventory-aware market maker — ported from agent-cli."""
import math
import numpy as np
from prepare import Signal, PortfolioState, BarData

GAMMA = 0.05
K = 1.5
POSITION_SIZE_PCT = 0.08
MAX_INVENTORY_PCT = 0.25
MIN_SPREAD_BPS = 15.0
MAX_SPREAD_BPS = 300.0
VOL_WINDOW = 36
ACTIVE_SYMBOLS = ["BTC", "ETH", "SOL"]

class Strategy:
    def __init__(self):
        self.entry_prices = {}

    def _compute_vol(self, closes):
        if len(closes) < 3:
            return 0.001
        log_rets = np.diff(np.log(closes[-VOL_WINDOW:]))
        return max(np.std(log_rets), 1e-6)

    def on_bar(self, bar_data: dict, portfolio: PortfolioState) -> list:
        signals = []
        equity = portfolio.equity if portfolio.equity > 0 else portfolio.cash

        for symbol in ACTIVE_SYMBOLS:
            if symbol not in bar_data:
                continue
            bd = bar_data[symbol]
            if len(bd.history) < VOL_WINDOW:
                continue

            closes = bd.history["close"].values
            mid = bd.close
            sigma = self._compute_vol(closes)
            sigma_dollar = sigma * mid

            current_pos = portfolio.positions.get(symbol, 0.0)
            max_inv = equity * MAX_INVENTORY_PCT
            q = current_pos / max_inv if max_inv > 0 else 0.0

            # Reservation price: skew away from inventory
            T = 1.0
            r_price = mid - q * GAMMA * sigma_dollar**2 * T

            # Optimal spread
            spread = GAMMA * sigma_dollar**2 * T
            if GAMMA > 0:
                spread += (2.0 / GAMMA) * math.log(1.0 + GAMMA / K)

            half_spread = max(mid * MIN_SPREAD_BPS / 10000, min(spread / 2, mid * MAX_SPREAD_BPS / 10000))

            # Size scaled by inventory utilization
            utilization = abs(current_pos) / max_inv if max_inv > 0 else 0
            size = equity * POSITION_SIZE_PCT * max(0.1, 1.0 - utilization)

            # Directional signal based on reservation price vs mid
            price_diff_pct = (r_price - mid) / mid
            target = current_pos

            # Entry when flat
            if current_pos == 0:
                if price_diff_pct > 0.001:
                    target = size
                elif price_diff_pct < -0.001:
                    target = -size
            else:
                # Inventory reduction when reservation price flips
                if q > 0 and price_diff_pct < -0.0005:
                    target = 0.0
                elif q < 0 and price_diff_pct > 0.0005:
                    target = 0.0

                # Stop loss
                if symbol in self.entry_prices:
                    entry = self.entry_prices[symbol]
                    pnl = (mid - entry) / entry
                    if current_pos < 0:
                        pnl = -pnl
                    if pnl < -0.03:
                        target = 0.0

            if abs(target - current_pos) > 1.0:
                signals.append(Signal(symbol=symbol, target_position=target))
                if target != 0 and current_pos == 0:
                    self.entry_prices[symbol] = mid
                elif target == 0:
                    self.entry_prices.pop(symbol, None)

        return signals
