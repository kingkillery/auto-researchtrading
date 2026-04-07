# Jupiter Rapid Execution Command Playbook

Use this file when you need concrete operator commands quickly.

## What the Jupiter notes establish

- Local coding agents should use `CLI + Skills` for action.
- Hosted agents should use docs MCP and, when available, remote MCP execution surfaces.
- Jupiter docs MCP is read-only documentation access.
- The Jupiter CLI is pre-v1 alpha and may change without warning.
- The repo's existing live path is intentionally CLI-backed, explicit, and guarded.
- A repo-owned `jupiter-execution` tool should separate `swap`, `perps`, `lending`, and `multiply` instead of blending them into one generic mutate call.

## Fastest safe sequence on this repo

1. Read current rules:

```powershell
Get-Content docs\jupiter-execution.md
```

2. Check toolchain:

```powershell
node --version
npm --version
jup --version
```

3. Check CLI state:

```powershell
jup config list -f json
jup keys list -f json
jup perps markets -f json
jup perps positions -f json
```

4. Validate local-wallet readiness through the repo:

```powershell
uv run python run_jupiter_live.py --validate-local-wallet-setup
```

5. Rehearse the live runner without broadcast:

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode local `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd 250 `
  --live-leverage 2 `
  --jupiter-cli-dry-run
```

6. Only then use a real broadcast path.

If the validator falls back to `npx` and that path is slow or broken, stop using it as a hot path. Install `@jup-ag/cli` globally, confirm `jup --version`, and rerun the validator before treating the machine as execution-ready.

## Direct CLI examples

### Inspect current positions

```powershell
jup perps positions -f json
```

### Inspect market metadata

```powershell
jup perps markets -f json
```

### Open a long

```powershell
jup perps open --asset SOL --side long --size 250 --amount 125 --input USDC
```

### Open a short

```powershell
jup perps open --asset SOL --side short --size 250 --amount 125 --input USDC
```

### Reduce or close a position

```powershell
jup perps close --asset SOL --side long --size 250 --receive USDC
```

Use `jup perps open --help` and `jup perps close --help` immediately before live use if the command pattern has not been validated in the current CLI version.

Guardrails for direct CLI use:

- only use supported repo assets: `BTC`, `ETH`, `SOL`
- keep notional and leverage explicit
- do not run more than one live operator loop against the same wallet

## Suggested repo-owned tool groups

If we create our own `jupiter-execution` tool surface, organize it like this:

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

Required behavior:

- `swap` returns quote first, then execute
- `perps` returns verify command after mutation
- `lending` distinguishes supply-only deposits from collateral semantics
- `multiply` requires explicit leverage caps, unwind plan, and post-action verification

## Repo-runner examples

### Live local wallet

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode local `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd 250 `
  --live-leverage 2 `
  --jup-key live-local
```

### External wallet handoff

```powershell
uv run python run_jupiter_live.py `
  --execution-mode live `
  --wallet-mode external `
  --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS `
  --live-equity-budget-usd 250 `
  --live-leverage 2 `
  --order-request-path artifacts\orders\live-orders.jsonl
```

Review queue:

```powershell
uv run python external_wallet_bridge.py --request-path artifacts\orders\live-orders.jsonl
```

Use the same file path for generation and review. If the JSONL was copied or edited after generation, discard it and regenerate a clean request file.

## Integration notes from the Jupiter docs

- Swap API base URL: `https://api.jup.ag/swap/v2`
- Most integrations should start with `/order` plus `/execute`
- `/build` is the advanced path for custom transaction control
- All Swap API endpoints require `x-api-key`
- Jupiter docs MCP endpoint: `https://dev.jup.ag/mcp`

## Lending and multiply operator guidance

Treat these as separate classes of action:

- `lending`
  - supply / withdraw only
  - requires APY, liquidity, utilization, and wallet-buffer checks
- `multiply`
  - leveraged earn exposure
  - requires supply APY, borrow APR, net carry, health factor, liquidation distance, and delever plan

Do not describe multiply as simple lending.

For any future repo-owned tool:

- `lending.deposit` should return the asset, amount, expected APY context, and verification step
- `lending.withdraw` should return resulting wallet inventory and verification step
- `multiply.open` should return target leverage, max leverage, carry summary, liquidation metric, and unwind instruction
- `multiply.adjust` should be able to delever without changing the rest of the portfolio plan
- `multiply.close` should be a first-class operation, not an implicit branch of withdraw

## Hard limits that matter here

- This repo's live adapter only supports `BTC`, `ETH`, and `SOL`
- The repo still uses explicit strategy budgets, not auto-read collateral sizing
- External-wallet mode is handoff-only
- Browser wallets are outside the repo trust boundary
- Mutable JSONL handoff files are still a trust gap until the runtime adds checksum or manifest verification
- Lend and multiply surfaces are not implemented in this repo yet; the skill now defines how they should be added without collapsing risk boundaries
