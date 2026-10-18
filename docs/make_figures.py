"""Collect and render every README image into docs/images (run after the design scripts)."""
import math
import shutil
import sys
from pathlib import Path

import fitz
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
IMG.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "report"))
import radar_sizing as rs  # noqa: E402
from build_report import BOARDS, mismatch_db  # noqa: E402


def jpg(src, dst, width=1600, q=85):
    if not Path(src).exists():
        return False
    im = Image.open(src).convert("RGB")
    if im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    im.save(IMG / dst, quality=q, optimize=True)
    return True


def main():
    rd = ROOT / "render"
    jpg(rd / "pixelcut_site_v2_1.jpg", "site_hero.jpg", 1800)
    jpg(rd / "pixelcut_site_v2_2.jpg", "site_ai_alt.jpg")
    jpg(rd / "sentinel_night_final.jpg", "blender_model.jpg")
    jpg(rd / "face_front.png", "face_front.jpg", 900)
    for name in ("active_reflection.png", "embedded_pattern.png", "element_impedance.png"):
        shutil.copy(ROOT / "antenna" / "results" / name, IMG / name)

    for folder, pro, *_ in BOARDS:
        d = ROOT / "hardware" / folder
        pdf = d / "export" / f"{pro}_schematic.pdf"
        if pdf.exists():
            page = fitz.open(pdf)[0]
            z = 2400 / page.rect.width
            page.get_pixmap(matrix=fitz.Matrix(z, z)).pil_save(IMG / f"{folder}_schematic.jpg", quality=80)
        jpg(d / "export" / "pcb_3d.jpg", f"{folder}_3d.jpg", 1400)
        jpg(d / "export" / "pcb_plan_preview.png", f"{folder}_layers.jpg", 1600)

    # detection range vs RCS, with the EM-model scan mismatch folded in
    import json
    em = json.loads((ROOT / "antenna" / "results" / "results.json").read_text())
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    rcs = np.logspace(-2, 1, 60)
    for ang, col, lab in ((0, "#2a78d6", "broadside"), (30, "#1baf7a", "30° scan"), (60, "#eb6834", "60° scan")):
        r10 = rs.detect_range(10, theta_scan=ang) * 10 ** (-2 * mismatch_db(em, ang) / 40) / 1e3
        ax.plot(rcs, r10 * (rcs / 10) ** 0.25, color=col, lw=2.2, label=lab)
        ax.annotate(f"{r10:,.0f} km", (10, r10), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8, color=col)
    ax.set_xscale("log")
    ax.set_xlim(0.01, 10)
    ax.set_ylim(0, 7000)
    ax.set_xlabel("radar cross section (m²)")
    ax.set_ylabel("detection range (km)")
    ax.set_title("Single 16 ms pulse, one face, SNR 15 dB (Pd 0.9, Pfa 1e-6)", fontsize=10)
    ax.grid(alpha=0.3, which="both")
    ax.legend(frameon=False, loc="upper left")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(IMG / "detection_range.png")
    print("images:", len(list(IMG.iterdir())))


if __name__ == "__main__":
    main()
