"""
SENTINEL-UHF subarray power supply: 380 VDC site bus -> 50 V drain bus for one tile.

Sizing (8 T/R modules): 87 A / 4.4 kW during a 16 ms pulse, 870 W average.
Two 600 W isolated full-brick converters (current-shared, OR-ed outputs) cover
the average with margin; the pulse energy (70 J) comes from a 0.3-0.6 F
capacitor bank mounted on the chassis and bolted to the M6 output studs, which
also feed the backplane directly so pulse current never crosses this PCB.

Primary (380 V) side: input fuse, NTC inrush limiter bypassed by a relay once
the bulk film capacitors are charged, brick ON/OFF through optocouplers.
All primary nets are named HV_* and get 2.5 mm clearance through the HV net class.
Secondary side: STM32G031 supervisor (output voltage, brick current, two brick
temperatures), RS-485 to the tile controller, 12 V aux converter for the modules.
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import fpgen as fp  # noqa: E402
from schgen import Schematic, custom_symbol, g_rect, write_project  # noqa: E402

PRO = "SENTINEL_PSU"
R0603, R0805, R2512 = "Resistor_SMD:R_0603_1608Metric", "Resistor_SMD:R_0805_2012Metric", "Resistor_SMD:R_2512_6332Metric"
C0603, C1210 = "Capacitor_SMD:C_0603_1608Metric", "Capacitor_SMD:C_1210_3225Metric"
CP18 = "Capacitor_THT:CP_Radial_D18.0mm_P7.50mm"
FILM = "Capacitor_THT:C_Rect_L26.5mm_W10.5mm_P22.50mm_MKS4"
SOT23, SOIC8, LQFP32 = "Package_TO_SOT_SMD:SOT-23", "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "Package_QFP:LQFP-32_7x7mm_P0.8mm"
HDR1x4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
MF2 = "Connector_Molex:Molex_Mini-Fit_Jr_5566-02A_2x01_P4.20mm_Vertical"


def footprints():
    out = HERE / "SENTINEL.pretty"
    # DOSA-style full brick (116.8 x 61 mm), through-hole pins
    b = fp.rect("F.Fab", -58.4, -30.5, 58.4, 30.5, 0.1)
    for num, x, y, d, dr in ((1, -53.34, -17.78, 3.2, 1.6), (2, -53.34, -7.62, 2.0, 1.0), (3, -53.34, 17.78, 3.2, 1.6),
                             (4, 53.34, 20.32, 4.5, 2.5), (5, 53.34, 10.16, 2.0, 1.0), (6, 53.34, 2.54, 2.0, 1.0),
                             (7, 53.34, -5.08, 2.0, 1.0), (8, 53.34, -15.24, 4.5, 2.5), (9, 53.34, -25.4, 2.0, 1.0)):
        b += fp.tht(num, x, y, d, dr)
    b += fp.rect("F.CrtYd", -59.0, -31.0, 59.0, 31.0, 0.05)
    fp.footprint(out, "Brick_Full_THT", "Isolated DC-DC full brick, 380 V in, 50 V 600 W out", b, 31.0, attr="through_hole")
    # 1/16 brick (33 x 23 mm)
    b = fp.rect("F.Fab", -16.5, -11.5, 16.5, 11.5, 0.1)
    for num, x, y in ((1, -15.24, -7.62), (2, -15.24, 0), (3, -15.24, 7.62), (4, 15.24, 7.62), (5, 15.24, 0), (6, 15.24, -7.62)):
        b += fp.tht(num, x, y, 2.2, 1.1)
    b += fp.rect("F.CrtYd", -17.0, -12.0, 17.0, 12.0, 0.05)
    fp.footprint(out, "Brick_16_THT", "DC-DC 1/16 brick, 36-75 V in, 12 V 4 A out", b, 12.0, attr="through_hole")
    b = fp.tht(1, 0, 0, 12.0, 6.5) + fp.rect("F.CrtYd", -6.5, -6.5, 6.5, 6.5, 0.05)
    fp.footprint(out, "Stud_M6", "M6 press-fit busbar stud, 60 A", b, 6.5, attr="through_hole")
    b = fp.tht(1, -11.3, 0, 3.0, 1.5) + fp.tht(2, 11.3, 0, 3.0, 1.5) + fp.rect("F.Fab", -13, -3, 13, 3, 0.1)
    b += fp.rect("F.CrtYd", -13.5, -3.5, 13.5, 3.5, 0.05)
    fp.footprint(out, "Fuse_Clips_5x20", "5 x 20 mm fuse clips, 500 V", b, 3.5, attr="through_hole")
    b = fp.tht(1, -3.75, 0, 2.4, 1.2) + fp.tht(2, 3.75, 0, 2.4, 1.2) + fp.rect("F.CrtYd", -8.5, -4, 8.5, 4, 0.05)
    fp.footprint(out, "NTC_Disc_D15_P7.5", "Inrush NTC disc 15 mm", b, 4.0, attr="through_hole")
    b = fp.tht(1, -3.81, 0, 3.2, 1.6) + fp.tht(2, 3.81, 0, 3.2, 1.6) + fp.rect("F.CrtYd", -7.5, -5, 7.5, 5, 0.05)
    fp.footprint(out, "Terminal_HV_2P_7.62", "2-pole 1000 V terminal block, 7.62 mm pitch", b, 5.0, attr="through_hole")


CUSTOM = [
    custom_symbol("Brick_Full", "U", "Brick_Full", "SENTINEL:Brick_Full_THT", "Isolated DC-DC full brick",
                  [(1, "+IN", -12.7, 7.62, 0, 2.54), (2, "ON/OFF", -12.7, 0, 0, 2.54), (3, "-IN", -12.7, -7.62, 0, 2.54),
                   (8, "+OUT", 12.7, 10.16, 180, 2.54), (7, "+S", 12.7, 5.08, 180, 2.54), (6, "TRIM", 12.7, 0, 180, 2.54),
                   (9, "SHARE", 12.7, -2.54, 180, 2.54), (5, "-S", 12.7, -5.08, 180, 2.54), (4, "-OUT", 12.7, -10.16, 180, 2.54)],
                  [g_rect(-10.16, 12.7, 10.16, -12.7)]),
    custom_symbol("Brick_16", "U", "Brick_16", "SENTINEL:Brick_16_THT", "Non-isolated/isolated DC-DC 1/16 brick",
                  [(1, "+IN", -10.16, 5.08, 0, 2.54), (2, "ON/OFF", -10.16, 0, 0, 2.54), (3, "-IN", -10.16, -5.08, 0, 2.54),
                   (6, "+OUT", 10.16, 5.08, 180, 2.54), (5, "TRIM", 10.16, 0, 180, 2.54), (4, "-OUT", 10.16, -5.08, 180, 2.54)],
                  [g_rect(-7.62, 7.62, 7.62, -7.62)]),
]


def build():
    sch = Schematic(PRO, "SENTINEL-UHF Subarray Power Supply, 380 V -> 50 V", "A2", CUSTOM)
    sch.text("PRIMARY 380 VDC  (HV_* nets: 2.5 mm clearance, isolated from secondary)", 20, 22, 2.5)
    sch.rect(15, 27, 175, 205)
    sch.add("J1", "Connector_Generic:Conn_01x02", "380VDC IN", "SENTINEL:Terminal_HV_2P_7.62", 25.4, 50.8, 0,
            {"1": "HV_IN_P", "2": "HV_N"}, Description="380 VDC site distribution bus")
    sch.add("F1", "Device:Fuse", "6.3A 500V", "SENTINEL:Fuse_Clips_5x20", 50.8, 50.8, 90, {"1": "HV_IN_P", "2": "HV_F"},
            Description="Input fuse, 500 VDC rated")
    sch.add("RT1", "Device:Thermistor_NTC", "10R NTC", "SENTINEL:NTC_Disc_D15_P7.5", 76.2, 50.8, 90, {"1": "HV_F", "2": "HV_P"},
            Description="Inrush limiter, bypassed by K1 after precharge")
    sch.add("K1", "Relay:G2RL-1A", "G2RL-1A 12V", "Relay_THT:Relay_SPST_Omron_G2RL-1A", 76.2, 81.28, 0,
            {"13": "HV_F", "14": "HV_P", "A1": "+12V", "A2": "RLY_DRV"}, Description="Inrush bypass relay, 5 kV coil-contact")
    for i in range(2):
        sch.add(f"C{i + 1}", "Device:C", "10u 450V", FILM, 104.14 + 12.7 * i, 50.8, 0, {"1": "HV_P", "2": "HV_N"},
                Description="Input film capacitor")
    for i in range(2):
        y = 116.84 + 55.88 * i
        sch.add(f"U{i + 1}", "SENTINEL:Brick_Full", "380V->50V 600W", "SENTINEL:Brick_Full_THT", 165.1, y, 0,
                {"1": "HV_P", "2": f"HV_ONOFF{i + 1}", "3": "HV_N", "8": f"BRICK{i + 1}_OUT", "7": "VOUT_50V",
                 "6": f"TRIM{i + 1}", "9": "SHARE", "5": "GND", "4": "GND"},
                Description="Isolated full brick, 380 V in, 50 V / 12 A out, current share")
        sch.add(f"U{3 + i}", "Isolator:PC817", "PC817", "Package_DIP:SMDIP-4_W7.62mm", 104.14, y, 0,
                {"1": f"ON_A{i + 1}", "2": "GND", "3": "HV_N", "4": f"HV_ONOFF{i + 1}"},
                Description="Brick enable across the isolation barrier")
        sch.add(f"R{1 + i}", "Device:R", "470", R0603, 76.2, y, 90, {"1": f"ON{i + 1}", "2": f"ON_A{i + 1}"})
        sch.add(f"R{3 + i}", "Device:R", "trim", R0603, 213.36, y, 0, {"1": f"TRIM{i + 1}", "2": "GND"},
                Description="Trim-up to 50.0 V per vendor formula", MPN="value per brick datasheet")
        sch.add(f"D{1 + i}", "Device:D_Schottky", "100V 60A", "Package_TO_SOT_THT:TO-247-2_Vertical", 228.6, y - 7.62, 0,
                {"2": f"BRICK{i + 1}_OUT", "1": "VOR"}, Description="Output OR-ing diode")
        sch.add(f"TH{1 + i}", "Device:Thermistor_NTC", "10k NTC", R0603, 251.46, y + 10.16, 0,
                {"1": f"NTC{i + 1}", "2": "GND"}, Description=f"Brick {i + 1} baseplate temperature")
        sch.add(f"R{5 + i}", "Device:R", "10k", R0603, 261.62, y + 10.16, 0, {"1": "+3V3", "2": f"NTC{i + 1}"})
    sch.text("SECONDARY 50 V  (pulse current flows bank <-> backplane through the studs, not this PCB)", 185, 22, 2.5)
    sch.add("R7", "Device:R", "1m", R2512, 266.7, 60.96, 90, {"1": "VOR", "2": "VOUT_50V"}, Description="Brick current shunt")
    sch.add("U9", "Amplifier_Current:INA240A1D", "INA240A1", SOIC8, 266.7, 88.9, 0,
            {"8": "VOR", "1": "VOUT_50V", "6": "+3V3", "2": "GND", "3": "GND", "7": "GND", "5": "I_OUT_V"})
    sch.add("R8", "Device:R", "1k", R0603, 289.56, 88.9, 90, {"1": "I_OUT_V", "2": "I_OUT"})
    for i in range(4):
        sch.add(f"C{3 + i}", "Device:C_Polarized", "1000u 63V", CP18, 304.8 + 12.7 * i, 60.96, 0,
                {"1": "VOUT_50V", "2": "GND"}, Description="Output bulk")
    sch.add("C7", "Device:C", "10u 100V", C1210, 355.6, 60.96, 0, {"1": "VOUT_50V", "2": "GND"})
    sch.add("C8", "Device:C", "10n", C0603, 304.8, 88.9, 0, {"1": "I_OUT", "2": "GND"})
    sch.add("J2", "Connector_Generic:Conn_01x01", "+50V STUD", "SENTINEL:Stud_M6", 381.0, 55.88, 0, {"1": "VOUT_50V"},
            Description="M6 stud: capacitor bank + and backplane 50 V")
    sch.add("J3", "Connector_Generic:Conn_01x01", "0V STUD", "SENTINEL:Stud_M6", 381.0, 71.12, 0, {"1": "GND"},
            Description="M6 stud: return")
    sch.add("R9", "Device:R", "200k", R0603, 330.2, 88.9, 0, {"1": "VOUT_50V", "2": "VOUT_MON"})
    sch.add("R10", "Device:R", "10k", R0603, 340.36, 88.9, 0, {"1": "VOUT_MON", "2": "GND"})
    # 12 V aux and logic supply
    sch.add("U5", "SENTINEL:Brick_16", "48V->12V 50W", "SENTINEL:Brick_16_THT", 210.82, 228.6, 0,
            {"1": "VOUT_50V", "2": "NC", "3": "GND", "6": "+12V", "5": "NC", "4": "GND"},
            Description="12 V aux for modules and relay")
    sch.add("C9", "Device:C", "22u 25V", C1210, 238.76, 233.68, 0, {"1": "+12V", "2": "GND"})
    sch.add("J4", "Connector_Generic:Conn_01x02", "12V OUT", MF2, 254.0, 228.6, 0, {"1": "+12V", "2": "GND"},
            Description="12 V aux to backplane")
    sch.add("U6", "Regulator_Linear:LM1117DT-3.3", "LM1117-3.3", "Package_TO_SOT_SMD:TO-252-3_TabPin2", 289.56, 228.6, 0,
            {"3": "+12V", "2": "+3V3", "1": "GND"})
    for i, (v, n1) in enumerate((("10u", "+12V"), ("10u", "+3V3"), ("100n", "+3V3"), ("100n", "+3V3"))):
        sch.add(f"C{10 + i}", "Device:C", v, C1210 if v == "10u" else C0603, 312.42 + 10.16 * i, 233.68, 0, {"1": n1, "2": "GND"})
    # relay driver
    sch.add("Q1", "Transistor_FET:2N7002", "2N7002", SOT23, 116.84, 228.6, 0, {"1": "RLY_G", "2": "GND", "3": "RLY_DRV"})
    sch.add("D3", "Device:D", "1N4148W", "Diode_SMD:D_SOD-123", 93.98, 223.52, 90, {"2": "RLY_DRV", "1": "+12V"},
            Description="Relay flyback")
    sch.add("R11", "Device:R", "100", R0603, 132.08, 228.6, 90, {"1": "RLY_EN", "2": "RLY_G"})
    sch.add("R12", "Device:R", "100k", R0603, 142.24, 233.68, 0, {"1": "RLY_G", "2": "GND"})
    # supervisor
    sch.add("U7", "MCU_ST_STM32G0:STM32G031K8Tx", "STM32G031K8T6", LQFP32, 345.44, 152.4, 0, {
        "4": "+3V3", "5": "GND", "6": "NRST", "7": "VOUT_MON", "8": "I_OUT", "9": "RS485_DI", "10": "RS485_RO",
        "11": "NTC1", "12": "NTC2", "13": "ON1", "14": "ON2", "15": "RLY_EN", "16": "LED_DRV", "17": "RS485_DE",
        "24": "SWDIO", "25": "SWCLK", "1": "NC", "2": "NC", "3": "NC", "18": "NC", "20": "NC", "22": "NC",
        "23": "NC", "26": "NC", "27": "NC", "28": "NC", "29": "NC", "30": "NC", "31": "NC", "32": "NC"},
        Description="Supervisor: soft start, OV/UV, current, temperature, telemetry")
    sch.add("U8", "Interface_UART:THVD1450D", "THVD1450", SOIC8, 302.26, 177.8, 0,
            {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND", "6": "RS485_A",
             "7": "RS485_B", "8": "+3V3"})
    sch.add("J5", "Connector_Generic:Conn_01x04", "RS485", HDR1x4, 266.7, 167.64, 0,
            {"1": "RS485_A", "2": "RS485_B", "3": "GND", "4": "NC"}, Description="Telemetry to tile controller")
    sch.add("J6", "Connector_Generic:Conn_01x04", "SWD", HDR1x4, 391.16, 132.08, 0,
            {"1": "+3V3", "2": "SWDIO", "3": "SWCLK", "4": "GND"})
    sch.add("C14", "Device:C", "100n", C0603, 391.16, 160.02, 0, {"1": "NRST", "2": "GND"})
    sch.add("R13", "Device:R", "1k", R0603, 391.16, 177.8, 0, {"1": "LED_DRV", "2": "LED_A"})
    sch.add("D4", "Device:LED", "GRN", "LED_SMD:LED_0603_1608Metric", 401.32, 177.8, 90, {"2": "LED_A", "1": "GND"})
    for i in range(4):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M4", "MountingHole:MountingHole_3.2mm_M3_Pad",
                358.14 + 12.7 * i, 228.6, 0, {"1": "GND"})
    sch.pwr_flag("GND", 22.86, 228.6)
    sch.pwr_flag("+12V", 35.56, 228.6)
    sch.pwr_flag("HV_N", 48.26, 228.6)
    sch.pwr_flag("HV_P", 60.96, 228.6)
    sch.pwr_flag("VOUT_50V", 73.66, 228.6)
    return sch


if __name__ == "__main__":
    footprints()
    write_project(build(), HERE, CUSTOM, "SENTINEL-UHF Subarray Power Supply")
