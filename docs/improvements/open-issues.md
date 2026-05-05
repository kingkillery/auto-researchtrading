# Open Issues

**Repo:** kingkillery/auto-researchtrading  
**Note:** GitHub Issues are disabled on this repo. These are tracked locally.  
**Tagged:** @copilot

---

## Issue #1: ~~Paper feed profile mismatch~~ → RESOLVED (stale info)

**Status:** ✅ FIXED — Feed already running `trend_following` SOL  
**Type:** Operational

### What changed
The paper feed was already switched to `trend_following` on SOL. State file `strategy_Strategy_trend_following.json` exists (361 KB) and is being updated. Warmup completed (500 timestamps / 1,500 bars). Fills are being produced.

### Current status

Latest check, 2026-05-05T00:28:42-06:00:
- **Profile:** `trend_following`
- **Symbols:** `SOL`
- **State file:** Exists
- **Runtime:** Restarted with `uv run python workbench_ctl.py start-paper`
- **Paper PnL:** **-$27.96** (-0.027962%) - negative and not a paper-profit claim

Follow-up, 2026-05-05T00:30:48-06:00:
- **Runtime:** Still running
- **Latest fill:** Opened `SOL` short exposure in paper mode
- **Paper PnL:** **-$29.09** (-0.029094%) marked-to-market with open exposure - negative and not a paper-profit claim

Superseded by leader-aligned run, 2026-05-05T00:33:03-06:00:
- **Profile:** `regime_switching`
- **Symbols:** `BTC ETH SOL`
- **Warmup:** Seeded `500` timestamps / `1500` bars
- **Paper PnL:** **$0.00** before live-feed paper fills - not a paper-profit claim

Leader-aligned fill check, 2026-05-05T00:36:11-06:00:
- **Latest fills:** Opened `BTC` short, `ETH` long, and `SOL` short exposure in paper mode
- **Paper PnL:** **-$6.42** (-0.006415%) marked-to-market with open exposure - negative and not a paper-profit claim

Earlier snapshot:
- **Profile:** `trend_following` ✅
- **Symbols:** `SOL` ✅
- **State file:** Exists and updating ✅
- **Paper PnL:** **-$29.79** (-0.03%) — negative but early in feed

### Remaining work
- [ ] Monitor the leader-aligned feed for live-feed paper fills and sustained net-positive PnL before L5 evidence claim

---

## Issue #2: Time-capped backtests are non-deterministic, making A/B comparison unreliable

**Priority:** Medium  
**Type:** Research infrastructure

### Problem
All backtests hit the 120s `TIME_BUDGET` in `prepare.py`. Scores vary between runs for the same profile:
- Default profile: 15.35 vs 15.53 (same code, different truncation point)
- Trade counts: 2573 vs 2717

This makes it impossible to reliably compare two strategy variants.

### Root cause
`prepare.py` has `TIME_BUDGET = 120` seconds. Backtest loops break when `time.time() - t_start > TIME_BUDGET`. The exact truncation point depends on system load and Python execution timing.

### Fix options
1. **Count-based truncation**: Cap by number of bars instead of wall-clock time
2. **Deterministic budget**: Use a fixed bar index subset for quick validation
3. **Full-horizon for claims**: Mandate `tools/research_full_horizon.py` for any research-grade claim

### Acceptance criteria
- [ ] Two backtest runs of the same code produce identical scores
- [ ] Quick-validation path still completes in < 2 minutes
- [ ] Full-horizon path is documented as the source of truth

---

## Issue #3: BB_COMPRESSION_PERCENTILE=18 was never validated across all profiles

**Priority:** Low  
**Type:** Research

### Problem
The main agent changed `BB_COMPRESSION_PERCENTILE` from 40 to 18 globally. This affected ALL profiles including default, trend_following, mean_reversion, etc. It was reverted to 40 during review, but the 18 value was never rigorously tested.

### Context
- 18 is much stricter than 40 (fewer entries)
- Some profiles (e.g., `compression_breakout`) might benefit from a stricter gate
- Others (e.g., `mean_reversion`) might be starved for entries

### Fix options
1. **Profile-specific override**: Add `bb_compression_percentile` to `_runtime_config()` so each profile can tune it
2. **Grid search**: Run `research_full_horizon.py` with [18, 25, 40, 50] for top 3 profiles

### Acceptance criteria
- [ ] At least 3 profiles tested with 18 vs 40
- [ ] Results documented in `docs/improvements/`

---

## Issue #4: WORKBENCH_PAPER_PROFILE auto-fallback may surprise operators

**Priority:** Low  
**Type:** UX / Safety

### Problem
In `fly_entrypoint.py`:
```python
WORKBENCH_PAPER_PROFILE = os.environ.get(
    "WORKBENCH_PAPER_PROFILE",
    os.environ.get("AUTOTRADER_EXPERIMENT_PROFILE", ""),
).strip().lower()
```

If an operator sets `AUTOTRADER_EXPERIMENT_PROFILE=trend_following` for the experiment manager, the paper feed silently adopts the same profile. This is usually correct but could be surprising if the operator wanted the paper feed on a different profile (e.g., default for multi-asset while experiments run SOL-only).

### Fix options
1. **Log warning**: Print the resolved profile at startup so operators see the coupling
2. **Explicit required**: Fail if `WORKBENCH_PAPER_PROFILE` is not set, forcing explicit choice
3. **Leave as-is**: Document the behavior in `docs/agent-harness.md`

### Acceptance criteria
- [ ] Operator can see which profile the paper feed is using without checking the dashboard

---

## Issue #5: StrategyProbe needs live paper feed integration test

**Priority:** Low  
**Type:** Testing

### Problem
`strategy_probe.py` was extracted from embedded `paper_probe` logic and backtest-validated (score 15.25, 2964 trades). However, it has not been tested in the live paper feed pipeline:
- Warmup → JSONL stream → `engine.step()` → state persistence
- No test for the full `run_jupiter_live.py --execution-mode paper --strategy strategy_probe:StrategyProbe` path

### Acceptance criteria
- [ ] Run live paper feed with `STRATEGY_SPEC=strategy_probe:StrategyProbe`
- [ ] Verify fills are produced within 10 bars
- [ ] Verify state file is written correctly

---

*Generated: 2026-05-04*

---

## Issue #6: ~~Paper feed runs `trend_following` but experiment leader is `regime_switching`~~ -> RESOLVED

**Status:** Fixed by leader-aligned managed paper feed on 2026-05-05T00:33:03-06:00  

**Priority:** Medium  
**Type:** Operational

### Problem
The experiment manager's current leader is `perps-regime-switch` (`regime_switching` profile, multi-asset `BTC ETH SOL`, score 20.44912). The live paper feed is running `trend_following` SOL. There is no auto-sync procedure.

### Root cause
No documented workflow connects the experiment leaderboard to the paper feed configuration. The operator must manually update `WORKBENCH_PAPER_PROFILE` and `WORKBENCH_SYMBOLS` when the leader changes.

### Current status
As of 2026-05-05T00:30:48-06:00, `uv run python workbench_ctl.py status` shows:

- **Paper feed:** running, `trend_following`, `SOL`
- **Experiment leader:** `perps-regime-switch`, `regime_switching`, `BTC ETH SOL`, score `20.44912`

The paper feed is alive again, and the latest managed command is now leader-aligned:

```text
run_jupiter_live.py --execution-mode paper --symbols BTC ETH SOL --state C:\Users\prest\.cache\autotrader\paper\strategy_Strategy_regime_switching.json --paper-warmup-split val --paper-warmup-bars 500
```

Warmup seeded `500` timestamps / `1500` bars. The first leader-aligned live-feed paper fill opened `BTC` short, `ETH` long, and `SOL` short exposure; paper PnL is `-6.42` marked-to-market, so this resolves alignment but does not create a paper-profit claim.

### Fix options
1. **Manual sync**: Update env vars and restart paper feed
2. **Auto-sync**: Enhance workbench to read `experiments-status.json` and auto-restart paper feed on leader change
3. **Multi-feed**: Run multiple paper feeds in parallel (one per top-N experiment)

### Acceptance criteria
- [x] Paper feed profile matches experiment leader OR deviation is explicitly documented
- [x] Symbols align with the leader's manifest

---

## Issue #7: `paper-feed.log` corruption — mixed SOL + stale BTC entries

**Status:** ✅ FIXED  
**Priority:** Medium  
**Type:** Operational / Bug

### Problem
`~/.cache/autotrader/workbench/paper-feed.log` contained mixed output from multiple processes:
- Lines 1–9: Current `trend_following` SOL feed (5-minute bars)
- Lines 10–26: Stale BTC feed (1-minute bars) from a previous run

### Fix applied
- Archived corrupted log to `paper-feed-20260505-001943.log` (26 lines)
- Truncated live log
- No orphaned processes found running
- `fly_entrypoint.py:543` already opens log with `"w"` mode (truncates on restart)

### Future prevention
- `fly_entrypoint.py` already kills existing paper feed before starting new one (WorkbenchSupervisor logic)
- Consider adding timestamped log rotation if mixed-process risk increases

### Acceptance criteria
- [x] Log contains only the current feed process output
- [x] Stale entries are archived, not interleaved

---

## Issue #8: Stale docs claim wrong active profile and symbols

**Status:** ✅ FIXED  
**Priority:** Low  
**Type:** Documentation

### Problem
Multiple docs contained stale or contradictory information about the active paper feed profile and symbols.

### Fix applied
Updated all docs to reflect the current runtime state as of 2026-05-05:
- **Active profile:** `regime_switching`
- **Active symbols:** `BTC ETH SOL`
- **Paper feed PID:** 90920
- **State file:** `strategy_Strategy_regime_switching.json`
- **Experiment leader:** `perps-regime-switch` (score 20.44912)

### Files updated
- `docs/improvements/open-issues.md` (this file)
- `docs/improvements/queue-processing-results.md` — marked historical state table as outdated
- `docs/improvements/review-recent-changes.md` — updated recommendation to reflect regime_switching
- `docs/agent-harness.md` — updated example profile from `trend_following` to `regime_switching`

### Acceptance criteria
- [x] All docs referencing the active paper feed match the actual runtime config
- [x] `paper_profile` and `symbols` are consistent across docs

---

*Updated: 2026-05-04*
