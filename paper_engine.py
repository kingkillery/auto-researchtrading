from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd

from paper_state import JsonStateStore, STATE_SCHEMA_VERSION, _jsonable
from prepare import (
    BarData,
    INITIAL_CAPITAL,
    LOOKBACK_BARS,
    MAX_LEVERAGE,
    PortfolioState,
    Signal,
    SLIPPAGE_BPS,
    TAKER_FEE,
)


BAR_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "funding_rate"]


@dataclass
class PaperFill:
    symbol: str
    delta: float
    exec_price: float
    fee: float
    timestamp: int
    side: str
    reason: str
    pnl: float = 0.0


@dataclass
class PaperStepResult:
    timestamp: int
    signals: list[Signal] = field(default_factory=list)
    fills: list[PaperFill] = field(default_factory=list)
    portfolio: PortfolioState | None = None
    equity: float = 0.0


class PaperTradingEngine:
    def __init__(
        self,
        strategy: Any,
        *,
        state_store: JsonStateStore | None = None,
        initial_capital: float = INITIAL_CAPITAL,
        history_limit: int = LOOKBACK_BARS,
        symbols: list[str] | None = None,
        persist_strategy_state: bool = True,
    ):
        self.strategy = strategy
        self.state_store = state_store
        self.initial_capital = float(initial_capital)
        self.history_limit = int(history_limit)
        self.persist_strategy_state = persist_strategy_state
        self.symbols = list(symbols) if symbols else None

        self.cash = float(initial_capital)
        self.positions: dict[str, float] = {}
        self.entry_prices: dict[str, float] = {}
        self.equity = float(initial_capital)
        self.timestamp = 0
        self.history_buffers: dict[str, list[dict[str, Any]]] = {}
        self.last_seen_timestamps: dict[str, int] = {}
        self.trade_log: list[dict[str, Any]] = []

    def load_state(self) -> bool:
        if self.state_store is None:
            return False

        payload = self.state_store.load()
        if not payload:
            return False

        if payload.get("schema_version") != STATE_SCHEMA_VERSION:
            return False

        engine_state = payload.get("engine", {})
        self.cash = float(engine_state.get("cash", self.cash))
        self.positions = {str(symbol): float(value) for symbol, value in engine_state.get("positions", {}).items()}
        self.entry_prices = {str(symbol): float(value) for symbol, value in engine_state.get("entry_prices", {}).items()}
        self.equity = float(engine_state.get("equity", self.equity))
        self.timestamp = int(engine_state.get("timestamp", self.timestamp))
        self.history_buffers = {
            str(symbol): [dict(item) for item in rows]
            for symbol, rows in engine_state.get("history_buffers", {}).items()
        }
        self.last_seen_timestamps = {
            str(symbol): int(value)
            for symbol, value in engine_state.get("last_seen_timestamps", {}).items()
        }

        if self.persist_strategy_state:
            self._restore_strategy_state(payload.get("strategy"))

        return True

    def save_state(self) -> None:
        if self.state_store is None:
            return

        payload = {
            "schema_version": STATE_SCHEMA_VERSION,
            "engine": {
                "cash": self.cash,
                "positions": self.positions,
                "entry_prices": self.entry_prices,
                "equity": self.equity,
                "timestamp": self.timestamp,
                "history_buffers": self.history_buffers,
                "last_seen_timestamps": self.last_seen_timestamps,
            },
        }

        if self.persist_strategy_state:
            payload["strategy"] = self._capture_strategy_state()

        self.state_store.save(payload)

    def snapshot_portfolio(self) -> PortfolioState:
        return PortfolioState(
            cash=self.cash,
            positions=dict(self.positions),
            entry_prices=dict(self.entry_prices),
            equity=self.equity,
            timestamp=self.timestamp,
        )

    def seed_history(self, snapshot: Mapping[str, Mapping[str, Any] | BarData]) -> int:
        bar_data = self._build_bar_data(snapshot)
        if not bar_data:
            return 0

        self.timestamp = max(bar.timestamp for bar in bar_data.values())
        self.equity = self._mark_to_market(bar_data)
        self.save_state()
        return len(bar_data)

    def step(self, snapshot: Mapping[str, Mapping[str, Any] | BarData]) -> PaperStepResult:
        bar_data = self._build_bar_data(snapshot)
        if not bar_data:
            return PaperStepResult(timestamp=self.timestamp, portfolio=self.snapshot_portfolio(), equity=self.equity)

        timestamp = max(bar.timestamp for bar in bar_data.values())
        self.timestamp = timestamp

        self.equity = self._mark_to_market(bar_data)
        self._apply_funding(bar_data)

        portfolio_view = self.snapshot_portfolio()
        portfolio_view.equity = self.equity

        try:
            signals = list(self.strategy.on_bar(bar_data, portfolio_view) or [])
        except Exception as exc:
            raise RuntimeError(f"strategy.on_bar failed at timestamp={timestamp}") from exc

        fills = self._execute_signals(bar_data, signals)

        self.equity = self._mark_to_market(bar_data)
        portfolio_after = self.snapshot_portfolio()
        portfolio_after.equity = self.equity

        self.save_state()

        return PaperStepResult(
            timestamp=timestamp,
            signals=signals,
            fills=fills,
            portfolio=portfolio_after,
            equity=self.equity,
        )

    def _capture_strategy_state(self) -> Any:
        if hasattr(self.strategy, "get_state") and callable(self.strategy.get_state):
            return _jsonable(self.strategy.get_state())
        return _jsonable(vars(self.strategy))

    def _restore_strategy_state(self, state: Any) -> None:
        if state is None:
            return
        if hasattr(self.strategy, "set_state") and callable(self.strategy.set_state):
            self.strategy.set_state(state)
            return
        if isinstance(state, dict):
            self.strategy.__dict__.update(state)

    def _coerce_bar(self, symbol: str, raw: Mapping[str, Any] | BarData) -> dict[str, Any]:
        if isinstance(raw, BarData):
            data = {
                "symbol": raw.symbol,
                "timestamp": raw.timestamp,
                "open": raw.open,
                "high": raw.high,
                "low": raw.low,
                "close": raw.close,
                "volume": raw.volume,
                "funding_rate": raw.funding_rate,
            }
        else:
            data = dict(raw)
            data.setdefault("symbol", symbol)

        for field_name in ("timestamp", "open", "high", "low", "close", "volume"):
            if field_name not in data:
                raise KeyError(f"missing required bar field '{field_name}' for {symbol}")

        data.setdefault("funding_rate", 0.0)
        data["timestamp"] = int(data["timestamp"])
        data["open"] = float(data["open"])
        data["high"] = float(data["high"])
        data["low"] = float(data["low"])
        data["close"] = float(data["close"])
        data["volume"] = float(data["volume"])
        data["funding_rate"] = float(data["funding_rate"])
        data["symbol"] = str(data.get("symbol", symbol))
        return data

    def _build_bar_data(self, snapshot: Mapping[str, Mapping[str, Any] | BarData]) -> dict[str, BarData]:
        if not snapshot:
            return {}

        timestamps = set()
        normalized: dict[str, dict[str, Any]] = {}
        for symbol, raw in snapshot.items():
            data = self._coerce_bar(symbol, raw)
            timestamps.add(data["timestamp"])
            normalized[str(symbol)] = data

        if len(timestamps) > 1:
            raise ValueError(f"paper engine expects aligned bars, got timestamps={sorted(timestamps)}")

        bar_data: dict[str, BarData] = {}
        for symbol, data in normalized.items():
            last_seen = self.last_seen_timestamps.get(symbol)
            if last_seen is not None and data["timestamp"] <= last_seen:
                continue

            buffer = self.history_buffers.setdefault(symbol, [])
            buffer.append({key: data.get(key, 0.0) for key in BAR_COLUMNS})
            if len(buffer) > self.history_limit:
                buffer[:] = buffer[-self.history_limit :]
            self.last_seen_timestamps[symbol] = data["timestamp"]

            history = pd.DataFrame(buffer, columns=BAR_COLUMNS)
            bar_data[symbol] = BarData(
                symbol=symbol,
                timestamp=data["timestamp"],
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                volume=data["volume"],
                funding_rate=data["funding_rate"],
                history=history,
            )

        return bar_data

    def _mark_to_market(self, bar_data: Mapping[str, BarData]) -> float:
        unrealized_pnl = 0.0
        for symbol, pos_notional in self.positions.items():
            if symbol not in bar_data:
                continue

            current_price = bar_data[symbol].close
            entry_price = self.entry_prices.get(symbol, current_price)
            if entry_price > 0:
                price_change = (current_price - entry_price) / entry_price
                unrealized_pnl += pos_notional * price_change

        return self.cash + sum(abs(value) for value in self.positions.values()) + unrealized_pnl

    def _apply_funding(self, bar_data: Mapping[str, BarData]) -> None:
        for symbol, pos_notional in list(self.positions.items()):
            if symbol not in bar_data:
                continue
            funding_rate = bar_data[symbol].funding_rate
            self.cash -= pos_notional * funding_rate / 8.0

    def _execute_signals(self, bar_data: Mapping[str, BarData], signals: list[Signal]) -> list[PaperFill]:
        fills: list[PaperFill] = []

        for signal in signals:
            if signal.symbol not in bar_data:
                continue

            current_price = bar_data[signal.symbol].close
            current_pos = self.positions.get(signal.symbol, 0.0)
            delta = signal.target_position - current_pos

            if abs(delta) < 1.0:
                continue

            new_positions = dict(self.positions)
            new_positions[signal.symbol] = signal.target_position
            total_exposure = sum(abs(value) for value in new_positions.values())
            if total_exposure > self.equity * MAX_LEVERAGE:
                continue

            slippage = current_price * SLIPPAGE_BPS / 10000.0
            exec_price = current_price + slippage if delta > 0 else current_price - slippage
            fee = abs(delta) * TAKER_FEE
            self.cash -= fee

            if signal.target_position == 0:
                pnl = 0.0
                if signal.symbol in self.entry_prices:
                    entry = self.entry_prices[signal.symbol]
                    if entry > 0:
                        pnl = current_pos * (exec_price - entry) / entry
                        self.cash += abs(current_pos) + pnl
                    self.entry_prices.pop(signal.symbol, None)

                self.positions.pop(signal.symbol, None)
                fills.append(
                    PaperFill(
                        symbol=signal.symbol,
                        delta=delta,
                        exec_price=exec_price,
                        fee=fee,
                        timestamp=self.timestamp,
                        side="close",
                        reason="target_zero",
                        pnl=pnl,
                    )
                )
            else:
                if current_pos == 0:
                    self.cash -= abs(signal.target_position)
                    self.positions[signal.symbol] = signal.target_position
                    self.entry_prices[signal.symbol] = exec_price
                    fills.append(
                        PaperFill(
                            symbol=signal.symbol,
                            delta=delta,
                            exec_price=exec_price,
                            fee=fee,
                            timestamp=self.timestamp,
                            side="open",
                            reason="new_position",
                        )
                    )
                else:
                    pnl = 0.0
                    old_notional = abs(current_pos)
                    old_entry = self.entry_prices.get(signal.symbol, exec_price)

                    if abs(signal.target_position) < abs(current_pos):
                        reduced = abs(current_pos) - abs(signal.target_position)
                        if old_entry > 0:
                            pnl = (current_pos / abs(current_pos)) * reduced * (exec_price - old_entry) / old_entry
                        self.cash += reduced + pnl
                    elif abs(signal.target_position) > abs(current_pos):
                        added = abs(signal.target_position) - abs(current_pos)
                        self.cash -= added
                        if old_notional + added > 0:
                            new_entry = (old_entry * old_notional + exec_price * added) / (old_notional + added)
                            self.entry_prices[signal.symbol] = new_entry

                    self.positions[signal.symbol] = signal.target_position
                    fills.append(
                        PaperFill(
                            symbol=signal.symbol,
                            delta=delta,
                            exec_price=exec_price,
                            fee=fee,
                            timestamp=self.timestamp,
                            side="modify",
                            reason="resize_or_flip",
                            pnl=pnl,
                        )
                    )

            self.trade_log.append(
                {
                    "symbol": signal.symbol,
                    "timestamp": self.timestamp,
                    "target_position": signal.target_position,
                    "delta": delta,
                    "exec_price": exec_price,
                    "fee": fee,
                }
            )

        return fills
