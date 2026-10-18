"""Custom footprints for the T/R module RF parts (SENTINEL.pretty)."""
from pathlib import Path

OUT = Path(__file__).parent / "SENTINEL.pretty"


def pad(num, x, y, w, h, layers=("F.Cu", "F.Paste", "F.Mask"), shape="roundrect"):
    lay = " ".join(f'"{l}"' for l in layers)
    rr = " (roundrect_rratio 0.1)" if shape == "roundrect" else ""
    return f'\t(pad "{num}" smd {shape} (at {x} {y}) (size {w} {h}) (layers {lay}){rr})\n'


def rect(layer, x1, y1, x2, y2, width=0.12):
    return (f'\t(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {width}) (type solid)) '
            f'(fill no) (layer "{layer}"))\n')


def text(kind, val, y, layer):
    return (f'\t(property "{kind}" "{val}" (at 0 {y} 0) (layer "{layer}") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n')


def footprint(name, descr, body, cy):
    s = (f'(footprint "{name}"\n\t(version 20260206)\n\t(generator "gen_footprints")\n\t(layer "F.Cu")\n'
         f'\t(descr "{descr}")\n')
    s += text("Reference", "REF**", -cy - 1.5, "F.SilkS") + text("Value", name, cy + 1.5, "F.Fab")
    s += "\t(attr smd)\n" + body + ")\n"
    (OUT / f"{name}.kicad_mod").write_text(s)


def main():
    OUT.mkdir(exist_ok=True)

    # 300 W GaN, NI-780 style flange. Flange sits in a board cutout on the cold plate,
    # gate/drain leads land on top pads; source is the flange, tied to top GND pads.
    b = rect("Edge.Cuts", -5.6, -17.5, 5.6, 17.5, 0.05)
    b += rect("F.Fab", -5.1, -17.0, 5.1, 17.0, 0.1)
    b += pad(1, -9.6, 0, 7, 10) + pad(2, 9.6, 0, 7, 10)
    b += pad(3, 0, -21, 10, 6) + pad(3, 0, 21, 10, 6)
    b += rect("F.SilkS", -13.4, -24.3, 13.4, 24.3)
    b += rect("F.CrtYd", -13.6, -24.5, 13.6, 24.5, 0.05)
    footprint("GaN_Flange_780", "300 W GaN HEMT, NI-780 flange in board cutout", b, 24.5)

    b = rect("Edge.Cuts", -2.4, -10.4, 2.4, 10.4, 0.05)
    b += rect("F.Fab", -2.0, -10.0, 2.0, 10.0, 0.1)
    b += pad(1, -4.6, 0, 3.6, 2.6) + pad(2, 4.6, 0, 3.6, 2.6)
    b += pad(3, 0, -12.6, 5, 2.4) + pad(3, 0, 12.6, 5, 2.4)
    b += rect("F.CrtYd", -6.6, -14.0, 6.6, 14.0, 0.05)
    footprint("GaN_Flange_440166", "10 W GaN HEMT, 440166 flange in board cutout", b, 14.0)

    # Drop-in circulator: body in a 31 mm pocket, three tabs, four ground lugs.
    b = rect("Edge.Cuts", -15.5, -15.5, 15.5, 15.5, 0.05)
    b += rect("F.Fab", -15.0, -15.0, 15.0, 15.0, 0.1)
    b += pad(1, -18.5, 0, 4, 3) + pad(2, 18.5, 0, 4, 3) + pad(3, 0, 18.5, 3, 4)
    for x, y in ((-18.5, -11), (18.5, -11), (-18.5, 11), (18.5, 11), (0, -18.5)):
        b += pad(4, x, y, 4, 4)
    b += rect("F.CrtYd", -21.0, -21.0, 21.0, 21.0, 0.05)
    footprint("Circulator_DropIn_32mm", "Drop-in circulator 420-450 MHz, 31 mm pocket", b, 21.0)

    b = rect("F.Fab", -6.35, -3.2, 6.35, 3.2, 0.1)
    b += pad(1, -5.8, -1.6, 1.8, 1.4) + pad(2, 5.8, -1.6, 1.8, 1.4)
    b += pad(3, -5.8, 1.6, 1.8, 1.4) + pad(4, 5.8, 1.6, 1.8, 1.4)
    b += pad(5, 0, 0, 7, 4.4)
    b += rect("F.CrtYd", -7.2, -3.6, 7.2, 3.6, 0.05)
    footprint("DirCoupler_SMD_12x6", "30 dB directional coupler, 4-port SMD", b, 3.6)

    b = rect("F.Fab", -2.5, -2.5, 2.5, 2.5, 0.1)
    b += pad(1, -1.9, 0, 1.0, 1.4) + pad(3, 1.9, 0, 1.0, 1.4)
    b += pad(2, 0, -1.9, 2.5, 1.0) + pad(2, 0, 1.9, 2.5, 1.0)
    b += rect("F.CrtYd", -2.9, -2.9, 2.9, 2.9, 0.05)
    footprint("BPF_SMD_5x5", "SAW band-pass filter 5x5 mm", b, 2.9)

    # N-type edge launch: centre pin on top, ground pads both sides; flange on panel.
    b = rect("F.Fab", -3, -7, 8, 7, 0.1)
    b += pad(1, 0, 0, 6, 1.6)
    b += pad(2, 0, -5.5, 6, 5) + pad(2, 0, 5.5, 6, 5)
    b += pad(2, 0, -5.5, 6, 5, layers=("B.Cu", "B.Mask")) + pad(2, 0, 5.5, 6, 5, layers=("B.Cu", "B.Mask"))
    b += rect("F.CrtYd", -3.4, -8.4, 8.4, 8.4, 0.05)
    footprint("N_EdgeLaunch", "N-type jack, edge launch, 50 ohm", b, 8.4)
    print("footprints:", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
