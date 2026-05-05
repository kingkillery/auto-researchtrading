from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from paper_engine import PaperTradingEngine
from paper_state import JsonStateStore, _jsonable, default_state_path
from paper_trade import load_strategy
from workbench_auth import WorkbenchAuth, load_auth_config_from_env


HOST = "0.0.0.0"


def resolve_port(env: dict[str, str]) -> int:
    if env.get("WORKBENCH_PORT"):
        return int(env["WORKBENCH_PORT"])
    # In hosted Fly/runtime environments, PORT is the platform contract.
    if env.get("FLY_APP_NAME") or env.get("FLY_ALLOC_ID") or env.get("FLY_MACHINE_ID"):
        return int(env.get("PORT", "8080"))
    # For local operator runs, ignore any unrelated ambient PORT and keep the
    # workbench on its stable default unless explicitly overridden.
    return 8080


PORT = resolve_port(dict(os.environ))
STRATEGY_SPEC = os.environ.get("STRATEGY_SPEC", "strategy:Strategy")
RESET_STATE = os.environ.get("RESET_STATE", "").lower() in {"1", "true", "yes", "on"}
ROOT = Path(__file__).resolve().parent
LOGO_PATH = ROOT / "assets" / "logo.png"
RESULTS_PATH = ROOT / "results.tsv"
RESEARCH_PATH = ROOT / "autoresearch-results.tsv"
EQUITY_PATH = ROOT / "equity_curve.csv"
BASELINE_PATH = ROOT / "equity_curve_baseline.csv"
TRADE_POSTMORTEMS_PATH = ROOT / "docs" / "trade_postmortems.md"
WORKBENCH_TEMPLATE_PATH = ROOT / "dashboard_template.html"
GENERATIVE_ARTIFACT_PATH = ROOT / "artifacts" / "dashboard-generative-ui" / "bundle.html"
WORKBENCH_ROOT = Path.home() / ".cache" / "autotrader" / "workbench"
WORKBENCH_LOCK_PATH = WORKBENCH_ROOT / "workbench.lock.json"
WORKBENCH_LOCK_FD: int | None = None
WORKBENCH_AUTOSTART = os.environ.get("WORKBENCH_AUTOSTART", "1").lower() not in {"0", "false", "no", "off"}
WORKBENCH_SYMBOLS = os.environ.get("WORKBENCH_SYMBOLS", "BTC ETH SOL").split()
WORKBENCH_PAPER_PROFILE = os.environ.get(
    "WORKBENCH_PAPER_PROFILE",
    os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE", ""),
).strip().lower()
WORKBENCH_PAPER_WARMUP_SPLIT = os.environ.get("WORKBENCH_PAPER_WARMUP_SPLIT", "").strip().lower()
WORKBENCH_PAPER_WARMUP_BARS = int(os.environ.get("WORKBENCH_PAPER_WARMUP_BARS", "500"))
WORKBENCH_POLL_SECONDS = float(os.environ.get("WORKBENCH_POLL_SECONDS", "30"))
WORKBENCH_BAR_SECONDS = int(os.environ.get("WORKBENCH_BAR_SECONDS", "300"))
WORKBENCH_EXPERIMENT_DELAY = float(os.environ.get("WORKBENCH_EXPERIMENT_DELAY", "5"))
WORKBENCH_EXPERIMENT_MANIFEST = Path(
    os.environ.get("WORKBENCH_EXPERIMENT_MANIFEST", str(ROOT / "docs" / "jupiter_experiment_threads.json"))
).expanduser()
UV_COMMAND = os.environ.get("UV_COMMAND", "uv")
AUTH = WorkbenchAuth(load_auth_config_from_env(dict(os.environ)))


def resolve_state_path() -> Path:
    if os.environ.get("STATE_PATH"):
        return Path(os.environ["STATE_PATH"]).expanduser()
    base = default_state_path(STRATEGY_SPEC)
    if not WORKBENCH_PAPER_PROFILE:
        return base
    safe_profile = "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in WORKBENCH_PAPER_PROFILE
    )
    return base.with_name(f"{base.stem}_{safe_profile}{base.suffix}")


STATE_PATH = resolve_state_path()


def build_engine() -> PaperTradingEngine:
    strategy = load_strategy(STRATEGY_SPEC)
    engine = PaperTradingEngine(strategy, state_store=JsonStateStore(STATE_PATH))
    if not RESET_STATE:
        engine.load_state()
    return engine


ENGINE = build_engine()
ENGINE_LOCK = threading.RLock()


def refresh_engine_from_state() -> None:
    with ENGINE_LOCK:
        ENGINE.load_state()


def to_jsonable(value: Any) -> Any:
    return _jsonable(value)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_float(value: str | None) -> float | None:
    if value in {None, "", "-"}:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def read_tsv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def read_curve(path: Path, max_points: int = 180) -> dict[str, Any]:
    if not path.exists():
        return {"points": [], "summary": None}
    all_points: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                all_points.append({"timestamp": row["timestamp"], "equity": float(row["equity"])})
            except (KeyError, TypeError, ValueError):
                continue
    if not all_points:
        return {"points": [], "summary": None}
    points = list(all_points)
    if len(points) > max_points:
        step = max(1, len(points) // max_points)
        sampled = points[::step]
        if sampled[-1]["timestamp"] != points[-1]["timestamp"]:
            sampled.append(points[-1])
        points = sampled
    start = all_points[0]["equity"]
    latest = all_points[-1]["equity"]
    return {
        "points": points,
        "summary": {
            "start_equity": start,
            "latest_equity": latest,
            "peak_equity": max(point["equity"] for point in all_points),
            "return_pct": 0.0 if start == 0 else ((latest / start) - 1.0) * 100.0,
        },
    }


def trading_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    parsed = []
    status_counts: dict[str, int] = {}
    for row in rows:
        item = {
            "commit": row.get("commit", ""),
            "description": row.get("description", ""),
            "status": row.get("status", "unknown"),
            "score": parse_float(row.get("score")),
            "sharpe": parse_float(row.get("sharpe")),
            "max_dd": parse_float(row.get("max_dd")),
        }
        parsed.append(item)
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    scored = [row for row in parsed if row["score"] is not None]
    best = max(scored, key=lambda row: row["score"], default=None)
    return {
        "summary": {
            "total_experiments": len(parsed),
            "best_score": best["score"] if best else None,
            "best_commit": best["commit"] if best else None,
            "best_description": best["description"] if best else None,
        },
        "leaders": sorted(scored, key=lambda row: row["score"], reverse=True)[:6],
        "recent": list(reversed(parsed[-8:])),
        "status_counts": status_counts,
    }


def research_summary(rows: list[dict[str, str]]) -> dict[str, Any]:
    parsed = []
    status_counts: dict[str, int] = {}
    for row in rows:
        item = {
            "commit": row.get("commit", ""),
            "description": row.get("description", ""),
            "status": row.get("status", "unknown"),
            "val_bpb": parse_float(row.get("val_bpb")),
        }
        parsed.append(item)
        status_counts[item["status"]] = status_counts.get(item["status"], 0) + 1
    best = min((row for row in parsed if row["val_bpb"] is not None), key=lambda row: row["val_bpb"], default=None)
    return {
        "summary": {
            "total_runs": len(parsed),
            "best_val_bpb": best["val_bpb"] if best else None,
            "best_commit": best["commit"] if best else None,
        },
        "status_counts": status_counts,
    }


def recent_manager_events(path: Path, limit: int = 12) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    except OSError:
        return []
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return list(reversed(events))


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


def append_markdown_entry(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing and not existing.endswith("\n"):
            existing += "\n"
    path.write_text(f"{existing}{markdown.rstrip()}\n\n", encoding="utf-8")


def last_markdown_entry(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return ""
    parts = content.split("\n\n## ")
    if len(parts) == 1:
        return content
    return f"## {parts[-1]}".strip()


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


def terminate_pid_tree(pid: int | None) -> bool:
    pid = safe_int(pid)
    if pid is None or pid <= 0:
        return False
    if not pid_is_running(pid):
        return True
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 10.0
        while time.time() < deadline:
            if not pid_is_running(pid):
                return True
            time.sleep(0.2)
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if not pid_is_running(pid):
                return True
            time.sleep(0.2)
        return not pid_is_running(pid)
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return not pid_is_running(pid)
    deadline = time.time() + 10.0
    while time.time() < deadline:
        if not pid_is_running(pid):
            return True
        time.sleep(0.2)
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            return not pid_is_running(pid)
    return not pid_is_running(pid)


def acquire_workbench_lock() -> None:
    global WORKBENCH_LOCK_FD
    WORKBENCH_ROOT.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 3.0
    while True:
        try:
            fd = os.open(WORKBENCH_LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_RDWR)
        except FileExistsError:
            existing = read_json(WORKBENCH_LOCK_PATH, {})
            existing_pid = safe_int(existing.get("pid"))
            if existing_pid is not None and pid_matches_command(existing_pid, ["fly_entrypoint.py"]) and existing_pid != os.getpid():
                raise RuntimeError(
                    f"workbench already running with pid={existing_pid} on http://127.0.0.1:{PORT}/. "
                    "Stop the existing launcher before starting another one."
                )
            if time.monotonic() < deadline:
                time.sleep(0.1)
                continue
            try:
                WORKBENCH_LOCK_PATH.unlink()
            except OSError:
                pass
            continue

        payload = json.dumps(
            {
                "pid": os.getpid(),
                "port": PORT,
                "started_at": utc_now(),
                "cwd": str(ROOT),
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
        WORKBENCH_LOCK_FD = fd
        return


def release_workbench_lock() -> None:
    global WORKBENCH_LOCK_FD
    if WORKBENCH_LOCK_FD is not None:
        try:
            os.close(WORKBENCH_LOCK_FD)
        finally:
            WORKBENCH_LOCK_FD = None
    existing = read_json(WORKBENCH_LOCK_PATH, {})
    existing_pid = safe_int(existing.get("pid"))
    if existing_pid == os.getpid() and WORKBENCH_LOCK_PATH.exists():
        WORKBENCH_LOCK_PATH.unlink(missing_ok=True)


def tail_text(path: Path, lines: int = 10) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()[-lines:]
    except OSError:
        return []


class ManagedProcess:
    def __init__(
        self,
        *,
        name: str,
        command: list[str],
        log_path: Path,
        cwd: Path,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        self.name = name
        self.command = command
        self.log_path = log_path
        self.cwd = cwd
        self.env_overrides = dict(env_overrides or {})
        self._proc: subprocess.Popen[str] | None = None
        self._log_handle = None
        self._lock = threading.RLock()
        self._last_pid: int | None = None
        self._last_returncode: int | None = None

    def _close_log_handle(self) -> None:
        if self._log_handle is None:
            return
        self._log_handle.flush()
        self._log_handle.close()
        self._log_handle = None

    def _reap_finished_process(self) -> None:
        if self._proc is None or self._proc.poll() is None:
            return
        self._last_pid = self._proc.pid
        self._last_returncode = self._proc.poll()
        self._proc = None
        self._close_log_handle()

    def _terminate_process_tree(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        terminate_pid_tree(proc.pid)
        try:
            proc.wait(timeout=0.1)
        except subprocess.TimeoutExpired:
            pass

    def is_running(self) -> bool:
        with self._lock:
            self._reap_finished_process()
            return self._proc is not None and self._proc.poll() is None

    def start(self) -> dict[str, Any]:
        with self._lock:
            self._reap_finished_process()
            if self.is_running():
                return self.snapshot()
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self._close_log_handle()
            self._log_handle = self.log_path.open("w", encoding="utf-8")
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env.update(self.env_overrides)
            popen_kwargs: dict[str, Any] = {
                "cwd": str(self.cwd),
                "stdout": self._log_handle,
                "stderr": subprocess.STDOUT,
                "text": True,
                "env": env,
            }
            if os.name == "nt":
                popen_kwargs["creationflags"] = creationflags
            else:
                popen_kwargs["start_new_session"] = True
            self._proc = subprocess.Popen(self.command, **popen_kwargs)
            self._last_pid = self._proc.pid
            self._last_returncode = None
            return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            self._reap_finished_process()
            if self._proc is None:
                self._close_log_handle()
                return self.snapshot()
            proc = self._proc
            self._terminate_process_tree(proc)
            self._last_pid = proc.pid
            self._last_returncode = proc.poll()
            self._proc = None
            self._close_log_handle()
            return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            self._reap_finished_process()
            pid = self._proc.pid if self._proc is not None else self._last_pid
            returncode = self._proc.poll() if self._proc is not None else self._last_returncode
            return {
                "name": self.name,
                "pid": pid,
                "running": self._proc is not None and returncode is None,
                "returncode": returncode,
                "command": self.command,
                "log_path": str(self.log_path),
                "log_tail": tail_text(self.log_path, lines=8),
            }


class WorkbenchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class WorkbenchSupervisor:
    def __init__(self) -> None:
        self.root = WORKBENCH_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.experiment_control_path = self.root / "experiments-control.json"
        self.experiment_status_path = self.root / "experiments-status.json"
        self.experiment_events_path = self.root / "experiments-events.jsonl"
        self._lock = threading.RLock()

        # Keep docs/fly-runtime-manifest.json in sync with any new repo-local scripts
        # or ROOT-relative runtime files added here so Fly image inputs stay explicit.
        paper_command = [
            UV_COMMAND,
            "run",
            "python",
            str(ROOT / "run_jupiter_live.py"),
            "--execution-mode",
            "paper",
            "--symbols",
            *WORKBENCH_SYMBOLS,
            "--poll-seconds",
            str(WORKBENCH_POLL_SECONDS),
            "--bar-seconds",
            str(WORKBENCH_BAR_SECONDS),
            "--state",
            str(STATE_PATH),
        ]
        if RESET_STATE:
            paper_command.append("--reset-state")
        if WORKBENCH_PAPER_WARMUP_SPLIT:
            paper_command.extend(
                [
                    "--paper-warmup-split",
                    WORKBENCH_PAPER_WARMUP_SPLIT,
                    "--paper-warmup-bars",
                    str(WORKBENCH_PAPER_WARMUP_BARS),
                ]
            )
        manager_command = [
            UV_COMMAND,
            "run",
            "python",
            str(ROOT / "experiment_manager.py"),
            "--control",
            str(self.experiment_control_path),
            "--status",
            str(self.experiment_status_path),
            "--events",
            str(self.experiment_events_path),
            "--manifest",
            str(WORKBENCH_EXPERIMENT_MANIFEST),
            "--cycle-delay-seconds",
            str(WORKBENCH_EXPERIMENT_DELAY),
        ]
        paper_env = {}
        if WORKBENCH_PAPER_PROFILE:
            paper_env["AUTOTRADER_EXPERIMENT_PROFILE"] = WORKBENCH_PAPER_PROFILE

        self.paper = ManagedProcess(
            name="paper-feed",
            command=paper_command,
            log_path=self.root / "paper-feed.log",
            cwd=ROOT,
            env_overrides=paper_env,
        )
        self.experiment_manager = ManagedProcess(
            name="experiment-manager",
            command=manager_command,
            log_path=self.root / "experiment-manager.log",
            cwd=ROOT,
        )

    def _experiment_status(self) -> dict[str, Any]:
        return read_json(
            self.experiment_status_path,
            {
                "state": "stopped",
                "summary": {
                    "experiment_count": 0,
                    "active_count": 0,
                    "paused_count": 0,
                    "failed_count": 0,
                    "degraded_count": 0,
                    "drift_count": 0,
                    "leader_id": None,
                    "leader_score": None,
                    "phase_counts": {},
                    "decision_counts": {},
                },
                "experiments": [],
            },
        )

    def _update_control(
        self,
        *,
        manager_state: str | None = None,
        experiment_id: str | None = None,
        experiment_state: str | None = None,
        restart: bool = False,
    ) -> None:
        current = read_json(
            self.experiment_control_path,
            {"manager": {"desired_state": "running"}, "experiments": {}},
        )
        manager = current.setdefault("manager", {"desired_state": "running"})
        experiments = current.setdefault("experiments", {})
        if manager_state is not None:
            manager["desired_state"] = manager_state
        if experiment_id is not None:
            experiment = experiments.setdefault(experiment_id, {"desired_state": "running", "restart_nonce": 0})
            if experiment_state is not None:
                experiment["desired_state"] = experiment_state
            if restart:
                experiment["restart_nonce"] = int(experiment.get("restart_nonce", 0)) + 1
        write_json(self.experiment_control_path, current)

    def _status_manager_pid(self) -> int | None:
        manager_pid = safe_int(self._experiment_status().get("pid"))
        if manager_pid is None or not pid_matches_command(manager_pid, ["experiment_manager.py", str(self.experiment_status_path)]):
            return None
        return manager_pid

    def _ensure_manager_process(self) -> None:
        tracked_pid = safe_int(self.experiment_manager.snapshot().get("pid"))
        manager_pid = self._status_manager_pid()
        if manager_pid is not None and manager_pid != tracked_pid:
            return
        self.experiment_manager.start()

    def _stop_manager_process(self) -> None:
        tracked_pid = safe_int(self.experiment_manager.snapshot().get("pid"))
        self.experiment_manager.stop()
        manager_pid = self._status_manager_pid()
        if manager_pid is not None and manager_pid != tracked_pid:
            terminate_pid_tree(manager_pid)

    def start_all(self) -> None:
        with self._lock:
            self.paper.start()
            self._update_control(manager_state="running")
            self._ensure_manager_process()

    def status(self) -> dict[str, Any]:
        with self._lock:
            manager_state = self._experiment_status()
            experiments = manager_state.get("experiments", [])
            summary = dict(manager_state.get("summary", {}))
            leader = next((item for item in experiments if item.get("id") == summary.get("leader_id")), None)
            manager_snapshot = self.experiment_manager.snapshot()
            manager_running = bool(manager_snapshot.get("running"))
            manager_pid = self._status_manager_pid()
            if manager_pid is not None:
                manager_running = True
                manager_snapshot["pid"] = manager_pid
                manager_snapshot["running"] = manager_running
                manager_snapshot["returncode"] = None if manager_running else manager_snapshot.get("returncode")
            manager_state_name = manager_state.get("state", "stopped")
            if not manager_running:
                manager_state_name = "stopped"
                summary["manager_state"] = "stopped"
            trainer_alias = {
                **manager_snapshot,
                "state": manager_state_name,
                "desired_state": summary.get("manager_state", "running"),
                "iteration": summary.get("experiment_count", 0),
                "mode": "message-bus",
                "last_completed_at": leader.get("last_completed_at") if leader else None,
                "last_metrics": leader.get("best_metrics", {}) if leader else {},
                "control_path": str(self.experiment_control_path),
                "status_path": str(self.experiment_status_path),
                "events_path": str(self.experiment_events_path),
            }
            return {
                "dashboard": {
                    "pid": os.getpid(),
                    "running": True,
                    "url": f"http://127.0.0.1:{PORT}/",
                },
                "paper": self.paper.snapshot(),
                "paper_profile": WORKBENCH_PAPER_PROFILE or "default",
                "paper_warmup_split": WORKBENCH_PAPER_WARMUP_SPLIT or None,
                "experiment_manager": {
                    **manager_snapshot,
                    "state": manager_state_name,
                    "summary": summary,
                    "control_path": str(self.experiment_control_path),
                    "status_path": str(self.experiment_status_path),
                    "events_path": str(self.experiment_events_path),
                },
                "trainer": trainer_alias,
                "experiments": experiments,
            }

    def control(self, *, target: str, action: str, experiment_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            if target == "paper":
                if action == "start":
                    self.paper.start()
                elif action == "stop":
                    self.paper.stop()
                elif action == "restart":
                    self.paper.stop()
                    self.paper.start()
                else:
                    raise ValueError(f"unsupported paper action: {action}")
            elif target in {"experiment-manager", "trainer"}:
                if action == "start":
                    self._update_control(manager_state="running")
                    self._ensure_manager_process()
                elif action == "pause":
                    self._update_control(manager_state="paused")
                elif action == "resume":
                    self._update_control(manager_state="running")
                    self._ensure_manager_process()
                elif action == "stop":
                    self._update_control(manager_state="stopped")
                    self._stop_manager_process()
                elif action == "restart":
                    self._update_control(manager_state="running")
                    self._stop_manager_process()
                    self._ensure_manager_process()
                else:
                    raise ValueError(f"unsupported experiment-manager action: {action}")
            elif target == "experiment":
                if not experiment_id:
                    raise ValueError("experiment_id is required for target=experiment")
                if action == "start":
                    self._update_control(manager_state="running", experiment_id=experiment_id, experiment_state="running")
                    self._ensure_manager_process()
                elif action == "pause":
                    self._update_control(experiment_id=experiment_id, experiment_state="paused")
                elif action == "resume":
                    self._update_control(manager_state="running", experiment_id=experiment_id, experiment_state="running")
                    self._ensure_manager_process()
                elif action == "stop":
                    self._update_control(experiment_id=experiment_id, experiment_state="stopped")
                elif action == "restart":
                    self._update_control(manager_state="running", experiment_id=experiment_id, experiment_state="running", restart=True)
                    self._ensure_manager_process()
                else:
                    raise ValueError(f"unsupported experiment action: {action}")
            else:
                raise ValueError(f"unsupported target: {target}")
            return self.status()


WORKBENCH = WorkbenchSupervisor()


def dashboard_payload() -> dict[str, Any]:
    refresh_engine_from_state()
    with ENGINE_LOCK:
        portfolio = ENGINE.snapshot_portfolio()
        positions = [
            {
                "symbol": symbol,
                "notional": notional,
                "entry_price": ENGINE.entry_prices.get(symbol),
                "direction": "Long" if notional > 0 else ("Short" if notional < 0 else "Flat"),
            }
            for symbol, notional in sorted(ENGINE.positions.items())
        ]
        paper = {
            "portfolio": to_jsonable(portfolio),
            "engine": {
                "cash": ENGINE.cash,
                "positions": ENGINE.positions,
                "entry_prices": ENGINE.entry_prices,
                "equity": ENGINE.equity,
                "timestamp": ENGINE.timestamp,
            },
            "positions": positions,
        }
    trading = trading_summary(read_tsv(RESULTS_PATH))
    manager_status = WORKBENCH.status()
    experiments = manager_status.get("experiments", [])
    experiment_summary = manager_status.get("experiment_manager", {}).get("summary", {})
    leader = next((item for item in experiments if item.get("id") == experiment_summary.get("leader_id")), None)
    research = {
        "summary": {
            "total_runs": experiment_summary.get("experiment_count", 0),
            "best_val_bpb": leader.get("best_score") if leader else None,
            "best_commit": experiment_summary.get("leader_id"),
        },
        "status_counts": {
            "keep": experiment_summary.get("active_count", 0),
            "discard": experiment_summary.get("paused_count", 0),
            "crash": experiment_summary.get("failed_count", 0),
        },
    }
    experiment_events = recent_manager_events(WORKBENCH.experiment_events_path)
    equity = read_curve(EQUITY_PATH)
    baseline = read_curve(BASELINE_PATH)
    actions = [
        {
            "title": "Review the current leader",
            "detail": "Use the experiment leaderboard to see which thread is producing the best paper score before you touch strategy.py.",
        },
        {
            "title": "Pause one thread, not the world",
            "detail": "Experiment controls are isolated. Pause or restart a single hypothesis without disrupting the other nine threads.",
        },
        {
            "title": "Watch the event stream",
            "detail": "The message-based manager emits append-only events for starts, completes, pauses, restarts, and degraded runs.",
        },
    ]
    return {
        "meta": {
            "generated_at": utc_now(),
            "strategy_spec": STRATEGY_SPEC,
            "paper_profile": WORKBENCH_PAPER_PROFILE or "default",
            "paper_warmup_split": WORKBENCH_PAPER_WARMUP_SPLIT or None,
            "state_path": str(STATE_PATH),
            "workbench_root": str(WORKBENCH.root),
            "experiment_manifest_path": str(WORKBENCH_EXPERIMENT_MANIFEST),
        },
        "paper": paper,
        "trading": trading,
        "research": research,
        "experiment_events": experiment_events,
        "experiments": experiments,
        "equity": equity,
        "baseline_equity": baseline,
        "actions": actions,
        "workbench": manager_status,
    }


DASHBOARD_HTML = WORKBENCH_TEMPLATE_PATH.read_text(encoding="utf-8") if WORKBENCH_TEMPLATE_PATH.exists() else "<h1>dashboard template missing</h1>"


class FlyPaperHandler(BaseHTTPRequestHandler):
    server_version = "AutoResearchTrading/3.0"

    def do_GET(self) -> None:  # noqa: N802
        route = urlparse(self.path).path
        if route == "/healthz":
            self._send_json(HTTPStatus.OK, self._health_payload())
            return
        if route == "/login":
            self._handle_login_page()
            return
        if route == "/logout":
            self._handle_logout()
            return
        if not self._ensure_authenticated():
            return
        if route == "/":
            if self._prefers_html():
                self._send_bytes(HTTPStatus.OK, DASHBOARD_HTML.encode("utf-8"), "text/html; charset=utf-8")
            else:
                self._send_json(HTTPStatus.OK, self._health_payload())
            return
        if route in {"/state", "/api/state"}:
            self._send_json(HTTPStatus.OK, self._state_payload())
            return
        if route == "/api/dashboard":
            self._send_json(HTTPStatus.OK, dashboard_payload())
            return
        if route == "/api/workbench/status":
            self._send_json(HTTPStatus.OK, WORKBENCH.status())
            return
        if route in {"/assets/logo.png", "/favicon.ico"} and LOGO_PATH.exists():
            self._send_bytes(HTTPStatus.OK, LOGO_PATH.read_bytes(), "image/png")
            return
        if route == "/artifacts/dashboard-generative-ui.html" and GENERATIVE_ARTIFACT_PATH.exists():
            self._send_bytes(
                HTTPStatus.OK,
                GENERATIVE_ARTIFACT_PATH.read_bytes(),
                "text/html; charset=utf-8",
            )
            return
        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/login":
            self._handle_login_submit()
            return
        if not self._ensure_authenticated():
            return
        if self.path == "/step":
            try:
                payload = self._read_json()
                snapshot = payload.get("bars", payload)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            try:
                with ENGINE_LOCK:
                    result = ENGINE.step(snapshot)
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "timestamp": result.timestamp,
                    "equity": result.equity,
                    "signals": to_jsonable(result.signals),
                    "fills": to_jsonable(result.fills),
                    "portfolio": to_jsonable(result.portfolio),
                },
            )
            return

        if self.path == "/api/workbench/control":
            try:
                payload = self._read_json()
                target = str(payload.get("target", "")).strip().lower()
                action = str(payload.get("action", "")).strip().lower()
                experiment_id = payload.get("experiment_id")
                if not target or not action:
                    raise ValueError("target and action are required")
                state = WORKBENCH.control(target=target, action=action, experiment_id=experiment_id)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                return
            self._send_json(HTTPStatus.OK, {"ok": True, "workbench": state})
            return

        if self.path == "/api/postmortem":
            try:
                payload = self._read_json()
                markdown = str(payload.get("markdown", "")).strip()
                if not markdown:
                    raise ValueError("markdown is required")
                duplicate = last_markdown_entry(TRADE_POSTMORTEMS_PATH) == markdown
                if not duplicate:
                    append_markdown_entry(TRADE_POSTMORTEMS_PATH, markdown)
            except ValueError as exc:
                self._send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            except Exception as exc:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": str(exc)})
                return
            self._send_json(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "path": str(TRADE_POSTMORTEMS_PATH),
                    "saved_at": utc_now(),
                    "duplicate": duplicate,
                },
            )
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _prefers_html(self) -> bool:
        accept = self.headers.get("Accept", "")
        return "text/html" in accept or accept in {"", "*/*"}

    def _request_is_secure(self) -> bool:
        forwarded_proto = self.headers.get("X-Forwarded-Proto", "")
        return forwarded_proto.lower() == "https"

    def _current_user(self) -> dict[str, Any] | None:
        return AUTH.current_user(self.headers.get("Cookie"))

    def _ensure_authenticated(self) -> bool:
        if not AUTH.enabled:
            return True
        if self._current_user() is not None:
            return True
        expects_json = self.path.startswith("/api/") or self.path in {"/state", "/step"}
        if not expects_json and self._prefers_html():
            next_path = AUTH.redirect_location(self.path)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", f"/login?next={next_path}")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return False
        self._send_json(
            HTTPStatus.UNAUTHORIZED,
            {"error": "authentication_required"},
            extra_headers={"WWW-Authenticate": f'Form realm="{AUTH.config.realm}"'},
        )
        return False

    def _handle_login_page(self) -> None:
        if not AUTH.enabled:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return
        if self._current_user() is not None:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return
        next_values = WorkbenchAuth.parse_form_body(urlparse(self.path).query.encode("utf-8"))
        next_path = AUTH.sanitize_next_path(next_values.get("next"))
        html_body = AUTH.login_html(next_path=next_path)
        self._send_bytes(HTTPStatus.OK, html_body.encode("utf-8"), "text/html; charset=utf-8")

    def _handle_login_submit(self) -> None:
        if not AUTH.enabled:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        body = self.rfile.read(max(0, min(content_length, 4096))) if content_length > 0 else b""
        form = WorkbenchAuth.parse_form_body(body)
        username = form.get("username", "")
        password = form.get("password", "")
        next_path = AUTH.sanitize_next_path(form.get("next"))
        if AUTH.authenticate_credentials(username, password):
            session_cookie = AUTH.build_session_cookie(username, secure=self._request_is_secure())
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", next_path)
            self.send_header("Set-Cookie", session_cookie)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        html_body = AUTH.login_html(next_path=next_path, error_message="Invalid username or password.")
        self._send_bytes(HTTPStatus.UNAUTHORIZED, html_body.encode("utf-8"), "text/html; charset=utf-8")

    def _handle_logout(self) -> None:
        if not AUTH.enabled:
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/login")
        self.send_header("Set-Cookie", AUTH.clear_session_cookie(secure=self._request_is_secure()))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _health_payload(self) -> dict[str, Any]:
        with ENGINE_LOCK:
            portfolio = ENGINE.snapshot_portfolio()
            return {"status": "ok", "timestamp": portfolio.timestamp, "equity": portfolio.equity}

    def _state_payload(self) -> dict[str, Any]:
        with ENGINE_LOCK:
            return {
                "portfolio": to_jsonable(ENGINE.snapshot_portfolio()),
                "engine": {
                    "cash": ENGINE.cash,
                    "positions": ENGINE.positions,
                    "entry_prices": ENGINE.entry_prices,
                    "equity": ENGINE.equity,
                    "timestamp": ENGINE.timestamp,
                },
            }

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        if content_length > 1_000_000:
            raise ValueError("request body too large")
        raw = self.rfile.read(content_length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid JSON body") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._send_bytes(
            status,
            json.dumps(_jsonable(payload), sort_keys=True).encode("utf-8"),
            "application/json",
            extra_headers=extra_headers,
        )

    def _send_bytes(
        self,
        status: HTTPStatus,
        body: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for header_name, header_value in (extra_headers or {}).items():
            self.send_header(header_name, header_value)
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    server: WorkbenchHTTPServer | None = None
    try:
        acquire_workbench_lock()
        server = WorkbenchHTTPServer((HOST, PORT), FlyPaperHandler)
        if WORKBENCH_AUTOSTART:
            WORKBENCH.start_all()

        print(f"listening on {HOST}:{PORT}", flush=True)
        server.serve_forever()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"failed to start workbench on {HOST}:{PORT}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if server is not None:
            server.server_close()
        WORKBENCH.control(target="paper", action="stop")
        WORKBENCH.control(target="experiment-manager", action="stop")
        release_workbench_lock()


if __name__ == "__main__":
    raise SystemExit(main())
