"""Shared forecast engine: loads pipeline outputs, computes road depths, uncertainty, time-dependent routing."""
import json, gzip, heapq, math
from pathlib import Path
import numpy as np

DATA = Path(__file__).resolve().parent.parent / 'data'
R_EARTH = 6378137.0
VEH = {'ped': ('Walking', 10, 4.5), 'two': ('Two-wheeler', 15, 20), 'auto': ('Auto-rickshaw', 20, 18),
       'car': ('Car', 25, 20), 'amb': ('Ambulance', 30, 26), 'bus': ('MTC bus', 40, 15)}
CLS_SPEED = [0, 1.25, 1.1, 1.0, 0.8]


def band(d, lead):
    h = lead / 60
    return d * max(0.35, 0.8 - 0.15 * h), d * (1.25 + 0.25 * h) + (2 if d > 1 else 0)


def p_exceed(d, lead, L):
    if d <= 0.5: return 0.0
    lo, hi = band(d, lead)
    if L <= lo: return 1.0
    if L >= hi: return 0.0
    return (hi - L) / (hi - lo)


class Engine:
    def __init__(self):
        B = json.loads((DATA / 'base.json').read_text())
        self.B = B; self.OX, self.OY = B['OX'], B['OY']
        self.gx = np.array(B['g']['x'], float); self.gy = np.array(B['g']['y'], float)
        e = B['e']; self.ea = np.array(e['a']); self.eb = np.array(e['b']); self.elen = np.array(e['len'], float); self.ecls = np.array(e['cls'])
        self.ename = e['name']; self.names = B['names']
        off = np.array(e['off']); geo = np.array(e['geo']).reshape(-1, 2)
        self.off = off; pts = np.zeros_like(geo)
        for k in range(len(off) - 1):
            pts[off[k]:off[k + 1]] = np.cumsum(geo[off[k]:off[k + 1]], axis=0)
        self.pts = pts.astype(float)
        G = json.loads((DATA / 'grid.json').read_text())
        self.grid = G; self.nc, self.nr, self.x0, self.y1, self.cell = G['nc'], G['nr'], G['x0'], G['y1'], G['cell']
        self.scen = {}
        for s in G['scenarios']:
            raw = np.frombuffer(gzip.decompress((DATA / f"depth_{s['id']}.bin.gz").read_bytes()), np.uint8).reshape(13, self.nr, self.nc)
            self.scen[s['id']] = raw
        for s in G['scenarios']:
            p = DATA / f"drains_{s['id']}.bin.gz"
            if p.exists(): G['drains'][s['id']] = np.frombuffer(gzip.decompress(p.read_bytes()), np.uint8).reshape(13, -1).tolist()
        self.modelled = np.frombuffer(gzip.decompress((DATA / 'modelled.bin.gz').read_bytes()), np.uint8).reshape(self.nr, self.nc)
        # sample cells per edge (20/50/80 % along)
        cells = []
        for k in range(len(off) - 1):
            g = self.pts[off[k]:off[k + 1]]; seg = np.hypot(*np.diff(g, axis=0).T); cum = np.r_[0, np.cumsum(seg)]; tot = cum[-1] or 1
            cs = set()
            for f in (0.2, 0.5, 0.8):
                j = min(max(int(np.searchsorted(cum, f * tot)), 1), len(g) - 1)
                t = (f * tot - cum[j - 1]) / max(cum[j] - cum[j - 1], 1e-6); p = g[j - 1] + t * (g[j] - g[j - 1])
                c = int((p[0] - self.x0) // self.cell); r = int((self.y1 - p[1]) // self.cell)
                if 0 <= r < self.nr and 0 <= c < self.nc: cs.add(r * self.nc + c)
            cells.append(sorted(cs))
        self.ecells = cells
        self.emod = np.array([any(self.modelled.flat[c] for c in cs) for cs in cells])
        EC = np.full((len(cells), 3), -1, np.int64)
        for k, cs in enumerate(cells): EC[k, :len(cs)] = cs
        valid = EC >= 0; ECc = np.where(valid, EC, 0)
        self.edepth = {}
        for sid, D in self.scen.items():
            flat = D.reshape(13, -1).astype(float)
            self.edepth[sid] = np.where(valid[None], flat[:, ECc], 0).max(axis=2)
        # adjacency
        self.adj = [[] for _ in range(len(self.gx))]
        for k, (a, b) in enumerate(zip(self.ea, self.eb)): self.adj[a].append(k); self.adj[b].append(k)
        from scipy.spatial import cKDTree
        self.tree = cKDTree(np.c_[self.gx, self.gy])
        self.fac = B['fac']; self.corridors = B.get('corridors', [])

    # --- geo helpers
    def to_ll(self, x, y):
        X, Y = x + self.OX, y + self.OY
        return round(math.degrees(X / R_EARTH), 6), round(math.degrees(2 * math.atan(math.exp(Y / R_EARTH)) - math.pi / 2), 6)

    def from_ll(self, lat, lon):
        X = math.radians(lon) * R_EARTH; Y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * R_EARTH
        return X - self.OX, Y - self.OY

    def snap(self, lat, lon):
        x, y = self.from_ll(lat, lon); d, i = self.tree.query([x, y]); return int(i), float(d)

    def edge_coords(self, k):
        return [list(self.to_ll(*p)) for p in self.pts[self.off[k]:self.off[k + 1]]]

    def name(self, k):
        n = self.ename[k]; return self.names[n] if n >= 0 else None

    # --- routing
    def route(self, s, t, veh='amb', dep=0, mode='forecast', scen='now', pmax=0.3):
        _, L, kmh = VEH[veh]; mpm = kmh * 1000 / 60; ED = self.edepth[scen]
        dist = {s: dep}; prev = {}; pq = [(dep, s)]
        while pq:
            tm, u = heapq.heappop(pq)
            if tm > dist.get(u, 1e18): continue
            if u == t: break
            for k in self.adj[u]:
                v = self.eb[k] if self.ea[k] == u else self.ea[k]
                arr = tm + self.elen[k] / (mpm * CLS_SPEED[self.ecls[k]]) * (1 if self.emod[k] else 1.15)
                f = min(12, round((dep if mode == 'static' else arr) / 15))
                if p_exceed(ED[f][k], 0 if mode == 'static' else arr, L) > pmax: continue
                if arr < dist.get(v, 1e18): dist[v] = arr; prev[v] = k; heapq.heappush(pq, (arr, v))
        if t not in dist: return None
        es = []; v = t
        while v != s: k = prev[v]; es.append(k); v = self.eb[k] if self.ea[k] == v else self.ea[k]
        es.reverse(); tt = dep; km = 0; hits = []; worst = (0, None, dep)
        for k in es:
            tt += self.elen[k] / (mpm * CLS_SPEED[self.ecls[k]]); km += self.elen[k] / 1000
            f = min(12, round(tt / 15)); d = ED[f][k]
            if d > worst[0]: worst = (d, k, tt)
            if p_exceed(d, tt, L) > 0.5: hits.append({'road': self.name(k), 'minute': round(tt, 1), 'depth_cm': round(d)})
        return {'edges': es, 'km': round(km, 2), 'eta_min': round(tt - dep, 1), 'hits': hits, 'worst_cm': round(worst[0])}

    def gmaps_url(self, r, s, t, veh, n=8):
        if not r: return None
        tot = r['km'] * 1000; acc = 0; k = 1; wps = []
        for e in r['edges']:
            acc += self.elen[e]
            while k <= n and acc >= tot * k / (n + 1):
                p = self.pts[(self.off[e] + self.off[e + 1]) // 2]; lo, la = self.to_ll(*p); wps.append(f'{la},{lo}'); k += 1
        o = self.to_ll(self.gx[s], self.gy[s]); d = self.to_ll(self.gx[t], self.gy[t])
        from urllib.parse import quote
        return (f'https://www.google.com/maps/dir/?api=1&origin={o[1]},{o[0]}&destination={d[1]},{d[0]}'
                f'&waypoints={quote("|".join(wps))}&travelmode={"walking" if veh == "ped" else "driving"}')
