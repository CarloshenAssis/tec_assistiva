// Envia o formulário de "linhas por página" assim que o usuário escolhe uma
// opção. Arquivo estático em vez de `onchange="..."` inline por causa da CSP
// (`script-src 'self'`, ver core/middleware.py) — um atributo de evento
// inline é bloqueado do mesmo jeito que um `<script>` solto.
document.addEventListener("change", function (evento) {
  if (evento.target.matches("select[name='por_pagina']")) {
    evento.target.form.submit();
  }
});
