"""
T/R module layout on the shared engine (hardware/tools/pcbgen.py): 230 x 130 mm, 4 layers.

  L1 F.Cu   RF microstrip and components   (RO4350B 0.254 mm to L2 -> 50 ohm = 0.56 mm)
  L2 In1.Cu solid GND plane
  L3 In2.Cu VD_SW pour (10 A pulsed) + signal routing
  L4 B.Cu   signal routing + GND pour

The RF chains are laid out exactly as the schematic chains: series parts along a line,
shunt stacks hanging off each node. The 50 V input strip (connector, TVS, bulk, shunt,
drain switch) is a placed 2.5 mm power chain.
"""
import sys
from pathlib import Path

from shapely.geometry import box

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import pcbgen as P  # noqa: E402

W, H = 230.0, 130.0
P.init(HERE, "SENTINEL_TRM", W, H, title="SENTINEL-UHF T/R Module, 420-450 MHz, 300 W",
       track_w={"+5V": 0.5, "+3V3": 0.5, "+12V": 0.6, "-5V": 0.4, "VDD_50V": 2.0, "VDD_50V_S": 2.0,
                "VG_PA": 0.4, "VG_DRV": 0.4},
       power_nets=["VDD_50V", "VDD_50V_S", "VD_SW"],
       node_w={"VDD_50V": 2.5, "VDD_50V_S": 2.5, "PA_OUT": P.PA_W, "ANT_FEED": P.PA_W, "ANT_RF": P.PA_W},
       node_w_tags=[("Q2-Pad2", P.PA_W), ("C17-", P.PA_W), ("L7-", P.PA_W)])
B = P.BRD
tx, rx, fwd, rev, cal = P.CHAINS
P.place_chain(tx, 2.94, 40.0, +1, fixed={"J1": (2.94, 40.0, 180), "J3": (W - 3.4, 40.0, 0)}, gap=1.0)
P.place_chain(rx, 0, 76.0, -1, fixed={"J2": (2.94, 76.0, 180)}, anchors={"RX_CIRC": ("U3", "3")}, gap=1.0)
P.place_chain(fwd, 0, 90.0, -1, anchors={"CPL_FWD": ("U4", "3")}, gap=1.0)
P.place_chain(rev, 0, 108.0, -1, anchors={"CPL_REV": ("U4", "4")}, gap=1.0)
P.place_chain(cal, 196.0, 122.0, +1, fixed={"J4": (W - 2.94, 122.0, 0)}, gap=1.0)
strip = [["start", "J6", "1"], ["shunt", [["D4", "2", "1"]], False, "GND"],
         ["shunt", [["C38", "1", "2"]], False, "GND"], ["shunt", [["C39", "1", "2"]], False, "GND"],
         ["tapvia"], ["series", "R37", "1", "2"], ["tapvia"], ["end", "Q4", "3"]]
P.place_chain(strip, 0, 6.5, +1, fixed={"J6": (4.5, 6.5, 0)}, gap=1.2)
P.pack(["U18", "C36", "R38", "C37", "R39", "R40", "D3", "R36", "R35", "Q3", "R34", "R48"], 60, 2, 81, 25.5, spacing=1.4)
P.pack(["C15", "C16", "C14", "C13"], 112, 1.5, 165, 15, spacing=1.2)
B.place("TH1", 120.0, 22.0, 0)
P.pack(["U12", "C30", "R18", "R19", "U14", "R20", "R24", "C20", "C22",
        "U13", "C31", "R21", "R22", "U15", "R23", "R25", "C21",
        "U11", "C32", "C33", "C34"], 3, 88, 54, 128, spacing=1.6)
P.pack(["U21", "C47", "C48", "C49", "C50", "J7", "R45", "D6",
        "U16", "R26", "R27", "R28", "R29", "R30", "R31", "R32",
        "U17", "R33", "C35", "R41", "C40", "R46"], 57, 88, 108, 128, spacing=1.6)
P.pack(["J5", "U22", "U19", "C41", "D5", "L11", "R43", "R44", "C42", "C43", "C44",
        "U20", "C45", "C46"], 111, 86, 150, 128, spacing=1.6)
for i, (x, y) in enumerate(((6, 30), (W - 6, 18), (6, 124), (W - 6, 104))):
    B.place(f"H{i + 1}", x, y, 0)
P.run(power_zones=[(P.IN2, "VD_SW", box(2.0, 1.0, 168.0, 36.0))])
