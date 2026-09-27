"""Build a Michaung SWMM run from the reclaimchennai model: per-cell IMERG gauges, ponding on, 24 h window."""
import re, sys, glob, time, numpy as np, xarray as xr, pandas as pd
from pyproj import Transformer
from swmm.toolkit import solver

scale = 1.3
tag = sys.argv[1]; rainmode = sys.argv[2]; blockc = sys.argv[3]; outfall_stage = float(sys.argv[4])
SRC = '/home/claude/jd/repo/derived/swd_model.inp'
rainf = (glob.glob('/mnt/user-data/uploads/*michaung*') + glob.glob('/root/.claude/uploads/*/*michaung*'))[0]
txt = open(SRC).read()
sec = {}
for m in re.finditer(r'^\[(\w+)\]\s*$', txt, re.M): sec[m.group(1)] = m.start()
names = sorted(sec, key=sec.get)
def body(name):
    i = names.index(name); s = txt.index('\n', sec[name]) + 1; e = sec[names[i + 1]] if i + 1 < len(names) else len(txt)
    return txt[s:e]
def replace(name, new):
    global txt, sec, names
    i = names.index(name); s = txt.index('\n', sec[name]) + 1; e = sec[names[i + 1]] if i + 1 < len(names) else len(txt)
    txt = txt[:s] + new + '\n' + txt[e:]
    sec = {m.group(1): m.start() for m in re.finditer(r'^\[(\w+)\]\s*$', txt, re.M)}; names = sorted(sec, key=sec.get)

# rain
d = xr.open_dataset(rainf); P = d.precipitation.transpose('time', 'lat', 'lon').values * scale
_t = pd.to_datetime([str(v) for v in d.time.values]); _i0 = int(np.where(_t == pd.Timestamp('2023-12-03 21:00'))[0][0])
if rainmode == 'persist':  # Eulerian persistence nowcast issued at 21:00 UTC: last hour's mean rain held for 3 h
    P = P.copy(); P[_i0:] = P[_i0 - 2:_i0].mean(axis=0)
lats, lons = d.lat.values, d.lon.values
times = pd.to_datetime([str(v) for v in d.time.values])
start, end = pd.Timestamp('2023-12-03 12:00'), pd.Timestamp('2023-12-04 00:30')
sel = (times >= start - pd.Timedelta('30min')) & (times <= end)
ts, gauges = [], []
for a in range(len(lats)):
    for b in range(len(lons)):
        g = f'G{a}{b}'; gauges.append(f'{g:<8} INTENSITY 0:30 1.0 TIMESERIES R{a}{b}')
        for t, v in zip(times[sel], P[sel, a, b]):
            ts.append(f'R{a}{b} {t:%m/%d/%Y} {t:%H:%M} {v:.3f}')
replace('RAINGAGES', ';;Name Format Interval SCF Source\n' + '\n'.join(gauges))
replace('TIMESERIES', ';;Name Date Time Value\n' + '\n'.join(ts))

# coordinates -> nearest gauge per subcatchment outlet
co = {}
for ln in body('COORDINATES').splitlines():
    p = ln.split()
    if len(p) == 3 and not ln.startswith(';'): co[p[0]] = (float(p[1]), float(p[2]))
tr = Transformer.from_crs(32644, 4326, always_xy=True)
sub = []
for ln in body('SUBCATCHMENTS').splitlines():
    p = ln.split()
    if len(p) >= 8 and not ln.startswith(';'):
        x, y = co.get(p[2], (None, None))
        if x is None: g = 'G00'
        else:
            lo, la = tr.transform(x, y); g = f'G{int(np.argmin(abs(lats - la)))}{int(np.argmin(abs(lons - lo)))}'
        p[1] = g; sub.append(' '.join(p))
    else: sub.append(ln)
replace('SUBCATCHMENTS', '\n'.join(sub))

# ponding: junction ponded area 1500 m2
j = []
for ln in body('JUNCTIONS').splitlines():
    p = ln.split()
    if len(p) >= 6 and not ln.startswith(';'): p[5] = '1500'; j.append(' '.join(p))
    else: j.append(ln)
replace('JUNCTIONS', '\n'.join(j))
if outfall_stage > 0:  # river/marsh backwater: fixed stage above outfall invert
    o = []
    for ln in body('OUTFALLS').splitlines():
        p = ln.split()
        if len(p) >= 3 and not ln.startswith(';') and p[2] == 'FREE':
            o.append(f'{p[0]} {p[1]} FIXED {float(p[1]) + outfall_stage:.3f} NO')
        else: o.append(ln)
    replace('OUTFALLS', '\n'.join(o))

if blockc != '-':  # partial blockage: reduce open depth of one conduit to 20%
    xl = []
    for ln in body('XSECTIONS').splitlines():
        p = ln.split()
        if p and p[0] == blockc: p[2] = f'{float(p[2]) * 0.2:.3f}'; xl.append(' '.join(p))
        else: xl.append(ln)
    replace('XSECTIONS', '\n'.join(xl))
opts = body('OPTIONS')
for k, v in {'START_DATE': '12/03/2023', 'START_TIME': '12:00:00', 'REPORT_START_DATE': '12/03/2023', 'REPORT_START_TIME': '12:00:00',
             'END_DATE': '12/04/2023', 'END_TIME': '00:15:00', 'ALLOW_PONDING': 'NO', 'ROUTING_STEP': '0:00:30', 'REPORT_STEP': '00:15:00'}.items():
    if re.search(rf'^{k}\s', opts, re.M): opts = re.sub(rf'^{k}\s+.*$', f'{k:<20} {v}', opts, flags=re.M)
    else: opts += f'{k:<20} {v}\n'
replace('OPTIONS', opts)
inp = f'/home/claude/jd/swmm_{tag}.inp'; open(inp, 'w').write(txt)
t0 = time.time()
solver.swmm_run(inp, inp.replace('.inp', '.rpt'), inp.replace('.inp', '.out'))
print(tag, 'done in', round((time.time() - t0) / 60, 1), 'min', flush=True)
