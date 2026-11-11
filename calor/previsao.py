"""Download das previsões (Open-Meteo) e processamento por modelo, como no código original.

- Determinístico: ECMWF IFS 0,25° e NOAA GFS, horário, 5 dias à frente e 3 dias para trás (contexto das
  regras de persistência, acúmulo e rescaldo), em 25 pontos num raio de 55 km de Porto Alegre. Os índices
  térmicos usam o ponto central; a chuva usa também a média e o máximo da grade. A radiação é a do
  instante da hora, coerente com a posição do sol calculada para o mesmo horário.
- Ensemble (GFS 0,25° com 31 membros e ECMWF IFS 0,25° com 51): probabilidade de chuva acumulada no
  dia acima de 10, 25 e 50 mm em algum ponto da vizinhança (NMEP).
"""
from __future__ import annotations

import numpy as np
import openmeteo_requests
import pandas as pd
import requests_cache
from openmeteo_sdk.Model import Model
from retry_requests import retry

from . import indices

LAT_CENTRAL, LON_CENTRAL, RAIO_KM = -30.08, -51.21, 55.0
LIMIARES_NMEP = [10.0, 25.0, 50.0]
FUSO = "America/Sao_Paulo"
DIAS = 5
DIAS_ANTERIORES = 3  # o acúmulo de N2 olha até 3 dias para trás
VARIAVEIS = ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "direct_radiation_instant",
             "diffuse_radiation_instant", "direct_normal_irradiance_instant", "precipitation", "weather_code",
             "wind_direction_10m", "wind_gusts_10m", "surface_temperature", "uv_index", "uv_index_clear_sky"]
# UVI é fornecido pelo NOAA GFS; o ECMWF IFS aberto devolve essas duas séries como ausentes.
MODELOS_DET = {"gfs_seamless": "gfs", "ecmwf_ifs025": "ecmwf"}
MODELOS_ENS = {"gfs025": "gfs", "ecmwf_ifs025": "ecmwf"}
_NOME_MODELO = {v: k for k, v in vars(Model).items() if not k.startswith("_") and isinstance(v, int)}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    dlat, dlon = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dlat / 2.0) ** 2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2.0) ** 2
    return float(2.0 * 6371.0 * np.arcsin(np.sqrt(a)))


def pontos_vizinhanca(passo=0.15) -> tuple[list[tuple[float, float]], int]:
    pontos = []
    for di in (-2, -1, 0, 1, 2):
        for dj in (-2, -1, 0, 1, 2):
            la, lo = round(LAT_CENTRAL + di * passo, 4), round(LON_CENTRAL + dj * passo, 4)
            if haversine_km(LAT_CENTRAL, LON_CENTRAL, la, lo) <= RAIO_KM:
                pontos.append((la, lo))
    return pontos, pontos.index((round(LAT_CENTRAL, 4), round(LON_CENTRAL, 4)))


def cliente(cache: str = ".cache_openmeteo") -> openmeteo_requests.Client:
    sessao = requests_cache.CachedSession(cache, expire_after=3600)
    return openmeteo_requests.Client(session=retry(sessao, retries=5, backoff_factor=0.3))


def _separar_por_modelo(respostas, mapa: dict, n_pontos: int) -> dict:
    """Agrupa as respostas pelo nome do modelo, preservando a ordem dos pontos."""
    grupos = {v: [] for v in mapa.values()}
    for r in respostas:
        nome = _NOME_MODELO.get(r.Model())
        if nome in mapa:
            grupos[mapa[nome]].append(r)
    for k, lista in grupos.items():
        if len(lista) != n_pontos:
            raise RuntimeError(f"modelo {k}: {len(lista)} respostas para {n_pontos} pontos")
    return grupos


def baixar_deterministico(om, pontos) -> dict:
    params = {"latitude": [p[0] for p in pontos], "longitude": [p[1] for p in pontos], "hourly": VARIAVEIS,
              "models": list(MODELOS_DET), "wind_speed_unit": "kmh", "precipitation_unit": "mm",
              "timezone": FUSO, "forecast_days": DIAS, "past_days": DIAS_ANTERIORES}
    return _separar_por_modelo(om.weather_api("https://api.open-meteo.com/v1/forecast", params=params), MODELOS_DET, len(pontos))


def _tempos(h) -> pd.DatetimeIndex:
    return pd.date_range(start=pd.to_datetime(h.Time(), unit="s", utc=True), end=pd.to_datetime(h.TimeEnd(), unit="s", utc=True),
                         freq=pd.Timedelta(seconds=h.Interval()), inclusive="left").tz_convert(FUSO)


def processar_modelo(respostas, idx_centro: int) -> pd.DataFrame:
    h = respostas[idx_centro].Hourly()
    tempos = _tempos(h)
    var = {nome: h.Variables(i).ValuesAsNumpy().astype(np.float64) for i, nome in enumerate(VARIAVEIS)}
    t2m, ur = var["temperature_2m"], var["relative_humidity_2m"]
    vento_ms = var["wind_speed_10m"] / 3.6
    zen = indices.zenite_solar(tempos, LAT_CENTRAL, LON_CENTRAL)
    dir_h, dif, dni = var["direct_radiation_instant"], var["diffuse_radiation_instant"], var["direct_normal_irradiance_instant"]
    tmrt = indices.tmrt_era5(t2m, dni, dif, dir_h, zen, ur=ur)
    chuva_grade = np.array([r.Hourly().Variables(VARIAVEIS.index("precipitation")).ValuesAsNumpy() for r in respostas], dtype=np.float64)
    return pd.DataFrame({
        "time": tempos, "t2m": t2m, "tskin": var["surface_temperature"], "rh2m": ur,
        "wind_kmh": var["wind_speed_10m"], "wind_gust_kmh": var["wind_gusts_10m"], "wind_dir": var["wind_direction_10m"],
        "precip_center": var["precipitation"], "precip_grid_mean": chuva_grade.mean(axis=0), "precip_grid_max": chuva_grade.max(axis=0),
        "weather_code": var["weather_code"], "tmrt": tmrt,
        "uv_index": var["uv_index"], "uv_index_clear_sky": var["uv_index_clear_sky"],
        "utci": indices.utci(t2m, tmrt, vento_ms, ur),
        "wbgt": indices.ibutg_iso7243(t2m, ur, vento_ms, dir_h + dif, tmrt),
    })


def baixar_ensemble(om, pontos) -> dict:
    """Por modelo: cubo (membros × pontos × horas) de chuva e as datas de cada hora."""
    params = {"latitude": [p[0] for p in pontos], "longitude": [p[1] for p in pontos], "hourly": "precipitation",
              "models": list(MODELOS_ENS), "timezone": FUSO, "forecast_days": DIAS}
    grupos = _separar_por_modelo(om.weather_api("https://ensemble-api.open-meteo.com/v1/ensemble", params=params),
                                 MODELOS_ENS, len(pontos))
    cubos = {}
    for k, resps in grupos.items():
        por_ponto = [[r.Hourly().Variables(v).ValuesAsNumpy() for v in range(r.Hourly().VariablesLength())] for r in resps]
        cubos[k] = {"cubo": np.transpose(np.array(por_ponto, dtype=np.float64), (1, 0, 2)),
                    "datas": np.array([t.date() for t in _tempos(resps[0].Hourly())])}
    return cubos


def nmep_diario(cubo: np.ndarray, datas: np.ndarray, dias_unicos, limiares=LIMIARES_NMEP) -> dict:
    """% de membros com chuva no dia ≥ limiar em pelo menos um ponto da vizinhança."""
    saida = {}
    for d in dias_unicos:
        idx = np.where(datas == d)[0]
        maximo_vizinhanca = np.nanmax(np.nansum(cubo[:, :, idx], axis=2), axis=1)
        saida[d] = {t: float(np.mean(maximo_vizinhanca >= t) * 100.0) for t in limiares}
    return saida
