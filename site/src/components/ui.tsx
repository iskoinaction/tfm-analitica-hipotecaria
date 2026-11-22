import { ReactNode, useEffect, useRef, useState } from 'react';
import type { Manifest, Table } from '../lib/data';
import { fmtCell, fmtDate } from '../lib/format';

export function Logo({ size = 28 }: { size?: number }) {
  // Atalaya: torre de vigía estilizada (marca ficticia)
  return (
    <svg className="brand__mark" width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="var(--brand-ink)" />
      <path d="M11 25h10l-2-12h-6z" fill="var(--brand-accent)" />
      <path d="M10 13h12l-1.5-3h-9z" fill="var(--surface-1)" opacity=".92" />
      <path d="M16 4l5 5H11z" fill="var(--surface-1)" />
      <circle cx="16" cy="18" r="1.6" fill="var(--brand-ink)" />
    </svg>
  );
}

export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!('IntersectionObserver' in window)) { el.classList.add('is-visible'); return; }
    const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add('is-visible'); io.unobserve(e.target); } }), { rootMargin: '0px 0px -8% 0px' });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  return ref;
}

export function Section({ id, num, kicker, title, lead, children }: { id: string; num: number; kicker: string; title: string; lead?: ReactNode; children: ReactNode }) {
  const ref = useReveal<HTMLDivElement>();
  return (
    <section id={id} className="section" aria-labelledby={`${id}-t`}>
      <div ref={ref} className="reveal">
        <div className="section__kicker"><span className="mono">{String(num).padStart(2, '0')}</span><span aria-hidden="true">·</span>{kicker}</div>
        <h2 id={`${id}-t`} className="section__title">{title}</h2>
        {lead && <p className="section__lead">{lead}</p>}
        <div className="stack">{children}</div>
      </div>
    </section>
  );
}

export function Card({ title, subtitle, actions, children, source, className = '' }: { title?: ReactNode; subtitle?: ReactNode; actions?: ReactNode; children: ReactNode; source?: ReactNode; className?: string }) {
  return (
    <div className={`card ${className}`}>
      {(title || actions) && (
        <div className="card__header">
          <div>{title && <h3 className="card__title">{title}</h3>}{subtitle && <p className="card__subtitle">{subtitle}</p>}</div>
          {actions}
        </div>
      )}
      {children}
      {source && <div className="card__source">{source}</div>}
    </div>
  );
}

export function Pending({ what, expected, note }: { what: string; expected: string[]; note?: string }) {
  return (
    <div className="pending" role="status">
      <div className="pending__title"><span className="badge badge--neutral"><span aria-hidden="true">◌</span> Pendiente de generar</span>{what}</div>
      <p>Esta sección se completa automáticamente cuando el pipeline publique: {expected.map((e, i) => <span key={e}>{i > 0 && ', '}<code>{e}</code></span>)}. No se muestran cifras provisionales ni inventadas.</p>
      {note && <p className="xs">{note}</p>}
    </div>
  );
}

export function SourceLine({ manifest, slots, extra }: { manifest?: Manifest; slots: string[]; extra?: ReactNode }) {
  const srcs = slots.flatMap((k) => manifest?.slots[k]?.status === 'ok' ? manifest.slots[k].sources.slice(0, 4) : []);
  const upd = slots.map((k) => manifest?.slots[k]?.updated).filter(Boolean).sort().at(-1);
  if (!srcs.length && !extra) return null;
  return (
    <span>
      {srcs.length > 0 && <>Fuente: {srcs.map((s, i) => <span key={s}>{i > 0 && ' · '}<code>{s}</code></span>)}</>}
      {upd && <> · Generado: {fmtDate(upd, true)}</>}
      {extra && <> · {extra}</>}
    </span>
  );
}

export function Kpi({ label, value, unit, period, delta }: { label: string; value: ReactNode; unit?: string; period?: ReactNode; delta?: ReactNode }) {
  return (
    <div className="card kpi">
      <span className="kpi__label">{label}</span>
      <span className="kpi__value num">{value}{unit && <span className="kpi__unit">{unit}</span>}</span>
      {delta && <span className="kpi__delta">{delta}</span>}
      {period && <span className="kpi__period">{period}</span>}
    </div>
  );
}

export function DataTable({ table, caption, maxRows = 200, numericCols, highlight, format }: {
  table: Table; caption?: ReactNode; maxRows?: number; numericCols?: Set<number>; highlight?: (row: Table['rows'][number]) => boolean;
  format?: (v: unknown, col: string) => string;
}) {
  const [all, setAll] = useState(false);
  const rows = all ? table.rows : table.rows.slice(0, maxRows);
  const isNum = (i: number) => numericCols?.has(i) ?? table.rows.slice(0, 20).some((r) => typeof r[i] === 'number');
  return (
    <div>
      <div className="table-wrap" tabIndex={0} role="region" aria-label={typeof caption === 'string' ? caption : 'Tabla de datos'}>
        <table className="table table--compact">
          {caption && <caption>{caption}</caption>}
          <thead><tr>{table.columns.map((c, i) => <th key={c + i} scope="col" className={isNum(i) ? 'num' : ''}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, j) => (
              <tr key={j} className={highlight?.(r) ? 'is-best' : ''}>
                {r.map((v, i) => <td key={i} className={typeof v === 'number' ? 'num' : ''}>{format ? format(v, table.columns[i]) : fmtCell(v)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {table.rows.length > maxRows && (
        <button className="btn btn--ghost mt-2" onClick={() => setAll(!all)}>{all ? 'Mostrar menos' : `Mostrar las ${table.rows.length} filas`}</button>
      )}
      {table.truncated && <p className="xs muted mt-2">Tabla truncada en la sincronización ({table.n_rows} filas en origen).</p>}
    </div>
  );
}

/** Visor genérico de JSON: objetos → lista clave/valor; arrays de objetos → tabla. */
export function JsonView({ data, depth = 0, maxDepth = 3 }: { data: unknown; depth?: number; maxDepth?: number }) {
  if (data == null || typeof data !== 'object') return <span>{fmtCell(data)}</span>;
  if (Array.isArray(data)) {
    if (data.length && data.every((x) => x && typeof x === 'object' && !Array.isArray(x))) {
      const cols = [...new Set(data.flatMap((x) => Object.keys(x as object)))];
      return <DataTable maxRows={25} table={{ columns: cols, rows: data.map((r) => cols.map((c) => { const v = (r as Record<string, unknown>)[c]; return v != null && typeof v === 'object' ? JSON.stringify(v) : (v as never); })) }} />;
    }
    return <span className="num">{data.map((x) => (typeof x === 'object' ? JSON.stringify(x) : fmtCell(x))).join(' · ')}</span>;
  }
  const entries = Object.entries(data as Record<string, unknown>);
  if (depth >= maxDepth) return <code>{JSON.stringify(data).slice(0, 300)}</code>;
  const simple = entries.filter(([, v]) => v == null || typeof v !== 'object' || (Array.isArray(v) && v.every((x) => typeof x !== 'object')));
  const nested = entries.filter((e) => !simple.includes(e));
  return (
    <div className="json-view">
      {simple.length > 0 && <dl className="kv">{simple.map(([k, v]) => <FragmentKV key={k} k={k} v={v} />)}</dl>}
      {nested.map(([k, v]) => (
        <details key={k} open={depth === 0 && nested.length <= 2}>
          <summary>{k}</summary>
          <JsonView data={v} depth={depth + 1} maxDepth={maxDepth} />
        </details>
      ))}
    </div>
  );
}
function FragmentKV({ k, v }: { k: string; v: unknown }) {
  return (<><dt>{k}</dt><dd>{Array.isArray(v) ? v.map((x) => fmtCell(x)).join(' · ') : fmtCell(v)}</dd></>);
}

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.id} role="tab" className="tab" aria-selected={value === t.id} tabIndex={value === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => {
            const i = tabs.findIndex((x) => x.id === value);
            if (e.key === 'ArrowRight') onChange(tabs[(i + 1) % tabs.length].id);
            if (e.key === 'ArrowLeft') onChange(tabs[(i - 1 + tabs.length) % tabs.length].id);
          }}>{t.label}</button>
      ))}
    </div>
  );
}

export function Loading({ label = 'Cargando datos…' }: { label?: string }) {
  return <div className="skeleton" role="status" aria-live="polite"><span className="visually-hidden">{label}</span></div>;
}
export function ErrorBox({ msg }: { msg: string }) {
  return <div className="callout callout--crit" role="alert">No se pudo cargar el recurso: <code>{msg}</code></div>;
}

export function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: ReactNode; error?: string; children: ReactNode }) {
  return (
    <div className="field">
      <label className="field__label" htmlFor={id}>{label}</label>
      {children}
      {hint && <span className="field__hint" id={`${id}-hint`}>{hint}</span>}
      {error && <span className="field__error" id={`${id}-err`} role="alert"><span aria-hidden="true">⚠</span>{error}</span>}
    </div>
  );
}
