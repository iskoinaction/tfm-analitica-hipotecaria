/* Widgets del panel observado: series, mapa y ranking desde /api/v1/panel/*. */
(function () {
  "use strict";
  var A = window.Atalaya, V = window.AtalayaViews;
  var API = "/api/v1/panel/";

  function sel(id) { return id ? document.getElementById(id) : null; }
  function qs(params) {
    return Object.keys(params).filter(function (k) { return params[k]; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); }).join("&");
  }
  function sourceLine(d, extra) {
    var t = "Fuente: " + (d.var_source ? d.var_source + " (" + d.source + ")" : d.source) + (d.aggregation ? " · " + d.aggregation : "") + (extra ? " · " + extra : "");
    return A.el("p", { class: "card__source", text: t });
  }

  function series(node) {
    var varSel = sel(node.getAttribute("data-var-select")), provSel = sel(node.getAttribute("data-prov-select"));
    var extra = node.getAttribute("data-extra-var");
    function load() {
      var v = varSel ? varSel.value : node.getAttribute("data-panel-series");
      var prov = provSel ? provSel.value : "";
      var reqs = [A.fetchJSON(API + "series?" + qs({ var: v, prov: prov }))];
      if (extra) reqs.push(A.fetchJSON(API + "series?" + qs({ var: extra, prov: prov })));
      A.clear(node);
      node.appendChild(A.el("div", { class: "skeleton", "aria-hidden": "true" }));
      Promise.all(reqs).then(function (res) {
        var bad = res.filter(function (r) { return !r.ok; })[0];
        if (bad) return A.errorState(node, bad.data.error || "No se pudieron cargar los datos.", load);
        var main = res[0].data;
        var x = main.x.slice();
        if (res[1]) res[1].data.x.forEach(function (p) { if (x.indexOf(p) < 0) x.push(p); });
        x.sort();
        var mk = function (d) {
          var m = {}; d.x.forEach(function (p, i) { m[p] = d.values[i]; });
          return { name: d.label + " (" + d.unit + ")", values: x.map(function (p) { return p in m ? m[p] : null; }), role: "observed" };
        };
        var spec = { type: "timeseries", title: main.label + " · " + main.scope, x: x,
                     series: [mk(main)].concat(res[1] ? [mk(res[1].data)] : []), unit: res[1] ? "" : main.unit };
        A.clear(node);
        if (!x.length) return node.appendChild(A.el("p", { class: "muted", text: "Sin datos para esta selección." }));
        node.appendChild(V.renderView(spec, { bare: true }));
        node.appendChild(sourceLine(main, "datos observados"));
      });
    }
    [varSel, provSel].forEach(function (s) { if (s) s.addEventListener("change", load); });
    load();
  }

  function map(node) {
    var varSel = sel(node.getAttribute("data-var-select"));
    function load() {
      var v = varSel ? varSel.value : "hipotecas_total";
      A.fetchJSON(API + "choropleth?" + qs({ var: v })).then(function (r) {
        if (!r.ok) return A.errorState(node, r.data.error || "No se pudo cargar el mapa.", load);
        var d = r.data;
        A.clear(node);
        var spec = { type: "choropleth", title: d.label, values: d.values, unit: d.unit, period: d.period };
        node.appendChild(V.renderView(spec, { bare: true }));
        node.appendChild(sourceLine(d, "ámbito de la variable: " + d.scope_note));
      });
    }
    if (varSel) varSel.addEventListener("change", load);
    load();
  }

  function ranking(node) {
    var varSel = sel(node.getAttribute("data-var-select"));
    function load() {
      var v = varSel ? varSel.value : node.getAttribute("data-panel-ranking");
      A.fetchJSON(API + "ranking?" + qs({ var: v, n: node.getAttribute("data-n") || "10" })).then(function (r) {
        if (!r.ok) return A.errorState(node, r.data.error || "No se pudo cargar el ranking.", load);
        var d = r.data;
        A.clear(node);
        var spec = { type: "bar", title: d.label + " · " + A.period(d.period), labels: d.labels, horizontal: true,
                     series: [{ name: d.label + " (" + d.unit + ")", values: d.values }], unit: d.unit };
        var view = V.renderView(spec, { bare: true });
        var chart = view.querySelector(".chart");
        if (chart) chart.style.height = Math.max(260, d.labels.length * 26) + "px";
        node.appendChild(view);
        node.appendChild(sourceLine(d, "periodo " + A.period(d.period)));
      });
    }
    if (varSel) varSel.addEventListener("change", load);
    load();
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-panel-series]").forEach(series);
    document.querySelectorAll("[data-panel-map]").forEach(map);
    document.querySelectorAll("[data-panel-ranking]").forEach(ranking);
  });
})();
