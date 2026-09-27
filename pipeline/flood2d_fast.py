"""2D surface routing (diffusion wave) of SWMM manhole flooding - numba version of flood2d.py, same method and output.
Usage: python3 flood2d_fast.py <tag> [dem.npz|dem30.npz]"""
import sys, json, time, os, numpy as np
from numba import njit
from swmm.toolkit import output, shared_enum as se
os.chdir(os.path.dirname(os.path.abspath(__file__)))
tag = sys.argv[1]; DEMF = sys.argv[2] if len(sys.argv) > 2 else 'dem.npz'; SUF = '' if DEMF == 'dem.npz' else '_30'
G = np.load(DEMF); z = G['dem'].astype(np.float64); sea = G['sea']; x0, y1, CELL = float(G['x0']), float(G['y1']), float(G['cell'])
nr, nc = z.shape; dx = CELL * 0.9742; A = dx * dx; nM = 0.035; g = 9.81
net = json.load(open('net3857.json'))
h_ = output.init(); output.open(h_, f'swmm_{tag}.out')
nper = output.get_times(h_, se.Time.NUM_PERIODS); step = output.get_times(h_, se.Time.REPORT_STEP)
NN = output.get_proj_size(h_)[se.ElementType.NODE.value]
oi = {output.get_elem_name(h_, se.ElementType.NODE, i): i for i in range(NN)}
nx_ = np.array(net['nodes']['x']); ny_ = np.array(net['nodes']['y'])
col = np.clip(((nx_ - x0) // CELL).astype(np.int64), 0, nc - 1); row = np.clip(((y1 - ny_) // CELL).astype(np.int64), 0, nr - 1)
omap = np.array([oi[n] for n in net['nodes']['id']])
Q = np.array([np.array(output.get_node_attribute(h_, p, se.NodeAttribute.FLOODING_LOSSES))[omap] for p in range(nper)])


@njit(cache=True)
def run(z, sea, Q, row, col, step, nper, dt, dx, A, nM, g, want_t):
    nr, nc = z.shape; h = np.zeros((nr, nc)); qx = np.zeros((nr, nc)); qy = np.zeros((nr, nc)); fac = np.ones((nr, nc))
    out = np.zeros((len(want_t), nr, nc), np.uint8); wi = 0
    r0, r1, c0, c1 = nr, -1, nc, -1  # active box
    t = 0.0; tend = nper * step; vin = 0.0
    while t < tend - 1e-6:
        p = min(nper - 1, int(t // step))
        for k in range(len(row)):
            if Q[p, k] > 0:
                r = row[k]; c = col[k]; h[r, c] += Q[p, k] * dt / A; vin += Q[p, k] * dt
                if r < r0: r0 = r
                if r > r1: r1 = r
                if c < c0: c0 = c
                if c > c1: c1 = c
        if r1 >= 0:
            a0 = max(r0 - 2, 0); a1 = min(r1 + 2, nr - 1); b0 = max(c0 - 2, 0); b1 = min(c1 + 2, nc - 1)
            # fluxes (x faces: between c and c+1; y faces: between r and r+1)
            for r in range(a0, a1 + 1):
                for c in range(b0, b1 + 1):
                    qx[r, c] = 0.0; qy[r, c] = 0.0; fac[r, c] = 1.0
            for r in range(a0, a1 + 1):
                for c in range(b0, b1 + 1):
                    e0 = z[r, c] + h[r, c]
                    if c < b1:
                        e1 = z[r, c + 1] + h[r, c + 1]; hf = max(e0, e1) - max(z[r, c], z[r, c + 1])
                        if hf > 0:
                            d = e0 - e1; q = hf ** (5.0 / 3.0) / nM * np.sqrt(abs(d) / dx); qm = hf * np.sqrt(g * hf)
                            qx[r, c] = min(q, qm) * (1.0 if d > 0 else -1.0)
                    if r < a1:
                        e1 = z[r + 1, c] + h[r + 1, c]; hf = max(e0, e1) - max(z[r, c], z[r + 1, c])
                        if hf > 0:
                            d = e0 - e1; q = hf ** (5.0 / 3.0) / nM * np.sqrt(abs(d) / dx); qm = hf * np.sqrt(g * hf)
                            qy[r, c] = min(q, qm) * (1.0 if d > 0 else -1.0)
            # positivity limiter
            for r in range(a0, a1 + 1):
                for c in range(b0, b1 + 1):
                    o = 0.0
                    if qx[r, c] > 0: o += qx[r, c]
                    if c > b0 and qx[r, c - 1] < 0: o -= qx[r, c - 1]
                    if qy[r, c] > 0: o += qy[r, c]
                    if r > a0 and qy[r - 1, c] < 0: o -= qy[r - 1, c]
                    need = o * dx * dt; avail = h[r, c] * A
                    if need > avail: fac[r, c] = avail / need
            for r in range(a0, a1 + 1):
                for c in range(b0, b1 + 1):
                    if c < b1:
                        q = qx[r, c]; q *= fac[r, c] if q > 0 else fac[r, c + 1]; qx[r, c] = q
                    if r < a1:
                        q = qy[r, c]; q *= fac[r, c] if q > 0 else fac[r + 1, c]; qy[r, c] = q
            for r in range(a0, a1 + 1):
                for c in range(b0, b1 + 1):
                    d = 0.0
                    if c < b1: d -= qx[r, c]
                    if c > b0: d += qx[r, c - 1]
                    if r < a1: d -= qy[r, c]
                    if r > a0: d += qy[r - 1, c]
                    v = h[r, c] + d * dx * dt / A
                    if sea[r, c] or v < 0: v = 0.0
                    h[r, c] = v
            # grow active box where water reached its edge
            for r in range(a0, a1 + 1):
                if h[r, b0] > 0 and b0 < c0: c0 = b0
                if h[r, b1] > 0 and b1 > c1: c1 = b1
            for c in range(b0, b1 + 1):
                if h[a0, c] > 0 and a0 < r0: r0 = a0
                if h[a1, c] > 0 and a1 > r1: r1 = a1
        t += dt
        while wi < len(want_t) and t >= want_t[wi] - 1e-6:
            for r in range(nr):
                for c in range(nc):
                    out[wi, r, c] = min(250, int(round(h[r, c] * 100)))
            wi += 1
    return out, vin, h.sum() * A


dt = 4.0 * CELL / 60.0; t0_idx = nper - 14
want = np.array([(t0_idx + 1 + f) * step for f in range(13)], float)
tic = time.time()
D, vin, vst = run(z, sea, Q, row, col, float(step), nper, dt, dx, A, nM, g, want)
np.savez_compressed(f'flood_{tag}{SUF}.npz', depth=D)
print(tag, SUF or '_60', 'done', round(time.time() - tic), 's', 'cells>15cm', [(d > 15).sum() for d in D][::4], 'max cm', int(D.max()), 'inflow Mm3', round(vin / 1e6, 2), 'stored Mm3', round(vst / 1e6, 2))
