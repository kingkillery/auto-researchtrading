# Integration Status - 2026-04-01

This note is a PM coordination snapshot for the three approved follow-ups:

1. 5-minute replay/backtest surface for the VWAP + EMA strategy
2. Jupiter CLI installation/config plus local-wallet live path
3. External-wallet signer flow

## Current State

### Track 1: 5-minute replay/backtest surface

Status: not landed in a dedicated form yet.

What exists now:

- `paper_trade.py` already supports historical replay via `--replay-split`.
- `run_jupiter_live.py` already supports synthetic bar sizing via `--bar-seconds`.

What is still missing for this track to count as complete:

- a clear 5-minute-specific replay/backtest entrypoint or documented workflow
- an agreed data source for 5-minute bars
- validation output that is comparable run to run

### Track 2: Jupiter CLI plus local-wallet live path

Status: code path is present and operator-guarded, but host-level CLI installation/config still needs explicit operator verification.

Current landing zone:

- `jupiter_execution.py` contains the CLI-backed execution model and live-order planning
- `run_jupiter_live.py` exposes `--execution-mode live`, `--wallet-mode local`, and the live confirmation guard
- `docs/jupiter-execution.md` documents the local-wallet path

Known dependency:

- the external `jup` CLI must be installed, configured, and funded outside the repo

### Track 3: external-wallet signer flow

Status: partial landing.

What exists now:

- `run_jupiter_live.py --wallet-mode external` emits JSONL order requests
- `external_wallet_bridge.py` provides a lightweight review/ack board for those requests

What is still missing for this track to count as complete:

- actual wallet signing/submission
- a browser or frontend signer bridge tied to Jupiter Wallet Kit or equivalent
- a stable schema contract for the emitted request payloads

## Dependency Order

Recommended merge order:

1. Track 2 first
2. Track 3 second
3. Track 1 independently, but align its operator docs with the final live-runner contract

Reasoning:

- Track 3 depends on the request schema and target-position semantics coming out of `jupiter_execution.py` and `run_jupiter_live.py`.
- If Track 2 changes plan serialization late, Track 3 will drift.
- Track 1 is mostly independent, but any operator docs should reference the final CLI flags and bar-sizing contract already exposed by `run_jupiter_live.py`.

## Sequencing Risks

- Schema drift: `external_wallet_bridge.py` currently renders whatever JSONL fields the live runner emits. Any rename in request payload fields can silently break the board.
- Timeframe mismatch: the strategy idea is 5-minute-native, but the fixed harness remains backtest-first and historically oriented. A replay surface that still reads hourly data does not solve the validation gap.
- Operator confusion: `paper_trade.py` replay, `run_jupiter_live.py --execution-mode paper`, and `run_jupiter_live.py --execution-mode live` are three different surfaces. Docs should keep them distinct.
- Wallet trust boundary: local CLI signing and external browser-wallet signing are different security models. Do not blur them in one path.

## Merge Notes

- Do not rework `strategy.py` as part of integration.
- Do not modify `prepare.py`, `backtest.py`, or `benchmarks/`.
- Keep any new signer UI or browser bridge isolated from the CLI-backed execution core.
- Before merging Track 3, freeze the JSONL request schema in docs and add a sample payload.
- Before calling Track 2 complete, verify `jup` installation and a non-destructive account read such as help/version/positions on the target host.
- Before calling Track 1 complete, publish one canonical command for 5-minute replay/backtest and one canonical output artifact.

## Files Currently Relevant To Integration

- `paper_trade.py`
- `run_jupiter_live.py`
- `jupiter_execution.py`
- `external_wallet_bridge.py`
- `docs/agent-harness.md`
- `docs/jupiter-execution.md`

## Follow-Up Needed

- Track 1 owner: land the dedicated 5-minute workflow and document the exact command.
- Track 2 owner: finish CLI install/config validation on the real host and capture the operator checklist.
- Track 3 owner: replace or augment the manual board with an actual signer handoff, then lock the request schema.
