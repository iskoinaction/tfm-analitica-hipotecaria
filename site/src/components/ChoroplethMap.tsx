import { useMemo, useState } from 'react';
import { geoConicConformal, geoMercator, geoPath, type GeoPermissibleObjects } from 'd3-geo';
import { fmtNum } from '../lib/format';

export interface GeoFeature { type: 'Feature'; properties: { prov_code: string; name: string }; geometry: GeoPermissibleObjects & { type: string; coordinates: unknown } }
export interface GeoFC { type: 'FeatureCollection'; features: GeoFeature[] }

const CLASSES = ['var(--seq-200)', 'var(--seq-300)', 'var(--seq-400)', 'var(--seq-500)', 'var(--seq-700)'];
const CANARIAS = new Set(['35', '38']);
const W = 640, H = 500;

function quantileBreaks(values: number[], k = 5): number[] {
  const v = [...values].sort((a, b) => a - b);
  if (!v.length) return [];
  return Array.from({ length: k - 1 }, (_, i) => v[Math.floor(((i + 1) / k) * (v.length - 1))]);
}

export function ChoroplethMap({ geo, values, label, format = (v) => fmtNum(v), names }: {
  geo: GeoFC; values: Record<string, number | undefined>; label: string; format?: (v: number) => string; names?: Record<string, string>;
}) {
  const [hover, setHover] = useState<{ code: string; x: number; y: number } | null>(null);
  const { paths, inset } = useMemo(() => {
    const main = { type: 'FeatureCollection', features: geo.features.filter((f) => !CANARIAS.has(f.properties.prov_code)) } as unknown as GeoPermissibleObjects;
    const can = { type: 'FeatureCollection', features: geo.features.filter((f) => CANARIAS.has(f.properties.prov_code)) } as unknown as GeoPermissibleObjects;
    const pMain = geoConicConformal().rotate([3.7, 0]).parallels([36, 43]).fitExtent([[150, 10], [W - 10, H - 10]], main);
    const insetBox = { x: 8, y: H - 130, w: 200, h: 120 };
    const pCan = geoMercator().fitExtent([[insetBox.x + 8, insetBox.y + 8], [insetBox.x + insetBox.w - 8, insetBox.y + insetBox.h - 8]], can);
    const gm = geoPath(pMain), gc = geoPath(pCan);
    return {
      paths: geo.features.map((f) => ({ code: f.properties.prov_code, name: f.properties.name, d: (CANARIAS.has(f.properties.prov_code) ? gc : gm)(f as unknown as GeoPermissibleObjects) ?? '' })),
      inset: insetBox,
    };
  }, [geo]);
  const vals = Object.values(values).filter((v): v is number => v != null && Number.isFinite(v));
  const breaks = quantileBreaks(vals);
  const color = (v: number | undefined) => {
    if (v == null || !Number.isFinite(v)) return 'url(#hatch-nodata)';
    let i = 0; while (i < breaks.length && v > breaks[i]) i++;
    return CLASSES[i];
  };
  const min = vals.length ? Math.min(...vals) : NaN, max = vals.length ? Math.max(...vals) : NaN;
  const edges = [min, ...breaks, max];
  const hv = hover ? values[hover.code] : undefined;
  return (
    <div className="map-wrap">
      <svg className="map-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Mapa coroplético provincial: ${label}`}
        onPointerLeave={() => setHover(null)}>
        <defs>
          <pattern id="hatch-nodata" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="var(--map-nodata)" /><line x1="0" y1="0" x2="0" y2="6" stroke="var(--border-control)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect className="map-inset" x={inset.x} y={inset.y} width={inset.w} height={inset.h} rx={6} />
        <text x={inset.x + 8} y={inset.y - 6} style={{ fill: 'var(--text-muted)', fontSize: 11 }}>Canarias (escala distinta)</text>
        {paths.map((p) => (
          <path key={p.code} d={p.d} fill={color(values[p.code])}
            onPointerMove={(e) => {
              const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
              setHover({ code: p.code, x: e.clientX - r.left, y: e.clientY - r.top });
            }}>
            <title>{`${names?.[p.code] ?? p.name}: ${values[p.code] != null ? format(values[p.code]!) : 'sin dato'}`}</title>
          </path>
        ))}
      </svg>
      {hover && (
        <div className="tooltip chart-tooltip" style={{ left: Math.min(hover.x + 12, 9999), top: hover.y + 12, transform: hover.x > 260 ? 'translateX(-110%)' : undefined }}>
          <strong>{names?.[hover.code] ?? paths.find((p) => p.code === hover.code)?.name}</strong>
          <div className="num">{hv != null ? format(hv) : 'sin dato'}</div>
        </div>
      )}
      {vals.length > 0 && (
        <div className="legend-scale" aria-label="Leyenda por quintiles">
          {CLASSES.map((c, i) => (
            <span key={c}><i style={{ background: c }} />{format(edges[i])} – {format(edges[i + 1])}</span>
          ))}
          <span><i style={{ background: 'var(--map-nodata)', outline: '1px solid var(--border-control)' }} />sin dato</span>
        </div>
      )}
    </div>
  );
}
