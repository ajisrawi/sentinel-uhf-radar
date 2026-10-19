#!/usr/bin/env bash
# export_bom.sh: grouped bill of materials (CSV) for every SENTINEL board, straight from KiCad.
# Identical parts (same value, footprint and MPN) share one line with a quantity.
set -e
K="/c/Program Files/KiCad/10.0/bin/kicad-cli.exe"
cd "$(dirname "$0")/.."
for d in tr_module feed_board rfsoc_tile backplane psu cal_board clock_board; do
    sch=$(ls "$d"/SENTINEL_*.kicad_sch)
    pro=$(basename "$sch" .kicad_sch)
    mkdir -p "$d/export"
    "$K" sch export bom \
        --fields 'ITEM_NUMBER,Reference,${QUANTITY},Value,Footprint,Description,MPN' \
        --labels 'Item,References,Qty,Value,Footprint,Description,MPN / part class' \
        --group-by 'Value,Footprint,MPN' --sort-field Reference \
        -o "$d/export/${pro}_BOM.csv" "$sch" > /dev/null
    echo "$d: $(($(wc -l < "$d/export/${pro}_BOM.csv") - 1)) lines"
done
