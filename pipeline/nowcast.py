"""Optical-flow extrapolation rain nowcast (pysteps-style: motion field + semi-Lagrangian advection).
Motion from the wide-area rain field (Open-Meteo, 0.1 deg, 2.6 x 2.6 deg box); advected field is bias-matched to the
local observation (IMERG for Michaung) at issue time.
Usage: python3 nowcast.py michaung   -> writes nowcast_michaung.npz (Chennai 5x4 cells, 30-min, T0..T0+3h)
       python3 nowcast.py verify     -> skill of extrapolation vs persistence over the heaviest 2021-2026 events"""
import sys, json, urllib.request, numpy as np, pandas as pd
from scipy.ndimage import map_coordinates, gaussian_filter, shift
LAT = np.round(np.arange(11.8, 14.41, 0.1), 2); LON = np.round(np.arange(79.0, 81.61, 0.1), 2)
CLAT = [12.85, 12.95, 13.05, 13.15, 13.25]; CLON = [80.05, 80.15, 80.25, 80.35]


def fetch(start, end):
    """hourly precip on the wide grid, returns times, array [t, lat, lon]"""
    la = [a for a in LAT for b in LON]; lo = [b for a in LAT for b in LON]; out = []
    for k in range(0, len(la), 40):
        url = ('https://archive-api.open-meteo.com/v1/archive?latitude=' + ','.join(f'{v:.2f}' for v in la[k:k + 40]) +
               '&longitude=' + ','.join(f'{v:.2f}' for v in lo[k:k + 40]) + f'&start_date={start}&end_date={end}&hourly=precipitation&timezone=GMT')
        for tr_ in range(4):
            try: js = json.load(urllib.request.urlopen(url, timeout=180)); break
            except Exception as e:
                import time; time.sleep(3 + 5 * tr_)
                if tr_ == 3: raise
        js = js if isinstance(js, list) else [js]
        out += [np.array(p['hourly']['precipitation'], float) for p in js]
    t = pd.to_datetime(js[0]['hourly']['time'])
    return t, np.nan_to_num(np.stack(out, 1).reshape(len(t), len(LAT), len(LON)))


def motion(f0, f1, maxs=6):
    """global + blockwise displacement (cells per hour) maximising correlation of log-rain, smoothed"""
    a, b = np.log1p(f0), np.log1p(f1)
    def best(A, Bm):
        bs, bv = (0, 0), -1e9
        for dy in range(-maxs, maxs + 1):
            for dx in range(-maxs, maxs + 1):
                s = shift(A, (dy, dx), order=0, mode='nearest'); m = s + Bm
                if m.sum() == 0: continue
                c = -np.abs(s - Bm).mean()
                if c > bv: bv, bs = c, (dy, dx)
        return bs
    g = best(a, b)
    H, W = a.shape; U = np.full((H, W), float(g[1])); V = np.full((H, W), float(g[0]))
    B_ = 9 if H > 20 else 5
    for i in range(0, H, B_):
        for j in range(0, W, B_):
            sa, sb = a[i:i + B_, j:j + B_], b[i:i + B_, j:j + B_]
            if sb.sum() < 1: continue
            dy, dx = best(sa, sb); V[i:i + B_, j:j + B_] = dy; U[i:i + B_, j:j + B_] = dx
    return gaussian_filter(U, 3), gaussian_filter(V, 3)


def advect(f, U, V, k):
    """semi-Lagrangian backward advection for k hours (fractional)"""
    H, W = f.shape; yy, xx = np.mgrid[0:H, 0:W].astype(float)
    return np.maximum(0, map_coordinates(f, [yy - V * k, xx - U * k], order=1, mode='nearest'))


def chennai(field):
    ia = [int(np.argmin(abs(LAT - a))) for a in CLAT]; io = [int(np.argmin(abs(LON - b))) for b in CLON]
    return field[..., ia, :][..., io]


def extrapolate(F, i0, steps_h):
    U, V = motion(F[i0 - 1], F[i0], maxs=3 if F.shape[1] < 20 else 6)
    return np.stack([advect(F[i0], U, V, k) for k in steps_h]), (float(U.mean()), float(V.mean()))


if sys.argv[1] == 'michaung':
    t, F = fetch('2023-12-03', '2023-12-04'); np.savez_compressed('om_wide_michaung.npz', t=t.values.astype('datetime64[s]').astype(int), F=F)
    T0 = pd.Timestamp('2023-12-03 21:00'); i0 = int(np.where(t == T0)[0][0])
    steps = np.arange(0.5, 3.01, 0.5)  # 30-min steps after issue
    ext, uv = extrapolate(F, i0, steps)
    # bias-match to IMERG over Chennai at issue time (last hour)
    import glob, xarray as xr
    d = xr.open_dataset((glob.glob('/mnt/user-data/uploads/*michaung*') + glob.glob('/root/.claude/uploads/*/*michaung*'))[0])
    P = d.precipitation.transpose('time', 'lat', 'lon').values; tt = pd.to_datetime([str(v) for v in d.time.values])
    j0 = int(np.where(tt == T0)[0][0]); im_last = P[j0 - 2:j0].mean(axis=0)  # 5x4 mm/h
    om_last = chennai(F[i0])
    ratio = np.clip(im_last.mean() / max(om_last.mean(), 0.1), 0.3, 3)
    nc = chennai(ext) * ratio  # [6,5,4] mm/h
    obs = P[j0:j0 + 6]; pers = np.repeat(im_last[None], 6, 0)
    mae = lambda a: float(np.abs(a - obs).mean())
    print('motion cells/h (u,v)', np.round(uv, 2), 'ratio', round(float(ratio), 2))
    print('Michaung rain MAE mm/h: extrapolation', round(mae(nc), 2), 'persistence', round(mae(pers), 2), 'obs mean', round(float(obs.mean()), 2))
    np.savez_compressed('nowcast_michaung.npz', nc=nc, pers=pers, obs=obs, uv=uv)
elif sys.argv[1] == 'verify':
    import time
    LAT = np.round(np.arange(11.8, 14.41, 0.2), 2); LON = np.round(np.arange(79.0, 81.61, 0.2), 2)
    H = np.load('om_hist.npz'); OT = pd.to_datetime(H['t'], unit='s'); s = pd.Series(H['P'].mean(1), index=OT)
    days = s.resample('1D').sum().sort_values(ascending=False).index[:8]
    rows = []
    for d in days:
        cf = f'om_wide_{d:%Y%m%d}.npz'
        import os
        if os.path.exists(cf): Z_ = np.load(cf); t, F = pd.to_datetime(Z_['t'], unit='s'), Z_['F']
        else:
          try: t, F = fetch(f'{d - pd.Timedelta("1D"):%Y-%m-%d}', f'{d + pd.Timedelta("1D"):%Y-%m-%d}')
          except Exception as e: print('skip', d.date(), e); time.sleep(90); continue
          np.savez_compressed(cf, t=t.values.astype('datetime64[s]').astype(int), F=F)
        loc = chennai(F).mean(axis=(1, 2))
        for i0 in range(2, len(t) - 3):
            if loc[i0 - 1] < 1: continue  # issue only when it is raining
            ext, _ = extrapolate(F, i0, [1, 2, 3])
            obs = chennai(F[i0 + 1:i0 + 4]); pers = np.repeat(chennai(F[i0])[None], 3, 0); ex = chennai(ext)
            rows.append([d.date(), *[np.abs(ex[k] - obs[k]).mean() for k in range(3)], *[np.abs(pers[k] - obs[k]).mean() for k in range(3)]])
        print(d.date(), len(rows), flush=True); time.sleep(45)
    R = pd.DataFrame(rows, columns=['day', 'ex1', 'ex2', 'ex3', 'pe1', 'pe2', 'pe3'])
    R.to_csv('nowcast_verify.csv', index=False)
    m = R.drop(columns='day').mean()
    print('issues', len(R), 'days', R.day.nunique())
    print('MAE mm/h  +1h: extrap', round(m.ex1, 2), 'persist', round(m.pe1, 2), '| +2h:', round(m.ex2, 2), round(m.pe2, 2), '| +3h:', round(m.ex3, 2), round(m.pe3, 2))
    json.dump({'issues': len(R), 'days': int(R.day.nunique()), 'mae': {k: round(float(v), 2) for k, v in m.items()}}, open('nowcast_verify.json', 'w'))
