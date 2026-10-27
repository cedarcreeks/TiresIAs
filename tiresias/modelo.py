# -*- coding: utf-8 -*-
"""Kronos con los pesos fijados y TODAS las trayectorias, no sólo su media.

Las revisiones de Hugging Face son las del test de regresión de upstream
(tests/test_kronos_regression.py): con ellas, la instalación reproduce sus
salidas de referencia, y es lo primero que se comprueba en cada máquina.
"""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
import torch

from model import Kronos, KronosTokenizer
from model.kronos import auto_regressive_inference, calc_time_stamps

MODELOS = {
    "small": ("NeoQuasar/Kronos-small", "901c26c1332695a2a8f243eb2f37243a37bea320"),
}
TOKENIZADOR = ("NeoQuasar/Kronos-Tokenizer-base", "0e0117387f39004a9016484a186a908917e22426")
COLUMNAS = ["open", "high", "low", "close", "volume", "amount"]


def cargar(modelo: str = "small", dispositivo: str = "cpu") -> tuple:
    (repo, rev), (trepo, trev) = MODELOS[modelo], TOKENIZADOR
    tok = KronosTokenizer.from_pretrained(trepo, revision=trev).eval().to(dispositivo)
    mod = Kronos.from_pretrained(repo, revision=rev).eval().to(dispositivo)
    return tok, mod


def semilla(*partes) -> int:
    """Una semilla estable a partir de lo que identifica un lote (no de `hash()`,
    que cambia entre procesos)."""
    return int(hashlib.sha256("|".join(map(str, partes)).encode()).hexdigest()[:8], 16)


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    """Como `KronosPredictor.predict_batch`: volumen a cero si falta, importe = volumen × precio medio."""
    df = df.copy()
    if "volume" not in df.columns:
        df["volume"] = 0.0
        df["amount"] = 0.0
    if "amount" not in df.columns:
        df["amount"] = df["volume"] * df[["open", "high", "low", "close"]].mean(axis=1)
    if df[COLUMNAS].isnull().values.any():
        raise ValueError("hay NaN en precios o volumen")
    return df


def trayectorias(tok, mod, dfs: list, ts_hist: list, ts_fut: list, H: int, N: int,
                 T: float = 0.6, top_p: float = 0.9, seed: int = 0, max_context: int = 512, clip: float = 5.0) -> np.ndarray:
    """[series, N, H, 6]: las N trayectorias de cada serie, desnormalizadas como las
    de `predict_batch`. Todas las series con la misma longitud de historia."""
    xs, xst, yst, medias, desv = [], [], [], [], []
    for df, th, tf in zip(dfs, ts_hist, ts_fut):
        x = _preparar(df)[COLUMNAS].values.astype(np.float32)
        m, s = np.mean(x, axis=0), np.std(x, axis=0)
        xs.append(np.clip((x - m) / (s + 1e-5), -clip, clip))
        xst.append(calc_time_stamps(pd.Series(th)).values.astype(np.float32))
        yst.append(calc_time_stamps(pd.Series(tf)).values.astype(np.float32))
        medias.append(m)
        desv.append(s)
    if len({len(x) for x in xs}) != 1 or any(len(y) != H for y in yst):
        raise ValueError("todas las series con la misma historia y H fechas futuras")
    disp = next(mod.parameters()).device
    t = lambda a: torch.from_numpy(np.stack(a).astype(np.float32)).to(disp)     # noqa: E731
    torch.manual_seed(seed)
    z = auto_regressive_inference(tok, mod, t(xs), t(xst), t(yst), max_context, H, clip, T, 0, top_p, N,
                                  verbose=False, return_samples=True)
    z = z[:, :, -H:, :]
    return z * (np.stack(desv)[:, None, None, :] + 1e-5) + np.stack(medias)[:, None, None, :]
