#!/usr/bin/env python3
"""Render the studio canvas from blackboard/events.jsonl shape events.
Mirrors frontend/src/Canvas.tsx: 120 logical units -> 560px, bg #0e1420,
composite by global z, fill polys (>=3 pts) if fill else stroke outline.
"""
import json
from PIL import Image, ImageDraw

SRC = "/mnt/win/Users/Staru/dev/projects/soslo/sverh/openclaw-stack/blackboard/events.jsonl"
OUT = "/home/starum/.claude/jobs/b71205e2/tmp/canvas.png"
UNIT = 120
PX = 560
S = PX / UNIT
BG = (0x0e, 0x14, 0x20)

def hex2rgb(h):
    h = (h or "#cccccc").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    except Exception:
        return (204, 204, 204)

shapes = []
for line in open(SRC):
    line = line.strip()
    if not line:
        continue
    try:
        e = json.loads(line)
    except Exception:
        continue
    if e.get("kind") == "shape":
        shapes.append(e)

# global z-composite; stable sort keeps append order within equal z
shapes.sort(key=lambda s: s.get("z", 0))
print(f"rendering {len(shapes)} shapes")

img = Image.new("RGB", (PX, PX), BG)
# supersample for alpha compositing + smoother lines
SS = 2
big = Image.new("RGB", (PX * SS, PX * SS), BG)
draw = ImageDraw.Draw(big, "RGBA")
lw = max(1, int(round(S * 0.35 * SS)))

for e in shapes:
    col = hex2rgb(e.get("color"))
    alpha = e.get("alpha")
    a = 255 if alpha is None else max(0, min(255, int(round(alpha * 255))))
    fill = e.get("fill")
    for poly in e.get("polys", []):
        if not poly or len(poly) < 2:
            continue
        pts = [(p[0] * S * SS, p[1] * S * SS) for p in poly]
        if fill and len(poly) >= 3:
            draw.polygon(pts, fill=(col[0], col[1], col[2], a))
        else:
            draw.line(pts, fill=(col[0], col[1], col[2], a), width=lw, joint="curve")

img = big.resize((PX, PX), Image.LANCZOS)
img.save(OUT)
print(f"saved {OUT}")
