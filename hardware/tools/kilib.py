"""Load symbols from the installed KiCad libraries (resolving `extends`)."""
import copy
import math
from functools import lru_cache
from pathlib import Path

from sexpr import Sym, find, find1, parse

KICAD_SHARE = Path(r"C:\Program Files\KiCad\10.0\share\kicad")
SYM_DIR = KICAD_SHARE / "symbols"


@lru_cache(maxsize=None)
def _lib(name):
    return parse((SYM_DIR / f"{name}.kicad_sym").read_text(encoding="utf-8"))


def _raw(lib, name):
    for s in find(_lib(lib), "symbol"):
        if s[1] == name:
            return s
    raise KeyError(f"{lib}:{name}")


def load_symbol(lib_id, lib_tree=None):
    """Return the flattened symbol definition named `lib_id` (e.g. 'Device:R')."""
    lib, name = lib_id.split(":")
    s = copy.deepcopy(_raw(lib, name) if lib_tree is None else
                      next(x for x in find(lib_tree, "symbol") if x[1] == name))
    ext = find1(s, "extends")
    if ext:
        base = load_symbol(f"{lib}:{ext[1]}", lib_tree)
        own_props = {p[1]: p for p in find(s, "property")}
        flat = [Sym("symbol"), lib_id]
        for c in base[2:]:
            if isinstance(c, list) and c[0] == "property" and c[1] in own_props:
                flat.append(own_props.pop(c[1]))
            elif isinstance(c, list) and c[0] == "symbol":
                c = copy.deepcopy(c)
                c[1] = c[1].replace(ext[1], name, 1)
                flat.append(c)
            else:
                flat.append(c)
        flat.extend(own_props.values())
        return flat
    s[1] = lib_id
    return s


def pins(symdef, unit=1, body_style=1):
    """Pins of a symbol unit: list of dicts with number, name, type, x, y, angle, length."""
    out = []
    base = symdef[1].split(":")[-1]
    for sub in find(symdef, "symbol"):
        tag = sub[1].rsplit("_", 2)
        u, st = int(tag[-2]), int(tag[-1])
        if u not in (0, unit) or st not in (0, body_style):
            continue
        for p in find(sub, "pin"):
            at = find1(p, "at")
            out.append({
                "type": str(p[1]),
                "name": find1(p, "name")[1],
                "number": find1(p, "number")[1],
                "x": float(at[1]), "y": float(at[2]), "angle": float(at[3]) if len(at) > 3 else 0.0,
                "length": float(find1(p, "length")[1]),
                "hidden": any(isinstance(c, Sym) and c == "hide" for c in p)
                          or (find1(p, "hide") is not None and find1(p, "hide")[1] == "yes"),
            })
    return out


def prop(symdef, key):
    p = next((p for p in find(symdef, "property") if p[1] == key), None)
    return p[2] if p else None


def units(symdef):
    us = set()
    for sub in find(symdef, "symbol"):
        us.add(int(sub[1].rsplit("_", 2)[-2]))
    return sorted(u for u in us if u > 0) or [1]


def pin_point(px, py, sx, sy, rot, mirror_x=False):
    """Schematic coordinate of a library pin point for a symbol placed at (sx, sy).

    Library Y is up, schematic Y is down; rot is the placement angle in degrees (CCW).
    """
    x, y = px, -py
    if mirror_x:
        y = -y
    r = math.radians(-rot)
    xr = x * math.cos(r) - y * math.sin(r)
    yr = x * math.sin(r) + y * math.cos(r)
    return round(sx + xr, 4), round(sy + yr, 4)


if __name__ == "__main__":
    import sys
    for lid in sys.argv[1:]:
        s = load_symbol(lid)
        print(f"== {lid}  fp={prop(s, 'Footprint')!r} units={units(s)}")
        for u in units(s):
            for p in pins(s, u):
                print(f"   u{u} {p['number']:>4} {p['name']:<14} {p['type']:<14} "
                      f"({p['x']:7.2f},{p['y']:7.2f}) a={p['angle']:.0f} L={p['length']}{' H' if p['hidden'] else ''}")
