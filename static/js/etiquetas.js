// Centro de Etiquetas — comportamento da seleção em lote.
//
// Vive em arquivo estático (e não inline no template) porque a CSP do produto
// é `script-src 'self'`, sem 'unsafe-inline' — ver core/middleware.py.
(function () {
  "use strict";

  var marcarTodos = document.getElementById("marcar-todos");
  if (!marcarTodos) {
    return;
  }

  var caixas = function () {
    return document.querySelectorAll(".marcavel");
  };

  // "Selecionar todos" marca apenas o que está visível na lista já filtrada —
  // é o que o operador espera depois de filtrar por categoria ou unidade, e
  // evita gerar uma folha com o acervo inteiro sem intenção.
  marcarTodos.addEventListener("change", function (evento) {
    caixas().forEach(function (caixa) {
      caixa.checked = evento.target.checked;
    });
    atualizarContador();
  });

  caixas().forEach(function (caixa) {
    caixa.addEventListener("change", atualizarContador);
  });

  function atualizarContador() {
    var contador = document.getElementById("contador-selecionados");
    if (!contador) {
      return;
    }
    var total = document.querySelectorAll(".marcavel:checked").length;
    contador.textContent = total === 0
      ? "Nenhum ativo selecionado"
      : total + (total === 1 ? " ativo selecionado" : " ativos selecionados");
  }

  atualizarContador();
})();
