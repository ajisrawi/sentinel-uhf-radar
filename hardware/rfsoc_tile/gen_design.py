"""
SENTINEL-UHF RFSoC digitiser tile: carrier board for a commercial RFSoC system-on-module.

The SOM (RFSoC with its DDR, power tree and configuration flash) plugs into two
0.8 mm board-to-board connectors. This carrier provides:
  - 9 receive inputs (8 T/R modules + calibration): SMA -> 1:2 balun -> AC-coupled ADC pair
  - 9 transmit outputs: DAC pair -> centre-tapped balun (DAC bias) -> SMA
  - 8 RS-485 transceivers + TX_EN / FAULT lines to the tile backplane (40-pin cable, pin-for-pin
    with backplane J9), calibration-board control, PSU telemetry
  - clock bundle from the timing board (CLK, SYSREF, PPS as LVDS)
  - QSFP28 cage: 4 x 25 Gb/s to the face beamformer
  - 12 V in, 3.3 V / 3 A buck for transceivers and optics; the SOM takes 12 V directly
The SOM connector pin map is this project's own and must be mapped to the chosen
module's connector pinout (e.g. a ZU4xDR-based SOM) before release.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import fpgen as fp  # noqa: E402
from schgen import Schematic, custom_symbol, g_rect, write_project  # noqa: E402

PRO = "SENTINEL_TILE"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"
R0603, C0603, C1210 = "Resistor_SMD:R_0603_1608Metric", "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_1210_3225Metric"
SOIC8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
NCH = 9      # 8 element channels + calibration


def pin_map_a():
    """SOM connector A (2x40): data-converter pairs, each pair flanked by ground."""
    sig = []
    for c in range(NCH):
        sig += [f"ADC{c}_P", f"ADC{c}_N"]
    for c in range(NCH):
        sig += [f"DAC{c}_P", f"DAC{c}_N"]
    sig += ["CLK_P", "CLK_N", "SYSREF_P", "SYSREF_N"]           # 40 signals
    m, k = {}, 0
    for row in range(40):                                     # odd column: signal, even column: ground
        m[2 * row + 1] = sig[k] if k < len(sig) else "GND"
        m[2 * row + 2] = "GND"
        k += 1
    return m


def pin_map_b():
    """SOM connector B (2x50): control, optics, power."""
    sig = []
    for s in range(1, 9):
        sig += [f"TXD{s}", f"RXD{s}", f"DE{s}", f"TX_EN_T{s}", f"FAULT_N{s}"]
    sig += ["CAL_SEL0", "CAL_SEL1", "CAL_SEL2", "CAL_SW_EN", "CAL_INJ_MEAS", "PPS_P", "PPS_N",
            "PSU_TXD", "PSU_RXD", "PSU_DE", "QSFP_SCL", "QSFP_SDA", "QSFP_MODSEL", "QSFP_RESET", "QSFP_LPMODE",
            "QSFP_INT", "QSFP_PRS", "MGT_REFCLK_P", "MGT_REFCLK_N"]
    for l in range(4):
        sig += [f"QTX{l}_P", f"QTX{l}_N", f"QRX{l}_P", f"QRX{l}_N"]
    m = {}
    for i, s in enumerate(sig):                               # 75 signals on pins 1..75
        m[i + 1] = s
    for p in range(76, 101):
        m[p] = "+12V" if p <= 82 else "GND"
    return m


MAP_A, MAP_B = pin_map_a(), pin_map_b()
QSFP = {1: "GND", 2: "QTX1_N", 3: "QTX1_P", 4: "GND", 5: "QTX3_N", 6: "QTX3_P", 7: "GND", 8: "QSFP_MODSEL",
        9: "QSFP_RESET", 10: "+3V3", 11: "QSFP_SCL", 12: "QSFP_SDA", 13: "GND", 14: "QRX3_P", 15: "QRX3_N", 16: "GND",
        17: "QRX1_P", 18: "QRX1_N", 19: "GND", 20: "GND", 21: "QRX2_N", 22: "QRX2_P", 23: "GND", 24: "QRX0_N",
        25: "QRX0_P", 26: "GND", 27: "QSFP_PRS", 28: "QSFP_INT", 29: "+3V3", 30: "+3V3", 31: "QSFP_LPMODE",
        32: "GND", 33: "QTX2_P", 34: "QTX2_N", 35: "GND", 36: "QTX0_P", 37: "QTX0_N", 38: "GND"}


def footprints():
    out = HERE / "SENTINEL.pretty"
    for name, n in (("SOM_B2B_2x40_P0.8", 40), ("SOM_B2B_2x50_P0.8", 50)):
        b = ""
        L = (n - 1) * 0.8
        for i in range(n):
            x = -L / 2 + 0.8 * i
            b += fp.pad(2 * i + 1, x, -1.9, 0.45, 1.6) + fp.pad(2 * i + 2, x, 1.9, 0.45, 1.6)
        b += fp.npth(-L / 2 - 2.0, 0, 1.0) + fp.npth(L / 2 + 2.0, 0, 1.0)
        b += fp.rect("F.Fab", -L / 2 - 3, -2.5, L / 2 + 3, 2.5, 0.1) + fp.rect("F.CrtYd", -L / 2 - 3.5, -3.2, L / 2 + 3.5, 3.2, 0.05)
        fp.footprint(out, name, f"SOM board-to-board receptacle, 2x{n}, 0.8 mm pitch", b, 3.2)
    b = ""
    for i in range(19):                                       # QSFP28 host connector, 0.8 mm pitch, two rows
        b += fp.pad(i + 1, -7.2 + 0.8 * i, -3.0, 0.5, 1.8) + fp.pad(38 - i, -7.2 + 0.8 * i, 3.0, 0.5, 1.8)
    b += fp.rect("F.Fab", -9.75, -6, 9.75, 6, 0.1) + fp.rect("F.CrtYd", -10.5, -6.5, 10.5, 6.5, 0.05)
    fp.footprint(out, "QSFP28_Host_38P", "QSFP28 host connector (cage mounts over it)", b, 6.5)
    b = fp.rect("F.Fab", -2, -2, 2, 2, 0.1)
    for num, x, y in ((1, -1.6, -0.95), (2, -1.6, 0), (3, -1.6, 0.95), (4, 1.6, 0.95), (5, 1.6, 0), (6, 1.6, -0.95)):
        b += fp.pad(num, x, y, 1.0, 0.6)
    b += fp.rect("F.CrtYd", -2.6, -2.2, 2.6, 2.2, 0.05)
    fp.footprint(out, "Balun_SMD_6P_3.8x3.8", "RF transformer 1:2, 6-pad (TCM2-43X class)", b, 2.2)


def som_symbol(name, mapping, rows):
    pins = []
    for p in sorted(mapping):
        side = -1 if p % 2 else 1
        row = (p - 1) // 2
        pins.append((p, mapping[p] if mapping[p] != "GND" else "GND", side * 12.7, rows * 1.27 - 2.54 * row, 0 if side < 0 else 180, 2.54))
    return custom_symbol(name, "J", name, "", "SOM board-to-board connector (project pin map)",
                         pins, [g_rect(-10.16, rows * 1.27 + 2.54, 10.16, -rows * 1.27)], show_pin_numbers=True)


CUSTOM = [
    som_symbol("SOM_A", MAP_A, 40),
    som_symbol("SOM_B", MAP_B, 50),
    custom_symbol("QSFP28", "J", "QSFP28", "SENTINEL:QSFP28_Host_38P", "QSFP28 host connector",
                  [(p, QSFP[p], -12.7 if p <= 19 else 12.7, 22.86 - 2.54 * ((p - 1) % 19), 0 if p <= 19 else 180, 2.54)
                   for p in QSFP], [g_rect(-10.16, 25.4, 10.16, -25.4)], show_pin_numbers=True),
    custom_symbol("Balun_CT", "T", "Balun_CT", "SENTINEL:Balun_SMD_6P_3.8x3.8", "1:2 RF transformer with centre tap",
                  [(1, "UNBAL", -7.62, 2.54, 0, 2.54), (2, "GND", -7.62, -2.54, 0, 2.54), (3, "SEC_P", 7.62, 2.54, 180, 2.54),
                   (5, "CT", 7.62, 0, 180, 2.54), (4, "SEC_N", 7.62, -2.54, 180, 2.54), (6, "NC", 0, -7.62, 90, 2.54)],
                  [g_rect(-5.08, 5.08, 5.08, -5.08)]),
]


def build():
    sch = Schematic(PRO, "SENTINEL-UHF RFSoC Digitiser Tile (SOM carrier)", "A1", CUSTOM)
    sch.text("RFSoC TILE CARRIER  -  9 RX + 9 TX RF channels, 8 module links, QSFP28, clock", 20, 22, 2.5)
    sch.add("J1", "SENTINEL:SOM_A", "SOM CONN A", "SENTINEL:SOM_B2B_2x40_P0.8", 381.0, 152.4, 0,
            {str(k): v for k, v in MAP_A.items()}, Description="SOM data-converter connector")
    sch.add("J2", "SENTINEL:SOM_B", "SOM CONN B", "SENTINEL:SOM_B2B_2x50_P0.8", 508.0, 177.8, 0,
            {str(k): v for k, v in MAP_B.items()}, Description="SOM control / optics / power connector")
    for c in range(NCH):
        y = 50.8 + 22.86 * c
        tag = "CAL" if c == 8 else str(c + 1)
        # receive: SMA -> balun -> AC-coupled ADC pair
        sch.add(f"J{10 + c}", "Connector:Conn_Coaxial", f"RX{tag}", SMA, 30.48, y, 180, {"1": f"RXIN{c}", "2": "GND"},
                Description=f"From T/R module {tag} RX_OUT" if c < 8 else "From calibration board MEASURE")
        sch.add(f"T{1 + c}", "SENTINEL:Balun_CT", "1:2", "SENTINEL:Balun_SMD_6P_3.8x3.8", 60.96, y, 0,
                {"1": f"RXIN{c}", "2": "GND", "3": f"ADCB{c}_P", "4": f"ADCB{c}_N", "5": f"ADC_CT{c}", "6": "NC"},
                Description="ADC input transformer, 50 -> 100 ohm")
        sch.add(f"C{100 + c}", "Device:C", "100n", C0603, 86.36, y - 5.08, 90, {"1": f"ADCB{c}_P", "2": f"ADC{c}_P"})
        sch.add(f"C{120 + c}", "Device:C", "100n", C0603, 86.36, y + 5.08, 90, {"1": f"ADCB{c}_N", "2": f"ADC{c}_N"})
        sch.add(f"C{140 + c}", "Device:C", "100n", C0603, 101.6, y, 0, {"1": f"ADC_CT{c}", "2": "GND"},
                Description="Centre-tap AC ground")
        # transmit: DAC pair -> centre-tapped balun (DAC_AVTT bias) -> SMA
        sch.add(f"T{11 + c}", "SENTINEL:Balun_CT", "1:2", "SENTINEL:Balun_SMD_6P_3.8x3.8", 680.72, y, 180,
                {"1": f"TXOUT{c}", "2": "GND", "3": f"DAC{c}_P", "4": f"DAC{c}_N", "5": "DAC_AVTT", "6": "NC"},
                Description="DAC output transformer, centre tap biases the DAC")
        sch.add(f"J{20 + c}", "Connector:Conn_Coaxial", f"TX{tag}", SMA, 711.2, y, 0, {"1": f"TXOUT{c}", "2": "GND"},
                Description=f"To T/R module {tag} TX_IN" if c < 8 else "To calibration board INJECT")
    sch.add("C160", "Device:C", "10u", C1210, 655.32, 264.16, 0, {"1": "DAC_AVTT", "2": "GND"})
    sch.add("C161", "Device:C", "100n", C0603, 665.48, 264.16, 0, {"1": "DAC_AVTT", "2": "GND"})
    sch.add("R160", "Device:R", "0", "Resistor_SMD:R_0805_2012Metric", 645.16, 264.16, 0, {"1": "+3V3", "2": "DAC_AVTT"},
            Description="DAC_AVTT from 3.3 V (fit per SOM DAC mode: 2.5 V or 3.0 V)")
    # module links: RS-485 transceivers
    bp = {}
    for s in range(1, 9):
        x, y = 152.4 + 63.5 * ((s - 1) % 4), 360.68 + 50.8 * ((s - 1) // 4)
        sch.add(f"U{s}", "Interface_UART:THVD1450D", "THVD1450", SOIC8, x, y, 0,
                {"1": f"RXD{s}", "2": f"DE{s}", "3": f"DE{s}", "4": f"TXD{s}", "5": "GND",
                 "6": f"RS485_A{s}", "7": f"RS485_B{s}", "8": "+3V3"}, Description=f"RS-485 to T/R module {s}")
        sch.add(f"C{s}", "Device:C", "100n", C0603, x + 20.32, y, 0, {"1": "+3V3", "2": "GND"})
        n = s - 1
        base = 2 * (4 * (n % 4)) + (1 if s <= 4 else 2)   # left column slots 1-4, right column 5-8
        bp.update({str(base): f"RS485_A{s}", str(base + 2): f"RS485_B{s}",
                    str(base + 4): f"TX_EN_T{s}", str(base + 6): f"FAULT_N{s}"})
    bp.update({str(k): "GND" for k in range(33, 41)})
    sch.add("J3", "Connector_Generic:Conn_02x20_Odd_Even", "BACKPLANE", "Connector_PinHeader_2.54mm:PinHeader_2x20_P2.54mm_Vertical",
            431.8, 381.0, 0, bp, Description="Cable to tile backplane J9 (pin-for-pin)")
    sch.add("J4", "Connector_Generic:Conn_02x05_Odd_Even", "CLOCK", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
            508.0, 330.2, 0, {"1": "CLK_P", "2": "CLK_N", "3": "GND", "4": "GND", "5": "SYSREF_P", "6": "SYSREF_N",
                              "7": "GND", "8": "GND", "9": "PPS_P", "10": "PPS_N"}, Description="From clock board")
    for i, nn in enumerate(("CLK", "SYSREF", "PPS")):
        sch.add(f"R{10 + i}", "Device:R", "100", R0603, 551.18 + 10.16 * i, 330.2, 0, {"1": f"{nn}_P", "2": f"{nn}_N"},
                Description="LVDS receiver termination" if nn == "PPS" else "LVDS termination (DNP if SOM terminates)")
    sch.add("J5", "Connector_Generic:Conn_02x05_Odd_Even", "CAL CTRL", "Connector_PinHeader_2.54mm:PinHeader_2x05_P2.54mm_Vertical",
            508.0, 381.0, 0, {"1": "+3V3", "3": "CAL_SEL0", "5": "CAL_SEL1", "7": "CAL_SEL2", "9": "CAL_SW_EN",
                              "2": "GND", "4": "GND", "6": "CAL_INJ_MEAS", "8": "GND", "10": "GND"},
            Description="To calibration board J11")
    sch.add("U9", "Interface_UART:THVD1450D", "THVD1450", SOIC8, 571.5, 381.0, 0,
            {"1": "PSU_RXD", "2": "PSU_DE", "3": "PSU_DE", "4": "PSU_TXD", "5": "GND", "6": "PSU_A", "7": "PSU_B", "8": "+3V3"},
            Description="RS-485 to subarray PSU")
    sch.add("C9", "Device:C", "100n", C0603, 591.82, 381.0, 0, {"1": "+3V3", "2": "GND"})
    sch.add("J6", "Connector_Generic:Conn_01x04", "PSU LINK", "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
            612.14, 381.0, 0, {"1": "PSU_A", "2": "PSU_B", "3": "GND", "4": "NC"})
    sch.add("J7", "SENTINEL:QSFP28", "QSFP28", "SENTINEL:QSFP28_Host_38P", 635.0, 177.8, 0, {str(k): v for k, v in QSFP.items()},
            Description="QSFP28 to face beamformer, 4 x 25 Gb/s")
    for i in range(4):
        sch.add(f"R{20 + i}", "Device:R", "4.7k", R0603, 668.02 + 10.16 * i, 223.52, 0,
                {"1": "+3V3", "2": ("QSFP_SCL", "QSFP_SDA", "QSFP_INT", "QSFP_PRS")[i]})
    for i in range(3):
        sch.add(f"C{10 + i}", "Device:C", "10u" if i == 0 else "100n", C1210 if i == 0 else C0603, 609.6 + 10.16 * i, 223.52, 0,
                {"1": "+3V3", "2": "GND"}, Description="QSFP supply filter" if i == 0 else "")
    sch.add("R24", "Device:R", "100", R0603, 599.44, 162.56, 0, {"1": "MGT_REFCLK_P", "2": "MGT_REFCLK_N"},
            Description="MGT reference clock termination (refclk from SOM oscillator)")
    # power
    sch.add("J8", "Connector_Generic:Conn_01x02", "12V IN", "Connector_Molex:Molex_Mini-Fit_Jr_5566-02A_2x01_P4.20mm_Vertical",
            152.4, 482.6, 0, {"1": "+12V", "2": "GND"}, Description="12 V from subarray PSU aux, 4 A")
    sch.add("U10", "Regulator_Switching:LMR33630ADDA", "LMR33630", "Package_SO:Texas_HSOP-8-1EP_3.9x4.9mm_P1.27mm_ThermalVias",
            228.6, 482.6, 0, {"2": "+12V", "3": "+12V", "1": "GND", "4": "PG_3V3", "5": "FB_3V3", "6": "VCC_BUCK",
                              "7": "BOOT_3V3", "8": "SW_3V3"}, Description="12 V -> 3.3 V, 3 A")
    parts = [("C20", "Device:C", "10u 25V", C1210, "+12V", "GND"), ("C21", "Device:C", "100n", C0603, "BOOT_3V3", "SW_3V3"),
             ("C22", "Device:C", "1u", C0603, "VCC_BUCK", "GND"), ("L1", "Device:L", "4.7u", "Inductor_SMD:L_1210_3225Metric", "SW_3V3", "+3V3"),
             ("R25", "Device:R", "100k", R0603, "+3V3", "FB_3V3"), ("R26", "Device:R", "43.2k", R0603, "FB_3V3", "GND"),
             ("C23", "Device:C", "22u", C1210, "+3V3", "GND"), ("C24", "Device:C", "22u", C1210, "+3V3", "GND"),
             ("R27", "Device:R", "100k", R0603, "+3V3", "PG_3V3"), ("C25", "Device:C", "22u 25V", C1210, "+12V", "GND")]
    for i, (ref, lib, val, fpn, n1, n2) in enumerate(parts):
        sch.add(ref, lib, val, fpn, 266.7 + 10.16 * i, 487.68, 0, {"1": n1, "2": n2})
    for i in range(4):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", "MountingHole:MountingHole_3.2mm_M3_Pad",
                431.8 + 12.7 * i, 482.6, 0, {"1": "GND"})
    sch.pwr_flag("GND", 22.86, 482.6)
    sch.pwr_flag("+12V", 35.56, 482.6)
    sch.pwr_flag("+3V3", 48.26, 482.6)
    return sch


if __name__ == "__main__":
    footprints()
    write_project(build(), HERE, CUSTOM, "SENTINEL-UHF RFSoC Digitiser Tile")
