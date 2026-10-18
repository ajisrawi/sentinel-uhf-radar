"""Helpers to write simple custom SMD/THT footprints (.kicad_mod)."""
from pathlib import Path


def pad(num, x, y, w, h, layers=("F.Cu", "F.Paste", "F.Mask"), shape="roundrect"):
    lay = " ".join(f'"{l}"' for l in layers)
    rr = " (roundrect_rratio 0.1)" if shape == "roundrect" else ""
    return f'\t(pad "{num}" smd {shape} (at {x} {y}) (size {w} {h}) (layers {lay}){rr})\n'


def tht(num, x, y, d, drill, shape="circle"):
    return (f'\t(pad "{num}" thru_hole {shape} (at {x} {y}) (size {d} {d}) (drill {drill}) '
            f'(layers "*.Cu" "*.Mask"))\n')


def npth(x, y, drill):
    return (f'\t(pad "" np_thru_hole circle (at {x} {y}) (size {drill} {drill}) (drill {drill}) '
            f'(layers "*.Cu" "*.Mask"))\n')


def rect(layer, x1, y1, x2, y2, width=0.12):
    return (f'\t(fp_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width {width}) (type solid)) '
            f'(fill no) (layer "{layer}"))\n')


def _text(kind, val, y, layer):
    return (f'\t(property "{kind}" "{val}" (at 0 {y} 0) (layer "{layer}") '
            f'(effects (font (size 1 1) (thickness 0.15))))\n')


def footprint(out_dir, name, descr, body, cy, attr="smd"):
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)
    s = (f'(footprint "{name}"\n\t(version 20260206)\n\t(generator "fpgen")\n\t(layer "F.Cu")\n'
         f'\t(descr "{descr}")\n')
    s += _text("Reference", "REF**", -cy - 1.5, "F.SilkS") + _text("Value", name, cy + 1.5, "F.Fab")
    s += f"\t(attr {attr})\n" + body + ")\n"
    (out_dir / f"{name}.kicad_mod").write_text(s)
