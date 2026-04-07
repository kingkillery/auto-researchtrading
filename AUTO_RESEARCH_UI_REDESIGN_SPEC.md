# Auto-Research UI Redesign Spec

Last updated: 2026-04-06
Priority: Top

## Objective

Redesign the Auto-Research workbench into a chat-first operator surface that:

- makes the room understandable in under 15 seconds
- lets the operator act without hunting through tiles
- preserves current dashboard and experiment controls
- exposes codebase capabilities as visible, routable tools
- supports future Jupiter execution surfaces including:
  - swaps
  - perps
  - lending
  - multiply

This redesign should not replace the current control plane logic.
It should recompose it into a more effective UI layer.

## Core Product Direction

The current UI is dashboard-first.
The redesigned UI should be operator-chat-first.

The main idea:

- the center of gravity becomes a guided chat and command timeline
- all major system capabilities become selectable context lenses or action rails
- status panels move from being the product to supporting the conversation

This means the workbench becomes:

- part cockpit
- part mission control
- part chat-assisted execution console

## Primary User Jobs

### Job 1: Understand the room fast

The operator needs to know:

- what is running
- what is winning
- what is degraded
- what is urgent
- what action is worth taking next

### Job 2: Intervene quickly

The operator needs to:

- restart or pause threads
- inspect the leader
- compare experiments
- shift to paper or live views
- review external-wallet handoffs

### Job 3: Ask the system questions

The operator wants to ask:

- why is this thread degraded
- what changed since the last leader
- what is the safest next action
- what commands should I run
- what capability owns this workflow

### Job 4: Transition into execution surfaces

The operator needs a clean path into:

- backtests
- benchmarks
- paper trading
- Jupiter live execution
- future swaps
- future lending
- future multiply

## Design Principles

### 1. Chat is the spine

The main content column is a chat and action timeline.

It should support:

- system summaries
- operator questions
- generated action cards
- thread summaries
- verification messages
- exact commands

### 2. The room is always visible

The operator should always be able to see:

- current leader
- active thread count
- degraded thread count
- paper equity
- auth / mode state

These should live in a compact top rail, not consume half the screen.

### 3. Capabilities, not pages

Navigation should be organized by capability, not by file or implementation detail.

Top-level capability rails:

- `Overview`
- `Threads`
- `Research`
- `Execution`
- `Wallet`
- `Reports`
- `System`

### 4. One action, one verification

Every operator action should visibly pair:

- action
- expected result
- verification check

This keeps the UI aligned with the repo’s execution philosophy.

### 5. Risk surfaces must look different

The UI must clearly distinguish:

- paper
- live
- external-wallet handoff
- future multiply

Multiply, live perps, and external signing should feel more dangerous than research browsing.

## Information Architecture

## Global Layout

Use a three-zone layout:

### A. Top command rail

Persistent compact strip with:

- current mode: `paper`, `live-local`, `live-external`, `read-only`
- auth user
- paper equity
- leader thread
- active / degraded / failed counts
- last refresh time
- quick actions:
  - refresh
  - start paper
  - restart manager
  - open external-wallet board

### B. Main center column

Chat-first mission timeline.

Contains:

- operator/system messages
- generated summaries
- exact commands
- thread action cards
- execution review cards
- future strategy assistant messages

This is the primary surface.

### C. Right context rail

Context panels that change with the current navigation lens.

Potential modules:

- thread inspector
- leader details
- event stream
- position summary
- runtime metadata
- wallet state
- risk summary

## Primary Navigation

### Overview

Purpose:

- orient the operator immediately

Contains:

- top room summary
- chat timeline with “what matters now”
- leader snapshot
- highest-priority interventions
- event highlights

### Threads

Purpose:

- manage the experiment fleet

Contains:

- sortable thread list
- phase
- score
- health
- last decision
- degraded reasons
- controls:
  - start
  - pause
  - resume
  - restart
  - stop

### Research

Purpose:

- understand research outputs and current strategy context

Contains:

- strategy summary
- benchmark links
- backtest entrypoints
- current research artifacts
- generated reasoning cards:
  - why the leader is leading
  - where challenger threads differ

### Execution

Purpose:

- bridge from research to paper/live action

Contains:

- paper mode status
- live readiness
- validator state
- execution capability cards:
  - `perps`
  - `swaps` future
  - `lending` future
  - `multiply` future
- exact commands
- verification steps

### Wallet

Purpose:

- separate trust-boundary-sensitive surfaces

Contains:

- local-wallet readiness
- external-wallet request queue
- handoff file status
- current positions
- future lend and multiply inventory

### Reports

Purpose:

- browse generated outputs and exports

Contains:

- equity curves
- milestone exports
- charts
- artifact links
- recent run outputs

### System

Purpose:

- operational internals

Contains:

- process health
- paths
- auth state
- refresh logs
- packaging/runtime contract state

## Chat Interface Specification

## Main Chat Roles

The chat surface should support these message types:

- `system-summary`
- `operator-question`
- `recommended-action`
- `verification-result`
- `warning`
- `command-block`
- `thread-insight`
- `execution-intent`

## Input Bar

The chat input should support:

- freeform questions
- slash-like quick intents
- capability filters

Suggested quick chips:

- `Explain leader`
- `Why degraded?`
- `Restart weakest thread`
- `Show paper state`
- `Validate live readiness`
- `Open wallet review`
- `Compare top 3 threads`

## Message Card Rules

Every actionable message card should include:

- title
- concise explanation
- recommended action
- one verification step

Every risky message should include:

- trust boundary
- risk level
- next safe action

## Capability-to-UI Mapping

### Current implemented capabilities

#### Research harness

Expose as:

- “Run canonical backtest”
- “Run 5-minute validation”
- “Run benchmark suite”

#### Experiment manager

Expose as:

- thread fleet board
- chat summaries of phase and health
- action cards for restart/pause/resume

#### Paper trading

Expose as:

- paper equity strip
- position cards
- “start paper feed” and “restart paper feed”

#### Jupiter perps live path

Expose as:

- validator readiness card
- local-wallet execution card
- external-wallet handoff card
- position and verification cards

### Future capabilities to design for now

#### Swaps

UI affordances:

- quote card
- route card
- execute card
- slippage chip
- verify card

#### Lending

UI affordances:

- lend markets table
- current deposits summary
- deposit action card
- withdraw action card
- APY and utilization callouts

#### Multiply

UI affordances:

- position risk card
- leverage gauge
- health factor / liquidation distance badge
- delever action card
- close position card

Multiply must be visually distinct from lending.

## Data Sources and Backend Mapping

## Existing backend surfaces to reuse

### `GET /api/dashboard`

Current primary data source.

Use for:

- top command rail
- chat summary seed
- thread list
- event stream
- positions
- metadata

### `GET /api/workbench/status`

Use for:

- lightweight status refresh
- health and process tiles

### `POST /api/workbench/control`

Use for:

- thread and manager actions
- paper feed actions

## Immediate frontend composition strategy

Do not rewrite the backend first.

Instead:

1. keep the current API shape
2. build a new chat-first frontend composition on top of `/api/dashboard`
3. keep the existing control POST surface
4. add new backend endpoints only when the UI truly needs new capability classes

## Component Model

Recommended component groups for the redesigned UI:

- `WorkbenchShell`
- `TopCommandRail`
- `CapabilityNav`
- `MissionTimeline`
- `ChatComposer`
- `ActionCard`
- `ThreadFleetBoard`
- `ThreadInspector`
- `LeaderSummary`
- `EventFeed`
- `ExecutionConsole`
- `WalletReviewPanel`
- `ReportGallery`
- `SystemHealthPanel`

## Visual Direction

The current UI is dark and competent but still reads as a dashboard.
The redesign should feel more like a command room.

Visual goals:

- stronger typographic hierarchy
- less tile repetition
- more asymmetry
- more timeline and rail-based structure
- clearer risk encoding
- more visible state transitions

Recommended design cues:

- keep the current dark palette family
- reduce equal-weight card repetition
- use one strong display font and one clear body font
- use amber for operator attention, green for healthy motion, red for unsafe/risky states
- reserve the most saturated warning treatment for:
  - live execution
  - external signing
  - future multiply

## Responsive Behavior

### Desktop

- three-zone layout
- center-column chat emphasis
- right rail stays visible

### Tablet

- top rail
- chat center
- collapsible side rail drawers

### Mobile

- command rail becomes compact pills
- capability nav becomes bottom segmented bar
- right rail becomes slide-up sheets
- chat remains the primary surface

## Suggested User Flows

### Flow 1: Morning operator check

1. land on `Overview`
2. top rail shows leader, paper equity, degraded count
3. chat presents “what changed since last refresh”
4. operator clicks one action card

### Flow 2: Investigate degraded thread

1. go to `Threads`
2. select degraded thread
3. right rail shows:
   - degraded reasons
   - last verification
   - last decision
4. chat offers restart or pause recommendation

### Flow 3: Move from research to execution

1. go to `Execution`
2. see readiness cards:
   - validator
   - paper/live mode
   - wallet path
3. chat offers exact command
4. operator sees verify step beside it

### Flow 4: Review external wallet request

1. go to `Wallet`
2. open handoff queue
3. inspect request card
4. jump to external review board

## Implementation Phases

### Phase 1: Frontend-only recomposition

Goal:

- redesign without backend expansion

Do:

- new layout shell
- chat timeline fed from existing dashboard payload
- capability navigation
- thread board redesign
- right-rail inspectors

### Phase 2: Chat-assisted action model

Goal:

- make action cards and operator prompts first-class

Do:

- structured message feed
- richer event-to-message translation
- saved operator prompts

### Phase 3: Execution console expansion

Goal:

- integrate future capability families

Do:

- swaps
- lending
- multiply
- richer wallet and verification views

## Acceptance Criteria

The redesign is successful if:

- an operator can identify the leader, degraded threads, and next recommended action in under 15 seconds
- thread controls are reachable without scrolling through dashboard clutter
- the execution path is visually and semantically separated from research browsing
- the chat timeline explains what changed, not just what exists
- multiply and live execution look riskier than research and paper surfaces
- the UI can absorb future swaps/lending/multiply capabilities without another IA rewrite

## Immediate Next Build Target

Build a new generative workbench artifact that replaces the current embedded generative surface with a chat-first mission-control layout.

The first implementation should:

- reuse `/api/dashboard`
- keep `/api/workbench/control`
- introduce:
  - top command rail
  - capability nav
  - mission timeline center column
  - thread fleet board
  - right context rail

Do not start by redesigning every backend route.
Start by changing the frontend composition model.
