from __future__ import annotations

import argparse
import json
import os
import sys
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
DEFAULT_LOCK_PATH = DEFAULT_WORKBENCH_ROOT / "experiment-manager.lock.json"
DEFAULT_MANIFEST_PATH = ROOT / "docs" / "jupiter_experiment_threads.json"
UV_COMMAND = os.environ.get("UV_COMMAND", "uv")
MANAGER_LOCK_FD: int | None = None
DEFAULT_EXPERIMENT_MANIFEST: list[dict[str, Any]] = [
    {
        "id": "perps-trend-follow",
        "hypothesis": "Continuation after short-term strength works best when exits trail slowly and leverage stays capped.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "trend_following",
        "desired_state": "running",
        "focus_tier": "primary",
        "auto_pause_failed_gate_streak": 1,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-mean-revert",
        "hypothesis": "Short-lived exhaustion reversals outperform trend chasing when hold times stay tight.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "mean_reversion",
        "desired_state": "paused",
        "focus_tier": "parked",
        "auto_pause_failed_gate_streak": 1,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-regime-switch",
        "hypothesis": "A volatility gate can switch between breakout and reversion logic more reliably than one static policy.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 15000,
        "split": "val",
        "search_space": "regime_switching",
        "desired_state": "paused",
        "focus_tier": "parked",
        "auto_pause_failed_gate_streak": 3,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-borrow-decay",
        "hypothesis": "Carry-aware hold limits reduce decay from expensive funding windows.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 12000,
        "split": "val",
        "search_space": "carry_aware_exits",
        "desired_state": "running",
        "focus_tier": "secondary",
        "auto_pause_failed_gate_streak": 2,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-impact-aware-sizing",
        "hypothesis": "Sizing down around poor liquidity conditions protects paper Sharpe more than forcing full entries.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 12000,
        "split": "val",
        "search_space": "impact_aware_sizing",
        "desired_state": "running",
        "focus_tier": "primary",
        "auto_pause_failed_gate_streak": 2,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-liquidation-buffer",
        "hypothesis": "A larger volatility-adjusted liquidation buffer improves survivability without killing return.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "liquidation_buffer",
        "desired_state": "running",
        "focus_tier": "primary",
        "auto_pause_failed_gate_streak": 2,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-limit-pullback",
        "hypothesis": "Pullback-style entries with restrained hold times produce cleaner paper fills than market chasing.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "limit_pullback",
        "desired_state": "paused",
        "focus_tier": "parked",
        "auto_pause_failed_gate_streak": 1,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-relative-strength",
        "hypothesis": "Relative-strength rotation across BTC, ETH, and SOL concentrates exposure into the cleanest perp trend.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["BTC", "ETH", "SOL"],
        "paper_budget_usd": 15000,
        "split": "val",
        "search_space": "relative_strength_rotation",
        "desired_state": "paused",
        "focus_tier": "parked",
        "auto_pause_failed_gate_streak": 1,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-compression-breakout",
        "hypothesis": "Volatility compression followed by expansion creates the highest-conviction perp breakout entries.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "compression_breakout",
        "desired_state": "running",
        "focus_tier": "secondary",
        "auto_pause_failed_gate_streak": 3,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
    },
    {
        "id": "perps-failure-reversal",
        "hypothesis": "Failed breakout reversals outperform naive fades when invalidation is fast and deterministic.",
        "objective": "paper_pnl_risk_adjusted",
        "symbols": ["SOL"],
        "paper_budget_usd": 10000,
        "split": "val",
        "search_space": "failure_reversal",
        "desired_state": "paused",
        "focus_tier": "parked",
        "auto_pause_failed_gate_streak": 1,
        "auto_pause_failed_gates": ["max_drawdown_within_limit", "process_exit_clean", "score_available"],
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


def iso_to_epoch(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def pid_is_running(pid: int | None) -> bool:
    pid = safe_int(pid)
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                exit_code = wintypes.DWORD()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259
            finally:
                kernel32.CloseHandle(handle)
        except OSError:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def process_commandline(pid: int | None) -> str:
    pid = safe_int(pid)
    if pid is None or pid <= 0:
        return ""
    if os.name == "nt":
        try:
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"$proc = Get-CimInstance Win32_Process -Filter \"ProcessId = {pid}\" | Select-Object -ExpandProperty CommandLine; if ($proc) {{ $proc }}",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip()
    proc_path = Path("/proc") / str(pid) / "cmdline"
    if proc_path.exists():
        try:
            return proc_path.read_bytes().replace(b"\x00", b" ").decode("utf-8", errors="ignore").strip()
        except OSError:
            return ""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def pid_matches_command(pid: int | None, required_tokens: list[str]) -> bool:
    if not pid_is_running(pid):
        return False
    commandline = process_commandline(pid).lower()
    if not commandline:
        return False
    return all(token.lower() in commandline for token in required_tokens if token)


def active_manager_pid(lock_path: Path, status_path: Path) -> tuple[int | None, str | None]:
    required_tokens = ["experiment_manager.py", str(status_path)]
    lock_payload = read_json(lock_path, {})
    lock_pid = safe_int(lock_payload.get("pid"))
    if lock_pid is not None and pid_matches_command(lock_pid, required_tokens):
        return lock_pid, "lock"

    status_payload = read_json(status_path, {})
    status_pid = safe_int(status_payload.get("pid"))
    if status_pid is not None and pid_matches_command(status_pid, required_tokens):
        return status_pid, "status"

    return None, None


def acquire_manager_lock(
    lock_path: Path,
    *,
    control_path: Path,
    status_path: Path,
    events_path: Path,
    manifest_path: Path,
) -> None:
    global MANAGER_LOCK_FD
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 3.0
    while True:
        existing_pid, source = active_manager_pid(lock_path, status_path)
        if existing_pid is not None and existing_pid != os.getpid():
            raise RuntimeError(
                f"experiment manager already running with pid={existing_pid} from {source} metadata for {status_path}. "
                "Stop the existing manager before starting another one."
            )
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            if time.monotonic() < deadline:
                time.sleep(0.1)
                continue
            try:
                lock_path.unlink()
            except OSError:
                pass
            continue
        payload = json.dumps(
            {
                "pid": os.getpid(),
                "parent_pid": os.getppid(),
                "started_at": utc_now(),
                "cwd": str(ROOT),
                "control_path": str(control_path),
                "status_path": str(status_path),
                "events_path": str(events_path),
                "manifest_path": str(manifest_path),
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        try:
            os.write(fd, payload)
            os.fsync(fd)
        except OSError:
            os.close(fd)
            raise
        MANAGER_LOCK_FD = fd
        return


def release_manager_lock(lock_path: Path) -> None:
    global MANAGER_LOCK_FD
    if MANAGER_LOCK_FD is not None:
        try:
            os.close(MANAGER_LOCK_FD)
        finally:
            MANAGER_LOCK_FD = None
    existing = read_json(lock_path, {})
    existing_pid = safe_int(existing.get("pid"))
    if existing_pid == os.getpid() and lock_path.exists():
        lock_path.unlink(missing_ok=True)


def phase_for_state(state: str) -> str:
    mapping = {
        "running": "executing_cycle",
        "paused": "paused",
        "stopped": "stopped",
        "idle": "waiting_for_cycle",
    }
    return mapping.get(state, state or "unknown")


@dataclass(frozen=True)
class ExperimentConfig:
    id: str
    hypothesis: str
    objective: str
    symbols: tuple[str, ...]
    split: str
    paper_budget_usd: float
    search_space: str
    desired_state: str
    focus_tier: str
    auto_pause_failed_gate_streak: int
    auto_pause_failed_gates: tuple[str, ...]
    max_drawdown_pct: float
    min_trades: int
    min_score_delta: float
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
        self._restore_best_candidates()

    def _load_configs(self) -> list[ExperimentConfig]:
        if self.manifest_path.exists():
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        else:
            raw = DEFAULT_EXPERIMENT_MANIFEST
        if not isinstance(raw, list):
            raise ValueError(f"experiment manifest must be a JSON list: {self.manifest_path}")
        configs: list[ExperimentConfig] = []
        base_dir = self.status_path.parent / "experiments"
        seen_ids: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError(f"experiment manifest entries must be JSON objects: {item!r}")
            missing = [field for field in ("id", "hypothesis", "search_space") if field not in item]
            if missing:
                raise ValueError(f"experiment manifest entry missing required fields {missing}: {item!r}")
            experiment_id = str(item["id"]).strip()
            if not experiment_id:
                raise ValueError(f"experiment manifest entry has empty id: {item!r}")
            if experiment_id in seen_ids:
                raise ValueError(f"duplicate experiment id in manifest: {experiment_id}")
            seen_ids.add(experiment_id)
            symbols = tuple(str(symbol).upper() for symbol in item.get("symbols", ["SOL"]))
            if not symbols:
                raise ValueError(f"experiment {experiment_id} must declare at least one symbol")
            desired_state = str(item.get("desired_state", "running")).strip().lower() or "running"
            if desired_state not in {"running", "paused", "stopped"}:
                raise ValueError(
                    f"experiment {experiment_id} has invalid desired_state={desired_state!r}; expected running|paused|stopped"
                )
            focus_tier = str(item.get("focus_tier", "default")).strip().lower() or "default"
            auto_pause_failed_gate_streak = int(item.get("auto_pause_failed_gate_streak", 0))
            raw_auto_pause_failed_gates = item.get("auto_pause_failed_gates", [])
            if isinstance(raw_auto_pause_failed_gates, str):
                raw_auto_pause_failed_gates = [raw_auto_pause_failed_gates]
            auto_pause_failed_gates = tuple(
                str(gate).strip() for gate in raw_auto_pause_failed_gates if str(gate).strip()
            )
            experiment_dir = base_dir / item["id"]
            configs.append(
                ExperimentConfig(
                    id=experiment_id,
                    hypothesis=str(item["hypothesis"]),
                    objective=str(item.get("objective", "paper_pnl_risk_adjusted")),
                    symbols=symbols,
                    split=str(item.get("split", "val")),
                    paper_budget_usd=float(item.get("paper_budget_usd", 10000)),
                    search_space=str(item.get("search_space", "unknown")),
                    desired_state=desired_state,
                    focus_tier=focus_tier,
                    auto_pause_failed_gate_streak=auto_pause_failed_gate_streak,
                    auto_pause_failed_gates=auto_pause_failed_gates,
                    max_drawdown_pct=float(item.get("max_drawdown_pct", 15.0)),
                    min_trades=int(item.get("min_trades", 20)),
                    min_score_delta=float(item.get("min_score_delta", 0.0)),
                    artifact_dir=experiment_dir,
                    output_dir=experiment_dir / "latest",
                )
            )
        return configs

    def _default_control(self) -> dict[str, Any]:
        return {
            "manager": {"desired_state": "running"},
            "experiments": {
                config.id: {"desired_state": config.desired_state, "restart_nonce": 0}
                for config in self._configs
            },
        }

    def _default_experiment_state(self, config: ExperimentConfig) -> dict[str, Any]:
        initial_state = "idle"
        if config.desired_state == "paused":
            initial_state = "paused"
        elif config.desired_state == "stopped":
            initial_state = "stopped"
        return {
            "id": config.id,
            "state": initial_state,
            "desired_state": config.desired_state,
            "iteration": 0,
            "hypothesis": config.hypothesis,
            "objective": config.objective,
            "search_space": config.search_space,
            "focus_tier": config.focus_tier,
            "symbols": list(config.symbols),
            "split": config.split,
            "paper_budget_usd": config.paper_budget_usd,
            "auto_pause_failed_gate_streak": config.auto_pause_failed_gate_streak,
            "auto_pause_failed_gates": list(config.auto_pause_failed_gates),
            "max_drawdown_pct": config.max_drawdown_pct,
            "min_trades": config.min_trades,
            "min_score_delta": config.min_score_delta,
            "artifact_dir": str(config.artifact_dir),
            "output_dir": str(config.output_dir),
            "cycle_records_dir": str(config.artifact_dir / "cycles"),
            "last_started_at": None,
            "last_completed_at": None,
            "last_heartbeat_at": None,
            "cycle_runtime_seconds": None,
            "phase": "waiting_for_cycle",
            "phase_detail": "idle",
            "phase_started_at": None,
            "last_phase_transition_at": None,
            "last_exit_code": None,
            "last_error": None,
            "last_metrics": {},
            "best_score": None,
            "best_iteration": None,
            "best_metrics": {},
            "best_cycle_record_path": None,
            "latest_cycle_record_path": None,
            "last_plan": {},
            "last_verification": {},
            "last_decision": {},
            "last_stdout_tail": "",
            "last_stderr_tail": "",
            "degraded": False,
            "degraded_reasons": [],
            "health": "idle",
            "health_reasons": [],
            "failed_gate_streak": 0,
            "auto_pause_reason": None,
            "restart_nonce": 0,
            "command": [],
        }

    def _restore_best_candidates(self) -> None:
        for config in self._configs:
            best_path = config.artifact_dir / "best-candidate.json"
            if not best_path.exists():
                continue
            try:
                payload = json.loads(best_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
            candidate_score = metrics.get("score") if isinstance(metrics.get("score"), (int, float)) else None
            with self._lock:
                state = self._experiment_state[config.id]
                if candidate_score is not None:
                    state["best_score"] = float(candidate_score)
                state["best_iteration"] = payload.get("iteration")
                state["best_metrics"] = metrics
                state["best_cycle_record_path"] = payload.get("cycle_record_path")

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

    def _build_environment(self, config: ExperimentConfig) -> dict[str, str]:
        env = os.environ.copy()
        env["AUTOTRADER_EXPERIMENT_ID"] = config.id
        env["AUTOTRADER_EXPERIMENT_PROFILE"] = config.search_space
        env["AUTOTRADER_EXPERIMENT_HYPOTHESIS"] = config.hypothesis
        return env

    def _cycle_record_path(self, config: ExperimentConfig, iteration: int) -> Path:
        return config.artifact_dir / "cycles" / f"cycle-{iteration:05d}.json"

    def _cycle_plan(self, config: ExperimentConfig, *, iteration: int, command: list[str]) -> dict[str, Any]:
        return {
            "iteration": iteration,
            "experiment_id": config.id,
            "hypothesis": config.hypothesis,
            "objective": config.objective,
            "search_space": config.search_space,
            "symbols": list(config.symbols),
            "split": config.split,
            "paper_budget_usd": config.paper_budget_usd,
            "command": command,
            "assumptions": [
                "score comparisons are only valid within the same experiment manifest entry",
                "promotion requires passing verification gates before baseline replacement",
                "validation split, symbol universe, and search_space remain fixed for this thread",
            ],
            "verification_policy": {
                "max_drawdown_pct": config.max_drawdown_pct,
                "min_trades": config.min_trades,
                "min_score_delta": config.min_score_delta,
                "auto_pause_failed_gate_streak": config.auto_pause_failed_gate_streak,
                "auto_pause_failed_gates": list(config.auto_pause_failed_gates),
            },
            "planned_at": utc_now(),
        }

    def _verification_snapshot(
        self,
        config: ExperimentConfig,
        *,
        metrics: dict[str, float | str],
        exit_code: int | None,
        interrupted_reason: str | None,
        degraded_reasons: list[str],
        baseline_score: float | None,
    ) -> dict[str, Any]:
        candidate_score = metrics.get("score") if isinstance(metrics.get("score"), float) else None
        candidate_drawdown = metrics.get("max_drawdown_pct") if isinstance(metrics.get("max_drawdown_pct"), float) else None
        candidate_trades_raw = metrics.get("num_trades")
        candidate_trades = int(candidate_trades_raw) if isinstance(candidate_trades_raw, float) else None
        gates = {
            "process_exit_clean": interrupted_reason is None and exit_code == 0,
            "score_available": candidate_score is not None,
            "not_degraded": not degraded_reasons,
            "max_drawdown_within_limit": candidate_drawdown is not None and candidate_drawdown <= config.max_drawdown_pct,
            "min_trade_count_met": candidate_trades is not None and candidate_trades >= config.min_trades,
        }
        failed_gates = [name for name, passed in gates.items() if not passed]
        return {
            "candidate_score": candidate_score,
            "baseline_score": baseline_score,
            "score_delta": None if candidate_score is None or baseline_score is None else candidate_score - baseline_score,
            "candidate_drawdown_pct": candidate_drawdown,
            "candidate_trades": candidate_trades,
            "exit_code": exit_code,
            "interrupted_reason": interrupted_reason,
            "degraded_reasons": list(degraded_reasons),
            "gates": gates,
            "failed_gates": failed_gates,
            "passed": not failed_gates,
            "verified_at": utc_now(),
        }

    def _decision_snapshot(self, config: ExperimentConfig, verification: dict[str, Any]) -> dict[str, Any]:
        baseline_score = verification.get("baseline_score")
        candidate_score = verification.get("candidate_score")
        score_delta = verification.get("score_delta")
        if verification.get("interrupted_reason"):
            status = "interrupted"
            reason = str(verification["interrupted_reason"])
        elif not verification.get("passed"):
            status = "reject"
            failed_gates = verification.get("failed_gates") or ["verification_failed"]
            reason = ",".join(str(item) for item in failed_gates)
        elif baseline_score is None:
            status = "promote"
            reason = "initial_verified_candidate"
        elif isinstance(candidate_score, float) and isinstance(score_delta, float) and score_delta > config.min_score_delta:
            status = "promote"
            reason = "score_above_baseline"
        else:
            status = "reject"
            reason = "score_not_above_baseline"
        return {
            "status": status,
            "reason": reason,
            "candidate_score": candidate_score,
            "baseline_score": baseline_score,
            "score_delta": score_delta,
            "decided_at": utc_now(),
        }

    def _write_cycle_record(self, path: Path, payload: dict[str, Any]) -> None:
        write_json(path, payload)

    def _decision_counts(self, experiments: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in experiments:
            status = str((item.get("last_decision") or {}).get("status", "none"))
            counts[status] = counts.get(status, 0) + 1
        return counts

    def _focus_tier_counts(self, experiments: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in experiments:
            tier = str(item.get("focus_tier", "default"))
            counts[tier] = counts.get(tier, 0) + 1
        return counts

    def _update_experiment_control_state(self, experiment_id: str, desired_state: str) -> None:
        control = self._load_control()
        experiments = control.setdefault("experiments", {})
        experiment = experiments.setdefault(experiment_id, {"desired_state": desired_state, "restart_nonce": 0})
        experiment["desired_state"] = desired_state
        write_json(self.control_path, control)

    def _set_phase(
        self,
        config: ExperimentConfig,
        phase: str,
        *,
        detail: str | None = None,
        emit_event: bool = True,
        payload: dict[str, Any] | None = None,
    ) -> None:
        timestamp = utc_now()
        with self._lock:
            state = self._experiment_state[config.id]
            phase_changed = state.get("phase") != phase or state.get("phase_detail") != detail
            state["phase"] = phase
            state["phase_detail"] = detail
            if phase_changed:
                state["phase_started_at"] = timestamp
                state["last_phase_transition_at"] = timestamp
            iteration = state.get("iteration", 0)
        if emit_event and phase_changed:
            event_payload = {
                "iteration": iteration,
                "phase": phase,
                "phase_detail": detail,
                "search_space": config.search_space,
            }
            if payload:
                event_payload.update(payload)
            self._emit_event("cycle_phase_changed", experiment_id=config.id, payload=event_payload)

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

    def _health_snapshot(self, item: dict[str, Any]) -> tuple[str, list[str]]:
        reasons: list[str] = []
        state = str(item.get("state", "idle"))
        desired_state = str(item.get("desired_state", "running"))
        if item.get("degraded"):
            reasons.extend(str(reason) for reason in item.get("degraded_reasons", []))
        if item.get("last_error"):
            reasons.append("last_error")
        if desired_state != state and not (desired_state == "running" and state == "idle"):
            reasons.append("state_drift")
        now = time.time()
        started_at = iso_to_epoch(item.get("last_started_at"))
        completed_at = iso_to_epoch(item.get("last_completed_at"))
        if state == "running" and started_at is not None:
            runtime = max(0.0, now - started_at)
            if runtime > max(180.0, self.cycle_delay_seconds + 150.0):
                reasons.append("slow_cycle")
        if state == "idle" and desired_state == "running" and completed_at is not None:
            idle_for = max(0.0, now - completed_at)
            if idle_for > max(30.0, self.cycle_delay_seconds + 20.0):
                reasons.append("reconcile_lag")
        if "last_error" in reasons:
            return "failed", reasons
        if reasons:
            return "degraded", reasons
        if state == "running":
            return "healthy", []
        if state == "paused":
            return "paused", []
        if state == "stopped":
            return "stopped", []
        return "idle", []

    def _write_status(self) -> None:
        with self._lock:
            experiments = []
            for item in self._experiment_state.values():
                snapshot = dict(item)
                health, health_reasons = self._health_snapshot(snapshot)
                snapshot["health"] = health
                snapshot["health_reasons"] = health_reasons
                experiments.append(snapshot)
            active = sum(1 for item in experiments if item.get("state") == "running")
            paused = sum(1 for item in experiments if item.get("state") == "paused")
            failed = sum(1 for item in experiments if item.get("last_error"))
            degraded = sum(1 for item in experiments if item.get("health") == "degraded")
            drifted = sum(1 for item in experiments if "state_drift" in item.get("health_reasons", []))
            manager_state = self._manager_desired_state()
            leaders = [
                item
                for item in experiments
                if isinstance(item.get("best_score"), float)
            ]
            leader = max(leaders, key=lambda item: float(item["best_score"]), default=None)
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
                    "degraded_count": degraded,
                    "drift_count": drifted,
                    "manager_state": manager_state,
                    "leader_id": leader.get("id") if leader else None,
                    "leader_score": leader.get("best_score") if leader else None,
                    "phase_counts": self._phase_counts(experiments),
                    "decision_counts": self._decision_counts(experiments),
                    "focus_tier_counts": self._focus_tier_counts(experiments),
                },
                "experiments": experiments,
            }
            write_json(self.status_path, self._manager_state)

    def _phase_counts(self, experiments: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in experiments:
            phase = str(item.get("phase", "unknown"))
            counts[phase] = counts.get(phase, 0) + 1
        return counts

    def _load_control(self) -> dict[str, Any]:
        current = read_json(self.control_path, self._default_control())
        experiments = current.setdefault("experiments", {})
        for config in self._configs:
            experiments.setdefault(config.id, {"desired_state": config.desired_state, "restart_nonce": 0})
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
                    self._experiment_state[config.id]["cycle_runtime_seconds"] = None
                self._set_phase(config, "stopped", detail="control_target_stopped", emit_event=False)
                self._write_status()
                time.sleep(max(self.poll_seconds, 0.25))
                continue

            if manager_state == "paused" or desired_state == "paused":
                with self._lock:
                    self._experiment_state[config.id]["state"] = "paused"
                    self._experiment_state[config.id]["cycle_runtime_seconds"] = None
                self._set_phase(config, "paused", detail="control_target_paused", emit_event=False)
                self._write_status()
                time.sleep(max(self.poll_seconds, 0.25))
                continue

            self._run_cycle(config, restart_nonce)
            self._set_phase(config, "waiting_for_cycle", detail="cooldown_before_next_cycle")
            self._write_status()
            time.sleep(max(self.cycle_delay_seconds, 0.0))

    def _run_cycle(self, config: ExperimentConfig, restart_nonce: int) -> None:
        command = self._build_command(config)
        env = self._build_environment(config)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        with self._lock:
            state = self._experiment_state[config.id]
            state["state"] = "running"
            state["iteration"] += 1
            state["last_started_at"] = utc_now()
            state["last_heartbeat_at"] = utc_now()
            state["cycle_runtime_seconds"] = 0.0
            state["last_error"] = None
            state["command"] = command
            iteration = state["iteration"]
            cycle_record_path = self._cycle_record_path(config, iteration)
            cycle_plan = self._cycle_plan(config, iteration=iteration, command=command)
            state["latest_cycle_record_path"] = str(cycle_record_path)
            state["last_plan"] = cycle_plan
        self._set_phase(config, "planning_cycle", detail="capturing_hypothesis_and_assumptions", emit_event=False)
        self._write_cycle_record(
            cycle_record_path,
            {
                "experiment_id": config.id,
                "iteration": iteration,
                "plan": cycle_plan,
                "status": {"phase": "planning_cycle", "phase_detail": "capturing_hypothesis_and_assumptions"},
            },
        )
        self._emit_event(
            "cycle_planned",
            experiment_id=config.id,
            payload={
                "iteration": iteration,
                "hypothesis": config.hypothesis,
                "search_space": config.search_space,
                "phase": "planning_cycle",
                "phase_detail": "capturing_hypothesis_and_assumptions",
                "cycle_record_path": str(cycle_record_path),
            },
        )
        self._set_phase(config, "launching_cycle", detail="preparing_subprocess", emit_event=False)
        self._emit_event(
            "cycle_started",
            experiment_id=config.id,
            payload={
                "iteration": iteration,
                "command": command,
                "phase": "launching_cycle",
                "phase_detail": "preparing_subprocess",
                "search_space": config.search_space,
                "desired_state": "running",
                "symbols": list(config.symbols),
                "cycle_record_path": str(cycle_record_path),
            },
        )
        self._write_status()

        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._set_phase(config, "executing_cycle", detail="backtest_running")
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
            with self._lock:
                running_state = self._experiment_state[config.id]
                running_state["last_heartbeat_at"] = utc_now()
                started_at = iso_to_epoch(running_state.get("last_started_at"))
                running_state["cycle_runtime_seconds"] = max(0.0, time.time() - started_at) if started_at is not None else None
            time.sleep(max(self.poll_seconds, 0.25))

        self._set_phase(
            config,
            "collecting_results",
            detail="waiting_for_process_output",
            payload={"interrupted_reason": interrupted_reason, "cycle_record_path": str(cycle_record_path)},
        )
        stdout_text, stderr_text = process.communicate()
        self._set_phase(
            config,
            "verifying_candidate",
            detail="checking_experimental_gates",
            payload={"interrupted_reason": interrupted_reason, "cycle_record_path": str(cycle_record_path)},
        )
        metrics = parse_metrics(stdout_text)
        degraded_reasons = []
        if not isinstance(metrics.get("score"), float):
            degraded_reasons.append("missing_score")
        with self._lock:
            state = self._experiment_state[config.id]
            baseline_score = state.get("best_score") if isinstance(state.get("best_score"), float) else None
            state["state"] = "paused" if interrupted_reason == "paused" else ("stopped" if interrupted_reason == "stopped" else "idle")
            state["last_exit_code"] = 0 if interrupted_reason else process.returncode
            state["last_completed_at"] = utc_now()
            state["last_heartbeat_at"] = utc_now()
            state["last_metrics"] = metrics
            state["last_stdout_tail"] = "\n".join(stdout_text.splitlines()[-20:])
            state["last_stderr_tail"] = "\n".join(stderr_text.splitlines()[-20:])
            state["degraded_reasons"] = degraded_reasons
            state["degraded"] = bool(degraded_reasons)
            started_at = iso_to_epoch(state.get("last_started_at"))
            state["cycle_runtime_seconds"] = max(0.0, time.time() - started_at) if started_at is not None else None
            if interrupted_reason:
                state["last_error"] = None
            elif process.returncode not in {0, None}:
                state["last_error"] = state["last_stderr_tail"] or f"cycle exited with code {process.returncode}"
            else:
                state["last_error"] = None
        verification = self._verification_snapshot(
            config,
            metrics=metrics,
            exit_code=process.returncode,
            interrupted_reason=interrupted_reason,
            degraded_reasons=degraded_reasons,
            baseline_score=baseline_score,
        )
        failed_gates = {str(name) for name in verification.get("failed_gates", [])}
        tracked_failed_gates = failed_gates.intersection(config.auto_pause_failed_gates)
        auto_pause_reason: str | None = None
        failed_gate_streak = 0
        with self._lock:
            state = self._experiment_state[config.id]
            state["last_verification"] = verification
            if interrupted_reason:
                failed_gate_streak = int(state.get("failed_gate_streak", 0) or 0)
            elif config.auto_pause_failed_gate_streak > 0 and tracked_failed_gates:
                failed_gate_streak = int(state.get("failed_gate_streak", 0) or 0) + 1
                state["failed_gate_streak"] = failed_gate_streak
            else:
                failed_gate_streak = 0
                state["failed_gate_streak"] = 0
                state["auto_pause_reason"] = None
            if (
                not interrupted_reason
                and config.auto_pause_failed_gate_streak > 0
                and tracked_failed_gates
                and failed_gate_streak >= config.auto_pause_failed_gate_streak
                and state.get("desired_state") == "running"
            ):
                auto_pause_reason = (
                    f"auto_pause_after_failed_gates:{','.join(sorted(tracked_failed_gates))}"
                )
                state["desired_state"] = "paused"
                state["state"] = "paused"
                state["auto_pause_reason"] = auto_pause_reason
        if auto_pause_reason:
            self._update_experiment_control_state(config.id, "paused")
            self._emit_event(
                "experiment_auto_paused",
                experiment_id=config.id,
                payload={
                    "iteration": iteration,
                    "search_space": config.search_space,
                    "cycle_record_path": str(cycle_record_path),
                    "failed_gate_streak": failed_gate_streak,
                    "tracked_failed_gates": sorted(tracked_failed_gates),
                    "reason": auto_pause_reason,
                },
            )
        self._emit_event(
            "candidate_verified",
            experiment_id=config.id,
            payload={
                "iteration": iteration,
                "search_space": config.search_space,
                "phase": "verifying_candidate",
                "phase_detail": "checking_experimental_gates",
                "cycle_record_path": str(cycle_record_path),
                "verification": verification,
                "failed_gate_streak": failed_gate_streak,
                "tracked_failed_gates": sorted(tracked_failed_gates),
                "auto_pause_reason": auto_pause_reason,
            },
        )
        self._set_phase(
            config,
            "decisioning_candidate",
            detail="baseline_replacement_decision",
            payload={"cycle_record_path": str(cycle_record_path)},
        )
        decision = self._decision_snapshot(config, verification)
        if auto_pause_reason:
            decision["auto_paused"] = True
            decision["auto_pause_reason"] = auto_pause_reason
        with self._lock:
            state = self._experiment_state[config.id]
            state["last_decision"] = decision
            if decision["status"] == "promote":
                state["best_score"] = decision.get("candidate_score")
                state["best_iteration"] = iteration
                state["best_metrics"] = dict(metrics)
                state["best_cycle_record_path"] = str(cycle_record_path)
                write_json(
                    config.artifact_dir / "best-candidate.json",
                    {
                        "experiment_id": config.id,
                        "iteration": iteration,
                        "metrics": metrics,
                        "verification": verification,
                        "decision": decision,
                        "cycle_record_path": str(cycle_record_path),
                    },
                )
        self._emit_event(
            "candidate_decided",
            experiment_id=config.id,
            payload={
                "iteration": iteration,
                "search_space": config.search_space,
                "phase": "decisioning_candidate",
                "phase_detail": "baseline_replacement_decision",
                "cycle_record_path": str(cycle_record_path),
                "decision": decision,
            },
        )
        if decision["status"] == "promote":
            self._emit_event(
                "candidate_promoted",
                experiment_id=config.id,
                payload={
                    "iteration": iteration,
                    "search_space": config.search_space,
                    "cycle_record_path": str(cycle_record_path),
                    "decision": decision,
                },
            )
        terminal_phase = "cycle_interrupted" if interrupted_reason else "cycle_completed"
        terminal_detail = interrupted_reason or decision["status"]
        self._set_phase(
            config,
            terminal_phase,
            detail=terminal_detail,
            payload={
                "metrics": metrics,
                "degraded_reasons": degraded_reasons,
                "cycle_record_path": str(cycle_record_path),
                "decision": decision,
            },
        )
        event_payload = {
            "iteration": iteration,
            "exit_code": process.returncode,
            "interrupted_reason": interrupted_reason,
            "metrics": metrics,
            "degraded_reasons": degraded_reasons,
            "search_space": config.search_space,
            "desired_state": state["desired_state"],
            "health": self._health_snapshot(dict(self._experiment_state[config.id]))[0],
            "phase": terminal_phase,
            "phase_detail": terminal_detail,
            "cycle_record_path": str(cycle_record_path),
            "verification": verification,
            "decision": decision,
        }
        self._emit_event(
            "cycle_interrupted" if interrupted_reason else "cycle_completed",
            experiment_id=config.id,
            payload=event_payload,
        )
        with self._lock:
            latest_state = dict(self._experiment_state[config.id])
        self._write_cycle_record(
            cycle_record_path,
            {
                "experiment_id": config.id,
                "iteration": iteration,
                "plan": cycle_plan,
                "results": {
                    "metrics": metrics,
                    "exit_code": process.returncode,
                    "interrupted_reason": interrupted_reason,
                    "stdout_tail": latest_state.get("last_stdout_tail"),
                    "stderr_tail": latest_state.get("last_stderr_tail"),
                    "completed_at": latest_state.get("last_completed_at"),
                },
                "verification": verification,
                "decision": decision,
                "best_after_cycle": {
                    "best_score": latest_state.get("best_score"),
                    "best_iteration": latest_state.get("best_iteration"),
                    "best_cycle_record_path": latest_state.get("best_cycle_record_path"),
                },
                "status": {"phase": terminal_phase, "phase_detail": terminal_detail},
            },
        )
        next_phase = phase_for_state(state["state"])
        next_detail = "awaiting_next_cycle" if state["state"] == "idle" else terminal_detail
        self._set_phase(config, next_phase, detail=next_detail, emit_event=False)
        self._write_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Message-based experiment manager for Jupiter paper research")
    parser.add_argument("--control", default=str(DEFAULT_CONTROL_PATH), help="Path to the manager control JSON file")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Path to the manager status JSON file")
    parser.add_argument("--events", default=str(DEFAULT_EVENTS_PATH), help="Path to the append-only manager event log")
    parser.add_argument("--lock", default=str(DEFAULT_LOCK_PATH), help="Path to the manager singleton lock file")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH), help="Experiment manifest JSON path")
    parser.add_argument("--cycle-delay-seconds", type=float, default=5.0, help="Delay between cycles for a running experiment")
    parser.add_argument("--poll-seconds", type=float, default=1.0, help="Polling cadence for control updates")
    args = parser.parse_args()

    control_path = Path(args.control).expanduser()
    status_path = Path(args.status).expanduser()
    events_path = Path(args.events).expanduser()
    manifest_path = Path(args.manifest).expanduser()
    lock_path = Path(args.lock).expanduser()
    manager = ExperimentManager(
        control_path=control_path,
        status_path=status_path,
        events_path=events_path,
        manifest_path=manifest_path,
        cycle_delay_seconds=args.cycle_delay_seconds,
        poll_seconds=args.poll_seconds,
    )
    try:
        acquire_manager_lock(
            lock_path,
            control_path=control_path,
            status_path=status_path,
            events_path=events_path,
            manifest_path=manifest_path,
        )
        manager.start()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        release_manager_lock(lock_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
