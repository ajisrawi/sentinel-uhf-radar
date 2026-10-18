"""Calibration network layout: 120 x 82 mm; 50 ohm channel lines on F.Cu or B.Cu (over In2 ground)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 120.0, 82.0
ch = [f"CH{i}" for i in range(1, 9)]
P.init(HERE, "SENTINEL_CAL", W, H, title="SENTINEL Calibration Network",
       track_w={**{c: P.RF_W for c in ch}, "+3V3": 0.4})
# channel lines may use B.Cu: it sits over the solid In2 ground pour on this board
inj, meas = P.CHAINS

for ref, x, y in (("U1", 17.0, 32.5), ("U3", 17.0, 58.5), ("U4", 103.0, 32.5), ("U5", 103.0, 58.5),
                  ("U6", 38.0, 45.5), ("U7", 82.0, 45.5), ("U8", 60.0, 45.5)):
    P.BRD.place(ref, x, y, 0)
for i in range(4):
    P.BRD.place(f"J{i + 1}", 2.94, 26.0 + 13.0 * i, 180)
    P.BRD.place(f"J{i + 5}", W - 2.94, 26.0 + 13.0 * i, 0)
# split the inject chain at U2: the selector feeds U2's common pin as a placed chain, but U2's
# output is router-connected so U2's ground pin (between its two outputs) keeps room for a via
assert inj[1][:2] == ["series", "U2"]
P.place_chain([inj[0], ["end", "U2", "5"]], 0, 14.0, +1, anchors={"COMMON": ("U8", "5")}, gap=1.4)
u2 = P.BRD.parts["U2"]
P.place_chain([["start_label", P.PADNET[("U2", "1")]]] + inj[2:], u2.x + 6.0, 14.0, +1,
              fixed={"J9": (98.0, 2.94, 90)}, gap=1.4)
P.place_chain(meas, 80.0, 26.0, +1, fixed={"J10": (110.0, 2.94, 90)}, gap=1.4)
P.BRD.place("J11", 30.0, 72.0, 90)
P.pack(["C1", "C2", "C3", "C4", "C5", "C6", "C7", "R7", "R8", "R9"], 44, 64, 100, 79, spacing=1.6)
P.BRD.place("H1", 12.0, 8.0)
P.BRD.place("H2", 12.0, H - 8.0)
P.run()
