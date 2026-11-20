# Preserve the deployed gateway application; update the exact node contract pin.
ARG GATEWAY_BASE=algobots/gateway:rc8-health-20261111
FROM ${GATEWAY_BASE}
COPY src/algobots/gateway/app.py src/algobots/gateway/nodes.py /usr/local/lib/python3.12/site-packages/algobots/gateway/
