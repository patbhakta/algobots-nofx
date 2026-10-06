"""One small deterministic monochrome grain tile, built once (no runtime noise).

The tile is an 8-bit grayscale PNG generated from a fixed-seed xorshift PRNG
using only the standard library, so the bytes are identical on every build.
CSS shows it on a fixed, non-animated layer under the content at
`GRAIN["opacity"]`; the texture-off setting removes the layer.
"""

import base64
import hashlib
import struct
import zlib
from functools import cache

from algobots.dashboard.design.tokens import GRAIN


def _xorshift32(seed: int):
    x = seed & 0xFFFFFFFF or 1
    while True:
        x ^= (x << 13) & 0xFFFFFFFF
        x ^= x >> 17
        x ^= (x << 5) & 0xFFFFFFFF
        yield x


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


@cache
def tile_png(size: int | None = None, seed: int | None = None) -> bytes:
    size = size or GRAIN["tile_px"]
    rng = _xorshift32(GRAIN["seed"] if seed is None else seed)
    lo, hi = GRAIN["levels"]
    span = hi - lo + 1
    rows = b"".join(
        b"\x00" + bytes(lo + next(rng) % span for _ in range(size)) for _ in range(size)
    )
    header = struct.pack(">IIBBBBB", size, size, 8, 0, 0, 0, 0)  # 8-bit grayscale
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", header)
        + _chunk(b"IDAT", zlib.compress(rows, 9))
        + _chunk(b"IEND", b"")
    )


def tile_data_uri() -> str:
    return "data:image/png;base64," + base64.b64encode(tile_png()).decode("ascii")


def tile_sha256() -> str:
    return hashlib.sha256(tile_png()).hexdigest()
