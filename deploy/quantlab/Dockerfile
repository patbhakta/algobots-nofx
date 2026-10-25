FROM ghcr.io/astral-sh/uv:0.9.7 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY deploy/quantlab/pyproject.toml deploy/quantlab/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/algobots/warehouse /app/src/algobots/warehouse
COPY notebooks/quantlab_openbb.py /app/notebooks/quantlab_openbb.py
USER 1000:1000
WORKDIR /home/quantlab
