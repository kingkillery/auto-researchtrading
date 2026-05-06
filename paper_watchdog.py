"""Watchdog for paper trading engines — auto-restart on exit."""
import subprocess
import time
import sys
import signal
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT

def start_hourly():
    env = dict(os.environ)
    return subprocess.Popen(
        ["uv", "run", "python", str(ROOT / "run_jupiter_live.py"),
         "--execution-mode", "paper", "--symbols", "BTC", "ETH", "SOL",
         "--bar-seconds", "3600", "--poll-seconds", "60",
         "--paper-warmup-split", "val", "--paper-warmup-bars", "500",
         "--state", str(Path.home() / ".cache" / "autotrader" / "live" / "paper_hourly.json"),
         "--reset-state", "--no-save"],
        stdout=open(LOG_DIR / "paper_hourly.log", "a"),
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

def start_5m():
    env = dict(os.environ, AUTOTRADER_EXPERIMENT_PROFILE="compression_breakout")
    return subprocess.Popen(
        ["uv", "run", "python", str(ROOT / "run_jupiter_live.py"),
         "--execution-mode", "paper", "--symbols", "BTC", "ETH", "SOL",
         "--bar-seconds", "300", "--poll-seconds", "5",
         "--paper-warmup-split", "val", "--paper-warmup-bars", "500",
         "--state", str(Path.home() / ".cache" / "autotrader" / "live" / "paper_5m.json"),
         "--reset-state", "--no-save"],
        stdout=open(LOG_DIR / "paper_5m.log", "a"),
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
    )

def main():
    hourly = None
    fivem = None
    running = True

    def shutdown(signum, frame):
        nonlocal running
        running = False
        if hourly:
            hourly.terminate()
        if fivem:
            fivem.terminate()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("[watchdog] Starting paper engines...")

    while running:
        if hourly is None or hourly.poll() is not None:
            if hourly:
                print(f"[watchdog] Hourly died (code={hourly.poll()}), restarting...")
            else:
                print("[watchdog] Starting hourly...")
            hourly = start_hourly()

        if fivem is None or fivem.poll() is not None:
            if fivem:
                print(f"[watchdog] 5m died (code={fivem.poll()}), restarting...")
            else:
                print("[watchdog] Starting 5m...")
            fivem = start_5m()

        time.sleep(30)

    print("[watchdog] Shutting down...")
    if hourly:
        hourly.terminate()
        hourly.wait(timeout=10)
    if fivem:
        fivem.terminate()
        fivem.wait(timeout=10)

if __name__ == "__main__":
    main()
