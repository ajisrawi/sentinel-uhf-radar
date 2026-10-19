"""
Generic placement / fan-out / routing engine for the SENTINEL KiCad projects.

Usage from a board's pcb_plan.py:
    import pcbgen as P
    P.init(Path(__file__).parent, "PROJECT", width, height, track_w={...})
    P.place_chain(...), P.pack(...), P.BRD.place(...)
    P.run(power_zones=[(P.IN2, "NET", polygon)])

Stack-up assumed by every board: L1 F.Cu components + RF, L2 In1.Cu solid GND,
L3 In2.Cu power pours + routing, L4 B.Cu routing + GND pour.
"""
import heapq
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

sys.path.insert(0, str(Path(__file__).parent))
from sexpr import find, find1, parse  # noqa: E402

CLR = 0.2                 # design clearance
RCLR = 0.25               # clearance the router/placer keeps (margin over DRC)
EDGE = 0.6                # copper to board edge / cutouts
VIA_D, VIA_DRILL = 0.6, 0.3
PVIA_D, PVIA_DRILL = 0.9, 0.45   # power / ground vias
CELL = 0.25
F, IN1, IN2, B = "F.Cu", "In1.Cu", "In2.Cu", "B.Cu"
RF_W, PA_W = 0.56, 1.6

HERE = None
PROJECT = ""
W = H = 0.0
TITLE = ""
COMPS, PADNET, GEOM, CHAINS = {}, {}, {}, []
TRACK_W = defaultdict(lambda: 0.25)
POWER_VIA_NETS = {"GND"}
ZONE_NETS = {"GND"}
NODE_W, NODE_W_TAGS = {}, []
NET_LAYERS = {}           # net -> tuple of layers the router may use
NET_CLR = {}              # net -> clearance (high-voltage nets), enforced both ways
NET_CLASSES = []          # [name, clearance, track width, pattern] written into the board
NET_DOMAIN = {}           # net -> isolation domain; NET_CLR applies across domains
NET_CLR_HARD = set()      # nets whose NET_CLR applies to every other net (e.g. 380 V rails)
DRU = ""                  # KiCad custom design rules text (written as <project>.kicad_dru)


def pair_clr(a, b):
    """Required clearance between copper of nets a and b."""
    if a == b:
        return 0.0
    if a in NET_CLR_HARD or b in NET_CLR_HARD or NET_DOMAIN.get(a) != NET_DOMAIN.get(b):
        return max(RCLR, NET_CLR.get(a, 0), NET_CLR.get(b, 0))
    return RCLR
BRD = None


def init(here, project, width, height, title="", track_w=None, power_nets=(), node_w=None, node_w_tags=()):
    global HERE, PROJECT, W, H, TITLE, COMPS, PADNET, GEOM, CHAINS, BRD, TRACK_W, POWER_VIA_NETS, NODE_W, NODE_W_TAGS
    HERE, PROJECT, W, H, TITLE = Path(here), project, float(width), float(height), title or project
    COMPS, PADNET = load_netlist(HERE / f"{project}.net")
    GEOM = json.loads((HERE / "fpgeom.json").read_text())
    cj = HERE / "chains.json"
    CHAINS = json.loads(cj.read_text()) if cj.exists() else []
    TRACK_W = defaultdict(lambda: 0.25, track_w or {})
    POWER_VIA_NETS = {"GND", *power_nets}
    NODE_W, NODE_W_TAGS = dict(node_w or {}), list(node_w_tags)
    ZONE_NETS.clear()
    ZONE_NETS.add("GND")
    BRD = Board()
    return BRD


# ------------------------------------------------------------------ inputs
def load_netlist(path):
    tree = parse(path.read_text(encoding="utf-8"))
    comps = {}
    for c in find(find1(tree, "components"), "comp"):
        ref = find1(c, "ref")[1]
        comps[ref] = {"fp": find1(c, "footprint")[1], "value": find1(c, "value")[1],
                      "tstamp": find1(c, "tstamps")[1] if find1(c, "tstamps") else ""}
    padnet = {}
    for n in find(find1(tree, "nets"), "net"):
        name = find1(n, "name")[1]
        if name.startswith("unconnected-"):
            continue
        name = name.lstrip("/")
        for node in find(n, "node"):
            padnet[(find1(node, "ref")[1], find1(node, "pin")[1])] = name
    return comps, padnet




def xf(fx, fy, rot, lx, ly):
    t = math.radians(rot)
    return fx + lx * math.cos(t) + ly * math.sin(t), fy - lx * math.sin(t) + ly * math.cos(t)


class Placed:
    def __init__(self, ref, x, y, rot):
        self.ref, self.x, self.y, self.rot = ref, x, y, rot % 360
        self.g = GEOM[COMPS[ref]["fp"]]

    def pads(self):
        """Copper pads in board coordinates: dicts with num, net, shape geometry per layer."""
        out = []
        for p in self.g["pads"]:
            if p.get("npth"):
                pass                          # unplated hole: an obstacle for every net
            elif not (p["top"] or p["bottom"] or p["tht"]) or p["num"] == "":
                continue
            cx, cy = xf(self.x, self.y, self.rot, p["x"], p["y"])
            ang = p["rot"] + self.rot
            if p["shape"] == "circle":
                geom = Point(cx, cy).buffer(p["w"] / 2, 16)
            else:
                hw, hh = p["w"] / 2, p["h"] / 2
                pts = [xf(cx, cy, ang, sx * hw, sy * hh) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                geom = Polygon(pts)
                if p["shape"] == "oval":
                    geom = geom.buffer(0)
            layers = [F, IN1, IN2, B] if p["tht"] else ([F] if p["top"] else []) + ([B] if p["bottom"] else [])
            out.append({"num": p["num"], "net": PADNET.get((self.ref, p["num"])), "geom": geom,
                        "c": (cx, cy), "layers": layers, "tht": p["tht"], "drill": p["drill"]})
        return out

    def courtyard(self):
        x1, y1, x2, y2 = self.g["courtyard"]
        pts = [xf(self.x, self.y, self.rot, a, b) for a, b in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
        return Polygon(pts)

    def cutouts(self):
        out = []
        for x1, y1, x2, y2 in self.g["cutouts"]:
            pts = [xf(self.x, self.y, self.rot, a, b) for a, b in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
            out.append(Polygon(pts))
        return out

    def pad_local(self, num):
        p = next(p for p in self.g["pads"] if p["num"] == num and (p["top"] or p["tht"]))
        return p


# ------------------------------------------------------------------ board model
class Board:
    def __init__(self):
        self.parts = {}
        self.tracks = []          # (layer, (x1,y1), (x2,y2), width, net)
        self.vias = []            # (x, y, dia, drill, net)
        self.zones = []           # (layer, net, polygon, priority)
        self.handled = set()      # (ref, pad) already connected
        self.terminals = defaultdict(list)   # net -> [(x, y, layers)]
        self.outline = box(0, 0, W, H)

    def place(self, ref, x, y, rot=0):
        p = Placed(ref, round(x, 3), round(y, 3), rot)
        self.parts[ref] = p
        return p

    def pad(self, ref, num):
        return next(p for p in self.parts[ref].pads() if p["num"] == num)

    def track(self, layer, a, b, w, net):
        if math.dist(a, b) > 1e-6:
            self.tracks.append((layer, (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4)), w, net))

    def via(self, x, y, net, power=False):
        d, dr = (PVIA_D, PVIA_DRILL) if power else (VIA_D, VIA_DRILL)
        self.vias.append((round(x, 4), round(y, 4), d, dr, net))

    def cutout_union(self):
        return unary_union([c for p in self.parts.values() for c in p.cutouts()] or [Polygon()])

    # copper shapes on a layer, as (geometry, net)
    def copper(self, layer):
        out = []
        for p in self.parts.values():
            for pad in p.pads():
                if layer in pad["layers"]:
                    out.append((pad["geom"], pad["net"]))
        for ly, a, b, w, net in self.tracks:
            if ly == layer:
                out.append((LineString([a, b]).buffer(w / 2, 8), net))
        for x, y, d, dr, net in self.vias:
            out.append((Point(x, y).buffer(d / 2, 12), net))
        return out




# ------------------------------------------------------------------ chain placement
ROTS = (0, 90, 180, 270)


def orient_series(ref, pin_in, pin_out, direction):
    g = GEOM[COMPS[ref]["fp"]]
    pi = next(p for p in g["pads"] if p["num"] == pin_in and p["top"])
    po = next(p for p in g["pads"] if p["num"] == pin_out and p["top"])
    best = None
    for r in ROTS:
        ix, iy = xf(0, 0, r, pi["x"], pi["y"])
        ox, oy = xf(0, 0, r, po["x"], po["y"])
        score = (ox - ix) * direction - 0.5 * abs(oy - iy)
        if best is None or score > best[0]:
            best = (score, r, (ix, iy), (ox, oy))
    return best[1], best[2], best[3]


def orient_vertical(ref, near, far, up):
    """Rotation that puts `near` closest to the line and `far` straight away from it."""
    g = GEOM[COMPS[ref]["fp"]]
    pn = next(p for p in g["pads"] if p["num"] == near and p["top"])
    pf = next(p for p in g["pads"] if p["num"] == far and p["top"])
    want = -1 if up else 1
    best = None
    for r in ROTS:
        nx, ny = xf(0, 0, r, pn["x"], pn["y"])
        fx, fy = xf(0, 0, r, pf["x"], pf["y"])
        score = (fy - ny) * want - abs(fx - nx)
        if best is None or score > best[0]:
            best = (score, r, (nx, ny), (fx, fy))
    return best[1], best[2], best[3]


def extent_x(ref, rot):
    x1, y1, x2, y2 = GEOM[COMPS[ref]["fp"]]["courtyard"]
    xs = [xf(0, 0, rot, a, b)[0] for a, b in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
    ys = [xf(0, 0, rot, a, b)[1] for a, b in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
    return min(xs), max(xs), min(ys), max(ys)


def node_width(nets):
    names = {n for n in nets if n}
    for n in names:
        if n in NODE_W:
            return NODE_W[n]
        for tag, w in NODE_W_TAGS:
            if tag in n:
                return w
    return RF_W


def pad_out(ref, pin):
    """Unit axis (dx, dy) pointing from the part body out through the pad."""
    part = BRD.parts[ref]
    cx, cy = BRD.pad(ref, pin)["c"]
    dx, dy = cx - part.x, cy - part.y
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return (0, 0)
    return (1 if dx > 0 else -1, 0) if abs(dx) >= abs(dy) else (0, 1 if dy > 0 else -1)


def place_chain(ops, x0, y, direction, fixed=None, anchors=None, gap=0.8):
    """Lay out one schematic chain. fixed: ref -> (x, y, rot); anchors: start label -> (ref, pad)."""
    fixed, anchors = fixed or {}, anchors or {}
    cursor = x0
    node = {"start": None, "pts": [], "net": None, "out": None}

    def leg(p, out, dirn):
        """Points from pad p to the line, leaving along the pad's outward axis."""
        if abs(p[1] - y) < 1e-6:
            return []
        ox, oy = out if out else (dirn, 0)
        if ox == 0:                            # top/bottom pin: straight to the line
            return [(p[0], y)]
        jx = p[0] + ox * 1.25                  # side pin: step out of the pin row first
        return [(jx, p[1]), (jx, y)]

    def close(next_xy, next_out=None):
        net = node["net"]
        w = node_width({net})
        path = [node["start"]] + leg(node["start"], node["out"], direction)
        path += [(x, y) for x in node["pts"]]
        if next_xy:
            path += leg(next_xy, next_out, -direction)[::-1] + [next_xy]
        # neck down to 0.25 mm on the first/last millimetre at fine-pitch IC pins
        segs = list(zip(path, path[1:]))
        out_pts = []
        for i, (a, b) in enumerate(segs):
            narrow_a = i == 0 and node["out"] is not None
            narrow_b = i == len(segs) - 1 and next_out is not None
            L = math.dist(a, b)
            if (narrow_a or narrow_b) and L > 1e-6:
                k = min(1.0, L) / L
                if narrow_a and narrow_b and L <= 2.0:
                    out_pts.append((a, b, min(w, 0.25)))
                    continue
                if narrow_a:
                    m = (a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)
                    out_pts.append((a, m, min(w, 0.25)))
                    a = m
                if narrow_b:
                    m = (b[0] - (b[0] - a[0]) * min(1.0, math.dist(a, b)) / max(math.dist(a, b), 1e-9),
                         b[1] - (b[1] - a[1]) * min(1.0, math.dist(a, b)) / max(math.dist(a, b), 1e-9))
                    out_pts.append((a, m, w))
                    out_pts.append((m, b, min(w, 0.25)))
                    continue
            out_pts.append((a, b, w))
        for a, b, ww in out_pts:
            BRD.track(F, a, b, ww, net)

    for op in ops:
        kind = op[0]
        if kind == "start":
            ref, pin = op[1], op[2]
            fx, fy, r = fixed[ref]
            p = BRD.place(ref, fx, fy, r)
            c = BRD.pad(ref, pin)["c"]
            node.update(start=c, pts=[], net=PADNET[(ref, pin)], out=None)
            BRD.handled.add((ref, pin))
            cursor = c[0] + direction * 2.6
        elif kind == "start_label":
            net = op[1]
            if net in anchors:
                aref, apin = anchors[net]
                c = BRD.pad(aref, apin)["c"]
                BRD.handled.add((aref, apin))
                node.update(start=c, pts=[], net=net, out=pad_out(aref, apin))
                # parts start beyond the vertical jog from the anchor pad to the line
                cursor = c[0] + direction * (1.25 + node_width({net}) / 2 + 0.6) if abs(c[1] - y) > 1e-6 else c[0]
            else:
                node.update(start=(cursor, y), pts=[], net=net, out=None)
                BRD.via(cursor, y, net)
                BRD.terminals[net].append((cursor, y, (F, IN2, B)))
                cursor += direction * 1.0
        elif kind in ("series", "end"):
            ref, pin_in = op[1], op[2]
            pin_out = op[3] if kind == "series" else None
            if ref in fixed:
                fx, fy, r = fixed[ref]
                BRD.place(ref, fx, fy, r)
            else:
                if pin_out:
                    r, li, lo = orient_series(ref, pin_in, pin_out, direction)
                else:
                    g = GEOM[COMPS[ref]["fp"]]
                    pi = next(p for p in g["pads"] if p["num"] == pin_in and p["top"])
                    r = max(ROTS, key=lambda rr: -xf(0, 0, rr, pi["x"], pi["y"])[0] * direction
                            - 0.3 * abs(xf(0, 0, rr, pi["x"], pi["y"])[1]))
                    li = xf(0, 0, r, pi["x"], pi["y"])
                ex0, ex1, _, _ = extent_x(ref, r)
                # x so that the courtyard starts `gap` after the cursor
                lead = -ex0 if direction > 0 else ex1
                fx = cursor + direction * (gap + lead)
                fy = y - li[1]
                BRD.place(ref, fx, fy, r)
            ci = BRD.pad(ref, pin_in)["c"]
            BRD.handled.add((ref, pin_in))
            node["net"] = node["net"] or PADNET[(ref, pin_in)]
            close(ci, pad_out(ref, pin_in) if GEOM[COMPS[ref]["fp"]]["pads"] and len(BRD.parts[ref].pads()) > 2 else None)
            if kind == "series":
                co = BRD.pad(ref, pin_out)["c"]
                BRD.handled.add((ref, pin_out))
                ex0, ex1, _, _ = extent_x(ref, BRD.parts[ref].rot)
                cursor = (BRD.parts[ref].x + ex1) if direction > 0 else (BRD.parts[ref].x + ex0)
                node.update(start=co, pts=[], net=PADNET.get((ref, pin_out)),
                            out=pad_out(ref, pin_out) if len(BRD.parts[ref].pads()) > 2 else None)
        elif kind == "tapvia":
            x = cursor + direction * 1.6
            node["pts"].append(x)
            BRD.track(F, (x, y), (x, y - 2.0), 0.6, node["net"])
            BRD.via(x, y - 2.0, node["net"])
            BRD.terminals[node["net"]].append((x, y - 2.0, (F, IN2, B)))
            cursor = x + direction * 0.8
        elif kind == "end_label":
            net = op[1]
            x = cursor + direction * 1.5
            close((x, y))
            BRD.via(x, y, net)
            BRD.terminals[net].append((x, y, (F, IN2, B)))
        elif kind == "shunt":
            stack, up, terminal = op[1], op[2], op[3]
            sgn = -1 if up else 1
            ref0 = stack[0][0]
            r0, _, _ = orient_vertical(ref0, stack[0][1], stack[0][2], up)
            ex0, ex1, _, _ = extent_x(ref0, r0)
            xs = cursor + direction * (gap + (-ex0 if direction > 0 else ex1))
            node["pts"].append(xs)
            attach_y = y + sgn * (node_width({node["net"]}) / 2 + 0.6)
            prev_far = None
            for i, (ref, near, far) in enumerate(stack):
                r, ln, lf = orient_vertical(ref, near, far, up)
                _, _, ey0, ey1 = extent_x(ref, r)
                if i == 0:
                    pn = next(p for p in GEOM[COMPS[ref]["fp"]]["pads"] if p["num"] == near)
                    half = max(abs(xf(0, 0, r, pn["w"] / 2, pn["h"] / 2)[1]), abs(xf(0, 0, r, pn["w"] / 2, -pn["h"] / 2)[1]))
                    ny = attach_y + sgn * half
                else:
                    edge = prev_edge + sgn * 0.6
                    ny = edge - (ey0 - ln[1]) if not up else edge - (ey1 - ln[1])
                    ny = edge + (ln[1] - ey0) if not up else edge - (ey1 - ln[1])
                BRD.place(ref, xs - ln[0], ny - ln[1], r)
                cn = BRD.pad(ref, near)["c"]
                cf = BRD.pad(ref, far)["c"]
                BRD.handled.add((ref, near))
                if i == 0:
                    BRD.track(F, (xs, y), cn, node_width({node["net"]}), node["net"])
                else:
                    BRD.track(F, prev_far, cn, 0.5, PADNET[(ref, near)])
                prev_far = cf
                prev_edge = BRD.parts[ref].y + (ey1 if not up else ey0)
                if i < len(stack) - 1:
                    BRD.handled.add((ref, far))
            ex0, ex1, _, _ = extent_x(stack[0][0], BRD.parts[stack[0][0]].rot)
            cursor = (xs + ex1) if direction > 0 else (xs + ex0)
    return cursor


# ------------------------------------------------------------------ region packing
def pack(refs, x0, y0, x1, y1, spacing=1.2, rot=0):
    """Shelf-pack parts left-to-right, top-to-bottom inside a rectangle."""
    x, y, row_h = x0, y0, 0.0
    for ref in refs:
        r = rot if not isinstance(ref, tuple) else ref[1]
        ref = ref if not isinstance(ref, tuple) else ref[0]
        ex0, ex1, ey0, ey1 = extent_x(ref, r)
        w, h = ex1 - ex0, ey1 - ey0
        if x + w > x1:
            x, y, row_h = x0, y + row_h + spacing, 0.0
        if y + h > y1:
            raise RuntimeError(f"region full at {ref}: {(x0, y0, x1, y1)}")
        BRD.place(ref, x - ex0, y - ey0, r)
        x += w + spacing
        row_h = max(row_h, h)


# ------------------------------------------------------------------ obstacle helpers
def blocked_by(geom, layers, net, clr=RCLR):
    for ly in layers:
        for g, n in BRD.copper(ly):
            if n != net and g.distance(geom) < clr:
                return True
    return False


class CopperIndex:
    """Cached per-layer copper shapes for fast clearance tests during fan-out."""

    def __init__(self):
        from shapely.strtree import STRtree
        self.STRtree = STRtree
        self.rebuild()

    def rebuild(self):
        self.shapes = {ly: BRD.copper(ly) for ly in (F, IN2, B)}
        self.trees = {ly: self.STRtree([g for g, _ in s]) if s else None for ly, s in self.shapes.items()}

    def add(self, layer, geom, net):
        self.shapes[layer].append((geom, net))
        self.trees[layer] = self.STRtree([g for g, _ in self.shapes[layer]])

    def clear(self, geom, layers, net, clr=RCLR):
        for ly in layers:
            t = self.trees.get(ly)
            if t is None:
                continue
            cmax = max(clr, NET_CLR.get(net, 0), max(NET_CLR.values(), default=0))
            for i in t.query(geom.buffer(cmax)):
                g, n = self.shapes[ly][i]
                c = max(clr, pair_clr(net, n))
                if n != net and g.distance(geom) < c:
                    return False
        return True


def keepout():
    edge = BRD.outline.exterior.buffer(EDGE)
    cut = BRD.cutout_union().buffer(EDGE)
    return unary_union([edge, cut])


# ------------------------------------------------------------------ fan-out
def fanout(idx, ko):
    """Give every unconnected SMD pad a via (GND: to the plane; others: router terminal)."""
    fails = []
    fanned = set()
    for ref, part in sorted(BRD.parts.items()):
        cx0, cy0 = part.x, part.y
        for pad in part.pads():
            net, num = pad["net"], pad["num"]
            # pads sharing a number (e.g. a DPAK tab and its lead) are separate copper:
            # each gets its own connection unless a chain trace already serves this number
            if net is None or ((ref, num) in BRD.handled and (ref, num) not in fanned):
                continue
            BRD.handled.add((ref, num))
            fanned.add((ref, num))
            if pad["tht"]:
                if net not in ("GND",):
                    BRD.terminals[net].append((pad["c"][0], pad["c"][1], (F, IN2, B), pad["geom"]))
                continue
            g = pad["geom"]
            power = net in POWER_VIA_NETS
            area = g.area
            vd = PVIA_D if power else VIA_D
            # via-in-pad arrays for big power/ground pads
            if power and area > (2.0 if net != "GND" else 6.0):
                shrunk = g.buffer(-vd / 2 - 0.15)
                pts = []
                if not shrunk.is_empty:
                    minx, miny, maxx, maxy = shrunk.bounds
                    pts = [(x, y) for x in np.arange(minx, maxx + 1e-6, 1.6) for y in np.arange(miny, maxy + 1e-6, 1.6)]
                placed = 0
                first = None
                for x, y in pts:
                    v = Point(x, y).buffer(vd / 2)
                    if g.contains(v) and not v.intersects(ko) and idx.clear(v, (IN2, B), net):
                        BRD.via(x, y, net, power=True)
                        for ly in (F, IN2, B):
                            idx.add(ly, v, net)
                        placed += 1
                        first = first or (x, y)
                if placed:
                    if net not in ZONE_NETS:
                        BRD.terminals[net].append((first[0], first[1], (F, IN2, B)))
                    continue
            # dog-bone via: search outward from the pad
            pcx, pcy = pad["c"]
            ox, oy = pcx - cx0, pcy - cy0
            base = math.atan2(oy, ox) if abs(ox) + abs(oy) > 1e-3 else 0.0
            minx, miny, maxx, maxy = g.bounds
            pw, ph = maxx - minx, maxy - miny
            if max(pw, ph) > 1.6 * min(pw, ph):    # elongated pad: escape along its long axis, away from the body
                base = (0.0 if ox >= 0 else math.pi) if pw > ph else (math.pi / 2 if oy >= 0 else -math.pi / 2)
            r0 = max(maxx - minx, maxy - miny) / 2
            done = False
            for vclr, dist in [(c, d) for c in (0.5, RCLR, CLR + 0.01) for d in np.arange(r0 + vd / 2 + 0.3, r0 + 8.0, 0.25)]:
                for k in range(24):
                    a = base + (k + 1) // 2 * (1 if k % 2 else -1) * math.pi / 12
                    vx, vy = pcx + dist * math.cos(a), pcy + dist * math.sin(a)
                    v = Point(vx, vy).buffer(vd / 2, 12)
                    stub = LineString([(pcx, pcy), (vx, vy)]).buffer(0.1, 6)
                    if v.intersects(ko) or stub.intersects(ko):
                        continue
                    if not idx.clear(v, (F, IN2, B), net, clr=vclr) or not idx.clear(stub.difference(g), (F,), net):
                        continue
                    BRD.via(vx, vy, net, power=power)
                    BRD.track(F, (pcx, pcy), (vx, vy), 0.2, net)
                    for ly in (F, IN2, B):
                        idx.add(ly, v, net)
                    idx.add(F, stub, net)
                    if net not in ZONE_NETS:
                        BRD.terminals[net].append((vx, vy, (F, IN2, B)))
                    done = True
                    break
                if done:
                    break
            if not done:
                # fine-pitch fallbacks: ground pins tie inward to the exposed pad,
                # signal pins become F.Cu router terminals (escape without a via)
                ep = [q for q in part.pads() if q["net"] == net and q["geom"].area > 6 and q["num"] != num]
                if ep:
                    from shapely.ops import nearest_points
                    tgt = nearest_points(ep[0]["geom"].buffer(-0.15), Point(pcx, pcy))[0]
                    BRD.track(F, (pcx, pcy), (tgt.x, tgt.y), 0.2, net)
                    idx.add(F, LineString([(pcx, pcy), (tgt.x, tgt.y)]).buffer(0.1), net)
                elif net not in ZONE_NETS:
                    BRD.terminals[net].append((pcx, pcy, (F,), g))
                else:
                    # boxed-in ground pin: via under the package body, between the pin rows
                    v = Point(cx0, cy0).buffer(VIA_D / 2, 12)
                    stub = LineString([(pcx, pcy), (cx0, cy0)]).buffer(0.1, 6)
                    if idx.clear(v, (F, IN2, B), net, clr=CLR + 0.01) and idx.clear(stub.difference(g), (F,), net, clr=CLR + 0.01):
                        BRD.via(cx0, cy0, net)
                        BRD.track(F, (pcx, pcy), (cx0, cy0), 0.2, net)
                        for ly in (F, IN2, B):
                            idx.add(ly, v, net)
                        idx.add(F, stub, net)
                    else:
                        fails.append(f"{ref}.{num}({net})")
    return fails


# ------------------------------------------------------------------ grid router
class Router:
    def __init__(self, layers=(F, IN2, B), blocked_zones=None):
        self.layers = layers
        self.nx, self.ny = int(W / CELL) + 1, int(H / CELL) + 1
        self.blocked_zones = blocked_zones or {}

    def _raster(self, shapes, inflate):
        img = Image.new("1", (self.nx, self.ny), 0)
        dr = ImageDraw.Draw(img)
        for g in shapes:
            gg = g.buffer(inflate, 6)
            polys = [gg] if gg.geom_type == "Polygon" else list(gg.geoms)
            for pg in polys:
                if pg.is_empty:
                    continue
                pts = [(x / CELL, y / CELL) for x, y in pg.exterior.coords]
                dr.polygon(pts, fill=1)
        return np.array(img, dtype=bool).T        # [ix, iy]

    def ko_mask(self, inflate):
        img = Image.new("1", (self.nx, self.ny), 1)
        dr = ImageDraw.Draw(img)
        m = EDGE + inflate
        dr.rectangle([m / CELL, m / CELL, (W - m) / CELL, (H - m) / CELL], fill=0)
        for c in BRD.cutout_union().geoms if BRD.cutout_union().geom_type != "Polygon" else [BRD.cutout_union()]:
            if c.is_empty:
                continue
            cc = c.buffer(EDGE + inflate, 4)
            dr.polygon([(x / CELL, y / CELL) for x, y in cc.exterior.coords], fill=1)
        return np.array(img, dtype=bool).T

    def masks(self, net, w):
        out = {}
        via_block = np.zeros((self.nx, self.ny), bool)
        for ly in tuple(dict.fromkeys(self.layers + (F,))):
            groups = defaultdict(list)
            for g, n in BRD.copper(ly):
                if n != net:
                    groups[pair_clr(net, n)].append(g)
            for zpoly, znet in self.blocked_zones.get(ly, []):
                if znet != net:
                    groups[pair_clr(net, znet)].append(zpoly)
            trk = self.ko_mask(w / 2 + CELL * 0.71)
            vb = self.ko_mask(VIA_D / 2 + CELL * 0.71)
            for c, shapes in groups.items():
                trk |= self._raster(shapes, c + w / 2 + CELL * 0.71)
                vb |= self._raster(shapes, c + VIA_D / 2 + CELL * 0.71)
            via_block |= vb
            if ly in self.layers:
                out[ly] = trk
        return out, via_block

    def layers_for(self, net):
        return [l for l in self.layers if l in NET_LAYERS.get(net, self.layers)]

    def route(self, net, terms, w):
        """terms: list of (x, y, layers[, geom]). Returns list of paths or None."""
        masks, via_block = self.masks(net, w)
        L = self.layers_for(net)
        tree = set()

        def cells_of(t):
            x, y = t[0], t[1]
            ix, iy = int(round(x / CELL)), int(round(y / CELL))
            lis = [L.index(ly) for ly in t[2] if ly in L]
            cs = {(li, ix, iy) for li in lis}
            if len(t) > 3:   # pad terminal: every cell inside the pad (shrunk so the track stays on it)
                inner = t[3].buffer(-w / 2) if t[3].buffer(-w / 2).area > 0 else t[3]
                minx, miny, maxx, maxy = t[3].bounds
                for jx in range(int(minx / CELL), int(maxx / CELL) + 2):
                    for jy in range(int(miny / CELL), int(maxy / CELL) + 2):
                        if inner.contains(Point(jx * CELL, jy * CELL)):
                            cs.update((li, jx, jy) for li in lis)
            return cs

        groups = [cells_of(t) for t in terms]
        for gcells in groups:
            for li, ix, iy in gcells:          # own terminals are always enterable
                masks[L[li]][ix, iy] = False
        tree |= groups[0]
        remaining = groups[1:]
        paths = []
        unreached = 0
        while remaining:
            targets = set().union(*remaining)
            tx = np.array([c[1] for c in targets])
            ty = np.array([c[2] for c in targets])
            path = self._astar(tree, targets, masks, via_block, L, tx, ty)
            if path is None:
                # nothing left is reachable from this tree: start a new island from the next
                # group so the remaining pins still connect among themselves
                unreached += 1
                tree = set(remaining.pop(0))
                continue
            paths.append(path)
            tree |= set(path)
            hit = path[-1]
            remaining = [g for g in remaining if hit not in g]
            for g in [g for g in remaining if g & tree]:
                remaining.remove(g)
        return paths, unreached

    def _astar(self, sources, targets, masks, via_block, L, tx, ty):
        moves = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
                 (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
        tx0, tx1, ty0, ty1 = tx.min(), tx.max(), ty.min(), ty.max()

        def h(ix, iy):
            dx = max(tx0 - ix, 0, ix - tx1)
            dy = max(ty0 - iy, 0, iy - ty1)
            return max(dx, dy) + 0.414 * min(dx, dy)

        openq = []
        best = {}
        came = {}
        for s in sources:
            best[s] = 0.0
            heapq.heappush(openq, (h(s[1], s[2]), 0.0, s))
        mx = [masks[l] for l in L]
        nxl, nyl = self.nx, self.ny
        expanded = 0
        while openq:
            f, g, cur = heapq.heappop(openq)
            if g > best.get(cur, 1e18):
                continue
            if cur in targets:
                path = [cur]
                while path[-1] in came:
                    path.append(came[path[-1]])
                return path[::-1]
            expanded += 1
            if expanded > 4_000_000:
                return None
            li, ix, iy = cur
            for dx, dy, c in moves:
                jx, jy = ix + dx, iy + dy
                if not (0 <= jx < nxl and 0 <= jy < nyl):
                    continue
                nb = (li, jx, jy)
                if mx[li][jx, jy] and nb not in targets:
                    continue
                if dx and dy and (mx[li][ix + dx, iy] or mx[li][ix, iy + dy]):
                    continue
                ng = g + c
                if ng < best.get(nb, 1e18):
                    best[nb] = ng
                    came[nb] = cur
                    heapq.heappush(openq, (ng + 1.3 * h(jx, jy), ng, nb))
            # layer change through a via
            if not via_block[ix, iy]:
                for lj in range(len(L)):
                    if lj == li:
                        continue
                    nb = (lj, ix, iy)
                    if mx[lj][ix, iy] and nb not in targets:
                        continue
                    ng = g + 12.0
                    if ng < best.get(nb, 1e18):
                        best[nb] = ng
                        came[nb] = cur
                        heapq.heappush(openq, (ng + h(ix, iy), ng, nb))
        return None


def emit_path(path, net, w, L):
    """Convert a cell path into tracks (merged straight runs) and vias."""
    pts = [(L[c[0]], c[1] * CELL, c[2] * CELL) for c in path]
    run = [pts[0]]
    for p in pts[1:]:
        if p[0] != run[-1][0]:
            flush(run, net, w)
            BRD.via(p[1], p[2], net)
            run = [p]
        else:
            run.append(p)
    flush(run, net, w)


def flush(run, net, w):
    if len(run) < 2:
        return
    ly = run[0][0]
    seg = [run[0]]
    for p in run[1:]:
        if len(seg) >= 2:
            d1 = (seg[-1][1] - seg[-2][1], seg[-1][2] - seg[-2][2])
            d2 = (p[1] - seg[-1][1], p[2] - seg[-1][2])
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) < 1e-9 and d1[0] * d2[0] + d1[1] * d2[1] > 0:
                seg[-1] = p
                continue
        seg.append(p)
    for a, b in zip(seg, seg[1:]):
        BRD.track(ly, (a[1], a[2]), (b[1], b[2]), w, net)


def courtyard_overlaps():
    items = list(BRD.parts.values())
    bad = []
    for i, a in enumerate(items):
        ca = a.courtyard()
        for b in items[i + 1:]:
            if ca.intersection(b.courtyard()).area > 0.05:
                bad.append((a.ref, b.ref))
    return bad


def run(power_zones=(), stitch=True, gnd_keepout=None, first=()):
    """Fan out, route, pour and write plan.json. power_zones: [(layer, net, polygon)]."""
    missing = set(COMPS) - set(BRD.parts)
    if missing:
        raise RuntimeError(f"unplaced: {sorted(missing)}")
    ov = courtyard_overlaps()
    print("courtyard overlaps:", ov)
    blocked = {}
    for ly, net, poly in power_zones:
        poly = poly.difference(BRD.cutout_union().buffer(1.0))
        BRD.zones.append((ly, net, poly, 2))
        ZONE_NETS.add(net)
        blocked.setdefault(ly, []).append((poly, net))
    ko = keepout()
    idx = CopperIndex()
    fails = fanout(idx, ko)
    print("fanout failures:", fails)
    # pour nets: vias that landed outside their pour are routed into it
    for ly, net, poly in power_zones:
        polys = [z[0] for zl in blocked.values() for z in zl if z[1] == net]
        vs = [(v[0], v[1]) for v in BRD.vias if v[4] == net]
        inside = [v for v in vs if any(pg.contains(Point(v)) for pg in polys)]
        outside = [v for v in vs if v not in inside]
        if outside and inside and not any(t[:2] == inside[0] for t in BRD.terminals[net]):
            BRD.terminals[net] += [(x, y, (F, IN2, B)) for x, y in outside] + [(inside[0][0], inside[0][1], (F, IN2, B))]
    router = Router(blocked_zones=blocked)
    nets = {n: t for n, t in BRD.terminals.items() if len(t) > 1}
    span = {n: np.ptp([t[0] for t in nets[n]]) + np.ptp([t[1] for t in nets[n]]) for n in nets}
    order = sorted(nets, key=lambda n: (n not in first, TRACK_W[n] < 0.4, span[n]))
    routed = {}

    def try_route(net):
        if net in routed:
            rip(net)
        best = None
        for w in dict.fromkeys((TRACK_W[net], 0.3, 0.25)):
            paths, unr = router.route(net, nets[net], w)
            if best is None or unr < best[2]:
                best = (w, paths, unr)
            if unr == 0:
                break
        w, paths, unr = best
        if paths:
            t0, v0 = len(BRD.tracks), len(BRD.vias)
            for p in paths:
                emit_path(p, net, w, router.layers_for(net))
            routed[net] = (BRD.tracks[t0:], BRD.vias[v0:])
        return unr == 0

    def rip(net):
        trk, via = routed.pop(net)
        ts, vs = set(map(id, trk)), set(map(id, via))
        BRD.tracks[:] = [t for t in BRD.tracks if id(t) not in ts]
        BRD.vias[:] = [v for v in BRD.vias if id(v) not in vs]

    failed = []
    for i, net in enumerate(order):
        ok = try_route(net)
        print(f"  [{i + 1}/{len(order)}] {net}: {'ok' if ok else 'FAILED'}", flush=True)
        if not ok:
            failed.append(net)
    for rnd in range(8):
        if not failed:
            break
        still = []
        for net in failed:
            xs = [t[0] for t in nets[net]]
            ys = [t[1] for t in nets[net]]
            region = box(min(xs) - 4, min(ys) - 4, max(xs) + 4, max(ys) + 4)
            victims = [n for n, (trk, _) in routed.items()
                       if any(region.intersects(LineString([a, b])) for _, a, b, _, _ in trk)]
            victims = sorted(victims, key=lambda n: span[n])[: 4 + 4 * rnd]
            for v in victims:
                rip(v)
            ok = try_route(net)
            lost = [v for v in sorted(victims, key=lambda n: span[n]) if not try_route(v)]
            print(f"  rip-up round {rnd + 1}: {net} {'ok' if ok else 'FAILED'}; "
                  f"ripped {len(victims)}, lost {lost}", flush=True)
            if not ok:
                still.append(net)
            still += lost
        failed = list(dict.fromkeys(still))
    print("routing failures:", failed)

    # ground zones: full plane on In1, pours on F.Cu / B.Cu / In2 (lowest priority)
    full = box(0.3, 0.3, W - 0.3, H - 0.3).difference(BRD.cutout_union().buffer(0.5))
    if gnd_keepout is not None:
        full = full.difference(gnd_keepout)
    for ly, pr in ((IN1, 0), (F, 0), (B, 0), (IN2, 0)):
        BRD.zones.append((ly, "GND", full, pr))
    # ground stitching vias on a 4 mm grid wherever every layer is clear
    idx.rebuild()
    n_stitch = 0
    for x in (np.arange(4, W - 3, 4.0) if stitch else []):
        for y in np.arange(3, H - 3, 4.0):
            v = Point(x, y).buffer(PVIA_D / 2)
            if v.intersects(ko) or any(v.intersects(z[0].buffer(0.5)) for zl in blocked.values() for z in zl)                     or (gnd_keepout is not None and v.intersects(gnd_keepout)):
                continue
            if idx.clear(v, (F, IN2, B), "GND", clr=0.6):
                BRD.via(x, y, "GND", power=True)
                n_stitch += 1
    print("stitching vias:", n_stitch)

    def poly_pts(p):
        geoms = [p] if p.geom_type == "Polygon" else list(p.geoms)
        return [[list(map(lambda c: [round(c[0], 3), round(c[1], 3)], g.exterior.coords))] +
                [[[round(c[0], 3), round(c[1], 3)] for c in r.coords] for r in g.interiors] for g in geoms]

    plan = {
        "size": [W, H], "title": TITLE, "netclasses": NET_CLASSES,
        "parts": [{"ref": p.ref, "fp": COMPS[p.ref]["fp"], "value": COMPS[p.ref]["value"],
                   "tstamp": COMPS[p.ref]["tstamp"], "x": p.x, "y": p.y, "rot": p.rot}
                  for p in BRD.parts.values()],
        "tracks": BRD.tracks, "vias": BRD.vias,
        "zones": [{"layer": ly, "net": net, "polys": poly_pts(pg), "priority": pr} for ly, net, pg, pr in BRD.zones],
        "padnets": [[r, p, n] for (r, p), n in PADNET.items()],
        "routing_failures": failed, "fanout_failures": fails, "courtyard_overlaps": ov,
    }
    (HERE / "plan.json").write_text(json.dumps(plan))
    if DRU:
        (HERE / f"{PROJECT}.kicad_dru").write_text(DRU)
    (HERE / "export").mkdir(exist_ok=True)
    preview(HERE / "export" / "pcb_plan_preview.png", failed)
    print(f"tracks {len(BRD.tracks)}  vias {len(BRD.vias)}")
    return plan



def preview(path, failed=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(max(8, 23 * W / 230), max(6, 13 * H / 130 + 1)), dpi=110)
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.set_aspect("equal")
    ax.add_patch(plt.Rectangle((0, 0), W, H, fc="#0d2b1a", ec="k"))
    for c in [c for p in BRD.parts.values() for c in p.cutouts()]:
        ax.fill(*c.exterior.xy, fc="white", ec="k")
    col = {F: "#d64040", IN2: "#d9a520", B: "#3b7de0"}
    for ly, a_, b_, w, net in BRD.tracks:
        ax.plot([a_[0], b_[0]], [a_[1], b_[1]], color=col[ly], lw=max(w * 4, 0.6), alpha=0.85, solid_capstyle="round")
    for p in BRD.parts.values():
        for pad in p.pads():
            if F in pad["layers"]:
                ax.fill(*pad["geom"].exterior.xy, fc="#c8a060", ec="none", alpha=0.9)
        cy = p.courtyard()
        ax.plot(*cy.exterior.xy, color="#cccccc", lw=0.4)
        ax.text(p.x, p.y, p.ref, fontsize=4, color="white", ha="center", va="center")
    for x, y, d, dr, net in BRD.vias:
        ax.add_patch(plt.Circle((x, y), d / 2, fc="#999999" if net == "GND" else "#ffffff", ec="none"))
    for net in failed:
        pts = BRD.terminals.get(net, [])
        ax.plot([t[0] for t in pts], [t[1] for t in pts], "m--", lw=1)
    ax.set_title(TITLE + " - red F.Cu, gold In2.Cu, blue B.Cu" + (f"  | unrouted: {', '.join(failed)}" if failed else ""))
    fig.tight_layout()
    fig.savefig(path)


