"""Build a Michaung SWMM run from the reclaimchennai model: per-cell IMERG gauges, ponding on, 24 h window."""
import re, sys, glob, time, numpy as np, pandas as pd
from pyproj import Transformer
from swmm.toolkit import solver

scale = 1.3
tag = sys.argv[1]; blockc = '-'; outfall_stage = 0.0
import os as _o
SRC = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), 'swd_model.inp')
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

# rain: Open-Meteo archive hourly per grid cell (x1.3, same correction as IMERG runs)
import os
H = np.load(os.environ.get('RAIN', 'om_hist.npz')); OT = pd.to_datetime(H['t'], unit='s'); OP = H['P'] * float(os.environ.get('RSCALE', scale))
STEPS = int(H['step']) if 'step' in H.files else 3600
T0 = pd.Timestamp(sys.argv[2]); start = T0 - pd.Timedelta('6h'); end = T0 + pd.Timedelta('3h30min')
sel = (OT >= start - pd.Timedelta('1h')) & (OT <= end)
lats = np.array([12.85, 12.95, 13.05, 13.15, 13.25]); lons = np.array([80.05, 80.15, 80.25, 80.35])
ts, gauges = [], []
for a_ in range(5):
    for b_ in range(4):
        g = f'G{a_}{b_}'; gauges.append(f'{g:<8} INTENSITY {STEPS // 3600}:{STEPS % 3600 // 60:02d} 1.0 TIMESERIES R{a_}{b_}')
        for t, v in zip(OT[sel], OP[sel, a_ * 4 + b_]):
            ts.append(f'R{a_}{b_} {t:%m/%d/%Y} {t:%H:%M} {v:.3f}')
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
_e = T0 + pd.Timedelta('3h15min')
for k, v in {'START_DATE': f'{start:%m/%d/%Y}', 'START_TIME': f'{start:%H:%M:%S}', 'REPORT_START_DATE': f'{start:%m/%d/%Y}', 'REPORT_START_TIME': f'{start:%H:%M:%S}',
             'END_DATE': f'{_e:%m/%d/%Y}', 'END_TIME': f'{_e:%H:%M:%S}', 'ALLOW_PONDING': 'NO', 'ROUTING_STEP': '0:01:00', 'REPORT_STEP': '00:15:00'}.items():
    if re.search(rf'^{k}\s', opts, re.M): opts = re.sub(rf'^{k}\s+.*$', f'{k:<20} {v}', opts, flags=re.M)
    else: opts += f'{k:<20} {v}\n'
replace('OPTIONS', opts)
inp = _o.path.join(_o.path.dirname(_o.path.abspath(__file__)), f'swmm_{tag}.inp'); open(inp, 'w').write(txt)
t0 = time.time()
solver.swmm_run(inp, inp.replace('.inp', '.rpt'), inp.replace('.inp', '.out'))
print(tag, 'done in', round((time.time() - t0) / 60, 1), 'min', flush=True)
