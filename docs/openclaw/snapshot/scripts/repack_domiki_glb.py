#!/usr/bin/env python3
"""Repack Domiki.glb into a light glb the gz drone-camera sensor can render.

The original 32MB glb (11 x 4K PNG textures) does NOT render in the camera sensor
under run load — the drone photos come back gray. This keeps the house geometry and
downscales the textures (roofs 1024 to keep ArUco crisp, walls/ground 512, JPEG q82)
-> ~1MB. Rebuilds the single BIN buffer + all bufferView offsets.

  python3 scripts/repack_domiki_glb.py [SRC.glb] [DST.glb]
  default DST: bridge/gazebo/models/domiki_city/meshes/Domiki_light.glb
"""
import struct, json, io, os, sys
from PIL import Image

SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/Downloads/Telegram Desktop/Domiki.glb")
DST = sys.argv[2] if len(sys.argv) > 2 else "bridge/gazebo/models/domiki_city/meshes/Domiki_light.glb"

raw = open(SRC, "rb").read()
_, _, _ = struct.unpack("<III", raw[:12]); off = 12
clen, _ = struct.unpack("<II", raw[off:off+8]); off += 8
js = json.loads(raw[off:off+clen]); off += clen
blen, _ = struct.unpack("<II", raw[off:off+8]); off += 8
bindata = raw[off:off+blen]

bvs = js["bufferViews"]
img_bv = {im["bufferView"]: i for i, im in enumerate(js.get("images", [])) if "bufferView" in im}
new = bytearray()
align = lambda b: b.extend(b"\x00" * ((4 - len(b) % 4) % 4))
for bi, bv in enumerate(bvs):
    o = bv.get("byteOffset", 0)
    data = bindata[o:o+bv["byteLength"]]
    if bi in img_bv:
        im = Image.open(io.BytesIO(data)).convert("RGB")
        name = (js["images"][img_bv[bi]].get("name", "")).lower()
        sz = 1024 if ("крыша" in name or "roof" in name) else 512
        buf = io.BytesIO(); im.resize((sz, sz), Image.LANCZOS).save(buf, "JPEG", quality=82)
        data = buf.getvalue()
        js["images"][img_bv[bi]]["mimeType"] = "image/jpeg"
    bv["byteOffset"] = len(new); bv["byteLength"] = len(data)
    new += data; align(new)
js["buffers"][0]["byteLength"] = len(new)
jb = json.dumps(js, separators=(",", ":")).encode()
jb += b" " * ((4 - len(jb) % 4) % 4)
new.extend(b"\x00" * ((4 - len(new) % 4) % 4))
body = struct.pack("<II", len(jb), 0x4E4F534A) + jb + struct.pack("<II", len(new), 0x004E4942) + bytes(new)
open(DST, "wb").write(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
print(f"wrote {DST}: {os.path.getsize(DST)//1024} KB")
