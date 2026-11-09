// Painel público do Protocolo de Calor de Porto Alegre. Lê window.PREVISAO (dados/previsao.js),
// gerado por gerar_painel.py, e desenha com D3. Todos os números vêm desse arquivo.
"use strict";
(() => {
  const P = window.PREVISAO;
  const $ = (id) => document.getElementById(id);
  if (!P) { $("alerta").textContent = "Não foi possível carregar a previsão. Recarregue a página."; return; }

  // ------------------------------------------------------------------ formatação
  const LOC = d3.formatLocale({ decimal: ",", thousands: ".", grouping: [3], currency: ["R$", ""], minus: "−" });
  const f0 = LOC.format(".0f"), f1 = LOC.format(".1f");
  const grau = (v) => (v == null ? "—" : `${f0(v)}°`);
  const grauC = (v) => (v == null ? "—" : `${f1(v)} °C`);
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const SEM = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];
  // Horários são "hora de Porto Alegre" e ficam como UTC no navegador, para não depender do fuso de quem vê.
  const dataDe = (s) => new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10), +(s.slice(11, 13) || 0), +(s.slice(14, 16) || 0)));
  const ddmm = (s) => `${s.slice(8, 10)}/${s.slice(5, 7)}`;
  function agoraPOA() {
    const p = Object.fromEntries(new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit",
      day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date()).map((x) => [x.type, x.value]));
    return { data: `${p.year}-${p.month}-${p.day}`, quando: Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute) };
  }
  const AGORA = agoraPOA();
  const rotuloDia = (d) => {
    const amanha = new Date(Date.UTC(+AGORA.data.slice(0, 4), +AGORA.data.slice(5, 7) - 1, +AGORA.data.slice(8, 10) + 1)).toISOString().slice(0, 10);
    return d.data === AGORA.data ? "Hoje" : d.data === amanha ? "Amanhã" : d.dia_semana;
  };

  // ------------------------------------------------------------------ DOM
  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") e.className = v;
      else if (k === "style") e.style.cssText = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const f of filhos) if (f != null) e.append(f);
    return e;
  }
  const svgEl = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; };

  // Ícones do tempo (códigos representativos do protocolo: 0, 2, 3, 51, 63, 95)
  function icone(codigo, tam = 40) {
    const nuvem = `<path d="M14 30h17a7 7 0 0 0 0-14 9 9 0 0 0-17 2 6 6 0 0 0 0 12z" fill="var(--nuvem2)" stroke="var(--nuvem)" stroke-width="1.2"/>`;
    const sol = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="var(--sol)"/>` + Array.from({ length: 8 }, (_, i) => {
      const a = (i * Math.PI) / 4, r1 = r + 2.5, r2 = r + 5.5;
      return `<line x1="${cx + r1 * Math.cos(a)}" y1="${cy + r1 * Math.sin(a)}" x2="${cx + r2 * Math.cos(a)}" y2="${cy + r2 * Math.sin(a)}" stroke="var(--sol)" stroke-width="2" stroke-linecap="round"/>`;
    }).join("");
    const gotas = (n) => [12, 19, 26].slice(0, n).map((x) => `<line x1="${x}" y1="33" x2="${x - 2}" y2="38" stroke="var(--gota)" stroke-width="2" stroke-linecap="round"/>`).join("");
    const corpo = {
      0: sol(20, 20, 8),
      2: sol(26, 14, 6) + nuvem,
      3: nuvem.replace("var(--nuvem2)", "var(--nuvem)"),
      51: nuvem + gotas(2),
      63: nuvem.replace("var(--nuvem2)", "var(--nuvem)") + gotas(3),
      95: nuvem.replace("var(--nuvem2)", "var(--nuvem)") + `<path d="M21 29l-5 7h4l-2 6 7-9h-4l2-4z" fill="var(--raio)"/>`,
    }[codigo] || sol(20, 20, 8);
    return svgEl(`<svg width="${tam}" height="${tam}" viewBox="0 0 40 42" aria-hidden="true">${corpo}</svg>`);
  }

  // ------------------------------------------------------------------ tooltip e tabelas
  const tip = $("tooltip");
  function mostrarTip(x, y, titulo, linhas) {
    tip.replaceChildren(el("div", { class: "t" }, titulo), ...linhas.map((l) => {
      const k = l.cor ? el("i", { class: "k-linha", style: `background:${l.cor}` }) : null;
      return el("div", { class: "l" }, k, el("strong", {}, l.valor), el("span", {}, l.rotulo || ""));
    }));
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    let left = x + 14, top = y + 14;
    if (left + r.width > innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > innerHeight - 8) top = y - r.height - 14;
    tip.style.left = `${Math.max(8, left)}px`; tip.style.top = `${Math.max(8, top)}px`;
  }
  const esconderTip = () => { tip.hidden = true; };
  function tabela(colunas, linhas) {
    return el("table", {}, el("thead", {}, el("tr", {}, ...colunas.map((c) => el("th", { scope: "col" }, c)))),
      el("tbody", {}, ...linhas.map((l) => el("tr", {}, ...l.map((v) => el("td", {}, v))))));
  }
  const TABELAS = {};
  function vistaTabela(id) {
    const btn = document.querySelector(`[data-tabela="${id}"]`), graf = $(id);
    let vt = $(`${id}-tabela`);
    if (btn.getAttribute("aria-pressed") !== "true") { if (vt) vt.hidden = true; graf.hidden = false; return; }
    if (!vt) { vt = el("div", { id: `${id}-tabela`, class: "vista-tabela" }); graf.after(vt); }
    vt.replaceChildren(tabela(TABELAS[id].colunas, TABELAS[id].linhas));
    vt.hidden = false; graf.hidden = true;
  }
  document.querySelectorAll(".btn-tabela").forEach((b) => b.addEventListener("click", () => {
    const ativo = b.getAttribute("aria-pressed") !== "true";
    b.setAttribute("aria-pressed", String(ativo)); b.textContent = ativo ? "Gráfico" : "Tabela";
    if (!ativo) { $(b.dataset.tabela).hidden = false; desenharGraficos(); } else vistaTabela(b.dataset.tabela);
  }));

  // ------------------------------------------------------------------ estado
  const DIAS = P.dias;
  let selecionado = Math.max(0, DIAS.findIndex((d) => d.data === AGORA.data));
  const H = P.horario;
  const T = H.tempo.map(dataDe);
  const FAIXAS = [
    { de: 28, ate: 34, cor: "#facc15", nome: "Atenção" }, { de: 34, ate: 38, cor: "#ea580c", nome: "Alerta" },
    { de: 38, ate: 48, cor: "#dc2626", nome: "Perigo" }, { de: 48, ate: 70, cor: "#6b21a8", nome: "Emergência" },
  ];
  const faixaDe = (u) => (u >= 48 ? "Emergência" : u >= 38 ? "Perigo" : u >= 34 ? "Alerta" : u >= 28 ? "Atenção" : "Sem calor relevante");

  // ------------------------------------------------------------------ cabeçalho e aviso
  const gerado = P.gerado_em;
  $("atualizado").textContent = `Atualizado em ${ddmm(gerado)}/${gerado.slice(0, 4)} às ${gerado.slice(11, 16)} · consenso dos modelos ECMWF e GFS`;
  const horasDesde = (AGORA.quando - dataDe(gerado)) / 3600000;
  if (horasDesde > 12) {
    const aviso = $("aviso-dados");
    aviso.hidden = false;
    aviso.textContent = `Atenção: esta previsão foi gerada há ${Math.round(horasDesde)} horas. A atualização automática pode ter falhado; confira os avisos oficiais.`;
  }

  // ------------------------------------------------------------------ destaque do dia escolhido
  function renderDestaque() {
    const d = DIAS[selecionado];
    const a = $("alerta");
    a.style.background = d.cor_bg; a.style.color = d.cor_fg;
    const quando = rotuloDia(d) === "Hoje" ? `Hoje, ${ddmm(d.data)}` : `${rotuloDia(d)}, ${ddmm(d.data)}`;
    // replaceChildren escreveria "null" para um filho vazio; por isso o filtro
    a.replaceChildren(...[
      el("div", { class: "quando" }, `${quando} · Protocolo de Calor`),
      el("div", { class: "nivel" }, el("span", { class: "num" }, `Nível ${d.nivel}`), el("span", { class: "nome" }, d.nome)),
      el("p", { class: "motivo" }, d.motivo),
      d.janela_ini != null ? el("div", { class: "janela" }, `Horário mais crítico: ${d.janela_ini}h às ${d.janela_fim}h`) : null,
      el("h3", {}, d.nivel > 1 ? "O que fazer" : "Recomendações"),
      el("ul", {}, ...d.publico.map((t) => el("li", {}, t))),
    ].filter(Boolean));
    const t = $("tempo-dia");
    t.replaceChildren(
      el("div", { class: "linha1" }, icone(d.codigo, 56), el("div", {}, el("div", { class: "cond" }, d.condicao), el("div", { class: "estab" }, d.tempo))),
      el("div", { class: "numeros" },
        el("div", {}, el("span", {}, "Máxima"), el("strong", {}, grau(d.temp.max)), el("small", {}, ` às ${d.temp.h_max}`)),
        el("div", {}, el("span", {}, "Mínima"), el("strong", {}, grau(d.temp.min)), el("small", {}, ` às ${d.temp.h_min}`)),
        el("div", {}, el("span", {}, "Sensação térmica máxima"), el("strong", {}, grau(d.sensacao.max)), el("small", {}, ` às ${d.sensacao.h_max}`)),
        el("div", {}, el("span", {}, "Madrugada"), el("strong", {}, grau(d.tmin_noite)),
          el("small", {}, d.noite_quente ? " quente" : d.noite_fresca ? " fresca" : "")),
        el("div", {}, el("span", {}, "Chuva"), el("strong", {}, `${f1(d.chuva_mm)} mm`),
          el("small", {}, d.chance_chuva_10mm != null ? ` · ${f0(d.chance_chuva_10mm)}% de chance de 10 mm ou mais` : "")),
        el("div", {}, el("span", {}, "Vento"), el("strong", {}, `${f0(d.vento_max)} km/h`), el("small", {}, ` ${d.vento_dir} · rajadas de ${f0(d.rajada_max)}`)),
      ),
    );
  }

  // ------------------------------------------------------------------ cartões dos dias
  function renderDias() {
    $("dias").replaceChildren(...DIAS.map((d, i) => el("button", {
      class: "dia", type: "button", "aria-pressed": String(i === selecionado),
      "aria-label": `${rotuloDia(d)} ${ddmm(d.data)}: nível ${d.nivel}, ${d.nome}`,
      onclick: () => { selecionado = i; renderTudo(); },
    },
      el("div", { class: "cab" }, el("b", {}, rotuloDia(d)), el("span", {}, ddmm(d.data))),
      el("span", { class: "chip", style: `background:${d.cor_bg};color:${d.cor_fg}` }, el("i", {}, String(d.nivel)), d.nome),
      el("div", { class: "cond" }, icone(d.codigo, 30), d.condicao),
      el("div", { class: "temps" }, el("b", {}, grau(d.temp.max)), ` / ${grau(d.temp.min)}`),
      el("div", { class: "info" }, `Sensação até ${grau(d.sensacao.max)}`, el("br"),
        `Chuva ${f1(d.chuva_mm)} mm${d.chance_chuva_10mm != null ? ` · ${f0(d.chance_chuva_10mm)}% ≥10 mm` : ""}`),
      d.noite_quente ? el("span", { class: "marca" }, "Madrugada quente") : null,
    )));
  }

  // ------------------------------------------------------------------ gráficos
  const largura = (div) => Math.max(280, Math.floor(div.clientWidth || 600));
  const linhaH = (g, x1, x2, y, cor) => g.append("line").attr("x1", x1).attr("x2", x2).attr("y1", y).attr("y2", y).style("stroke", cor).style("stroke-width", 1).attr("shape-rendering", "crispEdges");
  const linhaV = (g, x, y1, y2, cor) => g.append("line").attr("x1", x).attr("x2", x).attr("y1", y1).attr("y2", y2).style("stroke", cor).style("stroke-width", 1).attr("shape-rendering", "crispEdges");
  const texto = (g, x, y, t, { ancora = "start", cor = "var(--muda)", tam = 11.5, peso = 400 } = {}) =>
    g.append("text").attr("x", x).attr("y", y).attr("dy", "0.32em").attr("text-anchor", ancora).style("fill", cor).style("font-size", `${tam}px`).style("font-weight", peso).text(t);
  const UMA_HORA = 3600000;
  const dominioX = [T[0], new Date(+T[T.length - 1] + UMA_HORA)];
  const rotuloHora = (i) => `${SEM[T[i].getUTCDay()]} ${String(T[i].getUTCDate()).padStart(2, "0")}/${String(T[i].getUTCMonth() + 1).padStart(2, "0")}, ${T[i].getUTCHours()}h`;

  function eixoDias(svg, x, m, h, comRotulo) {
    const fundo = svg.append("g").attr("class", "eixo");
    DIAS.forEach((d, i) => {
      const x0 = x(dataDe(`${d.data}T00:00`)), x1 = x(new Date(+dataDe(`${d.data}T00:00`) + 24 * UMA_HORA));
      if (i === selecionado) fundo.append("rect").attr("x", x0).attr("y", m.t).attr("width", x1 - x0).attr("height", h - m.t - m.b).style("fill", "var(--lavagem)");
      if (i > 0) linhaV(fundo, x0, m.t - 6, h - m.b, "var(--grade)");
      if (comRotulo) texto(fundo, (x0 + x1) / 2, m.t - 14, x1 - x0 > 70 ? `${SEM[dataDe(d.data).getUTCDay()]} ${ddmm(d.data)}` : ddmm(d.data),
        { ancora: "middle", cor: i === selecionado ? "var(--tinta)" : "var(--muda)", peso: i === selecionado ? 600 : 400 });
    });
    return fundo;
  }
  function linhaAgora(svg, x, m, h) {
    if (AGORA.quando < +dominioX[0] || AGORA.quando > +dominioX[1]) return;
    const xa = x(new Date(AGORA.quando));
    linhaV(svg, xa, m.t, h - m.b, "var(--tinta2)");
    texto(svg, xa + 4, h - m.b - 8, "agora", { cor: "var(--tinta2)" });
  }
  function cruz(svg, x, m, w, h, aoMostrar, aoClicar) {
    const linha = svg.append("line").style("stroke", "var(--eixo)").style("stroke-width", 1).style("display", "none");
    const pontos = svg.append("g");
    let atual = 0;
    const mostrar = (i, cx, cy) => {
      atual = i;
      const px = x(T[i]) + (x(new Date(+T[i] + UMA_HORA)) - x(T[i])) / 2;
      linha.attr("x1", px).attr("x2", px).attr("y1", m.t).attr("y2", h - m.b).style("display", null);
      pontos.selectAll("*").remove();
      const r = aoMostrar(i, pontos, px);
      if (cx == null) { const b = svg.node().getBoundingClientRect(); cx = b.left + px; cy = b.top + m.t; }
      mostrarTip(cx, cy, r.titulo, r.linhas);
    };
    const esconder = () => { linha.style("display", "none"); pontos.selectAll("*").remove(); esconderTip(); };
    const indice = (px) => Math.max(0, Math.min(T.length - 1, Math.floor((+x.invert(px) - +T[0]) / UMA_HORA)));
    svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", w - m.l - m.r).attr("height", h - m.t - m.b).style("fill", "transparent").style("cursor", "crosshair")
      .on("pointermove", (ev) => mostrar(indice(d3.pointer(ev)[0]), ev.clientX, ev.clientY))
      .on("pointerleave", esconder)
      .on("click", (ev) => aoClicar && aoClicar(indice(d3.pointer(ev)[0])));
    svg.attr("tabindex", 0).on("focus", () => mostrar(atual)).on("blur", esconder).on("keydown", (ev) => {
      if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") { ev.preventDefault(); mostrar(Math.max(0, Math.min(T.length - 1, atual + (ev.key === "ArrowLeft" ? -1 : 1)))); }
    });
  }
  const selecionarPorHora = (i) => {
    const dia = H.tempo[i].slice(0, 10), j = DIAS.findIndex((d) => d.data === dia);
    if (j >= 0 && j !== selecionado) { selecionado = j; renderTudo(); }
  };

  function graficoCalor() {
    const div = $("graf-calor"), w = largura(div), h = w < 600 ? 300 : 360;
    const m = { t: 34, r: w < 600 ? 12 : 78, b: 26, l: 38 };
    div.replaceChildren();
    const svg = d3.select(div).append("svg").attr("width", w).attr("height", h).attr("role", "img")
      .attr("aria-label", "Sensação térmica e temperatura hora a hora nos próximos 5 dias");
    const x = d3.scaleUtc().domain(dominioX).range([m.l, w - m.r]);
    const meio = (i) => new Date(+T[i] + UMA_HORA / 2);
    const minM = H.sensacao_ecmwf.map((v, i) => Math.min(v, H.sensacao_gfs[i])), maxM = H.sensacao_ecmwf.map((v, i) => Math.max(v, H.sensacao_gfs[i]));
    const lo = Math.floor(Math.min(d3.min(H.temp), d3.min(minM)) - 2), hi = Math.ceil(Math.max(d3.max(maxM), 30) + 2);
    const y = d3.scaleLinear().domain([lo, hi]).nice(6).range([h - m.b, m.t]);
    const [y0, y1] = y.domain();
    const fundo = svg.append("g");
    FAIXAS.forEach((f) => {
      const a = Math.max(f.de, y0), b = Math.min(f.ate, y1);
      if (b <= a) return;
      fundo.append("rect").attr("x", m.l).attr("width", w - m.l - m.r).attr("y", y(b)).attr("height", y(a) - y(b)).style("fill", f.cor).style("fill-opacity", "var(--faixa-op)");
      if (m.r > 40 && y(a) - y(b) > 12) texto(fundo, w - m.r + 6, (y(a) + y(b)) / 2, `${f.nome} ≥${f.de}°`, { cor: "var(--tinta2)", tam: 11 });
    });
    eixoDias(svg, x, m, h, true);
    const eixo = svg.append("g").attr("class", "eixo");
    y.ticks(6).forEach((t) => { linhaH(eixo, m.l, w - m.r, y(t), "var(--grade)"); texto(eixo, m.l - 6, y(t), `${f0(t)}°`, { ancora: "end" }); });
    [0, 6, 12, 18].forEach((hh) => T.forEach((t, i) => { if (t.getUTCHours() === hh && hh !== 0 && w > 700) texto(eixo, x(meio(i)), h - m.b + 14, `${hh}h`, { ancora: "middle" }); }));
    const plot = svg.append("g");
    plot.append("path").datum(T.map((_, i) => i)).attr("d", d3.area().x((i) => x(meio(i))).y0((i) => y(minM[i])).y1((i) => y(maxM[i])))
      .style("fill", "var(--tinta)").style("fill-opacity", 0.08);
    const linha = (arr, cor, larg) => plot.append("path").datum(T.map((_, i) => i)).attr("d", d3.line().x((i) => x(meio(i))).y((i) => y(arr[i])))
      .style("fill", "none").style("stroke", cor).style("stroke-width", larg).style("stroke-linejoin", "round").style("stroke-linecap", "round");
    linha(H.temp, "var(--s1)", 2);
    linha(H.sensacao, "var(--tinta)", 2.5);
    linhaAgora(svg, x, m, h);
    cruz(svg, x, m, w, h, (i, g, px) => {
      [[H.sensacao[i], "var(--tinta)"], [H.temp[i], "var(--s1)"]].forEach(([v, cor]) => g.append("circle").attr("cx", px).attr("cy", y(v)).attr("r", 4)
        .style("fill", cor).style("stroke", "var(--superficie)").style("stroke-width", 2));
      return { titulo: rotuloHora(i), linhas: [
        { valor: grauC(H.sensacao[i]), rotulo: `sensação térmica · ${faixaDe(H.sensacao[i])}`, cor: "var(--tinta)" },
        { valor: grauC(H.temp[i]), rotulo: "temperatura do ar", cor: "var(--s1)" },
        { valor: `${f0(minM[i])}–${f0(maxM[i])}°`, rotulo: "sensação: faixa entre os modelos" },
        { valor: `${f0(H.umidade[i])}%`, rotulo: `umidade · vento ${f0(H.vento[i])} km/h` },
      ] };
    }, selecionarPorHora);
    TABELAS["graf-calor"] = { colunas: ["Hora", "Sensação térmica (°C)", "Faixa", "Temperatura (°C)", "ECMWF (°C)", "GFS (°C)", "Umidade (%)", "Vento (km/h)"],
      linhas: T.map((_, i) => [rotuloHora(i), f1(H.sensacao[i]), faixaDe(H.sensacao[i]), f1(H.temp[i]), f1(H.sensacao_ecmwf[i]), f1(H.sensacao_gfs[i]), f0(H.umidade[i]), f0(H.vento[i])]) };
    legendaCalor();
  }
  function legendaCalor() {
    $("legenda-calor").replaceChildren(
      el("span", {}, el("i", { class: "k-linha", style: "background:var(--tinta);height:3px" }), "Sensação térmica (UTCI)"),
      el("span", {}, el("i", { class: "k-linha", style: "background:var(--s1)" }), "Temperatura do ar"),
      el("span", {}, el("i", { class: "k-caixa", style: "background:var(--tinta);opacity:.12" }), "Diferença entre os modelos"),
      ...FAIXAS.map((f) => el("span", {}, el("i", { class: "k-caixa", style: `background:${f.cor};opacity:.45` }), `${f.nome} (≥${f.de}°)`)),
    );
  }

  function graficoChuva() {
    const div = $("graf-chuva"), w = largura(div), h = 170;
    const m = { t: 26, r: w < 600 ? 12 : 78, b: 22, l: 38 };
    div.replaceChildren();
    const svg = d3.select(div).append("svg").attr("width", w).attr("height", h).attr("role", "img").attr("aria-label", "Chuva prevista por hora");
    const x = d3.scaleUtc().domain(dominioX).range([m.l, w - m.r]);
    const max = d3.max(H.chuva) || 0;
    const y = d3.scaleLinear().domain([0, Math.max(1, max * 1.1)]).nice(3).range([h - m.b, m.t]);
    eixoDias(svg, x, m, h, true);
    const eixo = svg.append("g").attr("class", "eixo");
    y.ticks(3).forEach((t) => { linhaH(eixo, m.l, w - m.r, y(t), t === 0 ? "var(--eixo)" : "var(--grade)"); texto(eixo, m.l - 6, y(t), f1(t), { ancora: "end" }); });
    const passo = x(new Date(+T[0] + UMA_HORA)) - x(T[0]), larg = Math.max(1, Math.min(24, passo - 1));
    H.chuva.forEach((v, i) => {
      if (!(v > 0.05)) return;
      const x0 = x(T[i]) + (passo - larg) / 2, topo = y(v), base = y(0), r = Math.min(2, larg / 2, base - topo);
      svg.append("path").attr("d", `M${x0},${base}V${topo + r}Q${x0},${topo} ${x0 + r},${topo}H${x0 + larg - r}Q${x0 + larg},${topo} ${x0 + larg},${topo + r}V${base}Z`).style("fill", "var(--s1)");
    });
    if (max <= 0.05) texto(svg, (m.l + w - m.r) / 2, (m.t + h - m.b) / 2, "Sem chuva prevista no período", { ancora: "middle", cor: "var(--tinta2)", tam: 13 });
    linhaAgora(svg, x, m, h);
    cruz(svg, x, m, w, h, (i) => ({ titulo: rotuloHora(i), linhas: [{ valor: `${f1(H.chuva[i])} mm`, rotulo: "chuva na hora", cor: "var(--s1)" }] }), selecionarPorHora);
    TABELAS["graf-chuva"] = { colunas: ["Hora", "Chuva (mm)"], linhas: T.map((_, i) => [rotuloHora(i), f1(H.chuva[i])]) };
  }
  function desenharGraficos() {
    esconderTip();
    graficoCalor(); graficoChuva();
    ["graf-calor", "graf-chuva"].forEach(vistaTabela);
  }

  // ------------------------------------------------------------------ níveis
  function renderNiveis() {
    $("niveis").replaceChildren(...[1, 2, 3, 4, 5].map((n) => {
      const c = P.niveis[n];
      return el("div", { class: "nivel-linha" },
        el("span", { class: "chip", style: `background:${c.cor_bg};color:${c.cor_fg}` }, el("i", {}, String(n)), c.nome),
        el("p", {}, el("strong", {}, "Quando: "), c.quando),
        el("ul", {}, ...c.publico.map((t) => el("li", {}, t))));
    }));
  }

  // ------------------------------------------------------------------ detalhes técnicos
  const corBio = (v) => (v >= 48 ? ["#6b21a8", "#fff"] : v >= 38 ? ["#dc2626", "#fff"] : v >= 34 ? ["#ea580c", "#fff"] : v >= 28 ? ["#facc15", "#111"]
    : v >= 12 ? ["#74c476", "#111"] : v >= 6 ? ["#6baed6", "#111"] : v >= 0 ? ["#3182bd", "#fff"] : ["#08519c", "#fff"]);
  const corIbutg = (v) => (v >= 33 ? ["#6b21a8", "#fff"] : v >= 30 ? ["#dc2626", "#fff"] : v >= 28 ? ["#ea580c", "#fff"] : v >= 24 ? ["#facc15", "#111"] : ["#74c476", "#111"]);
  const pilula = (v, hora, cor) => { const [bg, fg] = cor(v); return el("span", { class: "pilula", style: `background:${bg};color:${fg}` }, `${f1(v)}° (${hora})`); };
  const minMax = (x, cor) => el("span", {}, pilula(x.min, x.h_min, cor), " – ", pilula(x.max, x.h_max, cor));
  let modeloTec = "ecmwf";
  function renderTecnico() {
    const seg = $("modelo-tec");
    seg.replaceChildren(...[["ecmwf", "ECMWF IFS"], ["gfs", "NOAA GFS"]].map(([k, r]) =>
      el("button", { type: "button", "aria-pressed": String(k === modeloTec), onclick: () => { modeloTec = k; renderTecnico(); } }, r)));
    const pct = (v) => (v == null ? "—" : `${f0(v)}%`);
    const linhas = [
      ["Condição", (d, x) => `${x.condicao}`],
      ["Estabilidade", (d, x) => el("span", { class: "pilula", style: `background:${x.estabilidade.bg};color:${x.estabilidade.fg}` }, x.estabilidade.texto)],
      ["Temperatura do ar", (d, x) => minMax(x.t2m, corBio)],
      ["UTCI", (d, x) => minMax(x.utci, corBio)],
      ["PET", (d, x) => minMax(x.pet, corBio)],
      ["IBUTG (ocupacional)", (d, x) => minMax(x.ibutg, corIbutg)],
      ["Índice de calor", (d, x) => minMax(x.hi, corBio)],
      ["Chuva no centro / máx. vizinhança", (d, x) => `${f1(x.chuva_mm)} / ${f1(x.chuva_max_grade_mm)} mm`],
      ["NMEP ≥10 / ≥25 / ≥50 mm", (d, x) => `${pct(x.nmep_10)} / ${pct(x.nmep_25)} / ${pct(x.nmep_50)}`],
      ["Umidade relativa", (d, x) => `${f0(x.ur_min)}–${f0(x.ur_max)}%`],
      ["Vento / rajada", (d, x) => `${f0(x.vento_min)}–${f0(x.vento_max)} km/h ${x.vento_dir} ${x.vento_seta} · ${f0(x.rajada_max)}`],
      ["Nível do protocolo (consenso)", (d) => el("span", { class: "pilula", style: `background:${d.cor_bg};color:${d.cor_fg}` }, `N${d.nivel} ${d.nome}`)],
      ["Gatilho", (d) => d.gatilho],
      ["Janela crítica", (d) => d.janela],
      ["Mínima da madrugada (0h–6h)", (d) => `${f1(d.tmin_noite)} °C`],
      ["Horas com UTCI ≥28 / ≥32 / ≥34 / ≥38", (d) => `${d.horas_utci_28} / ${d.horas_utci_32} / ${d.horas_utci_34} / ${d.horas_utci_38} h`],
      ["Pico do IBUTG (consenso)", (d) => `${f1(d.pico_ibutg)} °C`],
      ["Taxa metabólica admissível (NR-15)", (d) => `${f0(d.m_adm)} W · ${d.classe_madm}`],
    ];
    const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", { scope: "col" }, ""), ...DIAS.map((d) => el("th", { scope: "col" }, `${d.dia_semana} ${ddmm(d.data)}`)))),
      el("tbody", {}, ...linhas.map(([rot, f]) => el("tr", {}, el("td", {}, rot), ...DIAS.map((d) => el("td", {}, f(d, d.modelos[modeloTec])))))));
    $("tabela-tec").replaceChildren(t);
  }

  // ------------------------------------------------------------------ tema, redimensionamento e início
  const raiz = document.documentElement;
  const escuro = () => (raiz.dataset.theme ? raiz.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches);
  const rotularTema = () => { $("tema").textContent = escuro() ? "Tema claro" : "Tema escuro"; };
  try { const t = localStorage.getItem("calor-tema"); if (t === "dark" || t === "light") raiz.dataset.theme = t; } catch (e) { /* sem armazenamento */ }
  rotularTema();
  $("tema").addEventListener("click", () => {
    raiz.dataset.theme = escuro() ? "light" : "dark";
    try { localStorage.setItem("calor-tema", raiz.dataset.theme); } catch (e) { /* sem armazenamento */ }
    rotularTema();
  });

  function renderTudo() { renderDestaque(); renderDias(); desenharGraficos(); }
  let espera, larguraAnterior = document.querySelector("main").clientWidth;
  new ResizeObserver(() => {
    const w = document.querySelector("main").clientWidth;
    if (w === larguraAnterior) return;
    larguraAnterior = w; clearTimeout(espera); espera = setTimeout(desenharGraficos, 150);
  }).observe(document.querySelector("main"));
  renderNiveis(); renderTecnico(); renderTudo();
})();
