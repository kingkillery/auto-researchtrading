# Jupiter Perps MCP Governance Spec

Last updated: 2026-04-05
Target: `diaorui/jupiter-perps-mcp`

## Summary

This spec defines how `jupiter-perps-mcp` should be used inside a high-autonomy trading system.

The MCP server is treated as a **privileged trading actuator**, not as a planner or strategy engine. It may inspect portfolio state, estimate trades, and execute trades, but only inside a governed execution chain.

Operating model:

- Default mode is **human-gated**
- Paper mode is the default training and self-improvement lane
- Research outputs are **policy inputs**, not direct trading authority
- Emergency autonomy exists, but it is **reduce-only**
- Every privileged action must be traceable, verifiable, and journaled

## System Model

The governed system has seven layers:

1. **Research engine**
   - produces hypotheses, patterns, score deltas, and confidence signals
2. **Strategy / model inference**
   - converts current market state plus research inputs into a trade thesis
3. **Risk and governance policy**
   - validates whether the thesis is actionable under hard and soft rules
4. **Trade-intent builder**
   - converts an allowed thesis into a normalized trade intent
5. **MCP execution layer**
   - performs reads, estimates, and privileged execution against Jupiter Perps
6. **Post-trade verifier**
   - confirms that chain state matches intent
7. **Feedback loop**
   - scores results, analyzes failures, and adjusts policy or model behavior

The MCP server sits at layer 5 only. It must not decide strategy, position sizing policy, or live promotion on its own.

## Tool Trust Levels

The MCP surface must be classified into three trust tiers.

### Tier A, Read-only

Allowed without human approval:

- `get_market_snapshot`
- `get_candles`
- `get_account_portfolio`
- indicator tools such as RSI, MACD, Bollinger Bands, ATR, EMA, SMA, and Stochastic

Constraints:

- may not mutate portfolio state
- may be used freely in paper and live modes
- stale responses must be marked and may not be used for privileged execution

### Tier B, Estimate

Estimate-only tools:

- `estimate_open_position`
- any transaction simulation or fee/impact estimation tool

Constraints:

- required before any exposure-increasing live execution
- estimate outputs expire after a freshness window
- if estimate fails, privileged execution must refuse

### Tier C, Privileged execution

Privileged tools:

- `open_position`
- `close_position`

Constraints:

- never callable directly from research output
- require fresh Tier A state plus fresh Tier B estimate
- must emit a trade-intent envelope and a policy decision envelope before execution
- all executions must be journaled and verified

## Operating Modes

### Paper Mode

Default mode.

Properties:

- no real wallet side effects
- full research, scoring, and feedback loop enabled
- used for new strategies, policy changes, and threshold changes

### Live Human-Gated Mode

Normal production mode.

Properties:

- exposure-increasing actions require explicit human approval
- read-only and estimate operations are autonomous
- all live actions must pass policy checks and post-trade verification

### Live Emergency Mode

Special mode used only for protective actions.

Properties:

- autonomy is allowed only for **reduce-only** actions
- no new positions
- no increase to any existing position
- no hedge that increases gross exposure
- all emergency actions require explicit reason codes and journaling

## Allowed Execution Chains

### Standard live chain

1. Read fresh portfolio state
2. Read fresh market state
3. Generate strategy thesis
4. Build normalized trade intent
5. Evaluate hard and soft policy rules
6. Run estimate and simulation
7. Check estimate freshness and state freshness
8. Require human approval for any exposure-increasing action
9. Execute through MCP
10. Verify resulting portfolio state
11. Journal outcome
12. Update cooldowns, budgets, and feedback state

### Paper-mode chain

1. Read market state
2. Generate strategy thesis
3. Build trade intent
4. Evaluate policy
5. Simulate execution in paper mode
6. Verify simulated resulting state
7. Journal and score outcome
8. Feed results into adjustment loop

### Emergency reduce-only chain

1. Detect policy breach or model-judged danger
2. Confirm emergency mode eligibility
3. Refresh portfolio and market state
4. Build reduce-only intent
5. Estimate closing or reducing action
6. Execute reduce-only action
7. Verify resulting state
8. Journal cause, action, and outcome
9. Enter cooldown

## Forbidden Execution Chains

The following must be rejected:

- research output -> direct `open_position`
- execution without a fresh portfolio snapshot
- execution without a fresh market snapshot
- exposure increase without estimate
- execution after failed simulation
- execution when post-trade verification from the previous action is unresolved
- repeated identical execution attempts without a material state change
- emergency mode opening a new position
- emergency mode increasing exposure
- model confidence overriding hard policy limits

## Trade Intent Contract

Every potential trade must first be represented as a normalized trade intent.

Required fields:

- `intent_id`
- `timestamp`
- `mode`: `paper`, `live_human_gated`, or `live_emergency`
- `asset`
- `side`
- `action`: `open`, `increase`, `reduce`, `close`
- `target_notional_usd`
- `target_leverage`
- `reduce_only`
- `source_signal_summary`
- `confidence`
- `reason_codes`
- `research_refs`

Rules:

- `reduce_only = true` is mandatory in emergency mode
- trade intent must exist before estimate or execution
- raw strategy output may not bypass this envelope

## Policy Decision Contract

Every trade intent must be evaluated into a policy decision before execution.

Required fields:

- `decision_id`
- `intent_id`
- `decision`: `allow`, `deny`, `human_review`, or `emergency_reduce`
- `hard_rule_failures`
- `soft_rule_warnings`
- `state_freshness`
- `estimate_required`
- `approval_required`
- `expiry_timestamp`

Hard rule failures must block execution.

Soft rule warnings may:

- downgrade to human review
- reduce allowed size
- trigger paper-mode fallback

Research outputs may adjust warnings or confidence, but may not override hard failures.

## Hard Policy Rules

The implementation must support these rule categories, even if exact numbers are configurable per deployment:

- max leverage by asset
- max notional per trade
- max gross exposure
- max net directional exposure
- max number of open positions
- max portfolio drawdown
- max loss per day
- max loss per rolling session
- max slippage tolerance
- minimum collateral buffer after fees
- max trade frequency
- cooldown after failed execution
- cooldown after emergency action
- no averaging down unless explicitly enabled
- no live trading before paper-mode promotion criteria are met

## Emergency Authority

### Allowed actions

- partial reduce
- full close
- profit-taking close
- stop-loss close
- cancel or suppress any queued exposure-increasing action

### Forbidden actions

- new open
- increase position size
- flip from flat to non-flat
- open a hedge that increases gross exposure
- rotate capital into a different asset

### Trigger sources

Emergency mode may activate from either:

1. **Policy breach**
   - liquidation proximity
   - drawdown breach
   - collateral buffer breach
   - slippage blowout
   - stale state
   - verification failure after submission

2. **Model judgment**
   - only if informed by current market state plus research-derived signals
   - must provide explicit reason codes
   - must be journaled as model-invoked emergency action

Model judgment is allowed to trigger only **reduce-only** behavior. It may not create new exposure.

## Freshness and Staleness Rules

Privileged execution must refuse if any required state is stale.

Minimum freshness checks:

- portfolio snapshot freshness
- market snapshot freshness
- estimate freshness
- policy decision freshness

If any freshness window expires:

- invalidate estimate
- invalidate approval token
- require re-read of state
- require re-evaluation of policy

## Post-Trade Verification

Every privileged action must be followed by verification.

Verification must confirm:

- tx submission status
- tx signature exists if submitted
- resulting portfolio matches intended action
- resulting leverage and exposure are within policy
- fees and slippage are within tolerated range

Verification outcomes:

- `confirmed`
- `failed`
- `mismatched`
- `unknown`

If verification is not `confirmed`, no further privileged execution may proceed until the discrepancy is resolved or the system is downgraded to read-only.

## Persisted State and Journal

Every privileged attempt must be persisted.

Required recorded state:

- trade intent envelope
- policy decision envelope
- portfolio snapshot metadata
- market snapshot metadata
- estimate result
- approval status
- execution request
- tx signature
- verification result
- final portfolio delta
- resulting cooldowns
- failure class if any

This state is required for:

- duplicate detection
- replay protection
- incident review
- feedback scoring
- promotion and rollback decisions

## Duplicate and Loop Protection

The system must detect and suppress repeated unsafe patterns.

Required protections:

- reject repeated identical exposure-increasing intents inside cooldown
- reject submit-retry loops without new state
- reject open-close-open churn inside a short horizon unless explicitly approved
- cap failed execution retries
- force read-only downgrade after repeated verification failures

## Paper-Mode Training Loop

Paper mode is the default learning environment.

Required loop:

1. Generate research hypothesis
2. Produce strategy and policy candidate
3. Run in paper mode
4. Capture trades, misses, fees, slippage, and failure classes
5. Score outcome
6. Produce feedback record
7. Adjust model or policy
8. Retest

Required outputs per cycle:

- total return
- drawdown
- trade count
- slippage behavior
- policy denials
- emergency triggers
- verification failures
- model-vs-policy mismatch counts

## Promotion to Live

A candidate may not move from paper mode to live mode until all promotion criteria pass.

Required promotion gates:

- minimum paper-mode duration
- minimum paper trade count
- acceptable drawdown
- acceptable execution quality
- no unresolved verification failures
- explicit human approval

Promotion is an explicit state change. It must not happen implicitly because paper performance looks good.

## Feedback and Self-Improvement Loop

The standard loop is:

`results -> analyze -> score -> feedback -> adjust -> retest`

Feedback records must classify whether the needed adjustment belongs to:

- research hypothesis
- strategy logic
- policy thresholds
- emergency trigger logic
- MCP execution handling
- verification logic

Live-mode feedback may influence future proposals and review queues, but should not silently rewrite live governance.

## Refusal Rules

The implementation must fail closed.

Mandatory refusal conditions:

- no estimate for exposure-increasing action
- stale estimate
- stale portfolio state
- stale market state
- unresolved previous verification failure
- policy hard-rule violation
- insufficient collateral buffer
- slippage over policy limit
- invalid emergency action scope
- repeated execution attempt without state change

## Implementation Guidance

This spec implies these concrete implementation surfaces in or around the MCP system:

- a normalized trade-intent layer before tool execution
- a policy evaluator that runs before any Tier C tool
- a journal store for execution and verification records
- a freshness model for state and estimate expiry
- explicit reduce-only emergency helpers
- a mode controller for `paper`, `live_human_gated`, and `live_emergency`

The MCP server should remain a compact action interface, but it must be wrapped by explicit policy and verification contracts.

## Acceptance Criteria

The governance implementation is acceptable only if all of the following are true:

- no exposure-increasing live trade can occur without estimate and approval
- emergency mode can only reduce or close positions
- every privileged action is journaled and verified
- repeated failed submissions trigger cooldown or downgrade
- paper mode is the default training environment
- live promotion requires explicit approval
- research outputs cannot directly force execution
- the system can explain why any trade was allowed, denied, or reduced
