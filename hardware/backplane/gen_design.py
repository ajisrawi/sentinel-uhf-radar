"""
SENTINEL-UHF tile backplane: carries 8 T/R modules, links them to the RFSoC tile.

Per slot: a 2x8 header mating the module's J5 (aux power, RS-485, TX_EN, fault),
a Mini-Fit drain connector fed from the 50 V bus through its own 15 A fuse,
and a resettable fuse on the 12 V aux feed. All slot signals run point to point
to one 2x20 connector for the RFSoC tile, so a module fault can never disturb
its neighbours. TX_EN lines get 33 ohm source terminations at the tile side.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import fpgen as fp  # noqa: E402
from schgen import Schematic, write_project  # noqa: E402

PRO = "SENTINEL_BACKPLANE"
N = 8
HDR2x8 = "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical"
HDR2x20 = "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical"
MF2 = "Connector_Molex:Molex_Mini-Fit_Jr_5566-02A_2x01_P4.20mm_Vertical"
MF4 = "Connector_Molex:Molex_Mini-Fit_Jr_5566-04A_2x02_P4.20mm_Vertical"
R0603, PTC = "Resistor_SMD:R_0603_1608Metric", "Fuse:Fuse_1812_4532Metric"
CP10, C1210, SMB = "Capacitor_SMD:CP_Elec_10x10.5", "Capacitor_SMD:C_1210_3225Metric", "Diode_SMD:D_SMB"


def footprints():
    b = fp.rect("F.Fab", -5.1, -1.6, 5.1, 1.6, 0.1) + fp.pad(1, -4.6, 0, 2.8, 3.4) + fp.pad(2, 4.6, 0, 2.8, 3.4)
    b += fp.rect("F.CrtYd", -6.3, -2.1, 6.3, 2.1, 0.05)
    fp.footprint(HERE / "SENTINEL.pretty", "Fuse_456_SMD", "15 A fast SMD fuse, 10.1 x 3.1 mm (Littelfuse 456 class)", b, 2.1)


def build():
    sch = Schematic(PRO, "SENTINEL-UHF Tile Backplane (8 T/R modules)", "A2", [])
    sch.text("TILE BACKPLANE  -  8 module slots, point-to-point control, fused 50 V drain bus", 20, 22, 2.5)
    tile = {}
    for n in range(N):
        s = n + 1
        x = 30.48 + 63.5 * n
        sch.add(f"J{s}", "Connector_Generic:Conn_02x08_Odd_Even", f"SLOT{s}", HDR2x8, x + 20.32, 66.04, 0,
                {"1": f"+12V_S{s}", "3": f"+12V_S{s}", "5": f"RS485_A{s}", "7": f"RS485_B{s}", "9": f"TX_EN{s}",
                 "11": f"FAULT_N{s}", "13": "NC", "15": "NC", **{str(k): "GND" for k in range(2, 17, 2)}},
                Description=f"T/R module {s} control header (mates module J5)")
        sch.add(f"J{10 + s}", "Connector_Generic:Conn_01x02", f"DRAIN{s}", MF2, x + 20.32, 116.84, 0,
                {"1": f"VD50_S{s}", "2": "GND"}, Description=f"Module {s} 50 V drain feed")
        sch.add(f"F{s}", "Device:Fuse", "15A", "SENTINEL:Fuse_456_SMD", x + 5.08, 116.84, 0,
                {"1": "VDD_50V", "2": f"VD50_S{s}"}, Description="15 A fast fuse, per-slot drain protection")
        sch.add(f"F{10 + s}", "Device:Polyfuse", "0.5A", PTC, x + 5.08, 81.28, 0,
                {"1": "+12V", "2": f"+12V_S{s}"}, Description="Resettable fuse, module aux power")
        sch.add(f"R{s}", "Device:R", "33", R0603, x + 5.08, 152.4, 0,
                {"1": f"TX_EN_T{s}", "2": f"TX_EN{s}"}, Description="TX_EN source termination")
        tile.update({str(4 * n + 1): f"RS485_A{s}", str(4 * n + 3): f"RS485_B{s}",
                     str(4 * n + 2): f"TX_EN_T{s}", str(4 * n + 4): f"FAULT_N{s}"})
    tile.update({str(k): "GND" for k in range(33, 41)})
    sch.add("J9", "Connector_Generic:Conn_02x20_Odd_Even", "TO TILE", HDR2x20, 279.4, 215.9, 0, tile,
            Description="To RFSoC tile: 8 x (RS-485 A/B, TX_EN, FAULT_N)")
    sch.add("J10", "Connector_Generic:Conn_02x02_Odd_Even", "50V IN", MF4, 50.8, 210.82, 0,
            {"1": "VDD_50V", "2": "VDD_50V", "3": "GND", "4": "GND"}, Description="50 V from subarray supply, 40 A pk")
    sch.add("J19", "Connector_Generic:Conn_01x02", "12V IN", MF2, 50.8, 241.3, 0, {"1": "+12V", "2": "GND"},
            Description="12 V aux from subarray supply")
    sch.add("D1", "Device:D_TVS", "SMBJ58A", SMB, 88.9, 210.82, 90, {"2": "VDD_50V", "1": "GND"})
    sch.add("D2", "Device:D_TVS", "SMBJ15A", SMB, 88.9, 241.3, 90, {"2": "+12V", "1": "GND"})
    for i in range(4):
        sch.add(f"C{i + 1}", "Device:C_Polarized", "330u 63V", CP10, 106.68 + 12.7 * i, 210.82, 0,
                {"1": "VDD_50V", "2": "GND"}, Description="Bus reservoir")
    for i in range(4):
        sch.add(f"C{i + 5}", "Device:C", "4.7u 100V", C1210, 106.68 + 12.7 * i, 241.3, 0,
                {"1": "VDD_50V" if i < 2 else "+12V", "2": "GND"})
    for i in range(4):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M4", "MountingHole:MountingHole_3.2mm_M3_Pad",
                381.0 + 12.7 * i, 241.3, 0, {"1": "GND"})
    sch.pwr_flag("GND", 381.0, 210.82)
    sch.pwr_flag("+12V", 393.7, 210.82)
    sch.pwr_flag("VDD_50V", 406.4, 210.82)
    return sch


if __name__ == "__main__":
    footprints()
    write_project(build(), HERE, [], "SENTINEL-UHF Tile Backplane")
