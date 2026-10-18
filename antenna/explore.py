"""Quick trade study on a 37-element patch: lattice, tube radius, height, arm length."""
import itertools
import sys
import time

import numpy as np
from scipy.optimize import minimize

import mom
import simulate as S

F_BAND = (420e6, 435e6, 450e6)
theta = np.radians(np.arange(0, 61, 6))
planes = (0.0, np.pi / 4, np.pi / 2)


def evaluate(lattice, radius, h, arm, rings=3):
    S.RADIUS = radius
    xy = S.hex_lattice(rings, a=lattice)
    c = int(np.argmin(np.hypot(*xy.T)))
    st = S.build_array(xy, arm, h)
    Zps = {f: S.port_Z(st, f)[0] for f in F_BAND}

    def worst(zr, pol, lim=60):
        th = theta[np.degrees(theta) <= lim]
        return max(np.abs(S.active_gamma(Zp, xy, f, th, phi, pol, zr, c)).max()
                   for f, Zp in Zps.items() for phi in planes)

    out = []
    for pol in (0, 1):
        z0 = np.conj(Zps[435e6][2 * c + pol, 2 * c + pol])
        opt = minimize(lambda p: worst(p[0] + 1j * p[1], pol), [z0.real, z0.imag], method="Nelder-Mead",
                       options={"xatol": 0.5, "fatol": 1e-3, "maxiter": 120})
        zr = opt.x[0] + 1j * opt.x[1]
        out.append((20 * np.log10(opt.fun), 20 * np.log10(worst(zr, pol, 45)), zr))
    return out


if __name__ == "__main__":
    t0 = time.time()
    grid = itertools.product((0.41, 0.37), (0.006, 0.010), (0.18, 0.21), (0.13, 0.145))
    for lat, rad, h, arm in grid:
        if arm > lat / 2 - 0.04:
            continue
        r = evaluate(lat, rad, h, arm)
        print(f"a={lat:.2f} r={rad * 1e3:.0f}mm h={h:.2f} arm={arm:.3f} | "
              f"x: {r[0][0]:6.1f} dB@60 {r[0][1]:6.1f} dB@45 | y: {r[1][0]:6.1f} @60 {r[1][1]:6.1f} @45"
              f"  ({time.time() - t0:.0f}s)", flush=True)
