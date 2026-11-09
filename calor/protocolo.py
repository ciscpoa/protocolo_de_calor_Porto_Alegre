"""Lógica do Protocolo de Calor de Porto Alegre (Temporada 2026/2027).

Mesmos gatilhos do código original:
1. Nível de cada dia pela UTCI do consenso multimodelo (média ECMWF + GFS), com exigência de horas
   e filtro noturno para o Nível 2.
1b. Persistência do Nível 2 (descrita no código original e agora aplicada): com madrugada amena
   (mínima entre 20 e 22 °C), o N2 só vale a partir do 2º dia seguido de calor; com madrugada quente
   (≥ 22 °C), vale já no 1º dia.
2. Rampa antecipatória: dia em Nível 1 vira Nível 2 se o dia seguinte for Nível 3+ e a UTCI máxima
   do dia for ≥ 30 °C.
3. Acúmulo: N2 por mais de 3 dias seguidos → N3; N3 por mais de 2 dias → N4; N4 por 2 dias ou mais → N5.
4. Rescaldo: depois de um dia em N3+, um dia que cairia para N1 fica em N2.
Por fim, o horário crítico é recalculado para o nível final do dia.

Cada nível tem o texto técnico do código (gatilho) e um texto em linguagem simples para o público.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

NIVEIS = {
    1: {"nome": "Normalidade", "cor_fg": "#15803d", "cor_bg": "#dcfce7", "acao": "Atividades físicas e trabalhos livres",
        "publico": ["Rotina normal.", "Beba água ao longo do dia."],
        "quando": "Sem calor relevante, ou calor durante o dia seguido de noite fresca (mínima abaixo de 20 °C)."},
    2: {"nome": "Atenção", "cor_fg": "#854d0e", "cor_bg": "#fef9c3", "acao": "Hidratação e vigilância aos idosos",
        "publico": ["Beba água mesmo sem sede.", "Fique de olho em idosos, crianças pequenas e pessoas com doenças crônicas."],
        "quando": "Sensação térmica de 32 °C ou mais por 4 horas, ou de 28 °C ou mais por 7 horas: já no 1º dia se a madrugada for quente (22 °C ou mais); com madrugada amena (20 a 22 °C), a partir do 2º dia seguido."},
    3: {"nome": "Alerta", "cor_fg": "#c2410c", "cor_bg": "#ffedd5", "acao": "Pausas 45/15; evitar sol 10h-16h",
        "publico": ["Evite o sol das 10h às 16h.", "No trabalho ao ar livre, faça pausas: a cada 45 minutos, 15 de descanso na sombra.",
                    "Beba água com frequência."],
        "quando": "Sensação térmica de 34 °C ou mais por 3 horas ou mais."},
    4: {"nome": "Perigo", "cor_fg": "#b91c1c", "cor_bg": "#fee2e2", "acao": "Interdição trab. pesado; abrigos",
        "publico": ["Evite esforço físico ao ar livre; trabalho pesado deve ser suspenso.", "Procure lugares frescos ou abrigos climatizados.",
                    "Não deixe crianças, idosos ou animais em carros fechados."],
        "quando": "Sensação térmica de 38 °C ou mais por 3 horas ou mais."},
    5: {"nome": "Emergência", "cor_fg": "#581c87", "cor_bg": "#f3e8ff", "acao": "Interdição geral; alerta máximo SMS",
        "publico": ["Suspenda atividades ao ar livre.", "Permaneça em local fresco e siga as orientações da Saúde e da Defesa Civil."],
        "quando": "Sensação térmica de 48 °C ou mais por 2 horas ou mais, ou calor perigoso por vários dias seguidos."},
}

# Taxa metabólica admissível de referência (NR-15) por nível, como no código original
CLASSE_MADM = {1: "≥600 W (irrestrito)", 2: "430–599 W (trabalho pesado)", 3: "285–429 W (moderado com pausas)",
               4: "145–284 W (apenas leve)", 5: "<140 W"}


def nivel_horario(utci: np.ndarray) -> np.ndarray:
    """Nível de cada hora pela UTCI: 48 / 38 / 34 / 28 °C."""
    return np.select([utci >= 48.0, utci >= 38.0, utci >= 34.0, utci >= 28.0], [5, 4, 3, 2], default=1)


def avaliar_dia(dia: pd.DataFrame) -> dict:
    """Nível base de um dia a partir do consenso multimodelo (colunas UTCI_MME, WBGT_MME, T2M_MME, time)."""
    utci = dia["UTCI_MME"].to_numpy(dtype=np.float64)
    wbgt = dia["WBGT_MME"].to_numpy(dtype=np.float64)
    t2m = dia["T2M_MME"].to_numpy(dtype=np.float64)
    horas = dia["time"].dt.hour.to_numpy()
    niveis_h = nivel_horario(utci)

    h_n5 = int(np.sum(niveis_h == 5))
    h_n4 = int(np.sum(niveis_h >= 4))
    h_n3 = int(np.sum(niveis_h >= 3))
    h_n2 = int(np.sum(niveis_h >= 2))
    h_32 = int(np.sum(utci >= 32.0))

    noite = (horas >= 0) & (horas <= 6)
    tmin_noite = float(np.min(t2m[noite])) if noite.any() else float(np.min(t2m))
    noite_quente = tmin_noite >= 22.0
    recuperacao_plena = tmin_noite < 20.0
    carga_n2 = (h_32 >= 4) or (h_n2 >= 7)
    tipo_n2 = None

    if h_n5 > 1:
        nivel, gatilho = 5, f"UTCI ≥48°C por {h_n5}h (>1h)"
        motivo = f"Sensação térmica de 48 °C ou mais por {h_n5} horas."
    elif h_n4 > 2:
        nivel, gatilho = 4, f"UTCI ≥38°C por {h_n4}h (>2h)"
        motivo = f"Sensação térmica de 38 °C ou mais por {h_n4} horas."
    elif h_n3 > 2:
        nivel, gatilho = 3, f"UTCI ≥34°C por {h_n3}h (>2h)"
        motivo = f"Sensação térmica de 34 °C ou mais por {h_n3} horas."
    elif carga_n2:
        if recuperacao_plena:
            nivel, gatilho = 1, f"N2 atenuado por noite fresca ({tmin_noite:.1f}°C <20°)"
            motivo = f"Calor durante o dia, mas a madrugada fresca (mínima de {tmin_noite:.0f} °C) ajuda o corpo a se recuperar."
        elif noite_quente:
            nivel, gatilho = 2, f"N2: Noite quente ({tmin_noite:.1f}°C) + Calor ({h_32}h ≥32°)"
            motivo = f"Calor durante o dia e madrugada quente (mínima de {tmin_noite:.0f} °C)."
            tipo_n2 = "noite_quente"
        else:
            nivel, gatilho = 2, f"N2 potencial ({h_32}h ≥32° | {h_n2}h ≥28°)"
            motivo = f"Calor prolongado: sensação térmica de 28 °C ou mais por {h_n2} horas."
            tipo_n2 = "potencial"
    else:
        nivel, gatilho = 1, "Normal (Carga insuficiente p/ N2)"
        motivo = "Sem calor intenso previsto."

    pico_ibutg = float(np.max(wbgt))
    m_adm = float(np.clip(2004.0 - 56.5 * pico_ibutg, 100.0, 606.0))

    limiar = max(2, nivel)
    idx = np.where(niveis_h >= limiar)[0]
    if len(idx) and nivel > 1:
        h_ini, h_fim = int(horas[idx[0]]), int(min(23, horas[idx[-1]] + 1))
        janela = f"{h_ini:02d}h às {h_fim:02d}h"
    else:
        h_ini = h_fim = None
        janela = "Sem janela crítica ativa"

    return {"nivel": nivel, "gatilho": gatilho, "motivo": motivo, "m_adm": m_adm, "pico_ibutg": pico_ibutg,
            "tmin_noite": tmin_noite, "noite_quente": noite_quente, "recuperacao_plena": recuperacao_plena,
            "candidato_n2": nivel == 2, "tipo_n2": tipo_n2, "janela": janela, "janela_ini": h_ini, "janela_fim": h_fim,
            "_niveis_h": niveis_h, "_horas": horas,
            "pico_utci": float(np.max(utci)), "pico_temp": float(np.max(t2m)),
            "horas_n2": h_n2, "horas_n3": h_n3, "horas_n4": h_n4, "horas_n5": h_n5, "horas_32": h_32}


def aplicar_regras_multidiarias(diagnosticos: list[dict]) -> list[dict]:
    """Rampa antecipatória, acúmulo de dias e rescaldo (passos 2 a 4 do código original). Altera e devolve a lista."""
    n = len(diagnosticos)
    brutos = [d["nivel"] for d in diagnosticos]

    # Passo 1b: persistência do N2 com madrugada amena — exige o dia anterior também com calor (N2+ bruto)
    for i, d in enumerate(diagnosticos):
        if d.get("tipo_n2") == "potencial" and not (i > 0 and brutos[i - 1] >= 2):
            d.update(nivel=1, gatilho=f"N2 potencial: 1º dia com madrugada amena ({d['tmin_noite']:.1f}°C); aguarda persistência",
                     motivo=f"Calor prolongado, mas é o 1º dia e a madrugada é amena (mínima de {d['tmin_noite']:.0f} °C). "
                            "Se o calor continuar amanhã, o alerta sobe para Atenção.")
    niveis = [d["nivel"] for d in diagnosticos]

    # Passo 2: rampa antecipatória (olha o nível bruto do dia seguinte)
    for i in range(n - 1):
        hoje, amanha = diagnosticos[i], diagnosticos[i + 1]
        if amanha["nivel"] >= 3 and niveis[i] == 1 and hoje["pico_utci"] >= 30.0:
            niveis[i] = 2
            hoje.update(nivel=2, gatilho=f"Rampa: Alerta iminente D+1 (Pico {hoje['pico_utci']:.1f}°C)",
                        motivo="Preparação: o dia seguinte deve ter calor forte.")

    # Passo 3: acúmulo (persistência do calor)
    c2 = c3 = c4 = 0
    for i in range(n):
        niv = niveis[i]
        c2 = c2 + 1 if niv >= 2 else 0
        c3 = c3 + 1 if niv >= 3 else 0
        c4 = c4 + 1 if niv >= 4 else 0
        if niv == 2 and c2 > 3:
            niveis[i] = 3
            diagnosticos[i].update(nivel=3, gatilho=f"Acúmulo: {c2}d seguidos em N2 (>3d)",
                                   motivo=f"Calor acumulado: {c2} dias seguidos em Atenção.")
        elif niv == 3 and c3 > 2:
            niveis[i] = 4
            diagnosticos[i].update(nivel=4, gatilho=f"Acúmulo: {c3}d seguidos em N3 (>2d)",
                                   motivo=f"Calor acumulado: {c3} dias seguidos em Alerta.")
        elif niv == 4 and c4 >= 2:
            niveis[i] = 5
            diagnosticos[i].update(nivel=5, gatilho=f"Acúmulo: {c4}d seguidos em N4 (≥2d)",
                                   motivo=f"Calor acumulado: {c4} dias seguidos em Perigo.")

    # Passo 4: rescaldo (histerese da desescalada)
    for i in range(1, n):
        if niveis[i - 1] >= 3 and niveis[i] == 1:
            niveis[i] = 2
            diagnosticos[i].update(nivel=2, gatilho="Rescaldo: D-1 em Alerta (Lag biometeorológico)",
                                   motivo="Recuperação: o dia anterior teve calor forte, e o corpo ainda precisa de cuidado.")

    for d in diagnosticos:
        _recalcular_janela(d)
    return diagnosticos


def _recalcular_janela(d: dict) -> None:
    """Horário crítico do nível final: horas no nível do dia (ou no maior nível horário alcançado, se o
    dia subiu por acúmulo, rampa ou rescaldo), com mínimo de Atenção (UTCI ≥ 28 °C)."""
    if "_niveis_h" not in d:
        return
    nh, horas = d["_niveis_h"], d["_horas"]
    idx = []
    if d["nivel"] > 1 and nh.max() >= 2:
        idx = np.where(nh >= max(2, min(d["nivel"], int(nh.max()))))[0]
    if len(idx):
        d["janela_ini"], d["janela_fim"] = int(horas[idx[0]]), int(min(23, horas[idx[-1]] + 1))
        d["janela"] = f"{d['janela_ini']:02d}h às {d['janela_fim']:02d}h"
    else:
        d["janela_ini"] = d["janela_fim"] = None
        d["janela"] = "Sem janela crítica ativa"


# ---------------------------------------------------------------------------- tempo (chuva, vento, condição)
CODIGOS_CHUVA = [51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99]
ORDEM_CODIGO = {0: 0, 2: 1, 3: 2, 51: 3, 63: 4, 95: 5}
DESCRICAO_CODIGO = {0: "Ensolarado", 2: "Parcialmente nublado", 3: "Nublado", 51: "Chuva fraca", 63: "Chuva", 95: "Tempestade"}


def codigo_representativo(codigos, chuva_dia: float) -> int:
    c = set(int(x) for x in codigos if np.isfinite(x))
    if c & {95, 96, 99}:
        return 95
    if chuva_dia >= 2.0 or c & {61, 63, 65, 80, 81, 82}:
        return 63
    if chuva_dia >= 0.3 or c & {51, 53, 55}:
        return 51
    if 3 in c:
        return 3
    if c & {1, 2}:
        return 2
    return 0


def vento_predominante(velocidades, direcoes) -> tuple[str, str]:
    rad = np.radians(np.asarray(direcoes, dtype=np.float64))
    v = np.asarray(velocidades, dtype=np.float64)
    u, w = -np.mean(v * np.sin(rad)), -np.mean(v * np.cos(rad))
    direcao = np.degrees(np.arctan2(-u, -w)) % 360
    setores = [("N", "↓"), ("NE", "↙"), ("L", "←"), ("SE", "↖"), ("S", "↑"), ("SO", "↗"), ("O", "→"), ("NO", "↘")]
    return setores[int((direcao + 22.5) // 45) % 8]


def estabilidade(p_cen, p_max, codigo, nmep_10=0.0, nmep_25=0.0, nmep_50=0.0) -> dict:
    """Classificação do código original: estável, instável ou instável severo."""
    instavel = (p_cen >= 0.5) or (codigo in CODIGOS_CHUVA) or (p_max >= 5.0) or (nmep_10 >= 35.0) or (nmep_25 >= 20.0)
    if not instavel:
        return {"classe": "estavel", "texto": "Estável", "fg": "#166534", "bg": "#dcfce7"}
    if codigo in (95, 96, 99) or nmep_50 >= 15.0 or nmep_25 >= 40.0 or p_max >= 25.0:
        return {"classe": "severo", "texto": "Instável", "fg": "#991b1b", "bg": "#fee2e2"}
    return {"classe": "instavel", "texto": "Instável", "fg": "#9a3412", "bg": "#ffedd5"}


def estabilidade_publico(ec: dict, gf: dict) -> str:
    """Resumo para o público a partir dos dois modelos."""
    if "severo" in (ec["classe"], gf["classe"]):
        return "Risco de temporal"
    if ec["classe"] == gf["classe"] == "estavel":
        return "Tempo estável"
    if ec["classe"] != "estavel" and gf["classe"] != "estavel":
        return "Tempo instável, com chuva"
    return "Pode haver chuva"


# Faixas de cor das tabelas técnicas (código original)
def faixa_bioclimatica(v: float) -> tuple[str, str]:
    if v >= 48.0: return "#6b21a8", "#ffffff"
    if v >= 38.0: return "#dc2626", "#ffffff"
    if v >= 34.0: return "#ea580c", "#ffffff"
    if v >= 28.0: return "#facc15", "#111111"
    if v >= 12.0: return "#74c476", "#111111"
    if v >= 6.0: return "#6baed6", "#111111"
    if v >= 0.0: return "#3182bd", "#ffffff"
    return "#08519c", "#ffffff"


def faixa_ibutg(v: float) -> tuple[str, str]:
    if v >= 33.0: return "#6b21a8", "#ffffff"
    if v >= 30.0: return "#dc2626", "#ffffff"
    if v >= 28.0: return "#ea580c", "#ffffff"
    if v >= 24.0: return "#facc15", "#111111"
    return "#74c476", "#111111"
