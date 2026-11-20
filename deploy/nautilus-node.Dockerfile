# Paper execution node: Nautilus 2.0.0rc9, explicitly installed on a pinned base.
#
# Base is Nautech's own image pinned by digest — it is the one that ships
# Python 3.13 and an older engine; the RUN below upgrades the engine explicitly.
# Research and legacy API worker environments remain separate. `latest` is not used:
# a re-tag upstream must not change the engine under a running paper node.
#
# The `workers` extra is deliberately NOT installed — it pins nautilus-trader
# >=1.231 and would put the API's 1.x engine back into this image.
FROM ghcr.io/nautechsystems/jupyterlab@sha256:f5c9eabe4a2c802876f6a32a805f01e280c7056b26d6b83283b89ead296e1944

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir ".[postgres]" "redis>=5" "nautilus_trader==2.0.0rc9" \
    && python -c "import nautilus_trader as n; assert n.__version__ == '2.0.0rc9', n.__version__"

CMD ["python", "-m", "algobots.node.paper_node"]
