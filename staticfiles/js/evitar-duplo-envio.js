// Evita reenvio duplo de formulários que fazem POST "de verdade" (navegação
// da página) — sem isso, um duplo-clique no "Salvar" (ou Enter repetido)
// enquanto a página ainda está trocando dispara duas requisições POST
// completas. Caso real: dois Ativos criados ~2s um do outro, mesma
// categoria/subcategoria, porque o botão "Salvar" nunca desabilitava.
//
// Formulários de cadastro rápido (data-cadastro-rapido) cuidam disso por
// conta própria, em cadastro-rapido.js — não duplicamos a lógica aqui.

const formulariosJaEnviados = new WeakSet();

document.addEventListener("submit", function (evento) {
  const form = evento.target;
  if (!(form instanceof HTMLFormElement) || form.hasAttribute("data-cadastro-rapido")) return;

  if (formulariosJaEnviados.has(form)) {
    evento.preventDefault();
    return;
  }
  formulariosJaEnviados.add(form);
  form.querySelectorAll('button[type="submit"]').forEach(function (botao) {
    botao.disabled = true;
  });
});
