from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBENCH_ROOT = Path.home() / ".cache" / "autotrader" / "workbench"
DEFAULT_CONTROL_PATH = DEFAULT_WORKBENCH_ROOT / "experiments-control.json"
DEFAULT_STATUS_PATH = DEFAULT_WORKBENCH_ROOT / "experiments-status.json"
DEFAULT_EVENTS_PATH = DEFAULT_WORKBENCH_ROOT / "experiments-events.jsonl"
DEFAULT_MANIFEST_PATH = ROOT / "docs" / "jupiter_experiment_threads.json"
UV_COMMAND = os.environ.get("UV_COMMAND", "uv")
DEFAULT_EXPERIMENT_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "perps-trend-follow",
        "hypothesis": "Continuation after short-term strength works best when exits trail slowly and leverage stays capped.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "trend_following",
    },
    {
        "id": "perps-mean-revert",
        "hypothesis": "Short-lived exhaustion reversals outperform trend chasing when hold times stay tight.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "mean_reversion",
    },
    {
        "id": "perps-regime-switch",
        "hypothesis": "A volatility gate can switch between breakout and reversion logic more reliably than one static policy.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 15000,
        "split": "val",
        "search_space": "regime_switching",
    },
    {
        "id": "perps-borrow-decay",
        "hypothesis": "Carry-aware hold limits reduce decay from expensive funding windows.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 12000,
        "split": "val",
        "search_space": "carry_aware_exits",
    },
    {
        "id": "perps-impact-aware-sizing",
        "hypothesis": "Sizing down around poor liquidity conditions protects paper Sharpe more than forcing full entries.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 12000,
        "split": "val",
        "search_space": "impact_aware_sizing",
    },
    {
        "id": "perps-liquidation-buffer",
        "hypothesis": "A larger volatility-adjusted liquidation buffer improves survivability without killing return.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "liquidation_buffer",
    },
    {
        "id": "perps-limit-pullback",
        "hypothesis": "Pullback-style entries with restrained hold times produce cleaner paper fills than market chasing.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "limit_pullback",
    },
    {
        "id": "perps-relative-strength",
        "hypothesis": "Relative-strength rotation across BTC, ETH, and SOL concentrates exposure into the cleanest perp trend.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 15000,
        "split": "val",
        "search_space": "relative_strength_rotation",
    },
    {
        "id": "perps-compression-breakout",
        "hypothesis": "Volatility compression followed by expansion creates the highest-conviction perp breakout entries.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "compression_breakout",
    },
    {
        "id": "perps-failure-reversal",
        "hypothesis": "Failed breakout reversals outperform naive fades when invalidation is fast and deterministic.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "failure_reversal",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(fallback)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(fallback)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, indent=2, sort_keys=True)
    writer_id = f"{os.getpid()}.{threading.get_ident()}"
    last_error: OSError | None = None
    for attempt in range(5):
        temp_path = path.with_name(f"{path.name}.{writer_id}.{attempt}.tmp")
        try:
            temp_path.write_text(serialized, encoding="utf-8")
            os.replace(temp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            temp_path.unlink(missing_ok=True)
            time.sleep(0.05 * (attempt + 1))
        except OSError:
            temp_path.unlink(missing_ok=True)
            raise
    if last_error is not None:
        raise last_error


def append_event(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True))
        handle.write("\n")


def parse_metrics(stdout_text: str) -> dict[str, float | str]:
    metrics: dict[str, float | str] = {}
    for raw_line in stdout_text.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_").replace("%", "pct")
        raw_value = value.strip()
        if not raw_value:
            continue
        try:
            metrics[normalized_key] = float(raw_value.replace("%", "").strip())
        except ValueError:
            metrics[normalized_key] = raw_value
    return metrics


@dataclass(frozen=True)
class ExperimentConfig:
    id: str
    hypothesis: str
    objective: str
    symbols: tuple[str, ...]
    split: str
    paper_budget_usd: float
    search_space: str
    artifact_dir: Path
    output_dir: Path


class ExperimentManager:
    def __init__(
        self,
        *,
        control_path: Path,
        status_path: Path,
        events_path: Path,
        manifest_path: Path,
        cycle_delay_seconds: float,
        poll_seconds: float,
    ) -> None:
        self.control_path = control_path
        self.status_path = status_path
        self.events_path = events_path
        self.manifest_path = manifest_path
        self.cycle_delay_seconds = float(cycle_delay_seconds)
        self.poll_seconds = float(poll_seconds)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker_threads: list[threading.Thread] = []
        self._experiment_state: dict[str, dict[str, Any]] = {}
        self._manager_state: dict[str, Any] = {}
        self._configs = self._load_configs()
        for config in self._configs:
            self._experiment_state[config.id] = self._default_experiment_state(config)

    def _load_configs(self) -> list[ExperimentConfig]:
        if self.manifest_path.exists():
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        else:
            raw = DEFAULT_EXPERIMENT_MANIFEST
        configs: list[ExperimentConfig] = []
        base_dir = self.status_path.parent / "experiments"
        for item in raw:
            experiment_dir = base_dir / item["id"]
            configs.append(
                ExperimentConfig(
                    id=str(item["id"]),
                    hypothesis=str(item["hypothesis"]),
                    objective=str(item.get("objective", "paper_pnl_risk_adjusted")),
                    symbols=tuple(str(symbol).upper() for symbol in item.get("symbols", ["SOL"])),
                    split=str(item.get("split", "val")),
                    paper_budget_usd=float(item.get("paper_budget_usd", 10000)),
                    search_space=str(item.get("search_space", "unknown")),
                    artifact_dir=experiment_dir,
                    output_dir=experiment_dir / "latest",
                )
            )
        return configs

    def _default_control(self) -> dict[str, Any]:
        return {
            "manager": {"desired_state": "running"},
            "experiments": {config.id: {"desired_state": "running", "restart_nonce": 0} for config in self._configs},
        }

    def _default_experiment_state(self, config: ExperimentConfig) -> dict[str, Any]:
        return {
            "id": config.id,
            "state": "idle",
            "desired_state": "running",
            "iteration": 0,
            "hypothesis": config.hypothesis,
            "objective": config.objective,
            "search_space": config.search_space,
            "symbols": list(config.symbols),
            "split": config.split,
            "paper_budget_usd": config.paper_budget_usd,
            "artifact_dir": str(config.artifact_dir),
            "output_dir": str(config.output_dir),
            "last_started_at": None,
            "last_completed_at": None,
            "last_exit_code": None,
            "last_error": None,
            "last_metrics": {},
            "last_stdout_tail": "",
            "last_stderr_tail": "",
            "degraded": False,
            "degraded_reasons": [],
            "restart_nonce": 0,
            "command": [],
        }

    def _build_command(self, config: ExperimentConfig) -> list[str]:
        return [
            UV_COMMAND,
            "run",
            "python",
            str(ROOT / "backtest_5m.py"),
            "--split",
            config.split,
            "--symbols",
            *config.symbols,
            "--output-dir",
            str(config.output_dir),
        ]

    def _emit_event(self, event_type: str, *, experiment_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
        append_event(
            self.events_path,
            {
                "timestamp": utc_now(),
                "type": event_type,
                "experiment_id": experiment_id,
                "payload": payload or {},
            },
        )

    def _write_status(self) -> None:
        with self._lock:
            experiments = [dict(item) for item in self._experiment_state.values()]
            active = sum(1 for item in experiments if item.get("state") == "running")
            paused = sum(1 for item in experiments if item.get("state") == "paused")
            failed = sum(1 for item in experiments if item.get("last_error"))
            manager_state = self._manager_desired_state()
            leaders = [
                item
                for item in experiments
                if isinstance(item.get("last_metrics", {}).get("score"), float)
            ]
            leader = max(leaders, key=lambda item: float(item["last_metrics"]["score"]), default=None)
            self._manager_state = {
                "state": "stopped" if self._stop_event.is_set() else manager_state,
                "pid": os.getpid(),
                "manifest_path": str(self.manifest_path),
                "control_path": str(self.control_path),
                "status_path": str(self.status_path),
                "events_path": str(self.events_path),
                "last_updated_at": utc_now(),
                "summary": {
                    "experiment_count": len(experiments),
                    "active_count": active,
                    "paused_count": paused,
                    "failed_count": failed,
                    "manager_state": manager_state,
                    "leader_id": leader.get("id") if leader else None,
                    "leader_score": leader.get("last_metrics", {}).get("score") if leader else None,
                },
                "experiments": experiments,
            }
            write_json(self.status_path, self._manager_state)

    def _load_control(self) -> dict[str, Any]:
        current = read_json(self.control_path, self._default_control())
        experiments = current.setdefault("experiments", {})
        for config in self._configs:
            experiments.setdefault(config.id, {"desired_state": "running", "restart_nonce": 0})
        current.setdefault("manager", {"desired_state": "running"})
        return current

    def _manager_desired_state(self) -> str:
        control = self._load_control()
        return str(control.get("manager", {}).get("desired_state", "running")).lower()

    def start(self) -> None:
        write_json(self.control_path, self._load_control())
        self._emit_event("manager_started", payload={"manifest_path": str(self.manifest_path)})
        self._write_status()
        for config in self._configs:
            thread = threading.Thread(target=self._worker_loop, args=(config,), daemon=True, name=f"exp-{config.id}")
            self._worker_threads.append(thread)
            thread.start()

        while not self._stop_event.is_set():
            if self._manager_desired_state() == "stopped":
                self._stop_event.set()
                break
            self._write_status()
            time.sleep(max(self.poll_seconds, 0.25))

        self._emit_event("manager_stopped")
        self._write_status()

    def _worker_loop(self, config: ExperimentConfig) -> None:
        while not self._stop_event.is_set():
            control = self._load_control()
            manager_state = str(control.get("manager", {}).get("desired_state", "running")).lower()
            experiment_control = control.get("experiments", {}).get(config.id, {})
            desired_state = str(experiment_control.get("desired_state", "running")).lower()
            restart_nonce = int(experiment_control.get("restart_nonce", 0))

            with self._lock:
                state = self._experiment_state[config.id]
                state["desired_state"] = desired_state
                state["restart_nonce"] = restart_nonce

            if manager_state == "stopped" or desired_state == "stopped":
                with self._lock:
                    self._experiment_state[config.id]["state"] = "stopped"
                self._write_status()
                time.sleep(max(self.poll_seconds, 0.25))
                continue

            if manager_state == "paused" or desired_state == "paused":
                with self._lock:
                    self._experiment_state[config.id]["state"] = "paused"
                self._write_status()
                time.sleep(max(self.poll_seconds, 0.25))
                continue

            self._run_cycle(config, restart_nonce)
            time.sleep(max(self.cycle_delay_seconds, 0.0))

    def _run_cycle(self, config: ExperimentConfig, restart_nonce: int) -> None:
        command = self._build_command(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            state = self._experiment_state[config.id]
            state["state"] = "running"
            state["iteration"] += 1
            state["last_started_at"] = utc_now()
            state["last_error"] = None
            state["command"] = command
            iteration = state["iteration"]
        self._emit_event("cycle_started", experiment_id=config.id, payload={"iteration": iteration, "command": command})
        self._write_status()

        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        interrupted_reason: str | None = None
        while True:
            if process.poll() is not None:
                break
            if self._stop_event.is_set():
                interrupted_reason = "manager_stopping"
                process.terminate()
                break
            control = self._load_control()
            experiment_control = control.get("experiments", {}).get(config.id, {})
            desired_state = str(experiment_control.get("desired_state", "running")).lower()
            next_nonce = int(experiment_control.get("restart_nonce", 0))
            if desired_state in {"paused", "stopped"}:
                interrupted_reason = desired_state
                process.terminate()
                break
            if next_nonce != restart_nonce:
                interrupted_reason = "restart"
                process.terminate()
                break
            time.sleep(max(self.poll_seconds, 0.25))

        stdout_text, stderr_text = process.communicate()
        metrics = parse_metrics(stdout_text)
        degraded_reasons = []
        if not isinstance(metrics.get("score"), float):
            degraded_reasons.append("missing_score")
        with self._lock:
            state = self._experiment_state[config.id]
            state["state"] = "paused" if interrupted_reason == "paused" else ("stopped" if interrupted_reason == "stopped" else "idle")
            state["last_exit_code"] = 0 if interrupted_reason else process.returncode
            state["last_completed_at"] = utc_now()
            state["last_metrics"] = metrics
            state["last_stdout_tail"] = "\n".join(stdout_text.splitlines()[-20:])
            state["last_stderr_tail"] = "\n".join(stderr_text.splitlines()[-20:])
            state["degraded_reasons"] = degraded_reasons
            state["degraded"] = bool(degraded_reasons)
            if interrupted_reason:
                state["last_error"] = None
            elif process.returncode not in {0, None}:
                state["last_error"] = state["last_stderr_tail"] or f"cycle exited with code {process.returncode}"
            else:
                state["last_error"] = None

        event_payload = {
            "iteration": iteration,
            "exit_code": process.returncode,
            "interrupted_reason": interrupted_reason,
            "metrics": metrics,
            "degraded_reasons": degraded_reasons,
        }
        self._emit_event(
            "cycle_interrupted" if interrupted_reason else "cycle_completed",
            experiment_id=config.id,
            payload=event_payload,
        )
        self._write_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Message-based experiment manager for Jupiter paper research")
    parser.add_argument("--control", default=str(DEFAULT_CONTROL_PATH), help="Path to the manager control JSON file")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Path to the manager status JSON file")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_PATH), help="Path to the append-only manager event log")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Experiment manifest JSON path")
    parser.add_argument("--cycle-delay-seconds", type=float, default=5.0, help="Delay between cycles for a running experiment")
    parser.add_argument("--poll-seconds", type=float, default=1.0, help="Polling cadence for control updates")
    args = parser.parse_args()

    manager = ExperimentManager(
        control_path=Path(args.control).expanduser(),
        status_path=Path(args.status).expanduser(),
        events_path=Path(args.events).expanduser(),
        manifest_path=Path(args.manifest).expanduser(),
        cycle_delay_seconds=args.cycle_delay_seconds,
        poll_seconds=args.poll_seconds,
    )
    try:
        manager.start()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
