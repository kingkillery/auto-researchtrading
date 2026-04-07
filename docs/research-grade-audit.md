# Research Grade Audit

Last initialized: 2026-04-04

## Task Understanding
- task type: `qa` / audit initialization
- goal: establish a research-grade audit surface for the current Auto-Research strategy and compare it against recent empirical research
- success condition: one durable audit artifact exists with scope, evidence lanes, current baseline evidence, and falsifiable next-step hypotheses
- assumptions:
  - current strategy under audit is the implementation in [strategy.py](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py)
  - this audit is about research quality and empirical credibility, not only code quality
  - no code changes are part of initialization
- primary artifact type: docs + evidence log

## Repo Calibration
- system shape: backtest-first trading research harness with one mutable strategy surface and operator workbench overlays
- execution model: bar-close event loop over hourly data, offline backtesting, optional paper/live orchestration
- correctness surfaces:
  - [strategy.py](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py)
  - [backtest.py](/C:/Dev/Desktop-Projects/Auto-Research-Trading/backtest.py)
  - [prepare.py](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py)
  - [README.md](/C:/Dev/Desktop-Projects/Auto-Research-Trading/README.md)
  - [docs/sol-baseline-strategy-v1.md](/C:/Dev/Desktop-Projects/Auto-Research-Trading/docs/sol-baseline-strategy-v1.md)
- risk profile:
  - semantic overfit from repeated search over a short fixed validation window
  - mismatch between documented baseline contract and live implementation
  - inflated performance from tail-sensitive scoring and repeated experiment selection
  - understated execution and market-structure risk relative to empirical papers
- acceptance artifacts:
  - reproducible backtest results
  - documented strategy-to-baseline comparison
  - literature-backed claims with links
  - explicit VERIFIED / INFERRED / UNKNOWN separation

## Adapted Certificate Plan
- mode: `qa`
- target behavior or contract:
  - audit whether the current strategy is empirically credible relative to recent research
  - identify where it aligns with or departs from the repo's own baseline contract
- relevant code surface:
  - indicator and signal design in [strategy.py:15](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L15C1)
  - profile-specific vote logic in [strategy.py:93](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L93C1)
  - runtime sizing and exits in [strategy.py:310](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L310C1)
- prompt / metadata surface:
  - baseline spec in [docs/sol-baseline-strategy-v1.md:61](/C:/Dev/Desktop-Projects/Auto-Research-Trading/docs/sol-baseline-strategy-v1.md#L61C1)
  - scoring and benchmark claims in [README.md:160](/C:/Dev/Desktop-Projects/Auto-Research-Trading/README.md#L160C1)
- repo-specific invariants:
  - `strategy.py` is the only intended mutable strategy surface
  - baseline v1 says trade `SOL` only and use `BTC` / `ETH` only as context
  - no claims should outrun the evidence produced by the current harness
- acceptance artifacts to trust:
  - direct code inspection
  - direct backtest output from current workspace
  - primary-source papers and journal articles
- counterexample definition:
  - a claim of robustness is not credible if it depends on one short validation window, repeated search, or metrics materially outside realistic empirical ranges without additional falsification
- system-specific tables required:
  - implementation vs baseline contract
  - implementation vs empirical literature
  - audit backlog with severity and expected payoff

## Findings
### Verified
- The current implementation trades all three symbols, not `SOL` only, via `ACTIVE_SYMBOLS = ["BTC", "ETH", "SOL"]` in [strategy.py:15](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L15C1).
- The current implementation is a six-signal vote system using short/medium returns, EMA state, RSI, MACD histogram, and Bollinger-band width compression in [strategy.py:117](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L117C1).
- Dynamic thresholding is volatility-aware through `dyn_threshold`, scaled from realized volatility, in [strategy.py:351](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L351C1).
- The default strategy uses ATR trailing exits, cooldowns, and reversal logic in [strategy.py:404](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L404C1).
- The baseline spec says the first baseline should trade `SOL` only and use `BTC` and `ETH` only as context in [docs/sol-baseline-strategy-v1.md:63](/C:/Dev/Desktop-Projects/Auto-Research-Trading/docs/sol-baseline-strategy-v1.md#L63C1).
- The README scoring formula rewards Sharpe strongly once trade count exceeds 50, then adds only relatively mild drawdown and turnover penalties in [README.md:165](/C:/Dev/Desktop-Projects/Auto-Research-Trading/README.md#L165C1).
- Current local backtest output on 2026-04-04 was:
  - `score: 16.094431`
  - `total_return_pct: 44.668793`
  - `max_drawdown_pct: 0.377241`
  - `num_trades: 5189`
  - the harness timed out at ~120 seconds after printing results
- A direct read-only backtest script run on 2026-04-04 produced materially different metrics:
  - `score: 16.800871`
  - `total_return_pct: 73.096384`
  - `max_drawdown_pct: 0.377241`
  - `num_trades: 6821`
- The difference above is consistent with a reproducibility risk in the harness because [prepare.py:27](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py#L27C1) sets `TIME_BUDGET = 120` and [prepare.py:333](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py#L333C1) breaks the simulation loop on wall-clock elapsed time.
- Under the direct read-only run, symbol-level realized close PnL was:
  - `BTC`: `22,718.51`
  - `ETH`: `28,821.36`
  - `SOL`: `44,409.82`
- In the same run, close-PnL share was approximately:
  - `BTC`: `23.68%`
  - `ETH`: `30.04%`
  - `SOL`: `46.28%`
- Cost stress using the fixed harness with monkeypatched fees/slippage degraded the score materially:
  - default costs (`5 bps` taker, `1 bp` slippage): `16.8009`
  - stress x2 (`10 bps` taker, `2 bps` slippage): `12.0961`
  - stress x3 (`15 bps` taker, `5 bps` slippage): `6.4344`
- Relative to default costs, score degradation was:
  - stress x2: `-28.0%`
  - stress x3: `-61.7%`

### Inferred
- The current strategy has drifted from the documented `SOL_H1_COMPRESSION_BREAKOUT_V1` baseline into a broader multi-asset experimentation surface.
- The strategy family is closest to nonlinear trend/compression breakout with volatility-aware risk management, not to carry or market-making as primary edge sources.
- The repo's headline performance claims are likely optimistic relative to empirical literature because the validation window is short and the strategy has been repeatedly optimized on it.
- The current edge is not primarily a SOL-only effect. SOL is the largest contributor in the observed run, but BTC and ETH together contribute more than half of realized close PnL.
- Research-grade reproducibility is currently weakened by wall-clock-dependent backtest truncation, not just by search overfit.

### Unknown
- Whether the current edge survives a fresh holdout period not touched by the 103-experiment search loop.
- Whether the high reported Sharpe remains after stronger stress tests on fees, slippage, and execution latency.
- Whether profits are concentrated in one symbol, one regime, or a few outlier intervals.
- Whether strategy quality survives simplification back toward the documented SOL-only baseline.

## Certificate

### Premises
- P1: research-grade claims must be judged against recent empirical literature, not only internal backtests
- P2: repeated autonomous strategy search over one validation window raises data-snooping risk
- P3: crypto momentum evidence exists, but recent papers report much lower robust Sharpe than the repo headline metrics
- P4: implementation-to-spec drift matters because it changes what is actually being evaluated

### Trace Table
| Function/Stage/Artifact | File:Line | Inputs | Output/State Change | Verified Behavior | Why It Matters |
|---|---|---|---|---|---|
| universe selection | [strategy.py:15](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L15C1) | static constants | active tradable symbols | trades BTC, ETH, SOL | directly conflicts with SOL-only baseline |
| signal vote construction | [strategy.py:117](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L117C1) | returns, EMA, RSI, MACD, BB compression | bull/bear vote counts | nonlinear ensemble logic | closest empirical comparison is nonlinear momentum |
| threshold adaptation | [strategy.py:351](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L351C1) | realized volatility | dynamic threshold | volatility-aware entry strictness | relevant to volatility-managed momentum literature |
| exit and reversal logic | [strategy.py:404](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L404C1) | profile plan, ATR, RSI, current position | target positions and risk exits | uses trailing ATR stops and reversal | major source of reported drawdown suppression |
| baseline contract | [docs/sol-baseline-strategy-v1.md:63](/C:/Dev/Desktop-Projects/Auto-Research-Trading/docs/sol-baseline-strategy-v1.md#L63C1) | strategy intent | SOL-only spec | single-instrument baseline | defines what should count as faithful baseline research |
| score design | [README.md:165](/C:/Dev/Desktop-Projects/Auto-Research-Trading/README.md#L165C1) | returns, trade count, drawdown, turnover | final score | mostly Sharpe-driven once trade hurdle passed | affects selection pressure during autonomous search |

### Data / State Flow
| Value/Object/State | Origin | Modified At | Read At | Constraints | Risk |
|---|---|---|---|---|---|
| active universe | static config | [strategy.py:15](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L15C1) | [strategy.py:341](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L341C1) | should match documented strategy scope | scope drift |
| realized volatility | close history | [strategy.py:262](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L262C1) | [strategy.py:351](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L351C1) | lookback-sensitive | overfit through threshold tuning |
| BB compression percentile | close history | [strategy.py:291](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L291C1) | [strategy.py:379](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py#L379C1) | current implementation uses short lookback proxy | may not match intended compression regime definition |
| performance claims | README experiment log | [README.md:194](/C:/Dev/Desktop-Projects/Auto-Research-Trading/README.md#L194C1) | user-facing positioning | should be reproducible and robust | claim inflation |

### Alternative Hypotheses
1. Hypothesis: the strategy is genuinely exceptional and substantially better than recent crypto momentum research.
   - supporting evidence:
     - current local backtest score is still very high
     - logic includes risk management and nonlinear signal interaction
   - contradicting evidence:
     - recent empirical papers on realistic crypto momentum report much lower robust Sharpe
     - current research process appears highly exposed to repeated-search bias
   - status: not accepted
2. Hypothesis: the strategy contains a real but smaller edge, and the headline metrics mainly reflect over-optimization to the validation window.
   - supporting evidence:
     - signals are plausible and literature-consistent
     - reported Sharpe is far above empirical priors
     - repeated autonomous iteration on fixed data is visible in repo narrative
   - contradicting evidence:
     - no fresh holdout has been tested yet in this audit
   - status: leading hypothesis

### Divergence / Counterexample Check
- opposite answer would require:
  - fresh holdout evidence
  - stress-tested transaction cost robustness
  - regime-by-regime and symbol-by-symbol decomposition showing no dependency on isolated outliers
- evidence found:
  - only one current workspace backtest and historical repo claims
- divergence point:
  - research-grade robustness claim fails at external validation and anti-data-snooping standards
- counterexample:
  - if a fresh untouched period or stricter fee model collapses Sharpe toward normal crypto momentum ranges, the current headline interpretation is false

## Literature Anchors
- Han, Kang, Ryu, "Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions" (2024): realistic crypto momentum evidence exists, but robust Sharpe is much lower and tail/liquidation risk is central. https://ssrn.com/abstract=4675565
- Grobys, "Cryptocurrency momentum has (not) its moments" (2025): volatility management improves crypto momentum payoffs, but tail risk remains extreme. https://link.springer.com/article/10.1007/s11408-025-00474-9
- John, Li, Liu, "Sentiment in the Cross Section of Cryptocurrency Returns" (2024/2025): sentiment is a priced factor and improves explanatory power beyond basic factor sets. https://ssrn.com/abstract=4941032
- Bianchi, Babiak, Dickerson, "Trading volume and liquidity provision in cryptocurrency markets" (2022): return-volume interaction contains predictive information, especially in lower-activity settings. https://www.sciencedirect.com/science/article/abs/pii/S0378426622001418
- Moskowitz, Sabbatucci, Tamoni, Uhl, "Nonlinear Time Series Momentum" (2025): nonlinear trend rules can outperform simple linear momentum. https://ssrn.com/abstract=5933974

## Audit Backlog
| Priority | Question | Why It Matters | Evidence Needed |
|---|---|---|---|
| P0 | Does the current strategy survive a fresh holdout? | core anti-overfit test | untouched period backtest |
| P0 | Can the backtest be made deterministic enough for research claims? | current loop is wall-clock bounded | deterministic completion or processed-bar normalization |
| P1 | How much of performance comes from BTC/ETH trading vs SOL? | spec drift and edge attribution | deeper symbol-level PnL decomposition |
| P1 | How sensitive is Sharpe to higher fees/slippage? | practical tradability | extended fee and slippage stress matrix |
| P1 | Are returns concentrated in a few outlier windows? | tail dependence | regime and outlier decomposition |
| P1 | Does a simpler SOL-only variant retain most of the edge? | research hygiene and interpretability | baseline-faithful ablation |
| P1 | Does volume improve entry quality empirically here? | literature-guided enhancement test | volume-conditioned ablation |
| P2 | Do sentiment or macro filters add anything incremental? | frontier comparison | incremental factor test |

## Falsification Pass 1

### Scope

First pass was constrained to read-only execution. No source files in the trading harness were modified.

Questions tested:

1. Is the current edge actually SOL-only?
2. Does the edge remain strong under harsher transaction-cost assumptions?
3. Are the reported metrics stable enough to support research-grade claims?

### Method

- Loaded validation data through the fixed harness.
- Ran `prepare.run_backtest(Strategy(), data)` directly with the current [strategy.py](/C:/Dev/Desktop-Projects/Auto-Research-Trading/strategy.py).
- Extracted per-symbol trade event counts, turnover, and realized close PnL from `BacktestResult.trade_log`.
- Re-ran the same strategy under two harsher cost scenarios by monkeypatching [prepare.py:29](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py#L29C1) to [prepare.py:31](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py#L31C1) at runtime:
  - stress x2: `10 bps` taker fee and `2 bps` slippage
  - stress x3: `15 bps` taker fee and `5 bps` slippage

### Results

| Scenario | Taker Fee | Slippage | Score | Return % | Max DD % | Trades |
|---|---:|---:|---:|---:|---:|---:|
| default | 5 bps | 1 bp | 16.8009 | 73.10 | 0.377 | 6821 |
| stress x2 | 10 bps | 2 bps | 12.0961 | 36.02 | 0.409 | 5729 |
| stress x3 | 15 bps | 5 bps | 6.4344 | 17.39 | 0.632 | 5644 |

| Symbol | Trade Events | Turnover Notional | Realized Close PnL | Share of Close PnL |
|---|---:|---:|---:|---:|
| BTC | 2158 | 10,089,957 | 22,718.51 | 23.68% |
| ETH | 2321 | 11,101,162 | 28,821.36 | 30.04% |
| SOL | 2342 | 11,494,035 | 44,409.82 | 46.28% |

### Pass 1 Verdict

- Falsified: "this is effectively a SOL-only baseline strategy." It is not. BTC and ETH are economically meaningful contributors.
- Partially falsified: "the edge is robust to reasonable implementation frictions." It remains positive under harsher costs, but the score falls sharply, especially in the x3 scenario.
- Strengthened concern: research claims are currently reproducibility-sensitive because the backtest loop is explicitly wall-clock bounded.

## Falsification Pass 2

### Scope

Pass 2 tested whether the strategy survives an untouched holdout period using the harness's built-in `train`, `val`, and `test` splits.

### Method

- Loaded each split via [prepare.py:266](/C:/Dev/Desktop-Projects/Auto-Research-Trading/prepare.py#L266C1).
- Re-ran the current strategy with default fixed harness costs on:
  - `train`: 2023-06-01 to 2024-06-30
  - `val`: 2024-07-01 to 2025-03-31
  - `test`: 2025-04-01 to 2025-12-31
- Used the same direct read-only execution path as Pass 1.

### Results

| Split | Bars | Score | Return % | Max DD % | Trades | Backtest Seconds |
|---|---:|---:|---:|---:|---:|---:|
| train | 28440 | 12.2246 | 24.85 | 0.421 | 4294 | 120.02 |
| val | 19656 | 16.1443 | 44.56 | 0.377 | 5162 | 120.01 |
| test | 19728 | 14.4009 | 39.33 | 0.390 | 5234 | 120.01 |

Relative to validation:

- test score vs val score: `-10.8%`
- test return vs val return: `-11.7%`

### Pass 2 Verdict

- Not falsified: the strategy does survive the untouched `test` period with a still-high reported score and strong returns.
- But the strength of that conclusion is limited because all three split runs again terminated at the wall-clock budget boundary.
- This means the holdout result is encouraging, not decisive.

## Falsification Pass 3

### Scope

Pass 3 asked whether holdout performance appears broad-based or concentrated in a few outlier windows and simple BTC-led market regimes.

### Method

- Replayed the current `test` split with a read-only harness mirror that preserved timestamps on the processed equity curve.
- Measured:
  - monthly return concentration
  - top-day concentration
  - simple BTC-led regimes using 72-hour BTC return:
    - `btc_bull`: BTC 72h return `> +5%`
    - `btc_bear`: BTC 72h return `< -5%`
    - `btc_neutral`: everything else
- Important caveat:
  - because the fixed harness stops on wall-clock time, this analysis only covered the processed portion of the `test` split
  - observed processed window: `2025-04-01` through `2025-09-29 19:00 UTC`
  - processed bars: `~65%` of the available test bars

### Results

Processed-window concentration summary:

- top 3 positive months contributed `59.3%` of positive monthly return
- top 10 positive days contributed `21.7%` of all positive daily return
- positive-month HHI: `0.179`

Best processed months:

| Month | Return % | Share of Positive Months % |
|---|---:|---:|
| 2025-04 | 7.20 | 22.82 |
| 2025-05 | 5.95 | 18.86 |
| 2025-08 | 5.57 | 17.65 |
| 2025-06 | 5.26 | 16.69 |
| 2025-07 | 5.15 | 16.34 |

Top processed days:

| Day | Return % |
|---|---:|
| 2025-04-09 | 1.160 |
| 2025-04-07 | 1.043 |
| 2025-05-19 | 0.638 |
| 2025-06-23 | 0.600 |
| 2025-08-25 | 0.587 |

BTC-led regime summary on the processed test window:

| Regime | Share of Bars % | Cumulative Return % | Mean Hourly Return bps |
|---|---:|---:|---:|
| btc_neutral | 89.11 | 30.67 | 0.70 |
| btc_bull | 7.61 | 2.36 | 0.71 |
| btc_bear | 1.61 | 0.80 | 1.15 |
| unknown | 1.68 | 0.75 | 1.04 |

### Pass 3 Verdict

- Not falsified: within the processed portion of holdout, returns do not appear to come from only a handful of isolated days.
- Also not falsified: the strategy is not obviously dependent on BTC bull periods alone. Most observed cumulative return came during the much larger neutral regime bucket.
- But this pass remains incomplete because the time-budget cutoff prevented coverage of the full test horizon, especially the final quarter.

## Falsification Pass 4

### Scope

Pass 4 tested a baseline-faithful trading-scope ablation:

- keep the current signal logic
- allow `BTC` and `ETH` to remain in the bar stream as context
- force the strategy to trade `SOL` only at runtime

This is not a full restoration of the documented baseline spec. It is a scope ablation on the current strategy family.

### Method

- Re-ran the current strategy in two runtime modes:
  - `multi_asset`: default `ACTIVE_SYMBOLS = ["BTC", "ETH", "SOL"]`
  - `sol_only_ablation`: monkeypatched `ACTIVE_SYMBOLS = ["SOL"]` and `SYMBOL_WEIGHTS = {"SOL": 1.0}`
- Used default fixed harness costs.
- Measured both outcome metrics and processed-bar coverage to detect timeout bias.

### Results

Validation split:

| Mode | Score | Return % | Max DD % | Trades | Processed Bars % |
|---|---:|---:|---:|---:|---:|
| multi_asset | 16.5035 | 60.14 | 0.377 | 6187 | 92.9 |
| sol_only_ablation | 12.7503 | 132.33 | 1.111 | 2548 | 100.0 |

Untouched test split:

| Mode | Score | Return % | Max DD % | Trades | Processed Bars % |
|---|---:|---:|---:|---:|---:|
| multi_asset | 14.2363 | 55.07 | 0.436 | 6550 | 89.3 |
| sol_only_ablation | 11.5391 | 98.87 | 0.686 | 2585 | 100.0 |

Relative to the multi-asset mode:

- validation score delta: `-22.7%`
- test score delta: `-18.9%`
- validation trade count delta: `-58.8%`
- test trade count delta: `-60.5%`

### Pass 4 Verdict

- Not falsified: a SOL-only trading scope still appears strong under the current signal family.
- But the score falls materially relative to the multi-asset mode, which means a meaningful portion of the repo's current headline edge comes from trading BTC and ETH directly.
- The much higher SOL-only return should not be overinterpreted because the SOL-only ablation completed the full horizon while the multi-asset mode still hit the wall-clock ceiling before processing all bars.
- Practical conclusion: this ablation weakens the claim that multi-asset trading is required for a strong strategy, but it does not support replacing the current headline with a clean SOL-only claim yet.

## Verdict
- Audit initialized.
- Current leading thesis: the strategy family is plausible, but the repo has not yet earned research-grade confidence in the magnitude of its claimed edge.
- After Falsification Pass 1, the strongest immediate concerns are:
  - scope drift from the documented SOL-only baseline
  - large sensitivity to cost assumptions
  - wall-clock-driven result instability
- After Falsification Pass 2:
  - the untouched holdout does not invalidate the strategy
  - the reproducibility problem remains the main blocker to research-grade confidence
- After Falsification Pass 3:
  - the processed holdout window does not look dominated by a tiny handful of outlier days
  - the strategy does not look like a pure BTC-bull beta proxy
  - the fixed wall-clock cutoff still prevents a full-horizon concentration judgment
- After Falsification Pass 4:
  - a SOL-only trading scope still looks viable
  - current repo-level edge is still overstated if presented as a SOL-only baseline result
  - timeout bias now directly contaminates strategy-scope comparisons too

## Risks / Gaps
- A fresh holdout result has now been logged, but it is still contaminated by wall-clock truncation risk.
- Symbol attribution has only been run at one surface level so far. It has not yet been decomposed by regime, side, or holding period.
- Outlier and regime concentration have only been measured on the processed portion of the test split, not the full test horizon.
- The current implementation and the documented baseline are materially different.
- The harness still allows wall-clock truncation to change measured outcomes.
- SOL-only versus multi-asset comparisons are not fully apples-to-apples until both variants can process the same full horizon.

## Confidence
- level: medium
- because:
  - code inspection and current backtest evidence are direct
  - literature references are current and primary
  - final robustness judgment still depends on holdout and stress tests not yet run

## Smallest Next Step
- Run a strict empirical falsification pass:
  1. deterministic-harness proposal for research claims
  2. full-horizon concentration rerun once deterministic execution exists
  3. rerun SOL-only and multi-asset comparisons under equal bar coverage
