from __future__ import annotations

import argparse
import json
from urllib import error, request


def fetch_json(url: str, method: str = "GET", payload: dict | None = None) -> dict:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=body, headers=headers, method=method)
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def action_target(action: str) -> tuple[str, str]:
    mapping = {
        "start-paper": ("start", "paper"),
        "stop-paper": ("stop", "paper"),
        "restart-paper": ("restart", "paper"),
        "start-manager": ("start", "experiment-manager"),
        "restart-manager": ("restart", "experiment-manager"),
        "stop-manager": ("stop", "experiment-manager"),
        "start-experiment": ("start", "experiment"),
        "pause-experiment": ("pause", "experiment"),
        "resume-experiment": ("resume", "experiment"),
        "restart-experiment": ("restart", "experiment"),
        "stop-experiment": ("stop", "experiment"),
    }
    if action not in mapping:
        raise KeyError(action)
    return mapping[action]


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI control surface for the local workbench UI")
    parser.add_argument("action", choices=[
        "status",
        "start-paper",
        "stop-paper",
        "restart-paper",
        "start-manager",
        "restart-manager",
        "stop-manager",
        "list-experiments",
        "start-experiment",
        "pause-experiment",
        "resume-experiment",
        "restart-experiment",
        "stop-experiment",
    ])
    parser.add_argument("experiment_id_arg", nargs="?", default=None, help="Experiment id for experiment-scoped actions")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="Workbench base URL")
    parser.add_argument("--experiment-id", default=None, help="Experiment id for experiment-scoped actions")
    args = parser.parse_args()
    experiment_id = args.experiment_id_arg or args.experiment_id

    try:
        if args.action == "status":
            payload = fetch_json(f"{args.base_url}/api/workbench/status")
        elif args.action == "list-experiments":
            payload = fetch_json(f"{args.base_url}/api/workbench/status")
            experiments = payload.get("experiments", [])
            print(json.dumps({
                "dashboard_url": payload.get("dashboard", {}).get("url"),
                "experiment_count": len(experiments),
                "experiments": [
                    {
                        "id": item.get("id"),
                        "state": item.get("state"),
                        "phase": item.get("phase"),
                        "desired_state": item.get("desired_state"),
                        "candidate_score": (item.get("last_metrics") or {}).get("score"),
                        "accepted_best_score": item.get("best_score"),
                        "decision": (item.get("last_decision") or {}).get("status"),
                        "last_completed_at": item.get("last_completed_at"),
                        "degraded": item.get("degraded"),
                    }
                    for item in experiments
                ],
            }, indent=2, sort_keys=True))
            return 0
        else:
            verb, target = action_target(args.action)
            control_payload = {"target": target, "action": verb}
            if target == "experiment":
                if not experiment_id:
                    print(json.dumps({"ok": False, "error": "experiment id is required for experiment actions"}))
                    return 1
                control_payload["experiment_id"] = experiment_id
            payload = fetch_json(f"{args.base_url}/api/workbench/control", method="POST", payload=control_payload)
    except error.URLError as exc:
        print(json.dumps({"ok": False, "error": str(exc.reason)}))
        return 1

    if args.action == "status":
        dashboard = payload.get("dashboard", {})
        paper = payload.get("paper", {})
        manager = payload.get("experiment_manager", {})
        experiments = payload.get("experiments", [])
        summary = {
            "dashboard_url": dashboard.get("url"),
            "paper": {
                "running": paper.get("running"),
                "pid": paper.get("pid"),
                "returncode": paper.get("returncode"),
            },
            "experiment_manager": {
                "state": manager.get("state"),
                "pid": manager.get("pid"),
                "active_count": (manager.get("summary") or {}).get("active_count"),
                "leader_id": (manager.get("summary") or {}).get("leader_id"),
                "leader_score": (manager.get("summary") or {}).get("leader_score"),
            },
            "experiments": {
                "count": len(experiments),
                "running": sum(1 for item in experiments if item.get("state") == "running"),
                "paused": sum(1 for item in experiments if item.get("state") == "paused"),
                "failed": sum(1 for item in experiments if item.get("last_error")),
            },
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        print()

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
