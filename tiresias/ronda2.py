# -*- coding: utf-8 -*-
"""Segunda ronda (docs/PLAN_UTILIDAD.md): las hipótesis U1–U5, cada una con su p principal y su criterio económico.

    python -m tiresias.ronda2 u2 --sp500 ~/tiresias_resultados/sp500/datos
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np
import pandas as pd

from tiresias import estadistica as ES
from tiresias import metricas as X
from tiresias import transversal as T


def pasados(dsp: pathlib.Path, simbolos: list, fechas: list, n: int) -> np.ndarray:
    """[fechas × valores]: la rentabilidad de cierre a cierre de las `n` sesiones anteriores (hasta la fecha incluida)."""
    cal = T.leer_velas(dsp, T.CALENDARIO).index
    out = np.full((len(fechas), len(simbolos)), np.nan)
    for j, s in enumerate(simbolos):
        c = T.leer_velas(dsp, s)["close"]
        for i, f in enumerate(fechas):
            antes = cal[int(cal.get_loc(f)) - n]                    # type: ignore[arg-type]
            if f in c.index and antes in c.index:
                out[i, j] = c[f] / c[antes] - 1.0
    return out


def _rango(x: np.ndarray) -> np.ndarray:
    return (pd.Series(x).rank().to_numpy() - 0.5) / len(x) - 0.5


def residuo_ic(P: np.ndarray, R: np.ndarray, controles: list, minimo: int = 100) -> np.ndarray:
    """RankIC por fecha del residuo de P (en rangos) tras regresarlo, en esa fecha, sobre los controles (en rangos)."""
    out = np.full(len(P), np.nan)
    for i in range(len(P)):
        ok = ~np.isnan(P[i]) & ~np.isnan(R[i])
        for c in controles:
            ok &= ~np.isnan(c[i])
        if ok.sum() < minimo:
            continue
        y = _rango(P[i, ok])
        Xm = np.column_stack([np.ones(ok.sum())] + [_rango(c[i, ok]) for c in controles])
        res = y - Xm @ np.linalg.lstsq(Xm, y, rcond=None)[0]
        if np.std(res) > 1e-12:
            out[i] = X.spearman(res, R[i, ok])
    return out


def resumen_t(ic: np.ndarray) -> dict:
    v = ic[~np.isnan(ic)]
    t = T.t_media(ic)
    p = ES.p_t(t, len(v) - 1) if len(v) > 2 and math.isfinite(t) else (0.0 if t == math.inf else float("nan"))
    return {"n": len(v), "media": float(v.mean()) if len(v) else float("nan"), "t": t, "p": p}


def u2(dsp: pathlib.Path) -> dict:
    simbolos = [s for s in json.loads((dsp / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    fechas, simbolos, P, Rc, _ = T.matrices(dsp, simbolos)
    p5, p20 = pasados(dsp, simbolos, fechas, 5), pasados(dsp, simbolos, fechas, 20)
    r = resumen_t(residuo_ic(P, Rc, [p5, p20]))
    r["sin_descontar"] = resumen_t(T.rankic_por_fecha(P, Rc))
    return r


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="orden", required=True)
    a2 = sub.add_parser("u2")
    a2.add_argument("--sp500", required=True)
    a2.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    if a.orden == "u2":
        r = u2(pathlib.Path(a.sp500).expanduser())
        pathlib.Path(a.salida).expanduser().write_text(json.dumps(r, indent=1), encoding="utf-8")
        print(f"U2 · residuo tras descontar la última semana y las 20 sesiones: RankIC media {r['media']:+.4f}, "
              f"t {r['t']:+.2f}, p {r['p']:.3f} ({r['n']} semanas) · sin descontar {r['sin_descontar']['media']:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
