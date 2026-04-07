# Jupiter Execution Modes

This repo has two explicit execution modes in [`run_jupiter_live.py`](/C:/Dev/Desktop-Projects/Auto-Research-Trading/run_jupiter_live.py):

- `--execution-mode paper`
  Uses the current paper engine and simulated fills.
- `--execution-mode live`
  Uses the same market-data feed, but routes target positions through the Jupiter execution adapter.

Live mode is intentionally hard to trigger. It requires all of the following:

- `--execution-mode live`
- `--live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS`
- `--live-equity-budget-usd <explicit-usd>`

The local-wallet path now also refuses to start unless the Jupiter CLI, key configuration, and perps position probe all pass the built-in validator.

## Local-Wallet Path

`--wallet-mode local` is the real order path for this repo.

- Position sync uses `jup perps positions`
- Opens use `jup perps open`
- Reductions and closes use `jup perps close`
- Supported assets are currently `BTC`, `ETH`, and `SOL`
- The current implementation opens with `USDC` collateral and closes to `USDC`
- Target deltas smaller than `--min-live-position-change-usd` are ignored

The adapter converts the repo's strategy contract:

- input: `Signal(symbol, target_position=<signed USD notional>)`
- execution model: Jupiter perps open and close commands

Because Jupiter perps accepts an explicit USD size and collateral amount, the adapter uses:

- `--size <delta_usd>`
- `--amount <delta_usd / live_leverage>`
- `--input USDC`

## How The CLI Is Resolved

By default the runner now resolves the Jupiter CLI this way:

1. use an installed `jup` binary if one exists on `PATH`
2. otherwise fall back to `npx --yes @jup-ag/cli`

That means this machine can validate the path even when `jup` is not globally installed yet, as long as Node/npm is present.

You can still override the command explicitly:

```bash
uv run python run_jupiter_live.py --validate-local-wallet-setup --jupiter-cli-path "npx --yes @jup-ag/cli"
```

For lower latency and less runtime variability, a global install is still the recommended operator setup:

```bash
npm install -g @jup-ag/cli
jup --version
```

## Jupiter Ecosystem Layers

There are two distinct Jupiter-facing layers that may show up in future agent or integration work:

- `jup-ag/agent-skills`
  - knowledge layer for AI agents
  - provides instruction/context packages such as `integrating-jupiter` and `jupiter-lend`
  - useful for teaching an agent what Jupiter surfaces exist and how to reason about valid workflows
  - not a runtime dependency of this repo
- `@jup-ag/api` from `jup-ag/jupiter-quote-api-node`
  - execution layer for JavaScript or TypeScript integrations
  - provides the generated Jupiter API client for live HTTP quote and route calls
  - relevant only if this repo explicitly adds a JS or TS execution path

Current repo contract:

- live execution remains CLI-backed through `jup`
- operator docs may reference Jupiter skills as optional agent context
- agent skill packages must not be treated as proof that the repo has gained a new execution dependency
- `@jup-ag/api` should not be introduced into this repo without an explicit scope change

## Advanced Borrow Helper

The repo now includes an isolated advanced helper for Jupiter Lend borrow vault closes:

- path: `tools/jupiter-lend-advanced/`
- entrypoint: `node tools/jupiter-lend-advanced/repay_with_collateral_max_withdraw.mjs`
- purpose: implement the official `Repay with Collateral and Max Withdraw` flow using:
  - `@jup-ag/lend-read`
  - `@jup-ag/lend/flashloan`
  - `@jup-ag/lend/borrow`
  - Jupiter Lite API quote and swap-instructions

Trust boundary:

- this helper is separate from `run_jupiter_live.py`
- it targets borrow vault unwind / close flows, not perps
- it defaults to `--preview`
- it only broadcasts when `--send` and a matching Solana keypair path are provided
- it currently targets Jupiter Lend borrow vaults discovered through `@jup-ag/lend-read`, not the separate public Perps/JLP loan surface behind `perps-api.jup.ag/v1/loans/*`

## Perps JLP Loan Helper

The repo now also includes a dedicated helper for the public Jupiter Perps JLP loan surface:

- path: `tools/jupiter-perps-loans/`
- entrypoint: `node tools/jupiter-perps-loans/jlp_loan_cashout.mjs`
- purpose: preview and, when the upstream endpoint allows it, execute the sequence:
  - inspect live JLP loan state
  - sweep loose wallet `JLP` toward `USDC`
  - repay toward the JLP loan
  - withdraw the maximum JLP allowed by the official backend

Trust boundary:

- this helper is separate from `run_jupiter_live.py`
- it uses the official public Perps API under `https://perps-api.jup.ag/v1`
- it probes `POST /loans/repay-withdraw` before any mutation
- it refuses to send transactions when the official repay endpoint rejects the live position

Install:

```powershell
npm --prefix tools/jupiter-perps-loans install
```

Preview:

```powershell
node tools/jupiter-perps-loans/jlp_loan_cashout.mjs --preview
```

Broadcast only with an explicit keypair:

```powershell
node tools/jupiter-perps-loans/jlp_loan_cashout.mjs `
  --send `
  --keypair-path C:\path\to\solana-keypair.json
```

Operational note:

- the helper treats the official Perps API as the source of truth for current loan state
- it will not mutate unless the current preview sees an open position and the official `POST /loans/repay-withdraw` probe succeeds for the derived action

Install the helper dependencies:

```powershell
npm --prefix tools/jupiter-lend-advanced install
```

Preview the close path using the wallet in repo `.env`:

```powershell
node tools/jupiter-lend-advanced/repay_with_collateral_max_withdraw.mjs --preview
```

Preview while also sweeping any loose wallet JLP into the swap leg:

```powershell
node tools/jupiter-lend-advanced/repay_with_collateral_max_withdraw.mjs `
  --preview `
  --include-wallet-collateral
```

Broadcast only with an explicit keypair:

```powershell
node tools/jupiter-lend-advanced/repay_with_collateral_max_withdraw.mjs `
  --send `
  --keypair-path C:\path\to\solana-keypair.json `
  --include-wallet-collateral
```

## Local Wallet Setup

### 1. Confirm Node/npm or a global `jup`

```bash
node --version
npm --version
jup --version
```

If `jup` is missing but Node/npm exists, the repo validator can still use the npm package through `npx`.

### 2. Provision a Jupiter signing key

Inspect the current keyring:

```bash
jup keys list -f json
```

Create or import a signing key:

```bash
jup keys add live-local
```

or import an existing Solana CLI keypair:

```bash
jup keys solana-import --name live-local --path <solana-keypair.json>
```

Then select it:

```bash
jup keys use live-local
```

### 3. Run the repo-local validator

This does not start the feed and does not submit orders. It verifies:

- the CLI command can run
- the CLI config is readable
- the selected key exists
- perps market metadata is reachable
- `jup perps positions` works for the selected key

```bash
uv run python run_jupiter_live.py --validate-local-wallet-setup
```

To validate a specific configured key:

```bash
uv run python run_jupiter_live.py --validate-local-wallet-setup --jup-key live-local
```

The command exits with:

- `0` when `ready_for_live_local_wallet` is `true`
- `1` when setup is incomplete or broken

### 4. Exercise the live path without broadcasting

The runner can pass Jupiter's own `--dry-run` flag to every open and close command:

```bash
uv run python run_jupiter_live.py \
  --execution-mode live \
  --wallet-mode local \
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS \
  --live-equity-budget-usd 250 \
  --live-leverage 2 \
  --jupiter-cli-dry-run
```

This still requires the explicit live confirmation phrase, but it prevents actual order broadcast while exercising the signing and order-construction path.

### 5. Only then allow broadcasts

Keep the first live budget small and explicit:

```bash
uv run python run_jupiter_live.py \
  --execution-mode live \
  --wallet-mode local \
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS \
  --live-equity-budget-usd 250 \
  --live-leverage 2 \
  --jup-key live-local
```

## External-Wallet Path

`--wallet-mode external` remains a handoff path, not an auto-submit path.

- The runner can still observe current position state
- The strategy still runs against that position state
- Instead of signing, the runner appends JSONL order requests to `--order-request-path`

If you need a review surface for those requests:

```bash
uv run python external_wallet_bridge.py --request-path <orders.jsonl>
```

## External-Wallet Request Contract

The external-wallet handoff is now a documented schema contract. `run_jupiter_live.py --wallet-mode external` appends one JSON object per line to `--order-request-path`.

Schema version:

- `schema_version: 1`

Top-level fields emitted for each request:

- `schema_version`
- `request_id`
- `timestamp`
- `wallet_mode`
- `wallet_address`
- `status`
- `approval_status`
- `asset`
- `action`
- `side`
- `current_position_usd`
- `target_position_usd`
- `size_delta_usd`
- `position_pubkey`
- `message`
- `command_preview`
- `operator_summary`
- `signer_payload`
- `handoff`

`approval_status` semantics:

- `pending_manual_signature` for actionable planned orders
- `info_only` when the plan is informational and should not produce a signature request

`signer_payload` fields:

- `kind` = `jupiter_perps_order_request`
- `wallet_address`
- `asset`
- `action`
- `side`
- `size_usd`
- `current_position_usd`
- `target_position_usd`
- `collateral_token`
- `collateral_amount`
- `receive_token`
- `leverage`
- `slippage_bps`
- `position_pubkey`
- `command_preview`

`handoff` fields:

- `recommended_surface`
- `board_command`
- `checklist`

Example payload shape:

```json
{
  "schema_version": 1,
  "request_id": "1712102400000::sol::open::long::250.000000",
  "timestamp": 1712102400000,
  "wallet_mode": "external",
  "wallet_address": "<wallet>",
  "status": "planned",
  "approval_status": "pending_manual_signature",
  "asset": "SOL",
  "action": "open",
  "side": "long",
  "current_position_usd": 0.0,
  "target_position_usd": 250.0,
  "size_delta_usd": 250.0,
  "position_pubkey": null,
  "message": "External wallet mode cannot sign in-process...",
  "command_preview": ["jup", "perps", "open", "..."],
  "operator_summary": "Open a LONG SOL perp for 250.00 USD notional using about 125.00 USDC collateral at 2.00x leverage.",
  "signer_payload": {
    "kind": "jupiter_perps_order_request",
    "wallet_address": "<wallet>",
    "asset": "SOL",
    "action": "open",
    "side": "long",
    "size_usd": 250.0,
    "current_position_usd": 0.0,
    "target_position_usd": 250.0,
    "collateral_token": "USDC",
    "collateral_amount": 125.0,
    "receive_token": "USDC",
    "leverage": 2.0,
    "slippage_bps": 200,
    "position_pubkey": null,
    "command_preview": ["jup", "perps", "open", "..."]
  },
  "handoff": {
    "recommended_surface": "jupiter_wallet_kit_or_browser_wallet",
    "board_command": ["uv", "run", "python", "external_wallet_bridge.py", "--request-path", "<orders.jsonl>"],
    "checklist": [
      "Confirm the wallet address matches the operator's intended Jupiter wallet.",
      "Verify the current position and target delta still make sense before signing.",
      "Use the signer payload or command preview to recreate the order in the wallet-controlled surface.",
      "After acting, record approve/reject/submitted status in the approval board."
    ]
  }
}
```

Operator rule: do not change or extend this payload shape without updating this doc and the approval board expectations together.

## Operational Guardrails

- Live mode will not infer account size from defaults. `--live-equity-budget-usd` is mandatory.
- Local-wallet live mode now runs a setup validator before entering the market-data loop.
- The confirmation phrase must match exactly.
- `--jupiter-cli-dry-run` is available for end-to-end order-path testing without broadcast.
- The repo still does not embed a browser wallet signer. That trust boundary remains separate.

## Known Limits

- The live adapter only supports `BTC`, `ETH`, and `SOL`
- The current research feed is not a full perps-native mark-price engine
- Sizing is driven by the explicit strategy budget, not by automatically reading available collateral
- External-wallet mode still requires manual signature / submission

## Source Commands Verified On This Machine

These Jupiter CLI surfaces were checked directly from this Windows host via `npx --yes @jup-ag/cli`:

- `jup --help`
- `jup perps --help`
- `jup perps positions --help`
- `jup perps open --help`
- `jup perps close --help`
- `jup config list -f json`
- `jup keys list -f json`
- `jup perps markets -f json`
