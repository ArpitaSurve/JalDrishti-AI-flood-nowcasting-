"""DEM (60 m, local Web Mercator) interpolated from GCC survey road-edge levels; sea mask from OSM coastline."""
import json, numpy as np, pandas as pd
from pyproj import Transformer
from scipy.interpolate import griddata
from scipy.ndimage import gaussian_filter
B = json.load(open('base3857.json'))
OX, OY = B['OX'], B['OY']
T = Transformer.from_crs(32644, 3857, always_xy=True)
n = pd.read_csv('/mnt/user-data/uploads/1790396443831_swd_nodes_as_drawn.csv')
z = n.road_edge.fillna(n.drain_top)
ok = z.notna() & (z > -2) & (z < 40)
X, Y = T.transform(n.east[ok].values, n.north[ok].values); X -= OX; Y -= OY; Z = z[ok].values
# robust: drop points that differ > 3 m from local median (OCR outliers)
from scipy.spatial import cKDTree
tr = cKDTree(np.c_[X, Y]); keep = np.ones(len(Z), bool)
for i, (x, y) in enumerate(zip(X, Y)):
    idx = tr.query_ball_point([x, y], 400)
    if len(idx) > 4 and abs(Z[i] - np.median(Z[idx])) > 3: keep[i] = False
X, Y, Z = X[keep], Y[keep], Z[keep]
# grid over whole city (ward extent) + 1 km
xs, ys = [], []
for w in B['wards']:
    for r in w['r']: xs += r[0::2]; ys += r[1::2]
CELL = 60.0
x0, x1 = min(xs) - 1000, max(xs) + 1000; y0, y1 = min(ys) - 1000, max(ys) + 1000
nc, nr = int((x1 - x0) // CELL) + 1, int((y1 - y0) // CELL) + 1
gx = x0 + (np.arange(nc) + .5) * CELL; gy = y1 - (np.arange(nr) + .5) * CELL
GX, GY = np.meshgrid(gx, gy)
lin = griddata((X, Y), Z, (GX, GY), method='linear')
near = griddata((X, Y), Z, (GX, GY), method='nearest')
dem = np.where(np.isnan(lin), near, lin)
dem = gaussian_filter(dem, 1.0)
# distance to nearest survey point -> confidence mask
d, _ = tr.query(np.c_[GX.ravel(), GY.ravel()]); surveyd = (d.reshape(GX.shape) < 300)
# sea: east of coastline per row
cpts = np.vstack([np.array(c).reshape(-1, 2) for c in B['coast'] if len(c) >= 4])
sea = np.zeros_like(dem, bool)
for r in range(nr):
    band = cpts[np.abs(cpts[:, 1] - gy[r]) < CELL * 2]
    if len(band): sea[r] = gx > band[:, 0].max()
# rows without coastline: copy nearest row with one
has = sea.any(axis=1)
for r in range(nr):
    if not has[r]:
        k = np.argmin(np.where(has, np.abs(np.arange(nr) - r), 1e9)); sea[r] = sea[k]
dem[sea] = -1.0
np.savez_compressed('dem.npz', dem=dem.astype(np.float32), sea=sea, surveyd=surveyd, x0=x0, y1=y1, cell=CELL, nc=nc, nr=nr)
print('grid', nr, 'x', nc, 'points', len(Z), 'dropped', int((~keep).sum()), 'z range', np.round(np.percentile(dem[~sea], [1, 50, 99]), 2), 'sea frac', round(sea.mean(), 3), 'surveyed frac', round(surveyd.mean(), 3))
