# KADE.md - Project Manual & Handoff Log

## Project Overview
Backtest-first autonomous trading research for Hyperliquid perpetual futures. The intended loop is: edit `strategy.py`, run `uv run backtest.py`, keep only improvements, and use benchmarks when broader validation is needed.

## Handoff Log

2026-04-05T00:10:00-06:00 - Clarify Jupiter knowledge vs execution layers
Changed: Added explicit documentation that `jup-ag/agent-skills` is an agent-context layer while `@jup-ag/api` would be a separate execution-layer dependency, and tied that distinction into the Track 2 and Track 3 integration checklists.
Files: `docs/jupiter-execution.md`, `docs/integration-status-2026-04-01.md`, `kade/KADE.md`
Why: The next docs step was to prevent future scope drift where agent skill packages get mistaken for runtime integrations, especially around Jupiter CLI readiness and external-wallet handoff planning.
Verified: Re-read the updated docs and reviewed the resulting diff to confirm the repo still describes the CLI-backed `jup` path as the only current execution surface.
Next: If scope widens later, add a separate design note before introducing any JS or TS Jupiter client so the runtime contract changes explicitly rather than by implication.

2026-04-05T00:00:00-06:00 - Convert integration snapshot into execution checklists
Changed: Reframed the integration snapshot into concrete Track 1, Track 2, and Track 3 execution checklists, elevated the canonical 5-minute validation command into the harness doc, and froze the external-wallet JSONL request contract in the Jupiter operator doc.
Files: `docs/agent-harness.md`, `docs/integration-status-2026-04-01.md`, `docs/jupiter-execution.md`, `kade/KADE.md`
Why: The active repo plan called for replacing a coordination-only snapshot with legible, reproducible operator checklists so hourly validation, 5-minute validation, local-wallet readiness, and external-wallet handoff are documented as distinct execution surfaces.
Verified: Re-read the updated docs, checked the referenced commands and flags against `backtest_5m.py`, `run_jupiter_live.py`, and `jupiter_execution.py`, and reviewed the resulting git diff.
Next: If you want the Obsidian side kept in lockstep, point this session at the actual vault note path or note title so the same track checklists can be mirrored there.

2026-04-05T00:00:00+00:00 - Scribe Jupiter Perps MCP governance spec
Changed: Turned the approved governance architecture plan into a concrete spec for `diaorui/jupiter-perps-mcp`, covering tool trust levels, execution chains, policy rules, emergency reduce-only authority, paper-mode training, and post-trade verification.
Files: `docs/jupiter-perps-mcp-governance-spec.md`, `kade/KADE.md`
Why: The research objective is to uncover the rules and chains the MCP must obey so it can be used as a privileged trading actuator without collapsing planning, policy, and execution into one unsafe boundary.
Verified: Reviewed the target repo surface, wrote the full governance spec, and checked the resulting document in-repo.
Next: If needed, convert this governance spec into an implementation roadmap for the actual MCP repo, with file/module boundaries and policy storage design.

2026-04-04T01:30:00+00:00 - Run audit falsification pass 4 on SOL-only ablation
Changed: Ran a runtime SOL-only trading-scope ablation against the current strategy family and appended the comparison plus timeout caveat into the research audit.
Files: `docs/research-grade-audit.md`, `kade/KADE.md`
Why: After showing the edge survives holdout and is not just a few lucky days, the next question was whether the current repo-level edge really depends on trading BTC and ETH directly.
Verified: Measured validation and test outcomes for both the default multi-asset mode and a SOL-only trading-scope ablation, then checked processed-bar coverage to confirm timeout bias in the comparison.
Next: Write the deterministic-harness proposal so the next round of evidence can be compared at equal horizon coverage.

2026-04-04T01:00:00+00:00 - Run audit falsification pass 3 on outlier and regime concentration
Changed: Ran a timestamp-preserving read-only replay on the test split and appended processed-window concentration and BTC-led regime results into the research audit.
Files: `docs/research-grade-audit.md`, `kade/KADE.md`
Why: After the holdout survived, the next question was whether the edge was really broad or just a few lucky windows.
Verified: Computed monthly and daily concentration on the processed portion of the test split and showed the window reached only through 2025-09-29 because of the same wall-clock cutoff.
Next: Run the baseline-faithful SOL-only ablation, then propose the deterministic harness path needed for stronger research claims.

2026-04-04T00:30:00+00:00 - Run audit falsification pass 2 on untouched holdout
Changed: Executed the current strategy on train, validation, and untouched test splits, then appended the holdout results into the research audit.
Files: `docs/research-grade-audit.md`, `kade/KADE.md`
Why: The first falsification pass showed scope drift and cost sensitivity, but the main unresolved question was whether the edge survives an untouched holdout period.
Verified: Ran direct read-only backtests across `train`, `val`, and `test`; confirmed the test split remained strong, but also confirmed all runs still ended at the wall-clock budget boundary.
Next: Run outlier and regime concentration analysis, then decide whether to narrow claims or propose a deterministic harness path.

2026-04-04T00:00:00+00:00 - Harden KADE-gstack integration and run audit falsification pass 1
Changed: Hardened the repo-local KADE/gstack contract in agent guidance and docs, then ran a read-only falsification pass for the research audit covering symbol attribution, cost stress, and reproducibility risk.
Files: `AGENTS.md`, `docs/kade-gstack-integration.md`, `kade/AGENTS.md`, `docs/research-grade-audit.md`
Why: The repo had KADE and gstack surfaces but no explicit rule for reconciling their interactive workflow with this repo's autonomous Codex contract. The audit also needed hard evidence beyond literature and headline metrics.
Verified: Reviewed current KADE files and local skill surface, updated guidance docs, ran direct backtest-based attribution and fee/slippage stress analysis, appended results into the audit doc.
Next: Run the untouched holdout pass and outlier concentration analysis, then decide whether the repo headline claims need narrowing.

2026-04-04T02:47:54-06:00 - Generate GitVizz mapping for the repo
Changed: Added GitVizz analysis artifacts under `kade/` for the current repository, including a full mapping, raw graph JSON, and LLM-ready context bundle.
Files: `kade/gitvizz-full-mapping.md`, `kade/gitvizz-full-mapping.json`, `kade/gitvizz-contexts.md`, `kade/gitvizz-graph.json`
Why: Preserve the GitVizz run results locally so the repo context can be resumed without rerunning the analysis.
Verified: Ran GitVizz against a clean 24-file Python mirror of the repo, confirmed the main analyses completed, and removed the oversized GraphML export.
Next: If you want a narrower follow-up, ask for a subsystem-only map, for example workbench, Jupiter live, or backtest flow.

2026-04-04T02:36:45-06:00 - Capture GitVizz repo notes
Changed: Added a repository summary for GitVizz under `kade/gitvizz-report.md`.
Files: `kade/gitvizz-report.md`
Why: Preserve the external repo review in the local KADE folder for later sessions.
Verified: Reviewed the GitHub README and repository tree, then wrote the summary file.
Next: If you want deeper analysis, expand the report with file-by-file notes or architecture risks.

2026-04-04T02:32:31-06:00 - Initialize gstack and KADE context
Changed: Added `kade/AGENTS.md`, `kade/KADE.md`, and a local copy of the `g-kade` skill under `.agents/skills/g-kade`.
Files: `kade/AGENTS.md`, `kade/KADE.md`, `.agents/skills/g-kade/SKILL.md`
Why: Gives the repo a KADE session scaffold, project rules, and a local skill entry point.
Verified: `Test-Path` confirmed the skill copy exists; file contents were reviewed after creation.
Next: Start the next session on the actual repo task, with `strategy.py` still the only intended mutable code surface.

<!-- Newest entries at the top. Format:
YYYY-MM-DDTHH:MM:SS+HH:MM - Subject
Changed: [what changed]
Files: [file paths]
Why: [reasoning]
Verified: [tests/checks]
Next: [single next action]
-->

*Created by /g-kade install*
