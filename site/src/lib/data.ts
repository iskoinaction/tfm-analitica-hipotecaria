import { useEffect, useState } from 'react';

export type SlotStatus = 'ok' | 'pending';
export interface Slot {
  status: SlotStatus;
  title: string;
  files: string[];
  sources: string[];
  updated?: string;
  note?: string;
}
export interface Manifest {
  generated_at: string;
  repo_commit: string | null;
  repo_url?: string | null;
  repo_branch?: string | null;
  root_available: boolean;
  slots: Record<string, Slot>;
}
export interface Table {
  columns: string[];
  rows: (string | number | boolean | null)[][];
  n_rows?: number;
  truncated?: boolean;
}
export interface ArtifactItem {
  name: string;
  source: string;
  updated: string;
  bytes: number;
  kind: string;
  file?: string;
  n_rows?: number;
  truncated?: boolean;
  skipped?: string;
  error?: string;
}

const cache = new Map<string, Promise<unknown>>();
export function fetchJSON<T = unknown>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(path, { cache: 'no-cache' }).then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${path}`);
        return r.json();
      }),
    );
  }
  return cache.get(path) as Promise<T>;
}

export interface Async<T> { data?: T; error?: string; loading: boolean }
export function useJSON<T = unknown>(path: string | null | undefined): Async<T> {
  const [state, setState] = useState<Async<T>>({ loading: !!path });
  useEffect(() => {
    let alive = true;
    if (!path) { setState({ loading: false }); return; }
    setState({ loading: true });
    fetchJSON<T>(path)
      .then((d) => alive && setState({ data: d, loading: false }))
      .catch((e: Error) => alive && setState({ error: e.message, loading: false }));
    return () => { alive = false; };
  }, [path]);
  return state;
}

export function useManifest(): Async<Manifest> {
  return useJSON<Manifest>('data/manifest.json');
}

/** Primer fichero de un slot si está disponible. */
export function slotFile(m: Manifest | undefined, key: string, i = 0): string | null {
  const s = m?.slots[key];
  return s && s.status === 'ok' ? s.files[i] ?? null : null;
}
export function slotIndex(m: Manifest | undefined, key: string): string | null {
  return m?.slots[key]?.files[0] ?? null;
}

/** Convierte array de objetos o Table en Table. */
export function toTable(x: unknown): Table | null {
  if (!x) return null;
  if (typeof x === 'object' && x !== null && Array.isArray((x as Table).columns) && Array.isArray((x as Table).rows)) return x as Table;
  if (Array.isArray(x) && x.length && x.every((r) => r && typeof r === 'object' && !Array.isArray(r))) {
    const cols: string[] = [];
    for (const r of x as Record<string, unknown>[]) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
    return {
      columns: cols,
      rows: (x as Record<string, unknown>[]).map((r) => cols.map((c) => {
        const v = r[c];
        return v == null || typeof v === 'number' || typeof v === 'string' || typeof v === 'boolean' ? (v as never) : JSON.stringify(v);
      })),
    };
  }
  return null;
}

/** Busca una clave en un objeto de forma tolerante (minúsculas, sin tildes, alias). */
export function pick(obj: Record<string, unknown>, aliases: string[]): unknown {
  const norm = (s: string) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]/g, '');
  const map = new Map(Object.keys(obj).map((k) => [norm(k), k]));
  for (const a of aliases) { const k = map.get(norm(a)); if (k !== undefined && obj[k] != null && obj[k] !== '') return obj[k]; }
  return undefined;
}

/** Fichero publicado (JSON) de un artefacto por dominio y nombre. */
export function artifactFile(items: ArtifactItem[] | undefined, re: RegExp): ArtifactItem | undefined {
  return (items ?? []).find((i) => re.test(i.name) && i.file);
}
