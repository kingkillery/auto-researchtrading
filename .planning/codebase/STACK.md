# Stack

## Core language and packaging

- Language: Python 3.10+
- Package metadata lives in `pyproject.toml`
- Dependency and runner workflow is standardized on `uv`
- Lockfile is `uv.lock`

## Key runtime dependencies

- `numpy` for indicator math and array-heavy strategy logic
- `pandas` for bar history frames, cache reads, and report shaping
- `scipy` is declared but not central to the currently visible runtime paths
- `requests` for market-data and funding API access
- `pyarrow` for parquet cache reads and writes

## Primary execution surfaces

- Research harness: `prepare.py`, `backtest.py`, `run_benchmarks.py`
- Mutable strategy surface: `strategy.py`
- Intraday validation surface: `backtest_5m.py`
- Paper/live feed runner: `run_jupiter_live.py`
- Local workbench server: `fly_entrypoint.py`
- Workbench CLI client: `workbench_ctl.py`

## Data and artifact formats

- Historical market cache: parquet under `~/.cache/autotrader/data`
- Workbench and paper/live state: JSON and JSONL under `~/.cache/autotrader`
- Research summaries: TSV in repo root such as `results.tsv` and `autoresearch-results.tsv`
- Equity exports: CSV such as `equity_curve.csv`
- Dashboard frontend: static HTML in `dashboard_template.html`

## Operational model

- The repo is backtest-first, not deployment-first
- The fixed hourly harness remains the canonical scoring path via `backtest.py`
- The workbench is a local operator-run process at `http://127.0.0.1:8080/`
- Jupiter live execution is an explicit opt-in mode behind CLI confirmation guards in `run_jupiter_live.py`

## Notable constraints

- `prepare.py`, `backtest.py`, and `benchmarks/` are treated as fixed harness code
- No formal web framework, task queue, or database is in use
- No test framework is currently wired into the project metadata
