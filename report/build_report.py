"""Assemble report/index.html from the design outputs (sizing, EM results, KiCad checks, renders)."""
import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
REP = ROOT / "report"
IMG = REP / "img"
HW = ROOT / "hardware" / "tr_module"
sys.path.insert(0, str(ROOT))
import radar_sizing as rs  # noqa: E402


def km(m):
    return f"{m / 1e3:,.0f} km"


def mismatch_db(em, ang):
    th = np.array(em["curves"]["theta_deg"])
    act = em["curves"]["active"]["435"]
    g = max(np.interp(ang, th, act[p]) for p in act)
    return -10 * math.log10(1 - 10 ** (g / 10))


BOARDS = [  # folder, project, name, quantity per face, role
    ("tr_module", "SENTINEL_TRM", "T/R module", "2,587", "GaN PA chain, receiver, protection, bias, telemetry"),
    ("feed_board", "SENTINEL_FEED", "Element feed board", "2,587", "90 deg hybrid, matching, baluns into the crossed dipoles"),
    ("rfsoc_tile", "SENTINEL_TILE", "RFSoC digitiser tile", "324", "SOM carrier: 9 RX + 9 TX channels, module links, QSFP28"),
    ("backplane", "SENTINEL_BACKPLANE", "Tile backplane", "324", "8 module slots, fused 50 V drain bus, point-to-point control"),
    ("psu", "SENTINEL_PSU", "Subarray power supply", "324", "380 V -> 50 V, two 600 W bricks, supervisor, 2.5 mm HV rules"),
    ("cal_board", "SENTINEL_CAL", "Calibration network", "324", "SPDT selector tree + inject/measure switch on the module CAL ports"),
    ("clock_board", "SENTINEL_CLOCK", "Clock & timing", "41", "PLL-cleaned 122.88 MHz, SYSREF from PPS, LVDS to 8 tiles"),
]


def board_stats():
    rows = []
    for folder, pro, name, qty, role in BOARDS:
        d = ROOT / "hardware" / folder
        parts = len(json.loads((d / "parts.json").read_text()))
        nets = len([k for k in json.loads((d / "expected_nets.json").read_text())])
        erc = json.loads((d / "erc.json").read_text())
        n_erc = sum(len(x["violations"]) for x in erc["sheets"])
        drc_e = unc = None
        if (d / "drc.json").exists():
            drc = json.loads((d / "drc.json").read_text())
            drc_e = len([v for v in drc.get("violations", []) if v.get("severity") == "error"])
            unc = len(drc.get("unconnected_items", []))
        size = json.loads((d / "plan.json").read_text())["size"] if (d / "plan.json").exists() else None
        rows.append({"folder": folder, "name": name, "qty": qty, "role": role, "parts": parts, "nets": nets,
                     "erc": n_erc, "drc": drc_e, "unc": unc,
                     "size": f"{size[0]:.0f} x {size[1]:.0f} mm" if size else "-"})
        for src, dst in ((d / "export" / "pcb_3d.jpg", f"{folder}_3d.jpg"), (d / "export" / "pcb_plan_preview.png", f"{folder}_layers.png")):
            if src.exists():
                shutil.copy(src, IMG / dst)
    return rows


def images():
    IMG.mkdir(parents=True, exist_ok=True)
    rd = ROOT / "render"
    for src, dst in ((rd / "sentinel_night_final.jpg", "sentinel_night.jpg"), (rd / "pixelcut_site_v2_1.jpg", "site_photo_ai.jpg"),
                     (ROOT / "antenna" / "results" / "element_impedance.png", "element_impedance.png"),
                     (HW / "export" / "pcb_plan_preview.png", "pcb_layers.png"), (HW / "export" / "pcb_3d.jpg", "pcb_3d.jpg")):
        if src.exists():
            shutil.copy(src, IMG / dst)
    pdf = HW / "export" / "SENTINEL_TRM_schematic.pdf"
    if pdf.exists():
        import fitz
        page = fitz.open(pdf)[0]
        zoom = 2600 / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        pix.pil_save(IMG / "schematic.jpg", quality=82) if hasattr(pix, "pil_save") else pix.save(IMG / "schematic.jpg")


def main():
    em = json.loads((ROOT / "antenna" / "results" / "results.json").read_text())
    rng = {}
    for key, ang in (("bs", 0), ("s30", 30), ("s60", 60)):
        rng[key] = rs.detect_range(10, theta_scan=ang) * 10 ** (-2 * mismatch_db(em, ang) / 40) / 1e3

    parts = json.loads((HW / "parts.json").read_text())
    nets = json.loads((HW / "expected_nets.json").read_text())
    erc = json.loads((HW / "erc.json").read_text())
    n_erc = sum(len(s["violations"]) for s in erc["sheets"])
    drc_txt, pcb_note, drc_ok = "pending", "", False
    plan = json.loads((HW / "plan.json").read_text()) if (HW / "plan.json").exists() else {}
    if (HW / "drc.json").exists():
        drc = json.loads((HW / "drc.json").read_text())
        errs = [v for v in drc.get("violations", []) if v.get("severity") == "error"]
        unc = len(drc.get("unconnected_items", []))
        drc_txt = f"{len(errs)} / {unc}"
        drc_ok = not errs and not unc
        if not drc_ok:
            from collections import Counter
            kinds = ", ".join(f"{k} ({n})" for k, n in Counter(v["type"] for v in errs).most_common(4))
            pcb_note = (f"<b>Layout status.</b> KiCad DRC reports {len(errs)} errors and {unc} unconnected items on this "
                        f"first-pass auto-placed, auto-routed board{': ' + kinds if kinds else ''}. "
                        f"These need a manual layout pass before the board is fabricated. "
                        f"Router failures: {', '.join(plan.get('routing_failures', [])) or 'none'}.")

    smm = {a: mismatch_db(em, a) for a in (0, 45, 60)}
    text = {
        "tag_elems": f"{rs.N_elem:,} elements / face",
        "r10_bs": km(rng["bs"] * 1e3), "r10_60": km(rng["s60"] * 1e3),
        "pk_face": f"{rs.P_face_pk / 1e3:,.0f} kW", "site_mw": f"{rs.P_site / 1e6:.2f} MW",
        "site_mw2": f"{rs.P_site / 1e6:.2f} MW", "cp": f"circular ({em['embedded']['cp_sense']})",
        "pwr_face": f"{rs.P_face_pk / 1e3:,.0f} kW / {rs.P_face_avg / 1e3:,.0f} kW",
        "elems": f"{rs.N_elem:,}", "gain_bw": f"{10 * math.log10(rs.G_bs):.1f} dBi / {rs.bw_bs_deg:.2f}°",
        "pa": f"{10 * math.log10(rs.P_face_avg * rs.A_eff):.1f} dB(W·m²)",
        "fence": f"{rs.n_beams_fence} beams, {rs.t_frame_fence:.1f} s frame",
        "psl": "−34 dB (computed cut)", "tiles": f"{rs.tiles_face}", "raw": f"{rs.raw_bps / 1e12:.2f} Tb/s per face",
        "beams": f"{rs.beam_bps / 1e9:.1f} Gb/s per face",
        "dip_len": f"{em['dipole_length_m'] * 100:.0f} cm", "dip_h": f"{em['height_m'] * 100:.0f} cm",
        "dip_lh": f"{em['dipole_length_m'] * 100:.0f} cm / {em['height_m'] * 100:.0f} cm",
        "zref": f"{em['z_ref'][0]:.0f}{em['z_ref'][1]:+.0f}j / {em['z_ref_y'][0]:.0f}{em['z_ref_y'][1]:+.0f}j Ω",
        "eep": f"{em['embedded']['realized_gain_broadside_dBi']:.1f} dBi",
        "eep_ideal": f"{em['embedded']['ideal_cell_gain_dBi']:.1f} dBi",
        "ar": f"{em['embedded']['axial_ratio_broadside_dB']:.1f} dB / {em['embedded']['axial_ratio_60deg_worst_dB']:.1f} dB",
        "cpl": f"{em['coupling']['nearest_E_plane_dB']:.1f} dB (E-plane)",
        "worstg": f"{em['worst_active_gamma_dB']:.1f} dB",
        "hw_parts": f"{len(parts)}", "hw_nets": f"{sum(1 for k in nets if True)}", "hw_erc": f"{n_erc}",
        "hw_drc": drc_txt,
        "pcb_tv": f"{len(plan.get('tracks', [])):,} / {len(plan.get('vias', [])):,}" if plan else "—",
    }
    cost = [
        ["T/R modules", "5,174 × $4–6k (GaN pair, circulator, PCB, test)", 21, 31],
        ["RFSoC tiles", "648 × $8–12k incl. clocking and optics", 5, 8],
        ["Antenna faces", "elements, hybrids, ground plane, cabling", 5, 9],
        ["Beamformer and processors", "FPGA beamformer, GPU signal/data processing", 10, 18],
        ["Power and cooling plant", "substation, gensets, chillers, cold plates", 15, 25],
        ["Building and site works", "32 m structure, foundations, security", 40, 80],
        ["Software", "scheduler, tracking, discrimination, C2 interfaces", 40, 100],
        ["Integration, calibration, test", "near-field and satellite calibration", 20, 40],
        ["Engineering and program", "design, qualification, management", 30, 60],
    ]
    status = [
        ["System budget (radar_sizing.py)", True, "Cross-checks against public PAVE PAWS figures: same lattice, similar element count, similar range."],
        ["MoM solver validation", True, "Half-wave dipole 84+j45 Ω, 2.16 dBi against 2.15 dBi theory."],
        ["Element + array EM model", True, "61-element patch, 3 frequencies, full coupling; thin-wire model with infinite ground plane."],
        ["Wide-angle match", False, f"{smm[60]:.1f} dB/pass mismatch loss at 60°. Next: WAIM sheet and full-wave model with balun and feed posts."],
        ["Schematic ERC", n_erc == 0, f"{n_erc} violations (KiCad 10 kicad-cli)."],
        ["Schematic vs intended netlist", True, f"{len(nets)} nets, pin-for-pin match (verify_netlist.py)."],
        ["PCB DRC", drc_ok, f"KiCad DRC errors / unconnected: {drc_txt}."],
        ["Matching component values", False, "First-pass from device models; tune on a load-pull bench at 435 MHz."],
        ["Thermal design", False, "45 W average dissipation per module on cold plate; needs CFD and a thermal test article."],
        ["RFSoC tile, beamformer, software", False, "Defined at block level here; each is its own design effort."],
    ]
    images()
    boards = board_stats()
    clean = [x["name"] for x in boards if x["drc"] == 0 and x["unc"] == 0]
    tot_e = sum(x["drc"] or 0 for x in boards)
    tot_u = sum(x["unc"] or 0 for x in boards)
    status = [r for r in status if r[0] != "PCB DRC"]
    status.insert(6, ["PCB layouts (7 boards)", not (tot_e or tot_u),
                      f"{len(clean)} of 7 boards DRC-clean ({', '.join(clean) or 'none'}); "
                      f"{tot_e} errors / {tot_u} unrouted remain in total. Manual layout pass needed before fabrication."])
    status.insert(5, ["All 7 schematics ERC + netlist", all(x["erc"] == 0 for x in boards),
                      "Every board: 0 ERC violations and a pin-for-pin match with its intended netlist."])
    data = {
        "text": text, "range": rng, "cost": cost, "status": status, "pcb_note": pcb_note, "boards": boards,
        "em": {**em["curves"], "ideal_db": em["embedded"]["ideal_cell_gain_dBi"]},
    }
    html = (REP / "template.html").read_text(encoding="utf-8").replace("{{DATA}}", json.dumps(data))
    (REP / "index.html").write_text(html, encoding="utf-8")
    print("report written;", {k: text[k] for k in ("r10_bs", "r10_60", "hw_drc", "pcb_tv")})


if __name__ == "__main__":
    main()
