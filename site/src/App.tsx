import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { slotFile, useJSON, useManifest, type Manifest, type Table } from './lib/data';
import { buildDict, type VarInfo } from './lib/dict';
import { fmtDate } from './lib/format';
import { Logo } from './components/ui';
import { Hero, Problem, Architecture } from './sections/Intro';
import { Sources, ProvincialPanel, Economic } from './sections/DataSections';
import { Econometrics, MachineLearning, Forecasts } from './sections/Models';
import { Simulator } from './sections/Simulator';
import { BankApp, Results, Limitations, Docs } from './sections/Closing';
import { StatusView } from './sections/StatusView';

export interface Ctx { manifest?: Manifest; dict: Record<string, VarInfo> }
const AppCtx = createContext<Ctx>({ dict: {} });
export const useApp = () => useContext(AppCtx);

export const SECTIONS = [
  ['portada', 'Portada'], ['problema', 'Problema de negocio'], ['arquitectura', 'Arquitectura de datos'], ['fuentes', 'Fuentes y metodología'],
  ['panel', 'Panel provincial'], ['economia', 'Análisis económico'], ['econometria', 'Econometría'], ['ml', 'Machine Learning'],
  ['predicciones', 'Predicciones y escenarios 2030'], ['simulador', 'Simulador hipotecario'], ['app', 'Aplicación bancaria'],
  ['resultados', 'Resultados y conclusiones'], ['limitaciones', 'Limitaciones'], ['documentacion', 'Documentación técnica'],
] as const;

type Theme = 'light' | 'dark' | 'system';
function useTheme(): [Theme, (t: Theme) => void] {
  const [t, setT] = useState<Theme>(() => { try { return (localStorage.getItem('atalaya-theme') as Theme) || 'system'; } catch { return 'system'; } });
  useEffect(() => {
    const el = document.documentElement;
    if (t === 'system') el.removeAttribute('data-theme'); else el.setAttribute('data-theme', t);
    try { localStorage.setItem('atalaya-theme', t); } catch { /* sin almacenamiento */ }
  }, [t]);
  return [t, setT];
}

function useHashView() {
  const get = () => (window.location.hash === '#estado' ? 'estado' : 'main');
  const [v, setV] = useState<'main' | 'estado'>(get);
  useEffect(() => {
    const on = () => { const nv = get(); setV(nv); if (nv === 'estado') window.scrollTo(0, 0); };
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);
  return v;
}

function useActiveSection(enabled: boolean) {
  const [active, setActive] = useState<string>('portada');
  useEffect(() => {
    if (!enabled) return;
    const els = SECTIONS.map(([id]) => document.getElementById(id)).filter(Boolean) as HTMLElement[];
    const io = new IntersectionObserver((es) => {
      const vis = es.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (vis[0]) setActive(vis[0].target.id);
    }, { rootMargin: '-20% 0px -70% 0px' });
    els.forEach((e) => io.observe(e));
    return () => io.disconnect();
  }, [enabled]);
  return active;
}

export default function App() {
  const { data: manifest } = useManifest();
  const dictT = useJSON<Table>(slotFile(manifest, 'variables'));
  const dict = useMemo(() => buildDict(dictT.data), [dictT.data]);
  const [theme, setTheme] = useTheme();
  const view = useHashView();
  const active = useActiveSection(view === 'main');
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open]);
  const nextTheme: Record<Theme, Theme> = { system: 'dark', dark: 'light', light: 'system' };
  const themeLabel: Record<Theme, string> = { system: 'Tema: sistema', dark: 'Tema: oscuro', light: 'Tema: claro' };

  return (
    <AppCtx.Provider value={{ manifest, dict }}>
      <a className="skip-link" href="#contenido">Saltar al contenido</a>
      <header className="topbar">
        {view === 'main' && (
          <button className="icon-btn menu-btn" aria-label="Índice de secciones" aria-expanded={open} aria-controls="toc" onClick={() => setOpen(!open)}>
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" /></svg>
          </button>
        )}
        <a className="brand" href="#portada" onClick={() => { if (view !== 'main') { window.location.hash = ''; } }}>
          <Logo /><span className="brand__name">ATALAYA</span><span className="brand__sub">· Analítica Hipotecaria</span>
        </a>
        <span className="topbar__spacer" />
        <nav className="topbar__links" aria-label="Accesos rápidos">
          <a className="btn btn--ghost" href={view === 'main' ? '#simulador' : '#'}>Simulador</a>
          <a className="btn btn--ghost" href="#estado" aria-current={view === 'estado' ? 'page' : undefined}>Estado de datos</a>
        </nav>
        <button className="icon-btn" onClick={() => setTheme(nextTheme[theme])} aria-label={`${themeLabel[theme]}. Cambiar tema`} title={themeLabel[theme]}>
          {theme === 'dark' ? (
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><path d="M15.5 12.5A6.5 6.5 0 0 1 7.5 4.5a6.5 6.5 0 1 0 8 8z" fill="currentColor" /></svg>
          ) : theme === 'light' ? (
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="3.5" fill="currentColor" /><g stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">{[0, 45, 90, 135, 180, 225, 270, 315].map((a) => <line key={a} x1="10" y1="2" x2="10" y2="4" transform={`rotate(${a} 10 10)`} />)}</g></svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7" fill="none" stroke="currentColor" strokeWidth="1.6" /><path d="M10 3a7 7 0 0 1 0 14z" fill="currentColor" /></svg>
          )}
        </button>
      </header>

      {view === 'estado' ? (
        <div className="layout" style={{ gridTemplateColumns: 'minmax(0,1fr)' }}>
          <main id="contenido" tabIndex={-1}><StatusView /></main>
        </div>
      ) : (
        <div className="layout">
          {open && <div className="scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
          <nav id="toc" className="toc" aria-label="Secciones" data-open={open}>
            <p className="toc__title">Contenido</p>
            <ol>
              {SECTIONS.map(([id, t], i) => (
                <li key={id}><a href={`#${id}`} aria-current={active === id ? 'true' : undefined} onClick={() => setOpen(false)}>
                  <span className="toc__num">{String(i + 1).padStart(2, '0')}</span>{t}</a></li>
              ))}
              <li><a href="#estado" onClick={() => setOpen(false)}><span className="toc__num">◉</span>Estado de fuentes y pipeline</a></li>
            </ol>
          </nav>
          <main id="contenido" tabIndex={-1}>
            <Hero /><Problem /><Architecture /><Sources /><ProvincialPanel /><Economic />
            <Econometrics /><MachineLearning /><Forecasts /><Simulator /><BankApp /><Results /><Limitations /><Docs />
          </main>
        </div>
      )}

      <footer className="layout">
        <div className="site-footer" style={{ gridColumn: '1 / -1' }}>
          <div className="site-footer__grid">
            <div>
              <h3>Atalaya · Analítica Hipotecaria</h3>
              <p>Proyecto académico (Trabajo Fin de Máster). Marca ficticia: no representa a ninguna entidad financiera. Las simulaciones son orientativas y no constituyen oferta, evaluación de solvencia ni asesoramiento financiero.</p>
            </div>
            <div>
              <h3>Fuentes</h3>
              <p>INE · BCE · Eurostat · MIVAU. Detalle por serie en <a href="#fuentes">Fuentes y metodología</a> y en <a href="#estado">Estado de datos</a>.</p>
            </div>
            <div>
              <h3>Actualización</h3>
              <p>Datos sincronizados: {fmtDate(manifest?.generated_at, true)}{manifest?.repo_commit && <><br />Commit: <code>{manifest.repo_commit}</code></>}</p>
            </div>
          </div>
        </div>
      </footer>
    </AppCtx.Provider>
  );
}
