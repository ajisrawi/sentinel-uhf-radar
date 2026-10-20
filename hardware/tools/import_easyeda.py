"""Run with KiCad's Python: replace a board's tracks and vias with routes exported from EasyEDA Pro.

usage: import_easyeda.py <board.kicad_pcb> <easyeda_routes.json>
EasyEDA coordinates are mils with Y pointing up; KiCad is mm with Y pointing down, same origin.
"""
import json
import sys

import pcbnew

MIL = 0.0254
LAYER = {1: pcbnew.F_Cu, 2: pcbnew.B_Cu, 15: pcbnew.In1_Cu, 16: pcbnew.In2_Cu}

path, routes = sys.argv[1], json.load(open(sys.argv[2]))
b = pcbnew.LoadBoard(path)
for t in list(b.GetTracks()):
    b.Delete(t)


def pt(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x * MIL), pcbnew.FromMM(-y * MIL))


missing = set()


def net(name):
    n = b.FindNet(name)
    if n is None:
        missing.add(name)
    return n


for layer, x0, y0, x1, y1, w, name in routes["lines"]:
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pt(x0, y0))
    t.SetEnd(pt(x1, y1))
    t.SetWidth(pcbnew.FromMM(w * MIL))
    t.SetLayer(LAYER[layer])
    n = net(name)
    if n:
        t.SetNet(n)
    b.Add(t)
for x, y, d, h, name in routes["vias"]:
    v = pcbnew.PCB_VIA(b)
    v.SetPosition(pt(x, y))
    v.SetWidth(pcbnew.FromMM(round(d * MIL, 2)))  # EasyEDA stores 0.6 mm as 23.6 mil (0.599 mm)
    v.SetDrill(pcbnew.FromMM(round(h * MIL, 2)))
    n = net(name)
    if n:
        v.SetNet(n)
    b.Add(v)
pcbnew.SaveBoard(path, b)
print("tracks", len(routes["lines"]), "vias", len(routes["vias"]), "missing nets", sorted(missing))
