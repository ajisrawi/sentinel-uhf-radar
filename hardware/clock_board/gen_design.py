"""
SENTINEL-UHF clock and timing distribution board (one per 8 tiles).

10 MHz + 1 PPS from the site GPS-disciplined rubidium master come in on SMA.
A narrow-loop integer-N PLL locks a 122.88 MHz VCXO to the 10 MHz (jitter
cleaning: the VCXO sets close-in phase noise, the loop only removes drift).
SYSREF for deterministic multi-tile sync is the PPS re-timed by the clean
clock in a D flip-flop, so it is phase aligned to the sample clock on every
tile. Six quad LVDS drivers send CLK, SYSREF and PPS to 8 RFSoC tiles.

The PLL is a generic integer-N PLL in TSSOP-16 (ADF4002 class); its pin map
must be checked against the selected part's datasheet before layout release.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
from schgen import Schematic, custom_symbol, g_rect, write_project  # noqa: E402

PRO = "SENTINEL_CLOCK"
R0603, C0603 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"
SOIC16, TSSOP16 = "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm", "Package_SO:TSSOP-16_4.4x5mm_P0.65mm"
SOT23_5, SC70_6, SOIC8 = "Package_TO_SOT_SMD:SOT-23-5", "Package_TO_SOT_SMD:SOT-363_SC-70-6", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
HDR2x5 = "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical"
HDR1x4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
VCXO_FP = "Oscillator:Oscillator_SMD_EuroQuartz_XO53-4Pin_5.0x3.2mm"

PLL_PINS = [(1, "RSET"), (2, "CP"), (3, "CPGND"), (4, "AGND"), (5, "RFINB"), (6, "RFINA"), (7, "AVDD"), (8, "REFIN"),
            (9, "DGND"), (10, "CE"), (11, "CLK"), (12, "DATA"), (13, "LE"), (14, "MUXOUT"), (15, "DVDD"), (16, "VP")]
CUSTOM = [
    custom_symbol("PLL_IntN", "U", "PLL_IntN", TSSOP16, "Integer-N PLL, 200 MHz RF in, SPI (ADF4002 class)",
                  [(n, nm, -12.7 if i < 8 else 12.7, 8.89 - 2.54 * (i % 8), 0 if i < 8 else 180, 2.54)
                   for i, (n, nm) in enumerate(PLL_PINS)], [g_rect(-10.16, 11.43, 10.16, -11.43)]),
    custom_symbol("VCXO", "Y", "VCXO", VCXO_FP, "VCXO 122.88 MHz, LVCMOS, +/-50 ppm pull",
                  [(1, "VC", -7.62, 0, 0, 2.54), (2, "GND", 0, -7.62, 90, 2.54), (3, "OUT", 7.62, 0, 180, 2.54),
                   (4, "VDD", 0, 7.62, 270, 2.54)], [g_rect(-5.08, 5.08, 5.08, -5.08)]),
]


def build():
    sch = Schematic(PRO, "SENTINEL-UHF Clock & Timing Distribution (8 tiles)", "A2", CUSTOM)
    sch.text("CLOCK  -  10 MHz -> PLL + 122.88 MHz VCXO -> LVDS to 8 tiles; SYSREF = PPS re-timed by CLK", 20, 22, 2.5)
    sch.add("J1", "Connector:Conn_Coaxial", "10MHz IN", SMA, 30.48, 60.96, 180, {"1": "REF10", "2": "GND"},
            Description="10 MHz from site master, +7 dBm sine")
    sch.add("R1", "Device:R", "51", R0603, 45.72, 71.12, 0, {"1": "REF10", "2": "GND"}, Description="50 ohm termination")
    sch.add("C1", "Device:C", "100n", C0603, 55.88, 60.96, 90, {"1": "REF10", "2": "REFIN"})
    sch.add("J2", "Connector:Conn_Coaxial", "PPS IN", SMA, 30.48, 111.76, 180, {"1": "PPS_RAW", "2": "GND"},
            Description="1 PPS from site master")
    sch.add("R2", "Device:R", "51", R0603, 45.72, 121.92, 0, {"1": "PPS_RAW", "2": "GND"})
    sch.add("U2", "74xGxx:74LVC1G17", "74LVC1G17", SOT23_5, 71.12, 111.76, 0,
            {"2": "PPS_RAW", "4": "PPS", "3": "GND", "5": "+3V3"}, Description="PPS Schmitt buffer")
    pll = {"1": "RSET", "2": "CP", "3": "GND", "4": "GND", "5": "RFINB", "6": "RFIN", "7": "+3V3A", "8": "REFIN",
           "9": "GND", "10": "PLL_CE", "11": "SPI_SCK", "12": "SPI_MOSI", "13": "PLL_LE", "14": "LOCK",
           "15": "+3V3A", "16": "+3V3A"}
    sch.add("U1", "SENTINEL:PLL_IntN", "PLL", TSSOP16, 104.14, 76.2, 0, pll, Description="Integer-N PLL, verify pin map")
    for ref, val, n1, n2, x, y in (("R3", "5.1k", "RSET", "GND", 81.28, 99.06), ("C4", "2.2n", "CP", "GND", 137.16, 99.06),
                                   ("R4", "3.3k", "CP", "LF_Z", 147.32, 99.06), ("C5", "22n", "LF_Z", "GND", 157.48, 99.06),
                                   ("R5", "6.8k", "CP", "VC", 167.64, 99.06), ("C6", "1n", "VC", "GND", 177.8, 99.06),
                                   ("C7", "100p", "CLK_RAW", "RFIN", 187.96, 99.06), ("C8", "100p", "RFINB", "GND", 198.12, 99.06)):
        sch.add(ref, "Device:C" if ref[0] == "C" else "Device:R", val, C0603 if ref[0] == "C" else R0603, x, y, 0,
                {"1": n1, "2": n2}, Description="Loop filter (100 Hz loop)" if ref in ("C4", "R4", "C5", "R5", "C6") else "")
    sch.add("Y1", "SENTINEL:VCXO", "122.88MHz", VCXO_FP, 162.56, 66.04, 0,
            {"1": "VC", "2": "GND", "3": "CLK_RAW", "4": "+3V3A"}, Description="122.88 MHz VCXO, low phase noise")
    sch.add("R6", "Device:R", "33", R0603, 187.96, 66.04, 90, {"1": "CLK_RAW", "2": "CLK"}, Description="Source termination")
    sch.add("U3", "74xGxx:74LVC1G175", "74LVC1G175", SC70_6, 104.14, 137.16, 0,
            {"1": "CLK", "3": "PPS", "4": "SYSREF_RAW", "6": "+3V3", "5": "+3V3", "2": "GND"},
            Description="SYSREF: PPS re-timed by CLK")
    sch.add("R7", "Device:R", "33", R0603, 132.08, 132.08, 90, {"1": "SYSREF_RAW", "2": "SYSREF"})
    # LVDS drivers and tile connectors
    groups = (("CLK", "CLK"), ("SYSREF", "SYS"), ("PPS", "PPS"))
    u = 4
    for gi, (src, tag) in enumerate(groups):
        for half in range(2):
            nets = {"1": "LVDS_EN", "8": "GND", "4": "+3V3", "5": "GND"}
            for k, (din, pp, pn) in enumerate((("2", "15", "16"), ("3", "14", "13"), ("6", "11", "12"), ("7", "10", "9"))):
                t = 4 * half + k + 1
                nets.update({din: src, pp: f"{tag}_P{t}", pn: f"{tag}_N{t}"})
            sch.add(f"U{u}", "Interface:SN65LVDS047D", "SN65LVDS047", SOIC16, 241.3 + 50.8 * gi, 60.96 + 76.2 * half, 0, nets,
                    Description=f"Quad LVDS driver, {src} to tiles {4 * half + 1}-{4 * half + 4}")
            u += 1
    for t in range(1, 9):
        sch.add(f"J{2 + t}", "Connector_Generic:Conn_02x05_Odd_Even", f"TILE{t}", HDR2x5, 406.4, 30.48 + 25.4 * (t - 1), 0,
                {"1": f"CLK_P{t}", "2": f"CLK_N{t}", "3": "GND", "4": "GND", "5": f"SYS_P{t}", "6": f"SYS_N{t}",
                 "7": "GND", "8": "GND", "9": f"PPS_P{t}", "10": f"PPS_N{t}"}, Description=f"Clock bundle to tile {t}")
    # controller
    sch.add("U10", "MCU_ST_STM32G031:STM32G031K8Tx" if False else "MCU_ST_STM32G0:STM32G031K8Tx", "STM32G031K8T6",
            "Package_QFP:LQFP-32_7x7mm_P0.8mm", 104.14, 210.82, 0, {
                "4": "+3V3", "5": "GND", "6": "NRST", "7": "LOCK", "8": "LVDS_EN", "9": "RS485_DI", "10": "RS485_RO",
                "11": "PLL_LE", "12": "SPI_SCK", "13": "PLL_CE", "14": "SPI_MOSI", "15": "LED_LOCK", "18": "RS485_DE",
                "24": "SWDIO", "25": "SWCLK", **{str(n): "NC" for n in (1, 2, 3, 16, 17, 20, 22, 23, 26, 27, 28, 29, 30, 31, 32)}},
            Description="Programs the PLL, reports lock, enables outputs")
    sch.add("U11", "Interface_UART:THVD1450D", "THVD1450", SOIC8, 162.56, 215.9, 0,
            {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND", "6": "RS485_A",
             "7": "RS485_B", "8": "+3V3"})
    sch.add("J11", "Connector_Generic:Conn_01x04", "RS485", HDR1x4, 198.12, 210.82, 0,
            {"1": "RS485_A", "2": "RS485_B", "3": "GND", "4": "NC"}, Description="To site timing controller")
    sch.add("J12", "Connector_Generic:Conn_01x04", "SWD", HDR1x4, 50.8, 200.66, 0,
            {"1": "+3V3", "2": "SWDIO", "3": "SWCLK", "4": "GND"})
    sch.add("J13", "Connector_Generic:Conn_01x02", "5V IN", "Connector_Molex:Molex_Mini-Fit_Jr_5566-02A_2x01_P4.20mm_Vertical",
            241.3, 228.6, 0, {"1": "+5V", "2": "GND"})
    for i, (ref, out) in enumerate((("U12", "+3V3"), ("U13", "+3V3A"))):
        sch.add(ref, "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", SOT23_5, 279.4 + 45.72 * i, 228.6, 0,
                {"1": "+5V", "3": "+5V", "2": "GND", "5": out}, Description="Analog rail for PLL/VCXO" if i else "")
    sch.add("R8", "Device:R", "1k", R0603, 50.8, 228.6, 0, {"1": "LED_LOCK", "2": "LED_A"})
    sch.add("D1", "Device:LED", "LOCK", "LED_SMD:LED_0603_1608Metric", 60.96, 228.6, 90, {"2": "LED_A", "1": "GND"})
    caps = [("1u", "+5V"), ("1u", "+3V3"), ("1u", "+5V"), ("1u", "+3V3A")] + [("100n", "+3V3")] * 9 + [("100n", "+3V3A")] * 3
    for i, (val, n1) in enumerate(caps):
        sch.add(f"C{9 + i}", "Device:C", val, C0603, 241.3 + 10.16 * (i % 12), 251.46 + 22.86 * (i // 12), 0,
                {"1": n1, "2": "GND"})
    sch.add("C25", "Device:C", "100n", C0603, 81.28, 236.22, 0, {"1": "NRST", "2": "GND"})
    for i in range(4):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad",
                355.6 + 12.7 * i, 254.0, 0, {"1": "GND"})
    sch.pwr_flag("GND", 22.86, 254.0)
    sch.pwr_flag("+5V", 35.56, 254.0)
    return sch


if __name__ == "__main__":
    write_project(build(), HERE, CUSTOM, "SENTINEL-UHF Clock & Timing Distribution")
