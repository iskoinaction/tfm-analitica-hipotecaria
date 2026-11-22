/** Valida la implementación JS contra artifacts/advisor/test_vectors.json (motor Python src.advisor) y contra valores analíticos. */
import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import * as A from './advisor';

const ART = path.resolve(__dirname, '../../../artifacts/advisor');
const have = fs.existsSync(path.join(ART, 'test_vectors.json')) && fs.existsSync(path.join(ART, 'fiscal_tables.json'));
const close = (a: number, b: number, tol = 0.01) => expect(Math.abs(a - b)).toBeLessThanOrEqual(tol);

describe('fórmulas básicas', () => {
  it.each([[150000, 3.0, 300, 711.32], [200000, 3.5, 360, 898.09], [100000, 0, 120, 833.33]])('cuota %d/%d/%d', (P, t, n, e) => close(A.cuotaFrancesa(P, t, n), e));
  it('el cuadro termina en saldo 0 y capital máximo es la inversa', () => {
    const c = A.cuotaFrancesa(150000, 3, 300);
    const f = A.cuadroAnual(150000, [[300, 3]]);
    expect(f[f.length - 1].saldo).toBe(0);
    close(A.capitalMaximoPorCuota(c, 3, 300), 150000, 1e-6);
  });
});

describe.skipIf(!have)('vectores de prueba del motor Python', () => {
  const tabla = have ? JSON.parse(fs.readFileSync(path.join(ART, 'fiscal_tables.json'), 'utf8')) : null;
  const vec = have ? JSON.parse(fs.readFileSync(path.join(ART, 'test_vectors.json'), 'utf8')) : null;
  const pol = A.politicaDe(vec?.meta?.politica);
  const ccaa: Record<string, string> = {};
  if (have) {
    const csv = fs.readFileSync(path.resolve(__dirname, '../../../data/processed/panel_trimestral.csv'), 'utf8').split(/\r?\n/);
    const h = csv[0].split(','), ip = h.indexOf('prov_code'), ic = h.indexOf('ccaa_code');
    for (const l of csv.slice(1)) { const c = l.split(','); if (c[ip]) ccaa[c[ip].padStart(2, '0')] = c[ic].padStart(2, '0'); }
  }
  it('hay 18 casos', () => expect(vec.casos.length).toBeGreaterThanOrEqual(18));
  for (const c of have ? vec.casos : []) {
    it(c.id, () => {
      const i = c.entrada, s = c.salida;
      const r = A.simular({
        ccaa: ccaa[i.provincia], precio: i.precio_vivienda, tipoVivienda: i.tipo_vivienda ?? 'usada', viviendaHabitual: i.vivienda_habitual ?? true, aportacion: i.aportacion,
        valorTasacion: i.valor_tasacion, ingresosNetosMes: i.ingresos_netos_mensuales, numeroPagas: i.numero_pagas ?? 12, otrasDeudasMes: i.otras_deudas_mensuales ?? 0,
        edad: i.edad, plazoAnios: i.plazo_anios, modalidad: i.modalidad, tinPct: i.tin_pct, tinVariablePct: i.tin_variable_pct, aniosFijos: i.anios_fijos ?? 5, fecha: i.fecha_operacion,
      }, tabla.reglas, tabla.aranceles, pol);
      expect(ccaa[i.provincia]).toBeDefined();
      close(r.gastos.totalCliente, s.gastos_total_cliente, 0.011);
      close(r.capital, s.capital_prestamo, 0.011);
      expect(r.plazoMeses).toBe(s.plazo_meses);
      close(r.cuota, s.cuota_mensual, 0.011);
      close(r.cuotaEstres, s.cuota_estres, 0.011);
      close(r.totalIntereses, s.total_intereses, 0.02);
      close(r.entradaNecesariaLtv, s.entrada_necesaria_para_ltv_referencia, 0.011);
      close(r.ltv ?? 0, s.ltv, 1.1e-4); close(r.lti ?? 0, s.lti, 1.1e-3);
      close(r.dsti ?? 0, s.dsti, 1.1e-4); close(r.dstiEstres ?? 0, s.dsti_estres, 1.1e-4);
      expect(r.semaforo).toBe(s.semaforo);
      if (s.cuota_tras_periodo_fijo != null) close(r.cuotaTrasFijo ?? 0, s.cuota_tras_periodo_fijo, 0.011);
      const lineas = Object.entries(s.gastos) as [string, number][];
      for (const [k, v] of lineas) close(r.gastos.lineas.find((l) => l.concepto === k)?.importe ?? NaN, v, 0.011);
      expect(r.gastos.lineas.length).toBe(lineas.length);
      expect(JSON.stringify(r).toLowerCase()).not.toMatch(/aprobad|denegad|approved|denied/);
    });
  }
});
