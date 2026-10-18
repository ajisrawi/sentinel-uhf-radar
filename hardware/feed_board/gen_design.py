"""
SENTINEL-UHF element feed board: lives in the base of every crossed-dipole element.

N-type in from the T/R module -> 3 dB 90-degree hybrid -> two matching networks
-> two 1:1 baluns -> the x and y dipole arms. The hybrid's isolated port is
terminated in a 100 W load (it absorbs the cross-polar return and the element
mismatch). Each dipole arm is DC-grounded through a choke to bleed static.

Matching values come from the EM model (antenna/results/results.json): the
x dipole wants a 50+30j ohm source, the y dipole 39+36j ohm.
"""
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "tools"))
import fpgen as fp  # noqa: E402
from schgen import Chain, Schematic, custom_symbol, g_poly, g_rect, g_text, write_project  # noqa: E402

PRO = "SENTINEL_FEED"
F0 = 435e6
W0 = 2 * math.pi * F0
em = json.loads((HERE.parents[1] / "antenna" / "results" / "results.json").read_text())


def match_lc(zt, z0=50.0):
    """Shunt C at the 50 ohm side, then series L, presenting zt to the element."""
    if zt.real >= z0:
        return 0.0, max(zt.imag, 0) / W0
    g = 1 / z0
    b = math.sqrt(g / zt.real - g * g)
    x1 = -b / (g * g + b * b)
    return b / W0, (zt.imag - x1) / W0


zx = complex(*em["z_ref"])
zy = complex(*em["z_ref_y"])
cx, lx = match_lc(zx)
cy, ly = match_lc(zy)


def fmt_c(c):
    return "DNP" if c <= 0 else f"{c * 1e12:.1f}p"


def fmt_l(l):
    return f"{l * 1e9:.1f}n"


# ------------------------------------------------------------------ footprints
def footprints():
    out = HERE / "SENTINEL.pretty"
    b = fp.rect("F.Fab", -3, -7, 8, 7, 0.1) + fp.pad(1, 0, 0, 6, 1.6)
    b += fp.pad(2, 0, -5.5, 6, 5) + fp.pad(2, 0, 5.5, 6, 5)
    b += fp.pad(2, 0, -5.5, 6, 5, layers=("B.Cu", "B.Mask")) + fp.pad(2, 0, 5.5, 6, 5, layers=("B.Cu", "B.Mask"))
    b += fp.rect("F.CrtYd", -3.4, -8.4, 8.4, 8.4, 0.05)
    fp.footprint(out, "N_EdgeLaunch", "N-type jack, edge launch, 50 ohm", b, 8.4)
    b = fp.rect("F.Fab", -7.5, -5, 7.5, 5, 0.1)
    b += fp.pad(1, -6.5, -2.5, 2.0, 1.5) + fp.pad(2, -6.5, 2.5, 2.0, 1.5)
    b += fp.pad(3, 6.5, -2.5, 2.0, 1.5) + fp.pad(4, 6.5, 2.5, 2.0, 1.5) + fp.pad(5, 0, 0, 9, 6)
    b += fp.rect("F.CrtYd", -8.0, -5.5, 8.0, 5.5, 0.05)
    fp.footprint(out, "Hybrid90_SMD_15x10", "3 dB 90 deg hybrid, 420-450 MHz, 500 W", b, 5.5)
    b = fp.rect("F.Fab", -6.5, -4, 6.5, 4, 0.1) + fp.pad(1, -5.0, 0, 3, 3) + fp.pad(2, 2.0, 0, 8, 7)
    b += fp.rect("F.CrtYd", -7.0, -4.5, 7.0, 4.5, 0.05)
    fp.footprint(out, "Termination_100W_SMD", "50 ohm 100 W chip termination on flange", b, 4.5)
    b = fp.rect("F.Fab", -5, -4, 5, 4, 0.1)
    b += fp.pad(1, -4, -2, 2, 2) + fp.pad(2, -4, 2, 2, 2) + fp.pad(3, 4, -2, 2, 2) + fp.pad(4, 4, 2, 2, 2)
    b += fp.rect("F.CrtYd", -5.5, -4.5, 5.5, 4.5, 0.05)
    fp.footprint(out, "Balun_SMD_10x8", "1:1 balun transformer, 200 W pk", b, 4.5)
    b = fp.tht(1, -5, 0, 7, 4.3) + fp.tht(2, 5, 0, 7, 4.3) + fp.rect("F.CrtYd", -9, -4, 9, 4, 0.05)
    fp.footprint(out, "DipoleArm_M4_Pair", "Two M4 lugs for one dipole's arms", b, 4.0, attr="through_hole")


# ------------------------------------------------------------------ symbols
CUSTOM = [
    custom_symbol("Hybrid90", "U", "Hybrid90", "SENTINEL:Hybrid90_SMD_15x10", "3 dB 90-degree hybrid",
                  [(1, "IN", -7.62, 0, 0, 2.54), (2, "ISO", -7.62, -5.08, 0, 2.54), (3, "0°", 7.62, 0, 180, 2.54),
                   (4, "-90°", 7.62, -5.08, 180, 2.54), (5, "GND", 0, -10.16, 90, 2.54)],
                  [g_rect(-5.08, 2.54, 5.08, -7.62)], ref_at=(0, 3.81, None), val_at=(6.35, -8.89, "left")),
    custom_symbol("Balun", "T", "Balun", "SENTINEL:Balun_SMD_10x8", "1:1 balun",
                  [(1, "UNBAL", -7.62, 0, 0, 2.54), (2, "GND", -2.54, -7.62, 90, 2.54),
                   (3, "B+", 7.62, 0, 180, 2.54), (4, "B-", 7.62, -2.54, 180, 2.54)],
                  [g_rect(-5.08, 2.54, 5.08, -5.08)], ref_at=(0, 3.81, None), val_at=(0, -10.16, None)),
]


def P(ref, lib, value, footprint, rot=0, nets=None, **f):
    return dict(ref=ref, lib_id=lib, value=value, footprint=footprint, x=0, y=0, rot=rot, nets=nets or {}, **f)


C2220, L1210, L0805 = "Capacitor_SMD:C_2220_5750Metric", "Inductor_SMD:L_1210_3225Metric", "Inductor_SMD:L_0805_2012Metric"
COAX, MH = "Connector:Conn_Coaxial", "MountingHole:MountingHole_3.2mm_M3_Pad"


def build():
    sch = Schematic(PRO, "SENTINEL-UHF Element Feed Board", "A3", CUSTOM)
    sch.text("ELEMENT FEED  -  hybrid splits the module output into two dipoles in quadrature (circular polarisation)", 20, 25, 2.5)
    m = Chain(sch, 30.48, 81.28)
    m.start(P("J1", COAX, "FROM T/R", "SENTINEL:N_EdgeLaunch", rot=180, nets={"2": "GND"},
              Description="N-type from T/R module ANT port, 300 W pk"), "1")
    m.end(P("U1", "SENTINEL:Hybrid90", "HYB 3dB", "SENTINEL:Hybrid90_SMD_15x10",
            nets={"2": "HYB_ISO", "3": "HYB_0", "4": "HYB_90", "5": "GND"},
            Description="3 dB 90 deg hybrid, 420-450 MHz, 500 W"), "1")
    for tag, y, lab, c, l, refs in (("X", 60.96, "HYB_0", cx, lx, ("C1", "L1", "C2", "T1", "J2", "L3", "L4")),
                                    ("Y", 116.84, "HYB_90", cy, ly, ("C3", "L2", "C4", "T2", "J3", "L5", "L6"))):
        ch = Chain(sch, 101.6, y)
        ch.start_label(lab)
        ch.shunt([P(refs[0], "Device:C", fmt_c(c), C2220, Description=f"{tag} match shunt, 500 V")], "GND")
        ch.series(P(refs[1], "Device:L", fmt_l(l), L1210, rot=90, Description=f"{tag} match series"), "1", "2")
        ch.shunt([P(refs[2], "Device:C", "tune", C2220, Description="Bench trim, fit if needed", MPN="DNP")], "GND")
        ch.series(P(refs[3], "SENTINEL:Balun", "1:1", "SENTINEL:Balun_SMD_10x8",
                    nets={"2": "GND", "4": f"ARM_{tag}_N"}, Description="1:1 balun, 200 W pk"), "1", "3")
        ch.shunt([P(refs[5], "Device:L", "1u", L0805, Description="Static bleed")], "GND")
        ch.end(P(refs[4], "Connector_Generic:Conn_01x02", f"DIPOLE {tag}", "SENTINEL:DipoleArm_M4_Pair",
                 rot=180, nets={"2": f"ARM_{tag}_N"}, Description=f"{tag} dipole arms, M4 lugs"), "1")
        sch.add(refs[6], "Device:L", "1u", L0805, 233.68, y + 15.24, 0, {"1": f"ARM_{tag}_N", "2": "GND"},
                Description="Static bleed")
    sch.add("R1", "Device:R", "50 100W", "SENTINEL:Termination_100W_SMD", 60.96, 101.6, 0,
            {"1": "HYB_ISO", "2": "GND"}, Description="Isolated-port load, 100 W")
    for i in range(2):
        sch.add(f"H{i + 1}", "Mechanical:MountingHole_Pad", "M3", MH, 40.64 + 12.7 * i, 139.7, 0, {"1": "GND"})
    sch.pwr_flag("GND", 25.4, 139.7)
    sch.text(f"Match targets from EM model: X {zx.real:.0f}{zx.imag:+.0f}j ohm, Y {zy.real:.0f}{zy.imag:+.0f}j ohm at 435 MHz",
             20, 160, 1.8, bold=False)
    return sch


if __name__ == "__main__":
    footprints()
    write_project(build(), HERE, CUSTOM, "SENTINEL-UHF Element Feed Board")
    print(f"X: C {fmt_c(cx)} L {fmt_l(lx)}   Y: C {fmt_c(cy)} L {fmt_l(ly)}")
