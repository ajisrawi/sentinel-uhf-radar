"""
Programmatic KiCad 10 schematic writer.

Parts are placed by coordinates (or by the RF chain placer), then every pin
is connected either by an explicit wire (chains) or by a short stub plus a
net label / power symbol. The intended netlist is recorded alongside so it
can be compared with what KiCad itself extracts from the file.
"""
import math
import uuid
from collections import defaultdict

from kilib import load_symbol, pin_point, pins, units
from sexpr import Sym, dumps

GRID = 2.54
POWER_NETS = {"GND": "power:GND", "+5V": "power:+5V", "+3V3": "power:+3V3",
              "+12V": "power:+12V", "-5V": "power:-5V"}
NS = uuid.UUID("6f1d2c1e-8a8e-4c55-9d1a-5e17e1a0c0de")


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(map(str, parts))))


def _font(size=1.27, bold=False):
    f = [Sym("font"), [Sym("size"), size, size]]
    if bold:
        f.append([Sym("bold"), Sym("yes")])
    return f


def _prop(key, val, x, y, hide=False, angle=0, justify=None, size=1.27):
    p = [Sym("property"), key, val, [Sym("at"), x, y, angle]]
    if hide:
        p.append([Sym("hide"), Sym("yes")])
    eff = [Sym("effects"), _font(size)]
    if justify:
        eff.append([Sym("justify")] + [Sym(j) for j in justify.split()])
    p.append(eff)
    return p


# ------------------------------------------------------------------ custom symbols
def custom_symbol(name, ref, value, footprint, description, pin_defs, graphics,
                  show_pin_names=True, show_pin_numbers=False, ref_at=None, val_at=None):
    """pin_defs: (number, name, x, y, angle, length). graphics: list of sexpr items."""
    sym = [Sym("symbol"), name]
    pn = [Sym("pin_names"), [Sym("offset"), 0.508]]
    if not show_pin_names:
        pn.append([Sym("hide"), Sym("yes")])
    sym.append(pn)
    if not show_pin_numbers:
        sym.append([Sym("pin_numbers"), [Sym("hide"), Sym("yes")]])
    sym += [[Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes")],
            [Sym("on_board"), Sym("yes")]]
    ys = [p[3] for p in pin_defs] + [0]
    rx, ry, rj = ref_at or (0, max(ys) + 2.54, None)
    vx, vy, vj = val_at or (0, min(ys) - 2.54, None)
    sym.append(_prop("Reference", ref, rx, ry, justify=rj))
    sym.append(_prop("Value", value, vx, vy, justify=vj))
    sym.append(_prop("Footprint", footprint, 0, 0, hide=True))
    sym.append(_prop("Datasheet", "", 0, 0, hide=True))
    sym.append(_prop("Description", description, 0, 0, hide=True))
    sym.append([Sym("symbol"), f"{name}_0_1"] + graphics)
    body = [Sym("symbol"), f"{name}_1_1"]
    for num, pname, x, y, ang, length in pin_defs:
        body.append([Sym("pin"), Sym("passive"), Sym("line"), [Sym("at"), x, y, ang],
                     [Sym("length"), length],
                     [Sym("name"), pname, [Sym("effects"), _font(1.016)]],
                     [Sym("number"), str(num), [Sym("effects"), _font(1.016)]]])
    sym.append(body)
    sym.append([Sym("embedded_fonts"), Sym("no")])
    return sym


def g_rect(x1, y1, x2, y2, fill="background"):
    return [Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2],
            [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
            [Sym("fill"), [Sym("type"), Sym(fill)]]]


def g_poly(pts, fill="background", width=0.254):
    return [Sym("polyline"), [Sym("pts")] + [[Sym("xy"), x, y] for x, y in pts],
            [Sym("stroke"), [Sym("width"), width], [Sym("type"), Sym("default")]],
            [Sym("fill"), [Sym("type"), Sym(fill)]]]


def g_circle(x, y, r, fill="background"):
    return [Sym("circle"), [Sym("center"), x, y], [Sym("radius"), r],
            [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("default")]],
            [Sym("fill"), [Sym("type"), Sym(fill)]]]


def g_text(s, x, y, size=1.27):
    return [Sym("text"), s, [Sym("at"), x, y, 0], [Sym("effects"), _font(size)]]


# ------------------------------------------------------------------ schematic model
class Part:
    def __init__(self, sch, ref, lib_id, value, footprint, x, y, rot=0, unit=1, nets=None, fields=None):
        self.sch, self.ref, self.lib_id, self.value, self.fp = sch, ref, lib_id, value, footprint
        self.x, self.y, self.rot, self.unit = x, y, rot, unit
        self.nets = dict(nets or {})
        self.fields = dict(fields or {})
        self.symdef = sch.symdef(lib_id)
        self.pins = {p["number"]: p for p in pins(self.symdef, unit)}
        self.wired = set()

    def pin_xy(self, num, at=None):
        p = self.pins[num]
        x, y = at if at else (self.x, self.y)
        return pin_point(p["x"], p["y"], x, y, self.rot)

    def pin_dir(self, num):
        """Outward unit vector (schematic coords) for the pin."""
        p = self.pins[num]
        a = math.radians(p["angle"])
        vx, vy = -math.cos(a), math.sin(a)          # lib->sch flips y
        r = math.radians(-self.rot)
        dx = vx * math.cos(r) - vy * math.sin(r)
        dy = vx * math.sin(r) + vy * math.cos(r)
        return round(dx), round(dy)

    def pin_by_name(self, name):
        for n, p in self.pins.items():
            if p["name"] == name:
                return n
        raise KeyError(f"{self.ref}: no pin {name}")


class Schematic:
    def __init__(self, project, title, paper="A1", custom_lib=None):
        self.project, self.title, self.paper = project, title, paper
        self.root = uid(project, "root")
        self.custom = {s[1]: s for s in (custom_lib or [])}
        self.symdefs = {}
        self.parts = []
        self.wires, self.junctions, self.labels, self.nocons = [], [], [], []
        self.power, self.texts, self.rects = [], [], []
        self.expected = defaultdict(set)
        self.chains = []
        self._pwr_n = 0

    def symdef(self, lib_id):
        if lib_id not in self.symdefs:
            lib, name = lib_id.split(":")
            if lib == "SENTINEL":
                import copy
                s = copy.deepcopy(self.custom[name])
                s[1] = lib_id
                self.symdefs[lib_id] = s
            else:
                self.symdefs[lib_id] = load_symbol(lib_id)
        return self.symdefs[lib_id]

    def add(self, ref, lib_id, value, footprint, x, y, rot=0, nets=None, unit=1, **fields):
        p = Part(self, ref, lib_id, value, footprint, x, y, rot, unit, nets, fields)
        self.parts.append(p)
        return p

    def wire(self, a, b):
        if a != b:
            self.wires.append((a, b))

    def junction(self, xy):
        self.junctions.append(xy)

    def text(self, s, x, y, size=2.54, bold=True):
        self.texts.append((s, x, y, size, bold))

    def rect(self, x1, y1, x2, y2):
        self.rects.append((x1, y1, x2, y2))

    # -------------------------------------------------------------- connection resolution
    def _power_symbol(self, net, xy, direction):
        lib_id = POWER_NETS[net]
        self.symdef(lib_id)
        dx, dy = direction
        if net == "GND":
            rot = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}[(dx, dy)]
        else:
            rot = {(0, -1): 0, (0, 1): 180, (-1, 0): 90, (1, 0): 270}[(dx, dy)]
        self._pwr_n += 1
        self.power.append((f"#PWR{self._pwr_n:03d}", lib_id, net, xy, rot))

    def pwr_flag(self, net, x, y):
        self.symdef("power:PWR_FLAG")
        self._pwr_n += 1
        self.power.append((f"#FLG{self._pwr_n:03d}", "power:PWR_FLAG", "PWR_FLAG", (x, y), 0))
        end = (x, y + GRID)
        self.wire((x, y), end)
        if net in POWER_NETS:
            self._power_symbol(net, end, (0, 1))
        else:
            self.labels.append((net, end, 270))

    def resolve(self, stub=GRID):
        for p in self.parts:
            pending = []
            for num, pin in p.pins.items():
                net = p.nets.get(num)
                if pin["hidden"]:
                    continue
                if num in p.wired:
                    continue
                if net is None:
                    if pin["type"] == "no_connect":
                        continue
                    raise ValueError(f"{p.ref} pin {num} ({pin['name']}) has no net")
                xy = p.pin_xy(num)
                if net == "NC":
                    self.nocons.append(xy)
                    continue
                d = p.pin_dir(num)
                end = (round(xy[0] + d[0] * stub, 4), round(xy[1] + d[1] * stub, 4))
                self.wire(xy, end)
                self.expected[net].add((p.ref, num))
                pending.append((num, net, d, end))

            # adjacent pins on the same side with the same power net share one symbol
            done = set()
            groups = defaultdict(list)
            for num, net, d, end in pending:
                if net in POWER_NETS:
                    line = end[1] if d[1] else end[0]
                    groups[(net, d, line)].append((num, end))
            for (net, d, line), members in groups.items():
                if len(members) < 2:
                    continue
                along = (lambda e: e[0]) if d[1] else (lambda e: e[1])
                members.sort(key=lambda m: along(m[1]))
                lo, hi = along(members[0][1]), along(members[-1][1])
                names = {m[0] for m in members}
                blocked = any(n not in names and dd == d and (e[1] if d[1] else e[0]) == line
                              and lo < along(e) < hi for n, _, dd, e in pending)
                if blocked:
                    continue
                for (_, a), (_, b) in zip(members, members[1:]):
                    self.wire(a, b)
                for _, e in members[1:-1]:
                    self.junction(e)
                self._power_symbol(net, members[0][1], d)
                done |= names
            for num, net, d, end in pending:
                if num in done:
                    continue
                if net in POWER_NETS:
                    self._power_symbol(net, end, d)
                else:
                    ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[d]
                    self.labels.append((net, end, ang))
        # hidden pins stacked on a visible pin inherit its net
        for p in self.parts:
            for num, pin in p.pins.items():
                if not pin["hidden"] or pin["type"] == "no_connect":
                    continue
                for vn, vp in p.pins.items():
                    if not vp["hidden"] and (vp["x"], vp["y"]) == (pin["x"], pin["y"]):
                        net = p.nets.get(vn)
                        if net and net != "NC":
                            self.expected[net].add((p.ref, num))

    # -------------------------------------------------------------- writer
    def _symbol_instance(self, ref, lib_id, value, fp, x, y, rot, unit, fields, hide_ref=False):
        sd = self.symdef(lib_id)
        u = uid(self.project, ref, unit)
        inst = [Sym("symbol"), [Sym("lib_id"), lib_id], [Sym("at"), x, y, rot], [Sym("unit"), unit],
                [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("no" if hide_ref else "yes")],
                [Sym("on_board"), Sym("no" if hide_ref else "yes")], [Sym("dnp"), Sym("no")],
                [Sym("uuid"), u]]
        is_pwr = lib_id.startswith("power:")
        if is_pwr:
            inst.append(_prop("Reference", ref, x, y, hide=True))
            o = 3.81
            if lib_id == "power:GND":
                off = {0: (0, o), 180: (0, -o), 90: (o, 0), 270: (-o, 0)}[rot]
            else:
                off = {0: (0, -o), 180: (0, o), 90: (-o, 0), 270: (o, 0)}[rot]
            inst.append(_prop("Value", value, x + off[0], y + off[1]))
        else:
            # use the library's own property positions, transformed like pins
            for key, val in (("Reference", ref), ("Value", value)):
                lp = next(pp for pp in sd if isinstance(pp, list) and pp[:2] == [Sym("property"), key])
                at = next(c for c in lp if isinstance(c, list) and c[0] == "at")
                px, py = pin_point(float(at[1]), float(at[2]), x, y, rot)
                ang = (float(at[3]) if len(at) > 3 else 0) + rot
                ang = 90 if round(ang) % 180 == 90 else 0
                just = None
                eff = next((c for c in lp if isinstance(c, list) and c[0] == "effects"), None)
                j = next((c for c in eff if isinstance(c, list) and c[0] == "justify"), None) if eff else None
                if j and rot == 0:
                    just = " ".join(str(t) for t in j[1:])
                inst.append(_prop(key, val, px, py, angle=ang, justify=just))
        inst.append(_prop("Footprint", fp or "", x, y, hide=True))
        inst.append(_prop("Datasheet", "", x, y, hide=True))
        inst.append(_prop("Description", fields.pop("Description", "") if fields else "", x, y, hide=True))
        for k, v in (fields or {}).items():
            inst.append(_prop(k, v, x, y, hide=True))
        for pp in pins(sd, unit):
            inst.append([Sym("pin"), pp["number"], [Sym("uuid"), uid(self.project, ref, unit, "pin", pp["number"])]])
        inst.append([Sym("instances"), [Sym("project"), self.project,
                                        [Sym("path"), f"/{self.root}", [Sym("reference"), ref], [Sym("unit"), unit]]]])
        return inst

    def write(self, path, date="2026-10-18", rev="A"):
        doc = [Sym("kicad_sch"), [Sym("version"), 20250610], [Sym("generator"), "eeschema"],
               [Sym("generator_version"), "10.0"], [Sym("uuid"), self.root], [Sym("paper"), self.paper],
               [Sym("title_block"), [Sym("title"), self.title], [Sym("date"), date], [Sym("rev"), rev],
                [Sym("company"), "SENTINEL-UHF reference design"],
                [Sym("comment"), 1, "Generated by gen_schematic.py - first-pass design, not released for fabrication"]]]
        doc.append([Sym("lib_symbols")] + [self.symdefs[k] for k in sorted(self.symdefs)])
        for x, y in self.junctions:
            doc.append([Sym("junction"), [Sym("at"), x, y], [Sym("diameter"), 0],
                        [Sym("color"), 0, 0, 0, 0], [Sym("uuid"), uid(self.project, "j", x, y)]])
        for x, y in self.nocons:
            doc.append([Sym("no_connect"), [Sym("at"), x, y], [Sym("uuid"), uid(self.project, "nc", x, y)]])
        for i, (a, b) in enumerate(self.wires):
            doc.append([Sym("wire"), [Sym("pts"), [Sym("xy"), *a], [Sym("xy"), *b]],
                        [Sym("stroke"), [Sym("width"), 0], [Sym("type"), Sym("default")]],
                        [Sym("uuid"), uid(self.project, "w", i, a, b)]])
        for i, (x1, y1, x2, y2) in enumerate(self.rects):
            doc.append([Sym("rectangle"), [Sym("start"), x1, y1], [Sym("end"), x2, y2],
                        [Sym("stroke"), [Sym("width"), 0.254], [Sym("type"), Sym("dash")]],
                        [Sym("fill"), [Sym("type"), Sym("none")]], [Sym("uuid"), uid(self.project, "r", i)]])
        for i, (s, x, y, size, bold) in enumerate(self.texts):
            doc.append([Sym("text"), s, [Sym("exclude_from_sim"), Sym("no")], [Sym("at"), x, y, 0],
                        [Sym("effects"), _font(size, bold), [Sym("justify"), Sym("left"), Sym("bottom")]],
                        [Sym("uuid"), uid(self.project, "t", i)]])
        for i, (net, (x, y), ang) in enumerate(self.labels):
            just = "left bottom" if ang in (0, 90) else "right bottom"
            doc.append([Sym("label"), net, [Sym("at"), x, y, ang], [Sym("fields_autoplaced"), Sym("yes")],
                        [Sym("effects"), _font(1.27), [Sym("justify")] + [Sym(j) for j in just.split()]],
                        [Sym("uuid"), uid(self.project, "l", i, net)]])
        for p in self.parts:
            doc.append(self._symbol_instance(p.ref, p.lib_id, p.value, p.fp, p.x, p.y, p.rot, p.unit,
                                             dict(p.fields)))
        for ref, lib_id, value, (x, y), rot in self.power:
            doc.append(self._symbol_instance(ref, lib_id, value, "", x, y, rot, 1, {}, hide_ref=True))
        doc.append([Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]])
        doc.append([Sym("embedded_fonts"), Sym("no")])
        path.write_text(dumps(doc) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ RF chain placer
class Chain:
    """Lays parts out along a horizontal signal line and wires every node."""

    def __init__(self, sch, x0, y, gap=5.08):
        self.sch, self.x, self.y, self.gap = sch, x0, y, gap
        self.node_pins = []          # (part, pin) on the current node
        self.node_pts = []           # attach points along the line (x)
        self.prev_xy = None
        self.node_name = None
        self.count = 0
        self.ops = []
        sch.chains.append(self.ops)

    def _place_at_pin(self, spec, pin, target):
        p = self.sch.add(**spec)
        px, py = p.pin_xy(pin, at=(0, 0))
        p.x, p.y = round(target[0] - px, 4), round(target[1] - py, 4)
        return p

    def name(self, net):
        self.node_name = net
        return self

    def start_label(self, net):
        self.sch.labels.append((net, (self.x, self.y), 180))
        self.ops.append(("start_label", net))
        self.prev_xy = (self.x, self.y)
        self.node_name = net
        return self

    def start(self, spec, out_pin):
        p = self._place_at_pin(spec, out_pin, (self.x, self.y))
        p.wired.add(out_pin)
        self.ops.append(("start", p.ref, out_pin))
        self.node_pins = [(p, out_pin)]
        self.prev_xy = (self.x, self.y)
        return self

    def _close_node(self, next_xy):
        """Wire previous output through shunt attach points to next input."""
        pts = [self.prev_xy] + [(x, self.y) for x in self.node_pts] + [next_xy]
        for a, b in zip(pts, pts[1:]):
            self.sch.wire(a, b)
        for x in self.node_pts:
            self.sch.junction((x, self.y))
        self.count += 1
        net = self.node_name or f"__chain_{id(self)}_{self.count}"
        for part, pin in self.node_pins:
            self.sch.expected[net].add((part.ref, pin))
            if not net.startswith("__"):
                part.nets[pin] = net
        self.node_pins, self.node_pts, self.node_name = [], [], None

    def _next_attach_x(self):
        base = self.node_pts[-1] if self.node_pts else self.prev_xy[0]
        return round(base + self.gap, 4)

    def series(self, spec, pin_in, pin_out):
        tx = self._next_attach_x()
        p = self._place_at_pin(spec, pin_in, (tx, self.y))
        p.wired.update({pin_in, pin_out})
        self.ops.append(("series", p.ref, pin_in, pin_out))
        self.node_pins.append((p, pin_in))
        self._close_node((tx, self.y))
        self.prev_xy = p.pin_xy(pin_out)
        assert abs(self.prev_xy[1] - self.y) < 1e-6, f"{p.ref}: output pin off the line"
        self.node_pins = [(p, pin_out)]
        return self

    def end(self, spec, pin_in):
        tx = self._next_attach_x()
        p = self._place_at_pin(spec, pin_in, (tx, self.y))
        p.wired.add(pin_in)
        self.ops.append(("end", p.ref, pin_in))
        self.node_pins.append((p, pin_in))
        self._close_node((tx, self.y))
        return self

    def end_label(self, net):
        tx = self._next_attach_x()
        self.node_name = self.node_name or net
        self.sch.labels.append((net, (tx, self.y), 0))
        self.ops.append(("end_label", net))
        self._close_node((tx, self.y))
        return self

    def tap(self, net):
        """Name the current node and expose it with a label above the line."""
        x = self._next_attach_x()
        self.node_pts.append(x)
        self.node_name = net
        self.sch.wire((x, self.y), (x, self.y - 2 * GRID))
        self.sch.labels.append((net, (x, self.y - 2 * GRID), 90))
        self.ops.append(("tap", net))
        return self

    def shunt(self, specs, terminal, up=False):
        """Vertical stack of 2-pin parts hanging from the node.

        terminal: power net name, 'NET:<label>' or None (stack ends on the last part's
        free pin which must then carry a net in its spec).
        """
        x = self._next_attach_x()
        self.node_pts.append(x)
        sign = -1 if up else 1
        attach = (x, self.y + sign * GRID)
        self.sch.wire((x, self.y), attach)
        prev = None
        stack = []
        self.ops.append(("shunt", stack, up, terminal))
        for i, spec in enumerate(specs):
            spec = dict(spec)
            spec.setdefault("rot", 0)
            p = self.sch.add(**spec)
            ends = sorted(p.pins, key=lambda n: p.pin_xy(n, at=(0, 0))[1])
            near, far = (ends[-1], ends[0]) if up else (ends[0], ends[-1])
            px, py = p.pin_xy(near, at=(0, 0))
            p.x, p.y = round(attach[0] - px, 4), round(attach[1] - py, 4)
            p.wired.add(near)
            stack.append((p.ref, near, far))
            if i == 0:
                self.node_pins.append((p, near))
            else:
                self.sch.expected[f"__stack_{prev.ref}_{p.ref}"].update({(prev.ref, prev_far), (p.ref, near)})
            prev, prev_far = p, far
            fx, fy = p.pin_xy(far)
            if i < len(specs) - 1:
                attach = (fx, fy + sign * GRID)
                self.sch.wire((fx, fy), attach)
                p.wired.add(far)
        if terminal:
            prev.nets[prev_far] = terminal
        return self


# ------------------------------------------------------------------ project output
def write_project(sch, here, custom, title):
    """Write symbol lib, schematic, intent files and KiCad project tables for one board."""
    import json
    from pathlib import Path
    here = Path(here)
    sch.resolve()
    lib = [Sym("kicad_symbol_lib"), [Sym("version"), 20251024], [Sym("generator"), "schgen"],
           [Sym("generator_version"), "10.0"]] + list(custom)
    (here / "SENTINEL.kicad_sym").write_text(dumps(lib) + "\n", encoding="utf-8")
    sch.write(here / f"{sch.project}.kicad_sch")
    (here / "expected_nets.json").write_text(json.dumps({k: sorted(v) for k, v in sch.expected.items()}, indent=1))
    (here / "chains.json").write_text(json.dumps(sch.chains, indent=1))
    parts = sorted({(p.ref, p.value, p.fp, p.fields.get("Description", ""), p.fields.get("MPN", ""))
                    for p in sch.parts})
    (here / "parts.json").write_text(json.dumps(parts, indent=0))
    (here / "sym-lib-table").write_text(
        '(sym_lib_table\n\t(version 7)\n\t(lib (name "SENTINEL")(type "KiCad")(uri "${KIPRJMOD}/SENTINEL.kicad_sym")'
        '(options "")(descr "SENTINEL custom symbols"))\n)\n')
    (here / "fp-lib-table").write_text(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "SENTINEL")(type "KiCad")(uri "${KIPRJMOD}/SENTINEL.pretty")'
        '(options "")(descr "SENTINEL custom footprints"))\n)\n')
    pro = {"meta": {"filename": f"{sch.project}.kicad_pro", "version": 3},
           "board": {"design_settings": {"defaults": {}, "rules": {
               "min_clearance": 0.2, "min_track_width": 0.2, "min_via_diameter": 0.6,
               "min_through_hole_diameter": 0.3, "min_copper_edge_clearance": 0.3}}},
           "sheets": [], "text_variables": {}}
    (here / f"{sch.project}.kicad_pro").write_text(json.dumps(pro, indent=2))
    print(f"{sch.project}: parts {len(sch.parts)}  nets {len(sch.expected)}  labels {len(sch.labels)}")
