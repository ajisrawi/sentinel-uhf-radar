"""Clock & timing board layout: 150 x 130 mm.

LVDS pairs are routed by the generic router as single nets; a manual pass must
convert them to coupled 100 ohm pairs and length-match the 8 CLK/SYSREF outputs.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 150.0, 130.0
P.init(HERE, "SENTINEL_CLOCK", W, H, title="SENTINEL Clock & Timing Distribution",
       track_w={"+3V3": 0.4, "+3V3A": 0.4, "+5V": 0.5})
B = P.BRD
B.place("J1", 2.94, 18.0, 180)
B.place("J2", 2.94, 46.0, 180)
P.pack(["R1", "C1", "U1", "R3", "Y1", "C4", "R4", "C5", "R5", "C6", "C7", "C8", "R6"], 12, 4, 72, 36, spacing=1.6)
P.pack(["R2", "U2", "U3", "R7"], 12, 40, 72, 52, spacing=1.6)
# LVDS drivers sit beside the connectors they feed, outputs facing right:
# tiles 1-4 (U4 CLK, U6 SYSREF, U8 PPS) upper group, tiles 5-8 (U5, U7, U9) lower group
for i, (ref, y) in enumerate((("U4", 12.0), ("U6", 30.0), ("U8", 48.0), ("U5", 72.0), ("U7", 90.0), ("U9", 108.0))):
    B.place(ref, 112.0, y, 0)
# tile connectors turned so both pin rows are reachable from above and below
for t in range(1, 9):
    B.place(f"J{2 + t}", 132.0, 14.0 + 14.8 * (t - 1), 90)
P.pack(["U10", "C25", "J12", "R8", "D1", "U11", "J11", "J13", "U12", "U13"] + [f"C{9 + i}" for i in range(16)],
       4, 58, 74, 126, spacing=1.6)
for i, (x, y) in enumerate(((5.0, 5.0), (5.0, H - 5.0), (W - 5.0, 5.0), (W - 5.0, H - 5.0))):
    B.place(f"H{i + 1}", x, y)
P.run()
