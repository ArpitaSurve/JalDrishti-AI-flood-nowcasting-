"""Export pipeline outputs for dashboard + API into project/data."""
import json, gzip, re, numpy as np, networkx as nx
from pathlib import Path
from swmm.toolkit import output, shared_enum as se
OUT = Path('project/data'); OUT.mkdir(parents=True, exist_ok=True)
B = json.load(open('base3857.json')); NET = json.load(open('net3857.json'))
# ---------- MTC corridors between real depots/termini (sheet labels), main-road shortest paths
dep = B['fac']['depot']
G = nx.Graph(); W = {1: 1.0, 2: 1.0, 3: 1.2, 4: 2.0}
for k, (a, b, L, c) in enumerate(zip(B['e']['a'], B['e']['b'], B['e']['len'], B['e']['cls'])):
    if a != b and (not G.has_edge(a, b) or G[a][b]['w'] > L * W[c]): G.add_edge(a, b, w=L * W[c])
seen = set(); cor = []
FIX = {}
for q in dep:
    t = q['name']
    for k, v in {'T Nagan': 'T Nagar', 'Inina': '', 'KKNagar': 'KK Nagar', 'Vijayanagar Velachery': 'Velachery', 'IОC': 'IOC', 'ICF': 'ICF'}.items(): t = t.replace(k, v)
    t = re.sub(r'\s*(MTC|Bus)?\s*(Depot|Terminus|Mtc)\b.*$', '', t, flags=re.I).strip(' ,')
    t = t.strip(' ,-/'); FIX[q['name']] = t if len(t) > 2 and t.upper() not in ('MTC', 'IOC') else (t + ' depot' if t.upper() == 'IOC' else f"Depot, ward {q['ward']}")
for i, d in enumerate(dep):
    ds = sorted([(np.hypot(d['x'] - e['x'], d['y'] - e['y']), j) for j, e in enumerate(dep) if j != i])
    for dist, j in ds[:3]:
        if not (3000 < dist < 14000) or (min(i, j), max(i, j)) in seen: continue
        seen.add((min(i, j), max(i, j)))
        try: nx.shortest_path_length(G, d['g'], dep[j]['g'], weight='w')
        except nx.NetworkXNoPath: continue
        nm = lambda q: FIX.get(q['name'], None) or re.sub(r'\s*(MTC|Bus)?\s*(Depot|Terminus|Mtc)\b.*$', '', q['name'].replace('-/', ' ').replace('-', ' '), flags=re.I).strip() or f"Depot, ward {q['ward']}"
        name = f"{nm(d)} – {nm(dep[j])}"
        if name in {c['name'] for c in cor} or nm(d) == nm(dep[j]): continue
        cor.append({'name': name, 's': d['g'], 't': dep[j]['g']})
B['corridors'] = cor[:10]
print('corridors', [c['name'] for c in B['corridors']])
B['demo'] = json.load(open('demo.json')) if Path('demo.json').exists() else None
# ---------- grids
Gd = np.load('dem.npz'); nr, nc = Gd['dem'].shape
import pandas as pd
M = {'group': 'michaung', 't0': '2023-12-03T21:00:00'}
scen = [{'id': 'now', 'label': 'Nowcast', 'desc': 'Rain observed to issue time, then persistence nowcast (last hour held for 3 h)', **M},
        {'id': 'block', 'label': 'Culvert blocked', 'desc': 'Nowcast with drain W65_A2→A1 (1.9 × 1.75 m, ward 65) 80% blocked', **M},
        {'id': 'back', 'label': 'River backwater', 'desc': 'Nowcast with all 403 outfalls held 0.8 m above invert (rivers, marsh, tide in spate)', **M},
        {'id': 'obs', 'label': 'Hindsight', 'desc': 'Rain that actually fell after issue time (for checking the nowcast)', **M, 'name': 'Cyclone Michaung', 'when': '3–4 Dec 2023 · NASA IMERG rain'}]
H = np.load('om_hist.npz'); OT = pd.to_datetime(H['t'], unit='s'); OP = H['P']
EVENTS = [('e2021', '2021-11-11 03:00', 'Deep depression', '10–11 Nov 2021'), ('e2022', '2022-12-09 15:00', 'Cyclone Mandous', '9–10 Dec 2022'),
          ('e2024o', '2024-10-15 22:00', 'Northeast monsoon downpour', '15–16 Oct 2024'), ('e2024n', '2024-11-30 09:00', 'Cyclone Fengal', '30 Nov 2024'),
          ('e2025', '2025-12-01 11:00', 'Heavy rain spell', '1 Dec 2025')]
for eid, t0s, nm, when in EVENTS:
    if not Path(f'flood_{eid}.npz').exists(): continue
    T0 = pd.Timestamp(t0s); i0 = int(np.where(OT == T0)[0][0])
    r15 = np.repeat(OP[i0 - 12:i0 + 4], 4, axis=0)[:61]
    ser = OP[i0 - 36:i0 + 36].mean(axis=1)
    days = pd.Series(OP.mean(axis=1), index=OT)[T0 - pd.Timedelta('2D'):T0 + pd.Timedelta('2D')].resample('1D').sum()
    scen.append({'id': eid, 'label': nm, 'name': nm, 'when': when + ' · Open-Meteo rain', 'group': 'history', 't0': T0.isoformat(),
                 'desc': f'{nm}, {when}: hindsight replay of the rain that fell (Open-Meteo reanalysis, ×1.3) through the same SWMM + 2D model',
                 'rain12': int(round(OP[i0 - 9:i0 + 3].mean(axis=1).sum())),
                 'rain': {'r15': np.round(r15, 2).tolist(), 'spin': 48, 'series': np.round(ser, 2).tolist(), 'seriesT0': 36, 'step': 60,
                          'label': f'Rain over Chennai around {when} (Open-Meteo)', 'days': [[f'{d.day} {d:%b}', round(float(v), 0)] for d, v in days.items()], 'scale': 1.3}})
daily = pd.Series(OP.mean(axis=1), index=OT).resample('1D').sum()
drains = {}; frames = {}
names = NET['cond']['id']
for s in scen:
    D = np.load(f"flood_{s['id']}.npz")['depth']; frames[s['id']] = D
    (OUT / f"depth_{s['id']}.bin.gz").write_bytes(gzip.compress(D.tobytes(), 9))
    h = output.init(); output.open(h, f"swmm_{s['id']}.out")
    L = output.get_proj_size(h)[se.ElementType.LINK.value]; li = {output.get_elem_name(h, se.ElementType.LINK, i): i for i in range(L)}
    lm = np.array([li[n] for n in names])
    drains[s['id']] = [np.round(np.minimum(1, np.array(output.get_link_attribute(h, output.get_times(h, se.Time.NUM_PERIODS) - 14 + f, se.LinkAttribute.CAPACITY))[lm]) * 100).astype(int).tolist() for f in range(13)]
modelled = (Gd['surveyd'] | (frames['obs'].max(axis=0) > 0)) & ~Gd['sea']
(OUT / 'modelled.bin.gz').write_bytes(gzip.compress(modelled.astype(np.uint8).tobytes(), 9))
dem = np.clip(np.round((Gd['dem'] + 1) * 10), 0, 255).astype(np.uint8); (OUT / 'dem.bin.gz').write_bytes(gzip.compress(dem.tobytes(), 9))
# ---------- skill: nowcast vs hindsight (model-to-model)
skill = []
for f in range(13):
    a, o = frames['now'][f], frames['obs'][f]; row = {'lead': f * 15}
    for th in (15, 30):
        hit = int(((a > th) & (o > th)).sum()); miss = int(((a <= th) & (o > th)).sum()); fa = int(((a > th) & (o <= th)).sum())
        row[f'csi{th}'] = round(hit / max(1, hit + miss + fa), 2); row[f'pod{th}'] = round(hit / max(1, hit + miss), 2); row[f'far{th}'] = round(fa / max(1, hit + fa), 2)
    wet = (a > 5) | (o > 5); row['mae_cm'] = round(float(np.abs(a[wet].astype(int) - o[wet].astype(int)).mean()) if wet.any() else 0, 1)
    skill.append(row)
print('skill', [(r['lead'], r['csi15'], r['csi30'], r['mae_cm']) for r in skill])
for s_ in scen:
    s_['area180'] = round(float((frames[s_['id']][12] > 15).sum() * (Gd['cell'] * 0.9742) ** 2 / 1e6), 1)
grid = {'daily': {'start': '2021-01-01', 'mm': np.round(daily.values, 1).tolist()}, 'nc': int(nc), 'nr': int(nr), 'x0': float(Gd['x0']), 'y1': float(Gd['y1']), 'cell': float(Gd['cell']), 'scenarios': scen, 'drains': drains,
        'drainIds': names, 'drainWard': NET['nodes']['ward'] and [NET['nodes']['ward'][a] for a in NET['cond']['a']], 'skill': skill}
json.dump(grid, open(OUT / 'grid.json', 'w'), separators=(',', ':'))
json.dump(B, open(OUT / 'base.json', 'w'), separators=(',', ':'))
json.dump(NET, open(OUT / 'net.json', 'w'), separators=(',', ':'))
import os; print({p.name: os.path.getsize(p) // 1024 for p in OUT.iterdir()})
