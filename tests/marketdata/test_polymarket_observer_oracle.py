"""ALG-3411: on-chain payout decode for the Polymarket observer (stdlib only).

The observer runs as a standalone script (python3 -I), so load it by file
path here too — no package imports needed.
"""
import importlib.util
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src/algobots/marketdata/polymarket_observer.py"
spec = importlib.util.spec_from_file_location("pm", SRC)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

REAL_LOG = {  # captured live Oct 23 2026, Polygon tx 0xdc368053..947
    "transactionHash": "0xdc36805308aa4aa991e58fec79765acf7d40c9a38d8f3036db6ab988a1c55947",
    "blockNumber": "0x5b91126",
    "data": "0x0000000000000000000000000000000000000000000000000000000000000002"
            "0000000000000000000000000000000000000000000000000000000000000040"
            "0000000000000000000000000000000000000000000000000000000000000002"
            "0000000000000000000000000000000000000000000000000000000000000001"
            "0000000000000000000000000000000000000000000000000000000000000000",
}
COND = "0x1da7312f1be5a17632c22f44c2c8e30e00007cc4343fa42de670904583cb1f01"


def test_decode_and_query_shape():
    calls = []
    def fake_rpc(m, p):
        calls.append((m, p))
        return "0x5b92000" if m == "eth_blockNumber" else [REAL_LOG]
    pm._rpc = fake_rpc
    got = pm.onchain_payout(COND)
    want = {"tx": REAL_LOG["transactionHash"], "block": int("0x5b91126", 16), "payouts": [1, 0]}
    assert got == want, got
    args = calls[1][1][0]
    assert args["topics"] == [pm.CONDITION_RESOLUTION_TOPIC, COND]
    assert args["address"] == pm.CTF_ADDRESS
    assert int(args["fromBlock"], 16) == int("0x5b92000", 16) - 1500


def test_none_cases():
    pm._rpc = lambda m, p: None
    assert pm.onchain_payout(COND) is None
    assert pm.onchain_payout("") is None
    assert pm.onchain_payout("nothex") is None
