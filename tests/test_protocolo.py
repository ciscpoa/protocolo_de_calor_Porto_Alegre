"""Testes dos gatilhos do protocolo com dias sintéticos (24 horas cada)."""
import numpy as np
import pandas as pd
import pytest

from calor import indices, protocolo


def dia(utci_pico=20.0, horas_pico=0, base=20.0, tmin_noite=18.0, data="2026-12-01"):
    """Dia com UTCI = base e `horas_pico` horas (a partir das 12h) no valor `utci_pico`; madrugada com tmin_noite."""
    tempo = pd.date_range(f"{data} 00:00", periods=24, freq="h", tz="America/Sao_Paulo")
    utci = np.full(24, base)
    utci[12:12 + horas_pico] = utci_pico
    t2m = np.full(24, 25.0)
    t2m[0:7] = tmin_noite
    return pd.DataFrame({"time": tempo, "UTCI_MME": utci, "T2M_MME": t2m, "WBGT_MME": np.full(24, 24.0)})


# Cada nível exige horas acima do limiar: N5 >1 h ≥48 °C; N4 >2 h ≥38 °C; N3 >2 h ≥34 °C.
# O pico de 37 °C testa o gatilho normal de N3, fora das condições de atenuação para N2.
@pytest.mark.parametrize("pico,horas,nivel", [(48.5, 2, 5), (48.5, 1, 1), (48.5, 3, 5), (39, 3, 4), (39, 2, 1),
                                              (37, 3, 3), (35, 2, 1)])
def test_niveis_por_horas_de_utci(pico, horas, nivel):
    assert protocolo.avaliar_dia(dia(pico, horas, tmin_noite=18.0))["nivel"] == nivel


def test_atenuacao_de_nivel3_com_madrugada_fria():
    # Com todas as salvaguardas presentes, o N3 marginal é atenuado para N2.
    atenuado = protocolo.avaliar_dia(dia(35.0, 3, tmin_noite=18.0))
    assert atenuado["nivel"] == 2
    assert atenuado["tipo_n2"] == "atenuado_de_n3"
    assert "N3 atenuado" in atenuado["gatilho"]

    # Sem qualquer uma das salvaguardas, o dia permanece em N3.
    assert protocolo.avaliar_dia(dia(35.0, 3, tmin_noite=18.5))["nivel"] == 3  # madrugada não profunda
    assert protocolo.avaliar_dia(dia(36.5, 3, tmin_noite=18.0))["nivel"] == 3  # pico não marginal
    assert protocolo.avaliar_dia(dia(35.0, 4, tmin_noite=18.0))["nivel"] == 3  # exposição acima de 3 h

    ibutg_alto = dia(35.0, 3, tmin_noite=18.0)
    ibutg_alto["WBGT_MME"] = 28.0
    assert protocolo.avaliar_dia(ibutg_alto)["nivel"] == 3  # sem segurança ocupacional


def test_nivel2_noite_quente_e_noite_fresca():
    calor = dict(utci_pico=33.0, horas_pico=4)  # 4 h ≥32 °C: carga de N2
    assert protocolo.avaliar_dia(dia(**calor, tmin_noite=23.0))["nivel"] == 2   # noite quente: N2
    assert protocolo.avaliar_dia(dia(**calor, tmin_noite=21.0))["nivel"] == 2   # noite intermediária: N2
    d = protocolo.avaliar_dia(dia(**calor, tmin_noite=19.0))                    # noite fresca: atenuado
    assert d["nivel"] == 1 and "noite fresca" in d["gatilho"]


def test_nivel2_por_exposicao_prolongada():
    assert protocolo.avaliar_dia(dia(29.0, 7, tmin_noite=21.0))["nivel"] == 2   # ≥28 °C por 7 h
    assert protocolo.avaliar_dia(dia(29.0, 6, tmin_noite=21.0))["nivel"] == 1   # 6 h não basta


def _diags(niveis, picos=None, tipos=None):
    picos = picos or [30.0] * len(niveis)
    tipos = tipos or [None] * len(niveis)
    return [{"nivel": n, "pico_utci": p, "gatilho": "", "motivo": "", "tipo_n2": t, "tmin_noite": 21.0}
            for n, p, t in zip(niveis, picos, tipos)]


def test_persistencia_do_nivel2_com_madrugada_amena():
    # madrugada amena (20–22 °C): o N2 só vale a partir do 2º dia seguido de calor
    r = protocolo.aplicar_regras_multidiarias(_diags([2, 2, 2], tipos=["potencial"] * 3))
    assert [d["nivel"] for d in r] == [1, 2, 2] and "aguarda persistência" in r[0]["gatilho"]
    # madrugada quente (≥ 22 °C): vale já no 1º dia
    assert [d["nivel"] for d in protocolo.aplicar_regras_multidiarias(_diags([2], tipos=["noite_quente"]))] == [2]
    # dia anterior sem calor: o potencial não se confirma
    assert [d["nivel"] for d in protocolo.aplicar_regras_multidiarias(_diags([1, 2], tipos=[None, "potencial"]))] == [1, 1]


def test_horario_critico_do_nivel_final():
    # dia com UTCI 31 °C por 3 h (N1 bruto) antes de um dia de Alerta: sobe por rampa e ganha horário crítico
    hoje = protocolo.avaliar_dia(dia(31.0, 3, tmin_noite=18.0, data="2026-12-01"))
    amanha = protocolo.avaliar_dia(dia(35.0, 4, tmin_noite=18.0, data="2026-12-02"))
    assert hoje["nivel"] == 1 and hoje["janela_ini"] is None
    r = protocolo.aplicar_regras_multidiarias([hoje, amanha])
    assert r[0]["nivel"] == 2 and (r[0]["janela_ini"], r[0]["janela_fim"]) == (12, 15)
    assert r[1]["nivel"] == 3 and (r[1]["janela_ini"], r[1]["janela_fim"]) == (12, 16)


def test_fator_area_projetada_jendritzky():
    # fp = 0,308·cos[h·(0,998 − h²/50000)], h em graus
    assert float(indices.fator_area_projetada(60.0)) == pytest.approx(0.308 * np.cos(np.radians(30 * (0.998 - 900 / 50000))), abs=1e-9)
    assert float(indices.fator_area_projetada(0.0)) == pytest.approx(0.0785, abs=0.001)


def test_rampa_antecipatoria():
    r = protocolo.aplicar_regras_multidiarias(_diags([1, 3], picos=[31.0, 36.0]))
    assert [d["nivel"] for d in r] == [2, 3] and r[0]["gatilho"].startswith("Rampa")
    r = protocolo.aplicar_regras_multidiarias(_diags([1, 3], picos=[29.0, 36.0]))  # pico < 30 °C: sem rampa
    assert [d["nivel"] for d in r] == [1, 3]


def test_acumulo_e_rescaldo():
    assert [d["nivel"] for d in protocolo.aplicar_regras_multidiarias(_diags([2, 2, 2, 2, 2]))] == [2, 2, 2, 3, 3]
    assert [d["nivel"] for d in protocolo.aplicar_regras_multidiarias(_diags([3, 3, 3]))] == [3, 3, 4]
    assert [d["nivel"] for d in protocolo.aplicar_regras_multidiarias(_diags([4, 4]))] == [4, 5]
    r = protocolo.aplicar_regras_multidiarias(_diags([3, 1], picos=[36.0, 25.0]))
    assert [d["nivel"] for d in r] == [3, 2] and r[1]["gatilho"].startswith("Rescaldo")


def test_indices_valores_de_referencia():
    # UTCI: exemplo da documentação da pythermalcomfort (Ta = Tmrt = 25 °C, vento 1 m/s, UR 50%) = 24,6 °C
    assert float(indices.utci(25.0, 25.0, 1.0, 50.0)) == pytest.approx(24.6, abs=0.1)
    assert indices.utci(np.array([30.0, 35.0]), np.array([30.0, 50.0]), np.array([0.1, 25.0]), np.array([50.0, 50.0])).shape == (2,)
