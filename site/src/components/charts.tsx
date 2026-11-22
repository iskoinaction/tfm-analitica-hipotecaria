import { useEffect, useMemo, useRef, useState } from 'react';
import { fmtNum } from '../lib/format';

export interface Pt { x: number; y: number | null; lo?: number | null; hi?: number | null }
export interface Series { name: string; color: string; points: Pt[]; dashed?: boolean; band?: boolean }

function useWidth<T extends HTMLElement>(initial = 640) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(initial);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

function niceTicks(min: number, max: number, n = 5): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) { min -= 1; max += 1; }
  const step0 = (max - min) / n;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) ?? step0;
  const out: number[] = [];
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}

export function Legend({ series }: { series: Series[] }) {
  if (series.length < 2) return null;
  return (
    <div className="chart-legend" aria-hidden="true">
      {series.map((s) => (
        <span key={s.name}>
          <span className={`chart-legend__swatch${s.dashed ? ' chart-legend__swatch--dashed' : ''}`} style={s.dashed ? { color: s.color } : { background: s.color }} />
          {s.name}
        </span>
      ))}
    </div>
  );
}

/** Gráfico de líneas SVG con bandas de intervalo, cruz de lectura y tooltip. Un solo eje Y. */
export function LineChart({ series, height = 300, xFormat, yFormat = (v) => fmtNum(v), yLabel, markerX, markerLabel, ariaLabel, zeroBaseline = false }: {
  series: Series[]; height?: number; xFormat: (x: number) => string; yFormat?: (v: number) => string; yLabel?: string;
  markerX?: number; markerLabel?: string; ariaLabel: string; zeroBaseline?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const m = { t: 12, r: 16, b: 30, l: width < 420 ? 44 : 56 };
  const xs = useMemo(() => [...new Set(series.flatMap((s) => s.points.filter((p) => p.y != null).map((p) => p.x)))].sort((a, b) => a - b), [series]);
  const ys = series.flatMap((s) => s.points.flatMap((p) => [p.y, p.lo, p.hi])).filter((v): v is number => v != null && Number.isFinite(v));
  if (!xs.length || !ys.length) return <p className="muted small">Sin datos para representar.</p>;
  let yMin = Math.min(...ys), yMax = Math.max(...ys);
  if (zeroBaseline) yMin = Math.min(0, yMin);
  const pad = (yMax - yMin) * 0.06 || 1;
  const yt = niceTicks(yMin - (zeroBaseline && yMin === 0 ? 0 : pad), yMax + pad, height < 240 ? 4 : 5);
  const y0 = Math.min(yt[0], yMin), y1 = Math.max(yt[yt.length - 1], yMax);
  const x0 = xs[0], x1 = xs[xs.length - 1] === x0 ? x0 + 1 : xs[xs.length - 1];
  const X = (x: number) => m.l + ((x - x0) / (x1 - x0)) * (width - m.l - m.r);
  const Y = (y: number) => m.t + (1 - (y - y0) / (y1 - y0)) * (height - m.t - m.b);
  const nXT = Math.max(2, Math.floor((width - m.l - m.r) / 90));
  const xt = xs.filter((_, i) => i % Math.ceil(xs.length / nXT) === 0);
  const path = (pts: Pt[]) => {
    let d = '', pen = false;
    for (const p of pts) { if (p.y == null) { pen = false; continue; } d += `${pen ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`; pen = true; }
    return d;
  };
  const band = (pts: Pt[]) => {
    const b = pts.filter((p) => p.lo != null && p.hi != null);
    if (b.length < 2) return '';
    return `M${b.map((p) => `${X(p.x).toFixed(1)},${Y(p.hi!).toFixed(1)}`).join('L')}L${[...b].reverse().map((p) => `${X(p.x).toFixed(1)},${Y(p.lo!).toFixed(1)}`).join('L')}Z`;
  };
  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * width;
    let best = xs[0];
    for (const x of xs) if (Math.abs(X(x) - px) < Math.abs(X(best) - px)) best = x;
    setHover(best);
  };
  const hv = hover != null ? series.map((s) => ({ s, p: s.points.find((p) => p.x === hover) })).filter((o) => o.p && o.p.y != null) : [];
  return (
    <div ref={ref} className="map-wrap">
      <Legend series={series} />
      <svg className="chart-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={ariaLabel} onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        <g className="grid">{yt.map((t) => <line key={t} x1={m.l} x2={width - m.r} y1={Y(t)} y2={Y(t)} />)}</g>
        {yt.map((t) => <text key={t} x={m.l - 8} y={Y(t)} dy="0.32em" textAnchor="end">{yFormat(t)}</text>)}
        {xt.map((x) => <text key={x} x={X(x)} y={height - 8} textAnchor="middle">{xFormat(x)}</text>)}
        <line className="axis-line" x1={m.l} x2={width - m.r} y1={height - m.b} y2={height - m.b} />
        {yLabel && <text x={m.l} y={m.t - 2} dy="-0.2em" style={{ fontSize: 11 }}>{yLabel}</text>}
        {markerX != null && markerX >= x0 && markerX <= x1 && (
          <g><line className="today" x1={X(markerX)} x2={X(markerX)} y1={m.t} y2={height - m.b} />
            {markerLabel && <text x={X(markerX) + 4} y={m.t + 10} style={{ fontSize: 11 }}>{markerLabel}</text>}</g>
        )}
        {series.map((s) => s.band !== false && <path key={s.name + 'b'} d={band(s.points)} fill={s.color} opacity={0.16} />)}
        {series.map((s) => <path key={s.name} d={path(s.points)} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? '6 4' : undefined} strokeLinejoin="round" strokeLinecap="round" />)}
        {hover != null && <line className="crosshair" x1={X(hover)} x2={X(hover)} y1={m.t} y2={height - m.b} />}
        {hv.map(({ s, p }) => <circle key={s.name} cx={X(p!.x)} cy={Y(p!.y!)} r={4} fill={s.color} stroke="var(--surface-1)" strokeWidth={2} />)}
      </svg>
      {hover != null && hv.length > 0 && (
        <div className="tooltip chart-tooltip" style={{ left: Math.min(X(hover) + 12, width - 190), top: 28 }}>
          <strong>{xFormat(hover)}</strong>
          {hv.map(({ s, p }) => (
            <div key={s.name} className="row" style={{ gap: 6 }}>
              <span className="status-dot" style={{ background: s.color }} />{s.name}: <span className="num">{yFormat(p!.y!)}</span>
              {p!.lo != null && p!.hi != null && <span className="muted num">[{yFormat(p!.lo!)} – {yFormat(p!.hi!)}]</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Barras horizontales con intervalo opcional (bigotes). */
export function BarChart({ rows, format = (v) => fmtNum(v), color = 'var(--series-1)', ariaLabel, unit }: {
  rows: { label: string; value: number; lo?: number; hi?: number; highlight?: boolean }[]; format?: (v: number) => string; color?: string; ariaLabel: string; unit?: string;
}) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const labelW = Math.min(170, Math.max(90, width * 0.32));
  const rowH = 28, h = rows.length * rowH + 8;
  const max = Math.max(...rows.map((r) => Math.max(r.value, r.hi ?? r.value)), 0) || 1;
  const min = Math.min(0, ...rows.map((r) => Math.min(r.value, r.lo ?? r.value)));
  const valW = 64;
  const X = (v: number) => labelW + ((v - min) / (max - min)) * (width - labelW - valW - 8);
  return (
    <div ref={ref}>
      <svg className="chart-svg" viewBox={`0 0 ${width} ${h}`} role="img" aria-label={ariaLabel}>
        {rows.map((r, i) => {
          const y = i * rowH + 4;
          return (
            <g key={r.label}>
              <title>{`${r.label}: ${format(r.value)}${unit ? ' ' + unit : ''}${r.lo != null ? ` [${format(r.lo)} – ${format(r.hi!)}]` : ''}`}</title>
              <text x={labelW - 8} y={y + rowH / 2 - 2} dy="0.32em" textAnchor="end" style={{ fill: 'var(--text-secondary)' }}>{r.label.length > 24 ? r.label.slice(0, 23) + '…' : r.label}</text>
              <rect x={X(Math.min(0, r.value))} y={y + 4} width={Math.max(1, Math.abs(X(r.value) - X(0)))} height={rowH - 12} rx={3} fill={r.highlight ? 'var(--series-2)' : color} />
              {r.lo != null && r.hi != null && (
                <g stroke="var(--text-primary)" strokeWidth={1.4}>
                  <line x1={X(r.lo)} x2={X(r.hi)} y1={y + rowH / 2 - 2} y2={y + rowH / 2 - 2} />
                  <line x1={X(r.lo)} x2={X(r.lo)} y1={y + 8} y2={y + rowH - 12} />
                  <line x1={X(r.hi)} x2={X(r.hi)} y1={y + 8} y2={y + rowH - 12} />
                </g>
              )}
              <text x={width - valW + 4} y={y + rowH / 2 - 2} dy="0.32em" style={{ fill: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>{format(r.value)}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
