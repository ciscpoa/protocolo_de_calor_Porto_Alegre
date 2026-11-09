# Protocolo de Calor — Porto Alegre

Painel público com a previsão do tempo e os alertas de calor para os próximos 5 dias, pelos gatilhos
do Protocolo de Calor de Porto Alegre (Temporada 2026/2027). A página fica em `docs/` e é publicada
pelo GitHub Pages. Uma automação (GitHub Actions) refaz a previsão a cada 3 horas.

## O que o painel mostra

- **Nível de alerta do dia** (1 Normalidade, 2 Atenção, 3 Alerta, 4 Perigo, 5 Emergência), com o motivo,
  o horário mais crítico e o que fazer, em linguagem simples.
- **Próximos 5 dias:** nível, condição do tempo, máxima e mínima, sensação térmica e chuva.
- **Hora a hora:** sensação térmica (UTCI) e temperatura, com as faixas do protocolo e a diferença
  entre os modelos; chuva por hora.
- **Detalhes técnicos:** ECMWF × GFS, UTCI, IBUTG (escala ocupacional), chuva,
  probabilidade de chuva forte na vizinhança (NMEP), vento, gatilho e taxa metabólica admissível (NR-15).

## Página

- Layout fluido (CSS grid e `clamp()`), testado de 320 px (celular) a 2560 px (monitor): 1, 2 ou 3 colunas
  conforme a largura, sem rolagem lateral. Tema claro e escuro.
- A sensação térmica (UTCI), que aciona os gatilhos, é o número principal: quadro próprio com régua das faixas
  do protocolo e horas acima de 28, 34 e 38 °C; destaque nos cartões dos dias e no gráfico hora a hora.
- Gráfico hora a hora com seletor de modelo (Consenso, ECMWF, GFS) e legenda clicável para mostrar ou
  esconder linhas; fundo com as faixas: < 10 °C (azul), 10–28 °C (verde) e os limites do protocolo.
- Chuva por hora dos dois modelos lado a lado, sem média, com legenda clicável.
- Na publicação (GitHub Actions), `gerar_painel.py` carimba a versão nos endereços dos scripts
  (`app.js?v=AAAAMMDDHHMM`), para o navegador não usar arquivos antigos guardados na memória.
- Botão "Compartilhar este alerta" (WhatsApp ou menu de compartilhamento do celular) e imagem de prévia
  (`docs/img/compartilhar.png`) para links enviados em aplicativos.
- Logos em `docs/img/`: barra institucional (DVS/SMS, SUS, Prefeitura de Porto Alegre) e marca do CISC.
- Sem frameworks de CSS: HTML, CSS próprio e D3 (gráficos), sem dependências externas na hora de abrir.

## Versão anterior (cópia de segurança)

A primeira versão do painel (09/11/2026) está guardada de três formas:
- marca de versão `v1` e ramo `painel-v1` no repositório;
- cópia navegável, com dados congelados, em `docs/versao-anterior/`
  (https://ciscpoa.github.io/protocolo_de_calor_Porto_Alegre/versao-anterior/).

Para voltar à versão anterior: `git checkout v1 -- docs/index.html docs/app.js` e enviar (push).

## Como o nível é calculado

Sensação térmica (UTCI) do consenso multimodelo (média do ECMWF IFS e do NOAA GFS) no centro de Porto
Alegre (−30,08; −51,21):

| Nível | Gatilho diário |
|---|---|
| 5 Emergência | UTCI ≥ 48 °C por mais de 1 h |
| 4 Perigo | UTCI ≥ 38 °C por mais de 2 h |
| 3 Alerta | UTCI ≥ 34 °C por mais de 2 h |
| 2 Atenção | UTCI ≥ 32 °C por 4 h ou ≥ 28 °C por 7 h: no 1º dia se a madrugada (0h–6h) for ≥ 22 °C; com madrugada de 20–22 °C, a partir do 2º dia seguido |
| 1 Normalidade | abaixo disso, ou calor com madrugada < 20 °C |

Regras entre dias: **persistência** (N2 com madrugada amena só a partir do 2º dia), **rampa** (N1 com UTCI
máx. ≥ 30 °C vira N2 se o dia seguinte for N3+), **acúmulo** (N2 > 3 dias → N3; N3 > 2 dias → N4; N4 ≥ 2 dias
→ N5) e **rescaldo** (depois de N3+, um dia que cairia para N1 fica em N2). Essas regras olham também os
3 dias anteriores à previsão. O horário crítico é o do nível final do dia. Os testes em `tests/` cobrem cada regra.

## Rodar localmente

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q tests     # testes dos gatilhos
.venv/bin/python gerar_painel.py        # baixa a previsão e grava docs/dados/
```

Depois, abra `docs/index.html` no navegador (funciona sem servidor).

| Arquivo | Conteúdo |
|---|---|
| `calor/indices.py` | Geometria solar, Tmrt (ERA5-HEAT), UTCI e IBUTG |
| `calor/protocolo.py` | Gatilhos diários, rampa, acúmulo, rescaldo, estabilidade do tempo e textos para o público |
| `calor/previsao.py` | Download (Open-Meteo), vizinhança de 55 km e probabilidade de chuva (NMEP) |
| `gerar_painel.py` | Junta tudo e grava `docs/dados/previsao.js` e `previsao.json` |
| `docs/` | Página do painel (HTML + D3, sem servidor) |
| `.github/workflows/atualizar_painel.yml` | Atualização automática a cada 3 horas |

## Observações sobre o código de origem

- **UTCI:** usa a implementação de referência da biblioteca pythermalcomfort (mesmos coeficientes de
  Bröde et al., 2012, e mesma pressão de vapor de Hardy ITS-90 do código original). Na cópia do código,
  os operadores `*` e `**` do polinômio se perderam.
- **Operadores restaurados:** haversine (`** 2`) e coeficiente de convecção do globo no IBUTG
  (`6,3 · v^0,6 / D^0,4`).
- **PET e índice de calor da NOAA** foram retirados: não fazem parte da análise do protocolo.
- **Tmrt no esquema ERA5-HEAT completo** (Di Napoli et al., 2020), o método declarado no código
  (`METODO_TMRT = 'ECMWF_ERA5'`): fator de área projetada `0,308·cos[h·(0,998 − h²/50000)]` com h em graus
  (o código usava `γ²/4,92` com γ em radianos) e radiação direta normal ao sol, no instante da hora (o
  código usava a direta horizontal, média da hora anterior). Na semana de 09/11/2026, a UTCI máxima diária
  ficou ~1 °C menor que no código original, e os níveis passaram de 1-2-3-3-2 para 1-1-2-3-2.
- **Persistência do Nível 2:** o comentário do código original pedia 2 dias seguidos quando a madrugada fica
  entre 20 e 22 °C, mas o código não aplicava a regra. Agora aplica, com os 3 dias anteriores como contexto.

## Dados

Previsões ECMWF IFS 0,25° e NOAA GFS (determinísticas e ensembles), via [Open-Meteo](https://open-meteo.com/)
(CC BY 4.0). O painel é informativo e não substitui os avisos oficiais da Defesa Civil e da Saúde.
