"""
SENTINEL-UHF array element: design sweep and EM verification with mom.py.

Element: crossed tubular dipoles over the array face ground plane, one
dipole per polarisation, combined in a 90-degree hybrid for RHCP.
Lattice: equilateral triangle, a = 0.41 m (from radar_sizing.py).

Outputs go to ./results: PNG plots and results.json (used by the report).
"""
import json
import math
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import minimize

import mom

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)

F0, F_BAND = 435e6, (420e6, 435e6, 450e6)
LATTICE = 0.41
RADIUS = 0.006            # 12 mm OD aluminium tube
DZ = 0.020                # vertical offset between the two crossed dipoles
N_SEG = 16
RINGS = 4                 # hexagonal patch of 1 + 3R(R+1) = 61 elements

plt.rcParams.update({"figure.dpi": 130, "font.size": 9, "axes.grid": True,
                     "grid.alpha": 0.3, "axes.spines.top": False, "axes.spines.right": False})
INK, C1, C2, C3 = "#1b2333", "#2f5bd3", "#d0642a", "#2a9d6f"


def hex_lattice(rings, a=LATTICE):
    pts = []
    for q in range(-rings, rings + 1):
        for r in range(max(-rings, -q - rings), min(rings, -q + rings) + 1):
            pts.append((a * (q + r / 2), a * r * math.sqrt(3) / 2))
    pts.sort(key=lambda p: (round(p[1], 6), p[0]))
    return np.array(pts)


def element_wires(x, y, arm, h):
    """x-dipole on top at height h, y-dipole DZ below it."""
    return [mom.Wire([x - arm, y, h], [x + arm, y, h], N_SEG, RADIUS),
            mom.Wire([x, y - arm, h - DZ], [x, y + arm, h - DZ], N_SEG, RADIUS)]


def build_array(xy, arm, h):
    wires = []
    for x, y in xy:
        wires += element_wires(x, y, arm, h)
    return mom.Structure(wires, ground=True).build()


def port_Z(st, f):
    Z = mom.impedance_matrix(st, f)
    Y, _ = mom.port_admittance(Z, st)
    return np.linalg.inv(Y), Z


def active_gamma(Zp, xy, f, theta, phi, pol, z_ref, centre):
    """Active reflection at the centre element's pol port for a phased scan."""
    k = 2 * np.pi * f / mom.C0
    n = len(xy)
    I = np.eye(Zp.shape[0])
    S = (Zp - np.conj(z_ref) * I) @ np.linalg.inv(Zp + z_ref * I)
    ports = np.arange(n) * 2 + pol
    out = []
    for th in theta:
        u, v = np.sin(th) * np.cos(phi), np.sin(th) * np.sin(phi)
        a = np.exp(-1j * k * (xy[:, 0] * u + xy[:, 1] * v))
        out.append((S[ports[centre], ports] * a).sum() / a[centre])
    return np.array(out)


def main():
    t0 = time.time()
    res = {"lattice_m": LATTICE, "tube_od_mm": 2e3 * RADIUS, "segments_per_dipole": N_SEG}

    # --- 1. isolated element over ground: choose arm length and height --------
    sweep = []
    freqs = np.linspace(400e6, 470e6, 15)
    for arm in (0.140, 0.150, 0.160):
        for h in (0.140, 0.160, 0.180):
            st = mom.Structure(element_wires(0, 0, arm, h), ground=True).build()
            z = np.array([np.linalg.inv(mom.port_admittance(mom.impedance_matrix(st, f), st)[0])[0, 0]
                          for f in freqs])
            sweep.append({"arm": arm, "h": h, "Z": z})
    iso = {(s["arm"], s["h"]): s for s in sweep}

    # --- 2. finite array: scan impedance for each candidate ------------------
    xy = hex_lattice(RINGS)
    centre = int(np.argmin(np.hypot(*xy.T)))
    theta = np.radians(np.arange(0, 61, 2))
    planes = {"E-plane": 0.0, "D-plane": np.pi / 4, "H-plane": np.pi / 2}
    candidates = []
    for arm in (0.140, 0.150, 0.160):
        for h in (0.140, 0.160, 0.180):
            st = build_array(xy, arm, h)
            per_f = {}
            for f in F_BAND:
                Zp, _ = port_Z(st, f)
                per_f[f] = Zp
            # Matching network target per polarisation: the source impedance that
            # minimises the worst active |Gamma| over band and +/-60 deg scan
            # (a broadside conjugate match gives away the wide-angle performance).
            z_refs, curves, worst = [], {}, 0.0
            for pol in (0, 1):
                def cost(p, pol=pol):
                    zr = p[0] + 1j * p[1]
                    return max(np.abs(active_gamma(Zp, xy, f, theta[::3], phi, pol, zr, centre)).max()
                               for f, Zp in per_f.items() for phi in planes.values())
                zr0 = np.conj(per_f[F0][2 * centre + pol, 2 * centre + pol])
                opt = minimize(cost, [zr0.real, zr0.imag], method="Nelder-Mead",
                               options={"xatol": 0.5, "fatol": 1e-3, "maxiter": 150})
                zr = opt.x[0] + 1j * opt.x[1]
                z_refs.append(zr)
                for f, Zp in per_f.items():
                    for pname, phi in planes.items():
                        g = active_gamma(Zp, xy, f, theta, phi, pol, zr, centre)
                        curves[(f, pname, pol)] = g
                        worst = max(worst, np.abs(g).max())
            candidates.append({"arm": arm, "h": h, "z_ref": z_refs, "worst": worst,
                               "curves": curves, "st": st, "Zp": per_f})
            print(f"arm {arm:.3f} h {h:.3f}  Zref x {z_refs[0]:.1f} y {z_refs[1]:.1f}"
                  f"  worst |G| {worst:.3f}  ({time.time() - t0:.0f}s)", flush=True)

    best = min(candidates, key=lambda c: c["worst"])
    arm, h = best["arm"], best["h"]
    z_ref_xy = best["z_ref"]
    z_ref = z_ref_xy[0]
    res.update({"arm_m": arm, "dipole_length_m": 2 * arm, "height_m": h,
                "z_ref": [z_ref.real, z_ref.imag],
                "z_ref_y": [z_ref_xy[1].real, z_ref_xy[1].imag], "array_elements": len(xy),
                "candidates": [{"arm": c["arm"], "h": c["h"], "worst_gamma": c["worst"]}
                               for c in candidates]})

    # --- 3. embedded element pattern and CP performance ----------------------
    st = best["st"]
    th = np.radians(np.linspace(0, 90, 91))
    ph = np.radians(np.linspace(0, 360, 145)[:-1])
    Zfull = mom.impedance_matrix(st, F0)
    Zl = Zfull.copy()
    zr_port = np.tile(z_ref_xy, len(xy))               # x, y, x, y, ... matches st.ports order
    Zl[st.ports, st.ports] += zr_port                  # every port terminated / sourced with its z_ref
    px, py = st.ports[2 * centre], st.ports[2 * centre + 1]

    def pattern(vx, vy):
        V = np.zeros(st.n_basis, complex)
        V[px], V[py] = vx, vy
        I = np.linalg.solve(Zl, V)
        Et, Ep = mom.far_field(st, I, F0, th, ph)
        U = (np.abs(Et) ** 2 + np.abs(Ep) ** 2) / (2 * mom.ETA0)
        p_avail = abs(vx) ** 2 / (8 * z_ref_xy[0].real) + abs(vy) ** 2 / (8 * z_ref_xy[1].real)
        return Et, Ep, 4 * np.pi * U / p_avail

    Et, Ep, Gx = pattern(1.0, 0.0)
    _, _, Gcp_tot = pattern(1.0, -1j)        # y-dipole lags 90 deg
    EtC, EpC, _ = pattern(1.0, -1j)
    # circular components (IEEE: RHCP = (Et - jEp)/sqrt2 for exp(+jwt))
    Er = (EtC - 1j * EpC) / np.sqrt(2)
    El = (EtC + 1j * EpC) / np.sqrt(2)
    ar = (np.abs(Er) + np.abs(El)) / np.maximum(np.abs(np.abs(Er) - np.abs(El)), 1e-12)
    co = "R" if np.abs(Er[0, 0]) > np.abs(El[0, 0]) else "L"
    p_av_cp = 1 / (8 * z_ref_xy[0].real) + 1 / (8 * z_ref_xy[1].real)
    G_co = 4 * np.pi * (np.abs(Er if co == "R" else El) ** 2 / (2 * mom.ETA0)) / p_av_cp
    G_x = 4 * np.pi * (np.abs(El if co == "R" else Er) ** 2 / (2 * mom.ETA0)) / p_av_cp
    lam0 = mom.C0 / F0
    cell = math.sqrt(3) / 2 * LATTICE ** 2
    g_ideal = 4 * np.pi * cell / lam0 ** 2
    res["embedded"] = {
        "realized_gain_broadside_dBi": float(10 * np.log10(Gx[0, 0])),
        "ideal_cell_gain_dBi": float(10 * np.log10(g_ideal)),
        "cp_sense": co + "HCP",
        "cp_gain_broadside_dBic": float(10 * np.log10(G_co[0, 0])),
        "axial_ratio_broadside_dB": float(20 * np.log10(ar[0, 0])),
        "axial_ratio_60deg_worst_dB": float(20 * np.log10(ar[60].max())),
    }

    # coupling between centre x-port and neighbours at f0
    R = np.diag(zr_port)
    F = np.diag(1 / (2 * np.sqrt(zr_port.real)))
    S0 = F @ (best["Zp"][F0] - R.conj()) @ np.linalg.inv(best["Zp"][F0] + R) @ np.linalg.inv(F)
    dist = np.hypot(*(xy - xy[centre]).T)
    nb = [j for j in np.argsort(dist)[1:7]]
    res["coupling"] = {
        "nearest_E_plane_dB": float(20 * np.log10(abs(S0[2 * centre, 2 * nb[0]]))),
        "max_neighbour_copol_dB": float(max(20 * np.log10(abs(S0[2 * centre, 2 * j])) for j in nb)),
        "self_crosspol_dB": float(20 * np.log10(abs(S0[2 * centre, 2 * centre + 1]))),
    }

    # --- 4. plots ------------------------------------------------------------
    # 4a isolated element impedance
    fig, ax = plt.subplots(1, 2, figsize=(8, 3))
    s = iso[(arm, h)]
    ax[0].plot(freqs / 1e6, s["Z"].real, color=C1, label="R")
    ax[0].plot(freqs / 1e6, s["Z"].imag, color=C2, label="X")
    ax[0].axvspan(420, 450, color=C1, alpha=0.07)
    ax[0].set(xlabel="Frequency (MHz)", ylabel="Ohm", title="Isolated element input impedance")
    ax[0].legend(frameon=False)
    for c, (a_, h_) in zip([C1, C2, C3], [(arm, 0.14), (arm, 0.16), (arm, 0.18)]):
        z = iso[(a_, h_)]["Z"]
        g = np.abs((z - np.conj(z_ref)) / (z + z_ref))
        ax[1].plot(freqs / 1e6, 20 * np.log10(g), color=c, label=f"h = {h_ * 100:.0f} cm")
    ax[1].axvspan(420, 450, color=C1, alpha=0.07)
    ax[1].set(xlabel="Frequency (MHz)", ylabel="|S11| (dB)", title=f"Isolated, ref. {z_ref.real:.0f}{z_ref.imag:+.0f}j Ohm")
    ax[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "element_impedance.png")

    # 4b active reflection vs scan
    fig, ax = plt.subplots(1, 3, figsize=(10, 3), sharey=True)
    for i, f in enumerate(F_BAND):
        for (pname, _), c in zip(planes.items(), [C1, C3, C2]):
            for pol, ls in ((0, "-"), (1, ":")):
                g = best["curves"][(f, pname, pol)]
                ax[i].plot(np.degrees(theta), 20 * np.log10(np.abs(g)), color=c, ls=ls,
                           label=f"{pname} ({'x' if pol == 0 else 'y'}-dipole)")
        ax[i].axhline(-10, color=INK, lw=0.8, ls="--")
        ax[i].set(title=f"{f / 1e6:.0f} MHz", xlabel="Scan angle (deg)")
    ax[0].set_ylabel("Active |Γ| (dB)")
    ax[0].legend(frameon=False)
    fig.suptitle("Active reflection coefficient, centre element of 61-element patch (x-pol port)")
    fig.tight_layout()
    fig.savefig(OUT / "active_reflection.png")

    # 4c embedded element pattern cuts
    fig, ax = plt.subplots(1, 2, figsize=(8, 3))
    thd = np.degrees(th)
    for pidx, lbl, c in [(0, "E-plane", C1), (36, "H-plane", C2)]:
        ax[0].plot(thd, 10 * np.log10(Gx[:, pidx] + 1e-9), color=c, label=lbl)
    ax[0].plot(thd, 10 * np.log10(g_ideal * np.cos(th) + 1e-9), color=INK, ls="--", lw=0.8, label="4πA cosθ/λ²")
    ax[0].set(ylim=(-10, 10), xlabel="θ (deg)", ylabel="Realized gain (dBi)", title="Embedded element pattern, 435 MHz")
    ax[0].legend(frameon=False)
    ax[1].plot(thd, 20 * np.log10(ar[:, 0]), color=C1, label="φ = 0°")
    ax[1].plot(thd, 20 * np.log10(ar[:, 36]), color=C2, label="φ = 90°")
    ax[1].set(ylim=(0, 12), xlabel="θ (deg)", ylabel="Axial ratio (dB)", title=f"{co}HCP via 90° hybrid")
    ax[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / "embedded_pattern.png")

    # save curves for the report
    res["curves"] = {
        "theta_deg": np.degrees(theta).tolist(),
        "active": {f"{int(f / 1e6)}": {p: (20 * np.log10(np.abs(best["curves"][(f, p, 0)]))).round(2).tolist()
                                         for p in planes} for f in F_BAND},
        "eep_theta": thd.tolist(),
        "eep_E": (10 * np.log10(Gx[:, 0] + 1e-9)).round(2).tolist(),
        "eep_H": (10 * np.log10(Gx[:, 36] + 1e-9)).round(2).tolist(),
        "ar_0": (20 * np.log10(ar[:, 0])).round(2).tolist(),
    }
    res["worst_active_gamma_dB"] = float(20 * np.log10(best["worst"]))
    res["runtime_s"] = round(time.time() - t0, 1)
    (OUT / "results.json").write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "curves"}, indent=1))


if __name__ == "__main__":
    main()
