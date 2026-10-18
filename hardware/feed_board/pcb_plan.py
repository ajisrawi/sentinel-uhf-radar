"""Element feed board layout: 86 x 56 mm, all RF paths 1.6 mm (300 W pk)."""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 86.0, 56.0
P.init(HERE, "SENTINEL_FEED", W, H, title="SENTINEL Element Feed Board",
       track_w={"ARM_X_N": 1.6, "ARM_Y_N": 1.6, "HYB_ISO": 1.6})
P.RF_W = 1.6
main, chx, chy = P.CHAINS

P.place_chain(main, 3.4, 28.0, +1, fixed={"J1": (3.4, 28.0, 180)}, gap=3.0)
P.place_chain(chx, 0, 11.0, +1, anchors={"HYB_0": ("U1", "3")}, gap=1.4, fixed={"J2": (W - 10.0, 11.0, 0)})
P.place_chain(chy, 0, 45.0, +1, anchors={"HYB_90": ("U1", "4")}, gap=1.4, fixed={"J3": (W - 10.0, 45.0, 0)})
u1 = P.BRD.parts["U1"]
P.BRD.place("R1", u1.x - 2.0, u1.y + 13.0, 0)
P.BRD.place("L4", W - 7.0, 20.0, 90)
P.BRD.place("L6", W - 7.0, 36.0, 90)
P.BRD.place("H1", 5.0, 5.0)
P.BRD.place("H2", W - 5.0, 28.0)
P.run()
