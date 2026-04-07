# Auto-Research Terminal UI Spec

Last updated: 2026-04-06
Priority: Parallel to web mission-control UI

## Objective

Create a terminal operator surface for Auto-Research that competes directly with the redesigned web UI on:

- speed to situational awareness
- speed to intervention
- command clarity
- verification discipline

This should not be a generic dashboard.
It should be a command-room console.

## Recommended Stack

- Python
- `Textual` for app layout and focus management
- `Rich` for rendering, formatting, and dense operator summaries

Why:

- aligns with the repo’s Python-first tooling
- can consume existing local HTTP surfaces without adding another language/toolchain
- supports a high-density operator-first terminal experience

## Aesthetic

Direction:

- monochrome brutalist command room
- dark background
- sharp borders
- strong hierarchy
- minimal decorative color

Use color as semantics:

- green for healthy / running
- amber for caution / paused / review
- red for degraded / failed / risky
- muted gray-blue for background metadata

Avoid:

- toy-dashboard styling
- rainbow panes
- excessive animation

## Core User Jobs

### 1. Understand the room fast

The operator needs:

- leader thread
- paper equity
- active / degraded / failed counts
- what changed recently
- what action should happen next

### 2. Control experiment threads

The operator needs:

- start
- pause
- resume
- restart
- stop

### 3. Inspect execution readiness

The operator needs:

- paper/live state
- wallet readiness
- current positions
- exact verification commands

### 4. Review wallet handoffs

The operator needs:

- external-wallet queue visibility
- current handoff state
- clear next action

## Screen Model

### Overview

Purpose:

- immediate room summary

Contains:

- leader
- paper equity
- active / degraded / failed counts
- recent events
- top recommended action

### Threads

Purpose:

- experiment fleet management

Contains:

- thread list
- phase
- score
- health
- degraded reasons
- action bar

### Research

Purpose:

- strategy and validation context

Contains:

- backtest entrypoints
- benchmark path
- 5-minute validation path
- current artifacts and results references

### Execution

Purpose:

- paper/live operational readiness

Contains:

- paper feed state
- validator readiness
- current positions
- exact command suggestions
- post-action verify commands

### Wallet

Purpose:

- trust-boundary-sensitive surfaces

Contains:

- external-wallet handoff queue
- local-wallet readiness
- future lend and multiply placeholders

### Reports

Purpose:

- artifact access

Contains:

- equity exports
- charts
- milestones
- generated artifacts

### System

Purpose:

- process and environment internals

Contains:

- auth state
- process health
- paths
- logs
- runtime contract references

## Layout

Use a four-region TUI:

### Top status bar

Persistent line with:

- mode
- auth user
- paper equity
- leader
- active / degraded / failed
- last refresh

### Left navigation rail

Shows:

- screens
- quick filters
- current selection

### Center mission pane

Primary pane.

Shows:

- system summaries
- operator question prompts
- action cards
- command previews
- verification notices

This is the TUI equivalent of the web mission timeline.

### Right inspector pane

Context-sensitive detail:

- selected thread
- selected position
- selected wallet request
- selected event

### Bottom command bar

Always visible.

Contains:

- command input
- shortcut hints
- focused action

## Interaction Model

Keyboard-first controls:

- `j/k` or arrows to move list focus
- `Tab` to cycle focus regions
- `/` to open command palette
- `Enter` to confirm focused action
- `?` to show shortcuts
- `r` refresh
- `s` start/resume
- `p` pause
- `x` stop
- `v` show verify command
- `o` open detail modal
- `f` filter current list

Every mutating action should show:

1. action summary
2. target object
3. expected result
4. verification command

## Data Sources

Use existing APIs first:

- `GET /api/dashboard`
- `GET /api/workbench/status`
- `POST /api/workbench/control`

Do not invent new backend routes in the first TUI phase.

## Message Types

The center mission pane should support:

- `system-summary`
- `recommended-action`
- `warning`
- `verification`
- `command-block`
- `thread-insight`
- `execution-state`

## Capability Mapping

### Current capabilities

- research harness
- experiment manager
- paper trading
- Jupiter live perps
- external wallet review
- reporting and exports

### Future capability slots

- `swaps`
- `lending`
- `multiply`

These should appear as explicit but inactive slots, not be hidden.

## First Build Target

Phase 1 TUI should include:

- shell
- status bar
- left navigation
- overview screen
- threads screen
- execution screen
- right inspector
- bottom command bar

It should be driven by `/api/dashboard`.

## Acceptance Criteria

- operator can identify leader, equity, and degraded count in under 15 seconds
- thread actions are reachable without leaving the keyboard
- each mutating action exposes one verification step
- execution and wallet surfaces are visually risk-distinct from research browsing
- the screen model can absorb future `swaps`, `lending`, and `multiply` without IA changes

## Recommended Next Step

Scaffold a `Textual` app that:

- polls `/api/dashboard`
- renders the top status bar and screen navigation
- implements `Overview`, `Threads`, and `Execution` first
- leaves `Wallet`, `Reports`, and `System` as the next wave
