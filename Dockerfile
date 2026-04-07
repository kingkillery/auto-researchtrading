FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PORT=8080 \
    STATE_PATH=/data/paper-state.json \
    STRATEGY_SPEC=strategy:Strategy

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY *.py ./
COPY benchmarks ./benchmarks
COPY dashboard_template.html ./
COPY assets/logo.png ./assets/logo.png
COPY docs/jupiter_experiment_threads.json ./docs/jupiter_experiment_threads.json
COPY artifacts/dashboard-generative-ui/bundle.html ./artifacts/dashboard-generative-ui/bundle.html

EXPOSE 8080

CMD ["uv", "run", "python", "/app/fly_entrypoint.py"]
