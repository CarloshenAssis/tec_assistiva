// Cadastro rápido de Subcategoria/Fornecedor embutido no formulário de
// Ativo — popup com só o nome, sem sair da tela. Arquivo estático em vez
// de onclick/onsubmit inline por causa da CSP (script-src 'self', ver
// core/middleware.py).

function lerCookie(nome) {
  const valor = "; " + document.cookie;
  const partes = valor.split("; " + nome + "=");
  if (partes.length === 2) return partes.pop().split(";").shift();
  return "";
}

document.addEventListener("click", function (evento) {
  const botaoAbrir = evento.target.closest("[data-abrir-modal]");
  if (botaoAbrir) {
    document.getElementById(botaoAbrir.dataset.abrirModal).showModal();
  }
  const botaoFechar = evento.target.closest("[data-fechar-modal]");
  if (botaoFechar) {
    botaoFechar.closest("dialog").close();
  }
});

document.addEventListener("submit", function (evento) {
  const form = evento.target;
  if (!form.matches("[data-cadastro-rapido]")) return;
  evento.preventDefault();

  const erroEl = form.querySelector("[data-erro]");
  erroEl.hidden = true;

  const dados = new FormData(form);

  if (form.dataset.categoriaOrigem) {
    const categoriaSelect = document.getElementById(form.dataset.categoriaOrigem);
    if (!categoriaSelect.value) {
      erroEl.textContent = "Escolha a categoria antes de cadastrar a subcategoria.";
      erroEl.hidden = false;
      return;
    }
    dados.set("categoria_id", categoriaSelect.value);
  }

  fetch(form.action, {
    method: "POST",
    headers: { "X-CSRFToken": lerCookie("csrftoken") },
    body: dados,
  })
    .then(function (resposta) {
      return resposta.json().then(function (json) {
        return { ok: resposta.ok, json: json };
      });
    })
    .then(function (resultado) {
      if (!resultado.ok) {
        erroEl.textContent = resultado.json.erro || "Não foi possível cadastrar.";
        erroEl.hidden = false;
        return;
      }
      const alvoSelect = document.getElementById(form.dataset.alvoSelect);
      const novaOpcao = document.createElement("option");
      novaOpcao.value = resultado.json.id;
      novaOpcao.textContent = resultado.json.nome;
      novaOpcao.selected = true;
      alvoSelect.appendChild(novaOpcao);
      form.reset();
      form.closest("dialog").close();
    })
    .catch(function () {
      erroEl.textContent = "Falha de conexão. Tente novamente.";
      erroEl.hidden = false;
    });
});
