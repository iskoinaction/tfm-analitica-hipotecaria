const nf = (d: number) => new Intl.NumberFormat('es-ES', { minimumFractionDigits: d, maximumFractionDigits: d });
const cacheNF = new Map<number, Intl.NumberFormat>();
function getNF(d: number) { if (!cacheNF.has(d)) cacheNF.set(d, nf(d)); return cacheNF.get(d)!; }

export function fmtNum(v: number | null | undefined, digits?: number): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const d = digits ?? (Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 100 ? 1 : Math.abs(v) >= 1 ? 2 : 3);
  return getNF(d).format(v);
}
export const fmtEUR = (v: number | null | undefined, d = 0) => (v == null || !Number.isFinite(v) ? '—' : `${getNF(d).format(v)} €`);
export const fmtPct = (v: number | null | undefined, d = 1) => (v == null || !Number.isFinite(v) ? '—' : `${getNF(d).format(v)} %`);

export function fmtDate(iso?: string | null, withTime = false): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString('es-ES', { year: 'numeric', month: 'short', day: '2-digit', ...(withTime ? { hour: '2-digit', minute: '2-digit' } : {}) });
}

/** "2025Q3" → "2025 T3"; "2025-09" → "sep 2025". */
export function fmtPeriod(p: string | number): string {
  const s = String(p);
  const q = /^(\d{4})[-_ ]?[QT](\d)$/i.exec(s);
  if (q) return `${q[1]} T${q[2]}`;
  const m = /^(\d{4})-(\d{2})$/.exec(s);
  if (m) return new Date(Number(m[1]), Number(m[2]) - 1, 1).toLocaleDateString('es-ES', { month: 'short', year: 'numeric' });
  return s;
}
/** Valor numérico ordenable de un periodo ("2025Q3" → 2025.5). */
export function periodValue(p: string | number): number {
  const s = String(p);
  const q = /^(\d{4})[-_ ]?[QT](\d)$/i.exec(s);
  if (q) return Number(q[1]) + (Number(q[2]) - 1) / 4;
  const m = /^(\d{4})-(\d{2})/.exec(s);
  if (m) return Number(m[1]) + (Number(m[2]) - 1) / 12;
  const y = /^(\d{4})$/.exec(s);
  if (y) return Number(y[1]);
  return NaN;
}

/** Etiqueta legible de una variable técnica. */
export function humanize(k: string): string {
  return k.replace(/_/g, ' ').replace(/\bpc\b/i, 'per cápita').replace(/\bm2\b/i, 'm²').replace(/^\w/, (c) => c.toUpperCase());
}

export function fmtCell(v: unknown): string {
  if (v == null || v === '') return '—';
  if (typeof v === 'number') return fmtNum(v, Number.isInteger(v) ? 0 : undefined);
  if (typeof v === 'boolean') return v ? 'sí' : 'no';
  return String(v);
}
