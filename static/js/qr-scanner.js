// Leitura de QR Code pela câmera do dispositivo (docs/business-rules/qrcode.md).
//
// Usa jsQR vendorizado localmente (static/vendor/jsQR.min.js) — sem CDN
// externo, porque a CSP do produto é `script-src 'self'`
// (core/middleware.py). Roda inteiramente no navegador: nenhum frame de
// vídeo sai da máquina de quem está lendo o QR.
(function () {
  "use strict";

  var video = document.getElementById("qr-video");
  var overlay = document.getElementById("qr-overlay");
  var botaoIniciar = document.getElementById("qr-iniciar-camera");
  if (!video || !botaoIniciar || typeof window.jsQR !== "function") {
    return;
  }

  var canvas = document.createElement("canvas");
  var contexto = canvas.getContext("2d", { willReadFrequently: true });
  var streamAtivo = null;
  var lendo = false;

  function pararCamera() {
    lendo = false;
    if (streamAtivo) {
      streamAtivo.getTracks().forEach(function (faixa) {
        faixa.stop();
      });
      streamAtivo = null;
    }
  }

  function navegarSeForDoMesmoOrigem(texto) {
    // O conteúdo do QR pode ser qualquer texto — só navega se for uma URL
    // do próprio domínio, para uma etiqueta forjada não virar redirect
    // aberto para fora do sistema.
    var destino;
    try {
      destino = new URL(texto, window.location.origin);
    } catch (erro) {
      return false;
    }
    if (destino.origin !== window.location.origin) {
      return false;
    }
    window.location.href = destino.href;
    return true;
  }

  function lerFrame() {
    if (!lendo) {
      return;
    }
    if (video.readyState === video.HAVE_ENOUGH_DATA) {
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      contexto.drawImage(video, 0, 0, canvas.width, canvas.height);
      var quadro = contexto.getImageData(0, 0, canvas.width, canvas.height);
      var resultado = window.jsQR(quadro.data, quadro.width, quadro.height, {
        inversionAttempts: "dontInvert",
      });
      if (resultado && resultado.data && navegarSeForDoMesmoOrigem(resultado.data)) {
        pararCamera();
        return;
      }
    }
    window.requestAnimationFrame(lerFrame);
  }

  botaoIniciar.addEventListener("click", function () {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (overlay) {
        overlay.textContent = "Este navegador não suporta leitura por câmera — use o código manual abaixo.";
      }
      return;
    }
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: "environment" } })
      .then(function (stream) {
        streamAtivo = stream;
        video.srcObject = stream;
        video.setAttribute("playsinline", "true");
        video.play();
        lendo = true;
        botaoIniciar.style.display = "none";
        video.style.display = "block";
        window.requestAnimationFrame(lerFrame);
      })
      .catch(function () {
        if (overlay) {
          overlay.textContent = "Não foi possível acessar a câmera — use o código manual abaixo.";
        }
      });
  });

  window.addEventListener("pagehide", pararCamera);
})();
