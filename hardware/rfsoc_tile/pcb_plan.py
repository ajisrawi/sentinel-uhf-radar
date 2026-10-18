"""RFSoC tile carrier layout: 240 x 190 mm.

RX SMA + balun column on the left edge, TX column on the right edge, SOM connectors in
the centre, QSFP28 at the top edge, module links and power along the bottom.
Data-converter, LVDS and 25 Gb/s pairs are routed as single nets by the generic
router; a manual pass must make them coupled, length-matched differential pairs.
"""
import sys
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 240.0, 190.0
P.init(HERE, "SENTINEL_TILE", W, H, title="SENTINEL RFSoC Tile Carrier",
       track_w={"+3V3": 0.5, "DAC_AVTT": 0.4, "+12V": 0.8}, power_nets=["+12V"])
B = P.BRD
for c in range(9):
    y = 14.0 + 19.0 * c
    B.place(f"J{10 + c}", 2.94, y, 180)
    B.place(f"T{1 + c}", 15.0, y, 0)
    B.place(f"C{100 + c}", 23.0, y - 2.6, 0)
    B.place(f"C{120 + c}", 23.0, y + 2.6, 0)
    B.place(f"C{140 + c}", 15.0, y + 5.0, 0)
    B.place(f"J{20 + c}", W - 2.94, y, 0)
    B.place(f"T{11 + c}", W - 15.0, y, 180)
B.place("J1", 100.0, 48.0, 0)
B.place("J2", 100.0, 108.0, 0)
B.place("J7", 168.0, 9.0, 0)
P.pack(["J4", "R10", "R11", "R12", "J5", "U9", "C9", "J6", "R20", "R21", "R22", "R23", "C10", "C11", "C12",
        "R24", "C160", "C161", "R160"], 150, 22, 208, 126, spacing=2.0)
P.pack([f"U{s}" for s in range(1, 9)] + [f"C{s}" for s in range(1, 9)], 36, 124, 205, 160, spacing=2.4)
B.place("J3", 40.0, 183.0, 270)
B.place("J8", 112.0, 176.0, 90)
P.pack(["U10", "C20", "C21", "C22", "L1", "R25", "R26", "C23", "C24", "R27", "C25"], 122, 164, 205, 188, spacing=1.6)
for i, (x, y) in enumerate(((36.0, 5.0), (140.0, 5.0), (210.0, 120.0), (36.0, 120.0))):
    B.place(f"H{i + 1}", x, y)
P.run(power_zones=[(P.IN2, "+12V", box(84.0, 100.0, 132.0, 118.0).union(box(104.0, 118.0, 122.0, 188.0)))])
