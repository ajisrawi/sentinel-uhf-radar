"""Run with KiCad's Python: kicad_dump.py <project dir> - dump pad/courtyard/cutout geometry of every footprint the netlist uses."""
import json
import sys
from pathlib import Path

import pcbnew

HERE = Path(sys.argv[1]).resolve()
FP_ROOT = Path(r"C:\Program Files\KiCad\10.0\share\kicad\footprints")
NM = 1e-6


def lib_path(lib):
    return str(HERE / "SENTINEL.pretty") if lib == "SENTINEL" else str(FP_ROOT / f"{lib}.pretty")


def size_of(pad):
    try:
        s = pad.GetSize(pcbnew.F_Cu)
    except TypeError:
        s = pad.GetSize()
    return s.x * NM, s.y * NM


def main():
    parts = json.loads((HERE / "parts.json").read_text())
    out = {}
    for ref, value, fpid, *_ in parts:
        if fpid in out:
            continue
        lib, name = fpid.split(":")
        fp = pcbnew.FootprintLoad(lib_path(lib), name)
        if fp is None:
            sys.exit(f"cannot load {fpid}")
        pads = []
        for p in fp.Pads():
            pos = p.GetPosition()
            w, h = size_of(p)
            ls = p.GetLayerSet()
            attr = p.GetAttribute()
            pads.append({
                "num": p.GetNumber(), "x": pos.x * NM, "y": pos.y * NM, "w": w, "h": h,
                "rot": p.GetOrientationDegrees(),
                "shape": {pcbnew.PAD_SHAPE_CIRCLE: "circle", pcbnew.PAD_SHAPE_OVAL: "oval"}.get(p.GetShape(), "rect"),
                "tht": attr in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH),
                "npth": attr == pcbnew.PAD_ATTRIB_NPTH,
                "drill": p.GetDrillSize().x * NM,
                "top": ls.Contains(pcbnew.F_Cu), "bottom": ls.Contains(pcbnew.B_Cu),
            })
        crt, cut = None, []
        for g in fp.GraphicalItems():
            bb = g.GetBoundingBox()
            box = [bb.GetLeft() * NM, bb.GetTop() * NM, bb.GetRight() * NM, bb.GetBottom() * NM]
            if g.GetLayer() == pcbnew.F_CrtYd:
                crt = box if crt is None else [min(crt[0], box[0]), min(crt[1], box[1]),
                                              max(crt[2], box[2]), max(crt[3], box[3])]
            elif g.GetLayer() == pcbnew.Edge_Cuts:
                cut.append(box)
        if crt is None:
            bb = fp.GetBoundingBox(False)
            crt = [bb.GetLeft() * NM, bb.GetTop() * NM, bb.GetRight() * NM, bb.GetBottom() * NM]
        out[fpid] = {"pads": pads, "courtyard": crt, "cutouts": cut}
    (HERE / "fpgeom.json").write_text(json.dumps(out, indent=1))
    print("footprints dumped:", len(out))


if __name__ == "__main__":
    main()
