/* Demanda: alterna entre las vistas nacionales del artefacto y las de la provincia elegida. */
(function () {
  "use strict";
  var A = window.Atalaya, V = window.AtalayaViews;
  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-scope-root]");
    if (!root) return;
    var select = document.getElementById(root.getAttribute("data-prov-select"));
    var nat = root.querySelector("[data-scope-national]");
    var prov = root.querySelector("[data-scope-provincial]");
    var status = root.querySelector("[data-scope-status]");
    var target = root.querySelector("[data-scope-views]");
    var domain = root.getAttribute("data-domain"), scope = root.getAttribute("data-scope");
    if (!select) return;
    select.addEventListener("change", function () {
      var code = select.value;
      if (!code) { nat.hidden = false; prov.hidden = true; return; }
      nat.hidden = true; prov.hidden = false;
      var name = select.options[select.selectedIndex].text;
      status.textContent = "Cargando resultados del modelo para " + name + "…";
      A.clear(target);
      A.fetchJSON("/api/v1/artifacts/" + domain + "/scope/" + scope + "/" + encodeURIComponent(code)).then(function (r) {
        if (!r.ok) { status.textContent = r.data.error || "No se pudieron cargar los resultados."; return; }
        if (r.data.meta.status !== "ok") {
          status.textContent = "Artefacto de demanda no generado. Ejecuta: " + r.data.meta.command;
        } else if (!r.data.available) {
          status.textContent = "El artefacto de demanda no incluye resultados provinciales para " + name + ".";
        } else {
          var m = r.data.meta;
          status.textContent = "Resultados del modelo para " + name + " · Generado: " + (m.generated_at_display || "—") +
            " · Fuente: " + m.sources.map(function (s) { return s.name; }).join("; ");
          V.renderInto(target, r.data.views, {});
        }
      });
    });
  });
})();
