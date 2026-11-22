import type { Table } from './data';
import { humanize } from './format';

export interface VarInfo { key: string; label: string; unit?: string; source?: string; dataset?: string; description?: string; aggregation?: string; geo?: string }

function shortLabel(d?: string): string | undefined {
  if (!d) return undefined;
  const s = d.split(/\s[(]|[.,;]\s|\.$/)[0].trim();
  return s.length >= 3 && s.length <= 64 ? s : undefined;
}

/** Diccionario de variables a partir de data/metadata/data_dictionary.csv (convertido a Table). */
export function buildDict(t?: Table | null): Record<string, VarInfo> {
  const out: Record<string, VarInfo> = {};
  if (!t) return out;
  const i = (n: string) => t.columns.indexOf(n);
  const [c, u, f, d, desc, ag, geo] = ['columna', 'unidad', 'fuente', 'dataset', 'descripcion', 'agregacion_trimestral', 'geo_level'].map(i);
  for (const r of t.rows) {
    const key = String(r[c] ?? '');
    if (!key || out[key]) continue;
    const description = desc >= 0 && r[desc] ? String(r[desc]) : undefined;
    out[key] = {
      key, label: shortLabel(description) ?? humanize(key), geo: geo >= 0 && r[geo] ? String(r[geo]) : undefined,
      unit: u >= 0 && r[u] ? String(r[u]) : undefined, source: f >= 0 && r[f] ? String(r[f]) : undefined,
      dataset: d >= 0 && r[d] ? String(r[d]) : undefined, description, aggregation: ag >= 0 && r[ag] ? String(r[ag]) : undefined,
    };
  }
  return out;
}
export const varLabel = (d: Record<string, VarInfo>, k: string) => d[k]?.label ?? humanize(k);
