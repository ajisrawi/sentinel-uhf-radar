"""
Subarray PSU layout: 300 x 185 mm.

Left: 380 V primary (no ground pour, HV_* nets keep 2.5 mm clearance, 3 mm creepage
to the secondary pour). The two full bricks straddle the barrier: input pins on
the primary side, output pins on the secondary side. Optocouplers and the bypass
relay straddle it the same way. Right: OR-ing, shunt, bulk, M6 studs; bottom band:
12 V aux brick, supervisor MCU, RS-485.
"""
import sys
from pathlib import Path

from shapely.geometry import MultiPoint, box
from shapely.ops import unary_union

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 300.0, 185.0
HV = ["HV_IN_P", "HV_F", "HV_P", "HV_N", "HV_ONOFF1", "HV_ONOFF2"]
P.init(HERE, "SENTINEL_PSU", W, H, title="SENTINEL Subarray PSU 380 V -> 50 V",
       track_w={**{n: 1.5 for n in HV}, "+12V": 0.8, "VOUT_50V": 1.0},
       power_nets=["VOR", "VOUT_50V", "BRICK1_OUT", "BRICK2_OUT"])
# IPC-2221 B2 (external, uncoated, 301-500 V): 2.5 mm around the 380 V rails and across the
# primary/secondary barrier; normal spacing inside the primary-return domain (opto, ON/OFF).
P.NET_CLR.update({n: 2.5 for n in HV})
P.NET_DOMAIN.update({n: "primary" for n in HV})
P.NET_CLR_HARD.update({"HV_IN_P", "HV_F", "HV_P"})
for n in ("HV_IN_P", "HV_F", "HV_P"):
    P.NET_CLASSES.append(["HV380", 0.2, 1.5, n])
for n in ("HV_N", "HV_ONOFF1", "HV_ONOFF2"):
    P.NET_CLASSES.append(["PRI", 0.2, 1.5, n])
P.DRU = """(version 1)
(rule "380 V rails"
  (condition "A.NetClass == 'HV380' && A.Net != B.Net")
  (constraint clearance (min 2.5mm)))
(rule "isolation barrier"
  (condition "A.NetClass == 'PRI' && B.NetClass != 'PRI' && B.NetClass != 'HV380'")
  (constraint clearance (min 2.5mm)))
"""

primary = unary_union([box(0, 0, 100, 140), box(0, 140, 88, H)])
B = P.BRD
# primary side
B.place("J1", 10.0, 20.0, 0)
B.place("F1", 35.0, 20.0, 0)
B.place("RT1", 62.0, 20.0, 0)
B.place("C1", 12.0, 45.0, 0)
B.place("C2", 12.0, 66.0, 0)
# isolation barrier crossings
B.place("U1", 148.0, 45.0, 0)
B.place("U2", 148.0, 113.0, 0)
B.place("U3", 88.0, 150.0, 180)
B.place("U4", 88.0, 163.0, 180)
B.place("K1", 101.0, 172.0, 270)
B.place("R1", 101.0, 148.5, 0)
B.place("R2", 101.0, 161.5, 0)
# secondary power path
B.place("D1", 232.0, 22.0, 180)
B.place("D2", 232.0, 92.0, 180)
B.place("R3", 210.0, 50.0, 90)
B.place("R4", 210.0, 118.0, 90)
B.place("R7", 247.5, 57.0, 0)
B.place("TH1", 180.0, 79.0, 0)
B.place("TH2", 180.0, 147.0, 0)
P.pack(["C3", "C4", "C5", "C6"], 252, 4, 298, 50, spacing=1.6)
B.place("C7", 294.0, 56.0, 90)
B.place("J2", 290.0, 100.0, 0)
B.place("J3", 290.0, 124.0, 0)
P.pack(["U9", "R8", "C8", "R9", "R10"], 252, 62, 280, 92, spacing=1.6)
P.pack(["U5", "C9", "J4", "U6", "C10", "C11", "C12", "C13", "Q1", "D3", "R11", "R12",
        "U7", "C14", "U8", "J5", "J6", "R13", "D4", "R5", "R6"], 112, 149, 296, 183, spacing=1.6)
for i, (x, y) in enumerate(((106.0, 6.0), (215.0, 6.0), (213.0, 80.0), (296.0, 140.0))):
    B.place(f"H{i + 1}", x, y)


def hull(pads, margin):
    pts = [B.pad(r, n)["c"] for r, n in pads]
    return MultiPoint(pts).convex_hull.buffer(margin)


b1 = hull([("U1", "8"), ("D1", "2")], 2.6)
b2 = hull([("U2", "8"), ("D2", "2")], 2.6)
vor = hull([("D1", "1"), ("D2", "1"), ("R7", "1")], 2.4)
vout = hull([("R7", "2"), ("C3", "1"), ("C4", "1"), ("C5", "1"), ("C6", "1"), ("C7", "1"), ("J2", "1")], 3.0)
vout = vout.difference(vor.buffer(1.0))
P.run(power_zones=[(P.F, "BRICK1_OUT", b1), (P.F, "BRICK2_OUT", b2), (P.IN2, "VOR", vor), (P.IN2, "VOUT_50V", vout)],
      gnd_keepout=primary.buffer(3.0))
