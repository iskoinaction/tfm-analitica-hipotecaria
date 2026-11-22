/* Simulador: valida en cliente lo básico, envía a /api/v1/simulator/simulate (CSRF) y pinta el
   resultado del motor src.advisor de forma genérica y segura (textContent, sin HTML del servidor). */
(function () {
  "use strict";
  var A = window.Atalaya, V = window.AtalayaViews;
  var LABELS = {
    dsti: "DSTI (cuota / ingresos)", ltv: "LTV (préstamo / valor)", lti: "LTI (préstamo / ingresos anuales)",
    tin: "TIN", tae: "TAE", cuota_mensual: "Cuota mensual", importe_prestamo: "Importe del préstamo",
    entrada_necesaria: "Entrada necesaria", gastos: "Gastos de compra", estres: "Estrés de tipos",
    semaforo: "Capacidad de pago", avisos: "Avisos", supuestos: "Supuestos", fuente: "Fuente", fecha: "Fecha"
  };
  var NUMERIC = ["precio_vivienda", "superficie_m2", "ingresos_netos_mensuales", "ahorro_disponible", "otras_deudas_mensuales", "edad", "plazo_anios"];

  function human(k) {
    if (LABELS[k]) return LABELS[k];
    var s = String(k).replace(/_/g, " ");
    return s.charAt(0).toUpperCase() + s.slice(1);
  }
  function scalar(v) { return v === null || typeof v !== "object"; }
  function valueText(v) {
    if (typeof v === "boolean") return v ? "sí" : "no";
    if (typeof v === "number") return A.fmt(v);
    return v === null || v === undefined ? "—" : String(v);
  }
  function semaforoBadge(v) {
    var s = String(v).toLowerCase();
    var cls = /verde|green|holgad|asumible/.test(s) ? "good" : (/rojo|red|elevad|no asumible/.test(s) ? "crit" : (/ambar|ámbar|amarill|ajustad|amber/.test(s) ? "warn" : "neutral"));
    var icon = { good: "● ", warn: "▲ ", crit: "■ ", neutral: "○ " }[cls];
    return A.el("span", { class: "badge semaforo badge--" + cls, text: icon + String(v) });
  }
  function kvList(obj) {
    var dl = A.el("dl", { class: "kv" });
    Object.keys(obj).forEach(function (k) {
      var v = obj[k];
      if (!scalar(v)) v = Array.isArray(v) ? v.map(valueText).join(", ") : JSON.stringify(v);
      dl.appendChild(A.el("dt", { text: human(k) }));
      dl.appendChild(A.el("dd", { text: valueText(v) }));
    });
    return dl;
  }
  function renderValue(v) {
    if (scalar(v)) return A.el("p", { text: valueText(v) });
    if (Array.isArray(v)) {
      if (!v.length) return A.el("p", { class: "muted", text: "—" });
      if (v.every(scalar)) return A.el("ul", { class: "list-plain" }, v.map(function (x) { return A.el("li", { text: valueText(x) }); }));
      var cols = [];
      v.forEach(function (row) { if (row && typeof row === "object") Object.keys(row).forEach(function (k) { if (cols.indexOf(k) < 0) cols.push(k); }); });
      var rows = v.map(function (row) { return cols.map(function (c) { var x = row ? row[c] : null; return scalar(x) ? (typeof x === "boolean" ? valueText(x) : x) : JSON.stringify(x); }); });
      return V.tableFrom(cols.map(human), rows, null);
    }
    var simple = {}, nested = [];
    Object.keys(v).forEach(function (k) { if (scalar(v[k]) || (Array.isArray(v[k]) && v[k].every(scalar))) simple[k] = v[k]; else nested.push(k); });
    var box = A.el("div", { class: "stack" });
    if (Object.keys(simple).length) box.appendChild(kvList(simple));
    nested.forEach(function (k) { box.appendChild(A.el("h4", { text: human(k) })); box.appendChild(renderValue(v[k])); });
    return box;
  }

  function renderResult(body, data) {
    A.clear(body);
    var res = data.result || {};
    var semKey = Object.keys(res).filter(function (k) { return /semaforo|capacidad/.test(k) && scalar(res[k]); })[0];
    if (semKey) body.appendChild(A.el("p", null, [human(semKey) + ": ", semaforoBadge(res[semKey])]));
    var top = {};
    Object.keys(res).forEach(function (k) { if (k !== semKey && scalar(res[k])) top[k] = res[k]; });
    if (Object.keys(top).length) body.appendChild(A.el("section", { class: "result-section" }, [A.el("h3", { text: "Resumen" }), kvList(top)]));
    Object.keys(res).forEach(function (k) {
      if (k === semKey || scalar(res[k])) return;
      body.appendChild(A.el("section", { class: "result-section" }, [A.el("h3", { text: human(k) }), renderValue(res[k])]));
    });
    if (data.engine_version) body.appendChild(A.el("p", { class: "card__source", text: "Motor src.advisor v" + data.engine_version }));
  }

  function setStep(n) {
    document.querySelectorAll(".stepper li").forEach(function (li) {
      if (li.getAttribute("data-step") === String(n)) li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var form = document.getElementById("sim-form");
    if (!form) return;
    var summary = document.getElementById("sim-errors"), list = document.getElementById("sim-errors-list");
    var out = document.getElementById("sim-result"), body = document.getElementById("sim-result-body");
    var btn = document.getElementById("sim-submit");
    form.addEventListener("focusin", function (e) { setStep(e.target.closest("fieldset") === form.querySelectorAll("fieldset")[1] ? 2 : 1); });

    function clearErrors() {
      summary.hidden = true; A.clear(list);
      form.querySelectorAll("[aria-invalid]").forEach(function (n) { n.removeAttribute("aria-invalid"); });
      form.querySelectorAll(".field__error").forEach(function (n) { n.textContent = ""; });
    }
    function showErrors(errors) {
      Object.keys(errors).forEach(function (k) {
        var input = document.getElementById(k), err = document.getElementById(k + "-err");
        if (input) input.setAttribute("aria-invalid", "true");
        if (err) err.textContent = errors[k];
        var item = A.el("li");
        if (input) { var a = A.el("a", { href: "#" + k, text: (form.querySelector('label[for="' + k + '"]') || { textContent: k }).textContent + ": " + errors[k] }); item.appendChild(a); }
        else item.textContent = errors[k];
        list.appendChild(item);
      });
      summary.hidden = false; summary.focus();
    }
    function payload() {
      var fd = new FormData(form), p = {};
      ["prov_code", "anio", "escenario", "tipo_interes", "tipo_vivienda"].forEach(function (k) { if (fd.get(k)) p[k] = fd.get(k); });
      NUMERIC.forEach(function (k) {
        var raw = String(fd.get(k) || "").trim().replace(/\./g, "").replace(",", ".");
        if (raw !== "") p[k] = raw;
      });
      if (p.anio) p.anio = parseInt(p.anio, 10);
      p.primera_vivienda = !!document.getElementById("primera_vivienda").checked;
      return p;
    }
    form.addEventListener("reset", function () { clearErrors(); out.hidden = true; setStep(1); });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearErrors();
      btn.disabled = true; btn.setAttribute("aria-busy", "true"); btn.textContent = "Calculando…";
      A.fetchJSON(form.getAttribute("data-endpoint"), { method: "POST", body: payload() }).then(function (r) {
        btn.disabled = false; btn.removeAttribute("aria-busy"); btn.textContent = "Calcular";
        if (r.status === 400 && r.data.errors) return showErrors(r.data.errors);
        out.hidden = false; setStep(3);
        if (r.status === 503 && r.data.status === "pending") {
          A.clear(body); body.appendChild(A.el("p", { class: "callout callout--warn", text: "Motor de cálculo pendiente: " + r.data.reason }));
        } else if (!r.ok) {
          A.errorState(body, r.data.error || "No se pudo completar la simulación.", function () { form.requestSubmit(); });
        } else {
          renderResult(body, r.data);
        }
        out.focus();
      });
    });
  });
})();
