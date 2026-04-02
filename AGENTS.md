# Agent Harness

Scope for agent work in this repo:

- Keep changes limited to `AGENTS.md` and `docs/` unless the user explicitly asks for code or runtime edits.
- Treat `prepare.py`, `backtest.py`, and `benchmarks/` as fixed harness/runtime code.
- Read [docs/agent-harness.md](docs/agent-harness.md) before doing repo work.

Operational rules:

- Use `uv` for all Python entrypoints.
- Do not assume a live deployment or paper-trading daemon exists in this repo; the current execution surface is offline backtesting plus report generation.
- Preserve others' edits. Do not revert unrelated work.
- When working on the SOL baseline, read `docs/sol-baseline-strategy-v1.md` before editing `strategy.py`.

Codebase map references:

- `.planning/codebase/STACK.md` - Quick summary of the repo's language, dependencies, entrypoints, and artifact formats.
- `.planning/codebase/ARCHITECTURE.md` - High-level description of the research harness, workbench, and live/paper execution flow.
- `.planning/codebase/STRUCTURE.md` - Directory and module map covering the main runtime, reporting, benchmark, and docs surfaces.
- `.planning/codebase/CONVENTIONS.md` - Working rules for entrypoints, style, data contracts, validation, and documentation.
- `.planning/codebase/INTEGRATIONS.md` - External services, local HTTP surfaces, and filesystem integration points used by the repo.
- `.planning/codebase/CONCERNS.md` - Known risks, technical debt, portability issues, and recently corrected runtime failures.

Validation expectation:

- For docs-only changes, verify paths and commands are accurate.
- For any future strategy work, run `uv run backtest.py` and, when relevant, `uv run run_benchmarks.py`.
