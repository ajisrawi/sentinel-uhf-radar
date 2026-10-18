"""
SENTINEL-UHF early warning radar: first-order system sizing.

Every number in the design report comes from this script. Change a
parameter at the top and re-run to see how the system responds.
Formulas follow Skolnik, "Radar Handbook" 3rd ed., ch. 1-2 and 13.
"""
import math
from pathlib import Path

import numpy as np

k_B = 1.380649e-23   # Boltzmann constant, J/K
c = 299_792_458.0    # speed of light, m/s

# ---------------------------------------------------------------- inputs
f_lo, f_hi = 420e6, 450e6       # ITU radiolocation band used by PAVE PAWS/UEWR
f0 = 435e6                      # design centre frequency
faces = 2                       # two faces, 120 deg each -> 240 deg azimuth
D_face = 22.0                   # active aperture diameter per face, m
scan_max_deg = 60.0             # max electronic scan off boresight
face_tilt_deg = 20.0            # face tilted back from vertical
P_elem_pk = 300.0               # GaN T/R module peak power, W
duty_max = 0.20                 # max transmit duty cycle
pae = 0.55                      # GaN power-added efficiency at UHF
T_sys = 450.0                   # system noise temp (sky + LNA + losses), K
L_sys_dB = 6.0                  # Tx+Rx losses, processing loss, misc
SNR_det_dB = 15.0               # SNR for Pd ~0.9 at Pfa 1e-6, Swerling 1
tau_long = 16e-3                # longest LFM pulse, s
B_search = 100e3                # search waveform bandwidth, Hz
B_track = 10e6                  # wideband track/discrimination waveform, Hz

# ---------------------------------------------------------------- aperture
lam0 = c / f0
lam_min = c / f_hi
# Equilateral triangular lattice, grating-lobe free to scan_max at f_hi:
# a <= (2/sqrt3) * lam / (1 + sin(theta_max))
a_max = (2 / math.sqrt(3)) * lam_min / (1 + math.sin(math.radians(scan_max_deg)))
a = math.floor(a_max * 100) / 100            # round down to cm
cell_area = (math.sqrt(3) / 2) * a ** 2
A_phys = math.pi * (D_face / 2) ** 2


def lattice_xy():
    """Element centres of the triangular lattice clipped to the circular face."""
    xs, ys = [], []
    rows = int(D_face / (a * math.sqrt(3) / 2)) + 2
    cols = int(D_face / a) + 2
    for r in range(-rows // 2, rows // 2 + 1):
        for q in range(-cols // 2, cols // 2 + 1):
            x = q * a + (a / 2 if r % 2 else 0.0)
            y = r * a * math.sqrt(3) / 2
            if x * x + y * y <= (D_face / 2) ** 2:
                xs.append(x)
                ys.append(y)
    return np.array(xs), np.array(ys)


N_elem = len(lattice_xy()[0])
eta_ap = 0.80                                # taper + element efficiency
A_eff = eta_ap * A_phys
G_bs = 4 * math.pi * A_eff / lam0 ** 2       # broadside gain
bw_bs_deg = math.degrees(0.886 * lam0 / D_face) * 1.15   # with ~25 dB Taylor taper


def scan_loss(theta_deg, n=1.5):
    """Two-way gain falls roughly as cos^n per pass for a planar array."""
    return math.cos(math.radians(theta_deg)) ** n


# ---------------------------------------------------------------- power
P_face_pk = N_elem * P_elem_pk
P_face_avg = P_face_pk * duty_max
P_dc_face = P_face_avg / pae
P_prime_face = P_dc_face / 0.90 + 0.35 * P_dc_face / 0.90   # PSU loss + cooling
P_site = faces * P_prime_face + 600e3                       # + computing, HVAC, ops


def detect_range(sigma, tau=tau_long, theta_scan=0.0, n_pulses=1):
    """Max range for a coherent dwell of n_pulses of length tau."""
    G = G_bs * scan_loss(theta_scan, 1.0)          # one-way, cos^1 per pass
    E = P_face_pk * tau * n_pulses
    L = 10 ** (L_sys_dB / 10)
    snr = 10 ** (SNR_det_dB / 10)
    R4 = E * G ** 2 * lam0 ** 2 * sigma / ((4 * math.pi) ** 3 * k_B * T_sys * L * snr)
    return R4 ** 0.25


# ---------------------------------------------------------------- search fence
# Horizon fence: 120 deg az x 3 deg el per face, revisit every T_frame.
fence_az, fence_el = 120.0, 3.0
beam_sr = math.radians(bw_bs_deg) ** 2
fence_sr = math.radians(fence_az) * math.radians(fence_el)
n_beams_fence = math.ceil(fence_sr / (beam_sr * 0.8))   # 0.8 for beam overlap
R_fence = 4800e3
t_listen = 2 * R_fence / c
dwell = tau_long + t_listen                              # one pulse per beam
# Pulses are interleaved: transmit beam N+1 while listening for beam N.
t_frame_fence = n_beams_fence * max(tau_long / duty_max, dwell / 4)

# ---------------------------------------------------------------- resolution
dR_search = c / (2 * B_search)
dR_track = c / (2 * B_track)

# ---------------------------------------------------------------- digital backend
elem_per_tile = 8                          # one RFSoC per 8 elements
tiles_face = math.ceil(N_elem / elem_per_tile)
fs_out = 1.25 * B_track                    # complex baseband rate after DDC
bits = 32                                  # 16-bit I + 16-bit Q
raw_bps = N_elem * fs_out * bits
beams_rx = 16                              # simultaneous receive beams per face
beam_bps = beams_rx * fs_out * bits

# ---------------------------------------------------------------- array factor
def array_factor_cut(theta0_deg, n_pts=2001):
    """Principal-plane array factor of the circular triangular lattice."""
    x, y = lattice_xy()
    rho = np.hypot(x, y) / (D_face / 2)
    w = 0.3 + 0.7 * (1 - rho ** 2) ** 1.5       # tapered amplitude on receive
    k = 2 * math.pi / lam0
    th = np.radians(np.linspace(-90, 90, n_pts))
    ph = -k * x[None, :] * math.sin(math.radians(theta0_deg))
    af = np.abs((w[None, :] * np.exp(1j * (k * x[None, :] * np.sin(th)[:, None] + ph))).sum(1))
    af_db = 20 * np.log10(af / af.max() + 1e-12)
    return np.degrees(th), af_db


if __name__ == "__main__":
    th, af = array_factor_cut(0.0)
    psl = af[np.abs(th) > 3 * bw_bs_deg].max()

    def km(m):
        return f"{m / 1e3:,.0f} km"

    print("=== Aperture ===")
    print(f"wavelength @ f0           {lam0:.3f} m")
    print(f"lattice spacing (max/used) {a_max:.3f} / {a:.2f} m (equilateral)")
    print(f"elements per face          {N_elem}")
    print(f"broadside gain             {10 * math.log10(G_bs):.1f} dBi")
    print(f"3 dB beamwidth             {bw_bs_deg:.2f} deg broadside, "
          f"{bw_bs_deg / math.cos(math.radians(60)):.2f} deg at 60 deg scan")
    print(f"peak sidelobe (computed)   {psl:.1f} dB")
    print("=== Power ===")
    print(f"peak RF per face           {P_face_pk / 1e3:,.0f} kW")
    print(f"avg RF per face            {P_face_avg / 1e3:,.0f} kW")
    print(f"prime power per face       {P_prime_face / 1e3:,.0f} kW")
    print(f"site prime power           {P_site / 1e6:.2f} MW")
    print(f"power-aperture / face      {10 * math.log10(P_face_avg * A_eff):.1f} dB(W*m^2)")
    print("=== Detection (16 ms pulse, SNR 15 dB) ===")
    for sigma, lbl in [(10, "10 m^2 (booster/large sat)"), (1, "1 m^2"),
                       (0.1, "0.1 m^2 (small object)"), (0.01, "0.01 m^2 (RV-class)")]:
        print(f"{lbl:28s} broadside {km(detect_range(sigma)):>9}   "
              f"60 deg {km(detect_range(sigma, theta_scan=60)):>9}   "
              f"8-pulse {km(detect_range(sigma, n_pulses=8)):>9}")
    # element scan mismatch from the MoM array model (antenna/simulate.py)
    em = Path(__file__).parent / "antenna" / "results" / "results.json"
    if em.exists():
        import json
        r = json.loads(em.read_text())
        th = np.array(r["curves"]["theta_deg"])
        act = r["curves"]["active"]["435"]
        print("=== Scan mismatch (EM model, 435 MHz, worst plane) ===")
        for ang in (0, 30, 45, 60):
            g_db = max(np.interp(ang, th, act[p]) for p in act)
            ml = -10 * math.log10(1 - 10 ** (g_db / 10))          # one-way mismatch loss
            r10 = detect_range(10, theta_scan=ang) * 10 ** (-2 * ml / 40)
            print(f"scan {ang:2d} deg  |G| {g_db:6.1f} dB  loss {ml:.2f} dB/pass  "
                  f"10 m^2 range {km(r10):>9}")
    print("=== Search fence ===")
    print(f"beams in 120x3 deg fence   {n_beams_fence}")
    print(f"fence frame time           {t_frame_fence:.1f} s")
    print("=== Resolution ===")
    print(f"range res search / track   {dR_search:.0f} m / {dR_track:.0f} m")
    print("=== Digital backend ===")
    print(f"RFSoC tiles per face       {tiles_face}")
    print(f"raw element data           {raw_bps / 1e12:.2f} Tb/s per face")
    print(f"after DBF ({beams_rx} beams)       {beam_bps / 1e9:.1f} Gb/s per face")
