"""Simplifica Web/static/spain-provinces.geojson (Douglas-Peucker + redondeo) para el coroplético en cliente.
Uso: python simplify_geojson.py <entrada.geojson> <salida.geojson> [tolerancia_grados=0.01] [decimales=3] [area_min_grados2=0.002]
Conserva solo cod_prov (código INE 2 dígitos) y name. No requiere shapely.
Nota: simplifica cada anillo de forma independiente (puede dejar micro-huecos entre provincias vecinas;
para topología compartida usar mapshaper: npx mapshaper in.geojson -simplify 8% keep-shapes -o out.json)."""
import json, sys

def rdp(pts, eps):
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5 or 1e-12
    dmax, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        x0, y0 = pts[i]
        d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / n
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return rdp(pts[:idx + 1], eps)[:-1] + rdp(pts[idx:], eps)
    return [pts[0], pts[-1]]

def ring(r, eps, nd):
    pts = [tuple(p[:2]) for p in r]
    if len(pts) > 4 and pts[0] == pts[-1]:  # anillo cerrado: partir en dos mitades para que RDP funcione
        m = len(pts) // 2
        s = rdp(pts[:m + 1], eps)[:-1] + rdp(pts[m:], eps)
    else:
        s = rdp(pts, eps)
    if len(s) < 4:  # anillo degenerado: conservar original reducido
        s = [tuple(p[:2]) for p in r][:: max(1, len(r) // 4)] + [tuple(r[0][:2])]
    return [[round(x, nd), round(y, nd)] for x, y in s]

def area(r):
    return abs(sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))) / 2

def main(src, dst, eps=0.01, nd=3, min_area=0.002):
    sys.setrecursionlimit(100000)
    g = json.load(open(src, encoding='utf-8'))
    feats = []
    for f in g['features']:
        geo = f['geometry']
        polys = [geo['coordinates']] if geo['type'] == 'Polygon' else geo['coordinates']
        # descartar islotes: polígonos con área < min_area (grados²), conservando siempre el mayor de cada provincia
        polys = sorted(polys, key=lambda pl: -area(pl[0]))
        polys = [pl for i, pl in enumerate(polys) if i == 0 or area(pl[0]) >= min_area]
        coords = [[ring(r, eps, nd) for r in poly] for poly in polys]
        geo = {'type': 'MultiPolygon'}
        p = f['properties']
        feats.append({'type': 'Feature', 'properties': {'cod_prov': str(p.get('cod_prov')).zfill(2), 'name': p.get('name')},
                      'geometry': {'type': geo['type'], 'coordinates': coords}})
    out = json.dumps({'type': 'FeatureCollection', 'features': feats}, separators=(',', ':'), ensure_ascii=False)
    open(dst, 'w', encoding='utf-8').write(out)
    print(f'{len(feats)} provincias, {len(out.encode())/1024:.0f} KB')

if __name__ == '__main__':
    a = sys.argv
    main(a[1], a[2], float(a[3]) if len(a) > 3 else 0.01, int(a[4]) if len(a) > 4 else 3, float(a[5]) if len(a) > 5 else 0.002)
