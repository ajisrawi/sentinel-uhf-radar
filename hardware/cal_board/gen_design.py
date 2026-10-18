"""
SENTINEL-UHF calibration network board (one per tile, 324 per face).

The CAL port of each of the tile's 8 T/R modules (30 dB coupler sample at the
antenna port) comes here. A binary tree of seven SPDT switches (8 -> 4 -> 2 -> 1)
picks one channel; each tree level is driven directly by one select bit, so no
decoder is needed. A final SPDT connects the selected channel either to the
tile's calibration DAC (inject: receive-path cal) or its calibration ADC
(measure: transmit-path cal); 6 dB pads keep the tile ports well terminated.
Measuring every channel through the same path is what lets the array remove
channel-to-channel amplitude/phase drift and mutual coupling.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
from schgen import Chain, Schematic, custom_symbol, g_rect, write_project  # noqa: E402

PRO = "SENTINEL_CAL"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"
R0603, C0603 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
CUSTOM = [
    custom_symbol("RF_SPDT", "U", "RF_SPDT", "Package_TO_SOT_SMD:SOT-363_SC-70-6", "SPDT RF switch",
                  [(5, "RFC", -7.62, 0, 0, 2.54), (1, "RF1", 7.62, 0, 180, 2.54), (3, "RF2", 7.62, -5.08, 180, 2.54),
                   (4, "CTRL", -2.54, -10.16, 90, 2.54), (2, "GND", 2.54, -10.16, 90, 2.54),
                   (6, "VDD", 0, 7.62, 270, 2.54)], [g_rect(-5.08, 5.08, 5.08, -7.62)]),
]


def P(ref, lib, value, footprint, rot=0, nets=None, **f):
    return dict(ref=ref, lib_id=lib, value=value, footprint=footprint, x=0, y=0, rot=rot, nets=nets or {}, **f)


def build():
    sch = Schematic(PRO, "SENTINEL-UHF Calibration Network", "A3", CUSTOM)
    sch.text("CALIBRATION NETWORK  -  8 module CAL ports -> SPDT selector tree -> inject / measure", 20, 22, 2.5)
    # 8 -> 1 selector tree: (ref, RF1 net, RF2 net, RFC net, select bit, x, y)
    tree = [("U1", "CH1", "CH2", "L1A", "SEL0", 101.6, 71.12), ("U3", "CH3", "CH4", "L1B", "SEL0", 101.6, 111.76),
            ("U4", "CH5", "CH6", "L1C", "SEL0", 203.2, 71.12), ("U5", "CH7", "CH8", "L1D", "SEL0", 203.2, 111.76),
            ("U6", "L1A", "L1B", "L2A", "SEL1", 127.0, 91.44), ("U7", "L1C", "L1D", "L2B", "SEL1", 177.8, 91.44),
            ("U8", "L2A", "L2B", "COMMON", "SEL2", 152.4, 132.08)]
    for ref, rf1, rf2, rfc, sel, x, y in tree:
        sch.add(ref, "SENTINEL:RF_SPDT", "SPDT", "Package_TO_SOT_SMD:SOT-363_SC-70-6", x, y, 0,
                {"5": rfc, "1": rf1, "3": rf2, "4": sel, "2": "GND", "6": "+3V3"},
                Description=f"Selector tree, {sel} picks RF1/RF2")
    for i in range(8):
        x = 40.64 if i < 4 else 264.16
        y = 71.12 + 20.32 * (i % 4)
        rot = 180 if i < 4 else 0
        sch.add(f"J{i + 1}", "Connector:Conn_Coaxial", f"CAL{i + 1}", SMA, x, y, rot,
                {"1": f"CH{i + 1}", "2": "GND"}, Description=f"From T/R module {i + 1} CAL port")
    # inject / measure selection with 6 dB pads to the tile
    c = Chain(sch, 152.4, 50.8)
    c.start_label("COMMON")
    c.series(P("U2", "SENTINEL:RF_SPDT", "SPDT", "Package_TO_SOT_SMD:SOT-363_SC-70-6",
               nets={"3": "MEAS", "4": "INJ_MEAS", "2": "GND", "6": "+3V3"},
               Description="Inject (RF1) / measure (RF2)"), "5", "1")
    c.shunt([P("R1", "Device:R", "150", R0603)], "GND")
    c.series(P("R2", "Device:R", "37.4", R0603, rot=90, Description="6 dB pad"), "1", "2")
    c.shunt([P("R3", "Device:R", "150", R0603)], "GND")
    c.end(P("J9", "Connector:Conn_Coaxial", "INJECT", SMA, nets={"2": "GND"},
            Description="From tile calibration DAC"), "1")
    m = Chain(sch, 203.2, 25.4)
    m.start_label("MEAS")
    m.shunt([P("R4", "Device:R", "150", R0603)], "GND")
    m.series(P("R5", "Device:R", "37.4", R0603, rot=90, Description="6 dB pad"), "1", "2")
    m.shunt([P("R6", "Device:R", "150", R0603)], "GND")
    m.end(P("J10", "Connector:Conn_Coaxial", "MEASURE", SMA, nets={"2": "GND"},
            Description="To tile calibration ADC"), "1")
    sch.add("J11", "Connector_Generic:Conn_02x05_Odd_Even", "CTRL", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
            50.8, 172.72, 0, {"1": "+3V3", "3": "SEL0", "5": "SEL1", "7": "SEL2", "9": "NC",
                              "2": "GND", "4": "GND", "6": "INJ_MEAS", "8": "GND", "10": "GND"},
            Description="Control from RFSoC tile")
    for i, (val, fpn) in enumerate((("1u", C0603),) + (("100n", C0603),) * 6):
        sch.add(f"C{i + 1}", "Device:C", val, fpn, 101.6 + 10.16 * i, 172.72, 0, {"1": "+3V3", "2": "GND"})
    for i in range(3):
        sch.add(f"R{7 + i}", "Device:R", "100k", R0603, 182.88 + 10.16 * i, 172.72, 0,
                {"1": ("SEL0", "SEL1", "SEL2")[i], "2": "GND"}, Description="Default channel 1")
    for i in range(2):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad",
                228.6 + 12.7 * i, 172.72, 0, {"1": "GND"})
    sch.pwr_flag("GND", 254.0, 167.64)
    sch.pwr_flag("+3V3", 266.7, 167.64)
    return sch


if __name__ == "__main__":
    write_project(build(), HERE, CUSTOM, "SENTINEL-UHF Calibration Network")
