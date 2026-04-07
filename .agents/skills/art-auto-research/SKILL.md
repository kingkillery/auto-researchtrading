---
name: "ART - Auto Research"
description: "Expert operator for the Auto-Research-Trading repo. Use when working in this project and needing to choose, run, or explain the correct repo tool or workflow: data prep, hourly backtests, 5-minute replay/backtests, benchmark runs, equity and milestone exports, chart generation, paper trading, workbench control, or Jupiter execution modes. Trigger on requests like 'run the backtest', 'prepare data', 'use ART', 'generate charts', 'paper trade this', 'check Jupiter live', 'which script should I use', or any request to use the tools in this repo safely."
---

# ART - Auto Research

Read `docs/agent-harness.md` before doing repo work. Treat it as the primary operating contract for this repository.

## Follow these repo rules

- Use `uv` for every Python entrypoint.
- Treat `strategy.py` as the main experiment surface.
- Treat `prepare.py`, `backtest.py`, and `benchmarks/` as fixed harness code unless the user explicitly overrides that rule.
- Preserve unrelated user changes. Do not revert work you did not make.
- Do not assume there is a resident deployment or paper-trading daemon. The default surface is offline research plus report generation.

## Route the task to the correct surface

- For repo command selection, workflow routing, and artifact expectations, read `references/repo-tooling.md`.
- For standard strategy validation, use the hourly harness: `uv run backtest.py`.
- For benchmark comparison, use `uv run run_benchmarks.py`.
- For 5-minute validation, read `docs/backtest-5m.md` and use `uv run python backtest_5m.py ...`.
- For live Jupiter work, read `docs/jupiter-execution.md` before touching any live flags.
- For SOL baseline strategy edits, read `docs/sol-baseline-strategy-v1.md` before editing `strategy.py`.
- For workbench CLI control, remember `workbench_ctl.py` is an HTTP client for the local dashboard server. If it returns connection-refused on `127.0.0.1:8080`, start or restore `uv run python fly_entrypoint.py` before retrying control commands.
- If the workbench launcher dies but paper/trainer workers remain, treat that as a stale-runtime condition. Re-establish a single clean launcher before trusting any control or dashboard state.
- For UI redesign work, preserve the current shared operator contract before splitting implementation lanes:
  - primary read model: `/api/dashboard`
  - primary control surface: `/api/workbench/control`
  - current workbench remains the source of truth even if a generative or terminal layer is added on top.
- The repo now has planning artifacts for dual operator surfaces:
  - `CODEBASE_KNOWLEDGE_GRAPH.json`
  - `AUTO_RESEARCH_UI_REDESIGN_SPEC.md`
  - `AUTO_RESEARCH_TUI_SPEC.md`
- Future Jupiter capability work should preserve separate capability classes for:
  - `perps`
  - `swaps`
  - `lending`
  - `multiply`

## Use this operating sequence

1. Classify the task as one of: data prep, hourly backtest, 5-minute replay/backtest, benchmarking, reporting/export, paper execution, workbench control, or Jupiter live execution.
2. Read the matching repo doc if the task has a dedicated doc.
3. Run the narrowest command that satisfies the request.
4. Verify the expected artifact or output path exists when the command claims to generate one.
5. If you changed docs, confirm all referenced commands and paths exist in the repo.
6. If you changed strategy behavior, run the required validation command and summarize the score or failure mode.

## Guardrails by surface

- Prefer the hourly harness for official strategy validation unless the user explicitly asks for 5-minute work.
- Keep paper mode, replay mode, and live Jupiter mode distinct in explanations. They are different operator surfaces.
- Treat Jupiter live execution as operator-invoked and guarded. Do not blur paper and live paths.
- Treat `workbench_ctl.py` as a control client, not a launcher. It depends on a running `fly_entrypoint.py` server.
- On this Windows host, `uv run backtest.py` is still the official hourly validation surface. The fixed harness now falls back to a timer when `signal.SIGALRM` is unavailable, so do not route away from the hourly harness just because the host is Windows.

## Response expectations

- Tell the user which repo surface you chose and why.
- Use exact repo commands, not approximate paraphrases.
- Name the expected artifacts when a command writes files.
- Call out when a step depends on host setup outside the repo, especially the Jupiter CLI and wallet configuration.

