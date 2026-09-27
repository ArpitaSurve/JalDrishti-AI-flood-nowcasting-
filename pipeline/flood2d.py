"""2D surface routing (diffusion wave, 60 m grid) of SWMM node flooding over the survey DEM.
Usage: python3 flood2d.py <tag>  -> flood_<tag>.npz with 13 depth frames (cm) for T+0..T+180."""
import sys, json, time, os, numpy as np
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from swmm.toolkit import output, shared_enum as se
tag = sys.argv[1]; DEMF = sys.argv[2] if len(sys.argv) > 2 else 'dem.npz'; SUF = '' if DEMF == 'dem.npz' else '_30'
G = np.load(DEMF); z = G['dem'].astype(np.float32); sea = G['sea']; x0, y1, CELL = float(G['x0']), float(G['y1']), float(G['cell'])
nr, nc = z.shape; dx = CELL * 0.9742  # true metres (Mercator scale at 13 N)
A = dx * dx; nM = 0.035; g = 9.81
net = json.load(open('net3857.json'))
h_ = output.init(); output.open(h_, f'swmm_{tag}.out')
nper = output.get_times(h_, se.Time.NUM_PERIODS); step = output.get_times(h_, se.Time.REPORT_STEP)
NN = output.get_proj_size(h_)[se.ElementType.NODE.value]
names = [output.get_elem_name(h_, se.ElementType.NODE, i) for i in range(NN)]
oi = {n: i for i, n in enumerate(names)}
ids = net['nodes']['id']; nx_ = np.array(net['nodes']['x']); ny_ = np.array(net['nodes']['y'])
col = np.clip(((nx_ - x0) // CELL).astype(int), 0, nc - 1); row = np.clip(((y1 - ny_) // CELL).astype(int), 0, nr - 1)
omap = np.array([oi[n] for n in ids])
Q = np.zeros((nper, len(ids)))
for p in range(nper):
    Q[p] = np.array(output.get_node_attribute(h_, p, se.NodeAttribute.FLOODING_LOSSES))[omap]  # m3/s overflow onto street
# SWMM period p covers (start + p*step, start + (p+1)*step]
h = np.zeros_like(z); dt = 4.0 * CELL / 60.0; t = 0.0; tend = nper * step
t0_idx = nper - 14  # period ending at issue time (13 frames after it)
frames = {}; want = {(t0_idx + 1 + f) * step: f for f in range(13)}
flat = row * nc + col
tic = time.time(); vol_in = 0.0; started = False
while t < tend - 1e-6:
    p = min(nper - 1, int(t // step))
    if not started:
        if Q[p].max() <= 0:
            t += dt
            for tw, f in want.items():
                if f not in frames and t >= tw - 1e-6: frames[f] = np.zeros(z.shape, np.uint8)
            continue
        started = True
    src = np.bincount(flat, weights=Q[p] * dt, minlength=nr * nc).reshape(nr, nc)
    h += src / A; vol_in += src.sum()
    eta = z + h
    # x faces
    dE = eta[:, :-1] - eta[:, 1:]; hf = np.maximum(np.maximum(eta[:, :-1], eta[:, 1:]) - np.maximum(z[:, :-1], z[:, 1:]), 0)
    qx = np.sign(dE) * hf ** (5 / 3) / nM * np.sqrt(np.abs(dE) / dx); qx = np.clip(qx, -hf * np.sqrt(g * hf), hf * np.sqrt(g * hf))
    dN = eta[:-1, :] - eta[1:, :]; hfy = np.maximum(np.maximum(eta[:-1, :], eta[1:, :]) - np.maximum(z[:-1, :], z[1:, :]), 0)
    qy = np.sign(dN) * hfy ** (5 / 3) / nM * np.sqrt(np.abs(dN) / dx); qy = np.clip(qy, -hfy * np.sqrt(g * hfy), hfy * np.sqrt(g * hfy))
    # outflow limiter (positivity)
    out = np.zeros_like(h)
    out[:, :-1] += np.maximum(qx, 0); out[:, 1:] += np.maximum(-qx, 0); out[:-1, :] += np.maximum(qy, 0); out[1:, :] += np.maximum(-qy, 0)
    avail = h * A; need = out * dx * dt
    fac = np.where(need > avail, avail / np.maximum(need, 1e-12), 1.0)
    fx = np.where(qx > 0, fac[:, :-1], fac[:, 1:]); fy = np.where(qy > 0, fac[:-1, :], fac[1:, :])
    qx *= fx; qy *= fy
    dV = np.zeros_like(h)
    dV[:, :-1] -= qx; dV[:, 1:] += qx; dV[:-1, :] -= qy; dV[1:, :] += qy
    h += dV * dx * dt / A
    h[sea] = 0; h = np.maximum(h, 0)
    t += dt
    for tw, f in want.items():
        if f not in frames and t >= tw - 1e-6: frames[f] = np.minimum(250, np.round(h * 100)).astype(np.uint8)
D = np.stack([frames[f] for f in range(13)])
np.savez_compressed(f'flood_{tag}{SUF}.npz', depth=D)
wet = (D > 15).sum(axis=(1, 2))
print(tag, 'done', round(time.time() - tic), 's', 'cells>15cm', wet.tolist(), 'max cm', int(D.max()), 'inflow Mm3', round(vol_in / 1e6, 2), 'stored Mm3', round(float(h.sum() * A / 1e6), 2))
