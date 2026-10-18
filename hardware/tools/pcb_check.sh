#!/usr/bin/env bash
# pcb_check.sh <project dir> <name>: build board from plan.json, DRC with zone refill, 3D render, gerbers.
set -e
D="$(cd "$1" && pwd)"; N="$2"; T="$(cd "$(dirname "$0")" && pwd)"
K="/c/Program Files/KiCad/10.0/bin"
cd "$D"
"$K/python.exe" "$T/kicad_build.py" "$D" "$N" | tail -1
"$K/kicad-cli.exe" pcb drc --severity-error --schematic-parity --refill-zones --save-board --format json -o drc.json "$N.kicad_pcb" >/dev/null || true
python -c "
import json, collections
d = json.load(open('drc.json'))
v = [x for x in d.get('violations', []) if x.get('severity') == 'error']
print('DRC errors:', len(v), collections.Counter(x['type'] for x in v).most_common(8))
print('unconnected:', len(d.get('unconnected_items', [])), ' parity:', len(d.get('schematic_parity', [])))"
mkdir -p export/gerbers
"$K/kicad-cli.exe" pcb render --side top --quality high --width 1600 --height 1000 --background opaque -o export/pcb_3d.png "$N.kicad_pcb" >/dev/null 2>&1 \
  && python -c "from PIL import Image; Image.open('export/pcb_3d.png').convert('RGB').save('export/pcb_3d.jpg', quality=85)" || echo "3D render failed"
"$K/kicad-cli.exe" pcb export gerbers -o export/gerbers/ "$N.kicad_pcb" >/dev/null
"$K/kicad-cli.exe" pcb export drill -o export/gerbers/ "$N.kicad_pcb" >/dev/null
echo "gerbers: $(ls export/gerbers | wc -l) files"
