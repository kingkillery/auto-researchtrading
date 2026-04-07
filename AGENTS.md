# Agent Harness

Scope for agent work in this repo:

- Keep changes limited to `AGENTS.md` and `docs/` unless the user explicitly asks for code or runtime edits.
- Treat `prepare.py`, `backtest.py`, and `benchmarks/` as fixed harness/runtime code.
- Read [docs/agent-harness.md](docs/agent-harness.md) before doing repo work.

Operational rules:

- Use `uv` for all Python entrypoints.
- Do not assume a live deployment or paper-trading daemon exists in this repo; the current execution surface is offline backtesting plus report generation.
- Preserve others' edits. Do not revert unrelated work.
- Re-evaluate what is directly in front of you before each substantive step, and think one step ahead so the next action is chosen deliberately rather than by habit.
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

## KADE / gstack integration

- Repo-local KADE surfaces live in `kade/AGENTS.md` and `kade/KADE.md`. Keep them aligned with this file when repo rules or workflows change.
- Treat `.agents/skills/g-kade/SKILL.md` as the local entrypoint for KADE-structured sessions, but do not let it override this repo's narrower file-scope and validation rules.
- In autonomous Codex sessions, prefer direct execution over interactive prompting. If `g-kade` instructions suggest AskUserQuestion-style checkpoints, convert them into explicit assumptions plus logged next steps unless the decision is destructive or materially branching.
- When using `g-kade` here, session outputs should still be compact and execution-oriented:
  - current branch
  - last meaningful action
  - current plan
  - completed evidence
  - single next action
- Record session handoffs in `kade/KADE.md` whenever a KADE-scoped work session changes repo docs, agent guidance, or audit state.

## Child Agent Memory Heartbeat

- Every spawned sub-agent in this repo must emit a concise `memory-heartbeat` in its final handoff to the leader.
- The heartbeat must include only stable items worth carrying forward:
  - fact learned
  - why it matters
  - file or surface it applies to
  - immediate follow-on implication
- Do not write directly into shared memory artifacts from every agent.
- Use one designated memory-scribe agent or lane to collect these heartbeats and record them into durable notes.
- For parallel campaigns, freeze the shared contract first, then let implementation lanes send heartbeats back to the memory-scribe lane.

## Design Context

### Users

The primary users are the repo owner and a very small group of power operators, roughly 1 to 4 people, using the workbench directly to understand research state, intervene on experiment threads, validate execution readiness, and inspect wallet or risk surfaces. The interface should assume high familiarity with the domain and should optimize for fast orientation, deliberate action, and low cognitive drag. Future external users are possible, but the current design should serve expert internal operators first.

### Brand Personality

Calm, analytical, exact. The interface should feel like a serious operator console for research and execution oversight, not a hype product and not a hacker toy. It should project confidence through clarity, state legibility, and disciplined restraint rather than spectacle. Emotional goals are composure, situational awareness, and trust in the control surface.

### Aesthetic Direction

Use a composed, high-signal command-room visual language that helps a regular user digest backend complexity without hiding important risk or verification details. Favor strong information hierarchy, clean rails, visible system state, and purposeful use of color. Dark mode is the current native fit for the workbench, but the visual direction should also be portable to a disciplined light mode in the future. Positive references are classic white-mode BitMEX and Bybit for density, market legibility, and operator efficiency. Anti-reference: anything hackery, flashy, neon, cyberpunk, casino-finance, or aggressively gamer-like.

### Design Principles

- The frontend must serve the backend's purpose. It exists to make the research harness, workbench control plane, and execution boundaries understandable and actionable for a human operator.
- Calm beats flashy. The UI should reduce stress, not create it, especially around execution, wallet, and postmortem flows.
- Show one action with one verification path. Every intervention should make the expected result and the next check obvious.
- Risk must be visually explicit. Paper, live, external-wallet, and future multiply or postmortem flows should never be visually interchangeable.
- Operator workflows come first. Dense, high-utility layouts are good when they improve speed and comprehension for expert users.
- Postmortem is part of the product, not an afterthought. Any trade or execution review flow should support a deliberate postmortem modal and make it easy to turn outcomes into reusable rules and guardrails.
