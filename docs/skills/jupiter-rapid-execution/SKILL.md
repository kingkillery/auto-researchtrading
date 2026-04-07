---
name: jupiter-rapid-execution
description: "Gain rapid operator context on any Jupiter-related item in this repo, then move to the fastest safe action when needed. Use for low-friction position understanding, CLI-first execution planning, repo-local live runner operation, wallet readiness checks, dry-run rehearsals, external-wallet handoff creation, or design and operation of a repo-owned `jupiter-execution` tool surface spanning swaps, perps, lending, and multiply. Prefer this skill when speed, clarity, and low-friction operator briefings matter."
---

# Jupiter Rapid Execution

Use the fastest safe local surface that still preserves control.

## Primary purpose

This skill exists to reduce time-to-understanding first, then time-to-action.

When invoked, do this in order:

1. Gain the minimum context needed to explain the item clearly.
2. Summarize that context so the user can understand it quickly too.
3. Choose the correct execution surface only after the state is clear.

The skill is not just for placing orders. It is for rapidly answering:

- what is this item
- what surface owns it
- what is the current state
- what is the next safe action
- what exact command proves or changes that state

It is also the design surface for a repo-owned `jupiter-execution` tool when the user wants one unified control plane instead of separate ad hoc commands.

That tool surface should cover four capability families:

- `swaps`
- `perps`
- `lending`
- `multiply`

The skill should treat those as separate trust and risk classes even if they share one user-facing tool namespace.

## Output contract

Default to a short operator briefing with low friction.

Use this shape unless the user asks for more depth:

- `What it is:` one sentence
- `Why it matters now:` one sentence
- `Current state:` 2 to 4 bullets max
- `Next action:` one clear recommendation
- `Command:` one exact command if a command is appropriate
- `Verify:` one exact check after action

ADHD rule:

- prefer scan-friendly answers over prose walls
- keep the first useful answer short
- front-load the decision and the next command
- avoid making the user reconstruct state from scattered details
- if more depth is needed, layer it after the short briefing

## Execution stance

- Start with context gathering when the user asks about an item, position, setup, path, or failure.
- Prefer local shell plus `jup` CLI for urgent action.
- Use this repo's `run_jupiter_live.py` when the strategy contract is the source of truth and the position must be translated from target USD notional.
- Treat Jupiter docs MCP as a read-only knowledge surface, not an execution surface.
- Treat browser wallets and external signing as separate trust boundaries.
- Keep the first command read-only whenever setup uncertainty exists.
- When designing a repo-owned `jupiter-execution` tool, prefer one explicit typed tool surface over a fuzzy agent prompt.
- The tool should normalize intent first, then choose the correct Jupiter backend.

## Rapid context checklist

When the user asks about any Jupiter item, gather only the shortest set of facts needed to orient them:

- item type: direct CLI action, repo live runner action, external-wallet handoff, docs question, or integration question
- asset scope: `BTC`, `ETH`, `SOL`, swap-only assets, lendable assets, or multiply-eligible assets
- readiness: global `jup` available or not, validator pass or fail
- trust boundary: local signing, external signing, or docs-only
- current state: current position, current config, pending handoff file, blocked setup, active lend deposits, or multiply exposure

Stop gathering once you can produce a decision-ready briefing.

## Surface selection

Choose one path before acting:

- `Direct CLI`
  - Best when the desired trade is already known and speed matters more than strategy replay.
  - Typical cases: open or close a specific perp position, inspect current positions, inspect config, inspect key state.
- `Repo live runner`
  - Best when the strategy output in this repo should drive the action.
  - Use for paper/live mode, guarded budget control, dry-run rehearsal, and external-wallet request generation.
- `External-wallet handoff`
  - Best when signing must stay outside the local process.
  - Use `--wallet-mode external` and review requests through `external_wallet_bridge.py`.
- `Repo-owned jupiter-execution tool`
  - Best when the repo should present one explicit operator or MCP surface for swaps, perps, lending, and multiply.
  - Use it as a thin orchestration layer, not as a hidden strategy engine.

## Repo-owned `jupiter-execution` tool contract

If the user asks to create our own Jupiter tool, use this shape.

The tool should expose explicit operations instead of one overloaded command:

- `swap.quote`
- `swap.execute`
- `perps.positions`
- `perps.open`
- `perps.close`
- `lending.markets`
- `lending.positions`
- `lending.deposit`
- `lending.withdraw`
- `multiply.markets`
- `multiply.position`
- `multiply.open`
- `multiply.adjust`
- `multiply.close`

Each operation should accept a normalized request envelope and return a normalized response envelope.

### Required request envelope

Every mutating action should normalize into:

- `request_id`
- `mode`: `read_only`, `paper`, `live_local`, or `live_external`
- `capability`: `swap`, `perps`, `lending`, or `multiply`
- `operation`
- `asset`
- `amount_usd` and/or `amount_token`
- `wallet_mode`
- `slippage_bps` where applicable
- `max_leverage` where applicable
- `reduce_only` where applicable
- `dry_run`
- `reason`

### Required response envelope

Every operation should return:

- `request_id`
- `status`
- `capability`
- `operation`
- `summary`
- `raw_surface`
- `verify_command`
- `artifacts`
- `warnings`

### Backend routing rules

Route capabilities explicitly:

- `swap`
  - prefer Jupiter Swap API or a dedicated repo wrapper when HTTP execution is intentionally added
  - until then, use the shortest verified local surface or browser handoff
- `perps`
  - use `jup` CLI directly for urgent known actions
  - use `run_jupiter_live.py` when strategy output is the source of truth
- `lending`
  - use a dedicated Jupiter Lend integration path when added
  - do not fake lend support by pretending perps or swaps cover it
- `multiply`
  - keep as a distinct capability because it combines supply, borrow, and leverage semantics
  - require stronger checks than plain lending

### Tool-design hard rules

- Do not collapse `lending` and `multiply` into one generic "earn" mutation surface.
- Do not let research outputs call mutating operations directly.
- Do not hide leverage defaults.
- Do not infer collateral source silently.
- Do not mix read-only docs MCP with execution authority.
- Do not use one planner prompt as a substitute for typed tool arguments.

## Capability-specific rules

### Swaps

Use for token conversion and pre-lend / pre-perps inventory preparation.

Required fields:

- `input_token`
- `output_token`
- `amount`
- `slippage_bps`

Required checks:

- quote freshness
- route sanity
- minimum received
- fee visibility

### Perps

Use for directional exposure, reduce-only exits, and strategy-driven target deltas.

Required fields:

- `asset`
- `side`
- `target_notional_usd`
- `leverage`
- `reduce_only`

Required checks:

- current position state
- market state
- estimate / preview before exposure increase
- verification after execution

### Lending

Use for supply-only deposits and withdrawals.

Required fields:

- `asset`
- `deposit_amount`
  or
- `withdraw_amount`

Required checks:

- current supply APY
- utilization if available
- liquidity / TVL quality
- wallet post-action balance buffer

### Multiply

Treat multiply as the highest-risk retail surface in this skill.

Required fields:

- `asset`
- `initial_collateral`
- `target_leverage`
- `max_leverage`

Required checks:

- supply APY
- borrow APR
- net carry
- health factor or equivalent risk indicator
- liquidation distance
- explicit de-risk plan

Multiply refusal conditions:

- missing leverage cap
- no visible liquidation / health metric
- borrow APR too close to or above supply yield
- too little post-action wallet buffer
- unclear unwind path

## Mandatory preflight

Before any live-capable action:

1. Read [docs/jupiter-execution.md](../../jupiter-execution.md).
2. Confirm command availability:
   - `node --version`
   - `npm --version`
   - `jup --version`
3. Inspect Jupiter CLI state:
   - `jup config list -f json`
   - `jup keys list -f json`
4. Validate repo-local live readiness without sending orders:
   - `uv run python run_jupiter_live.py --validate-local-wallet-setup`
5. If building or operating a repo-owned `jupiter-execution` tool, decide capability scope first:
   - `swap`
   - `perps`
   - `lending`
   - `multiply`

If `jup` is missing but Node/npm exist, the repo may still resolve the CLI through `npx --yes @jup-ag/cli`.

If the fallback path fails, install the CLI globally before relying on it in a fast market:

```powershell
npm install -g @jup-ag/cli
jup --version
```

## Fast operating rules

- Prefer JSON output where available.
- Prefer the shortest command that proves readiness before the command that changes state.
- Use `--jupiter-cli-dry-run` before the first real broadcast through the repo runner.
- Keep `--live-equity-budget-usd` explicit. Never infer budget from wallet state.
- Keep leverage explicit. Never assume leverage from an old terminal session.
- Ignore tiny deltas by keeping `--min-live-position-change-usd` intentional.
- After any action, verify resulting position state instead of assuming the request landed.
- Treat global `jup` install as the real readiness standard for urgent execution. `npx` fallback is acceptable for setup and testing, but it adds startup variability and can fail on local npm cache or lock issues.
- Fail fast if CLI resolution is slow or unstable. Do not wait through a flaky first-run `npx` install when the market is moving.
- Keep one live writer per wallet and one request writer per JSONL handoff path. Do not run parallel live loops against the same wallet.
- For `multiply`, require an explicit de-risk / delever plan before allowing execution instructions.
- For `lending`, distinguish clearly between supply-only actions and collateral-bearing actions.
- For `swap`, prefer quote first, execute second.

## Required parameter bounds

Apply these bounds before running live-capable commands:

- Asset whitelist: `BTC`, `ETH`, `SOL` only
- `--live-equity-budget-usd`: positive, explicit, and intentionally small on the first live run
- `--live-leverage`: greater than `1.0`; prefer a bounded operating range such as `1.1` to `5` unless a higher value is deliberately justified
- `--jup-key`: non-empty and already visible in `jup keys list -f json`
- `--order-request-path`: keep under a repo-controlled path such as `artifacts\orders\`
- `multiply` leverage: require explicit target and explicit max; do not silently default to aggressive leverage
- `lending`: keep explicit wallet buffer after deposit
- `swap`: keep slippage explicit

If any of those checks fail, stop and correct the setup before retrying.

## Repo-local workflows

### Workflow A: Validate local wallet path

Run:

```powershell
uv run python run_jupiter_live.py --validate-local-wallet-setup
```

Use this when live mode might be needed soon but you do not want to start the feed yet.

### Workflow B: Rehearse the live order path without broadcast

Run:

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode local `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd 250 `
  --live-leverage 2 `
  --jupiter-cli-dry-run
```

Use this to exercise signing and order construction without actually sending orders.

### Workflow C: Let the repo translate strategy targets into live deltas

Run:

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode local `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd <usd_budget> `
  --live-leverage <leverage> `
  --jup-key <key_name>
```

Use this only after wallet validation and dry-run rehearsal pass.

Do not start a second live local-wallet process for the same key while one is already running.

### Workflow D: Emit an external-wallet approval request instead of signing

Run:

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode external `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd <usd_budget> `
  --live-leverage <leverage> `
  --order-request-path <path-to-orders.jsonl>
```

Review with:

```powershell
uv run python external_wallet_bridge.py --request-path <path-to-orders.jsonl>
```

Use one canonical request file per workflow, keep it under `artifacts\orders\`, and review the same file that the runner created. If the file was copied, edited, or relocated after generation, treat it as untrusted.

## Direct CLI workflows

Use direct CLI when the trade is already decided and the repo strategy translation layer is unnecessary.

These examples assume `jup` is installed globally and already validated on this machine.

- Inspect positions:
  - `jup perps positions -f json`
- Inspect markets:
  - `jup perps markets -f json`
- Open a perp:
  - `jup perps open --asset SOL --side long --size 250 --amount 125 --input USDC`
- Close a perp:
  - `jup perps close --asset SOL --side long --size 250 --receive USDC`

Exact flags can drift because the CLI is pre-v1 alpha. Re-check `--help` on the target command before using a command pattern you have not exercised on this machine.

## Swap-specific guidance

For swap integrations or code generation:

- Prefer Jupiter Swap API `/order` + `/execute` for most execution flows because it offers the best routing and simplest path.
- Use `/build` only when transaction modification or composition is required.
- Treat this as integration guidance, not evidence that this repo already has a native HTTP execution path.

## Lending and multiply guidance

If the user asks for Jup Lend or Multiply support:

- treat it as a first-class capability, not an afterthought under swaps or perps
- separate `deposit / withdraw` from `add collateral / open multiply / adjust leverage / close multiply`
- require explicit inventory state before recommending swaps to prepare deposits
- require explicit unwind instructions for any multiply recommendation
- require a post-action verification step that reads back resulting positions or balances

Suggested repo-owned operation groups:

- `lending.markets`
- `lending.positions`
- `lending.deposit`
- `lending.withdraw`
- `multiply.markets`
- `multiply.position`
- `multiply.open`
- `multiply.adjust`
- `multiply.close`

## Read-only knowledge sources

- Jupiter docs MCP: `https://dev.jup.ag/mcp`
- Jupiter docs LLM index: `https://dev.jup.ag/docs/ai/llms-txt`
- Raw markdown export: append `.md` to a docs URL

Use these to resolve docs uncertainty quickly before execution or coding.

Use them for context compression, not for action execution.

## Do not do these

- Do not use a hosted-only flow when a local CLI path is available and speed matters.
- Do not assume MCP can execute trades just because it can search docs.
- Do not treat community MCP servers as production-safe without reviewing their trust model and key handling.
- Do not broadcast from the repo live path before the validator passes.
- Do not point external-wallet review at a copied or hand-edited JSONL file.
- Do not run concurrent live loops against the same wallet or concurrent writers against the same order-request file.
- Do not broaden this repo's execution dependency set without an explicit scope change.
- Do not describe `multiply` as low-risk lending.
- Do not use one blended "earn" label when the user actually needs to know whether the action is supply, collateralization, borrow, or leverage.
- Do not let a future `jupiter-execution` tool mutate positions without returning a verification command.

## Verification

After any live-capable action:

1. Re-read positions:
   - `jup perps positions -f json`
2. If using the repo runner, inspect emitted `portfolio_before`, `portfolio_after`, `orders`, and `order_events`.
3. If using external-wallet mode, confirm approval or submission state in the JSONL board.
4. Record the exact command used and the resulting state.

After any lend or multiply action:

1. Re-read the resulting deposit or multiply position state.
2. Confirm the intended asset, amount, and leverage are reflected.
3. Confirm the wallet still has the intended buffer.
4. Record the unwind or delever command for the operator.

After any context-only request:

1. Restate the owning surface.
2. Restate the current state in a few bullets.
3. Give the next command that would prove or change the state.

## References

- Fast command patterns and operator notes: [references/command-playbook.md](references/command-playbook.md)
