# Conventions

## Workflow rules

- Use `uv` for Python entrypoints
- Treat `strategy.py` as the intended experiment surface
- Treat `prepare.py`, `backtest.py`, and `benchmarks/` as fixed harness code
- Prefer docs-verified commands rather than inferred entrypoints

## Code style

- Python modules use standard-library-first imports followed by third-party imports
- Constants are UPPER_SNAKE_CASE
- Functions and variables are `snake_case`
- Type hints are used throughout the active runtime paths
- Module docstrings are common and often describe whether a file is fixed or operator-facing

## Data contracts

- Shared trading contracts are dataclasses from `prepare.py`
- Strategy outputs are target-position `Signal` objects, not imperative order calls
- Long-running state is expected to be JSON-serializable
- Cache and status files are written under `~/.cache/autotrader`

## CLI patterns

- Operator entrypoints use `argparse`
- Human-readable summaries are usually printed alongside JSON or CSV/TSV artifacts
- Local control surfaces prefer explicit modes and flags over hidden defaults, especially in `run_jupiter_live.py`

## Documentation conventions

- The repo relies heavily on Markdown docs for workflow and guardrails
- Strategy-specific caveats are documented in `docs/` rather than encoded in many runtime checks
- AGENTS instructions are part of the working contract and should be read before editing repo code

## Validation conventions

- For strategy work, the default validation command is `uv run backtest.py`
- For broader comparison, use `uv run run_benchmarks.py`
- For intraday strategy validation, use `uv run python backtest_5m.py`
- There is no established automated unit/integration test suite; confidence comes from CLI validation surfaces and workbench/runtime checks
