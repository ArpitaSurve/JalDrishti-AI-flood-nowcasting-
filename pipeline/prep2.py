"""Basemap + routing graph + facilities for JalDrishti v2. Output: base.json"""
import json, re, numpy as np, pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
R = '/home/claude/jd/repo/'
tr = Transformer.from_crs(4326, 32644, always_xy=True)
E0, N0 = 400000.0, 1410000.0  # fixed local origin (UTM 44N)
def xy(lon, lat):
    x, y = tr.transform(lon, lat); return np.round(np.asarray(x) - E0).astype(int), np.round(np.asarray(y) - N0).astype(int)

def dp(pts, eps):  # Douglas-Peucker on Nx2
    if len(pts) < 3: return pts
    a, b = pts[0], pts[-1]; ab = b - a; L = np.hypot(*ab) or 1
    d = np.abs(np.cross(ab, pts[1:-1] - a)) / L; i = int(np.argmax(d))
    if d[i] > eps: return np.vstack([dp(pts[:i + 2], eps)[:-1], dp(pts[i + 1:], eps)])
    return np.vstack([a, b])

# ---------- drain model nodes (from SWMM inp) for depth lookup
inp = open(R + 'derived/swd_model.inp').read()
def section(n):
    m = re.search(rf'^\[{n}\]\s*$(.*?)(?=^\[|\Z)', inp, re.M | re.S); return [l.split() for l in m.group(1).splitlines() if l.strip() and not l.startswith(';')]
coords = {p[0]: (float(p[1]) - E0, float(p[2]) - N0) for p in section('COORDINATES')}
jn = [p[0] for p in section('JUNCTIONS')] + [p[0] for p in section('OUTFALLS')]
dn = np.array([coords[n] for n in jn]); dtree = cKDTree(dn)

# ---------- roads -> graph split at shared OSM nodes
KEEP = {'motorway': 1, 'trunk': 1, 'primary': 1, 'secondary': 2, 'tertiary': 3, 'motorway_link': 1, 'trunk_link': 1, 'primary_link': 1,
        'secondary_link': 2, 'tertiary_link': 3, 'residential': 4, 'living_street': 4, 'unclassified': 4, 'road': 4}
ways = [w for w in json.load(open(R + 'derived/osm/roads.json'))['elements'] if w.get('tags', {}).get('highway') in KEEP and w.get('geometry')]
use = {}
for w in ways:
    for n in w['nodes']: use[n] = use.get(n, 0) + 1
gid = {}; gx = []; gy = []
def gnode(osm, x, y):
    if osm not in gid: gid[osm] = len(gx); gx.append(int(x)); gy.append(int(y))
    return gid[osm]
edges = []  # (a,b,len,cls,nameidx,geom)
names = {}; name_list = []
def nidx(nm):
    if not nm: return -1
    if nm not in names: names[nm] = len(name_list); name_list.append(nm)
    return names[nm]
for w in ways:
    t = w['tags']; cls = KEEP[t['highway']]; nm = nidx(t.get('name'))
    lon = np.array([g['lon'] for g in w['geometry']]); lat = np.array([g['lat'] for g in w['geometry']])
    X, Y = xy(lon, lat); nodes = w['nodes']
    if len(nodes) != len(X): continue
    cut = [0] + [i for i in range(1, len(nodes) - 1) if use[nodes[i]] > 1] + [len(nodes) - 1]
    for s, e in zip(cut[:-1], cut[1:]):
        seg = np.c_[X[s:e + 1], Y[s:e + 1]].astype(float)
        L = float(np.sum(np.hypot(*np.diff(seg, axis=0).T)))
        if L < 1: continue
        g = dp(seg, 4.0).astype(int)
        a = gnode(nodes[s], X[s], Y[s]); b = gnode(nodes[e], X[e], Y[e])
        edges.append((a, b, round(L), cls, nm, g))
print('graph nodes', len(gx), 'edges', len(edges), 'pts', sum(len(e[5]) for e in edges))

# drain samples per edge: nearest drain node (<=70 m) at 3 points along the edge
samp = []
for e in edges:
    g = e[5].astype(float); cum = np.r_[0, np.cumsum(np.hypot(*np.diff(g, axis=0).T))]; tot = cum[-1] or 1
    ids = {}
    for f in (0.2, 0.5, 0.8):
        k = np.searchsorted(cum, f * tot); k = min(max(k, 1), len(g) - 1)
        t = (f * tot - cum[k - 1]) / max(cum[k] - cum[k - 1], 1e-6); p = g[k - 1] + t * (g[k] - g[k - 1])
        d, i = dtree.query(p)
        if d <= 150: ids[int(i)] = max(ids.get(int(i), 0), 10 if d <= 70 else 6)  # weight x10: overflow spreads, attenuated beyond 70 m
    samp.append([v for kv in sorted(ids.items()) for v in kv])
cov = sum(1 for s in samp if s) / len(samp); print('edges with drain data', round(cov, 3))

# flatten geometry with delta encoding
geo = []; goff = [0]
for e in edges:
    g = e[5]; d = np.diff(np.vstack([[0, 0], g]), axis=0); d[0] = g[0]
    geo.extend(d.ravel().tolist()); goff.append(len(geo) // 2)

# road name anchor points for search/labels (longest edge per name)
best = {}
for k, e in enumerate(edges):
    if e[4] >= 0 and (e[4] not in best or e[2] > edges[best[e[4]]][2]): best[e[4]] = k
labels = []
for nmi, k in best.items():
    g = edges[k][5]; m = g[len(g) // 2]
    labels.append([nmi, int(m[0]), int(m[1]), edges[k][3], edges[k][2]])

# ---------- wards and coastline
wf = json.load(open(R + 'web/data/wards.json'))['features']
wards = []
for f in wf:
    gm = f['geometry']; polys = gm['coordinates'] if gm['type'] == 'MultiPolygon' else [gm['coordinates']]
    rings = []
    for poly in polys:
        ring = np.array(poly[0]); X, Y = xy(ring[:, 0], ring[:, 1]); rr = dp(np.c_[X, Y].astype(float), 6).astype(int)
        rings.append(rr.ravel().tolist())
    wards.append({'w': f['properties']['ward'], 'z': f['properties']['zone'], 'have': f['properties']['have'], 'r': rings})
coast = []
for w in json.load(open(R + 'derived/osm/coastline.json'))['elements']:
    if not w.get('geometry'): continue
    X, Y = xy([g['lon'] for g in w['geometry']], [g['lat'] for g in w['geometry']])
    coast.append(dp(np.c_[X, Y].astype(float), 8).astype(int).ravel().tolist())

# ---------- facilities from survey-sheet labels (real names, sheet positions)
t = pd.read_csv('/mnt/user-data/uploads/1790396429200_map_text_as_drawn.csv')
tE, tN = t.east - E0, t.north - N0
def clean(s):
    s = re.sub(r'([a-z])([A-Z])', r'\1 \2', s); s = re.sub(r'\s+', ' ', s).strip(' ,.-/›'); return s.replace('Chennal', 'Chennai')
def pick(pat, maxlen, sep, bad=None):
    out = []
    for i in t.index[t.text.str.contains(pat, case=False, na=False)]:
        s = t.text[i]
        if len(s) > maxlen or (bad and re.search(bad, s, re.I)): continue
        nm = clean(s); p = (float(tE[i]), float(tN[i]))
        if any(np.hypot(p[0] - q['x'], p[1] - q['y']) < sep for q in out): continue
        out.append({'name': nm, 'x': round(p[0]), 'y': round(p[1]), 'ward': int(t.ward[i])})
    return out
hosp = pick('Hospital', 38, 600, bad=r'Road|Street|Quarters|St$')
subw = pick('Subway', 30, 300, bad=r'Restaurant|Road')
for f in subw: f['name'] = {'7.705Doraiswamy Subway Dmnin': 'Doraiswamy Subway', 'Madleysubway': 'Madley Subway'}.get(f['name'], f['name'])
depot = pick(r'MTC|Bus Terminus|BusTerminus', 34, 500, bad=r'Street|Road')
fire = pick(r'Fire ?Station', 20, 500)
police = pick(r'Police ?Station|Police\)Station', 26, 500)
print('hosp', len(hosp), 'subways', [s['name'] for s in subw], 'depots', len(depot), 'fire', len(fire), 'police', len(police))

# snap facilities to road graph nodes
gtree = cKDTree(np.c_[gx, gy])
for L in (hosp, subw, depot, fire, police):
    for f in L: d, i = gtree.query([f['x'], f['y']]); f['g'] = int(i); f['snap'] = round(float(d))

out = {'E0': E0, 'N0': N0,
       'g': {'x': gx, 'y': gy},
       'e': {'a': [e[0] for e in edges], 'b': [e[1] for e in edges], 'len': [e[2] for e in edges], 'cls': [e[3] for e in edges],
             'name': [e[4] for e in edges], 'geo': geo, 'off': goff, 'samp': samp},
       'names': name_list, 'labels': labels, 'wards': wards, 'coast': coast,
       'drainXY': np.round(dn).astype(int).ravel().tolist(), 'drainIds': jn,
       'fac': {'hosp': hosp, 'subway': subw, 'depot': depot, 'fire': fire, 'police': police}}
json.dump(out, open('/home/claude/jd/base.json', 'w'), separators=(',', ':'))
import os; print('base.json KB', os.path.getsize('/home/claude/jd/base.json') // 1024)
