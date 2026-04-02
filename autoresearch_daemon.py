from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBENCH_ROOT = Path.home() / ".cache" / "autotrader" / "workbench"
DEFAULT_CONTROL_PATH = DEFAULT_WORKBENCH_ROOT / "trainer-control.json"
DEFAULT_STATUS_PATH = DEFAULT_WORKBENCH_ROOT / "trainer-status.json"


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


def default_trainer_command(symbols: list[str], split: str) -> list[str]:
    return [sys.executable, str(ROOT / "backtest_5m.py"), "--split", split, "--symbols", *symbols]


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed autoresearch worker for the local workbench")
    parser.add_argument("--control", default=str(DEFAULT_CONTROL_PATH), help="Path to the trainer control JSON file")
    parser.add_argument("--status", default=str(DEFAULT_STATUS_PATH), help="Path to the trainer status JSON file")
    parser.add_argument("--split", default="val", choices=["train", "val", "test"], help="Replay split for the default validation loop")
    parser.add_argument("--symbols", nargs="+", default=["SOL"], help="Symbols for the default validation loop")
    parser.add_argument("--cycle-delay-seconds", type=float, default=5.0, help="Delay between cycles when the worker is running")
    parser.add_argument("--poll-seconds", type=float, default=1.0, help="How often to re-check the control file")
    parser.add_argument("--trainer-command", default=None, help="Optional shell command to run each cycle instead of the default backtest_5m validation loop")
    args = parser.parse_args()

    control_path = Path(args.control).expanduser()
    status_path = Path(args.status).expanduser()
    command = args.trainer_command or " ".join(default_trainer_command(args.symbols, args.split))

    write_json(control_path, {"desired_state": read_json(control_path, {"desired_state": "running"}).get("desired_state", "running")})
    status: dict[str, Any] = {
        "state": "starting",
        "pid": os.getpid(),
        "iteration": 0,
        "mode": "external-command" if args.trainer_command else "validation-loop",
        "symbols": args.symbols,
        "split": args.split,
        "trainer_command": command,
        "last_started_at": None,
        "last_completed_at": None,
        "last_exit_code": None,
        "last_error": None,
        "last_metrics": {},
        "desired_state": "running",
    }
    write_json(status_path, status)

    while True:
        control = read_json(control_path, {"desired_state": "running"})
        desired_state = str(control.get("desired_state", "running")).lower()
        status["desired_state"] = desired_state

        if desired_state == "stopped":
            status["state"] = "stopped"
            status["last_completed_at"] = utc_now()
            write_json(status_path, status)
            return 0

        if desired_state == "paused":
            status["state"] = "paused"
            write_json(status_path, status)
            time.sleep(max(args.poll_seconds, 0.25))
            continue

        status["state"] = "running"
        status["iteration"] += 1
        status["last_started_at"] = utc_now()
        status["last_error"] = None
        status["last_exit_code"] = None
        status["last_stdout_tail"] = ""
        status["last_stderr_tail"] = ""
        write_json(status_path, status)

        process = subprocess.Popen(
            command if args.trainer_command else default_trainer_command(args.symbols, args.split),
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=bool(args.trainer_command),
        )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []
        interrupted_by_control: str | None = None
        while True:
            if process.poll() is not None:
                break
            control = read_json(control_path, {"desired_state": "running"})
            desired_state = str(control.get("desired_state", "running")).lower()
            status["desired_state"] = desired_state
            if desired_state in {"paused", "stopped"}:
                interrupted_by_control = desired_state
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                break
            time.sleep(max(args.poll_seconds, 0.25))

        stdout_text, stderr_text = process.communicate()
        if stdout_text:
            stdout_chunks.append(stdout_text)
        if stderr_text:
            stderr_chunks.append(stderr_text)

        status["last_exit_code"] = 0 if interrupted_by_control else process.returncode
        status["last_completed_at"] = utc_now()
        status["last_metrics"] = parse_metrics("".join(stdout_chunks))
        status["last_stdout_tail"] = "\n".join("".join(stdout_chunks).splitlines()[-20:])
        status["last_stderr_tail"] = "\n".join("".join(stderr_chunks).splitlines()[-20:])
        if interrupted_by_control:
            status["last_error"] = None
        elif process.returncode not in {0, None}:
            status["last_error"] = status["last_stderr_tail"] or f"trainer exited with code {process.returncode}"
        write_json(status_path, status)

        control = read_json(control_path, {"desired_state": "running"})
        desired_state = str(control.get("desired_state", "running")).lower()
        if desired_state == "stopped":
            status["state"] = "stopped"
            write_json(status_path, status)
            return 0
        if desired_state == "paused":
            status["state"] = "paused"
            write_json(status_path, status)
            continue

        time.sleep(max(args.cycle_delay_seconds, 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
