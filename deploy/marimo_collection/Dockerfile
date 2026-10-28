# Reuse the deployed OpenBB/Nautilus runtime without its quantlab worker entrypoint.
FROM algobots/quantlab:alg3421
USER root
RUN uv pip install --python /opt/venv/bin/python --no-cache-dir matplotlib==3.10.8 plotly==6.3.1 scipy==1.16.3 sympy==1.14.0 scikit-learn==1.7.2 altair==5.5.0
ENTRYPOINT []
USER 1000:1000
