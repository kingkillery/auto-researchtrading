# KADE and gstack Integration

Last updated: 2026-04-04

## Purpose

This repo uses KADE session artifacts and the local `g-kade` skill as workflow aids, not as a replacement for the repo's top-level `AGENTS.md`.

The integration rule is simple:

1. root [AGENTS.md](../AGENTS.md) defines repo-wide constraints
2. [kade/AGENTS.md](../kade/AGENTS.md) captures repo-local KADE session metadata
3. [kade/KADE.md](../kade/KADE.md) is the handoff log
4. [.agents/skills/g-kade/SKILL.md](../.agents/skills/g-kade/SKILL.md) is the session orchestrator surface

## Repo-specific hardening rules

- `g-kade` must not widen edit scope beyond the repo rule that defaults work to `AGENTS.md` and `docs/` unless the user explicitly requests code or runtime edits.
- `g-kade` checkpoint prompts are advisory in this repo. In autonomous Codex sessions, replace interactive pauses with:
  - stated assumption
  - action taken
  - evidence collected
  - single next action
- If `g-kade` suggests creating or editing `CLAUDE.md`, prefer updating [AGENTS.md](../AGENTS.md) or docs first unless the user explicitly asks for Claude-specific routing.
- Session opener should always ground to:
  - branch
  - last action
  - latest KADE handoff
  - current concrete task
- Session close should always append a handoff entry to [kade/KADE.md](../kade/KADE.md) when work changes:
  - agent guidance
  - docs
  - audit state
  - generated repo context artifacts

## Recommended session shape here

Use this lightweight structure:

1. Goal
2. Status
3. Current plan
4. Evidence
5. Next action

This keeps KADE useful without fighting the repo's autonomous execution model.
