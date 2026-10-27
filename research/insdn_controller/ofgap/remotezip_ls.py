"""List / extract selected members of a remote zip via HTTP range requests (stdlib only)."""
import struct, sys, urllib.request, zlib
from pathlib import Path
URL = sys.argv[1]

def rng(a, b):
    req = urllib.request.Request(URL, headers={"Range": f"bytes={a}-{b}"})
    return urllib.request.urlopen(req, timeout=120).read()

size = int(urllib.request.urlopen(urllib.request.Request(URL, method="HEAD"), timeout=60).headers["Content-Length"])
tail = rng(size - 65536, size - 1)
e = tail.rfind(b"PK\x05\x06")
cd_size, cd_off = struct.unpack("<II", tail[e + 12:e + 20])
if cd_off == 0xFFFFFFFF:  # zip64
    l = tail.rfind(b"PK\x06\x06")
    cd_size, cd_off = struct.unpack("<QQ", tail[l + 40:l + 56])
cd = rng(cd_off, cd_off + cd_size - 1)
p, ents = 0, []
while cd[p:p + 4] == b"PK\x01\x02":
    meth, = struct.unpack("<H", cd[p + 10:p + 12])
    csz, usz = struct.unpack("<II", cd[p + 20:p + 28])
    nl, xl, cl = struct.unpack("<HHH", cd[p + 28:p + 34])
    off, = struct.unpack("<I", cd[p + 42:p + 46])
    name = cd[p + 46:p + 46 + nl].decode(errors="replace")
    x = cd[p + 46 + nl:p + 46 + nl + xl]
    q = 0
    while q + 4 <= len(x):  # zip64 extra
        hid, hl = struct.unpack("<HH", x[q:q + 4])
        if hid == 1:
            vals = list(struct.unpack("<" + "Q" * (hl // 8), x[q + 4:q + 4 + hl]))
            if usz == 0xFFFFFFFF: usz = vals.pop(0)
            if csz == 0xFFFFFFFF: csz = vals.pop(0)
            if off == 0xFFFFFFFF: off = vals.pop(0)
        q += 4 + hl
    ents.append((name, meth, csz, usz, off))
    p += 46 + nl + xl + cl
if len(sys.argv) == 2:
    for n, m, c, u, o in ents:
        print(f"{c:>12} {u:>12} m{m} {n}")
else:
    pat, out = sys.argv[2], Path(sys.argv[3])
    for n, m, c, u, o in ents:
        if pat.lower() not in Path(n).name.lower() or n.endswith("/"):
            continue
        h = rng(o, o + 29)
        nl, xl = struct.unpack("<HH", h[26:30])
        data = rng(o + 30 + nl + xl, o + 30 + nl + xl + c - 1)
        raw = zlib.decompress(data, -15) if m == 8 else data
        assert len(raw) == u, (n, len(raw), u)
        dst = out / n
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(raw)
        print("OK", n, u, flush=True)
