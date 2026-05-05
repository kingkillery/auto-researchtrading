from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from jupiter_execution import (
    LIVE_CONFIRMATION_PHRASE,
    JupiterCliClient,
    LiveExecutionConfig,
    StrategyRuntime,
    build_live_order_plan,
    default_jupiter_cli_command,
    default_live_equity_budget,
    execute_live_order_plan,
    serialize_plan,
    serialize_portfolio,
    serialize_signal,
    strategy_portfolio_snapshot,
)
from jupiter_live_adapter import JupiterLiveMarketFeed, JupiterPublicMarketDataClient
from paper_engine import PaperTradingEngine
from paper_state import JsonStateStore, default_state_path
from prepare import load_data


LIVE_STATE_ROOT = Path.home() / ".cache" / "autotrader" / "live"


def load_strategy(spec: str) -> Any:
    module_name, _, class_name = spec.partition(":")
    if not module_name:
        raise ValueError("strategy spec must look like module:ClassName")
    if not class_name:
        class_name = "Strategy"

    module = importlib.import_module(module_name)
    strategy_cls = getattr(module, class_name)
    return strategy_cls()


def _serialize_fill(fill) -> dict[str, Any]:
    return {
        "symbol": fill.symbol,
        "side": fill.side,
        "delta": round(fill.delta, 2),
        "exec_price": round(fill.exec_price, 4),
        "fee": round(fill.fee, 4),
        "pnl": round(fill.pnl, 4),
        "reason": fill.reason,
    }


def _serialize_bars(bar_snapshot: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        symbol: {
            "open": round(bar["open"], 8),
            "high": round(bar["high"], 8),
            "low": round(bar["low"], 8),
            "close": round(bar["close"], 8),
            "volume": round(bar["volume"], 8),
            "funding_rate": round(bar.get("funding_rate", 0.0), 8),
        }
        for symbol, bar in bar_snapshot.items()
    }


def emit_paper_bar(result, bar_snapshot: dict[str, dict[str, Any]]) -> None:
    print(
        json.dumps(
            {
                "type": "bar_close",
                "execution_mode": "paper",
                "timestamp": result.timestamp,
                "equity": round(result.equity, 2),
                "portfolio": {
                    "cash": round(result.portfolio.cash, 2) if result.portfolio else None,
                    "positions": result.portfolio.positions if result.portfolio else {},
                },
                "bars": _serialize_bars(bar_snapshot),
                "fills": [_serialize_fill(fill) for fill in result.fills],
            }
        )
    )


def emit_live_bar(payload: dict[str, Any]) -> None:
    print(json.dumps(payload))


def _state_path_for(args) -> Path:
    return Path(args.state) if args.state else default_state_path(args.strategy, root=LIVE_STATE_ROOT)


def _default_order_request_path(state_path: Path) -> Path:
    return state_path.with_suffix(".orders.jsonl")


def process_paper_bar(engine: PaperTradingEngine, bar_snapshot: dict[str, dict[str, Any]]) -> None:
    result = engine.step(bar_snapshot)
    emit_paper_bar(result, bar_snapshot)


def warmup_paper_history(
    engine: PaperTradingEngine,
    *,
    split: str,
    symbols: list[str],
    limit: int,
) -> dict[str, Any]:
    data = load_data(split)
    requested = {symbol.upper() for symbol in symbols}
    indexed = {
        symbol: frame.set_index("timestamp").sort_index()
        for symbol, frame in data.items()
        if symbol.upper() in requested
    }
    if not indexed:
        return {
            "type": "paper_warmup",
            "split": split,
            "requested_symbols": sorted(requested),
            "seeded_timestamps": 0,
            "seeded_bars": 0,
            "latest_timestamp": None,
        }

    timestamps = sorted({timestamp for frame in indexed.values() for timestamp in frame.index.tolist()})
    if limit > 0:
        timestamps = timestamps[-limit:]

    seeded_timestamps = 0
    seeded_bars = 0
    latest_timestamp = None
    for timestamp in timestamps:
        snapshot: dict[str, dict[str, Any]] = {}
        for symbol, frame in indexed.items():
            if timestamp not in frame.index:
                continue
            row = frame.loc[timestamp]
            if getattr(row, "ndim", 1) > 1:
                row = row.iloc[0]
            if hasattr(row, "to_dict"):
                payload = dict(row.to_dict())
            else:
                payload = dict(row)
            payload.setdefault("timestamp", int(timestamp))
            snapshot[symbol] = payload

        if not snapshot:
            continue

        count = engine.seed_history(snapshot)
        if count:
            seeded_timestamps += 1
            seeded_bars += count
            latest_timestamp = int(timestamp)

    return {
        "type": "paper_warmup",
        "split": split,
        "requested_symbols": sorted(requested),
        "seeded_timestamps": seeded_timestamps,
        "seeded_bars": seeded_bars,
        "latest_timestamp": latest_timestamp,
        "state_path": str(engine.state_store.path) if engine.state_store is not None else None,
    }


def process_live_bar(
    runtime: StrategyRuntime,
    cli: JupiterCliClient,
    config: LiveExecutionConfig,
    bar_snapshot: dict[str, dict[str, Any]],
) -> None:
    account_before = cli.positions(key_name=config.key_name, wallet_address=config.wallet_address)
    timestamp = max(int(bar["timestamp"]) for bar in bar_snapshot.values())
    portfolio_before = strategy_portfolio_snapshot(
        account_before,
        equity_budget_usd=config.equity_budget_usd,
        timestamp=timestamp,
    )
    step = runtime.evaluate(bar_snapshot, portfolio_before)
    plans = build_live_order_plan(step.signals, account_before, config)
    order_events = execute_live_order_plan(cli, plans, config, bar_timestamp=step.timestamp)

    account_after = account_before
    if config.wallet_mode == "local":
        account_after = cli.positions(key_name=config.key_name)

    portfolio_after = strategy_portfolio_snapshot(
        account_after,
        equity_budget_usd=config.equity_budget_usd,
        timestamp=step.timestamp,
    )

    emit_live_bar(
        {
            "type": "bar_close",
            "execution_mode": "live",
            "wallet_mode": config.wallet_mode,
            "timestamp": step.timestamp,
            "bars": _serialize_bars(bar_snapshot),
            "portfolio_before": serialize_portfolio(portfolio_before),
            "portfolio_after": serialize_portfolio(portfolio_after),
            "signals": [serialize_signal(signal) for signal in step.signals],
            "orders": [serialize_plan(plan) for plan in plans],
            "order_events": order_events,
        }
    )


def run_loop(feed: JupiterLiveMarketFeed, poll_seconds: float, on_bar) -> None:
    next_tick = time.monotonic()
    while True:
        try:
            emitted_bars = feed.poll()
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "type": "poll_error",
                        "error": str(exc),
                    }
                ),
                file=sys.stderr,
            )
            next_tick = time.monotonic()
            time.sleep(max(5.0, float(poll_seconds)))
            continue

        for bar_snapshot in emitted_bars:
            on_bar(bar_snapshot)

        next_tick += float(poll_seconds)
        sleep_seconds = max(0.0, next_tick - time.monotonic())
        time.sleep(sleep_seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Jupiter market feed into paper mode or Jupiter live execution mode")
    parser.add_argument("--strategy", default="strategy:Strategy", help="Strategy import path, e.g. strategy:Strategy")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["BTC", "ETH", "SOL"],
        help="Strategy symbols to request from Jupiter",
    )
    parser.add_argument("--poll-seconds", type=float, default=60.0, help="Polling cadence for Jupiter public market data")
    parser.add_argument("--bar-seconds", type=int, default=3600, help="Synthetic bar size in seconds")
    parser.add_argument("--state", default=None, help="State file path. Defaults to a live cache path under ~/.cache/autotrader/live/")
    parser.add_argument("--reset-state", action="store_true", help="Start from a fresh state even if a saved state exists")
    parser.add_argument("--no-save", action="store_true", help="Disable persistence writes")
    parser.add_argument("--no-gap-fill", action="store_true", help="Do not synthesize missing hourly bars")
    parser.add_argument(
        "--paper-warmup-split",
        choices=["train", "val", "test"],
        default=None,
        help="Paper mode only: seed indicator history from cached historical bars before consuming live bars. This does not execute historical trades.",
    )
    parser.add_argument(
        "--paper-warmup-bars",
        type=int,
        default=500,
        help="Number of historical timestamps to use with --paper-warmup-split.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["paper", "live"],
        default="paper",
        help="paper keeps the current simulated fill path; live routes target positions through Jupiter order planning / execution",
    )
    parser.add_argument(
        "--wallet-mode",
        choices=["local", "external"],
        default="local",
        help="local submits via the Jupiter CLI signer path; external only emits execution requests for an external wallet flow",
    )
    parser.add_argument(
        "--live-confirmation",
        default=None,
        help=f"Required in live mode. Must exactly equal: {LIVE_CONFIRMATION_PHRASE}",
    )
    parser.add_argument(
        "--live-equity-budget-usd",
        type=float,
        default=None,
        help="Required in live mode. Synthetic strategy budget used to size positions against the real Jupiter account.",
    )
    parser.add_argument(
        "--live-leverage",
        type=float,
        default=2.0,
        help="Leverage to use when translating target USD position deltas into Jupiter perps open commands",
    )
    parser.add_argument(
        "--min-live-position-change-usd",
        type=float,
        default=10.0,
        help="Ignore live target changes smaller than this USD notional",
    )
    parser.add_argument(
        "--live-input-token",
        default="USDC",
        help="Collateral token for opens in live mode. Only USDC is implemented right now.",
    )
    parser.add_argument(
        "--live-receive-token",
        default="USDC",
        help="Settlement token for closes in live mode. Only USDC is implemented right now.",
    )
    parser.add_argument(
        "--live-slippage-bps",
        type=int,
        default=200,
        help="Slippage passed to Jupiter perps open commands in live mode",
    )
    parser.add_argument(
        "--jupiter-cli-path",
        default=default_jupiter_cli_command(),
        help="Jupiter CLI command used for live order submission / position sync. Accepts a binary path or a full command such as \"npx --yes @jup-ag/cli\".",
    )
    parser.add_argument(
        "--jupiter-cli-dry-run",
        action="store_true",
        help="Pass --dry-run to Jupiter CLI open/close commands so the local-wallet path can be exercised without broadcasting.",
    )
    parser.add_argument(
        "--jup-key",
        default=None,
        help="Jupiter CLI key name. In local wallet mode, defaults to the active CLI key if omitted.",
    )
    parser.add_argument(
        "--wallet-address",
        default=None,
        help="External wallet address to track in live external mode",
    )
    parser.add_argument(
        "--order-request-path",
        default=None,
        help="Where to append external-wallet order requests in live external mode. Defaults next to the live state file.",
    )
    parser.add_argument(
        "--validate-local-wallet-setup",
        action="store_true",
        help="Run a Jupiter CLI / key / perps preflight for the local-wallet path and exit without starting the market-data loop.",
    )
    args = parser.parse_args()

    live_config: LiveExecutionConfig | None = None
    live_cli: JupiterCliClient | None = None

    if args.validate_local_wallet_setup:
        live_cli = JupiterCliClient(args.jupiter_cli_path, dry_run_orders=args.jupiter_cli_dry_run)
        try:
            report = live_cli.validate_local_wallet_setup(key_name=args.jup_key)
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "type": "local_wallet_setup",
                        "ready_for_live_local_wallet": False,
                        "cli_command": args.jupiter_cli_path,
                        "error": str(exc),
                    }
                )
            )
            return 1

        print(json.dumps(report))
        return 0 if report.get("ready_for_live_local_wallet") else 1

    strategy = load_strategy(args.strategy)
    state_path = _state_path_for(args)
    state_store = None if args.no_save else JsonStateStore(state_path)

    if args.execution_mode == "live":
        if args.live_equity_budget_usd is None:
            raise ValueError(
                "--live-equity-budget-usd is required in live mode. "
                f"Use an explicit value instead of relying on the research default ({default_live_equity_budget():.2f})."
            )

        order_request_path = (
            Path(args.order_request_path)
            if args.order_request_path
            else _default_order_request_path(state_path)
        )
        live_config = LiveExecutionConfig(
            wallet_mode=args.wallet_mode,
            equity_budget_usd=float(args.live_equity_budget_usd),
            leverage=float(args.live_leverage),
            input_token=args.live_input_token,
            receive_token=args.live_receive_token,
            min_position_change_usd=float(args.min_live_position_change_usd),
            slippage_bps=int(args.live_slippage_bps),
            key_name=args.jup_key,
            wallet_address=args.wallet_address,
            jupiter_cli_path=args.jupiter_cli_path,
            cli_dry_run_orders=args.jupiter_cli_dry_run,
            live_confirmation=args.live_confirmation,
            order_request_path=order_request_path,
        )
        live_config.validate_for_live()
        live_cli = JupiterCliClient(args.jupiter_cli_path, dry_run_orders=args.jupiter_cli_dry_run)
        live_cli.ensure_available()
        if live_config.wallet_mode == "local":
            setup_report = live_cli.validate_local_wallet_setup(key_name=live_config.key_name)
            print(json.dumps(setup_report))
            if not setup_report.get("ready_for_live_local_wallet"):
                raise RuntimeError(
                    "local-wallet live mode is not ready on this machine. "
                    "Run uv run python run_jupiter_live.py --validate-local-wallet-setup and resolve the reported issues first."
                )
            if live_config.key_name is None:
                live_config.key_name = setup_report.get("selected_key")

    client = JupiterPublicMarketDataClient()
    feed = JupiterLiveMarketFeed(
        client,
        [symbol.upper() for symbol in args.symbols],
        bar_seconds=args.bar_seconds,
        fill_gaps=not args.no_gap_fill,
    )

    try:
        universe = client.describe_universe([symbol.upper() for symbol in args.symbols])
        print(json.dumps({"type": "universe", "execution_mode": args.execution_mode, "symbols": universe}))

        if args.execution_mode == "paper":
            engine = PaperTradingEngine(strategy, state_store=state_store)
            if not args.reset_state:
                engine.load_state()
            if args.paper_warmup_split:
                print(
                    json.dumps(
                        warmup_paper_history(
                            engine,
                            split=args.paper_warmup_split,
                            symbols=[symbol.upper() for symbol in args.symbols],
                            limit=max(0, int(args.paper_warmup_bars)),
                        )
                    )
                )
            run_loop(feed, args.poll_seconds, lambda bar_snapshot: process_paper_bar(engine, bar_snapshot))

            final_portfolio = engine.snapshot_portfolio()
            print(
                json.dumps(
                    {
                        "type": "final",
                        "execution_mode": "paper",
                        "final_equity": round(final_portfolio.equity, 2),
                        "cash": round(final_portfolio.cash, 2),
                        "positions": final_portfolio.positions,
                        "state_path": str(state_path),
                    }
                )
            )
            return 0

        runtime = StrategyRuntime(strategy, state_store=state_store)
        if not args.reset_state:
            runtime.load_state()

        account = live_cli.positions(key_name=live_config.key_name, wallet_address=live_config.wallet_address)
        portfolio = strategy_portfolio_snapshot(account, equity_budget_usd=live_config.equity_budget_usd, timestamp=0)
        print(
            json.dumps(
                {
                    "type": "live_config",
                    "execution_mode": "live",
                    "wallet_mode": live_config.wallet_mode,
                    "equity_budget_usd": live_config.equity_budget_usd,
                    "leverage": live_config.leverage,
                    "input_token": live_config.input_token,
                    "receive_token": live_config.receive_token,
                    "min_position_change_usd": live_config.min_position_change_usd,
                    "jupiter_cli_path": live_config.jupiter_cli_path,
                    "jupiter_cli_dry_run": live_config.cli_dry_run_orders,
                    "jup_key": live_config.key_name,
                    "wallet_address": live_config.wallet_address,
                    "order_request_path": str(live_config.order_request_path),
                    "external_wallet_board_command": (
                        [
                            "uv",
                            "run",
                            "python",
                            "external_wallet_bridge.py",
                            "--request-path",
                            str(live_config.order_request_path),
                        ]
                        if live_config.wallet_mode == "external"
                        else None
                    ),
                    "starting_portfolio": serialize_portfolio(portfolio),
                }
            )
        )

        run_loop(
            feed,
            args.poll_seconds,
            lambda bar_snapshot: process_live_bar(runtime, live_cli, live_config, bar_snapshot),
        )

    except KeyboardInterrupt:
        pass
    finally:
        if args.execution_mode == "live" and live_cli is not None and live_config is not None:
            try:
                final_account = live_cli.positions(
                    key_name=live_config.key_name,
                    wallet_address=live_config.wallet_address,
                )
                final_portfolio = strategy_portfolio_snapshot(
                    final_account,
                    equity_budget_usd=live_config.equity_budget_usd,
                    timestamp=0,
                )
                print(
                    json.dumps(
                        {
                            "type": "final",
                            "execution_mode": "live",
                            "wallet_mode": live_config.wallet_mode,
                            "portfolio": serialize_portfolio(final_portfolio),
                            "order_request_path": str(live_config.order_request_path),
                            "state_path": str(state_path),
                        }
                    )
                )
            except Exception as exc:
                print(
                    json.dumps(
                        {
                            "type": "final_error",
                            "execution_mode": "live",
                            "error": str(exc),
                            "state_path": str(state_path),
                        }
                    ),
                    file=sys.stderr,
                )
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
