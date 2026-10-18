"""Generate the SENTINEL-UHF logo (light and dark SVG) and a PNG preview.

Mark: the octagonal array face drawn as a triangular lattice of element dots,
tilted like the real face, with a scanned beam leaving it as three wavefront arcs.
"""
import math
from pathlib import Path

OUT = Path(__file__).parent / "assets"
OUT.mkdir(exist_ok=True)


def mark(fg, accent, dim):
    cx, cy, r = 64, 64, 46
    oct_pts = []
    for i in range(8):
        a = math.radians(22.5 + 45 * i)
        oct_pts.append((cx + r / math.cos(math.radians(22.5)) * math.cos(a), cy + r / math.cos(math.radians(22.5)) * math.sin(a)))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in oct_pts)
    dots = []
    a = 7.2
    for row in range(-8, 9):
        for col in range(-8, 9):
            x = col * a + (a / 2 if row % 2 else 0)
            y = row * a * math.sqrt(3) / 2
            ax, ay = abs(x), abs(y)
            if max(ax, ay, (ax + ay) / math.sqrt(2)) > r - 6:
                continue
            active = x * x + y * y <= (r - 12) ** 2
            dots.append(f'<circle cx="{cx + x:.1f}" cy="{cy + y:.1f}" r="{1.55 if active else 1.1}" '
                        f'fill="{fg if active else dim}"/>')
    # beam: three wavefront arcs leaving the face towards upper right
    arcs = []
    for k, rr in enumerate((62, 76, 90)):
        a0, a1 = math.radians(-58), math.radians(-22)
        x0, y0 = cx + rr * math.cos(a0), cy + rr * math.sin(a0)
        x1, y1 = cx + rr * math.cos(a1), cy + rr * math.sin(a1)
        arcs.append(f'<path d="M{x0:.1f},{y0:.1f} A{rr},{rr} 0 0 1 {x1:.1f},{y1:.1f}" fill="none" '
                    f'stroke="{accent}" stroke-width="{4.2 - k * 1.1:.1f}" stroke-linecap="round" opacity="{1 - k * 0.25:.2f}"/>')
    return (f'<polygon points="{poly}" fill="none" stroke="{fg}" stroke-width="3.2" stroke-linejoin="round"/>'
            + "".join(dots) + "".join(arcs))


def svg(fg, accent, dim, sub):
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 700 160" width="700" height="160" role="img" aria-label="SENTINEL-UHF">
  <g transform="translate(6,26)">{mark(fg, accent, dim)}</g>
  <text x="176" y="100" font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="54" font-weight="700"
        letter-spacing="2" fill="{fg}">SENTINEL<tspan fill="{accent}">-UHF</tspan></text>
  <text x="178" y="132" font-family="'Segoe UI', 'Helvetica Neue', Arial, sans-serif" font-size="16" letter-spacing="3.2"
        fill="{sub}">GROUND-BASED EARLY-WARNING PHASED ARRAY</text>
</svg>
'''


(OUT / "logo-light.svg").write_text(svg("#14213a", "#2a78d6", "#a9b4c6", "#4f5d73"))
(OUT / "logo-dark.svg").write_text(svg("#e8eef7", "#5aa2ff", "#56637a", "#a9b6c9"))
icon = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -30 160 160" width="256" height="256">{mark("#14213a", "#2a78d6", "#a9b4c6")}</svg>\n'
(OUT / "icon.svg").write_text(icon)
print("logos written:", sorted(p.name for p in OUT.iterdir()))
