# Concerns

## Validation and portability risks

- `backtest.py` uses `signal.SIGALRM`, which is Unix-oriented and fragile on Windows hosts
- The repo has multiple validation surfaces (`backtest.py`, `backtest_5m.py`, `paper_trade.py`, workbench trainer loop), so operators can accidentally compare unlike-for-like outputs
- There is no formal automated test suite, so regressions are caught mainly through manual CLI runs and runtime observation

## Runtime reliability risks

- The local workbench depends on a single launcher process in `fly_entrypoint.py`; `workbench_ctl.py` cannot recover anything if the dashboard is down
- Windows process trees around the workbench can be confusing because parent and child Python command lines look similar during supervision
- Root-level log and artifact files can preserve stale evidence if not reset between sessions

## Recently corrected issue

- The trainer-status failure on Windows came from concurrent writes to a fixed temp path: `trainer-status.json.tmp`
- `fly_entrypoint.py` and `autoresearch_daemon.py` were updated to use unique temp files plus `os.replace` retries, which has already been verified against the running workbench
- `ManagedProcess.start()` in `fly_entrypoint.py` now truncates managed logs on fresh starts, reducing stale-error confusion in the dashboard

## Architectural debt

- Most entrypoints and helper modules live at repo root, which makes local operation easy but weakens separation between source, runtime state, and generated artifacts
- There is no package boundary separating fixed harness code, operator tools, and integration experiments
- The external-wallet path is intentionally partial; signing and submission are still outside the repo’s completed execution contract

## Documentation and operator risk

- The repo contains both offline-harness rules and active local workbench/live-path docs, so contributors need to check current docs before assuming which surface is canonical for a task
- Workbench, paper, trainer, and live execution share related terminology but have distinct safety and trust boundaries
