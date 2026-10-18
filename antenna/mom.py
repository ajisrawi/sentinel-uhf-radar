"""
Thin-wire Method of Moments (EFIE, mixed potential) for straight wires.

- Triangular (rooftop) basis functions, Galerkin testing.
- Reduced kernel G = exp(-jkR) / (4 pi R), R = sqrt(|r - r'|^2 + a^2).
- Optional infinite PEC ground plane at z = 0 via image theory. Only
  horizontal wires are allowed above ground, so both the vector and
  scalar potential image terms carry a minus sign.
- Delta-gap ports at interior nodes; lumped loads at ports.

Reference: Harrington, "Field Computation by Moment Methods";
Gibson, "The Method of Moments in Electromagnetics", ch. 3-4.
"""
from dataclasses import dataclass, field

import numpy as np

C0 = 299_792_458.0
MU0 = 4e-7 * np.pi
EPS0 = 1.0 / (MU0 * C0 ** 2)
ETA0 = MU0 * C0


@dataclass
class Wire:
    start: np.ndarray
    end: np.ndarray
    n_seg: int
    radius: float
    port: bool = True          # delta-gap port at the centre node


@dataclass
class Structure:
    wires: list
    ground: bool = False

    # filled by build()
    seg_a: np.ndarray = field(init=False)
    seg_b: np.ndarray = field(init=False)
    seg_len: np.ndarray = field(init=False)
    seg_t: np.ndarray = field(init=False)
    seg_rad: np.ndarray = field(init=False)
    basis: np.ndarray = field(init=False)     # (M, 2): segment carrying rising / falling half
    ports: np.ndarray = field(init=False)     # basis index of each port

    def build(self):
        a, b, rad, basis, ports = [], [], [], [], []
        s0 = 0
        for w in self.wires:
            w.start, w.end = np.asarray(w.start, float), np.asarray(w.end, float)
            if self.ground:
                assert abs(w.start[2] - w.end[2]) < 1e-12 and w.start[2] > 0, \
                    "only horizontal wires above the ground plane"
            nodes = w.start + np.linspace(0, 1, w.n_seg + 1)[:, None] * (w.end - w.start)
            a.append(nodes[:-1])
            b.append(nodes[1:])
            rad += [w.radius] * w.n_seg
            m0 = len(basis)
            for i in range(1, w.n_seg):
                basis.append((s0 + i - 1, s0 + i))
            if w.port:
                assert w.n_seg % 2 == 0, "port needs a centre node"
                ports.append(m0 + w.n_seg // 2 - 1)
            s0 += w.n_seg
        self.seg_a, self.seg_b = np.vstack(a), np.vstack(b)
        d = self.seg_b - self.seg_a
        self.seg_len = np.linalg.norm(d, axis=1)
        self.seg_t = d / self.seg_len[:, None]
        self.seg_rad = np.array(rad)
        self.basis = np.array(basis)
        self.ports = np.array(ports, dtype=int)
        return self

    @property
    def n_basis(self):
        return len(self.basis)


def _gauss(q):
    x, w = np.polynomial.legendre.leggauss(q)
    return 0.5 * (x + 1), 0.5 * w            # map to (0, 1)


def _segment_integrals(st, k, obs_idx, src_idx, q):
    """Shape-weighted double integrals of the kernel for segment pairs.

    Returns P (4, len(obs), len(src)) for shape pairs (u,u'),(u,1-u'),(1-u,u'),(1-u,1-u')
    and P0 (len(obs), len(src)) for the charge term; lengths are folded in.
    """
    u, w = _gauss(q)
    ro = st.seg_a[obs_idx, None, :] + u[None, :, None] * (st.seg_b - st.seg_a)[obs_idx, None, :]
    rs = st.seg_a[src_idx, None, :] + u[None, :, None] * (st.seg_b - st.seg_a)[src_idx, None, :]
    a2 = st.seg_rad[src_idx] ** 2

    def kern(src_pts):
        d = ro[:, :, None, None, :] - src_pts[None, None, :, :, :]
        R = np.sqrt((d ** 2).sum(-1) + a2[None, None, :, None])
        return np.exp(-1j * k * R) / (4 * np.pi * R)

    G = kern(rs)
    if st.ground:
        G = G - kern(rs * np.array([1.0, 1.0, -1.0]))

    shapes = (u, 1 - u)
    Lo, Ls = st.seg_len[obs_idx], st.seg_len[src_idx]
    LL = Lo[:, None] * Ls[None, :]
    P = np.empty((4, len(obs_idx), len(src_idx)), complex)
    for i, (fa, fb) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)]):
        P[i] = np.einsum("q,cqsr,r->cs", w * shapes[fa], G, w * shapes[fb], optimize=True) * LL
    P0 = np.einsum("q,cqsr,r->cs", w, G, w, optimize=True) * LL
    return P, P0


def impedance_matrix(st, freq, q_far=4, q_near=10, chunk=96):
    k = 2 * np.pi * freq / C0
    S = len(st.seg_len)
    P = np.empty((4, S, S), complex)
    P0 = np.empty((S, S), complex)
    all_s = np.arange(S)
    for c0 in range(0, S, chunk):
        idx = all_s[c0:c0 + chunk]
        P[:, idx, :], P0[idx, :] = _segment_integrals(st, k, idx, all_s, q_far)

    # refine near-field pairs (self and neighbours) with more quadrature points
    ctr = 0.5 * (st.seg_a + st.seg_b)
    for o in range(S):
        dist = np.linalg.norm(ctr - ctr[o], axis=1)
        near = np.nonzero(dist < 2.5 * st.seg_len.max())[0]
        Pn, P0n = _segment_integrals(st, k, np.array([o]), near, q_near)
        P[:, o, near], P0[o, near] = Pn[:, 0, :], P0n[0, :]

    omega = 2 * np.pi * freq
    B = st.basis
    # role 0: rising half (shape u, div +1/L) on B[:,0]; role 1: falling half (1-u, -1/L) on B[:,1]
    M = st.n_basis
    Z = np.zeros((M, M), complex)
    for ra in (0, 1):
        sa = B[:, ra]
        da = (1.0 if ra == 0 else -1.0) / st.seg_len[sa]
        for rb in (0, 1):
            sb = B[:, rb]
            db = (1.0 if rb == 0 else -1.0) / st.seg_len[sb]
            tt = st.seg_t[sa] @ st.seg_t[sb].T
            Z += 1j * omega * MU0 * tt * P[2 * ra + rb][np.ix_(sa, sb)]
            Z += (da[:, None] * db[None, :]) / (1j * omega * EPS0) * P0[np.ix_(sa, sb)]
    return Z


def port_admittance(Z, st):
    """Short-circuit admittance matrix seen at the delta-gap ports."""
    V = np.zeros((st.n_basis, len(st.ports)), complex)
    V[st.ports, np.arange(len(st.ports))] = 1.0
    I = np.linalg.solve(Z, V)
    return I[st.ports, :], I


def segment_currents(st, I_basis):
    """Current at the two ends of every segment from basis coefficients."""
    S = len(st.seg_len)
    ia, ib = np.zeros(S, complex), np.zeros(S, complex)
    np.add.at(ib, st.basis[:, 0], I_basis)    # rising half ends at segment end
    np.add.at(ia, st.basis[:, 1], I_basis)    # falling half starts at segment start
    return ia, ib


def far_field(st, I_basis, freq, theta, phi, q=4):
    """Return (E_theta, E_phi) far-field patterns (r * E, V) over a theta/phi grid."""
    k = 2 * np.pi * freq / C0
    omega = 2 * np.pi * freq
    ia, ib = segment_currents(st, I_basis)
    u, w = _gauss(q)
    pts = st.seg_a[:, None, :] + u[None, :, None] * (st.seg_b - st.seg_a)[:, None, :]
    cur = (ia[:, None] * (1 - u) + ib[:, None] * u) * w * st.seg_len[:, None]   # (S, q)
    th, ph = np.meshgrid(theta, phi, indexing="ij")
    rhat = np.stack([np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)], -1)

    def radiate(points, sign):
        phase = np.exp(1j * k * np.einsum("...c,sqc->...sq", rhat, points))
        return sign * np.einsum("...sq,sq,sc->...c", phase, cur, st.seg_t)

    N = radiate(pts, 1.0)
    if st.ground:
        N = N + radiate(pts * np.array([1.0, 1.0, -1.0]), -1.0)
        N[th > np.pi / 2] = 0.0
    th_hat = np.stack([np.cos(th) * np.cos(ph), np.cos(th) * np.sin(ph), -np.sin(th)], -1)
    ph_hat = np.stack([-np.sin(ph), np.cos(ph), np.zeros_like(ph)], -1)
    pre = -1j * omega * MU0 / (4 * np.pi)
    return pre * (N * th_hat).sum(-1), pre * (N * ph_hat).sum(-1)


def directivity_grid(Et, Ep, theta, phi):
    """Directivity (linear) over the grid, integrating over the full theta/phi range given."""
    U = (np.abs(Et) ** 2 + np.abs(Ep) ** 2) / (2 * ETA0)
    th = theta[:, None]
    dth, dph = theta[1] - theta[0], phi[1] - phi[0]
    P_rad = (U * np.sin(th)).sum() * dth * dph
    return 4 * np.pi * U / P_rad, P_rad
