# -*- coding: utf-8 -*-
"""Velas diarias de Yahoo para TiresIAs, con un corte explícito y sin sesiones a medias.

    from tiresias.datos import velas
    df = velas("IDR.MC", fin="2026-10-23")   # open, high, low, close, volume, adjclose; índice de fechas

- `open/high/low/close/volume`: las de Yahoo (ajustadas por splits, no por dividendos): la entrada de Kronos.
- `adjclose`: ajustado también por dividendos: para medir la rentabilidad total.
- Caché fuera del repo (`TIRESIAS_CACHE`, por defecto `~/.cache/tiresias`), una por símbolo y día de descarga:
  repetir no vuelve a pedir y un resultado dice de qué descarga son sus datos. En el repo no entra ningún dato.
- `fin`: la última sesión que entra. Si la descarga se hizo con esa sesión aún abierta, es un error: una vela a
  medias pasaría por un cierre (la última barra de una descarga hecha con la bolsa abierta es la de ese día).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request

import pandas as pd

CACHE = pathlib.Path(os.environ.get("TIRESIAS_CACHE") or pathlib.Path.home() / ".cache" / "tiresias")
UA = {"User-Agent": "Mozilla/5.0"}


def _bajar(simbolo: str) -> dict:
    u = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(simbolo)
         + "?period1=-631152000&period2=" + str(int(time.time()) + 86400) + "&interval=1d&events=div,split")
    for intento in range(4):
        try:
            return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=60).read())
        except Exception:
            if intento == 3:
                raise
            time.sleep(3 * (intento + 1))
    raise RuntimeError("inalcanzable")


def ruta(simbolo: str, dia: str) -> pathlib.Path:
    return CACHE / f"{simbolo.replace('^', '_').replace('=', '_')}_{dia}.json"


def velas(simbolo: str, fin: str, dia: str | None = None) -> pd.DataFrame:
    """Velas hasta `fin` incluida, de la descarga del día `dia` (por defecto, hoy)."""
    dia = dia or dt.date.today().isoformat()
    f = ruta(simbolo, dia)
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(_bajar(simbolo)), encoding="utf-8")
    return leer(json.loads(f.read_text(encoding="utf-8")), fin, f.stat().st_mtime)


def leer(respuesta: dict, fin: str, bajado: float) -> pd.DataFrame:
    """La respuesta del chart v8 en un DataFrame, cortado en `fin`; error si la vela de `fin` estaba a medias."""
    r = respuesta["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    idx = pd.to_datetime([dt.datetime.fromtimestamp(t, dt.timezone.utc).date() for t in r["timestamp"]])
    adj = r["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    df = pd.DataFrame({"open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
                       "volume": q["volume"], "adjclose": adj}, index=idx, dtype="float64")
    df = df[~df.index.duplicated(keep="last")].sort_index().dropna(subset=["open", "high", "low", "close"])
    df["volume"] = df["volume"].fillna(0.0)
    periodo = r.get("meta", {}).get("currentTradingPeriod", {}).get("regular", {})
    if periodo.get("end") and len(df):
        inicio = dt.datetime.fromtimestamp(periodo.get("start", periodo["end"]), dt.timezone.utc).date()
        if bajado < periodo["end"] and inicio <= dt.date.fromisoformat(fin) and df.index[-1].date() >= inicio:
            raise ValueError(f"la sesión del {inicio} estaba abierta al descargar y entra en el corte ({fin})")
    return df.loc[:fin]
