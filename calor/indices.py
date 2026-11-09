"""Índices térmicos do protocolo: geometria solar, Tmrt, UTCI e IBUTG (WBGT).

Fórmulas do código original do protocolo (Temporada 2026/2027), com estes ajustes:
- UTCI: polinômio de Bröde et al. (2012) pela implementação de referência da pythermalcomfort,
  que usa os mesmos coeficientes e a mesma pressão de vapor de Hardy (ITS-90) do código original.
- Os operadores de potência perdidos na cópia do código (haversine, IBUTG) foram restaurados conforme
  as fórmulas publicadas (ISO 7243).
- PET e índice de calor da NOAA saíram: não são usados pelo protocolo.
- Tmrt no esquema ERA5-HEAT completo (Di Napoli et al., 2020), o método declarado no código
  (METODO_TMRT = 'ECMWF_ERA5'): fator de área projetada de Jendritzky com a elevação em graus e
  radiação direta normal ao sol (I*). O código original usava γ²/4,92 e a direta horizontal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pythermalcomfort.models import utci as utci_referencia



def zenite_solar(tempos: pd.DatetimeIndex, lat: float, lon: float) -> np.ndarray:
    """Ângulo zenital solar (graus) para cada horário."""
    utc = tempos.tz_convert("UTC")
    dia = np.asarray(utc.dayofyear, dtype=np.float64)
    hora = np.asarray(utc.hour, dtype=np.float64) + np.asarray(utc.minute, dtype=np.float64) / 60.0
    gamma = 2.0 * np.pi * (dia - 1) / 365.25
    decl = np.radians(23.44) * np.sin(2.0 * np.pi * (284.0 + dia) / 365.25)
    eqtime = 229.18 * (0.000075 + 0.001868 * np.cos(gamma) - 0.032077 * np.sin(gamma)
                       - 0.014615 * np.cos(2.0 * gamma) - 0.040849 * np.sin(2.0 * gamma))
    tempo_solar = hora * 60.0 + eqtime + 4.0 * lon
    angulo_horario = np.radians(tempo_solar / 4.0 - 180.0)
    lat_r = np.radians(lat)
    cos_z = np.sin(lat_r) * np.sin(decl) + np.cos(lat_r) * np.cos(decl) * np.cos(angulo_horario)
    return np.degrees(np.arccos(np.clip(cos_z, -1.0, 1.0)))


_G_HARDY = [-2.8365744e3, -6.028076559e3, 1.954263612e1, -2.737830188e-2,
            1.6261698e-5, 7.0229056e-10, -1.8680009e-13, 2.7150305]


def es_hardy_its90(ta) -> np.ndarray:
    """Pressão de saturação do vapor (hPa), Hardy (ITS-90)."""
    tk = np.asarray(ta, dtype=np.float64) + 273.15
    es = _G_HARDY[7] * np.log(tk)
    for i in range(7):
        es = es + _G_HARDY[i] * tk ** (i - 2)
    return np.exp(es) * 0.01


def fator_area_projetada(zenite) -> np.ndarray:
    """fp de Jendritzky para pessoa em pé: 0,308·cos[h·(0,998 − h²/50000)], h = elevação solar em graus."""
    h = np.maximum(0.0, 90.0 - np.asarray(zenite, dtype=np.float64))
    return np.where(h > 0, 0.308 * np.cos(np.radians(h * (0.998 - h ** 2 / 50000.0))), 0.08)


def tmrt_era5(ta, rad_direta_normal, rad_difusa, rad_direta_horizontal, zenite, ur=50.0, albedo=0.20) -> np.ndarray:
    """Temperatura radiante média (°C), esquema ERA5-HEAT (Di Napoli et al., 2020).

    σ·Tmrt⁴ = 0,5·(L↓ + L↑) + (α/ε)·(fp·I* + 0,5·D + 0,5·albedo·G), com I* a radiação direta normal
    ao sol, D a difusa e G a global horizontal. As ondas longas seguem o código original
    (emissividade do céu a partir da pressão de vapor; superfície à temperatura do ar).
    """
    sigma, a_p, eps_p = 5.670374e-8, 0.70, 0.97
    fp = fator_area_projetada(zenite)
    i_norm = np.asarray(rad_direta_normal, dtype=np.float64)
    i_dif = np.asarray(rad_difusa, dtype=np.float64)
    i_glob = np.asarray(rad_direta_horizontal, dtype=np.float64) + i_dif
    r_sw = a_p * (fp * i_norm + 0.5 * i_dif + 0.5 * albedo * i_glob)
    tk = np.asarray(ta, dtype=np.float64) + 273.15
    e_vap = es_hardy_its90(ta) * (np.asarray(ur, dtype=np.float64) / 100.0)
    eps_ceu = np.clip(0.70 + 5.95e-5 * e_vap * np.exp(1500.0 / tk), 0.70, 0.99)
    r_lw = 0.5 * eps_p * (eps_ceu * sigma * tk ** 4 + sigma * tk ** 4)
    return ((r_sw + r_lw) / (eps_p * sigma)) ** 0.25 - 273.15


def utci(ta, tmrt, va, ur) -> np.ndarray:
    """UTCI (°C). Vento limitado a 0,5–17 m/s, como no código original."""
    v = np.clip(np.asarray(va, dtype=np.float64), 0.5, 17.0)
    r = utci_referencia(tdb=np.asarray(ta, dtype=np.float64), tr=np.asarray(tmrt, dtype=np.float64), v=v,
                        rh=np.asarray(ur, dtype=np.float64), limit_inputs=False, round_output=False)
    return np.asarray(r.utci, dtype=np.float64)


def bulbo_umido_stull(ta, ur) -> np.ndarray:
    ta = np.asarray(ta, dtype=np.float64)
    ur = np.asarray(ur, dtype=np.float64)
    return (ta * np.arctan(0.151977 * np.sqrt(ur + 8.313659)) + np.arctan(ta + ur) - np.arctan(ur - 1.676331)
            + 0.00391838 * ur ** 1.5 * np.arctan(0.023101 * ur) - 4.686035)


def ibutg_iso7243(ta, ur, va, rad_solar, tmrt) -> np.ndarray:
    """IBUTG/WBGT ao sol (°C), ISO 7243."""
    ta = np.asarray(ta, dtype=np.float64)
    va = np.clip(np.asarray(va, dtype=np.float64), 0.1, 20.0)
    rad = np.maximum(0.0, np.asarray(rad_solar, dtype=np.float64))
    v2 = np.maximum(0.1, va * 0.75)
    tnw = bulbo_umido_stull(ta, ur) + 0.0012 * rad / v2 ** 0.3
    hc = 6.3 * v2 ** 0.6 / 0.15 ** 0.4  # globo de 0,15 m
    hr = 5.7
    tg = (hc * ta + hr * np.asarray(tmrt, dtype=np.float64)) / (hc + hr)
    return 0.7 * tnw + 0.2 * tg + 0.1 * ta
