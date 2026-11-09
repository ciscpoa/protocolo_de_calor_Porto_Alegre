"""Gera os dados do painel público do Protocolo de Calor de Porto Alegre.

Baixa as previsões (ECMWF IFS e NOAA GFS, via Open-Meteo), calcula os índices térmicos, aplica o
protocolo (gatilhos diários + persistência + rampa + acúmulo + rescaldo) e grava:
  docs/dados/previsao.js    lido pela página (window.PREVISAO)
  docs/dados/previsao.json  os mesmos dados, para reutilização
No GitHub Actions (variável GITHUB_ACTIONS), também carimba a versão nos endereços dos scripts de
docs/index.html (?v=AAAAMMDDHHMM), para o navegador não reaproveitar arquivos antigos da memória.
Uso: python gerar_painel.py
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from calor import previsao, protocolo

AQUI = Path(__file__).resolve().parent
SAIDA = AQUI / "docs" / "dados"
DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def limpar(x):
    """Converte para tipos do JSON (NaN vira null)."""
    if isinstance(x, dict):
        return {str(k): limpar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [limpar(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else round(float(x), 2)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def extremos(dia: pd.DataFrame, coluna: str) -> dict:
    s = dia[coluna]
    return {"min": s.min(), "h_min": dia.loc[s.idxmin(), "time"].strftime("%H:%M"),
            "max": s.max(), "h_max": dia.loc[s.idxmax(), "time"].strftime("%H:%M")}


def resumo_modelo(dia: pd.DataFrame, nmep: dict | None) -> dict:
    p_cen, p_max = float(dia["precip_center"].sum()), float(dia["precip_grid_max"].sum())
    codigo = protocolo.codigo_representativo(dia["weather_code"], p_cen)
    n = nmep or {10.0: None, 25.0: None, 50.0: None}
    est = protocolo.estabilidade(p_cen, p_max, codigo, n[10.0] or 0.0, n[25.0] or 0.0, n[50.0] or 0.0)
    seta, direcao = protocolo.vento_predominante(dia["wind_kmh"], dia["wind_dir"])
    return {
        "codigo": codigo, "condicao": protocolo.DESCRICAO_CODIGO[codigo], "estabilidade": est,
        "chuva_mm": p_cen, "chuva_max_grade_mm": p_max, "nmep_10": n[10.0], "nmep_25": n[25.0], "nmep_50": n[50.0],
        "ur_min": dia["rh2m"].min(), "ur_max": dia["rh2m"].max(),
        "vento_min": dia["wind_kmh"].min(), "vento_max": dia["wind_kmh"].max(), "rajada_max": dia["wind_gust_kmh"].max(),
        "vento_dir": direcao, "vento_seta": seta,
        "t2m": extremos(dia, "t2m"), "utci": extremos(dia, "utci"), "ibutg": extremos(dia, "wbgt"),
    }


def condicao_consenso(ec: dict, gf: dict) -> tuple[int, str]:
    """Ícone e texto do dia: se os modelos divergem, vale o mais severo, com 'Possível' quando for chuva."""
    if ec["codigo"] == gf["codigo"]:
        return ec["codigo"], ec["condicao"]
    pior = max((ec["codigo"], gf["codigo"]), key=lambda c: protocolo.ORDEM_CODIGO[c])
    texto = protocolo.DESCRICAO_CODIGO[pior]
    return pior, (f"Possível {texto.lower()}" if pior in (51, 63, 95) else texto)


def carimbar_versao(versao: str) -> None:
    """Troca ?v=... nos endereços de app.js, dados/previsao.js e lib/d3.min.js do index.html."""
    pagina = AQUI / "docs" / "index.html"
    html = pagina.read_text(encoding="utf-8")
    novo, n = re.subn(r'((?:app\.js|dados/previsao\.js|lib/d3\.min\.js)\?v=)[^"]*"', rf'\g<1>{versao}"', html)
    pagina.write_text(novo, encoding="utf-8")
    print(f"versão {versao} carimbada em {n} endereços de docs/index.html")


def main() -> None:
    om = previsao.cliente(str(AQUI / ".cache_openmeteo"))
    pontos, centro = previsao.pontos_vizinhanca()
    print(f"Vizinhança: {len(pontos)} pontos num raio de {previsao.RAIO_KM:.0f} km")
    det = previsao.baixar_deterministico(om, pontos)
    print("Calculando índices (UTCI e IBUTG)...")
    ec, gf = previsao.processar_modelo(det["ecmwf"], centro), previsao.processar_modelo(det["gfs"], centro)
    if not ec["time"].equals(gf["time"]):
        raise SystemExit("os horários do ECMWF e do GFS não coincidem")

    mme = pd.DataFrame({"time": ec["time"]})
    for nome, col in [("T2M", "t2m"), ("UTCI", "utci"), ("WBGT", "wbgt")]:
        mme[f"{nome}_MME"] = (ec[col] + gf[col]) / 2.0
    for df in (ec, gf, mme):
        df["date"] = df["time"].dt.date
    agora = datetime.now(ZoneInfo(previsao.FUSO))
    todos_dias = list(dict.fromkeys(ec["date"]))          # inclui os dias anteriores (contexto das regras)
    dias = [d for d in todos_dias if d >= agora.date()]  # o painel mostra de hoje em diante

    try:
        cubos = previsao.baixar_ensemble(om, pontos)
        nmep = {k: previsao.nmep_diario(c["cubo"], c["datas"], dias) for k, c in cubos.items()}
        ensemble_ok = True
    except Exception as erro:  # o painel sai sem as probabilidades
        print(f"Aviso: ensemble indisponível ({erro})", file=sys.stderr)
        nmep, ensemble_ok = {"ecmwf": {}, "gfs": {}}, False

    diag_todos = protocolo.aplicar_regras_multidiarias([protocolo.avaliar_dia(mme[mme["date"] == d]) for d in todos_dias])
    anteriores = [{"data": d.isoformat(), "nivel": x["nivel"], "gatilho": x["gatilho"]}
                  for d, x in zip(todos_dias, diag_todos) if d < agora.date()]
    diagnosticos = [x for d, x in zip(todos_dias, diag_todos) if d >= agora.date()]

    saida_dias = []
    for d, diag in zip(dias, diagnosticos):
        dia_ec, dia_gf, dia_m = ec[ec["date"] == d], gf[gf["date"] == d], mme[mme["date"] == d]
        r_ec, r_gf = resumo_modelo(dia_ec, nmep["ecmwf"].get(d)), resumo_modelo(dia_gf, nmep["gfs"].get(d))
        codigo, condicao = condicao_consenso(r_ec, r_gf)
        seta, direcao = protocolo.vento_predominante(pd.concat([dia_ec["wind_kmh"], dia_gf["wind_kmh"]]),
                                                     pd.concat([dia_ec["wind_dir"], dia_gf["wind_dir"]]))
        nivel = diag["nivel"]
        saida_dias.append({
            "data": d.isoformat(), "dia_semana": DIAS_SEMANA[d.weekday()],
            "nivel": nivel, **{k: protocolo.NIVEIS[nivel][k] for k in ("nome", "cor_fg", "cor_bg", "acao", "publico")},
            "motivo": diag["motivo"], "gatilho": diag["gatilho"], "janela": diag["janela"],
            "janela_ini": diag["janela_ini"], "janela_fim": diag["janela_fim"],
            "tmin_noite": diag["tmin_noite"], "noite_quente": diag["noite_quente"], "noite_fresca": diag["recuperacao_plena"],
            "pico_ibutg": diag["pico_ibutg"], "m_adm": diag["m_adm"], "classe_madm": protocolo.CLASSE_MADM[nivel],
            "horas_utci_28": diag["horas_n2"], "horas_utci_32": diag["horas_32"], "horas_utci_34": diag["horas_n3"],
            "horas_utci_38": diag["horas_n4"], "horas_utci_48": diag["horas_n5"],
            "temp": extremos(dia_m, "T2M_MME"), "sensacao": extremos(dia_m, "UTCI_MME"),
            "codigo": codigo, "condicao": condicao,
            "tempo": protocolo.estabilidade_publico(r_ec["estabilidade"], r_gf["estabilidade"]),
            "vento_max": max(r_ec["vento_max"], r_gf["vento_max"]), "rajada_max": max(r_ec["rajada_max"], r_gf["rajada_max"]),
            "vento_dir": direcao, "vento_seta": seta,
            "modelos": {"ecmwf": r_ec, "gfs": r_gf},
        })

    f = (ec["date"] >= agora.date()).to_numpy()
    horario = {
        "tempo": [t.strftime("%Y-%m-%dT%H:%M") for t in ec["time"][f]],
        "temp": mme["T2M_MME"].to_numpy()[f], "sensacao": mme["UTCI_MME"].to_numpy()[f],
        "sensacao_ecmwf": ec["utci"].to_numpy()[f], "sensacao_gfs": gf["utci"].to_numpy()[f],
        "temp_ecmwf": ec["t2m"].to_numpy()[f], "temp_gfs": gf["t2m"].to_numpy()[f],
        "chuva_ecmwf": ec["precip_center"].to_numpy()[f], "chuva_gfs": gf["precip_center"].to_numpy()[f],
        "umidade": ((ec["rh2m"] + gf["rh2m"]) / 2.0).to_numpy()[f],
        "vento": ((ec["wind_kmh"] + gf["wind_kmh"]) / 2.0).to_numpy()[f],
        "ibutg": mme["WBGT_MME"].to_numpy()[f],
    }
    dados = limpar({
        "gerado_em": agora.isoformat(timespec="minutes"), "local": "Porto Alegre (RS)",
        "centro": [previsao.LAT_CENTRAL, previsao.LON_CENTRAL], "raio_km": previsao.RAIO_KM, "pontos": len(pontos),
        "ensemble": ensemble_ok, "niveis": protocolo.NIVEIS, "dias": saida_dias, "dias_anteriores": anteriores,
        "horario": {k: list(v) for k, v in horario.items()},
    })
    SAIDA.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    (SAIDA / "previsao.json").write_text(texto, encoding="utf-8")
    (SAIDA / "previsao.js").write_text(f"window.PREVISAO={texto};\n", encoding="utf-8")
    if os.environ.get("GITHUB_ACTIONS") or "--carimbar" in sys.argv:
        carimbar_versao(agora.strftime("%Y%m%d%H%M"))

    print(f"\nPrevisão gerada em {agora:%d/%m/%Y %H:%M} (ensemble: {'sim' if ensemble_ok else 'não'})")
    for x in anteriores:
        print(f"  (anterior) {x['data']}  N{x['nivel']}  | {x['gatilho']}")
    for x in saida_dias:
        print(f"  {x['dia_semana']:<8} {x['data']}  N{x['nivel']} {x['nome']:<11} Tmáx {x['temp']['max']:4.1f}  "
              f"UTCI máx {x['sensacao']['max']:4.1f}  chuva EC {x['modelos']['ecmwf']['chuva_mm']:4.1f} / GFS {x['modelos']['gfs']['chuva_mm']:4.1f} mm  | {x['gatilho']}")


if __name__ == "__main__":
    main()
