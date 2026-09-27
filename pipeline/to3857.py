"""Reproject base.json + net.json local UTM coords -> local Web Mercator (EPSG:3857) so raster tiles align."""
import json, numpy as np
from pyproj import Transformer
T = Transformer.from_crs(32644, 3857, always_xy=True)
B = json.load(open('base.json')); N = json.load(open('net.json'))
E0, N0 = B['E0'], B['N0']
def tx(x, y):
    X, Y = T.transform(np.asarray(x, float) + E0, np.asarray(y, float) + N0); return X, Y
# origin in 3857
ox, oy = T.transform(E0 + 20000, N0 + 20000); ox, oy = round(ox), round(oy)
def loc(x, y):
    X, Y = tx(x, y); return np.round(X - ox).astype(int), np.round(Y - oy).astype(int)
gx, gy = loc(B['g']['x'], B['g']['y']); B['g']['x'], B['g']['y'] = gx.tolist(), gy.tolist()
geo = np.array(B['e']['geo']).reshape(-1, 2); off = B['e']['off']; pts = np.zeros_like(geo)
for e in range(len(off) - 1):
    seg = geo[off[e]:off[e + 1]]; pts[off[e]:off[e + 1]] = np.cumsum(seg, axis=0)
X, Y = loc(pts[:, 0], pts[:, 1]); P = np.c_[X, Y]; enc = np.zeros_like(P)
for e in range(len(off) - 1):
    s = P[off[e]:off[e + 1]]; d = np.diff(np.vstack([[0, 0], s]), axis=0); d[0] = s[0]; enc[off[e]:off[e + 1]] = d
B['e']['geo'] = enc.ravel().tolist()
for l in B['labels']: x, y = loc(l[1], l[2]); l[1], l[2] = int(x), int(y)
for w in B['wards']:
    w['r'] = [np.c_[loc(np.array(r[0::2]), np.array(r[1::2]))].ravel().tolist() for r in w['r']]
B['coast'] = [np.c_[loc(np.array(c[0::2]), np.array(c[1::2]))].ravel().tolist() for c in B['coast']]
d = np.array(B['drainXY']).reshape(-1, 2); B['drainXY'] = np.c_[loc(d[:, 0], d[:, 1])].ravel().tolist()
for L in B['fac'].values():
    for f in L: x, y = loc(f['x'], f['y']); f['x'], f['y'] = int(x), int(y)
B['OX'], B['OY'] = ox, oy
nx_, ny_ = loc(N['nodes']['x'], N['nodes']['y']); N['nodes']['x'], N['nodes']['y'] = nx_.tolist(), ny_.tolist()
json.dump(B, open('base3857.json', 'w'), separators=(',', ':')); json.dump(N, open('net3857.json', 'w'), separators=(',', ':'))
print('origin', ox, oy)
