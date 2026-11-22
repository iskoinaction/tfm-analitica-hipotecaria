import { useApp } from '../App';
import { artifactFile, slotFile, slotIndex, useJSON, type ArtifactItem, type Table } from '../lib/data';
import { fmtDate } from '../lib/format';
import { Card, DataTable, Loading, Pending, SourceLine } from '../components/ui';

interface Issue { check: string; severity: string; target: string; detail: string; n: number }
interface Report { started_at?: string; mode?: string; datasets?: Record<string, { source: string; ref: string; fetched: boolean; changed: boolean; origin_last_modified?: string; retrieved_at?: string; staging?: string; notes?: string[] }> }
const SEV: Record<string, string> = { info: 'badge badge--info', warning: 'badge badge--warn', error: 'badge badge--crit', critical: 'badge badge--crit' };

export function StatusView() {
  const { manifest } = useApp();
  const qa = useJSON<ArtifactItem[]>(slotIndex(manifest, 'artifacts:data_quality'));
  const issuesItem = artifactFile(qa.data, /^build_issues\.json$/);
  const v1v2Item = artifactFile(qa.data, /^v1_vs_v2\.(csv|json)$/);
  const reportItem = (qa.data ?? []).filter((i) => /^update_report.*\.json$/.test(i.name) && i.file).sort((a, b) => b.name.localeCompare(a.name))[0];
  const issues = useJSON<Issue[]>(issuesItem?.file);
  const v1v2 = useJSON<Table>(v1v2Item?.file);
  const report = useJSON<Report>(reportItem?.file);
  const prov = useJSON<Table>(slotFile(manifest, 'provenance'));
  const slots = Object.entries(manifest?.slots ?? {});
  const bySev = (issues.data ?? []).reduce<Record<string, number>>((a, i) => ({ ...a, [i.severity]: (a[i.severity] ?? 0) + 1 }), {});

  return (
    <div className="section" style={{ borderTop: 0 }}>
      <div className="section__kicker"><span className="mono">◉</span>Transparencia</div>
      <h1 className="section__title">Estado de las fuentes y del pipeline</h1>
      <p className="section__lead">Qué se descargó, cuándo, con qué huella (sha256), qué controles de calidad se han pasado y qué partes de esta web están pendientes de generar. Todo procede de <code>artifacts/data_quality/</code>, <code>data/metadata/provenance.csv</code> y del manifiesto de sincronización.</p>
      <div className="stack">
        <Card title="Sincronización de esta web" subtitle={`Generada ${fmtDate(manifest?.generated_at, true)}${manifest?.repo_commit ? ` · commit ${manifest.repo_commit}` : ''}`}>
          <div className="table-wrap" tabIndex={0} role="region" aria-label="Estado de los artefactos"><table className="table table--compact">
            <thead><tr><th>Componente</th><th>Estado</th><th>Actualizado</th><th>Origen</th></tr></thead>
            <tbody>{slots.map(([k, s]) => (
              <tr key={k}><td>{s.title}</td><td>{s.status === 'ok' ? <span className="badge badge--good">✓ disponible</span> : <span className="badge badge--neutral">◌ pendiente de generar</span>}</td>
                <td className="xs nowrap">{s.updated ? fmtDate(s.updated, true) : '—'}</td><td className="xs">{s.sources.slice(0, 2).map((x) => <code key={x}>{x}</code>)}{s.sources.length > 2 && ` +${s.sources.length - 2}`}</td></tr>
            ))}</tbody></table></div>
        </Card>
        <Card title="Snapshots de datos brutos" subtitle="Cada descarga se guarda con su huella; el cambio de huella delata una revisión en origen" source={<SourceLine manifest={manifest} slots={['provenance']} />}>
          {prov.loading ? <Loading /> : prov.data ? (
            <DataTable maxRows={20} table={{ columns: ['Conjunto', 'Fuente', 'Extracción', 'Series', 'Observaciones', 'sha256 (contenido)'],
              rows: prov.data.rows.filter((r) => !/tinsa/i.test(String(r[0]))).map((r) => { const c = (n: string) => r[prov.data!.columns.indexOf(n)]; return [c('dataset'), String(c('fuente')).toUpperCase(), fmtDate(String(c('fecha_extraccion')), true), c('n_series'), c('n_obs'), String(c('sha256_contenido') ?? '').slice(0, 12) + '…']; }) }} />
          ) : <Pending what="Procedencia" expected={['data/metadata/provenance.csv']} />}
        </Card>
        <div className="grid-2 grid-2--even">
          <Card title="Última ejecución de actualización" subtitle={report.data ? `${report.data.mode ?? ''} · ${fmtDate(report.data.started_at, true)}` : undefined}>
            {report.loading ? <Loading /> : report.data?.datasets ? (
              <DataTable maxRows={12} table={{ columns: ['Conjunto', 'Descargado', 'Cambió', 'Última modificación en origen'], rows: Object.entries(report.data.datasets).map(([k, d]) => [k, d.fetched ? 'sí' : 'no', d.changed ? 'sí' : 'no', d.origin_last_modified ?? '—']) }} />
            ) : <Pending what="Informe de actualización" expected={['artifacts/data_quality/update_report_*.json']} />}
          </Card>
          <Card title="Controles de calidad de la construcción del panel" subtitle={Object.keys(bySev).length ? Object.entries(bySev).map(([k, v]) => `${v} ${k}`).join(' · ') : undefined}>
            {issues.loading ? <Loading /> : issues.data ? (
              <div className="table-wrap" tabIndex={0} role="region" aria-label="Controles de calidad"><table className="table table--compact"><thead><tr><th>Control</th><th>Objetivo</th><th>Detalle</th></tr></thead>
                <tbody>{issues.data.map((i, k) => <tr key={k}><td><span className={SEV[i.severity] ?? 'badge badge--neutral'}>{i.severity}</span> {i.check}</td><td className="xs"><code>{i.target}</code></td><td className="xs">{i.detail}</td></tr>)}</tbody></table></div>
            ) : <Pending what="Controles de calidad" expected={['artifacts/data_quality/build_issues.json']} />}
          </Card>
        </div>
        <Card title="Comparación v1 frente a v2" subtitle="Reconciliación de las series de la primera versión con el pipeline reproducible">
          {v1v2.data ? <DataTable table={v1v2.data} maxRows={20} /> : v1v2.loading ? <Loading /> : <Pending what="Comparación v1/v2" expected={['artifacts/data_quality/v1_vs_v2.csv']} />}
        </Card>
        <p><a className="btn btn--secondary" href="#portada" onClick={() => { window.location.hash = ''; }}>← Volver a la presentación</a></p>
      </div>
    </div>
  );
}
