"""
SENTINEL-UHF transmit/receive module (one per array element, 2,587 per face).

Generates:
  SENTINEL.kicad_sym      custom symbols for the RF parts
  SENTINEL_TRM.kicad_sch  the full module schematic (A1, single sheet)
  expected_nets.json      intended connectivity, checked by verify_netlist.py

Signal chain: RFSoC DAC (0 dBm) -> gain block -> 3 dB pad -> 10 W GaN driver
-> 300 W GaN final -> circulator -> 30 dB coupler -> antenna (N-type).
Receive: circulator port 3 -> two-stage limiter -> LNA -> SAW BPF -> gain
block -> RFSoC ADC. Coupler ports feed power detectors and a calibration port.
Control: STM32G031 monitors drain current, VSWR, temperature and gate bias,
sets gate voltages through two DACs and owns the drain-switch interlock.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))

from schgen import Chain, Schematic, custom_symbol, g_circle, g_poly, g_rect, g_text  # noqa: E402
from sexpr import Sym, dumps  # noqa: E402

# ------------------------------------------------------------------ footprints
R0603, R0805, R1206, R2512 = (f"Resistor_SMD:R_{s}" for s in
                              ("0603_1608Metric", "0805_2012Metric", "1206_3216Metric", "2512_6332Metric"))
C0603, C0805, C1206, C1210, C2220 = (f"Capacitor_SMD:C_{s}" for s in
                                     ("0603_1608Metric", "0805_2012Metric", "1206_3216Metric",
                                      "1210_3225Metric", "2220_5750Metric"))
CP10 = "Capacitor_SMD:CP_Elec_10x10.5"
L0603, L0805, L1210, L1812 = (f"Inductor_SMD:L_{s}" for s in
                              ("0603_1608Metric", "0805_2012Metric", "1210_3225Metric", "1812_4532Metric"))
SOD323, DSMA, DSMB = "Diode_SMD:D_SOD-323", "Diode_SMD:D_SMA", "Diode_SMD:D_SMB"
LED0603 = "LED_SMD:LED_0603_1608Metric"
SOT23, SOT23_5, SOT23_6, SOT89 = (f"Package_TO_SOT_SMD:{s}" for s in ("SOT-23", "SOT-23-5", "SOT-23-6", "SOT-89-3"))
SC70_6, TO252 = "Package_TO_SOT_SMD:SOT-363_SC-70-6", "Package_TO_SOT_SMD:TO-252-2"
SOIC8, LQFP32 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "Package_QFP:LQFP-32_7x7mm_P0.8mm"
SMA = "Connector_Coaxial:SMA_Amphenol_132289_EdgeMount"
HDR2x8 = "Connector_PinHeader_2.54mm:PinHeader_2x08_P2.54mm_Vertical"
HDR1x4 = "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical"
MINIFIT = "Connector_Molex:Molex_Mini-Fit_Jr_5566-02A_2x01_P4.20mm_Vertical"
MH = "MountingHole:MountingHole_3.2mm_M3_Pad"
FP_PA, FP_DRV = "SENTINEL:GaN_Flange_780", "SENTINEL:GaN_Flange_440166"
FP_CIRC, FP_CPL = "SENTINEL:Circulator_DropIn_32mm", "SENTINEL:DirCoupler_SMD_12x6"
FP_BPF, FP_N = "SENTINEL:BPF_SMD_5x5", "SENTINEL:N_EdgeLaunch"


# ------------------------------------------------------------------ custom symbols
def arc_pts(r, a0, a1, n=7):
    return [(round(r * math.cos(math.radians(a0 + (a1 - a0) * i / (n - 1))), 3),
             round(r * math.sin(math.radians(a0 + (a1 - a0) * i / (n - 1))), 3)) for i in range(n)]


AMP = [g_poly([(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)])]
CUSTOM = [
    custom_symbol("GainBlock", "U", "GainBlock", "Package_TO_SOT_SMD:SOT-89-3",
                  "Cascadable MMIC gain block, bias through RF output",
                  [(1, "RFIN", -7.62, 0, 0, 2.54), (3, "RFOUT", 7.62, 0, 180, 2.54), (2, "GND", 0, -7.62, 90, 5.08)],
                  AMP, show_pin_names=False),
    custom_symbol("LNA", "U", "LNA", "Package_TO_SOT_SMD:SOT-89-3",
                  "Low-noise amplifier MMIC, bias through RF output",
                  [(1, "RFIN", -7.62, 0, 0, 2.54), (3, "RFOUT", 7.62, 0, 180, 2.54), (2, "GND", 0, -7.62, 90, 5.08)],
                  AMP + [g_text("LNA", -1.5, 0, 1.016)], show_pin_names=False),
    custom_symbol("GaN_HEMT", "Q", "GaN_HEMT", "", "GaN on SiC HEMT, depletion mode, source on flange",
                  [(1, "G", -7.62, 0, 0, 2.54), (2, "D", 7.62, 0, 180, 2.54), (3, "S", 0, -7.62, 90, 2.54)],
                  [g_rect(-5.08, 5.08, 5.08, -5.08), g_text("GaN", 0, 2.6, 1.27)],
                  ref_at=(0, 6.35, None), val_at=(6.35, -3.81, "left")),
    custom_symbol("Circulator", "U", "Circulator", "", "Drop-in ferrite circulator, 1->2->3",
                  [(1, "P1", -7.62, 0, 0, 2.54), (2, "P2", 7.62, 0, 180, 2.54),
                   (3, "P3", 0, -7.62, 90, 2.54), (4, "GND", 0, 7.62, 270, 2.54)],
                  [g_circle(0, 0, 5.08), g_poly(arc_pts(2.8, 150, 30), fill="none"),
                   g_poly([(2.0, 2.6), (2.42, 1.4), (1.2, 1.2)], fill="none")],
                  show_pin_names=False, show_pin_numbers=True,
                  ref_at=(-6.35, 5.08, "right"), val_at=(6.35, -6.35, "left")),
    custom_symbol("DirCoupler", "U", "DirCoupler", "", "Directional coupler, IN->OUT, CPL forward, ISO reverse",
                  [(1, "IN", -7.62, 0, 0, 2.54), (2, "OUT", 7.62, 0, 180, 2.54), (3, "CPL", -2.54, -6.35, 90, 2.54),
                   (4, "ISO", 2.54, -6.35, 90, 2.54), (5, "GND", 0, 6.35, 270, 2.54)],
                  [g_rect(-5.08, 3.81, 5.08, -3.81), g_poly([(-3.8, 1.3), (3.8, 1.3)], fill="none"),
                   g_poly([(-3.8, -1.3), (3.8, -1.3)], fill="none")],
                  show_pin_names=False, show_pin_numbers=True,
                  ref_at=(-6.35, 5.08, "right"), val_at=(6.35, -5.08, "left")),
    custom_symbol("RF_SPDT", "U", "RF_SPDT", "Package_TO_SOT_SMD:SOT-363_SC-70-6", "SPDT RF switch, CMOS control",
                  [(5, "RFC", -7.62, 0, 0, 2.54), (1, "RF1", 7.62, 0, 180, 2.54), (3, "RF2", 7.62, -5.08, 180, 2.54),
                   (4, "CTRL", -2.54, -10.16, 90, 2.54), (2, "GND", 2.54, -10.16, 90, 2.54),
                   (6, "VDD", 0, 7.62, 270, 2.54)],
                  [g_rect(-5.08, 5.08, 5.08, -7.62)]),
    custom_symbol("LogDet", "U", "LogDet", "Package_TO_SOT_SMD:SOT-23-6", "RF log/RMS power detector, 0.1-2.5 GHz",
                  [(1, "RFIN", -10.16, 0, 0, 2.54), (4, "VOUT", 10.16, 0, 180, 2.54), (5, "VPOS", -2.54, 7.62, 270, 2.54),
                   (3, "ENBL", 2.54, 7.62, 270, 2.54), (2, "GND", 0, -7.62, 90, 2.54), (6, "GND", 2.54, -7.62, 90, 2.54)],
                  [g_rect(-7.62, 5.08, 7.62, -5.08)]),
    custom_symbol("BPF", "U", "BPF", "", "SAW / ceramic band-pass filter",
                  [(1, "IN", -7.62, 0, 0, 2.54), (3, "OUT", 7.62, 0, 180, 2.54), (2, "GND", 0, -6.35, 90, 2.54)],
                  [g_rect(-5.08, 3.81, 5.08, -3.81),
                   g_poly([(-3, 1.5), (-1.5, 2.5), (0, 1.5), (1.5, 0.5), (3, 1.5)], fill="none"),
                   g_poly([(-3, -0.5), (-1.5, 0.5), (0, -0.5), (1.5, -1.5), (3, -0.5)], fill="none")],
                  show_pin_names=False),
]


def P(ref, lib, value, fp, rot=0, nets=None, **fields):
    return dict(ref=ref, lib_id=lib, value=value, footprint=fp, x=0, y=0, rot=rot, nets=nets or {}, **fields)


R = "Device:R"
C = "Device:C"
CP = "Device:C_Polarized"
L = "Device:L"
COAX = "Connector:Conn_Coaxial"


def passives(sch, x0, y, step, specs):
    """Place vertical 2-pin parts in a row; each spec is (ref, lib, value, fp, net_pin1, net_pin2)."""
    for i, (ref, lib, val, fp, n1, n2, *extra) in enumerate(specs):
        fields = extra[0] if extra else {}
        sch.add(ref, lib, val, fp, x0 + i * step, y, 0, {"1": n1, "2": n2}, **fields)


def build():
    sch = Schematic("SENTINEL_TRM", "SENTINEL-UHF T/R Module, 420-450 MHz, 300 W", "A1", CUSTOM)

    # ============================================================== TX CHAIN
    sch.text("TX CHAIN  -  0 dBm in, 300 W (+54.8 dBm) peak out, 20 % max duty", 25, 45, 3.0)
    sch.rect(20, 50, 445, 130)
    t = Chain(sch, 35.56, 81.28)
    t.start(P("J1", COAX, "TX_IN", SMA, rot=180, nets={"2": "GND"},
              Description="SMA edge launch, RF drive from RFSoC DAC (0 dBm)"), "1")
    t.series(P("C1", C, "100p", C0603, rot=90, Description="DC block, C0G"), "1", "2")
    t.series(P("U1", "SENTINEL:GainBlock", "GB 20dB", SOT89, nets={"2": "GND"},
               Description="Driver gain block, G 20 dB, P1dB +21 dBm", MPN="PHA-13LN+ class"), "1", "3")
    t.shunt([P("L1", L, "390n", L0603, Description="RF choke"), P("R1", R, "33", R0603)], "+5V", up=True)
    t.series(P("C3", C, "100p", C0603, rot=90), "1", "2")
    t.shunt([P("R3", R, "292", R0603, Description="3 dB pi pad")], "GND")
    t.series(P("R4", R, "17.6", R0603, rot=90, Description="3 dB pi pad"), "1", "2")
    t.shunt([P("R5", R, "292", R0603, Description="3 dB pi pad")], "GND")
    t.series(P("C5", C, "33p", C0603, rot=90, Description="Driver input DC block"), "1", "2")
    t.shunt([P("C6", C, "8.2p", C0603, Description="Driver input match")], "GND")
    t.shunt([P("L2", L, "220n", L0805, Description="Gate feed"), P("R6", R, "22", R0603)], "VG_DRV", up=True)
    t.series(P("R7", R, "4.7", R0603, rot=90, Description="Gate stability resistor"), "1", "2")
    t.series(P("Q1", "SENTINEL:GaN_HEMT", "GaN 10W", FP_DRV, nets={"3": "GND"},
               Description="Driver GaN HEMT 10 W, 50 V, 440166 flange", MPN="CG2H40010F class"), "1", "2")
    t.shunt([P("L3", L, "120n", L1210, Description="Driver drain feed")], "VD_SW", up=True)
    t.shunt([P("C8", C, "1.5p", C0805, Description="Driver output match")], "GND")
    t.series(P("C9", C, "47p", C0805, rot=90, Description="Interstage DC block"), "1", "2")
    t.shunt([P("C10", C, "10p", C0805, Description="Interstage match")], "GND")
    t.series(P("L4", L, "18n", L0805, rot=90, Description="Interstage match"), "1", "2")
    t.shunt([P("C11", C, "22p", C1206, Description="PA input match")], "GND")
    t.shunt([P("L5", L, "56n", L1210, Description="PA gate feed"), P("R8", R, "10", R0805)], "VG_PA", up=True)
    t.series(P("Q2", "SENTINEL:GaN_HEMT", "GaN 300W", FP_PA, nets={"3": "GND"},
               Description="Final GaN HEMT 300 W pulsed, 50 V, NI-780 flange", MPN="UHF radar GaN, 300 W class"),
             "1", "2")
    t.shunt([P("L6", L, "47n", L1812, Description="PA drain feed, 10 A peak")], "VD_SW", up=True)
    t.series(P("C17", C, "100p", C2220, rot=90, Description="Output DC block, 500 V, high-Q"), "1", "2")
    t.shunt([P("C18", C, "6.8p", C2220, Description="Output match, 500 V")], "GND")
    t.series(P("L7", L, "8n", L1812, rot=90, Description="Output match, air core"), "1", "2")
    t.shunt([P("C19", C, "3.3p", C2220, Description="Output match, 500 V")], "GND")
    t.name("PA_OUT")
    t.series(P("U3", "SENTINEL:Circulator", "CIRC 400W", FP_CIRC, nets={"3": "RX_CIRC", "4": "GND"},
               Description="Drop-in circulator 420-450 MHz, 400 W pk, 20 dB isolation"), "1", "2")
    t.name("ANT_FEED")
    t.series(P("U4", "SENTINEL:DirCoupler", "-30dB", FP_CPL, nets={"3": "CPL_FWD", "4": "CPL_REV", "5": "GND"},
               Description="Directional coupler 30 dB, 500 W"), "1", "2")
    t.name("ANT_RF")
    t.end(P("J3", COAX, "ANT", FP_N, nets={"2": "GND"},
            Description="N-type edge launch to crossed-dipole hybrid"), "1")

    # ============================================================== RX CHAIN
    sch.text("RX CHAIN  -  limiter protected, NF 1.1 dB, G 34 dB", 25, 145, 3.0)
    sch.rect(20, 150, 445, 215)
    r = Chain(sch, 35.56, 175.26)
    r.start_label("RX_CIRC")
    r.shunt([P("D1", "Device:D", "PIN", DSMB, rot=90, Description="Coarse PIN limiter diode, 100 W pk")], "GND")
    r.shunt([P("L8", L, "100n", L0603, Description="Limiter DC return")], "GND")
    r.series(P("C23", C, "100p", C0603, rot=90), "1", "2")
    r.shunt([P("D2", "Device:D_Schottky", "Schottky", SOD323, rot=90, Description="Fine limiter")], "GND")
    r.series(P("C24", C, "100p", C0603, rot=90), "1", "2")
    r.series(P("U8", "SENTINEL:LNA", "LNA", SOT89, nets={"2": "GND"},
               Description="LNA NF 0.5 dB, G 18 dB at 435 MHz"), "1", "3")
    r.shunt([P("L9", L, "390n", L0603), P("R9", R, "47", R0603)], "+5V", up=True)
    r.series(P("C25", C, "100p", C0603, rot=90), "1", "2")
    r.series(P("U9", "SENTINEL:BPF", "BPF 420-450", FP_BPF, nets={"2": "GND"},
               Description="SAW BPF 435 MHz, 30 MHz BW, IL 2 dB"), "1", "3")
    r.series(P("U10", "SENTINEL:GainBlock", "GB 20dB", SOT89, nets={"2": "GND"},
               Description="Receive gain block, G 20 dB"), "1", "3")
    r.shunt([P("L10", L, "390n", L0603), P("R10", R, "33", R0603)], "+5V", up=True)
    r.series(P("C26", C, "100p", C0603, rot=90), "1", "2")
    r.end(P("J2", COAX, "RX_OUT", SMA, nets={"2": "GND"}, Description="SMA edge launch to RFSoC ADC"), "1")

    # ============================================================== COUPLER / DETECTORS / CAL
    sch.text("POWER MONITOR AND CALIBRATION PORT", 25, 228, 3.0)
    sch.rect(20, 233, 445, 330)
    d = Chain(sch, 35.56, 256.54)
    d.start_label("CPL_FWD")
    d.shunt([P("R12", R, "96", R0603)], "GND")
    d.series(P("R13", R, "71", R0603, rot=90, Description="10 dB pi pad"), "1", "2")
    d.shunt([P("R14", R, "96", R0603)], "GND")
    d.series(P("U5", "SENTINEL:RF_SPDT", "SPDT", SC70_6,
               nets={"3": "CAL_PORT", "4": "CAL_SW", "2": "GND", "6": "+3V3"},
               Description="RF switch: detector or calibration port"), "5", "1")
    d.series(P("C27", C, "100p", C0603, rot=90), "1", "2")
    d.series(P("U6", "SENTINEL:LogDet", "DET FWD", SOT23_6, nets={"5": "+5V", "3": "+5V", "2": "GND", "6": "GND"},
               Description="Forward power detector"), "1", "4")
    d.end_label("V_FWD")

    e = Chain(sch, 35.56, 292.1)
    e.start_label("CPL_REV")
    e.shunt([P("R15", R, "96", R0603)], "GND")
    e.series(P("R16", R, "71", R0603, rot=90), "1", "2")
    e.shunt([P("R17", R, "96", R0603)], "GND")
    e.series(P("C28", C, "100p", C0603, rot=90), "1", "2")
    e.series(P("U7", "SENTINEL:LogDet", "DET REV", SOT23_6, nets={"5": "+5V", "3": "+5V", "2": "GND", "6": "GND"},
               Description="Reflected power detector (VSWR trip)"), "1", "4")
    e.end_label("V_REFL")

    k = Chain(sch, 220.98, 256.54)
    k.start_label("CAL_PORT")
    k.series(P("C29", C, "100p", C0603, rot=90), "1", "2")
    k.end(P("J4", COAX, "CAL", SMA, nets={"2": "GND"},
            Description="SMA to array calibration network (mutual-coupling cal)"), "1")

    # ============================================================== DRAIN SUPPLY, SWITCH, SENSE
    sch.text("DRAIN SUPPLY  -  50 V, 10 A peak, pulsed drain switch + current sense", 460, 45, 3.0)
    sch.rect(455, 50, 665, 235)
    sch.add("J6", "Connector_Generic:Conn_01x02", "50V IN", MINIFIT, 480.06, 78.74, 0,
            {"1": "VDD_50V", "2": "GND"}, Description="Mini-Fit Jr, 50 V drain bus from subarray supply")
    sch.add("D4", "Device:D_TVS", "SMBJ58A", DSMB, 500.38, 81.28, 90, {"2": "VDD_50V", "1": "GND"},
            Description="Bus transient clamp")
    passives(sch, 510.54, 81.28, 10.16, [
        ("C38", CP, "100u 100V", CP10, "VDD_50V", "GND", {"Description": "Bus bulk"}),
        ("C39", C, "1u 100V", C1210, "VDD_50V", "GND"),
        ("R37", R, "5m", R2512, "VDD_50V", "VDD_50V_S", {"Description": "Drain current shunt, Kelvin"}),
    ])
    sch.add("U18", "Amplifier_Current:INA240A1D", "INA240A1", SOIC8, 566.42, 81.28, 0,
            {"8": "VDD_50V", "1": "VDD_50V_S", "6": "+5V", "2": "GND", "3": "GND", "7": "GND", "5": "I_DRAIN_V"},
            Description="Drain current sense, 20 V/V")
    passives(sch, 594.36, 81.28, 10.16, [
        ("C36", C, "100n", C0603, "+5V", "GND"),
        ("R38", R, "1k", R0603, "I_DRAIN_V", "I_DRAIN"),
        ("C37", C, "10n", C0603, "I_DRAIN", "GND"),
        ("R39", R, "180k", R0603, "VDD_50V", "VDD50_MON"),
        ("R40", R, "10k", R0603, "VDD50_MON", "GND"),
    ])
    sch.add("Q4", "Transistor_FET:SUD50P10-43L", "SUD50P10", TO252, 543.56, 152.4, 0,
            {"1": "PFET_G", "2": "VD_SW", "3": "VDD_50V_S"}, Description="High-side drain switch, 100 V P-FET")
    sch.add("D3", "Device:D_Zener", "12V", SOD323, 497.84, 152.4, 270, {"1": "VDD_50V_S", "2": "PFET_G"},
            Description="P-FET Vgs clamp")
    passives(sch, 510.54, 152.4, 10.16, [
        ("R36", R, "4.7k", R0805, "VDD_50V_S", "PFET_G"),
        ("R35", R, "10k", R1206, "PFET_G", "PFET_PULL"),
    ])
    sch.add("Q3", "Transistor_FET:2N7002", "2N7002", SOT23, 576.58, 152.4, 0,
            {"1": "Q3_G", "2": "GND", "3": "PFET_PULL"}, Description="Level shifter")
    passives(sch, 594.36, 152.4, 10.16, [
        ("R34", R, "100", R0603, "DRAIN_ON", "Q3_G"),
        ("R48", R, "100k", R0603, "Q3_G", "GND"),
    ])
    passives(sch, 520.7, 205.74, 10.16, [
        ("C13", C, "1n 100V", C1210, "VD_SW", "GND"),
        ("C14", C, "10u 100V", C2220, "VD_SW", "GND"),
        ("C15", CP, "330u 63V", CP10, "VD_SW", "GND", {"Description": "Polymer, pulse reservoir"}),
        ("C16", CP, "330u 63V", CP10, "VD_SW", "GND", {"Description": "Polymer, pulse reservoir"}),
    ])
    sch.text("Drain switch: Vgs = -12 V (clamped), t_on ~ 25 us, t_off ~ 80 us.", 460, 228, 1.5, bold=False)

    # ============================================================== POWER
    sch.text("POWER  -  12 V aux in, 5 V buck, 3.3 V LDO, -5 V inverter", 675, 45, 3.0)
    sch.rect(670, 50, 830, 345)
    sch.add("J5", "Connector_Generic:Conn_02x08_Odd_Even", "BACKPLANE", HDR2x8, 711.2, 101.6, 0,
            {"1": "+12V", "3": "+12V", "5": "RS485_A", "7": "RS485_B", "9": "TX_EN", "11": "FAULT_N",
             "13": "NC", "15": "NC", **{str(n): "GND" for n in range(2, 17, 2)}},
            Description="Tile backplane: aux power, RS-485, TX_EN gate, fault; even pins ground")
    sch.pwr_flag("GND", 762, 66.04)
    sch.pwr_flag("+12V", 777.24, 66.04)
    sch.pwr_flag("+5V", 792.48, 66.04)
    sch.add("U19", "Regulator_Switching:LMR16006YQ", "LMR16006", SOT23_6, 718.82, 185.42, 0,
            {"5": "+12V", "4": "+12V", "2": "GND", "1": "BOOT", "6": "SW_5V", "3": "FB_5V"},
            Description="12 V to 5 V buck, 0.6 A")
    passives(sch, 680.72, 205.74, 10.16, [
        ("C43", C, "10u 50V", C1210, "+12V", "GND"),
        ("C44", C, "100n", C0603, "+12V", "GND"),
    ])
    passives(sch, 746.76, 205.74, 10.16, [
        ("C41", C, "100n", C0603, "BOOT", "SW_5V"),
    ])
    sch.add("D5", "Device:D_Schottky", "SS16", DSMA, 756.92, 205.74, 270, {"1": "SW_5V", "2": "GND"})
    passives(sch, 767.08, 205.74, 10.16, [
        ("L11", L, "22u", L1210, "SW_5V", "+5V"),
        ("R43", R, "56.2k", R0603, "+5V", "FB_5V"),
        ("R44", R, "10k", R0603, "FB_5V", "GND"),
        ("C42", C, "22u", C1210, "+5V", "GND"),
    ])
    sch.add("U20", "Regulator_Linear:AP2112K-3.3", "AP2112K-3.3", SOT23_5, 718.82, 254, 0,
            {"1": "+5V", "3": "+5V", "2": "GND", "5": "+3V3"})
    passives(sch, 746.76, 259.08, 10.16, [
        ("C45", C, "1u", C0603, "+5V", "GND"),
        ("C46", C, "1u", C0603, "+3V3", "GND"),
    ])
    sch.add("U11", "Regulator_SwitchedCapacitor:LM2776", "LM2776", SOT23_6, 718.82, 309.88, 0,
            {"3": "+5V", "2": "GND", "1": "-5V", "4": "+5V", "5": "CFLY_P", "6": "CFLY_N"},
            Description="-5 V for GaN gate bias")
    passives(sch, 746.76, 314.96, 10.16, [
        ("C32", C, "1u", C0603, "CFLY_P", "CFLY_N"),
        ("C33", C, "1u", C0603, "+5V", "GND"),
        ("C34", C, "4.7u", C0805, "-5V", "GND"),
    ])

    # ============================================================== GATE BIAS
    sch.text("GATE BIAS  -  VG = -1.25 x VDAC  (-1.0 ... -4.1 V), fail-safe pinch-off", 25, 350, 3.0)
    sch.rect(20, 355, 215, 545)
    for i, (tag, cs) in enumerate((("PA", "DAC_CS_PA"), ("DRV", "DAC_CS_DRV"))):
        y = 391.16 + i * 81.28
        sch.add(f"U{12 + i}", "Analog_DAC:DAC7311xDCK", "DAC7311", SC70_6, 50.8, y, 0,
                {"1": cs, "2": "DAC_SCLK", "3": "DAC_DIN", "4": "+3V3", "5": "GND", "6": f"VDAC_{tag}"},
                Description=f"12-bit DAC, {tag} gate setpoint")
        sch.add(f"U{14 + i}", "Amplifier_Operational:LM321", "LM321", SOT23_5, 132.08, y, 0,
                {"1": "GND", "3": f"INV_{tag}", "4": f"VG_{tag}_OP", "5": "+5V", "2": "-5V"},
                Description="Inverting gate driver, +5/-5 V")
        base = 18 + 3 * i
        passives(sch, 86.36, y + 2.54, 10.16, [
            (f"R{base}", R, "10k", R0603, f"VDAC_{tag}", f"INV_{tag}"),
            (f"R{base + 1}", R, "12.4k", R0603, f"INV_{tag}", f"VG_{tag}_OP"),
        ])
        passives(sch, 160.02, y + 2.54, 10.16, [
            (f"R{base + 2}", R, "10", R0603, f"VG_{tag}_OP", f"VG_{tag}"),
            (f"R{24 + i}", R, "100k", R0603, f"VG_{tag}", "-5V", {"Description": "Fail-safe pinch-off"}),
            (f"C{20 + i}", C, "100n", C0603, f"VG_{tag}", "GND"),
        ])
    passives(sch, 30.48, 525.78, 10.16, [
        ("C30", C, "100n", C0603, "+3V3", "GND"),
        ("C31", C, "100n", C0603, "+3V3", "GND"),
        ("C22", C, "1u", C0603, "VG_PA", "GND"),
    ])

    # ============================================================== INTERLOCK / MONITOR
    sch.text("SEQUENCING INTERLOCK AND MONITORS", 230, 350, 3.0)
    sch.rect(225, 355, 440, 545)
    sch.add("U16", "Comparator:LMV331", "LMV331", SOT23_5, 266.7, 386.08, 0,
            {"5": "+3V3", "2": "GND", "1": "VREF_BOK", "3": "VG_MON", "4": "BIAS_OK"},
            Description="BIAS_OK high only when VG_PA < -2.0 V")
    sch.add("U17", "74xGxx:74LVC1G11", "74LVC1G11", SC70_6, 365.76, 386.08, 0,
            {"1": "TX_EN", "3": "BIAS_OK", "6": "DRAIN_EN_MCU", "4": "DRAIN_ON", "5": "+3V3", "2": "GND"},
            Description="Drain on = TX_EN AND BIAS_OK AND MCU enable")
    passives(sch, 238.76, 439.42, 10.16, [
        ("R26", R, "10k", R0603, "+3V3", "BIAS_OK"),
        ("R27", R, "100k", R0603, "VG_PA", "VG_MON"),
        ("R28", R, "100k", R0603, "VG_MON", "+3V3"),
        ("R29", R, "82k", R0603, "+3V3", "VREF_BOK"),
        ("R30", R, "20k", R0603, "VREF_BOK", "GND"),
        ("R31", R, "100k", R0603, "VG_DRV", "VGD_MON"),
        ("R32", R, "100k", R0603, "VGD_MON", "+3V3"),
        ("R33", R, "10k", R0603, "TX_EN", "GND", {"Description": "TX_EN defaults low"}),
        ("C35", C, "100n", C0603, "+3V3", "GND"),
    ])
    passives(sch, 238.76, 500.38, 10.16, [
        ("TH1", "Device:Thermistor_NTC", "10k NTC", R0603, "NTC_V", "GND", {"Description": "On PA flange"}),
        ("R41", R, "10k", R0603, "+3V3", "NTC_V"),
        ("C40", C, "100n", C0603, "NTC_V", "GND"),
        ("R46", R, "10k", R0603, "+3V3", "FAULT_N"),
    ])

    # ============================================================== MCU / INTERFACE
    sch.text("MODULE CONTROLLER  -  STM32G031, RS-485 to tile, SWD", 455, 350, 3.0)
    sch.rect(450, 355, 665, 572)
    sch.add("U21", "MCU_ST_STM32G0:STM32G031K8Tx", "STM32G031K8T6", LQFP32, 530.86, 434.34, 0, {
        "4": "+3V3", "5": "GND", "6": "NRST",
        "7": "I_DRAIN", "8": "V_FWD", "9": "RS485_DI", "10": "RS485_RO", "11": "V_REFL", "12": "DAC_SCLK",
        "13": "NTC_V", "14": "DAC_DIN", "15": "VG_MON", "16": "VDD50_MON", "17": "VGD_MON", "18": "DAC_CS_PA",
        "22": "DAC_CS_DRV", "23": "RS485_DE", "24": "SWDIO", "25": "SWCLK", "26": "DRAIN_EN_MCU",
        "27": "CAL_SW", "28": "LED_DRV", "29": "FAULT_N", "30": "TX_EN",
        "1": "NC", "2": "NC", "3": "NC", "20": "NC", "31": "NC", "32": "NC"},
        Description="Module controller: bias, protection, telemetry")
    sch.add("U22", "Interface_UART:THVD1450D", "THVD1450", SOIC8, 627.38, 497.84, 0,
            {"1": "RS485_RO", "2": "RS485_DE", "3": "RS485_DE", "4": "RS485_DI", "5": "GND",
             "6": "RS485_A", "7": "RS485_B", "8": "+3V3"}, Description="RS-485 to tile controller")
    sch.add("J7", "Connector_Generic:Conn_01x04", "SWD", HDR1x4, 637.54, 411.48, 0,
            {"1": "+3V3", "2": "SWDIO", "3": "SWCLK", "4": "GND"})
    passives(sch, 462.28, 528.32, 10.16, [
        ("C47", C, "100n", C0603, "+3V3", "GND"),
        ("C48", C, "4.7u", C0603, "+3V3", "GND"),
        ("C49", C, "100n", C0603, "NRST", "GND"),
        ("C50", C, "100n", C0603, "+3V3", "GND"),
        ("R45", R, "1k", R0603, "LED_DRV", "LED_A"),
    ])
    sch.add("D6", "Device:LED", "GRN", LED0603, 513.08, 528.32, 90, {"2": "LED_A", "1": "GND"},
            Description="Status LED")
    for i in range(4):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", MH, 690.88 + 15.24 * i, 393.7, 0, {"1": "GND"},
                Description="Cold-plate bond, M3")
    sch.text("MOUNTING / COLD PLATE", 675, 375, 2.0)
    sch.rect(670, 380, 830, 410)

    sch.text("NOTES", 675, 430, 2.5)
    notes = [
        "1. Matching values are first-pass from transistor large-signal models; tune at 435 MHz on load-pull bench.",
        "2. Q2 and U3 mount through board cutouts onto the copper cold plate (liquid cooled, 45 W avg per module).",
        "3. RF lines: 50 ohm microstrip, 1.70 mm on RO4350B 0.762 mm (L1-L2). Output path >= 3 mm wide.",
        "4. TX_EN is the only path that can turn the drain on; MCU and BIAS_OK can veto it in hardware.",
        "5. Module power: 155 W avg RF per module x 2,587 per face; see radar_sizing.py for the system budget.",
    ]
    for i, n in enumerate(notes):
        sch.text(n, 675, 440 + 6 * i, 1.4, bold=False)
    return sch


def main():
    sch = build()
    sch.resolve()
    lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20251024], [Sym("generator"), "gen_schematic"],
           [Sym("generator_version"), "10.0"]] + CUSTOM
    (HERE / "SENTINEL.kicad_sym").write_text(dumps(lib) + "\n", encoding="utf-8")
    sch.write(HERE / "SENTINEL_TRM.kicad_sch")
    exp = {k: sorted(v) for k, v in sch.expected.items()}
    (HERE / "expected_nets.json").write_text(json.dumps(exp, indent=1))
    (HERE / "chains.json").write_text(json.dumps(sch.chains, indent=1))
    bom = sorted({(p.ref, p.value, p.fp, p.fields.get("Description", ""), p.fields.get("MPN", ""))
                  for p in sch.parts}, key=lambda r: (r[0].rstrip("0123456789"), int("".join(c for c in r[0] if c.isdigit()) or 0)))
    (HERE / "parts.json").write_text(json.dumps(bom, indent=0))
    print(f"parts: {len(sch.parts)}  wires: {len(sch.wires)}  labels: {len(sch.labels)}  nets: {len(exp)}")


if __name__ == "__main__":
    main()
