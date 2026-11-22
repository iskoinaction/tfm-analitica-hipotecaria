/* Renderizador genérico de "vistas" declarativas procedentes de artifacts/ (ver services/views.py).
   Tipos: metrics, timeseries, bar, table, choropleth, note, invalid. Sin innerHTML. */
(function () {
  "use strict";
  var A = window.Atalaya;
  var redraws = [];

  function chartDefaults() {
    if (!window.Chart) return false;
    Chart.defaults.font.family = A.cssVar("--font-sans", "system-ui");
    Chart.defaults.color = A.cssVar("--chart-axis", "#5b6b80");
    Chart.defaults.borderColor = A.cssVar("--chart-grid", "#e8ecf1");
    Chart.defaults.maintainAspectRatio = false;
    Chart.defaults.animation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 };
    return true;
  }

  function tableFrom(columns, rows, caption) {
    var thead = A.el("thead", null, [A.el("tr", null, columns.map(function (c) { return A.el("th", { scope: "col", text: c }); }))]);
    var tbody = A.el("tbody", null, rows.map(function (r) {
      return A.el("tr", null, r.map(function (c) {
        var isNum = typeof c === "number";
        return A.el("td", { class: isNum ? "num" : null, text: isNum ? A.fmt(c) : (c === null || c === undefined ? "—" : String(c)) });
      }));
    }));
    var t = A.el("table", { class: "table" }, [caption ? A.el("caption", { text: caption }) : null, thead, tbody]);
    return A.el("div", { class: "table-wrap" }, [t]);
  }

  function withTableToggle(card, makeTable) {
    var holder = A.el("div", { class: "view-table", hidden: true });
    var btn = A.el("button", { type: "button", class: "btn btn--ghost", "aria-expanded": "false", text: "Ver tabla" });
    btn.addEventListener("click", function () {
      var open = holder.hasAttribute("hidden");
      if (open && !holder.firstChild) holder.appendChild(makeTable());
      if (open) holder.removeAttribute("hidden"); else holder.setAttribute("hidden", "");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.textContent = open ? "Ocultar tabla" : "Ver tabla";
    });
    card.querySelector(".card__header").appendChild(A.el("div", { class: "view-actions" }, [btn]));
    card.appendChild(holder);
  }

  function lineDatasets(view) {
    var ds = [], colorIdx = 0, bandFor = null;
    var lower = view.series.filter(function (s) { return s.role === "lower"; });
    var upper = view.series.filter(function (s) { return s.role === "upper"; });
    view.series.forEach(function (s) {
      if (s.role === "lower" || s.role === "upper") return;
      var color = A.seriesColor(colorIdx++);
      var isFc = s.role === "forecast" || s.role === "scenario";
      ds.push({ label: s.name + (isFc ? " (proyección)" : ""), data: s.values, borderColor: color, backgroundColor: color,
                borderDash: isFc ? [6, 4] : [], pointRadius: 0, pointHitRadius: 6, borderWidth: 2, spanGaps: false, tension: 0 });
      if (isFc && !bandFor) bandFor = color;
    });
    for (var i = 0; i < Math.min(lower.length, upper.length); i++) {
      ds.push({ label: lower[i].name, data: lower[i].values, borderWidth: 0, pointRadius: 0, fill: false, _band: true });
      ds.push({ label: upper[i].name, data: upper[i].values, borderWidth: 0, pointRadius: 0, fill: "-1",
                backgroundColor: A.cssVar("--series-forecast-band", "rgba(42,120,214,.16)"), _band: true });
    }
    return ds;
  }

  function drawChart(canvas, view) {
    if (!chartDefaults()) return null;
    var isBar = view.type === "bar";
    var unit = view.unit ? " " + view.unit : "";
    var cfg = {
      type: isBar ? "bar" : "line",
      data: {
        labels: (isBar ? view.labels : view.x).map(A.period),
        datasets: isBar ? view.series.map(function (s, i) {
          var c = A.seriesColor(i);
          return { label: s.name, data: s.values, backgroundColor: c, borderColor: c, borderRadius: 3 };
        }) : lineDatasets(view)
      },
      options: {
        indexAxis: isBar && view.horizontal ? "y" : "x",
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { labels: { filter: function (item, data) { return !data.datasets[item.datasetIndex]._band; } } },
          tooltip: { callbacks: { label: function (ctx) {
            var v = isBar && view.horizontal ? ctx.parsed.x : ctx.parsed.y;
            return ctx.dataset.label + ": " + A.fmt(v) + unit;
          } } }
        },
        scales: {
          x: { stacked: !!view.stacked, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 10 } },
          y: { stacked: !!view.stacked, ticks: { callback: function (v) { return A.fmt(v); } } }
        }
      }
    };
    return new Chart(canvas, cfg);
  }

  function header(view, bare) {
    return A.el("div", { class: "card__header" }, [A.el("div", null, [
      bare ? null : A.el("h3", { class: "card__title", text: view.title }),
      view.subtitle ? A.el("p", { class: "card__subtitle", text: view.subtitle }) : null
    ])]);
  }

  function renderView(view, opts) {
    opts = opts || {};
    var card = A.el(opts.bare ? "div" : "section", { class: opts.bare ? "view-bare" : "card", "data-view-type": view.type });
    card.appendChild(header(view, opts.bare));
    if (view.description) card.appendChild(A.el("p", { class: "view-description", text: view.description }));

    if (view.type === "invalid") {
      card.appendChild(A.el("p", { class: "view-invalid", text: "Vista no válida en el artefacto: " + view.error }));
    } else if (view.type === "metrics") {
      card.appendChild(A.el("div", { class: "metrics-grid" }, view.items.map(function (it) {
        return A.el("div", { class: "metric kpi" }, [
          A.el("span", { class: "kpi__label", text: it.label }),
          A.el("span", { class: "kpi__value num", text: A.fmt(it.value) }, [it.unit ? A.el("span", { class: "kpi__unit", text: it.unit }) : null]),
          it.period ? A.el("span", { class: "kpi__period", text: A.period(it.period) }) : null,
          it.note ? A.el("span", { class: "kpi__period", text: it.note }) : null
        ]);
      })));
    } else if (view.type === "timeseries" || view.type === "bar") {
      if (opts.span) card.setAttribute("data-span", opts.span);
      var hasFc = view.series && view.series.some(function (s) { return s.role === "forecast" || s.role === "scenario"; });
      if (hasFc) card.querySelector(".card__header > div").appendChild(A.el("span", { class: "badge badge--forecast", text: "Incluye proyección" }));
      var canvas = A.el("canvas", { role: "img", "aria-label": view.title + (view.unit ? " (" + view.unit + ")" : "") });
      card.appendChild(A.el("div", { class: "chart" }, [canvas]));
      var chart = null;
      var draw = function () { if (chart) chart.destroy(); chart = drawChart(canvas, view); };
      redraws.push(draw);
      requestAnimationFrame(draw);
      withTableToggle(card, function () {
        var labels = view.type === "bar" ? view.labels : view.x;
        var cols = [view.type === "bar" ? "Categoría" : "Periodo"].concat(view.series.map(function (s) { return s.name + (view.unit ? " (" + view.unit + ")" : ""); }));
        var rows = labels.map(function (l, i) { return [A.period(l)].concat(view.series.map(function (s) { return s.values[i]; })); });
        return tableFrom(cols, rows, view.title);
      });
    } else if (view.type === "table") {
      card.appendChild(tableFrom(view.columns, view.rows, null));
    } else if (view.type === "choropleth") {
      var holder = A.el("div", { class: "map" });
      card.appendChild(holder);
      if (window.AtalayaMap) window.AtalayaMap.render(holder, view.values, { unit: view.unit, period: view.period, label: view.title });
      withTableToggle(card, function () {
        var rows = Object.keys(view.values).sort().map(function (k) { return [window.AtalayaMap ? window.AtalayaMap.name(k) : k, view.values[k]]; });
        return tableFrom(["Provincia", view.unit || "Valor"], rows, view.title);
      });
    } else if (view.type === "note") {
      card.appendChild(A.el("p", { text: view.text }));
    }
    if (view.source) card.appendChild(A.el("p", { class: "card__source", text: "Fuente: " + view.source }));
    return card;
  }

  function renderInto(container, views, opts) {
    A.clear(container);
    (views || []).forEach(function (v) { container.appendChild(renderView(v, opts)); });
    if (!views || !views.length) container.appendChild(A.el("p", { class: "muted", text: "El artefacto no contiene vistas." }));
  }

  window.AtalayaViews = { renderInto: renderInto, renderView: renderView, tableFrom: tableFrom, redraws: redraws };

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-views]").forEach(function (c) {
      var src = document.getElementById(c.getAttribute("data-views"));
      var views = [];
      try { views = JSON.parse(src ? src.textContent : "[]"); } catch (e) { views = [{ type: "invalid", title: "Vistas", error: "JSON no válido" }]; }
      renderInto(c, views, { span: c.getAttribute("data-span-charts") });
    });
  });
  document.addEventListener("atalaya:theme", function () { redraws.forEach(function (f) { f(); }); });
})();
