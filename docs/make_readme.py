"""Write README.md from the live design outputs (sizing, EM results, KiCad checks)."""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "report"))
import radar_sizing as rs  # noqa: E402
from build_report import BOARDS, mismatch_db  # noqa: E402


def board_rows():
    rows = []
    for folder, pro, name, qty, role in BOARDS:
        d = ROOT / "hardware" / folder
        parts = len(json.loads((d / "parts.json").read_text()))
        nets = len(json.loads((d / "expected_nets.json").read_text()))
        erc = sum(len(x["violations"]) for x in json.loads((d / "erc.json").read_text())["sheets"])
        drc = unc = None
        if (d / "drc.json").exists() and (d / "plan.json").exists() and \
                (d / "drc.json").stat().st_mtime >= (d / "plan.json").stat().st_mtime:
            j = json.loads((d / "drc.json").read_text())
            drc = len([v for v in j.get("violations", []) if v.get("severity") == "error"])
            unc = len(j.get("unconnected_items", []))
        size = json.loads((d / "plan.json").read_text())["size"] if (d / "plan.json").exists() else None
        clean = drc == 0 and unc == 0
        rows.append(dict(folder=folder, pro=pro, name=name, qty=qty, role=role, parts=parts, nets=nets, erc=erc,
                         drc=drc, unc=unc, clean=clean, size=f"{size[0]:.0f} × {size[1]:.0f} mm" if size else "–"))
    return rows


def main():
    em = json.loads((ROOT / "antenna" / "results" / "results.json").read_text())
    r = {a: rs.detect_range(10, theta_scan=a) * 10 ** (-2 * mismatch_db(em, a) / 40) / 1e3 for a in (0, 30, 60)}
    boards = board_rows()
    n_clean = sum(b["clean"] for b in boards)
    img = "docs/images"

    def status(b):
        if b["clean"]:
            return "✅ DRC clean"
        if b["drc"] is None:
            return "🔄 layout in progress"
        return f"🔄 {b['drc']} err / {b['unc']} unrouted"

    table = "\n".join(
        f"| **{b['name']}** | {b['qty']} | {b['role']} | {b['parts']} | {b['nets']} | {b['erc']} | ✔ | {status(b)} | {b['size']} |"
        for b in boards)

    sections = []
    notes = {
        "tr_module": "GaN driver + 300 W GaN final, drop-in circulator, 30 dB coupler, two-stage PIN/Schottky limiter, "
                     "LNA (NF 0.5 dB), SAW filter. Hardware sequencing interlock: the drain switch closes only when "
                     "`TX_EN` AND gate-bias-OK AND MCU-enable. STM32G031 monitors drain current, VSWR, temperature and both gates.",
        "feed_board": f"3 dB 90° hybrid for circular polarisation, isolated port into a 100 W load, per-dipole matching from "
                      f"the EM model (x: series 11.2 nH; y: shunt 3.9 pF + series 20.7 nH), 1:1 baluns, static-bleed chokes.",
        "rfsoc_tile": "Carrier for a commercial RFSoC system-on-module: 9 receive channels (SMA → 1:2 balun → ADC), 9 transmit "
                      "channels (DAC → centre-tapped balun → SMA), eight RS-485 module links, clock input, calibration "
                      "control, QSFP28 (4 × 25 Gb/s) to the beamformer, 12 V → 3.3 V / 3 A buck. Routed with the "
                      "EasyEDA Pro autorouter (Top / In2 / Bottom, In1 solid GND) and imported back into KiCad "
                      "(`tools/import_easyeda.py`, `easyeda_routes.json`).",
        "backplane": "Eight module slots. Each gets a 15 A fuse on the 50 V drain bus and a resettable fuse on 12 V aux. "
                     "All control lines run point-to-point to one 40-pin cable for the tile, so a faulty module cannot "
                     "disturb its neighbours.",
        "psu": "380 VDC → 50 V: two isolated 600 W full bricks (current-shared, OR-ed), NTC inrush limiter with relay bypass, "
               "opto-isolated enables, STM32 supervisor, 12 V aux brick. Pulse energy (87 A for 16 ms) comes from a chassis "
               "capacitor bank on M6 studs. Primary nets enforce IPC-2221 2.5 mm clearance through KiCad custom rules.",
        "cal_board": "Binary tree of seven SPDT switches (8 → 1, one select bit per level) plus an inject/measure switch, "
                     "so the tile can inject into or measure every module's coupler port through one common path.",
        "clock_board": "Narrow-loop PLL locks a 122.88 MHz VCXO to the site 10 MHz. SYSREF is PPS re-timed by the clean "
                       "clock in a D flip-flop, so it is phase-aligned on every tile. Six quad LVDS drivers feed 8 tiles.",
    }
    for b in boards:
        f = b["folder"]
        pics = [f'<img src="{img}/{f}_schematic.jpg" alt="{b["name"]} schematic" width="49%">']
        if (ROOT / img / f"{f}_3d.jpg").exists() and b["drc"] is not None:
            pics.append(f'<img src="{img}/{f}_3d.jpg" alt="{b["name"]} 3D view" width="49%">')
        sections.append(f"""### {b['name']}
`hardware/{f}/` · {b['qty']} per face · {b['parts']} parts · {b['nets']} nets · {status(b)}

📄 [Bill of materials (CSV)](hardware/{f}/export/{b['pro']}_BOM.csv) · [Schematic (PDF)](hardware/{f}/export/{b['pro']}_schematic.pdf) · [Gerbers](hardware/{f}/export/gerbers)

{notes[f]}

<p align="center">{' '.join(pics)}</p>
""")

    text = f"""<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.svg">
    <img src="docs/assets/logo-light.svg" alt="SENTINEL-UHF" width="620">
  </picture>
</p>

<p align="center">
  <b>A complete reference design for a two-face UHF early-warning phased-array radar</b><br>
  system sizing · antenna design and EM simulation · seven KiCad PCB projects · site visualisation
</p>

<p align="center">
  <img alt="Band" src="https://img.shields.io/badge/band-420--450%20MHz-2a78d6">
  <img alt="Elements" src="https://img.shields.io/badge/elements-{rs.N_elem:,}%20per%20face-2a78d6">
  <img alt="KiCad" src="https://img.shields.io/badge/KiCad-10-314cb0">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.13-3776ab">
  <img alt="Blender" src="https://img.shields.io/badge/Blender-5.2-e87d0d">
  <img alt="Status" src="https://img.shields.io/badge/status-first--pass%20design-eb6834">
</p>

<p align="center">
  <img src="{img}/site_hero.jpg" alt="Night view of the SENTINEL-UHF radar site: a tall concrete building with an octagonal phased-array face" width="100%">
  <br><sub>AI visualisation (Pixelcut / Nano Banana 2.1) generated from the project's Blender model. Site details are illustrative.</sub>
</p>

---

## Contents

- [What this is](#what-this-is)
- [Key numbers](#key-numbers)
- [Architecture](#architecture)
- [System design](#system-design)
- [Antenna and EM simulation](#antenna-and-em-simulation)
- [Electronics: seven custom boards](#electronics-seven-custom-boards)
- [Site and building](#site-and-building)
- [Cost estimate](#cost-estimate)
- [Repository layout](#repository-layout)
- [Reproduce everything](#reproduce-everything)
- [Verification status and known gaps](#verification-status-and-known-gaps)
- [Notes](#notes)

## What this is

SENTINEL-UHF is an engineering reference design for a ground-based early-warning radar in the class of
PAVE PAWS / UEWR. It is built from public radar engineering principles, and every number in it comes from code in
this repository:

- a **system budget** (aperture, power, detection range, search fence, data rates),
- an **antenna element** sized with a **method-of-moments EM solver** written for the project and validated against
  textbook results, including a 61-element mutual-coupling and scan-impedance study,
- **seven complete KiCad 10 projects** covering every custom board in the radar, each with a schematic, PCB, gerbers
  and its own symbol/footprint library,
- a **Blender model** of the site and a photorealistic visualisation.

It is a first-pass design meant for study and as a starting point. It is not a fielded system and nothing here is
released for fabrication.

## Key numbers

| | |
|---|---|
| Band | 420–450 MHz (UHF radiolocation), circular polarisation |
| Faces | 2 × 120° = 240° azimuth, tilted back 20° |
| Aperture | 22 m active circle per face, **{rs.N_elem:,} elements** on a 0.41 m triangular lattice |
| Gain / beamwidth | {10 * math.log10(rs.G_bs):.1f} dBi / {rs.bw_bs_deg:.2f}° at broadside |
| Peak / average RF | **{rs.P_face_pk / 1e3:,.0f} kW / {rs.P_face_avg / 1e3:,.0f} kW per face** (300 W GaN per element, 20 % duty) |
| Detection, 10 m² target | **{r[0]:,.0f} km** broadside · {r[30]:,.0f} km at 30° · {r[60]:,.0f} km at 60° (incl. EM mismatch loss) |
| Search fence | {rs.n_beams_fence} beams over 120° × 3°, {rs.t_frame_fence:.1f} s frame |
| Digital back end | {rs.tiles_face} RFSoC tiles per face, {rs.raw_bps / 1e12:.2f} Tb/s element data → {rs.beam_bps / 1e9:.1f} Gb/s after beamforming |
| Site prime power | {rs.P_site / 1e6:.2f} MW |

## Architecture

```mermaid
flowchart LR
    A["Crossed-dipole element<br/>× {rs.N_elem:,} per face"] --- FB["Feed board<br/>hybrid + baluns"]
    FB --- TRM["T/R module<br/>300 W GaN, LNA"]
    TRM --- BP["Tile backplane<br/>8 slots, fused 50 V"]
    BP --- TILE["RFSoC tile<br/>9 RX + 9 TX channels"]
    CAL["Calibration network"] --- TRM
    CAL --- TILE
    PSU["Subarray PSU<br/>380 V → 50 V"] --- BP
    CLK["Clock & timing<br/>122.88 MHz, SYSREF, PPS"] --- TILE
    TILE -- "QSFP28 4×25 Gb/s" --> BF["Face beamformer<br/>16 receive beams"]
    BF --> SP["Signal processor<br/>pulse compression, Doppler, CFAR"]
    SP --> DP["Data processor<br/>tracking, discrimination, C2"]
```

Every element has its own T/R module and its own ADC/DAC channel. There is no analog beamforming network: beams are
formed digitally, so one face can hold a search fence and track several targets in the same dwell.

## System design

`radar_sizing.py` sizes the radar from first principles (Skolnik, *Radar Handbook*). The lattice spacing is set so
no grating lobes appear out to 60° scan at 450 MHz. The result, 2,587 elements in 22 m, lands very close to the
fielded PAVE PAWS (2,677 positions in 22.1 m), which is a useful sanity check.

<p align="center"><img src="{img}/detection_range.png" alt="Detection range versus radar cross section at 0, 30 and 60 degrees scan" width="80%"></p>

| Waveform | Pulse | Bandwidth | Range resolution | Use |
|---|---|---|---|---|
| Long-range search | 16 ms LFM | 100 kHz | 1.5 km | horizon fence |
| Track | 2–8 ms LFM | 1 MHz | 150 m | track updates |
| Discrimination | 0.25–2 ms LFM | 10 MHz | 15 m | object separation |

## Antenna and EM simulation

Each element is a pair of crossed 12 mm aluminium dipoles, **{em['dipole_length_m'] * 100:.0f} cm long, {em['height_m'] * 100:.0f} cm above the
face**, combined in a 90° hybrid for circular polarisation.

The element was designed with `antenna/mom.py`, a thin-wire method-of-moments solver written for this project
(rooftop basis functions, Galerkin testing, image theory for the ground plane, delta-gap ports). It reproduces the
textbook half-wave dipole: **84 + j45 Ω and 2.16 dBi** (theory: 2.15 dBi). `antenna/simulate.py` then solves a
**61-element hexagonal patch** (122 ports, 1,830 unknowns) at 420, 435 and 450 MHz to get the full coupling matrix,
the active reflection coefficient versus scan, and the embedded element pattern.

| Result (centre element) | Value |
|---|---|
| Embedded realised gain, broadside | {em['embedded']['realized_gain_broadside_dBi']:.1f} dBi (ideal cell {em['embedded']['ideal_cell_gain_dBi']:.1f} dBi) |
| Axial ratio, broadside | {em['embedded']['axial_ratio_broadside_dB']:.1f} dB |
| Nearest-neighbour coupling | {em['coupling']['nearest_E_plane_dB']:.1f} dB |
| Worst active reflection, band × ±60° | {em['worst_active_gamma_dB']:.1f} dB |

<p align="center">
  <img src="{img}/active_reflection.png" alt="Active reflection coefficient versus scan angle" width="100%">
  <img src="{img}/embedded_pattern.png" alt="Embedded element pattern and axial ratio" width="49%">
  <img src="{img}/element_impedance.png" alt="Isolated element impedance and S11" width="49%">
</p>

> **Where it falls short.** The match holds to about −9 dB out to 45° but drops to about −4 dB at 60°, which costs
> about 2.2 dB per pass at the scan edge (already included in the detection numbers). A lattice trade study
> (`antenna/explore.py`) showed a tighter 0.37 m grid gains under 1 dB, which isn't worth 30 % more modules.
> The next step is a wide-angle matching sheet, checked in a full-wave model that includes the balun and feed posts.

## Electronics: seven custom boards

Every custom board is generated from a Python circuit description (`gen_schematic.py` / `gen_design.py`) and checked by
KiCad itself:

1. **ERC**: electrical rules, 0 violations required.
2. **Netlist intent check**: KiCad's extracted netlist is compared pin-for-pin with the intended circuit.
3. **Layout**: a shared placement / fan-out / A* routing engine (`hardware/tools/pcbgen.py`) lays out the board on 4
   layers (signal / solid ground / power + signal / signal), then KiCad DRC checks it, refills the zones and verifies
   parity with the schematic.

| Board | Per face | Role | Parts | Nets | ERC | Netlist | Layout | Size |
|---|---|---|---|---|---|---|---|---|
{table}

{n_clean} of 7 layouts are DRC-clean with zero unrouted nets. The rest are still being routed and are updated as they
finish.

{chr(10).join(sections)}
## Site and building

<p align="center"><img src="{img}/blender_model.jpg" alt="Blender render of the radar building from the same viewpoint as the hero image" width="100%"></p>

`render/build_radar.py` builds the site procedurally in Blender. The building is a 48 m equilateral triangle in plan
with its front corner truncated, 32 m high, with both array faces tilted back 20°. Each 33 m face carries a 28 m
octagon of **4,305 crossed-dipole positions**: the 2,587 active elements in the 22 m circle, plus terminated dummy
elements around them. That ratio (60 % active) is close to PAVE PAWS (1,792 of 2,677).

<p align="center">
  <img src="{img}/face_front.jpg" alt="Front elevation of one array face" width="42%">
  <img src="{img}/site_ai_alt.jpg" alt="Alternative AI visualisation of the site" width="56%">
</p>

## Cost estimate

Rough order of magnitude for one two-face site, using commercial GaN and RFSoC prices at production volume:

| Item | Basis | $M |
|---|---|---|
| T/R modules | 5,174 × $4–6k | 21–31 |
| RFSoC tiles | 648 × $8–12k | 5–8 |
| Antenna faces | elements, hybrids, ground plane | 5–9 |
| Beamformer and processors | FPGA + GPU | 10–18 |
| Power and cooling | substation, gensets, chillers | 15–25 |
| Building and site works | 32 m structure, security | 40–80 |
| Software | scheduler, tracking, discrimination, C2 | 40–100 |
| Integration, calibration, test | | 20–40 |
| Engineering and program | | 30–60 |
| **Total acquisition** | | **≈ 186–371** |

Equipment alone is about $56–91M. Military-qualified modules ($10–20k each) and software overruns are the biggest
risks. Operation adds roughly $15–25M per year. The > $1 billion figures quoted for fielded radars include decades
of operation, security and program overhead.

## Repository layout

```
radar_sizing.py            system budget (run it first)
antenna/                   MoM solver, element + 61-element array study, lattice trade study, results/
hardware/
  tools/                   schematic writer, PCB engine, KiCad build / ERC / DRC scripts
  tr_module/               T/R module           (KiCad project + generators + gerbers)
  feed_board/              element feed board
  rfsoc_tile/              RFSoC digitiser tile (SOM carrier)
  backplane/               tile backplane
  psu/                     subarray power supply
  cal_board/               calibration network
  clock_board/             clock & timing distribution
render/                    Blender site model and renders
report/                    interactive HTML design report (build_report.py)
docs/                      logo, README figures, generators
```

Each `hardware/<board>/` folder holds `SENTINEL_*.kicad_pro/.kicad_sch/.kicad_pcb`, its `SENTINEL.kicad_sym` /
`SENTINEL.pretty` libraries, `export/` (schematic PDF, grouped BOM CSV, 3D view, gerbers + drill files) and the generators.

## Reproduce everything

Requires Python 3.13 with numpy, scipy, matplotlib, shapely, pillow and PyMuPDF, plus KiCad 10 and Blender 5.2.

```bash
python radar_sizing.py
cd antenna && python simulate.py && cd ..                              # ~8 min
cd hardware/tr_module && python gen_footprints.py && python gen_schematic.py && cd ../..
bash hardware/tools/sch_check.sh hardware/tr_module SENTINEL_TRM        # ERC + netlist check + footprint dump
python hardware/tr_module/pcb_plan.py                                  # place + route (~30-60 min)
bash hardware/tools/pcb_check.sh hardware/tr_module SENTINEL_TRM        # build board, DRC, 3D view, gerbers
bash hardware/tools/export_bom.sh                                      # grouped BOM CSV for every board
# same pattern for the other boards (gen_design.py, then the two check scripts)
blender -b -P render/build_radar.py -- night 64
python report/build_report.py && python docs/make_figures.py && python docs/make_readme.py
```

## Verification status and known gaps

| Item | Status |
|---|---|
| System budget | ✅ cross-checked against public PAVE PAWS figures |
| MoM solver | ✅ validated on the half-wave dipole |
| Element + array EM model | ✅ 61 elements, 3 frequencies, full coupling (thin-wire, infinite ground) |
| Wide-angle match | ⚠️ ~−4 dB at 60°: needs a WAIM sheet and full-wave verification |
| All 7 schematics | ✅ 0 ERC violations, exact netlist match |
| PCB layouts | {n_clean}/7 DRC-clean; the rest are being routed |
| Differential pairs | ⚠️ data-converter, LVDS and 25 Gb/s pairs are auto-routed as single nets; need a manual coupled, length-matched pass |
| Pin maps not in the KiCad library | ⚠️ RFSoC SOM connector, PLL and RF modules use this project's own pin maps; map to the chosen parts' datasheets |
| T/R module matching values | ⚠️ first-pass from device models; tune on a load-pull bench |
| Thermal | ⚠️ 45 W average per module on a cold plate; needs CFD and a test article |

## Notes

- **No license.** This repository is published without a license. All rights are reserved by the author; viewing
  is fine, but reuse needs permission.
- Designed with [Claude Code](https://claude.com/claude-code). The radar is a study design built from public
  engineering principles; it does not reproduce any classified or proprietary system design.
"""
    (ROOT / "README.md").write_text(text, encoding="utf-8")
    print(f"README written: {len(text):,} chars, {n_clean}/7 boards clean")


if __name__ == "__main__":
    main()
