"""Periodic read-only recorder export service; each cycle is independently logged."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    feeds = [
        ("kalshi", "KXBTC15M.KALSHI", "/feeds/kalshi/observations.jsonl"),
        ("pmus", "BTC15M.PMUS", "/feeds/pmus/observations.jsonl"),
        ("nautilus-paper", "KXBTC15M/USD.SIM", None),
    ]
    while True:
        for feed, instrument, source in feeds:
            command = [
                sys.executable,
                "-m",
                "algobots.warehouse.export",
                "--feed",
                feed,
                "--instrument-id",
                instrument,
                "--provider-release",
                os.environ["ALGOBOTS_RECORDER_RELEASE"],
                "--catalog-root",
                "/mnt/funnytree/algobots/ntl_catalog",
            ]
            if source:
                command += ["--source", source]
            result = subprocess.run(command, check=False, timeout=300)
            log.info("export feed=%s exit=%s", feed, result.returncode)
        time.sleep(900)


if __name__ == "__main__":
    main()
