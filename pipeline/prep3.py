"""Quick what-if model inputs from the SWMM inp (same network) + IMERG rain. Output: net.json"""
import re, glob, json, numpy as np, pandas as pd, xarray as xr, networkx as nx
from pyproj import Transformer
R = '/home/claude/jd/repo/'
inp = open(R + 'derived/swd_model.inp').read()
def section(n):
    m = re.search(rf'^\[{n}\]\s*$(.*?)(?=^\[|\Z)', inp, re.M | re.S); return [l.split() for l in m.group(1).splitlines() if l.strip() and not l.startswith(';')]
E0, N0 = 400000.0, 1410000.0
J = section('JUNCTIONS'); O = section('OUTFALLS')
names = [p[0] for p in J] + [p[0] for p in O]; idx = {n: i for i, n in enumerate(names)}
N = len(names)
elev = np.array([float(p[1]) for p in J] + [float(p[1]) for p in O])
maxd = np.array([float(p[2]) for p in J] + [0.0] * len(O))
outlet = np.array([0] * len(J) + [1] * len(O))
co = {p[0]: (float(p[1]), float(p[2])) for p in section('COORDINATES')}
X = np.array([co[n][0] - E0 for n in names]); Y = np.array([co[n][1] - N0 for n in names])
xs = {p[0]: p for p in section('XSECTIONS')}
C = section('CONDUITS')
ca, cb, cap, clen, cw, cd, cid = [], [], [], [], [], [], []
for p in C:
    a, b = idx.get(p[1]), idx.get(p[2])
    if a is None or b is None: continue
    L = float(p[3]); n = float(p[4]); x = xs[p[0]]; d = float(x[2]); w = float(x[3]) if x[1].startswith('RECT') else d
    io, oo = float(p[5]), float(p[6])
    S = abs((elev[a] + io) - (elev[b] + oo)) / max(L, 1); S = min(max(S, 0.0005), 0.02)
    A = w * d; Rh = A / (w + 2 * d); q = (1 / n) * A * Rh ** (2 / 3) * np.sqrt(S)
    ca.append(a); cb.append(b); cap.append(round(q, 3)); clen.append(round(L)); cw.append(round(w, 2)); cd.append(round(d, 2)); cid.append(p[0])
G = nx.DiGraph(); G.add_nodes_from(range(N)); G.add_edges_from((a, b, {'k': k}) for k, (a, b) in enumerate(zip(ca, cb)))
rm = 0
while True:
    try: cyc = nx.find_cycle(G)
    except nx.NetworkXNoCycle: break
    G.remove_edge(*cyc[-1][:2]); rm += 1
order = list(nx.topological_sort(G)); outs = [[G.edges[i, j]['k'] for j in G.successors(i)] for i in range(N)]
inc = {}
for k, b in enumerate(cb): inc[b] = max(inc.get(b, 0), cap[k])
# subcatchments: area (ha), imperv
area = np.zeros(N); imp = np.full(N, 75.0)
for p in section('SUBCATCHMENTS'):
    i = idx.get(p[2])
    if i is not None: area[i] += float(p[3]) * 1e4; imp[i] = float(p[4])
# rain
rainf = (glob.glob('/mnt/user-data/uploads/*michaung*') + glob.glob('/root/.claude/uploads/*/*michaung*'))[0]
d = xr.open_dataset(rainf); P = d.precipitation.transpose('time', 'lat', 'lon').values
lats, lons = d.lat.values, d.lon.values; times = pd.to_datetime([str(v) for v in d.time.values])
tr = Transformer.from_crs(32644, 4326, always_xy=True); lo, la = tr.transform(X + E0, Y + N0)
cell = [int(np.argmin(abs(lats - a))) * len(lons) + int(np.argmin(abs(lons - b))) for a, b in zip(la, lo)]
i0 = int(np.where(times == pd.Timestamp('2023-12-03 09:00'))[0][0]); t0 = int(np.where(times == pd.Timestamp('2023-12-03 21:00'))[0][0])
rain15 = np.repeat(P[i0:t0 + 7].reshape(t0 + 7 - i0, -1), 2, axis=0)
am = P.mean(axis=(1, 2))
r1 = lambda a, k=1: [round(float(v), k) for v in a]
out = {'meta': {'t0': '2023-12-03T21:00:00', 'spin': (t0 - i0) * 2, 'areaSeries': r1(am, 2), 'seriesT0': t0,
                'dailyMean': r1(pd.Series(am, index=times).resample('1D').sum() * 0.5, 0), 'cyclesBroken': rm},
       'nodes': {'x': r1(X, 0), 'y': r1(Y, 0), 'id': names, 'inv': r1(elev, 2), 'maxd': r1(maxd, 2), 'outlet': outlet.tolist(),
                 'area': r1(area, 0), 'imp': r1(imp, 0), 'cell': cell, 'outCap': [round(inc.get(i, 0.3), 3) for i in range(N)],
                 'ward': [int(re.match(r'W(\d+)_', n).group(1)) if re.match(r'W(\d+)_', n) else 0 for n in names]},
       'order': order, 'outs': outs,
       'cond': {'a': ca, 'b': cb, 'cap': cap, 'len': clen, 'w': cw, 'd': cd, 'id': cid},
       'rain15': np.round(rain15, 2).tolist()}
json.dump(out, open('/home/claude/jd/net.json', 'w'), separators=(',', ':'))
import os; print('nodes', N, 'conduits', len(ca), 'cycles', rm, 'area med ha', round(np.median(area[area > 0]) / 1e4, 2), 'zero-area', int((area == 0).sum()), 'KB', os.path.getsize('/home/claude/jd/net.json') // 1024)
