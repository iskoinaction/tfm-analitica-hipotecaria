// script.js

let barChartInstance = null;
let lineChartInstance = null;

let macroChartInstance = null;
let hipNacChartInstance = null;
let topProvDashChartInstance = null;

// Estado global del filtro de años
let _yearFrom = '';
let _yearTo = '';
let _specificYear = ''; // Nuevo filtro específico para el BarChart

// Datos completos de custom charts (para re-filtrar sin rellamar la API)
let _allCustomCharts = [];

// Colores corporativos CaixaBank
const _CB_COLORS = [
    '#007BC0', '#FF6600', '#003F6C', '#66C4E8',
    '#FF9933', '#00A8E0', '#CC5200', '#004E96'
];

// Instancias Chart.js de custom charts
const _customChartInstances = {};

// ══════════════════════════════════════════════
//  INIT
// ══════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('barChart') || document.getElementById('lineChart')) {
        loadDashboardData();
        loadMaps();
        loadExtraCharts();
    }
    if (document.getElementById('customChartsGrid')) {
        loadCustomCharts();
    }
});

// ══════════════════════════════════════════════
//  FILTRO DE RANGO DE AÑOS Y ESPECÍFICO
// ══════════════════════════════════════════════
function _populateYearSelects(years) {
    const fromSel = document.getElementById('yearFrom');
    const toSel = document.getElementById('yearTo');
    const specificSel = document.getElementById('specificYearFilter');
    const lSel = document.getElementById('filterLineChart');
    const mSel = document.getElementById('filterMacroChart');
    const hnSel = document.getElementById('filterHipotecasNac');
    const tpSel = document.getElementById('filterTopProv');

    if (!fromSel || !toSel) return;

    // Guardar selección actual
    const prevFrom = fromSel.value;
    const prevTo = toSel.value;
    const prevSpecific = specificSel ? specificSel.value : '';
    const prevL = lSel ? lSel.value : '';
    const prevM = mSel ? mSel.value : '';
    const prevHN = hnSel ? hnSel.value : '';
    const prevTP = tpSel ? tpSel.value : '';

    // Limpiar y repoblar
    fromSel.innerHTML = '<option value="">--</option>';
    toSel.innerHTML = '<option value="">--</option>';
    if (specificSel) specificSel.innerHTML = '<option value="">Todos los años</option>';
    if (lSel) lSel.innerHTML = '<option value="">Todos</option>';
    if (mSel) mSel.innerHTML = '<option value="">Todos</option>';
    if (hnSel) hnSel.innerHTML = '<option value="">Todos</option>';
    if (tpSel) tpSel.innerHTML = '<option value="">Último disp</option>';

    years.forEach(y => {
        fromSel.innerHTML += `<option value="${y}">${y}</option>`;
        toSel.innerHTML += `<option value="${y}">${y}</option>`;
        if (specificSel) specificSel.innerHTML += `<option value="${y}">${y}</option>`;
        if (lSel) lSel.innerHTML += `<option value="${y}">${y}</option>`;
        if (mSel) mSel.innerHTML += `<option value="${y}">${y}</option>`;
        if (hnSel) hnSel.innerHTML += `<option value="${y}">${y}</option>`;
        if (tpSel) tpSel.innerHTML += `<option value="${y}">${y}</option>`;
    });

    // Restaurar selección si sigue siendo válida
    if (prevFrom && years.includes(prevFrom)) fromSel.value = prevFrom;
    if (prevTo && years.includes(prevTo)) toSel.value = prevTo;
    if (specificSel && prevSpecific && years.includes(prevSpecific)) specificSel.value = prevSpecific;
    if (lSel && prevL && years.includes(prevL)) lSel.value = prevL;
    if (mSel && prevM && years.includes(prevM)) mSel.value = prevM;
    if (hnSel && prevHN && years.includes(prevHN)) hnSel.value = prevHN;
    if (tpSel && prevTP && years.includes(prevTP)) tpSel.value = prevTP;
}

function applyYearFilter() {
    const fromSel = document.getElementById('yearFrom');
    const toSel = document.getElementById('yearTo');
    _yearFrom = fromSel ? fromSel.value : '';
    _yearTo = toSel ? toSel.value : '';

    // Validar que from <= to
    if (_yearFrom && _yearTo && _yearFrom > _yearTo) {
        toSel.value = _yearFrom;
        _yearTo = _yearFrom;
    }

    loadDashboardData();
    filterCustomCharts();
}

let _lastDashboardData = null;

function applySpecificYearFilter(chartId) {
    if (!chartId) {
        // Bar chart uses API directly
        const specificSel = document.getElementById('specificYearFilter');
        _specificYear = specificSel ? specificSel.value : '';
        loadDashboardData();
        return;
    }

    // For other charts, filter locally from _lastDashboardData
    if (!_lastDashboardData) return;

    if (chartId === 'lineChart' && _lastDashboardData.timeSeries) {
        let yr = document.getElementById('filterLineChart').value;
        const d = _lastDashboardData.timeSeries;
        if (!yr) { renderLineChart(d); return; }
        const mask = d.labels.map(l => String(l).startsWith(yr));
        renderLineChart({
            labels: d.labels.filter((_, i) => mask[i]),
            euribor: d.euribor.filter((_, i) => mask[i]),
            spread: d.spread.filter((_, i) => mask[i])
        });
    } else if (chartId === 'macroChart' && _lastDashboardData.macroSeries) {
        let yr = document.getElementById('filterMacroChart').value;
        const d = _lastDashboardData.macroSeries;
        if (!yr) { renderMacroChart(d); return; }
        const mask = d.labels.map(l => String(l) === yr); // labels are years here
        renderMacroChart({
            labels: d.labels.filter((_, i) => mask[i]),
            ipc: d.ipc.filter((_, i) => mask[i]),
            paro: d.paro.filter((_, i) => mask[i])
        });
    } else if (chartId === 'hipotecasNac' && _lastDashboardData.hipotecasNac) {
        let yr = document.getElementById('filterHipotecasNac').value;
        const d = _lastDashboardData.hipotecasNac;
        if (!yr) { renderHipotecasNacChart(d); return; }
        const mask = d.labels.map(l => String(l).startsWith(yr));
        renderHipotecasNacChart({
            labels: d.labels.filter((_, i) => mask[i]),
            values: d.values.filter((_, i) => mask[i])
        });
    } else if (chartId === 'topProv' && _lastDashboardData.topProvHip) {
        let yr = document.getElementById('filterTopProv').value;
        const d = _lastDashboardData.topProvHip;
        if (!yr || !d.by_year[yr]) {
            yr = d.last_yr;
            const el = document.getElementById('filterTopProv');
            if (el) el.value = yr;
        }
        renderTopProvDashChart(d.by_year[yr]);
    }
}

function resetYearFilter() {
    _yearFrom = '';
    _yearTo = '';
    _specificYear = '';
    const fromSel = document.getElementById('yearFrom');
    const toSel = document.getElementById('yearTo');
    const specificSel = document.getElementById('specificYearFilter');
    const sels = ['filterLineChart', 'filterMacroChart', 'filterHipotecasNac', 'filterTopProv'];

    if (fromSel) fromSel.value = '';
    if (toSel) toSel.value = '';
    if (specificSel) specificSel.value = '';
    sels.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });

    loadDashboardData();
    filterCustomCharts();
}

// Construye la query string para /api/data
function _buildYearQuery() {
    const params = new URLSearchParams();
    if (_yearFrom) params.set('year_from', _yearFrom);
    if (_yearTo) params.set('year_to', _yearTo);
    if (_specificYear) params.set('specific_year', _specificYear);
    return params.toString();
}

// ══════════════════════════════════════════════
//  DASHBOARD NATIVO
// ══════════════════════════════════════════════
function loadDashboardData() {
    const query = _buildYearQuery();
    fetch(`/api/data${query ? '?' + query : ''}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) { console.warn('No data:', data.error); return; }
            _lastDashboardData = data;

            // Poblar los selects de año la primera vez
            if (data.availableYears) {
                _populateYearSelects(data.availableYears);
            }

            // Sync selectors state
            ['lineChart', 'macroChart', 'hipotecasNac'].forEach(id => {
                const el = document.getElementById(`filter${id.charAt(0).toUpperCase() + id.slice(1)}`);
                if (el && el.value) applySpecificYearFilter(id);
                else {
                    if (id === 'lineChart') renderLineChart(data.timeSeries);
                    if (id === 'macroChart') renderMacroChart(data.macroSeries);
                    if (id === 'hipotecasNac') renderHipotecasNacChart(data.hipotecasNac);
                }
            });

            renderBarChart(data.barData);
            if (data.topProvHip) renderTopProvDashChart(data.topProvHip);
        })
        .catch(err => console.error('Error loading chart data:', err));
}

function renderBarChart(barData) {
    if (!barData) return;
    const canvas = document.getElementById('barChart');
    if (!canvas) return;

    // Cambiar título dinámicamente si hay filtro específico
    const titleEl = document.getElementById('barChartTitle');
    if (titleEl) {
        titleEl.textContent = barData.year
            ? `Precio Medio Histórico por Provincia (€/m²) (${barData.year})`
            : `Precio Medio Histórico por Provincia (€/m²) (Todos los años)`;
    }

    if (barChartInstance) barChartInstance.destroy();
    barChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: barData.labels,
            datasets: [{
                label: 'Precio Medio €/m²',
                data: barData.values,
                backgroundColor: '#007EAA',
                borderRadius: 4,
                hoverBackgroundColor: '#004D73'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

function renderLineChart(timeData) {
    if (!timeData) return;
    const canvas = document.getElementById('lineChart');
    if (!canvas) return;
    if (lineChartInstance) lineChartInstance.destroy();
    lineChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: timeData.labels,
            datasets: [
                {
                    label: 'Euribor Medio (%)',
                    data: timeData.euribor,
                    borderColor: '#000000',
                    backgroundColor: 'transparent',
                    tension: 0.3,
                    borderWidth: 2
                },
                {
                    label: 'Spread Hipotecas (%)',
                    data: timeData.spread,
                    borderColor: '#00A4E4',
                    backgroundColor: 'rgba(0,164,228,0.1)',
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false }
        }
    });
}

function renderMacroChart(macroData) {
    if (!macroData) return;
    const canvas = document.getElementById('macroChart');
    if (!canvas) return;
    if (macroChartInstance) macroChartInstance.destroy();

    // Gráfico mix: Tasa de Paro (Barras) e IPC (Línea)
    macroChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: macroData.labels,
            datasets: [
                {
                    type: 'line',
                    label: 'IPC Medio (%)',
                    data: macroData.ipc,
                    borderColor: '#FF6600',  // Naranja corporativo
                    backgroundColor: 'transparent',
                    tension: 0.4,
                    borderWidth: 3,
                    yAxisID: 'y1',
                },
                {
                    type: 'bar',
                    label: 'Tasa de Paro (%)',
                    data: macroData.paro,
                    backgroundColor: '#003F6C', // Azul oscuro corporativo
                    borderRadius: 3,
                    yAxisID: 'y',
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    title: { display: true, text: 'Tasa de Paro (%)' }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { drawOnChartArea: false },
                    title: { display: true, text: 'IPC (%)' }
                }
            }
        }
    });
}

function renderHipotecasNacChart(d) {
    const canvas = document.getElementById('hipotecasNacChart');
    if (!canvas) return;
    if (hipNacChartInstance) hipNacChartInstance.destroy();
    hipNacChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: d.labels,
            datasets: [{
                label: 'Hipotecas Totales (España)',
                data: d.values,
                borderColor: '#007BC0',
                backgroundColor: 'rgba(0,123,192,0.08)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxTicksLimit: 12, font: { size: 10 } } },
                y: { title: { display: true, text: 'Total hipotecas' } }
            }
        }
    });
}

function renderTopProvDashChart(d) {
    if (!d || !d.labels) return;
    const canvas = document.getElementById('topProvDashChart');
    if (topProvDashChartInstance) topProvDashChartInstance.destroy();
    topProvDashChartInstance = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: d.labels,
            datasets: [{
                label: 'Hipotecas ' + (d.year || ''),
                data: d.values,
                backgroundColor: d.labels.map((_, i) => i < 3 ? '#007BC0' : '#66C4E8'),
                borderRadius: 4,
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { title: { display: true, text: 'Total hipotecas' } },
                y: { ticks: { font: { size: 10 } } }
            }
        }
    });
}

// ══════════════════════════════════════════════
//  CUSTOM CHARTS — CARGA Y FILTRADO
// ══════════════════════════════════════════════
async function loadCustomCharts() {
    const res = await fetch('/api/custom-charts');
    _allCustomCharts = await res.json();
    renderCustomCharts(_allCustomCharts);
}

/** Filtra _allCustomCharts por el rango actual y re-renderiza */
function filterCustomCharts() {
    if (!_allCustomCharts.length) return;
    renderCustomCharts(_allCustomCharts);
}

/**
 * Extrae el año de un label. Funciona con:
 * "2005-01-01", "2005-T1", "2010Q1", "2015", "2020 Q3", etc.
 * Si no puede extraer un año válido, devuelve null.
 */
function _labelToYear(label) {
    const m = String(label).match(/^(20\d{2}|19\d{2})/);
    return m ? m[1] : null;
}

/**
 * Dado un chart entry, devuelve { labels, datasets } filtrados por el rango
 * _yearFrom / _yearTo. Si no hay filtro activo, devuelve los datos completos.
 * Usa year_for_labels si existe; si no, intenta inferir el año del propio label.
 */
function _applyYearRangeToChart(c) {
    const hasFilter = _yearFrom || _yearTo;
    if (!hasFilter) return { labels: c.labels || [], datasets: c.datasets || [] };

    const allLabels = c.labels || [];
    // Intentar usar year_for_labels; si no existe o tiene longitud incorrecta,
    // inferir el año de cada label directamente.
    let yearPerPoint;
    if (c.year_for_labels && c.year_for_labels.length === allLabels.length) {
        yearPerPoint = c.year_for_labels;
    } else {
        yearPerPoint = allLabels.map(_labelToYear);
    }

    // Si ningún label tiene año reconocible, no filtramos (ej. ranking de provincias)
    const anyYearFound = yearPerPoint.some(y => y !== null);
    if (!anyYearFound) return { labels: allLabels, datasets: c.datasets || [] };

    // Indices que pasan el filtro
    const idxOk = yearPerPoint
        .map((y, i) => {
            if (y === null) return i; // sin año = incluir siempre
            const ok = (!_yearFrom || y >= _yearFrom) && (!_yearTo || y <= _yearTo);
            return ok ? i : -1;
        })
        .filter(i => i >= 0);

    const labels = idxOk.map(i => allLabels[i]);
    const datasets = (c.datasets || []).map(ds => ({
        ...ds,
        data: idxOk.map(i => (ds.data || [])[i])
    }));
    return { labels, datasets };
}

function renderCustomCharts(charts) {
    const grid = document.getElementById('customChartsGrid');
    const section = document.getElementById('custom-charts-section');
    if (!grid) return;

    if (!charts.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    grid.innerHTML = '';

    charts.forEach(c => {
        const card = document.createElement('div');

        if (c.render_type === 'chartjs') {
            const canvasId = `custom-chart-${c.id}`;
            card.className = 'chart-card';
            card.style.position = 'relative';
            const filterHtml = c.filterable ? `
              <div style="margin-bottom:0.5rem;text-align:right;">
                <label style="font-size:0.82rem;color:#555;">Filtro año:
                  <select id="filter-${c.id}" onchange="filterCustomChart('${c.id}')" class="styled-select" style="padding:3px 8px;margin-left:4px;">
                    <option value="">Todos</option>
                  </select>
                </label>
              </div>` : '';
            card.innerHTML = `
              <h3>${c.title || c.description}</h3>
              ${filterHtml}
              <canvas id="${canvasId}" style="max-height:300px;"></canvas>
              <div style="display:flex;align-items:center;justify-content:space-between;padding:0.4rem 0.2rem 0;">
                <span style="font-size:0.78rem;color:#888;">${c.source || ''}</span>
                <button class="btn-cc-delete" onclick="deleteCustomChart('${c.id}', this)" title="Eliminar">✕</button>
              </div>`;
            grid.appendChild(card);

            // Populate year filter if filterable
            if (c.filterable && c.labels) {
                const sel = document.getElementById(`filter-${c.id}`);
                if (sel) {
                    const years = [...new Set(c.labels.map(l => String(l).substring(0, 4)))].filter(y => /^\d{4}$/.test(y)).sort();
                    years.forEach(y => { const o = document.createElement('option'); o.value = y; o.textContent = y; sel.appendChild(o); });
                }
            }

            requestAnimationFrame(() => {
                const canvas = document.getElementById(canvasId);
                if (!canvas) return;
                if (_customChartInstances[c.id]) _customChartInstances[c.id].destroy();

                // Aplicar filtro de rango de años
                const { labels: filteredLabels, datasets: filteredRaw } = _applyYearRangeToChart(c);

                const datasets = filteredRaw.map((ds, i) => {
                    const color = ds.color || _CB_COLORS[i % _CB_COLORS.length];
                    return {
                        label: ds.label || '',
                        data: ds.data || [],
                        borderColor: color,
                        backgroundColor: ds.fill ? hexToRgba(color, 0.13)
                            : (c.chart_type === 'bar' ? color : 'transparent'),
                        borderWidth: 2,
                        borderRadius: c.chart_type === 'bar' ? 4 : undefined,
                        hoverBackgroundColor: c.chart_type === 'bar' ? darken(color) : undefined,
                        fill: !!ds.fill,
                        tension: ds.tension ?? (c.chart_type === 'line' ? 0.3 : undefined),
                        pointRadius: c.chart_type === 'line' ? 3 : undefined,
                    };
                });

                _customChartInstances[c.id] = new Chart(canvas.getContext('2d'), {
                    type: c.chart_type || 'bar',
                    data: { labels: filteredLabels, datasets },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        interaction: { mode: 'index', intersect: false },
                        plugins: {
                            legend: {
                                display: datasets.length > 1,
                                position: 'top',
                                labels: { boxWidth: 12, font: { size: 11 } }
                            },
                            tooltip: {
                                backgroundColor: 'rgba(0,50,100,0.88)',
                                titleFont: { weight: 'bold' }
                            }
                        },
                        scales: (c.chart_type === 'doughnut' || c.chart_type === 'pie') ? {} : {
                            x: { grid: { color: '#E2EAF4' }, ticks: { font: { size: 10 } } },
                            y: { beginAtZero: true, grid: { color: '#E2EAF4' }, ticks: { font: { size: 10 } } }
                        }
                    }
                });
            });

        } else {
            // Fallback PNG
            card.className = 'custom-chart-card';
            card.innerHTML = `
              <img src="/static/custom_charts/${c.filename}" alt="${c.description}" loading="lazy">
              <div class="cc-footer">
                <span class="cc-desc">${c.description}</span>
                <button class="btn-cc-delete" onclick="deleteCustomChart('${c.id}', this)" title="Eliminar">✕</button>
              </div>`;
            grid.appendChild(card);
        }
    });
}

function filterCustomChart(chartId) {
    const sel = document.getElementById(`filter-${chartId}`);
    if (!sel) return;
    const year = sel.value;
    const c = _allCustomCharts.find(x => x.id === chartId);
    if (!c || c.render_type !== 'chartjs') return;

    const canvasId = `custom-chart-${chartId}`;
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (_customChartInstances[chartId]) _customChartInstances[chartId].destroy();

    let labels = c.labels || [];
    let datasets = (c.datasets || []).map(ds => ({ ...ds, data: [...(ds.data || [])] }));

    if (year) {
        const mask = labels.map(l => String(l).startsWith(year));
        labels = labels.filter((_, i) => mask[i]);
        datasets = datasets.map(ds => ({
            ...ds,
            data: (ds.data || []).filter((_, i) => mask[i])
        }));
    }

    const dsRendered = datasets.map((ds, i) => {
        const color = ds.color || _CB_COLORS[i % _CB_COLORS.length];
        return {
            label: ds.label || '', data: ds.data || [],
            borderColor: color,
            backgroundColor: ds.fill ? hexToRgba(color, 0.13) : (c.chart_type === 'bar' ? color : 'transparent'),
            borderWidth: 2, borderRadius: c.chart_type === 'bar' ? 4 : undefined,
            fill: !!ds.fill, tension: ds.tension ?? (c.chart_type === 'line' ? 0.3 : undefined),
            pointRadius: c.chart_type === 'line' ? 3 : undefined,
        };
    });

    _customChartInstances[chartId] = new Chart(canvas.getContext('2d'), {
        type: c.chart_type || 'bar',
        data: { labels, datasets: dsRendered },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: dsRendered.length > 1, position: 'top' } },
            scales: (c.chart_type === 'doughnut' || c.chart_type === 'pie') ? {} : {
                x: { grid: { color: '#E2EAF4' }, ticks: { font: { size: 10 } } },
                y: { beginAtZero: true, grid: { color: '#E2EAF4' }, ticks: { font: { size: 10 } } }
            }
        }
    });
}

async function deleteCustomChart(id, btn) {
    btn.disabled = true;
    const res = await fetch(`/api/custom-charts/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
        const card = btn.closest('.chart-card, .custom-chart-card');
        card.style.transition = 'opacity 0.3s';
        card.style.opacity = '0';
        setTimeout(() => {
            card.remove();
            _allCustomCharts = _allCustomCharts.filter(c => c.id !== id);
            if (!document.querySelectorAll('#customChartsGrid .chart-card, #customChartsGrid .custom-chart-card').length) {
                document.getElementById('custom-charts-section').style.display = 'none';
            }
        }, 300);
    } else if (res.status === 401) {
        alert('Necesitas iniciar sesión como administrador para eliminar gráficos.');
        btn.disabled = false;
    } else {
        alert('Error: ' + data.error);
        btn.disabled = false;
    }
}

// ══════════════════════════════════════════════
//  HELPERS DE COLOR
// ══════════════════════════════════════════════
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r},${g},${b},${alpha})`;
}
function darken(hex) {
    const r = Math.max(0, parseInt(hex.slice(1, 3), 16) - 30);
    const g = Math.max(0, parseInt(hex.slice(3, 5), 16) - 30);
    const b = Math.max(0, parseInt(hex.slice(5, 7), 16) - 30);
    return `rgb(${r},${g},${b})`;
}

// ══════════════════════════════════════════════
//  MAPAS GEOESPACIALES
// ══════════════════════════════════════════════
function loadMaps() {
    loadMapItem('tension', 'mapTensionContainer');

}

function loadMapItem(tipo, containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    fetch(`/api/mapa/${tipo}`)
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                container.innerHTML = `<span style="color:#d9534f;">Error cargando mapa: ${data.error}</span>`;
                return;
            }
            if (data.image) {
                container.innerHTML = `<img src="${data.image}" style="max-width:100%; height:auto; border-radius: 4px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);" alt="Mapa geoespacial" />`;
            }
        })
        .catch(err => {
            console.error(`Error fetching map ${tipo}:`, err);
            container.innerHTML = `<span style="color:#d9534f;">Error de red al cargar el mapa</span>`;
        });
}

// ══════════════════════════════════════════════
//  CHATBOT
// ══════════════════════════════════════════════
let chatAbortController = null;

function toggleChat() {
    document.getElementById('chatbot').classList.toggle('open');
}
function handleKey(event) {
    if (event.key === 'Enter') sendMessage();
}
function cancelChatRequest() {
    if (chatAbortController) {
        chatAbortController.abort();
        chatAbortController = null;
        const typingEl = document.getElementById('ai-typing-indicator');
        if (typingEl) typingEl.remove();
        appendMessage('Has cancelado la respuesta.', 'bot');
    }
}
function sendMessage() {
    const input = document.getElementById('chatInput');
    const msg = input.value.trim();
    if (!msg) return;
    appendMessage(msg, 'user');
    input.value = '';

    // Indicador "escribiendo" y botón cancelar
    const body = document.getElementById('chatBody');
    const wrapDiv = document.createElement('div');
    wrapDiv.id = 'ai-typing-indicator';
    wrapDiv.style.textAlign = 'left';
    wrapDiv.style.margin = '8px 0';
    wrapDiv.innerHTML = `
        <span style="font-size:0.8rem; color:#003366; font-style:italic;">AI Asistente está escribiendo...</span>
        <button onclick="cancelChatRequest()" style="background:#dc3545; color:white; border:none; border-radius:4px; padding:2px 6px; font-size:0.7rem; margin-left:8px; cursor:pointer;">🛑 Cancelar</button>
    `;
    body.appendChild(wrapDiv);
    body.scrollTop = body.scrollHeight;

    chatAbortController = new AbortController();

    fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
        signal: chatAbortController.signal
    })
        .then(r => r.json())
        .then(d => {
            const typingEl = document.getElementById('ai-typing-indicator');
            if (typingEl) typingEl.remove();
            appendMessage(d.reply, 'bot');
            chatAbortController = null;
        })
        .catch(err => {
            if (err.name === 'AbortError') {
                console.log('Chat fetch aborted');
            } else {
                const typingEl = document.getElementById('ai-typing-indicator');
                if (typingEl) typingEl.remove();
                appendMessage('Error conectando con el servidor.', 'bot');
                chatAbortController = null;
            }
        });
}
function appendMessage(text, sender) {
    const body = document.getElementById('chatBody');
    const div = document.createElement('div');
    div.classList.add('chat-message', sender);
    // Usar innerHTML en lugar de textContent para permitir <br> e incrustar links de fuentes
    div.innerHTML = text;
    body.appendChild(div);
    body.scrollTop = body.scrollHeight;
}

// ══════════════════════════════════════════════
//  NUEVOS GRÁFICOS DASHBOARD — API /api/dashboard-extra
// ══════════════════════════════════════════════
let _extraChartsData = null;
let _precioProvChart = null;
let _pibChart = null;
let _paroChart = null;
let _scatterChart = null;

function loadExtraCharts(provincia = '', year = '') {
    if (!document.getElementById('precioProvChart')) return;
    const params = new URLSearchParams();
    if (provincia) params.set('provincia', provincia);
    if (year) params.set('year', year);
    fetch('/api/dashboard-extra' + (params.toString() ? '?' + params.toString() : ''))
        .then(r => r.json())
        .then(data => {
            if (data.error) return;
            _extraChartsData = data;
            // Poblar selects de provincia
            ['filterPrecioProvSelect','filterPibProvSelect','filterParoProvSelect'].forEach(id => {
                const sel = document.getElementById(id);
                if (!sel || sel.options.length > 2) return;
                const defaultLabel = id === 'filterPrecioProvSelect' ? 'Top 5 provincias' : 'Nacional (media)';
                sel.innerHTML = `<option value="">${defaultLabel}</option>`;
                (data.provinces || []).forEach(p => {
                    sel.innerHTML += `<option value="${p}">${p}</option>`;
                });
            });
            const scatterSel = document.getElementById('filterScatterYear');
            if (scatterSel && scatterSel.options.length < 3) {
                scatterSel.innerHTML = '<option value="">Último disponible</option>';
                (data.years || []).slice(-10).forEach(y => {
                    scatterSel.innerHTML += `<option value="${y}">${y}</option>`;
                });
            }
            renderPrecioProvChart(data.precio_prov_series);
            renderPibChart(data.pib_series);
            renderParoChart(data.paro_series);
            renderScatterChart(data.scatter);
        })
        .catch(err => console.error('Extra charts error:', err));
}

function updatePrecioProvChart() {
    const sel = document.getElementById('filterPrecioProvSelect');
    loadExtraCharts(sel ? sel.value : '');
}
function updatePibChart() {
    const sel = document.getElementById('filterPibProvSelect');
    loadExtraCharts(sel ? sel.value : '');
}
function updateParoChart() {
    const sel = document.getElementById('filterParoProvSelect');
    loadExtraCharts(sel ? sel.value : '');
}
function updateScatterChart() {
    const sel = document.getElementById('filterScatterYear');
    loadExtraCharts('', sel ? sel.value : '');
}

function renderPrecioProvChart(series) {
    const canvas = document.getElementById('precioProvChart');
    if (!canvas || !series) return;
    if (_precioProvChart) _precioProvChart.destroy();
    const datasets = series.map((s, i) => ({
        label: s.provincia,
        data: s.values,
        borderColor: _CB_COLORS[i % _CB_COLORS.length],
        backgroundColor: 'transparent',
        tension: 0.3,
        borderWidth: 2,
        pointRadius: 0,
    }));
    // Use labels from first series (all share same timeline)
    const labels = series.length ? series[0].labels : [];
    _precioProvChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { font: { size: 11 } } },
                tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString('es')} €/m²` } }
            },
            scales: {
                y: { title: { display: true, text: '€/m²' }, beginAtZero: false },
                x: { ticks: { maxTicksLimit: 10 } }
            }
        }
    });
}

function renderPibChart(series) {
    const canvas = document.getElementById('pibProvChart');
    if (!canvas || !series) return;
    if (_pibChart) _pibChart.destroy();
    _pibChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: series.labels,
            datasets: [{
                label: series.scope + ' — PIB/pc',
                data: series.values,
                borderColor: '#007BC0',
                backgroundColor: 'rgba(0,123,192,0.08)',
                fill: true,
                tension: 0.3,
                borderWidth: 2.5,
                pointRadius: 0,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => `${ctx.parsed.y.toLocaleString('es')} €` } }
            },
            scales: {
                y: { title: { display: true, text: '€ / habitante' }, beginAtZero: false },
                x: { ticks: { maxTicksLimit: 10 } }
            }
        }
    });
}

function renderParoChart(series) {
    const canvas = document.getElementById('paroProvChart');
    if (!canvas || !series) return;
    if (_paroChart) _paroChart.destroy();
    _paroChart = new Chart(canvas.getContext('2d'), {
        type: 'line',
        data: {
            labels: series.labels,
            datasets: [{
                label: series.scope + ' — Tasa de Paro',
                data: series.values,
                borderColor: '#FF6600',
                backgroundColor: 'rgba(255,102,0,0.08)',
                fill: true,
                tension: 0.3,
                borderWidth: 2.5,
                pointRadius: 0,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: { callbacks: { label: ctx => `${ctx.parsed.y.toFixed(1)}%` } }
            },
            scales: {
                y: { title: { display: true, text: '%' }, beginAtZero: true },
                x: { ticks: { maxTicksLimit: 10 } }
            }
        }
    });
}

function renderScatterChart(scatter) {
    const canvas = document.getElementById('scatterAccessChart');
    if (!canvas || !scatter) return;
    if (_scatterChart) _scatterChart.destroy();

    // Build scatter points
    const points = scatter.labels.map((lbl, i) => ({
        x: scatter.pib_pc[i],
        y: scatter.precio_m2[i],
        prov: lbl,
        paro: scatter.tasa_paro[i],
    }));

    // Color by tasa_paro
    const minParo = Math.min(...scatter.tasa_paro);
    const maxParo = Math.max(...scatter.tasa_paro);
    const bgColors = points.map(p => {
        const t = (p.paro - minParo) / (maxParo - minParo + 0.001);
        const r = Math.round(255 * t);
        const b = Math.round(192 * (1 - t));
        return `rgba(${r}, 100, ${b}, 0.75)`;
    });

    _scatterChart = new Chart(canvas.getContext('2d'), {
        type: 'scatter',
        data: {
            datasets: [{
                label: `Provincias (${scatter.year}) — color = Tasa Paro`,
                data: points.map(p => ({ x: p.x, y: p.y })),
                backgroundColor: bgColors,
                pointRadius: 7,
                pointHoverRadius: 9,
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: true, position: 'bottom' },
                tooltip: {
                    callbacks: {
                        label: (ctx) => {
                            const p = points[ctx.dataIndex];
                            return [`${p.prov}`, `PIB/pc: ${p.x.toLocaleString('es')}€`, `Precio m²: ${p.y.toLocaleString('es')}€`, `Paro: ${p.paro.toFixed(1)}%`];
                        }
                    }
                }
            },
            scales: {
                x: { title: { display: true, text: 'PIB per cápita (€)' } },
                y: { title: { display: true, text: 'Precio m² (€)' }, beginAtZero: false }
            }
        }
    });
}
