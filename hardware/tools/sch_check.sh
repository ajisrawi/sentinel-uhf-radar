#!/usr/bin/env bash
# sch_check.sh <project dir> <name>: ERC, netlist export, intent check, PDF, footprint dump.
set -e
D="$(cd "$1" && pwd)"; N="$2"; T="$(cd "$(dirname "$0")" && pwd)"
K="/c/Program Files/KiCad/10.0/bin"
cd "$D"
"$K/kicad-cli.exe" sch erc --severity-all --format json -o erc.json "$N.kicad_sch" >/dev/null
python -c "
import json; d=json.load(open('erc.json')); v=[x for s in d['sheets'] for x in s['violations']]
print('ERC violations:', len(v), [ (x['type'], x['description'][:60]) for x in v][:6])"
"$K/kicad-cli.exe" sch export netlist --format kicadsexpr -o "$N.net" "$N.kicad_sch" >/dev/null
python "$T/verify_netlist.py" "$D" "$N" | tail -3
mkdir -p export
"$K/kicad-cli.exe" sch export pdf -o "export/${N}_schematic.pdf" "$N.kicad_sch" >/dev/null
"$K/python.exe" "$T/kicad_dump.py" "$D"
