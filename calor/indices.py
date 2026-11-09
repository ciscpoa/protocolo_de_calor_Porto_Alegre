"""Índices térmicos do protocolo: geometria solar, Tmrt, UTCI, IBUTG (WBGT), índice de calor e PET.

Fórmulas do código original do protocolo (Temporada 2026/2027), com duas observações:
- UTCI: polinômio de Bröde et al. (2012) pela implementação de referência da pythermalcomfort,
  que usa os mesmos coeficientes e a mesma pressão de vapor de Hardy (ITS-90) do código original.
- Os operadores de potência perdidos na cópia do código (haversine, índice de calor, IBUTG) foram
  restaurados conforme as fórmulas publicadas (NOAA/Rothfusz; ISO 7243).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pythermalcomfort.models import pet_steady
from pythermalcomfort.models import utci as utci_referencia

# Fator de área projetada (fp) da Tmrt: divisor de γ² com γ (elevação solar) em radianos.
# O código original usa 4,92. O ERA5-HEAT (Di Napoli et al., 2020) usa γ²/50000 com γ em graus,
# o que equivale a 15,23 com γ em radianos. Mantido o valor do código; ver README.
FP_DIVISOR = 4.92


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


def tmrt_era5(ta, rad_direta, rad_difusa, zenite, ur=50.0, albedo=0.20) -> np.ndarray:
    """Temperatura radiante média (°C), esquema ECMWF ERA5 do código original."""
    sigma, a_p, eps_p = 5.670374e-8, 0.70, 0.97
    zen = np.radians(np.asarray(zenite, dtype=np.float64))
    elevacao = np.maximum(0.0, np.pi / 2.0 - zen)
    fp = np.where(elevacao > 0, 0.308 * np.cos(elevacao * (0.998 - elevacao ** 2 / FP_DIVISOR)), 0.08)
    i_dir = np.asarray(rad_direta, dtype=np.float64)
    i_dif = np.asarray(rad_difusa, dtype=np.float64)
    r_sw = a_p * (fp * i_dir + 0.5 * i_dif + 0.5 * albedo * (i_dir + i_dif))
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


def indice_calor_noaa(ta, ur) -> np.ndarray:
    """Índice de calor da NOAA (°C), Rothfusz com ajustes."""
    ta = np.asarray(ta, dtype=np.float64)
    ur = np.asarray(ur, dtype=np.float64)
    tf = ta * 1.8 + 32.0
    simples = 0.5 * (tf + 61.0 + (tf - 68.0) * 1.2 + ur * 0.094)
    roth = (-42.379 + 2.04901523 * tf + 10.14333127 * ur - 0.22475541 * tf * ur - 0.00683783 * tf ** 2
            - 0.05481717 * ur ** 2 + 0.00122874 * tf ** 2 * ur + 0.00085282 * tf * ur ** 2
            - 0.00000199 * tf ** 2 * ur ** 2)
    adj1 = ((13.0 - ur) / 4.0) * np.sqrt(np.maximum(0.0, (17.0 - np.abs(tf - 95.0)) / 17.0))
    roth = np.where((ur < 13.0) & (tf >= 80.0) & (tf <= 112.0), roth - adj1, roth)
    adj2 = ((ur - 85.0) / 10.0) * ((87.0 - tf) / 5.0)
    roth = np.where((ur > 85.0) & (tf >= 80.0) & (tf <= 87.0), roth + adj2, roth)
    hi_f = np.where((simples + tf) / 2.0 >= 80.0, roth, simples)
    return (hi_f - 32.0) / 1.8


def pet(ta, tmrt, va, ur) -> np.ndarray:
    """PET (°C) com vento a 1,1 m (0,68 × vento a 10 m), met 1,35 e clo 0,9, como no código original."""
    v = np.maximum(0.1, np.asarray(va, dtype=np.float64) * 0.68)
    ta, tmrt, ur = (np.asarray(x, dtype=np.float64) for x in (ta, tmrt, ur))
    try:
        valores = np.asarray(pet_steady(tdb=ta, tr=tmrt, v=v, rh=ur, met=1.35, clo=0.9).pet, dtype=np.float64)
    except Exception:  # versões antigas só aceitam escalares
        valores = []
        for t, tr, vv, r in zip(ta, tmrt, v, ur):
            try:
                valores.append(float(pet_steady(tdb=float(t), tr=float(tr), v=float(vv), rh=float(r), met=1.35, clo=0.9).pet))
            except Exception:
                valores.append(np.nan)
        valores = np.asarray(valores, dtype=np.float64)
    return pd.Series(valores).interpolate().bfill().ffill().to_numpy()
