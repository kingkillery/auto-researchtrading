# Integration Execution Checklists - 2026-04-01

This note is the concrete operator follow-through for the three approved integration tracks:

1. Track 1: canonical 5-minute replay or backtest workflow
2. Track 2: Jupiter CLI plus local-wallet live readiness
3. Track 3: external-wallet signer handoff

It replaces the earlier PM-only status snapshot with execution checklists tied to the current repo surfaces.

## Canonical Commands

Hourly validation source of truth:

```bash
uv run backtest.py
```

5-minute validation source of truth:

```bash
uv run python backtest_5m.py --split val --symbols SOL
```

Local-wallet readiness check:

```bash
uv run python run_jupiter_live.py --validate-local-wallet-setup
```

External-wallet review board:

```bash
uv run python external_wallet_bridge.py --request-path <orders.jsonl>
```

## Track 1 - 5-Minute Replay / Backtest Workflow

Current landing state:

- The dedicated runner already exists at `backtest_5m.py`.
- The canonical operator doc is `docs/backtest-5m.md`.
- The current default validation command is `uv run python backtest_5m.py --split val --symbols SOL`.

Data-source contract:

- First choice: Binance public 5-minute OHLCV
- Fallback: Hyperliquid candle API
- Funding overlay: Hyperliquid funding history merged into the 5-minute bars

Comparable output contract:

- Artifact root: `artifacts/backtests_5m/<strategy>_<split>/`
- Required artifacts:
  - `metrics.json`
  - `equity_curve.csv`
  - `trade_log.csv`

Execution checklist:

- Confirm `docs/backtest-5m.md` still matches `backtest_5m.py` flags.
- Use `uv run python backtest_5m.py --split val --symbols SOL` as the default validation command unless the experiment explicitly needs a different symbol set.
- Use `--refresh-data` only when the cache is stale or missing.
- Compare runs using the emitted `metrics.json` and `equity_curve.csv`, not console output alone.
- Keep hourly and 5-minute conclusions separate in docs so unlike-for-like results do not get merged into one narrative.

Track-1 done means:

- one canonical 5-minute command is documented
- one canonical artifact location is documented
- the data-source order is documented
- the workflow is linked from repo operator docs

## Track 2 - Jupiter CLI Plus Local-Wallet Readiness

Current landing state:

- The guarded live path is `uv run python run_jupiter_live.py --execution-mode live --wallet-mode local ...`.
- The canonical operator doc is `docs/jupiter-execution.md`.
- The repo exposes a non-destructive validator through `--validate-local-wallet-setup`.
- Jupiter agent-skill packages are context only; the actual execution surface in this repo remains the CLI-backed `jup` path.

Host-level readiness checklist:

- Confirm either a global `jup` install or working `node` plus `npm` for the `npx --yes @jup-ag/cli` fallback.
- Confirm the intended Jupiter key exists and is selectable.
- Run `uv run python run_jupiter_live.py --validate-local-wallet-setup`.
- Treat exit code `0` plus `ready_for_live_local_wallet: true` as the readiness gate.
- Exercise the live order path with `--jupiter-cli-dry-run` before allowing broadcast.
- Keep the first real live budget small and explicit with `--live-equity-budget-usd`.

Non-destructive validation sequence:

```bash
node --version
npm --version
jup --version
uv run python run_jupiter_live.py --validate-local-wallet-setup
uv run python run_jupiter_live.py --execution-mode live --wallet-mode local --live-confirmation I_UNDERSTAND_JUPITER_LIVE_ORDERS --live-equity-budget-usd 250 --live-leverage 2 --jupiter-cli-dry-run
```

Track-2 done means:

- the target host has passed the repo validator
- the operator checklist matches the current CLI flags
- dry-run exercise succeeded before any broadcast path was used
- docs describe local-wallet signing as a separate trust boundary from external-wallet signing

## Track 3 - External-Wallet Signer Handoff

Current landing state:

- `run_jupiter_live.py --wallet-mode external` emits JSONL requests.
- `external_wallet_bridge.py` provides the review and decision board.
- `docs/jupiter-execution.md` now documents the emitted schema contract.
- Any future JS or TS client adoption, including `@jup-ag/api`, is a separate execution-layer decision and is not implied by agent-skill docs alone.

Schema contract:

- Request file format: JSONL
- Schema version: `1`
- Approval board statuses in play:
  - `pending_manual_signature`
  - `info_only`
  - board decisions: `approved`, `rejected`, `submitted`, `handled`

Execution checklist:

- Start the runner with `--execution-mode live --wallet-mode external --wallet-address <wallet>`.
- If needed, pin `--order-request-path` so the file location is explicit.
- Launch the board with `uv run python external_wallet_bridge.py --request-path <orders.jsonl>`.
- Review `signer_payload`, `operator_summary`, and `handoff.checklist` before acting.
- Record a board decision after every operator action so the queue stays auditable.
- Do not expand the bridge beyond manual review until the signer target surface is chosen.

Implementation boundary:

- The repo currently stops at request emission plus operator review.
- Wallet signing and submission remain outside the completed repo contract.
- Any future wallet-kit or signer bridge must preserve the documented JSONL payload or rev the schema intentionally.

Track-3 done means:

- the request schema is frozen in docs
- the board command is documented
- the trust boundary between repo planning and wallet signing is explicit
- any future signer bridge is built against the documented payload instead of an implicit field grab

## Dependency Order

Recommended merge order remains:

1. Track 2 first
2. Track 3 second
3. Track 1 alongside docs alignment, with no coupling to live signing

Why:

- Track 2 fixes the local-wallet operator baseline.
- Track 3 depends on the live-runner order semantics and request payload remaining stable.
- Track 1 is mostly independent but should continue using the same terminology around paper, live, and explicit operator control.

## Cross-Track Risks

- Multiple validation surfaces can still drift if hourly and 5-minute runs are reported interchangeably.
- The workbench remains dependent on `fly_entrypoint.py` as the single supervision surface.
- Windows portability remains fragile around Unix-oriented validation paths.
- Local-wallet signing and external-wallet signing must remain documented as separate trust boundaries.

## Source Docs

- `docs/agent-harness.md`
- `docs/backtest-5m.md`
- `docs/jupiter-execution.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/CONCERNS.md`
