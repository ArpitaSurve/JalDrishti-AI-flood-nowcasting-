"""JalDrishti API: street-level flood nowcast for Chennai (0-3 h) and flood-safe routing for navigation apps.
Run: uvicorn api.main:app --host 0.0.0.0 --port 8000   (from the project folder)"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from .engine import Engine, VEH, band, p_exceed

app = FastAPI(title='JalDrishti API', version='1.0',
              description='0-3 h street-level flood nowcast for Chennai (EPA SWMM + 2D surface routing) and flood-safe routing.')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['GET'], allow_headers=['*'])
E = Engine()
ISSUE = datetime(2023, 12, 3, 21, 0, tzinfo=timezone.utc)  # replay issue time (T+0)
IST = timezone(timedelta(hours=5, minutes=30))
DASH = Path(__file__).resolve().parent.parent / 'dashboard' / 'index.html'


def t0_of(scenario):
    s = next((x for x in E.grid['scenarios'] if x['id'] == scenario), None)
    return datetime.fromisoformat(s['t0']).replace(tzinfo=timezone.utc) if s and s.get('t0') else ISSUE


def frame(t: int) -> int:
    if t < 0 or t > 180: raise HTTPException(400, 't must be 0-180 minutes')
    return round(t / 15)


def check(scenario, vehicle=None):
    if scenario not in E.edepth: raise HTTPException(400, f'scenario must be one of {list(E.edepth)}')
    if vehicle and vehicle not in VEH: raise HTTPException(400, f'vehicle must be one of {list(VEH)}')


@app.get('/', include_in_schema=False)
def dashboard():
    return FileResponse(DASH) if DASH.exists() else {'docs': '/docs'}


@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'replay', 'issued_utc': ISSUE.isoformat(), 'scenarios': list(E.edepth), 'roads': len(E.elen)}


@app.get('/scenarios')
def scenarios():
    return E.grid['scenarios']


@app.get('/nowcast/depth')
def depth(t: int = 60, scenario: str = 'now', min_cm: int = 5, bbox: str | None = Query(None, description='minLon,minLat,maxLon,maxLat')):
    """Forecast water depth per road segment (GeoJSON) at lead time t minutes."""
    check(scenario); f = frame(t); ED = E.edepth[scenario][f]
    box = None
    if bbox:
        a, b, c, d = map(float, bbox.split(',')); x0, y0 = E.from_ll(b, a); x1, y1 = E.from_ll(d, c); box = (x0, y0, x1, y1)
    feats = []
    for k in range(len(ED)):
        v = ED[k]
        if v < min_cm or not E.emod[k]: continue
        if box:
            p = E.pts[E.off[k]]
            if not (box[0] <= p[0] <= box[2] and box[1] <= p[1] <= box[3]): continue
        lo, hi = band(v, t)
        feats.append({'type': 'Feature', 'properties': {'road': E.name(k), 'depth_cm': round(v), 'low_cm': round(lo), 'high_cm': round(hi)},
                      'geometry': {'type': 'LineString', 'coordinates': E.edge_coords(k)}})
        if len(feats) >= 20000: break
    valid = (t0_of(scenario) + timedelta(minutes=t)).astimezone(IST).isoformat()
    return {'type': 'FeatureCollection', 'properties': {'valid_at': valid, 'scenario': scenario, 'lead_min': t}, 'features': feats}


@app.get('/point')
def point(lat: float, lon: float, scenario: str = 'now'):
    """3-hour depth forecast (15-min steps) for the road nearest to a location."""
    check(scenario); g, d = E.snap(lat, lon)
    if d > 400: raise HTTPException(404, 'no road within 400 m')
    series = []
    for f in range(13):
        v = max((E.edepth[scenario][f][k] for k in E.adj[g]), default=0); lo, hi = band(v, f * 15)
        series.append({'lead_min': f * 15, 'depth_cm': round(v), 'low_cm': round(lo), 'high_cm': round(hi)})
    return {'road': next((E.name(k) for k in E.adj[g] if E.name(k)), None), 'modelled': bool(any(E.emod[k] for k in E.adj[g])), 'series': series}


@app.get('/closures')
def closures(t: int = 0, vehicle: str = 'car', scenario: str = 'now'):
    """Road segments a vehicle should avoid at lead time t (probability of exceeding its depth limit > 50%)."""
    check(scenario, vehicle); f = frame(t); L = VEH[vehicle][1]; ED = E.edepth[scenario][f]
    feats = [{'type': 'Feature', 'properties': {'road': E.name(k), 'depth_cm': round(ED[k]), 'limit_cm': L, 'p_exceed': round(p_exceed(ED[k], t, L), 2)},
              'geometry': {'type': 'LineString', 'coordinates': E.edge_coords(k)}}
             for k in range(len(ED)) if E.emod[k] and p_exceed(ED[k], t, L) > 0.5]
    return {'type': 'FeatureCollection', 'properties': {'vehicle': vehicle, 'lead_min': t, 'scenario': scenario}, 'features': feats}


@app.get('/route')
def route(frm: str = Query(..., alias='from', description='lat,lon'), to: str = Query(..., description='lat,lon'),
          vehicle: str = 'amb', depart: int = 0, scenario: str = 'now'):
    """Flood-safe route that judges each road at the minute the vehicle reaches it, compared with a current-conditions route."""
    check(scenario, vehicle)
    if depart < 0 or depart > 180: raise HTTPException(400, 'depart must be 0-180')
    (a, b), (c, d) = map(float, frm.split(',')), map(float, to.split(','))
    s, ds = E.snap(a, b); t, dt = E.snap(c, d)
    if ds > 500 or dt > 500: raise HTTPException(404, 'start or end is more than 500 m from a road in the model area')
    fc = E.route(s, t, vehicle, depart, 'forecast', scenario); st = E.route(s, t, vehicle, depart, 'static', scenario)
    geo = lambda r: None if not r else {'type': 'MultiLineString', 'coordinates': [E.edge_coords(k) for k in r['edges']]}
    strip = lambda r: None if not r else {k: v for k, v in r.items() if k != 'edges'}
    return {'vehicle': VEH[vehicle][0], 'limit_cm': VEH[vehicle][1], 'depart_min': depart,
            'flood_safe': strip(fc), 'flood_safe_geometry': geo(fc), 'current_conditions': strip(st), 'current_conditions_geometry': geo(st),
            'google_maps_url': E.gmaps_url(fc, s, t, vehicle)}


@app.get('/drains/status')
def drains(t: int = 0, scenario: str = 'now', top: int = 50):
    """Storm drains ranked by load (% of capacity) at lead time t."""
    check(scenario); f = frame(t); D = E.grid['drains'][scenario][f]
    rows = sorted(range(len(D)), key=lambda k: -D[k])[:top]
    return [{'drain': E.grid['drainIds'][k], 'ward': E.grid['drainWard'][k], 'percent_full': D[k]} for k in rows]


@app.get('/alerts', response_class=Response)
def alerts(scenario: str = 'now'):
    """CAP 1.2 alerts (format used by NDMA SACHET) for subways forecast to exceed 15 cm."""
    check(scenario); out = []
    for s in E.fac['subway']:
        g = s['g']; fx = next((f for f in range(13) if max((E.edepth[scenario][f][k] for k in E.adj[g]), default=0) >= 15), None)
        if fx is None: continue
        on = (ISSUE + timedelta(minutes=fx * 15)).isoformat()
        out.append(f"""  <alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>JD-{scenario}-{s['name'].replace(' ', '')}</identifier><sender>jaldrishti</sender>
    <sent>{ISSUE.isoformat()}</sent><status>Exercise</status><msgType>Alert</msgType><scope>Restricted</scope>
    <info><category>Met</category><event>Subway flooding</event><urgency>Expected</urgency><severity>Severe</severity><certainty>Likely</certainty>
      <onset>{on}</onset><headline>Close {s['name']}: water above 15 cm expected at T+{fx * 15} min</headline><area><areaDesc>{s['name']}, ward {s['ward']}</areaDesc></area></info></alert>""")
    return Response('<alerts>\n' + '\n'.join(out) + '\n</alerts>', media_type='application/xml')


@app.get('/bus/diversions')
def bus(scenario: str = 'now'):
    """MTC corridors between depots/termini: forecast blockage for a bus (40 cm) and flood-safe diversion."""
    check(scenario); out = []
    for c in E.corridors:
        s, t = c['s'], c['t']; st = E.route(s, t, 'bus', 0, 'static', scenario); fc = E.route(s, t, 'bus', 0, 'forecast', scenario)
        status = 'suspend' if not st and not fc else 'divert' if st and st['hits'] and fc else 'suspend' if st and st['hits'] else 'normal'
        out.append({'corridor': c['name'], 'status': status, 'blocked_on_usual_path': bool(st and st['hits']), 'first_block': st['hits'][0] if st and st['hits'] else None,
                    'usual_eta_min': st and st['eta_min'], 'diversion_eta_min': fc and fc['eta_min'], 'diversion_available': fc is not None})
    return out


@app.get('/live/rain')
def live_rain():
    """Live 15-min rain for the Chennai grid (last 3 h + next 3 h) from Open-Meteo. The production loop (pipeline/live.py)
    feeds this into SWMM + 2D every 15 minutes."""
    import json, urllib.request
    lats = [12.85, 12.95, 13.05, 13.15, 13.25]; lons = [80.05, 80.15, 80.25, 80.35]
    LA = ','.join(str(a) for a in lats for _ in lons); LO = ','.join(str(b) for _ in lats for b in lons)
    url = f'https://api.open-meteo.com/v1/forecast?latitude={LA}&longitude={LO}&minutely_15=precipitation&past_minutely_15=12&forecast_minutely_15=12&timezone=GMT'
    try: js = json.load(urllib.request.urlopen(url, timeout=20))
    except Exception as e: raise HTTPException(502, f'rain feed unavailable: {e}')
    times = js[0]['minutely_15']['time']
    return {'source': 'Open-Meteo', 'unit': 'mm per 15 min', 'times_utc': times,
            'cells': [{'lat': p['latitude'], 'lon': p['longitude'], 'rain': p['minutely_15']['precipitation']} for p in js]}
