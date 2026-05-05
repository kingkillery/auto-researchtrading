# Open Issues

**Repo:** kingkillery/auto-researchtrading  
**Note:** GitHub Issues are disabled on this repo. These are tracked locally.  
**Tagged:** @copilot

---

## Issue #1: Paper feed runs wrong profile (paper_probe BTC) while winner is trend_following SOL

**Priority:** High  
**Type:** Operational

### Problem
The live paper feed is running `paper_probe` (BTC-only mean-reversion scalper) and producing zero fills. The current winning experiment is `perps-trend-follow` (`trend_following` profile, SOL-only, best score 18.94).

### Root cause
The infrastructure for profile switching exists (`WORKBENCH_PAPER_PROFILE` env var, profile-specific state files), but the live feed hasn't been configured to use the winning profile.

### Fix options
1. **Probe mode**: Launch with `STRATEGY_SPEC=strategy_probe:StrategyProbe` for explicit fill-testing
2. **Winner mode**: Set `WORKBENCH_PAPER_PROFILE=trend_following` and `WORKBENCH_SYMBOLS=SOL` before launching `fly_entrypoint.py`

### Acceptance criteria
- [ ] Paper feed produces fills on the chosen profile
- [ ] State file matches the profile name (e.g. `strategy_Strategy_trend_following.json`)
- [ ] Dashboard shows correct `paper_profile`

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
