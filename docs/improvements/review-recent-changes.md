# Review: Recent Changes (All Uncommitted)

**Date:** 2026-05-04
**Reviewer:** sub-agent (post-compaction)
**Scope:** All modifications since last commit

---

## 1. Overview

Two waves of changes are in the working tree:

1. **Main agent changes** (5 core files + docs): Paper warmup infrastructure, profiled state paths, env var plumbing, documentation updates.
2. **Sub-agent fixes** (strategy.py cleanup + strategy_probe.py): Removed embedded probe logic, fixed peak_equity, reverted BB_COMPRESSION_PERCENTILE, extracted standalone probe strategy.

---

## 2. File-by-File Review

### 2.1 `strategy.py` — MIXED, now CLEAN

**Status after sub-agent fixes:** Clean. All paper_probe code removed.

**What remains from main agent:**
- `_runtime_config()` — Good pattern. Centralizes per-profile overrides.
- `min_entry_notional` filtering on entries and flips — Good safety addition.
- Use of `active_symbols`, `symbol_weights`, `base_position_pct`, `cooldown_bars` from runtime config instead of module constants — Good configurability improvement.
- Removed walrus operators (`:=`) and unused intermediate variables (`mom_bull`, `rsi_bull`, etc.) — Reduces noise.
- Docstring updated from experiment notes to proper module documentation — Better.

**Sub-agent fixes applied:**
- `peak_equity = INITIAL_CAPITAL` (was `0.0`) — Fixes drawdown understatement.
- `BB_COMPRESSION_PERCENTILE = 40` (was `18`) — Reverts global change that affected all profiles.
- All `paper_probe` branches removed — Restores single-strategy-surface principle.

**Verdict:** ✅ Clean and safe after fixes.

---

### 2.2 `fly_entrypoint.py` — MOSTLY GOOD

**Additions:**
- `resolve_state_path()` — Creates profile-specific state files (e.g., `strategy_Strategy_trend_following.json`). Prevents collision between experiments running different profiles. Well-designed with safe char filtering.
- `WORKBENCH_SYMBOLS` default changed from `"SOL"` to `"BTC ETH SOL"` — Matches the default strategy's active symbols.
- `WORKBENCH_PAPER_PROFILE`, `WORKBENCH_PAPER_WARMUP_SPLIT`, `WORKBENCH_PAPER_WARMUP_BARS` env vars — Clean env-driven configuration.
- `ManagedProcess.env_overrides` — Allows passing `AUTOTRADER_EXPERIMENT_PROFILE` to the paper feed subprocess. Good abstraction.
- Paper command builder now appends `--reset-state`, `--paper-warmup-split`, `--paper-warmup-bars` args.
- Dashboard payload includes `paper_profile` and `paper_warmup_split` — Better observability.

**Concerns:**
- `STATE_PATH` resolution moved from module-level constant to a `resolve_state_path()` function called at import time. This is functionally equivalent but slightly more complex. The function reads `WORKBENCH_PAPER_PROFILE` which is set at import time — safe.
- `WORKBENCH_PAPER_PROFILE` falls back to `AUTOTRADER_EXPERIMENT_PROFILE`. This coupling means the workbench paper feed automatically adopts the experiment profile. This is fine for most cases but could surprise an operator who wants the paper feed on a different profile than the experiment manager.

**Verdict:** ✅ Good additions. One minor concern about automatic profile coupling.

---

### 2.3 `paper_engine.py` — GOOD

**Addition:**
- `seed_history(snapshot)` — Warms up indicator state without executing trades. Updates `timestamp`, `equity`, and saves state. Returns count of symbols seeded.

**Design note:** Intentionally does NOT call `strategy.on_bar()` — correct. Warmup is for engine state only, not strategy signals.

**Verdict:** ✅ Clean, minimal, correct.

---

### 2.4 `paper_trade.py` — GOOD

**Addition:**
- `snapshot_from_rows(rows, timestamp=None)` — Optional timestamp parameter injects timestamp into each symbol's payload if missing.
- `run_replay()` passes `timestamp` through.

**Use case:** Ensures historical bars have timestamps when building snapshots for warmup or replay.

**Verdict:** ✅ Clean, backward-compatible.

---

### 2.5 `run_jupiter_live.py` — GOOD

**Additions:**
- `warmup_paper_history(engine, split, symbols, limit)` — Loads cached historical data, iterates timestamps, builds snapshots, calls `engine.seed_history()`.
- CLI args: `--paper-warmup-split` (choices: train/val/test), `--paper-warmup-bars` (default 500).
- Warmup metadata returned as JSON including `seeded_timestamps`, `seeded_bars`, `latest_timestamp`, `state_path`.
- Handles duplicate timestamps safely (`row.iloc[0]`).
- Empty data guard: returns early with zeros if no matching symbols.

**Verdict:** ✅ Well-implemented. Good edge-case handling.

---

### 2.6 `strategy_probe.py` — GOOD (new file)

**Purpose:** Standalone probe strategy extracted from embedded `paper_probe` logic.

**Design:**
- Simple `StrategyProbe` class with `on_bar()` interface.
- BTC-only, mean-reversion scalper.
- Checks bar cadence regularity (gap <= 300s).
- Hard stop at -0.15%, take profit at 0.12%.
- ATR trailing stop with 1.0x multiplier.
- Documented explicitly as NOT a research candidate.

**Verdict:** ✅ Clean extraction. Solves the "second strategy disguised as profile" problem.

---

### 2.7 `tests/test_paper_warmup.py` — GOOD (new file, untracked)

**What it tests:**
- `warmup_paper_history()` seeds history without calling `strategy.on_bar()` — uses `_NoopStrategy` that raises if `on_bar` is called.
- Verifies `history_buffers` are populated, positions remain empty, cash unchanged.
- Verifies state file is written.

**Verdict:** ✅ Good contract test. Should be added to the test suite.

---

### 2.8 `docs/agent-harness.md` — GOOD

**Additions:**
- Explicit profit rule: "Profit is real only when net money is realized in a controlled wallet..."
- Documented `tools/research_full_horizon.py` for research-grade claims.
- Documented `--paper-warmup-split` and `--paper-warmup-bars` flags.
- Documented `tools/paper_wallet_report.py` with proper `paper trading profit` scoping.
- Documented `WORKBENCH_SYMBOLS`, `WORKBENCH_PAPER_PROFILE`, `WORKBENCH_PAPER_WARMUP_SPLIT`, `WORKBENCH_PAPER_WARMUP_BARS`.
- Documented `RESET_STATE=1` behavior.
- Added validation step: "For profitability-improvement claims, run `tools/research_full_horizon.py`..."

**Verdict:** ✅ Excellent doc updates. The profit-rule paragraph is critical.

---

### 2.9 `docs/fly-runtime-manifest.json` — MINOR

- Added `docs/trade_postmortems.md` to optional files list.

**Verdict:** ✅ Trivial, correct.

---

### 2.10 `docs/trade_postmortems.md` — MINOR

- Added duplicate save regression test entry (2026-04-07).

**Verdict:** ✅ Trivial.

---

## 3. Cross-Cutting Concerns

### 3.1 Profile Mismatch Still Exists

The live paper feed configuration hasn't been updated to use the winning `trend_following` profile. The infrastructure now supports it (`WORKBENCH_PAPER_PROFILE`), but no one has flipped the switch.

**To fix:** Set `WORKBENCH_PAPER_PROFILE=trend_following` and `WORKBENCH_SYMBOLS=SOL` for the live paper feed, or launch `run_jupiter_live.py` with `--strategy strategy:Strategy` and `AUTOTRADER_EXPERIMENT_PROFILE=trend_following`.

### 3.2 Time-Capped Backtests

All backtests hit the 120s `TIME_BUDGET`. Scores vary between runs (15.35 vs 15.53 for default profile) because truncation points differ slightly. Research-grade claims still require `tools/research_full_horizon.py`.

### 3.3 `BB_COMPRESSION_PERCENTILE` Reverted

Main agent changed it from 40 → 18 globally. Sub-agent reverted to 40. The 18 value was never validated across profiles. If compression breakout research wants to test 18, it should be a `_profile_signal_plan` override, not a global constant.

---

## 4. Verdict

| File | Verdict | Notes |
|------|---------|-------|
| `strategy.py` | ✅ Clean | After sub-agent fixes |
| `fly_entrypoint.py` | ✅ Good | Profile coupling is minor |
| `paper_engine.py` | ✅ Good | Minimal, correct |
| `paper_trade.py` | ✅ Good | Backward-compatible |
| `run_jupiter_live.py` | ✅ Good | Well-implemented warmup |
| `strategy_probe.py` | ✅ Good | Clean extraction |
| `test_paper_warmup.py` | ✅ Good | Good contract test |
| `docs/agent-harness.md` | ✅ Excellent | Profit rule is critical |
| `docs/fly-runtime-manifest.json` | ✅ Trivial | |
| `docs/trade_postmortems.md` | ✅ Trivial | |

**Overall:** The changes are safe to commit. The main agent's warmup infrastructure is well-designed. The sub-agent's cleanup restores strategy.py to a single mutable surface. The only remaining operational issue is the paper feed profile mismatch, which is a configuration change, not a code change.
