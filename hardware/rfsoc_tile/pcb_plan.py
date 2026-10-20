"""RFSoC tile carrier layout: 320 x 260 mm (enlarged for routing room).

RX SMA + balun column on the left edge, TX column on the right edge, SOM connectors in
the centre, QSFP28 at the top edge, module links and power along the bottom.

This script fixes the placement and zones. The grid router could not finish this board
(about 50 nets left around the 0.8 mm SOM connectors), so the released routing comes from
the EasyEDA Pro autorouter (Top / Bottom / In2, In1 kept as the solid GND plane) and is
stored in easyeda_routes.json. To rebuild the board:

    python rfsoc_tile/pcb_plan.py                      # placement + zones (+ grid-router tracks)
    bash tools/pcb_check.sh rfsoc_tile SENTINEL_TILE   # build .kicad_pcb
    "<KiCad>/bin/python.exe" tools/import_easyeda.py rfsoc_tile/SENTINEL_TILE.kicad_pcb rfsoc_tile/easyeda_routes.json
    kicad-cli pcb drc --refill-zones --save-board ...  # refill zones, check

Data-converter, LVDS and 25 Gb/s pairs are routed as single nets; a manual pass must make
them coupled, length-matched differential pairs.
"""
import sys
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 320.0, 260.0
P.init(HERE, "SENTINEL_TILE", W, H, title="SENTINEL RFSoC Tile Carrier",
       track_w={"+3V3": 0.5, "DAC_AVTT": 0.4, "+12V": 0.8}, power_nets=["+12V"])
B = P.BRD
for c in range(9):
    y = 18.0 + 27.0 * c
    B.place(f"J{10 + c}", 2.94, y, 180)
    B.place(f"T{1 + c}", 15.0, y, 0)
    B.place(f"C{100 + c}", 23.0, y - 2.6, 0)
    B.place(f"C{120 + c}", 23.0, y + 2.6, 0)
    B.place(f"C{140 + c}", 15.0, y + 5.0, 0)
    B.place(f"J{20 + c}", W - 2.94, y, 0)
    B.place(f"T{11 + c}", W - 15.0, y, 180)
B.place("J1", 140.0, 70.0, 0)
B.place("J2", 140.0, 165.0, 0)
B.place("J7", 230.0, 9.0, 0)
P.pack(["J4", "R10", "R11", "R12", "J5", "U9", "C9", "J6", "R20", "R21", "R22", "R23", "C10", "C11", "C12",
        "R24", "C160", "C161", "R160"], 205, 28, 282, 160, spacing=3.0)
# backplane cable header stands upright: module 1-4 transceivers on its left, 5-8 on its right
B.place("J3", 190.0, 192.0, 0)
P.pack([f"U{s}" for s in range(1, 5)] + [f"C{s}" for s in range(1, 5)], 45, 186, 180, 226, spacing=3.5)
P.pack([f"U{s}" for s in range(5, 9)] + [f"C{s}" for s in range(5, 9)], 200, 186, 282, 224, spacing=3.5)
B.place("J8", 150.0, 248.0, 90)
P.pack(["U10", "C20", "C21", "C22", "L1", "R25", "R26", "C23", "C24", "R27", "C25"], 200, 228, 282, 257, spacing=2.4)
for i, (x, y) in enumerate(((45.0, 5.0), (195.0, 5.0), (288.0, 170.0), (45.0, 170.0))):
    B.place(f"H{i + 1}", x, y)
P.run(power_zones=[(P.IN2, "+12V", box(124.0, 157.0, 172.0, 175.0).union(box(141.0, 175.0, 159.0, 258.0)))])
