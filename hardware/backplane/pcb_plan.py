"""Tile backplane layout: 232 x 112 mm, 8 slot columns, 50 V bus as an In2.Cu pour."""
import sys
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 232.0, 112.0
tw = {"+12V": 0.8, **{f"VD50_S{s}": 2.5 for s in range(1, 9)}, **{f"+12V_S{s}": 0.6 for s in range(1, 9)}}
P.init(HERE, "SENTINEL_BACKPLANE", W, H, title="SENTINEL Tile Backplane", track_w=tw,
       power_nets=["VDD_50V"] + [f"VD50_S{s}" for s in range(1, 9)])

for n in range(8):
    s, x = n + 1, 16.0 + 28.5 * n
    P.BRD.place(f"J{s}", x, 12.0, 0)            # module control header
    P.BRD.place(f"F{10 + s}", x + 9.0, 22.0, 90)  # 12 V polyfuse
    P.BRD.place(f"J{10 + s}", x + 2.0, 44.0, 90)  # drain Mini-Fit
    P.BRD.place(f"F{s}", x + 4.0, 60.0, 0)        # 15 A drain fuse
P.BRD.place("J9", 92.0, 100.0, 90)
P.BRD.place("J10", 10.0, 92.0, 0)
P.BRD.place("J19", 28.0, 98.0, 90)
P.pack(["D1", "D2", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"], 38, 74, 92, 108, spacing=1.6)
P.pack([f"R{s}" for s in range(1, 9)], 96, 82, 160, 90, spacing=1.6)
for i, (x, y) in enumerate(((4.5, 4.5), (W - 4.5, 4.5), (W - 4.5, H - 4.5), (180.0, H - 4.5))):
    P.BRD.place(f"H{i + 1}", x, y)
P.run(power_zones=[(P.IN2, "VDD_50V", box(2.0, 55.5, W - 2.0, 64.5).union(box(2.0, 64.5, 36.0, H - 2.0)).union(box(36.0, 72.5, 74.0, 92.0)))])
