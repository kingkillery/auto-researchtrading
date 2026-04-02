from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from paper_state import JsonStateStore, _jsonable
from prepare import BAR_INTERVAL, INITIAL_CAPITAL, LOOKBACK_BARS, BarData, PortfolioState, Signal


BAR_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "funding_rate"]
LIVE_RUNTIME_SCHEMA_VERSION = 1
LIVE_CONFIRMATION_PHRASE = "I_UNDERSTAND_JUPITER_LIVE_ORDERS"
SUPPORTED_JUPITER_PERP_ASSETS = {"BTC", "ETH", "SOL"}
JUPITER_CLI_NPM_PACKAGE = "@jup-ag/cli"


@dataclass
class StrategyRuntimeStep:
    timestamp: int
    bar_data: dict[str, BarData]
    signals: list[Signal]
    portfolio: PortfolioState


@dataclass(frozen=True)
class JupiterPerpsPosition:
    asset: str
    side: str
    size_usd: float
    entry_price_usd: float
    mark_price_usd: float
    leverage: float
    liquidation_price_usd: float | None
    position_pubkey: str
    raw: dict[str, Any]

    @property
    def signed_size_usd(self) -> float:
        return self.size_usd if self.side == "long" else -self.size_usd


@dataclass(frozen=True)
class JupiterPerpsAccountSnapshot:
    positions: dict[str, JupiterPerpsPosition]
    limit_orders: list[dict[str, Any]]
    wallet_address: str | None = None

    def to_portfolio_state(self, equity_budget_usd: float) -> PortfolioState:
        positions = {asset: position.signed_size_usd for asset, position in self.positions.items()}
        entry_prices = {asset: position.entry_price_usd for asset, position in self.positions.items()}
        gross_exposure = sum(abs(value) for value in positions.values())
        cash = max(0.0, float(equity_budget_usd) - gross_exposure)
        return PortfolioState(
            cash=cash,
            positions=positions,
            entry_prices=entry_prices,
            equity=float(equity_budget_usd),
            timestamp=0,
        )


@dataclass(frozen=True)
class PlannedOrder:
    asset: str
    action: str
    side: str | None
    current_position_usd: float
    target_position_usd: float
    size_delta_usd: float
    command: list[str] | None
    status: str = "planned"
    message: str | None = None
    requires_manual_signature: bool = False
    position_pubkey: str | None = None


@dataclass
class LiveExecutionConfig:
    wallet_mode: str
    equity_budget_usd: float
    leverage: float = 2.0
    input_token: str = "USDC"
    receive_token: str = "USDC"
    min_position_change_usd: float = 10.0
    slippage_bps: int = 200
    key_name: str | None = None
    wallet_address: str | None = None
    jupiter_cli_path: str = "jup"
    cli_dry_run_orders: bool = False
    live_confirmation: str | None = None
    order_request_path: Path | None = None

    def validate_for_live(self) -> None:
        if self.live_confirmation != LIVE_CONFIRMATION_PHRASE:
            raise ValueError(
                "live execution requires an explicit confirmation phrase: "
                f"--live-confirmation {LIVE_CONFIRMATION_PHRASE}"
            )

        if self.wallet_mode not in {"local", "external"}:
            raise ValueError("wallet mode must be 'local' or 'external'")

        if self.equity_budget_usd <= 0:
            raise ValueError("--live-equity-budget-usd must be positive")

        if self.leverage <= 1.0:
            raise ValueError("--live-leverage must be greater than 1.0")

        if self.input_token.upper() != "USDC":
            raise ValueError("the current live implementation only supports --live-input-token USDC")

        if self.receive_token.upper() != "USDC":
            raise ValueError("the current live implementation only supports --live-receive-token USDC")

        if self.wallet_mode == "external" and not self.wallet_address:
            raise ValueError("--wallet-address is required for --wallet-mode external")


def default_jupiter_cli_command() -> str:
    installed = shutil.which("jup")
    if installed:
        return installed

    if shutil.which("npx.cmd"):
        return f"npx.cmd --yes {JUPITER_CLI_NPM_PACKAGE}"
    if shutil.which("npx"):
        return f"npx --yes {JUPITER_CLI_NPM_PACKAGE}"

    return "jup"


def _split_command(command_spec: str) -> list[str]:
    try:
        return shlex.split(command_spec, posix=os.name != "nt")
    except ValueError as exc:
        raise RuntimeError(f"invalid Jupiter CLI command: {command_spec!r}") from exc


def _format_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


class StrategyRuntime:
    def __init__(
        self,
        strategy: Any,
        *,
        state_store: JsonStateStore | None = None,
        history_limit: int = LOOKBACK_BARS,
        persist_strategy_state: bool = True,
    ):
        self.strategy = strategy
        self.state_store = state_store
        self.history_limit = int(history_limit)
        self.persist_strategy_state = persist_strategy_state

        self.timestamp = 0
        self.history_buffers: dict[str, list[dict[str, Any]]] = {}
        self.last_seen_timestamps: dict[str, int] = {}

    def load_state(self) -> bool:
        if self.state_store is None:
            return False

        payload = self.state_store.load()
        if not payload:
            return False

        if payload.get("schema_version") != LIVE_RUNTIME_SCHEMA_VERSION:
            return False

        runtime_state = payload.get("runtime", {})
        self.timestamp = int(runtime_state.get("timestamp", self.timestamp))
        self.history_buffers = {
            str(symbol): [dict(item) for item in rows]
            for symbol, rows in runtime_state.get("history_buffers", {}).items()
        }
        self.last_seen_timestamps = {
            str(symbol): int(value)
            for symbol, value in runtime_state.get("last_seen_timestamps", {}).items()
        }

        if self.persist_strategy_state:
            self._restore_strategy_state(payload.get("strategy"))

        return True

    def save_state(self) -> None:
        if self.state_store is None:
            return

        payload = {
            "schema_version": LIVE_RUNTIME_SCHEMA_VERSION,
            "runtime": {
                "timestamp": self.timestamp,
                "history_buffers": self.history_buffers,
                "last_seen_timestamps": self.last_seen_timestamps,
            },
        }
        if self.persist_strategy_state:
            payload["strategy"] = self._capture_strategy_state()
        self.state_store.save(payload)

    def evaluate(
        self,
        snapshot: Mapping[str, Mapping[str, Any] | BarData],
        portfolio: PortfolioState,
    ) -> StrategyRuntimeStep:
        bar_data = self._build_bar_data(snapshot)
        if not bar_data:
            return StrategyRuntimeStep(
                timestamp=self.timestamp,
                bar_data={},
                signals=[],
                portfolio=portfolio,
            )

        timestamp = max(bar.timestamp for bar in bar_data.values())
        self.timestamp = timestamp

        runtime_portfolio = PortfolioState(
            cash=float(portfolio.cash),
            positions=dict(portfolio.positions),
            entry_prices=dict(portfolio.entry_prices),
            equity=float(portfolio.equity),
            timestamp=timestamp,
        )

        try:
            signals = list(self.strategy.on_bar(bar_data, runtime_portfolio) or [])
        except Exception as exc:
            raise RuntimeError(f"strategy.on_bar failed at timestamp={timestamp}") from exc

        self.save_state()
        return StrategyRuntimeStep(
            timestamp=timestamp,
            bar_data=bar_data,
            signals=signals,
            portfolio=runtime_portfolio,
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
            normalized[str(symbol).upper()] = data

        if len(timestamps) > 1:
            raise ValueError(f"live runtime expects aligned bars, got timestamps={sorted(timestamps)}")

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


class JupiterCliClient:
    def __init__(self, cli_path: str = "jup", *, dry_run_orders: bool = False):
        self.cli_path = cli_path
        self.dry_run_orders = dry_run_orders
        self.base_command = _split_command(cli_path)

    @property
    def command_preview(self) -> str:
        return _format_command(self.base_command)

    def ensure_available(self) -> None:
        executable = self.base_command[0] if self.base_command else ""
        if not executable or shutil.which(executable) is None:
            raise RuntimeError(
                f"Jupiter CLI command is not available: {self.command_preview!r}. "
                "Install @jup-ag/cli globally or point --jupiter-cli-path at a working command, "
                "for example --jupiter-cli-path \"npx --yes @jup-ag/cli\"."
            )

    def version(self) -> str:
        completed = subprocess.run(
            [*self.base_command, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"failed to read Jupiter CLI version from {self.command_preview}: {stderr}")
        return (completed.stdout or "").strip()

    def config_list(self) -> dict[str, Any]:
        return self._run_json(["config", "list"])

    def keys_list(self) -> list[dict[str, Any]]:
        payload = self._run_json(["keys", "list"])
        if not isinstance(payload, list):
            raise RuntimeError("unexpected Jupiter CLI keys payload")
        return [item for item in payload if isinstance(item, dict)]

    def perps_markets(self) -> list[dict[str, Any]]:
        payload = self._run_json(["perps", "markets"])
        if not isinstance(payload, list):
            raise RuntimeError("unexpected Jupiter CLI perps markets payload")
        return [item for item in payload if isinstance(item, dict)]

    def validate_local_wallet_setup(self, *, key_name: str | None = None) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []

        def add_check(name: str, ok: bool, message: str, **extra: Any) -> None:
            checks.append({"name": name, "ok": ok, "message": message, **extra})

        self.ensure_available()
        version = self.version()
        add_check("cli_available", True, f"using Jupiter CLI command {self.command_preview}", version=version)

        config = self.config_list()
        active_key = str(config.get("activeKey") or "").strip() or None
        add_check("config_readable", True, "read CLI config", config=config)

        keys = self.keys_list()
        key_names = [str(item.get("name") or "").strip() for item in keys if str(item.get("name") or "").strip()]
        if key_names:
            add_check("keys_present", True, f"found {len(key_names)} configured Jupiter key(s)", keys=key_names)
        else:
            add_check(
                "keys_present",
                False,
                "no Jupiter keys are configured",
                recommended_commands=[
                    f"{self.command_preview} keys add live-local",
                    f"{self.command_preview} keys solana-import --name live-local --path <solana-keypair.json>",
                ],
            )

        selected_key = key_name or active_key
        if selected_key:
            if selected_key in key_names:
                add_check("selected_key", True, f"selected Jupiter key {selected_key!r} is configured", selected_key=selected_key)
            else:
                add_check(
                    "selected_key",
                    False,
                    f"selected Jupiter key {selected_key!r} is not configured",
                    selected_key=selected_key,
                    available_keys=key_names,
                )
        else:
            add_check(
                "selected_key",
                False,
                "no active Jupiter key is set and --jup-key was not provided",
                recommended_commands=[
                    f"{self.command_preview} keys use <name>",
                ],
            )

        markets = self.perps_markets()
        market_assets = sorted({str(item.get("asset") or "").upper() for item in markets if item.get("asset")})
        missing_assets = sorted(SUPPORTED_JUPITER_PERP_ASSETS - set(market_assets))
        add_check(
            "supported_markets",
            not missing_assets,
            "perps market metadata is reachable" if not missing_assets else f"missing expected perps markets: {', '.join(missing_assets)}",
            markets=market_assets,
        )

        positions_ok = False
        positions_error = None
        position_count = 0
        wallet_address = None
        if selected_key and selected_key in key_names:
            try:
                snapshot = self.positions(key_name=selected_key)
                positions_ok = True
                position_count = len(snapshot.positions)
                wallet_address = snapshot.wallet_address
                add_check(
                    "positions_probe",
                    True,
                    f"perps positions query succeeded for key {selected_key!r}",
                    open_positions=position_count,
                    wallet_address=wallet_address,
                )
            except Exception as exc:
                positions_error = str(exc)
                add_check(
                    "positions_probe",
                    False,
                    f"perps positions query failed for key {selected_key!r}: {positions_error}",
                )

        ready = all(check["ok"] for check in checks)
        if not ready:
            next_steps = [
                "Run the recommended Jupiter CLI key setup commands above.",
                "Repeat uv run python run_jupiter_live.py --validate-local-wallet-setup until ready_for_live_local_wallet becomes true.",
                "Keep --execution-mode paper until the validator passes cleanly.",
            ]
        else:
            next_steps = [
                "Optionally rerun with --jupiter-cli-dry-run to exercise order submission without broadcasting.",
                "Use a small --live-equity-budget-usd and keep the confirmation phrase explicit.",
            ]

        return {
            "type": "local_wallet_setup",
            "ready_for_live_local_wallet": ready,
            "cli_command": self.command_preview,
            "cli_version": version,
            "active_key": active_key,
            "selected_key": selected_key,
            "configured_keys": key_names,
            "checks": checks,
            "positions_probe_succeeded": positions_ok,
            "positions_probe_error": positions_error,
            "open_position_count": position_count,
            "wallet_address": wallet_address,
            "dry_run_orders": self.dry_run_orders,
            "next_steps": next_steps,
        }

    def positions(self, *, key_name: str | None = None, wallet_address: str | None = None) -> JupiterPerpsAccountSnapshot:
        command = ["perps", "positions"]
        if key_name:
            command.extend(["--key", key_name])
        elif wallet_address:
            command.extend(["--address", wallet_address])

        payload = self._run_json(command)
        positions = payload.get("positions", [])
        limit_orders = payload.get("limitOrders", [])
        if not isinstance(positions, list):
            raise RuntimeError("unexpected Jupiter CLI positions payload")

        parsed: dict[str, JupiterPerpsPosition] = {}
        for item in positions:
            if not isinstance(item, dict):
                continue
            asset = str(item.get("asset") or "").upper()
            if asset in parsed:
                raise RuntimeError(f"multiple live positions detected for asset={asset}; manual reconciliation required")
            if not asset:
                continue
            parsed[asset] = JupiterPerpsPosition(
                asset=asset,
                side=str(item.get("side") or "").lower(),
                size_usd=float(item.get("sizeUsd") or 0.0),
                entry_price_usd=float(item.get("entryPriceUsd") or 0.0),
                mark_price_usd=float(item.get("markPriceUsd") or 0.0),
                leverage=float(item.get("leverage") or 0.0),
                liquidation_price_usd=float(item["liquidationPriceUsd"]) if item.get("liquidationPriceUsd") is not None else None,
                position_pubkey=str(item.get("positionPubkey") or ""),
                raw=item,
            )

        return JupiterPerpsAccountSnapshot(
            positions=parsed,
            limit_orders=[item for item in limit_orders if isinstance(item, dict)],
            wallet_address=wallet_address,
        )

    def open_position(
        self,
        *,
        asset: str,
        side: str,
        size_usd: float,
        leverage: float,
        input_token: str,
        slippage_bps: int,
        key_name: str | None = None,
    ) -> dict[str, Any]:
        collateral_amount = size_usd / leverage
        command = [
            "perps",
            "open",
            "--asset",
            asset.upper(),
            "--side",
            side,
            "--amount",
            _format_decimal(collateral_amount),
            "--input",
            input_token.upper(),
            "--size",
            _format_decimal(size_usd),
            "--slippage",
            str(int(slippage_bps)),
        ]
        if key_name:
            command.extend(["--key", key_name])
        return self._run_json(command, include_dry_run=self.dry_run_orders)

    def close_position(
        self,
        *,
        position_pubkey: str,
        size_usd: float | None,
        receive_token: str,
        key_name: str | None = None,
    ) -> dict[str, Any]:
        command = [
            "perps",
            "close",
            "--position",
            position_pubkey,
            "--receive",
            receive_token.upper(),
        ]
        if size_usd is not None:
            command.extend(["--size", _format_decimal(size_usd)])
        if key_name:
            command.extend(["--key", key_name])
        return self._run_json(command, include_dry_run=self.dry_run_orders)

    def _run_json(self, command: list[str], *, include_dry_run: bool = False) -> dict[str, Any]:
        argv = [*self.base_command]
        if include_dry_run:
            argv.append("--dry-run")
        argv.extend([*command, "-f", "json"])
        completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Jupiter CLI command failed ({completed.returncode}): {' '.join(argv)} :: {stderr}")

        stdout = (completed.stdout or "").strip()
        if not stdout:
            return {}

        try:
            return json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"failed to decode Jupiter CLI JSON output for command: {' '.join(argv)}") from exc


def build_live_order_plan(
    signals: list[Signal],
    account: JupiterPerpsAccountSnapshot,
    config: LiveExecutionConfig,
) -> list[PlannedOrder]:
    planned: list[PlannedOrder] = []
    current_positions = {asset: position.signed_size_usd for asset, position in account.positions.items()}

    for signal in signals:
        asset = signal.symbol.upper()
        target = float(signal.target_position)
        current = float(current_positions.get(asset, 0.0))
        delta = target - current

        if asset not in SUPPORTED_JUPITER_PERP_ASSETS:
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="skip",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=target,
                    size_delta_usd=delta,
                    command=None,
                    status="unsupported_asset",
                    message="live Jupiter perps currently supports BTC, ETH, and SOL",
                )
            )
            continue

        if signal.order_type != "market":
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="skip",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=target,
                    size_delta_usd=delta,
                    command=None,
                    status="unsupported_order_type",
                    message="the live Jupiter path only supports market targets for now",
                )
            )
            continue

        if abs(delta) < config.min_position_change_usd:
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="hold",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=target,
                    size_delta_usd=delta,
                    command=None,
                    status="below_threshold",
                    message=(
                        f"delta {delta:.2f} USD is below --min-live-position-change-usd "
                        f"{config.min_position_change_usd:.2f}"
                    ),
                )
            )
            continue

        existing = account.positions.get(asset)

        if target == 0.0 and existing is not None:
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="close",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=target,
                    size_delta_usd=abs(current),
                    command=_close_command_preview(existing.position_pubkey, None, config),
                    position_pubkey=existing.position_pubkey,
                )
            )
            continue

        if existing is None:
            planned.append(_open_plan(asset, current, target, abs(target), config))
            continue

        if current * target < 0:
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="close",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=0.0,
                    size_delta_usd=abs(current),
                    command=_close_command_preview(existing.position_pubkey, None, config),
                    position_pubkey=existing.position_pubkey,
                )
            )
            planned.append(_open_plan(asset, 0.0, target, abs(target), config))
            continue

        if abs(target) > abs(current):
            planned.append(_open_plan(asset, current, target, abs(target) - abs(current), config))
            continue

        if abs(target) < abs(current):
            planned.append(
                PlannedOrder(
                    asset=asset,
                    action="reduce",
                    side=None,
                    current_position_usd=current,
                    target_position_usd=target,
                    size_delta_usd=abs(current) - abs(target),
                    command=_close_command_preview(existing.position_pubkey, abs(current) - abs(target), config),
                    position_pubkey=existing.position_pubkey,
                )
            )
            continue

        planned.append(
            PlannedOrder(
                asset=asset,
                action="hold",
                side=None,
                current_position_usd=current,
                target_position_usd=target,
                size_delta_usd=delta,
                command=None,
                status="already_at_target",
            )
        )

    return planned


def execute_live_order_plan(
    cli: JupiterCliClient,
    plans: list[PlannedOrder],
    config: LiveExecutionConfig,
    *,
    bar_timestamp: int,
) -> list[dict[str, Any]]:
    if config.wallet_mode == "external":
        path = config.order_request_path
        if path is None:
            raise ValueError("order request path is required for wallet_mode=external")
        path.parent.mkdir(parents=True, exist_ok=True)
        emitted: list[dict[str, Any]] = []
        with path.open("a", encoding="utf-8") as handle:
            for plan in plans:
                payload = _build_external_order_request(plan, config, bar_timestamp=bar_timestamp)
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")
                emitted.append(
                    {
                        **payload,
                        "requires_manual_signature": True,
                    }
                )
        return emitted

    cli.ensure_available()
    responses: list[dict[str, Any]] = []
    for plan in plans:
        if plan.command is None or plan.status not in {"planned"}:
            responses.append(
                {
                    "asset": plan.asset,
                    "action": plan.action,
                    "status": plan.status,
                    "message": plan.message,
                }
            )
            continue

        response: dict[str, Any]
        if plan.action == "open":
            response = cli.open_position(
                asset=plan.asset,
                side=plan.side or "long",
                size_usd=plan.size_delta_usd,
                leverage=config.leverage,
                input_token=config.input_token,
                slippage_bps=config.slippage_bps,
                key_name=config.key_name,
            )
        elif plan.action in {"close", "reduce"}:
            response = cli.close_position(
                position_pubkey=plan.position_pubkey or "",
                size_usd=None if plan.action == "close" else plan.size_delta_usd,
                receive_token=config.receive_token,
                key_name=config.key_name,
            )
        else:
            responses.append(
                {
                    "asset": plan.asset,
                    "action": plan.action,
                    "status": "skipped",
                    "message": f"unsupported live action {plan.action!r}",
                }
            )
            continue

        responses.append(
            {
                "asset": plan.asset,
                "action": plan.action,
                "status": "submitted",
                "response": response,
            }
        )

    return responses


def _build_external_order_request(
    plan: PlannedOrder,
    config: LiveExecutionConfig,
    *,
    bar_timestamp: int,
) -> dict[str, Any]:
    request_id = _external_request_id(plan, bar_timestamp=bar_timestamp)
    collateral_amount = None
    if plan.action == "open" and plan.size_delta_usd > 0:
        collateral_amount = round(float(plan.size_delta_usd) / float(config.leverage), 6)

    return {
        "schema_version": 1,
        "request_id": request_id,
        "timestamp": int(bar_timestamp),
        "wallet_mode": config.wallet_mode,
        "wallet_address": config.wallet_address,
        "status": plan.status,
        "approval_status": "pending_manual_signature" if plan.status == "planned" else "info_only",
        "asset": plan.asset,
        "action": plan.action,
        "side": plan.side,
        "current_position_usd": round(float(plan.current_position_usd), 6),
        "target_position_usd": round(float(plan.target_position_usd), 6),
        "size_delta_usd": round(float(plan.size_delta_usd), 6),
        "position_pubkey": plan.position_pubkey,
        "message": plan.message
        or "External wallet mode cannot sign in-process. Review this request, submit it through a wallet-controlled Jupiter surface, then record the decision in the approval board.",
        "command_preview": plan.command,
        "operator_summary": _external_operator_summary(plan, config),
        "signer_payload": {
            "kind": "jupiter_perps_order_request",
            "wallet_address": config.wallet_address,
            "asset": plan.asset,
            "action": plan.action,
            "side": plan.side,
            "size_usd": round(float(plan.size_delta_usd), 6),
            "current_position_usd": round(float(plan.current_position_usd), 6),
            "target_position_usd": round(float(plan.target_position_usd), 6),
            "collateral_token": config.input_token.upper(),
            "collateral_amount": collateral_amount,
            "receive_token": config.receive_token.upper(),
            "leverage": round(float(config.leverage), 6),
            "slippage_bps": int(config.slippage_bps),
            "position_pubkey": plan.position_pubkey,
            "command_preview": plan.command,
        },
        "handoff": {
            "recommended_surface": "jupiter_wallet_kit_or_browser_wallet",
            "board_command": [
                "uv",
                "run",
                "python",
                "external_wallet_bridge.py",
                "--request-path",
                str(config.order_request_path) if config.order_request_path else "",
            ],
            "checklist": _external_handoff_checklist(plan),
        },
    }


def _external_request_id(plan: PlannedOrder, *, bar_timestamp: int) -> str:
    return "::".join(
        [
            str(int(bar_timestamp)),
            plan.asset.lower(),
            plan.action.lower(),
            (plan.side or "flat").lower(),
            _format_decimal(plan.target_position_usd),
        ]
    )


def _external_operator_summary(plan: PlannedOrder, config: LiveExecutionConfig) -> str:
    if plan.status != "planned":
        return plan.message or f"{plan.asset} {plan.action} did not produce a live order and is informational only."
    if plan.action == "open":
        side = (plan.side or "long").upper()
        collateral_amount = plan.size_delta_usd / config.leverage
        return (
            f"Open a {side} {plan.asset} perp for {plan.size_delta_usd:.2f} USD notional "
            f"using about {collateral_amount:.2f} {config.input_token.upper()} collateral at {config.leverage:.2f}x leverage."
        )
    if plan.action == "close":
        return f"Fully close the existing {plan.asset} perp position via the wallet-controlled Jupiter flow."
    if plan.action == "reduce":
        return f"Reduce the existing {plan.asset} perp position by {plan.size_delta_usd:.2f} USD notional."
    return f"Review the {plan.asset} {plan.action} request before acting."


def _external_handoff_checklist(plan: PlannedOrder) -> list[str]:
    checklist = [
        "Confirm the wallet address matches the operator's intended Jupiter wallet.",
        "Verify the current position and target delta still make sense before signing.",
    ]
    if plan.command:
        checklist.append("Use the signer payload or command preview to recreate the order in the wallet-controlled surface.")
    if plan.action in {"close", "reduce"}:
        checklist.append("Double-check the referenced position before reducing or closing it.")
    checklist.append("After acting, record approve/reject/submitted status in the approval board.")
    return checklist


def strategy_portfolio_snapshot(
    account: JupiterPerpsAccountSnapshot,
    *,
    equity_budget_usd: float,
    timestamp: int,
) -> PortfolioState:
    portfolio = account.to_portfolio_state(equity_budget_usd)
    portfolio.timestamp = timestamp
    return portfolio


def _open_plan(
    asset: str,
    current: float,
    target: float,
    size_delta_usd: float,
    config: LiveExecutionConfig,
) -> PlannedOrder:
    side = "long" if target > 0 else "short"
    collateral_amount = size_delta_usd / config.leverage
    if collateral_amount < 10.0 and abs(current) < 1e-9:
        return PlannedOrder(
            asset=asset,
            action="skip",
            side=side,
            current_position_usd=current,
            target_position_usd=target,
            size_delta_usd=size_delta_usd,
            command=None,
            status="below_min_collateral",
            message=(
                f"opening {size_delta_usd:.2f} USD at leverage {config.leverage:.2f} only posts "
                f"{collateral_amount:.2f} {config.input_token.upper()} collateral; Jupiter CLI docs require at least $10 for a new position"
            ),
        )

    return PlannedOrder(
        asset=asset,
        action="open",
        side=side,
        current_position_usd=current,
        target_position_usd=target,
        size_delta_usd=size_delta_usd,
        command=_open_command_preview(asset, side, size_delta_usd, config),
    )


def _open_command_preview(asset: str, side: str, size_delta_usd: float, config: LiveExecutionConfig) -> list[str]:
    collateral_amount = size_delta_usd / config.leverage
    command = [*_split_command(config.jupiter_cli_path)]
    if config.cli_dry_run_orders:
        command.append("--dry-run")
    command.extend(
        [
            "perps",
            "open",
            "--asset",
            asset.upper(),
            "--side",
            side,
            "--amount",
            _format_decimal(collateral_amount),
            "--input",
            config.input_token.upper(),
            "--size",
            _format_decimal(size_delta_usd),
            "--slippage",
            str(int(config.slippage_bps)),
        ]
    )
    if config.key_name:
        command.extend(["--key", config.key_name])
    command.extend(["-f", "json"])
    return command


def _close_command_preview(position_pubkey: str, size_delta_usd: float | None, config: LiveExecutionConfig) -> list[str]:
    command = [*_split_command(config.jupiter_cli_path)]
    if config.cli_dry_run_orders:
        command.append("--dry-run")
    command.extend(
        [
            "perps",
            "close",
            "--position",
            position_pubkey,
            "--receive",
            config.receive_token.upper(),
        ]
    )
    if size_delta_usd is not None:
        command.extend(["--size", _format_decimal(size_delta_usd)])
    if config.key_name:
        command.extend(["--key", config.key_name])
    command.extend(["-f", "json"])
    return command


def serialize_signal(signal: Signal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "target_position": round(float(signal.target_position), 6),
        "order_type": signal.order_type,
    }


def serialize_plan(plan: PlannedOrder) -> dict[str, Any]:
    payload = asdict(plan)
    if payload["size_delta_usd"] is not None:
        payload["size_delta_usd"] = round(float(payload["size_delta_usd"]), 6)
    payload["current_position_usd"] = round(float(payload["current_position_usd"]), 6)
    payload["target_position_usd"] = round(float(payload["target_position_usd"]), 6)
    return payload


def serialize_portfolio(portfolio: PortfolioState) -> dict[str, Any]:
    return {
        "cash": round(float(portfolio.cash), 6),
        "equity": round(float(portfolio.equity), 6),
        "positions": {symbol: round(float(value), 6) for symbol, value in portfolio.positions.items()},
        "entry_prices": {symbol: round(float(value), 6) for symbol, value in portfolio.entry_prices.items()},
        "timestamp": int(portfolio.timestamp),
    }


def default_live_equity_budget() -> float:
    return float(INITIAL_CAPITAL)


def live_interval_label() -> str:
    return BAR_INTERVAL


def _format_decimal(value: float) -> str:
    return f"{float(value):.6f}".rstrip("0").rstrip(".")
