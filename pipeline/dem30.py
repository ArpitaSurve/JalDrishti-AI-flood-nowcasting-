"""30 m terrain: Copernicus GLO-30 (DSM) fused with 5,373 GCC survey road levels, roads burned in. Output dem30.npz"""
import json, glob, numpy as np, pandas as pd, rasterio
from rasterio.merge import merge
from pyproj import Transformer
from scipy.ndimage import map_coordinates, gaussian_filter, minimum_filter, zoom
from scipy.interpolate import griddata
old = np.load('dem.npz'); B = json.load(open('base3857.json'))
OX, OY = B['OX'], B['OY']
import sys
SIG = float(sys.argv[1]) if len(sys.argv) > 1 else 2
HOLD = len(sys.argv) > 2
CELL = 30.0; x0, y1 = float(old['x0']), float(old['y1'])
nr, nc = old['dem'].shape[0] * 2, old['dem'].shape[1] * 2
gx = x0 + (np.arange(nc) + .5) * CELL; gy = y1 - (np.arange(nr) + .5) * CELL
GX, GY = np.meshgrid(gx, gy)
# grid -> lon/lat
R = 6378137.0
lon = np.degrees((GX + OX) / R); lat = np.degrees(2 * np.arctan(np.exp((GY + OY) / R)) - np.pi / 2)
src = [rasterio.open(f) for f in sorted(glob.glob('cop_*.tif'))]
mos, tr = merge(src)
Z = mos[0].astype(np.float32)
col = (lon - tr.c) / tr.a; row = (lat - tr.f) / tr.e
cop = map_coordinates(Z, [row, col], order=1, mode='nearest')
# survey points
T = Transformer.from_crs(32644, 3857, always_xy=True)
n = pd.read_csv('/mnt/user-data/uploads/1790396443831_swd_nodes_as_drawn.csv')
z = n.road_edge.fillna(n.drain_top); ok = z.notna() & (z > -2) & (z < 40)
X, Y = T.transform(n.east[ok].values, n.north[ok].values); X -= OX; Y -= OY; Zs = z[ok].values
ci = np.clip(((X - x0) // CELL).astype(int), 0, nc - 1); ri = np.clip(((y1 - Y) // CELL).astype(int), 0, nr - 1)
# ground estimate from DSM: 5th-percentile-like minimum over 150 m removes buildings/trees
ground = gaussian_filter(minimum_filter(cop, size=5), 1.5)
res = Zs - ground[ri, ci]
keep = np.abs(res - np.median(res)) < 4
rng = np.random.default_rng(1); test = rng.random(len(res)) < 0.2
fitk = keep & ~test if HOLD else keep
print('survey minus DSM-ground: median', round(float(np.median(res)), 2), 'IQR', np.round(np.percentile(res, [25, 75]), 2), 'kept', int(keep.sum()))
# smooth residual field (bias correction), zero-mean outside survey via nearest+blur
rf = griddata((X[fitk], Y[fitk]), res[fitk], (GX, GY), method='linear')
rn = griddata((X[fitk], Y[fitk]), res[fitk], (GX, GY), method='nearest')
rf = np.where(np.isnan(rf), np.median(res[keep]), rf); rf = gaussian_filter(np.where(np.isnan(rf), rn, rf), SIG)
g_dsm = ground + rf
# where survey is dense, trust the survey levels (holdout MAE 0.2 m vs 0.8 m for fused DSM); blend over 300-600 m
from scipy.spatial import cKDTree
sv = griddata((X[fitk], Y[fitk]), Zs[fitk], (GX, GY), method='linear')
dd, _ = cKDTree(np.c_[X[fitk], Y[fitk]]).query(np.c_[GX.ravel(), GY.ravel()]); dd = dd.reshape(GX.shape)
w = np.clip((600 - dd) / 300, 0, 1); w[np.isnan(sv)] = 0
g2 = np.where(w > 0, w * np.nan_to_num(sv) + (1 - w) * g_dsm, g_dsm)
# building/tree obstacles from DSM, capped at +3 m above ground (walls divert water, no towers)
obst = np.clip(cop + rf - g2, 0, 3.0)
# burn OSM roads: road cells = corrected ground minus 0.15 m (camber/kerb)
road = np.zeros((nr, nc), bool)
geo = np.array(B['e']['geo']).reshape(-1, 2); off = B['e']['off']
for e in range(len(off) - 1):
    p = np.cumsum(geo[off[e]:off[e + 1]], axis=0).astype(float)
    for a, b in zip(p[:-1], p[1:]):
        L = max(1, int(np.hypot(*(b - a)) // 10))
        for t in np.linspace(0, 1, L + 1):
            q = a + t * (b - a); c = int((q[0] - x0) // CELL); r = int((y1 - q[1]) // CELL)
            if 0 <= r < nr and 0 <= c < nc: road[r, c] = True
dem = np.where(road, g2 - 0.05, g2 + obst)
sea = zoom(old['sea'].astype(np.uint8), 2, order=0).astype(bool)[:nr, :nc]
dem[sea] = -1.0
surveyd = zoom(old['surveyd'].astype(np.uint8), 2, order=0).astype(bool)[:nr, :nc]
# check: error at survey points (leave-in) and vs old 60 m grid
err = dem[ri, ci] - Zs
tk = keep & test
print('HOLDOUT MAE ground', round(float(np.abs(g2[ri,ci]-Zs)[tk].mean()), 2), 'with obstacles', round(float(np.abs(err[tk]).mean()), 2), 'raw DSM', round(float(np.abs(cop[ri,ci]-Zs)[tk].mean()),2), 'survey-only interp', round(float(np.abs(griddata((X[fitk],Y[fitk]),Zs[fitk],(X[tk],Y[tk]),method='linear')-Zs[tk])[~np.isnan(griddata((X[fitk],Y[fitk]),Zs[fitk],(X[tk],Y[tk]),method='linear'))].mean()),2)) if HOLD else None
print('grid', nr, 'x', nc, 'road cells', int(road.sum()), 'fit at survey pts MAE', round(float(np.abs(err[keep]).mean()), 2), 'm', 'z pct', np.round(np.percentile(dem[~sea], [1, 50, 99]), 2))
if not HOLD: np.savez_compressed('dem30.npz', dem=dem.astype(np.float32), sea=sea, surveyd=surveyd, road=road, x0=x0, y1=y1, cell=CELL, nc=nc, nr=nr)
