"""
Default hourly ensemble strategy with optional alternate profiles.

The default path is a balanced six-signal ensemble:
- fast RSI(8) regime check
- EMA(7/26) trend confirmation
- MACD(14,23,9) momentum confirmation
- BB width compression as a stricter quality gate

"""

import os

import numpy as np
import pandas as pd
from prepare import Signal, PortfolioState, BarData, INITIAL_CAPITAL

ACTIVE_SYMBOLS = ["BTC", "ETH", "SOL"]
SYMBOL_WEIGHTS = {"BTC": 0.33, "ETH": 0.33, "SOL": 0.33}

SHORT_WINDOW = 6
MED_WINDOW = 12
MED2_WINDOW = 24
LONG_WINDOW = 36
EMA_FAST = 10  # tuned from grid search: 17.49 vs 17.47 at 7/26
EMA_SLOW = 34  # tuned from grid search
RSI_PERIOD = 8
RSI_BULL = 50
RSI_BEAR = 50
RSI_OVERBOUGHT = 69
RSI_OVERSOLD = 31

MACD_FAST = 14
MACD_SLOW = 23
MACD_SIGNAL = 9

BB_PERIOD = 10  # tuned from grid search: 17.52 vs 17.47 at 7
BB_COMPRESSION_PERCENTILE = 40

FUNDING_LOOKBACK = 24
FUNDING_BOOST = 0.0
BASE_POSITION_PCT = 0.08
VOL_LOOKBACK = 36
TARGET_VOL = 0.015
ATR_LOOKBACK = 24
ATR_STOP_MULT = 5.5
TAKE_PROFIT_PCT = 99.0
BASE_THRESHOLD = 0.008  # tuned from grid search: 17.47 vs 16.84 at 0.012
BTC_OPPOSE_THRESHOLD = -99.0

PYRAMID_THRESHOLD = 0.015
PYRAMID_SIZE = 0.0
CORR_LOOKBACK = 72
HIGH_CORR_THRESHOLD = 99.0

DD_REDUCE_THRESHOLD = 99.0
DD_REDUCE_SCALE = 0.5

COOLDOWN_BARS = 2
MIN_VOTES = 4  # out of 6 now

DEFAULT_EXPERIMENT_PROFILE = "impact_aware_sizing"  # promoted from hourly profile sweep (score 17.53)

def ema(values, span):
    alpha = 2.0 / (span + 1)
    result = np.empty_like(values, dtype=float)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = alpha * values[i] + (1 - alpha) * result[i - 1]
    return result

def calc_rsi(closes, period):
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-(period+1):])
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains)
    avg_loss = np.mean(losses)
    rs = avg_gain / max(avg_loss, 1e-10)
    return 100 - 100 / (1 + rs)


class Strategy:
    def __init__(self):
        self.profile = os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE", DEFAULT_EXPERIMENT_PROFILE).strip().lower() or DEFAULT_EXPERIMENT_PROFILE
        self.experiment_id = os.environ.get("AUTOTRADER_EXPERIMENT_ID", "").strip()
        self.entry_prices = {}
        self.peak_prices = {}
        self.atr_at_entry = {}
        self.btc_momentum = 0.0
        self.pyramided = {}
        self.peak_equity = INITIAL_CAPITAL
        self.exit_bar = {}
        self.bar_count = 0

    def _runtime_config(self):
        config = {
            "active_symbols": ACTIVE_SYMBOLS,
            "symbol_weights": SYMBOL_WEIGHTS,
            "base_position_pct": BASE_POSITION_PCT,
            "cooldown_bars": COOLDOWN_BARS,
            "min_entry_notional": 1.0,
        }


        return config

    def _profile_signal_plan(
        self,
        *,
        symbol,
        ret_vshort,
        ret_short,
        ret_med,
        dyn_threshold,
        ema_bull,
        ema_bear,
        ema_fast_value,
        ema_slow_value,
        rsi,
        macd_hist,
        bb_compressed,
        avg_funding,
        realized_vol,
        rank_map,
    ):
        min_votes = MIN_VOTES
        atr_stop_mult = ATR_STOP_MULT
        take_profit_pct = TAKE_PROFIT_PCT
        size_scale = 1.0

        trend_bull = [ret_short > dyn_threshold, ret_vshort > dyn_threshold * 0.7, ema_bull, rsi > RSI_BULL, macd_hist > 0, bb_compressed]
        trend_bear = [ret_short < -dyn_threshold, ret_vshort < -dyn_threshold * 0.7, ema_bear, rsi < RSI_BEAR, macd_hist < 0, bb_compressed]

        if self.profile == "trend_following":
            atr_stop_mult = 6.8
            size_scale = 1.1
            bull_checks = trend_bull
            bear_checks = trend_bear
        elif self.profile == "mean_reversion":
            min_votes = 4
            atr_stop_mult = 4.0
            take_profit_pct = 0.03
            bull_checks = [
                ret_short < -dyn_threshold * 1.1,
                ret_vshort < -dyn_threshold * 0.8,
                rsi <= RSI_OVERSOLD + 6,
                macd_hist > -0.015,
                ret_med > -dyn_threshold * 2.5,
                not ema_bear,
            ]
            bear_checks = [
                ret_short > dyn_threshold * 1.1,
                ret_vshort > dyn_threshold * 0.8,
                rsi >= RSI_OVERBOUGHT - 6,
                macd_hist < 0.015,
                ret_med < dyn_threshold * 2.5,
                not ema_bull,
            ]
        elif self.profile == "regime_switching":
            atr_stop_mult = 5.0 if realized_vol <= TARGET_VOL else 4.2
            take_profit_pct = 0.045
            if bb_compressed or realized_vol <= TARGET_VOL:
                bull_checks = [trend_bull[0], trend_bull[1], trend_bull[2], trend_bull[4], ret_med > 0, bb_compressed]
                bear_checks = [trend_bear[0], trend_bear[1], trend_bear[2], trend_bear[4], ret_med < 0, bb_compressed]
            else:
                bull_checks = [
                    ret_short < -dyn_threshold,
                    ret_vshort < -dyn_threshold * 0.7,
                    rsi <= RSI_OVERSOLD + 5,
                    macd_hist > -0.02,
                    ret_med > -dyn_threshold * 2,
                    not ema_bear,
                ]
                bear_checks = [
                    ret_short > dyn_threshold,
                    ret_vshort > dyn_threshold * 0.7,
                    rsi >= RSI_OVERBOUGHT - 5,
                    macd_hist < 0.02,
                    ret_med < dyn_threshold * 2,
                    not ema_bull,
                ]
        elif self.profile == "carry_aware_exits":
            atr_stop_mult = 4.8
            take_profit_pct = 0.04
            size_scale = 1.15 if avg_funding <= 0 else 0.55
            bull_checks = trend_bull[:]
            bear_checks = trend_bear[:]
            bull_checks[5] = bb_compressed or avg_funding <= 0
            bear_checks[5] = bb_compressed or avg_funding >= 0
        elif self.profile == "impact_aware_sizing":
            atr_stop_mult = 5.0
            size_scale = max(0.3, min(1.0, TARGET_VOL / max(realized_vol, TARGET_VOL)))
            bull_checks = trend_bull
            bear_checks = trend_bear
        elif self.profile == "liquidation_buffer":
            atr_stop_mult = 8.0
            size_scale = 0.45
            bull_checks = trend_bull
            bear_checks = trend_bear
        elif self.profile == "limit_pullback":
            min_votes = 4
            atr_stop_mult = 4.6
            take_profit_pct = 0.035
            bull_checks = [
                ret_med > dyn_threshold,
                ret_short > 0,
                ret_vshort < 0,
                ema_bull,
                rsi < 58,
                bb_compressed,
            ]
            bear_checks = [
                ret_med < -dyn_threshold,
                ret_short < 0,
                ret_vshort > 0,
                ema_bear,
                rsi > 42,
                bb_compressed,
            ]
        elif self.profile == "relative_strength_rotation":
            min_votes = 4
            atr_stop_mult = 5.2
            rank = rank_map.get(symbol, 99)
            size_scale = 1.45 if rank == 1 else 0.15
            bull_checks = [rank == 1, ret_med > dyn_threshold, ema_bull, macd_hist > 0, rsi > RSI_BULL, bb_compressed]
            bear_checks = [rank == 1, ret_med < -dyn_threshold, ema_bear, macd_hist < 0, rsi < RSI_BEAR, bb_compressed]
        elif self.profile == "compression_breakout":
            min_votes = 4
            atr_stop_mult = 5.8
            take_profit_pct = 0.05
            size_scale = max(0.3, min(1.0, TARGET_VOL / max(realized_vol, TARGET_VOL)))
            bull_checks = [bb_compressed, ret_short > dyn_threshold, ret_vshort > dyn_threshold * 0.7, ema_bull, macd_hist > 0, ret_med > 0]
            bear_checks = [bb_compressed, ret_short < -dyn_threshold, ret_vshort < -dyn_threshold * 0.7, ema_bear, macd_hist < 0, ret_med < 0]
        elif self.profile == "failure_reversal":
            min_votes = 4
            atr_stop_mult = 4.2
            take_profit_pct = 0.025
            bull_checks = [
                ret_vshort < -dyn_threshold * 1.1,
                ret_short < -dyn_threshold * 0.8,
                rsi <= RSI_OVERSOLD + 4,
                macd_hist > -0.01,
                ret_med > -dyn_threshold * 2,
                ema_fast_value >= ema_slow_value * 0.985,
            ]
            bear_checks = [
                ret_vshort > dyn_threshold * 1.1,
                ret_short > dyn_threshold * 0.8,
                rsi >= RSI_OVERBOUGHT - 4,
                macd_hist < 0.01,
                ret_med < dyn_threshold * 2,
                ema_fast_value <= ema_slow_value * 1.015,
            ]
        else:
            bull_checks = trend_bull
            bear_checks = trend_bear

        return {
            "bull_votes": sum(bull_checks),
            "bear_votes": sum(bear_checks),
            "min_votes": min_votes,
            "atr_stop_mult": atr_stop_mult,
            "take_profit_pct": take_profit_pct,
            "size_scale": size_scale,
        }

    def _calc_atr(self, history, lookback):
        if len(history) < lookback + 1:
            return None
        highs = history["high"].values[-lookback:]
        lows = history["low"].values[-lookback:]
        closes = history["close"].values[-(lookback+1):-1]
        tr = np.maximum(highs - lows,
                        np.maximum(np.abs(highs - closes), np.abs(lows - closes)))
        return np.mean(tr)

    def _calc_vol(self, closes, lookback):
        if len(closes) < lookback:
            return TARGET_VOL
        log_rets = np.diff(np.log(closes[-lookback:]))
        return max(np.std(log_rets), 1e-6)

    def _calc_correlation(self, bar_data):
        if "BTC" not in bar_data or "ETH" not in bar_data:
            return 0.5
        btc_h = bar_data["BTC"].history
        eth_h = bar_data["ETH"].history
        if len(btc_h) < CORR_LOOKBACK or len(eth_h) < CORR_LOOKBACK:
            return 0.5
        btc_rets = np.diff(np.log(btc_h["close"].values[-CORR_LOOKBACK:]))
        eth_rets = np.diff(np.log(eth_h["close"].values[-CORR_LOOKBACK:]))
        if len(btc_rets) < 10:
            return 0.5
        corr = np.corrcoef(btc_rets, eth_rets)[0, 1]
        return corr if not np.isnan(corr) else 0.5

    def _calc_macd(self, closes):
        if len(closes) < MACD_SLOW + MACD_SIGNAL + 5:
            return 0.0
        fast_ema = ema(closes[-(MACD_SLOW + MACD_SIGNAL + 5):], MACD_FAST)
        slow_ema = ema(closes[-(MACD_SLOW + MACD_SIGNAL + 5):], MACD_SLOW)
        macd_line = fast_ema - slow_ema
        signal_line = ema(macd_line, MACD_SIGNAL)
        return macd_line[-1] - signal_line[-1]

    def _calc_bb_width_pctile(self, closes, period):
        """Calculate current BB width percentile over lookback."""
        if len(closes) < period * 3:
            return 50.0
        s = pd.Series(closes)
        rolling_mean = s.rolling(window=period).mean()
        rolling_std = s.rolling(window=period).std()
        widths = (2 * rolling_std / rolling_mean).values
        # Match original indexing: original i ranges from period*2 to len(closes)-1
        # Pandas rolling: widths[k] = window closes[k-period+1:k+1]
        # We want k+1 = i, so k = i-1 -> first k = period*2 - 1, last k = len(closes)-2
        valid_widths = widths[period * 2 - 1 : -1]
        if len(valid_widths) < 2:
            return 50.0
        current_width = valid_widths[-1]
        pctile = 100 * np.sum(valid_widths <= current_width) / len(valid_widths)
        return pctile

    def on_bar(self, bar_data, portfolio):
        signals = []
        equity = portfolio.equity if portfolio.equity > 0 else portfolio.cash
        runtime = self._runtime_config()
        active_symbols = runtime["active_symbols"]
        symbol_weights = runtime["symbol_weights"]
        base_position_pct = runtime["base_position_pct"]
        cooldown_bars = runtime["cooldown_bars"]
        min_entry_notional = runtime["min_entry_notional"]
        self.bar_count += 1

        self.peak_equity = max(self.peak_equity, equity)
        current_dd = (self.peak_equity - equity) / self.peak_equity
        dd_scale = 1.0
        if current_dd > DD_REDUCE_THRESHOLD:
            dd_scale = max(DD_REDUCE_SCALE, 1.0 - (current_dd - DD_REDUCE_THRESHOLD) * 5)

        if "BTC" in bar_data and len(bar_data["BTC"].history) >= LONG_WINDOW + 1:
            btc_closes = bar_data["BTC"].history["close"].values
            self.btc_momentum = (btc_closes[-1] - btc_closes[-MED2_WINDOW]) / btc_closes[-MED2_WINDOW]

        btc_eth_corr = self._calc_correlation(bar_data)
        high_corr = btc_eth_corr > HIGH_CORR_THRESHOLD
        rank_map = {}
        if self.profile == "relative_strength_rotation":
            strengths = []
            for rank_symbol in active_symbols:
                if rank_symbol not in bar_data:
                    continue
                rank_history = bar_data[rank_symbol].history["close"].values
                if len(rank_history) < MED2_WINDOW + 1:
                    continue
                rank_strength = (rank_history[-1] - rank_history[-MED2_WINDOW]) / rank_history[-MED2_WINDOW]
                strengths.append((rank_symbol, rank_strength))
            strengths.sort(key=lambda item: item[1], reverse=True)
            rank_map = {rank_symbol: index + 1 for index, (rank_symbol, _) in enumerate(strengths)}

        for symbol in active_symbols:
            if symbol not in bar_data:
                continue
            bd = bar_data[symbol]
            if len(bd.history) < max(LONG_WINDOW, EMA_SLOW, MACD_SLOW + MACD_SIGNAL + 5, BB_PERIOD * 3) + 1:
                continue

            closes = bd.history["close"].values
            mid = bd.close

            realized_vol = self._calc_vol(closes, VOL_LOOKBACK)
            vol_ratio = realized_vol / TARGET_VOL
            dyn_threshold = BASE_THRESHOLD * (0.3 + vol_ratio * 0.7)
            dyn_threshold = max(0.005, min(0.020, dyn_threshold))

            ret_vshort = (closes[-1] - closes[-SHORT_WINDOW]) / closes[-SHORT_WINDOW]
            ret_short = (closes[-1] - closes[-MED_WINDOW]) / closes[-MED_WINDOW]
            ret_med = (closes[-1] - closes[-MED2_WINDOW]) / closes[-MED2_WINDOW]
            ema_fast_arr = ema(closes[-(EMA_SLOW+10):], EMA_FAST)
            ema_slow_arr = ema(closes[-(EMA_SLOW+10):], EMA_SLOW)
            ema_bull = ema_fast_arr[-1] > ema_slow_arr[-1]
            ema_bear = ema_fast_arr[-1] < ema_slow_arr[-1]

            rsi = calc_rsi(closes, RSI_PERIOD)

            macd_hist = self._calc_macd(closes)

            # BB width: low percentile = compression = pending breakout
            bb_pctile = self._calc_bb_width_pctile(closes, BB_PERIOD)
            bb_compressed = bb_pctile < BB_COMPRESSION_PERCENTILE

            funding_rates = bd.history["funding_rate"].values[-FUNDING_LOOKBACK:]
            avg_funding = np.mean(funding_rates) if len(funding_rates) >= FUNDING_LOOKBACK else 0.0

            profile_plan = self._profile_signal_plan(
                symbol=symbol,
                ret_vshort=ret_vshort,
                ret_short=ret_short,
                ret_med=ret_med,
                dyn_threshold=dyn_threshold,
                ema_bull=ema_bull,
                ema_bear=ema_bear,
                ema_fast_value=ema_fast_arr[-1],
                ema_slow_value=ema_slow_arr[-1],
                rsi=rsi,
                macd_hist=macd_hist,
                bb_compressed=bb_compressed,
                avg_funding=avg_funding,
                realized_vol=realized_vol,
                rank_map=rank_map,
            )

            bull_votes = profile_plan["bull_votes"]
            bear_votes = profile_plan["bear_votes"]
            min_votes = profile_plan["min_votes"]
            atr_stop_mult = profile_plan["atr_stop_mult"]
            take_profit_pct = profile_plan["take_profit_pct"]
            size_scale = profile_plan["size_scale"]

            btc_confirm = True
            if symbol != "BTC":
                if bull_votes >= min_votes and self.btc_momentum < BTC_OPPOSE_THRESHOLD:
                    btc_confirm = False
                if bear_votes >= min_votes and self.btc_momentum > -BTC_OPPOSE_THRESHOLD:
                    btc_confirm = False

            bullish = bull_votes >= min_votes and btc_confirm
            bearish = bear_votes >= min_votes and btc_confirm

            in_cooldown = (self.bar_count - self.exit_bar.get(symbol, -999)) < cooldown_bars

            vol_scale = 1.0
            weight = symbol_weights.get(symbol, 0.33)
            if high_corr and symbol == "SOL":
                weight *= 0.5
            mom_strength = abs(ret_short) / dyn_threshold
            strength_scale = max(0.65, min(1.35, mom_strength))
            strength_scale *= size_scale
            size = equity * base_position_pct * weight * vol_scale * strength_scale * dd_scale

            current_pos = portfolio.positions.get(symbol, 0.0)
            target = current_pos

            if current_pos == 0:
                if not in_cooldown:
                    funding_mult = 1.0
                    if bullish:
                        if avg_funding < 0:
                            funding_mult = 1.0 + FUNDING_BOOST
                        proposed = size * funding_mult
                        target = proposed if abs(proposed) >= min_entry_notional else 0.0
                        self.pyramided[symbol] = False
                    elif bearish:
                        if avg_funding > 0:
                            funding_mult = 1.0 + FUNDING_BOOST
                        proposed = -size * funding_mult
                        target = proposed if abs(proposed) >= min_entry_notional else 0.0
                        self.pyramided[symbol] = False
            else:
                if symbol in self.entry_prices and not self.pyramided.get(symbol, True):
                    entry = self.entry_prices[symbol]
                    pnl = (mid - entry) / entry
                    if current_pos < 0:
                        pnl = -pnl
                    if pnl > PYRAMID_THRESHOLD:
                        if current_pos > 0 and bullish:
                            target = current_pos + size * PYRAMID_SIZE
                            self.pyramided[symbol] = True
                        elif current_pos < 0 and bearish:
                            target = current_pos - size * PYRAMID_SIZE
                            self.pyramided[symbol] = True

                atr = self._calc_atr(bd.history, ATR_LOOKBACK)
                if atr is None:
                    atr = self.atr_at_entry.get(symbol, mid * 0.02)

                if symbol not in self.peak_prices:
                    self.peak_prices[symbol] = mid

                if current_pos > 0:
                    self.peak_prices[symbol] = max(self.peak_prices[symbol], mid)
                    stop = self.peak_prices[symbol] - atr_stop_mult * atr
                    if mid < stop:
                        target = 0.0
                else:
                    self.peak_prices[symbol] = min(self.peak_prices[symbol], mid)
                    stop = self.peak_prices[symbol] + atr_stop_mult * atr
                    if mid > stop:
                        target = 0.0

                if symbol in self.entry_prices:
                    entry = self.entry_prices[symbol]
                    pnl = (mid - entry) / entry
                    if current_pos < 0:
                        pnl = -pnl
                    if pnl > take_profit_pct:
                        target = 0.0

                if current_pos > 0 and rsi > RSI_OVERBOUGHT:
                    target = 0.0
                elif current_pos < 0 and rsi < RSI_OVERSOLD:
                    target = 0.0

                if current_pos > 0 and bearish and not in_cooldown:
                    target = -size if abs(size) >= min_entry_notional else 0.0
                elif current_pos < 0 and bullish and not in_cooldown:
                    target = size if abs(size) >= min_entry_notional else 0.0

            if abs(target - current_pos) > 1.0:
                signals.append(Signal(symbol=symbol, target_position=target))
                if target != 0 and current_pos == 0:
                    self.entry_prices[symbol] = mid
                    self.peak_prices[symbol] = mid
                    self.atr_at_entry[symbol] = self._calc_atr(bd.history, ATR_LOOKBACK) or mid * 0.02
                elif target == 0:
                    self.entry_prices.pop(symbol, None)
                    self.peak_prices.pop(symbol, None)
                    self.atr_at_entry.pop(symbol, None)
                    self.pyramided.pop(symbol, None)
                    self.exit_bar[symbol] = self.bar_count
                elif (target > 0 and current_pos < 0) or (target < 0 and current_pos > 0):
                    self.entry_prices[symbol] = mid
                    self.peak_prices[symbol] = mid
                    self.atr_at_entry[symbol] = self._calc_atr(bd.history, ATR_LOOKBACK) or mid * 0.02
                    self.pyramided[symbol] = False

        return signals
