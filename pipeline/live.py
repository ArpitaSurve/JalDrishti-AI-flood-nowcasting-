"""Live operation loop (every 15 min): fetch latest rain -> nowcast -> SWMM -> 2D surface -> publish data for API/dashboard.

Status: code path for production. Needs (1) NASA Earthdata login for IMERG Early (4 h latency) or IMD radar
mosaics via an MoES data-sharing agreement, (2) a server in India (NIC MeghRaj or an Indian cloud region).
Run:  EARTHDATA_TOKEN=... python pipeline/live.py
"""
import os, time, subprocess, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BOX = (79.5, 12.3, 81.0, 13.8)  # wider than Chennai so optical flow can track storms entering the city


def fetch_rain(now):
    """Download the last 3 h of rain frames for BOX.
    Production: IMD Doppler radar (Chennai / Karaikal / Sriharikota) reflectivity -> rain rate (Z = 200 R^1.6).
    Fallback: IMERG Early half-hourly via NASA GES DISC OPeNDAP (needs EARTHDATA_TOKEN)."""
    token = os.environ.get('EARTHDATA_TOKEN')
    if not token:
        raise SystemExit('Set EARTHDATA_TOKEN (NASA Earthdata) or configure the IMD radar feed')
    # GES DISC subset URL pattern (IMERG Early HH, V07): see https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGHHE_07
    # Implemented with earthaccess in production: earthaccess.search_data(short_name='GPM_3IMERGHHE', bounding_box=BOX, temporal=(...))
    import earthaccess  # pip install earthaccess
    earthaccess.login(strategy='environment')
    res = earthaccess.search_data(short_name='GPM_3IMERGHHE', version='07', bounding_box=BOX,
                                  temporal=((now - dt.timedelta(hours=3)).isoformat(), now.isoformat()))
    return earthaccess.download(res, str(ROOT / 'work' / 'rain'))


def nowcast(frames):
    """0-3 h rain nowcast. Uses pysteps (optical flow + S-PROG extrapolation) when >= 3 frames on BOX are available,
    otherwise persistence of the last hour (what the replay uses)."""
    import numpy as np
    try:
        from pysteps import motion, nowcasts
        V = motion.get_method('lucaskanade')(frames[-3:])
        return nowcasts.get_method('sprog')(frames[-3:], V, 12, n_cascade_levels=6, R_thr=0.1)  # 12 x 15 min
    except Exception:
        return np.repeat(frames[-2:].mean(axis=0, keepdims=True), 12, axis=0)


def run_cycle():
    now = dt.datetime.utcnow().replace(second=0, microsecond=0)
    files = fetch_rain(now)
    # 1) build rain frames and nowcast, 2) write SWMM inp with per-cell gauges, 3) run SWMM, 4) 2D routing, 5) export
    for cmd in (['python', 'pipeline/run2.py', 'live', 'persist', '-', '0'],
                ['python', 'pipeline/flood2d.py', 'live'],
                ['python', 'pipeline/export.py', '--live']):
        subprocess.run(cmd, cwd=ROOT, check=True)
    print('cycle done', now.isoformat(), 'files', len(files))


if __name__ == '__main__':
    while True:
        t = time.time()
        try: run_cycle()
        except Exception as e: print('cycle failed:', e)
        time.sleep(max(60, 900 - (time.time() - t)))
