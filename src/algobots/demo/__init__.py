"""algobots.demo — live paper-trading demo (ALG-3248).

Reads the Kalshi BTC 15-minute forward-observer feed (Laya System One + Jev
decisions per settled interval), replays it through paper strategies sized
$5-15 behind the real ``algobots.risk`` envelopes and a kill switch, and
serves one A09-styled page at ``/demo``. PAPER ONLY: nothing here can route
an order to a broker.
"""
