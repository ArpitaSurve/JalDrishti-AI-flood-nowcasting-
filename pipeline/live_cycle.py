"""One real-time cycle (run every 15 min by GitHub Actions or cron on a server):
  1. rain: Open-Meteo 15-min for the last 6 h (spin-up) + radar nowcast 0-3 h
     (RainViewer composite of the IMD Doppler network -> dBZ -> Marshall-Palmer -> motion field -> extrapolation);
     falls back to the Open-Meteo 15-min forecast if radar is unavailable
  2. EPA SWMM 5.2 on the full GCC drain network (run_event.py)
  3. 2D surface routing of manhole overflow on the terrain grid (flood2d.py)
  4. publish site/live/latest.json + depth_live.bin.gz, which the dashboard's Live mode loads
Usage: python3 live_cycle.py [site_dir]"""
import sys, os, io, json, gzip, time, subprocess, urllib.request, datetime as dt, numpy as np
from pathlib import Path
from PIL import Image
from scipy.ndimage import map_coordinates, gaussian_filter, shift
HERE = Path(__file__).resolve().parent; SITE = Path(sys.argv[1] if len(sys.argv) > 1 else HERE / 'site'); (SITE / 'live').mkdir(parents=True, exist_ok=True)
LATS = [12.85, 12.95, 13.05, 13.15, 13.25]; LONS = [80.05, 80.15, 80.25, 80.35]
PAL = {int(k): v for k, v in json.load(open(HERE / 'rvpal.json')).items()}
tic = time.time()


def get(url, n=4):
    for k in range(n):
        try: return urllib.request.urlopen(url, timeout=60).read()
        except Exception:
            if k == n - 1: raise
            time.sleep(4 * (k + 1))


# ---- 1a. Open-Meteo: last 6 h + next 3 h at 15 min
la = ','.join(str(a) for a in LATS for _ in LONS); lo = ','.join(str(b) for _ in LATS for b in LONS)
om = json.loads(get(f'https://api.open-meteo.com/v1/forecast?latitude={la}&longitude={lo}&minutely_15=precipitation&past_minutely_15=24&forecast_minutely_15=13&timezone=GMT'))
times = [dt.datetime.fromisoformat(t) for t in om[0]['minutely_15']['time']]
R = np.array([[p['minutely_15']['precipitation'][k] or 0 for p in om] for k in range(len(times))]) * 4  # mm/h
now = dt.datetime.utcnow(); k0 = max(i for i, t in enumerate(times) if t <= now)
src = 'Open-Meteo 15-min forecast'

# ---- 1b. radar nowcast (overrides 0-3 h if available)
try:
    meta = json.loads(get('https://api.rainviewer.com/public/weather-maps.json')); past = meta['radar']['past'][-7:]
    Z, TX, TY, DS = 7, (91, 92, 93), (58, 59, 60), 3
    frames = []
    for p in past:
        img = np.zeros((768, 768), np.float32)
        for i, tx in enumerate(TX):
            for j, ty in enumerate(TY):
                a = np.array(Image.open(io.BytesIO(get(f"{meta['host']}{p['path']}/256/{Z}/{tx}/{ty}/2/0_0.png"))).convert('RGBA')).astype(np.int64)
                key = a[..., 0] << 16 | a[..., 1] << 8 | a[..., 2]
                dbz = np.vectorize(lambda k: PAL.get(int(k), -99.0))(key); dbz[a[..., 3] == 0] = -99
                rr = np.where(dbz >= 5, ((10 ** (dbz / 10)) / 200) ** (1 / 1.6), 0)
                img[j * 256:(j + 1) * 256, i * 256:(i + 1) * 256] = rr
        frames.append(img.reshape(256, DS, 256, DS).mean(axis=(1, 3)))
    gap = (past[-1]['time'] - past[-3]['time']) / 60  # minutes
    A, Bf = np.log1p(frames[-3]), np.log1p(frames[-1]); best, bv = (0, 0), 1e9
    for dy in range(-6, 7):
        for dx in range(-6, 7):
            c = np.abs(shift(A, (dy, dx), order=0, mode='nearest') - Bf).mean()
            if c < bv: bv, best = c, (dy, dx)
    vy, vx = best[0] / gap, best[1] / gap  # cells per minute
    yy, xx = np.mgrid[0:256, 0:256].astype(float)
    def cells(F):
        out = []
        for a_ in LATS:
            for b_ in LONS:
                X = (b_ + 180) / 360 * 2 ** Z; Y = (1 - np.log(np.tan(np.radians(a_)) + 1 / np.cos(np.radians(a_))) / np.pi) / 2 * 2 ** Z
                px, py = (X - TX[0]) * 256 / DS, (Y - TY[0]) * 256 / DS; out.append(F[int(py) - 1:int(py) + 2, int(px) - 1:int(px) + 2].mean())
        return out
    t_r = dt.datetime.utcfromtimestamp(past[-1]['time'])
    k0 = max(i for i, t in enumerate(times) if t <= t_r)
    for k in range(13):
        F = np.maximum(0, map_coordinates(frames[-1], [yy - vy * 15 * k, xx - vx * 15 * k], order=1, mode='constant'))
        if k0 + k < len(R): R[k0 + k] = cells(F)
    src = f'radar nowcast (RainViewer composite of the IMD Doppler network, motion {np.hypot(*best) / gap * 60 * 3.65:.0f} km/h)'
except Exception as e:
    print('radar unavailable:', e)

# ---- 2. SWMM: write rain file and run (6 h spin-up, 3 h forecast)
T0 = times[k0]; sel = slice(max(0, k0 - 24), min(len(times), k0 + 13))
np.savez(HERE / 'live_rain.npz', t=np.array([int(t.replace(tzinfo=dt.timezone.utc).timestamp()) for t in times[sel]]), P=R[sel], step=900)
env = dict(os.environ, RAIN=str(HERE / 'live_rain.npz'), RSCALE='1.0')
subprocess.run([sys.executable, 'run_event.py', 'live', T0.strftime('%Y-%m-%d %H:%M')], cwd=HERE, env=env, check=True)
# ---- 3. 2D surface routing
subprocess.run([sys.executable, 'flood2d_fast.py', 'live', 'dem30.npz'], cwd=HERE, check=True)
CR = json.load(open(HERE / 'crop.json'))
D = np.load(HERE / 'flood_live_30.npz')['depth'][:, CR['R0']:CR['R1'], CR['C0']:CR['C1']]
D = np.minimum(250, np.round(D.astype(float) / CR['qstep']) * CR['qstep']).astype(np.uint8)
gz = gzip.compress(D.tobytes(), 9)
import base64
(SITE / 'live' / 'depth_live.txt').write_text(base64.b64encode(gz).decode())
# drains % full
from swmm.toolkit import output, shared_enum as se
net = json.load(open(HERE / 'net3857.json')); h = output.init(); output.open(h, str(HERE / 'swmm_live.out'))
L = output.get_proj_size(h)[se.ElementType.LINK.value]; li = {output.get_elem_name(h, se.ElementType.LINK, i): i for i in range(L)}
lm = np.array([li[n] for n in net['cond']['id']]); nper = output.get_times(h, se.Time.NUM_PERIODS)
drains = [np.round(np.minimum(1, np.array(output.get_link_attribute(h, nper - 14 + f, se.LinkAttribute.CAPACITY))[lm]) * 100).astype(int).tolist() for f in range(13)]
r15 = R[max(0, k0 - 48):k0 + 13].tolist()
latest = {'t0': T0.isoformat(), 'rain_source': src, 'runtime_min': round((time.time() - tic) / 60, 1), 'depth': 'depth_live.txt', 'drains': drains,
          'rain': {'r15': r15, 'spin': min(48, k0), 'series': [float(np.mean(r)) for r in R[max(0, k0 - 24):k0 + 13:4]], 'seriesT0': min(24, k0) // 4, 'step': 60,
                   'label': 'Live rain over Chennai: last 6 h and ' + ('radar nowcast' if 'radar' in src else 'forecast') + ' to +3 h', 'days': [], 'scale': 1},
          'wet_cells_15cm': [int((d > 15).sum()) for d in D]}
json.dump(latest, open(SITE / 'live' / 'latest.json', 'w'))
print('cycle done', T0, src, 'runtime', latest['runtime_min'], 'min', 'wet cells', latest['wet_cells_15cm'][-1])
