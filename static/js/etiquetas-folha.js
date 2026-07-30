// Abre a caixa de impressão assim que a folha de etiquetas carrega.
//
// Arquivo estático em vez de script inline por causa da CSP
// (`script-src 'self'`, ver core/middleware.py).
//
// `window.print()` é chamado depois de `load` (e não em `DOMContentLoaded`)
// porque os QR Codes são imagens `data:` embutidas: imprimir antes de estarem
// decodificadas geraria etiquetas com o espaço do QR em branco — papel de
// etiqueta perdido, que é o insumo caro aqui.
window.addEventListener("load", function () {
  window.print();
});

var botao = document.getElementById("imprimir-agora");
if (botao) {
  botao.addEventListener("click", function () {
    window.print();
  });
}
