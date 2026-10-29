# -*- coding: utf-8 -*-
"""U1 (docs/PLAN_UTILIDAD.md): ¿ordena Kronos reentrenado los candidatos del swing de una misma sesión?

Las señales son las del motor PIT del bot (`senales.csv`, extraídas en `80ff106`); la puntuación, la de U4 (`u4.puntuar`,
modelo reentrenado); la rentabilidad, de la apertura de `fecha_entrada` a la apertura 5 sesiones después. Las sesiones,
como se concretó el 29-oct antes de puntuar: las que tienen ≥ 5 candidatos, sin solape (cada una a ≥ 5 sesiones de la
anterior tomada); la rejilla fija de 5 en 5, de sensibilidad.

    python -m tiresias.u1 puntuar --dir <ronda2/u1> --u4 <modelos> --dispositivo mps
    python -m tiresias.u1 evaluar --dir <ronda2/u1>
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

from tiresias import metricas as X
from tiresias import ronda2 as R2
from tiresias import u4 as U

HORIZONTE, MINIMO, SEPARACION = 5, 5, 5


def leer(d: pathlib.Path, s: str) -> pd.DataFrame:
    v = pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
    v.index.name = None
    return v


def puntuar(d: pathlib.Path, tok, mod, lote: int = 60) -> pd.DataFrame:
    """La puntuación de U4 de cada señal (ticker, fecha), con la ventana de 90 velas que acaba en `fecha`."""
    s = pd.read_csv(d / "senales.csv")
    filas = []
    for ticker, g in s.groupby("ticker"):
        v = leer(d, ticker)
        pos = {f: i for i, f in enumerate(v.index.strftime("%Y-%m-%d"))}
        validas = sorted({pos[f] for f in g["fecha"] if f in pos and pos[f] >= U.L - 1})
        if validas:
            p = U.puntuar(tok, mod, v, ticker, validas, "u1", lote)
            filas += [{"ticker": ticker, **r} for r in p.to_dict("records")]
    return pd.DataFrame(filas)


def rentabilidades(d: pathlib.Path, senales: pd.DataFrame) -> pd.Series:
    """Apertura ajustada de `fecha_entrada` → la de 5 sesiones después, en el calendario del propio valor."""
    out = {}
    for ticker, g in senales.groupby("ticker"):
        v = leer(d, ticker)
        a = v["open"] * v["adjclose"] / v["close"]
        pos = {f: i for i, f in enumerate(v.index.strftime("%Y-%m-%d"))}
        for k, f in zip(g.index, g["fecha_entrada"]):
            i = pos.get(f)
            if i is not None and i + HORIZONTE < len(a):
                out[k] = float(a.iloc[i + HORIZONTE] / a.iloc[i] - 1.0)
    return pd.Series(out, dtype=float)


def sin_solape(fechas: list, calendario: pd.DatetimeIndex, separacion: int = SEPARACION) -> list:
    """De las fechas candidatas, en orden, cada una que esté a ≥ `separacion` sesiones de la última tomada."""
    pos = {f: i for i, f in enumerate(calendario.strftime("%Y-%m-%d"))}
    tomadas, ultima = [], None
    for f in sorted(fechas):
        if ultima is None or pos[f] - ultima >= separacion:
            tomadas.append(f)
            ultima = pos[f]
    return tomadas


def rejilla(fechas: list, calendario: pd.DatetimeIndex, desde: str, separacion: int = SEPARACION) -> list:
    """Sensibilidad: las de una rejilla fija de `separacion` en `separacion` sesiones desde `desde`."""
    cal = calendario[calendario >= pd.Timestamp(desde)].strftime("%Y-%m-%d")
    fijas = set(cal[::separacion])
    return sorted(f for f in fechas if f in fijas)


def por_sesion(t: pd.DataFrame, fechas: list) -> pd.DataFrame:
    """En cada sesión: RankIC entre candidatos y la mitad de arriba menos todos."""
    filas = []
    for f in fechas:
        g = t[t["fecha"] == f]
        mejores = g.sort_values(by="puntuacion", ascending=False, kind="mergesort").head(len(g) // 2)
        filas.append({"fecha": f, "n": len(g), "rankic": X.spearman(g["puntuacion"], g["r"]),
                      "exceso_mitad": float(mejores["r"].mean() - g["r"].mean())})
    return pd.DataFrame(filas)


def evaluar(d: pathlib.Path) -> dict:
    s = pd.read_csv(d / "senales.csv")
    p = pd.read_csv(d / "u1_puntuaciones.csv", float_precision="round_trip")
    s["r"] = rentabilidades(d, s)
    t = s.merge(p[["ticker", "fecha", "puntuacion"]], on=["ticker", "fecha"], how="inner").dropna(subset=["r", "puntuacion"])
    cuenta = t.groupby("fecha").size()
    validas = list(cuenta[cuenta >= MINIMO].index)
    cal = leer(d, "SPY").index
    out: dict = {"senales": len(s), "puntuadas_con_rentabilidad": len(t), "sesiones_con_5": len(validas)}
    for nombre, fechas in (("principal", sin_solape(validas, cal)),
                           ("rejilla", rejilla(validas, cal, json.loads((d / "senales.json").read_text())["desde"]))):
        ps = por_sesion(t, fechas)
        r: dict = dict(R2.resumen_t(ps["rankic"].to_numpy()))
        e = ps["exceso_mitad"].to_numpy()
        idx = X.bloques(len(e), 4.0, 2000, 0) if len(e) else np.empty((0, 0), dtype=int)
        r.update({"exceso_mitad_media": float(e.mean()) if len(e) else float("nan"),
                  "p_exceso_positivo": float(np.mean([e[i].mean() > 0 for i in idx])) if len(e) else float("nan"),
                  "candidatos_por_sesion_mediana": float(ps["n"].median()) if len(ps) else float("nan")})
        r["pasa_economico"] = bool(r["p_exceso_positivo"] >= 0.9)
        out[nombre] = r
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("puntuar")
    p.add_argument("--dir", required=True)
    p.add_argument("--u4", required=True)
    p.add_argument("--dispositivo", default="mps")
    p.add_argument("--lote", type=int, default=60)
    e = sub.add_parser("evaluar")
    e.add_argument("--dir", required=True)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    if a.orden == "puntuar":
        tok, mod = U.cargar("reentrenado", pathlib.Path(a.u4).expanduser(), a.dispositivo)
        puntuar(d, tok, mod, a.lote).to_csv(d / "u1_puntuaciones.csv", index=False)
        return 0
    r = evaluar(d)
    (d / "u1.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
