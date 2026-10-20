"""Copper preview of a finished .kicad_pcb (tracks, vias, outline) as a PNG.

usage: layer_preview.py <board.kicad_pcb> <out.png>
Reads the board file directly, so it shows routing done in any tool (e.g. EasyEDA imports).
"""
import re
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Rectangle  # noqa: E402

src, out = sys.argv[1], sys.argv[2]
text = open(src, encoding="utf-8").read()
COL = {"F.Cu": "#d9412b", "B.Cu": "#2b6fd9", "In2.Cu": "#d9b02b", "In1.Cu": "#2bd96a"}

fig, ax = plt.subplots(figsize=(16, 13), dpi=110)
ax.set_facecolor("#0d2b1d")
W = H = 0
m = re.search(r"\(gr_rect\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)", text)
if m:
    x0, y0, W, H = map(float, m.groups())
    ax.add_patch(Rectangle((x0, y0), W - x0, H - y0, fill=False, ec="#e0e0e0", lw=1))
for seg in re.finditer(r"\(segment\s*\(start ([\d.-]+) ([\d.-]+)\)\s*\(end ([\d.-]+) ([\d.-]+)\)\s*\(width ([\d.-]+)\)"
                       r"\s*\(layer \"([^\"]+)\"\)", text):
    xa, ya, xb, yb, w = map(float, seg.groups()[:5])
    ax.plot([xa, xb], [ya, yb], color=COL.get(seg.group(6), "w"), lw=max(w * 2.2, 0.6), solid_capstyle="round",
            alpha=0.9)
for via in re.finditer(r"\(via\s*\(at ([\d.-]+) ([\d.-]+)\)\s*\(size ([\d.-]+)\)", text):
    x, y, d = map(float, via.groups())
    ax.add_patch(Circle((x, y), d / 2, color="#f0f0f0", zorder=3))
ax.set_xlim(-2, W + 2)
ax.set_ylim(H + 2, -2)
ax.set_aspect("equal")
ax.set_title(f"Copper: F.Cu (red), In2.Cu (yellow), B.Cu (blue), vias (white)   {W:.0f} x {H:.0f} mm")
fig.savefig(out, bbox_inches="tight", facecolor="white")
print("wrote", out)
