# -*- coding: utf-8 -*-
"""Predicciones de Kronos fecha a fecha, fuera de su muestra de entrenamiento.

Para cada sesión *t* (desde `DESDE`) y cada horizonte H: las 40 velas hasta *t* incluida, las N trayectorias de las
H sesiones siguientes (con sus fechas reales: el calendario se conoce, los precios no), y de ellas la rentabilidad
prevista, la probabilidad de subida y sus cuantiles; al lado, lo que pasó. Nada posterior a *t* entra en la
predicción de *t* (lo comprueba un test).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tiresias import modelo as M

DESDE = "2024-07-01"          # Kronos se entrenó con datos hasta junio de 2024
L = 40                        # velas de historia: el protocolo diario del artículo
ENTRADA = ["open", "high", "low", "close", "volume"]


def predecir(tok, mod, df: pd.DataFrame, simbolo: str, H: int, N: int = 10, desde: str = DESDE,
             lote: int = 100, T: float = 0.6, top_p: float = 0.9) -> pd.DataFrame:
    """Una fila por sesión *t*: cierre, rentabilidad prevista (media de las N), p de subida,
    cuantiles 10/50/90 de la prevista, y la real a H sesiones."""
    fechas = df.index
    pos = [i for i, d in enumerate(fechas) if d >= pd.Timestamp(desde) and i >= L - 1 and i + H < len(fechas)]
    filas = []
    for k in range(0, len(pos), lote):
        trozo = pos[k:k + lote]
        dfs = [df.iloc[i - L + 1:i + 1][ENTRADA].reset_index(drop=True) for i in trozo]
        th = [pd.Series(fechas[i - L + 1:i + 1]) for i in trozo]
        tf = [pd.Series(fechas[i + 1:i + H + 1]) for i in trozo]
        # la semilla depende del lote (su primera fecha): reproducible con el mismo `lote` y dispositivo
        z = M.trayectorias(tok, mod, dfs, th, tf, H, N, T=T, top_p=top_p,
                           seed=M.semilla(simbolo, H, N, str(fechas[trozo[0]].date())))
        for j, i in enumerate(trozo):
            c0 = float(df["close"].iloc[i])
            r = z[j, :, -1, 3] / c0 - 1.0
            filas.append({"simbolo": simbolo, "fecha": str(fechas[i].date()), "H": H, "cierre": c0,
                          "r_prevista": float(r.mean()), "p_subida": float((r > 0).mean()),
                          "r_p10": float(np.quantile(r, 0.1)), "r_p50": float(np.quantile(r, 0.5)),
                          "r_p90": float(np.quantile(r, 0.9)),
                          "r_real": float(df["close"].iloc[i + H]) / c0 - 1.0})
    return pd.DataFrame(filas)
