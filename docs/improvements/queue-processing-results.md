# Queue Processing Results — Main Agent Takeover

**Date:** 2026-05-04  
**Processed by:** sub-agent → main agent handoff

---

## Task 1: inspect README.md

**Result:** Standard Nunchi project README. Key facts:
- 103 autonomous experiments completed
- Claims Sharpe 21.4, 0.3% max drawdown
- `uv run prepare.py` for data, `uv run backtest.py` for validation
- No API keys required (public CryptoCompare + Hyperliquid APIs)

---

## Task 2: Count experiment profiles in strategy.py

**Result:** 10 profiles defined in `_profile_signal_plan()`:
1. `trend_following`
2. `mean_reversion`
3. `regime_switching`
4. `carry_aware_exits`
5. `impact_aware_sizing`
6. `liquidation_buffer`
7. `limit_pullback`
8. `relative_strength_rotation`
9. `compression_breakout`
10. `failure_reversal`

Plus `DEFAULT_EXPERIMENT_PROFILE = "default"` (fallback to trend_bull/trend_bear ensemble).

**No paper_probe** — successfully removed during earlier cleanup.

---

## Task 3: Cross-reference profiles across files

**Result:** Perfect alignment. No orphans.

| Profile | strategy.py | experiment_manager.py | backtest.py | manifest |
|---------|-------------|----------------------|-------------|----------|
| All 10 | ✅ | ✅ (search_space) | ✅ (indirect via env var) | ✅ |

- **strategy.py → experiment_manager.py**: None missing.
- **experiment_manager.py → strategy.py**: None extra.
- Benchmark modules (`benchmarks.mean_reversion`, etc.) are separate from experiment profiles.

---

## Task 4: Search for `getout_mode` references

**Result:** NOT fully dead.

Found in:
- `tools/evaluate_getout_mode.py` — **Active tool** that temporarily overrides `prepare.INITIAL_CAPITAL` per run
- `docs/improvements/subagent-watcher-log.md` — Log reference
- `docs/improvements/profitability-evidence-loop/README.md` — Doc reference
- `docs/improvements/subagent-command-queue.md` — Queue reference

**Verdict:** `getout_mode` was removed from `strategy.py` (correct), but `tools/evaluate_getout_mode.py` still exists as a standalone research tool. It is intentionally preserved for manual capital-sensitivity studies, not invoked by the main harness.

---

## Task 5: Audit trend_following paper launch

**Result:** Significant findings. See detailed audit below.

### Current State (as of 2026-05-05 00:10 local) — HISTORICAL

> ⚠️ **Outdated:** The paper feed was later switched to `regime_switching` on `BTC ETH SOL` to align with the experiment leader (see Issue #6).

| Item | Expected / Documented | Actual / Runtime (at time of audit) |
|------|----------------------|------------------|
| **Profile** | `trend_following` | `trend_following` ✅ |
| **Symbols** | `BTC ETH SOL` (per docs) | `SOL` only ⚠️ |
| **State file** | `strategy_Strategy_trend_following.json` | Exists (361 KB) ✅ |
| **Warmup** | 500 timestamps / 1,500 bars | Completed ✅ |
| **Paper PnL** | Net positive for L5 claim | **-$29.79** (negative) ❌ |
| **Experiment leader** | `trend_following` (per open-issues.md) | `regime_switching` (score 20.45) ⚠️ |
| **Log integrity** | Single feed, clean output | Mixed SOL + stale BTC ❌ |

### Critical Finding: Issue #1 is STALE

`docs/improvements/open-issues.md` Issue #1 claims:
> "The live paper feed is running `paper_probe` (BTC-only mean-reversion scalper) and producing zero fills."

**Reality:** The paper feed was already switched to `trend_following` SOL. It is producing fills. The state file exists and is being updated. Issue #1 is **outdated**.

### Remaining evidence gates (from `docs/improvements/profitability-evidence-loop/`)

1. **Net-positive paper PnL** over meaningful bar count (currently negative)
2. **Reproducible reconciliation** via `tools/paper_wallet_report.py`
3. **Sufficient observation window** to rule out noise
4. **L5/L6 completion** per deterministic wrapper contract

### Stale docs / mismatches found

1. **`docs/improvements/open-issues.md` Issue #1** — Stale (paper feed already switched)
2. **`docs/improvements/profitability-evidence-loop/README.md`** — Claims active profile is `liquidation_buffer` (line 97, 129), but runtime is `trend_following`
3. **`docs/agent-harness.md`** — Describes `trend_following` relaunch as using `BTC ETH SOL`, but runtime uses `SOL` only
4. **Experiment leader vs paper feed** — Leader is `regime_switching` (score 20.45), paper feed is `trend_following`. No auto-sync procedure exists.
5. **`paper-feed.log` corruption** — Contains mixed SOL (current) + stale BTC (previous run) entries. Orphaned process handles appended after truncation.

---

## Actions Taken

- [x] All 5 queue tasks executed
- [x] Queue cleared and archived to `subagent-command-queue-processed.md`
- [ ] `open-issues.md` Issue #1 needs update (stale)
- [ ] `profitability-evidence-loop/README.md` needs correction
- [ ] `paper-feed.log` needs cleanup / truncation guard


---

## Full-Horizon Backtest Results — regime_switching (2026-05-05)

**Command:** `uv run python tools/research_full_horizon.py --split val --profile regime_switching`
**Status:** Completed (exit code 0)
**Coverage:** 100.00% (6,552 / 6,552 bars)
**Backtest time:** ~295 seconds

### Leaderboard

| Rank | Strategy | Score | Return% | Trades | WinRate% | ProfitFactor | MaxDD% | Status |
|------|----------|-------|---------|--------|----------|--------------|--------|--------|
| 1 | **current_strategy (regime_switching)** | **14.133141** | **79.68%** | 6,469 | 74.48 | 7.96 | 1.22 | ✅ full-horizon |
| 2 | funding_arb | -0.128636 | -0.62% | 879 | — | — | — | full-horizon |
| 3 | regime_mm | -0.320249 | -3.12% | 12,858 | — | — | — | full-horizon |
| 4 | mean_reversion | -3.967560 | -26.17% | 3,185 | — | — | — | full-horizon |
| 5 | avellaneda_mm | -999.000000 | 0.00% | 0 | — | — | — | full-horizon |
| 6 | momentum_breakout | -999.000000 | 0.00% | 0 | — | — | — | full-horizon |

### Cost Stress Test

| Cost Multiplier | Fee Rate | Slippage (bps) | Score | Return% | WinRate% | Profit Factor |
|-----------------|----------|----------------|-------|---------|----------|---------------|
| 1x (default) | 0.05% | 1.0 | 14.133141 | 79.68% | 74.48% | 7.96 |
| 2x | 0.10% | 2.0 | 10.930968 | 56.70% | 73.37% | 7.52 |
| 3x | 0.15% | 5.0 | 6.865714 | 32.40% | 70.19% | 6.34 |

### Verdict

- **Beats all benchmarks** by a wide margin ✅
- **Survives 3x cost stress** with positive score (6.87) and 32% return ✅
- **Drawdown is controlled** at 1.22% ✅
- **Full-horizon score (14.13)** is lower than time-capped experiment score (~20.45) because 120s truncation covered only the most favorable portion of the data ⚠️
- **Research-grade claim:** This is L4 evidence (backtest on validation data, full horizon). L5 requires live paper PnL.

### Comparison: Time-Capped vs Full-Horizon

| Metric | Time-Capped (120s) | Full-Horizon | Delta |
|--------|-------------------|--------------|-------|
| Score | ~20.45 | 14.13 | -31% |
| Return% | ~2.35% | 79.68% | +33x |
| Trades | ~1,753 | 6,469 | +3.7x |
| Coverage | ~27% | 100% | +73pp |

**Key insight:** Time-capped backtests dramatically understate return because they truncate before the strategy compounds. The score is inflated by selection bias (favorable early data), but the true score on full data is 14.13 — still strong.

### Artifacts

- `artifacts/research_full_horizon/summary.json`
- `artifacts/research_full_horizon/leaderboard.csv`
- `artifacts/research_full_horizon/cost_stress.csv`
