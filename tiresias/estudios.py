# -*- coding: utf-8 -*-
"""Las dos preguntas exploratorias del 28-oct sobre los 5 valores, con el criterio escrito antes de mirar:

- `volatilidad`: ¿la anchura del abanico de Kronos ordena el TAMAÑO del movimiento mejor que una fórmula gratuita (la
  volatilidad de Parkinson de 20 sesiones, con máximos y mínimos)? Aporta si su correlación parcial, descontada esa
  fórmula, es > 0 en al menos 4 de 5 valores.
- `mineria`: ¿se pueden sacar reglas rentables de sus salidas? 91 reglas por valor elegidas en el desarrollo, probadas
  una vez después, contra el mismo procedimiento con las salidas barajadas. Aprueba si gana a mantener y al p95.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

from tiresias import informe as I
from tiresias import metricas as X

SIMBOLOS = ["IDR.MC", "ACS.MC", "SPY", "3USL.MI", "BTC-EUR"]
CORTE = "2025-07-01"                      # desarrollo antes, prueba final desde aquí (docs/PLAN.md, fase 4)
UMBRALES = np.round(np.arange(0.1, 1.0, 0.1), 1)
CUANTILES = [0.2, 0.4, 0.6, 0.8, 1.0]


def _velas(d, s):
    return pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")


def _pred(d, s, H):
    return pd.read_csv(d / f"pred_{s}_H{H}.csv", float_precision="round_trip")


def parcial(rxy: float, rxz: float, ryz: float) -> float:
    """Correlación de x con y descontada z."""
    return (rxy - rxz * ryz) / np.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))


def parkinson(v: pd.DataFrame, n: int = 20) -> pd.Series:
    return np.sqrt((np.log(v["high"] / v["low"]) ** 2).rolling(n).mean() / (4 * np.log(2)))


def volatilidad(d: pathlib.Path, simbolos: list = SIMBOLOS, H: int = 1) -> dict:
    out = {}
    for s in simbolos:
        q = X.sin_solape(_pred(d, s, H), H).copy()
        q["abanico"] = q["r_p90"] - q["r_p10"]
        q["park"] = (parkinson(_velas(d, s)) * np.sqrt(H)).reindex(pd.to_datetime(q["fecha"])).to_numpy()
        q["absreal"] = q["r_real"].abs()
        q = q.dropna(subset=["park"])
        rk, rp, rkp = X.spearman(q.abanico, q.absreal), X.spearman(q.park, q.absreal), X.spearman(q.abanico, q.park)
        out[s] = {"n": len(q), "kronos": rk, "parkinson": rp, "entre_ellos": rkp, "parcial": float(parcial(rk, rkp, rp))}
    aporta = sum(v["parcial"] > 0 for v in out.values()) >= 4
    return {"H": H, "por_valor": out, "aporta": bool(aporta)}


# ── minería de reglas ────────────────────────────────────────────────────
def _sharpe5(c: pd.Series) -> float:
    """Para ORDENAR reglas dentro de un valor: Sharpe de periodos de 5 sesiones, sin anualizar."""
    v = c.to_numpy()[::5]
    r = v[1:] / v[:-1] - 1
    return r.mean() / r.std(ddof=1) if len(r) > 2 and r.std(ddof=1) > 0 else -np.inf


def _cdev(sim: X.Simulador, x) -> pd.Series:
    """La curva del desarrollo acaba con su última decisión: sin la cola plana hasta el final de los datos."""
    c = sim.curva(x)
    fin = min(int(sim.i[-1]) + 1 + sim.paso, len(sim.fechas) - 1)
    return c.loc[:sim.fechas[fin]]


def reglas(ps: np.ndarray, ab: np.ndarray, cortes_ab: list):
    yield "siempre dentro", np.ones(len(ps), bool)
    for a in UMBRALES:
        for q, cab in zip(CUANTILES, cortes_ab):
            yield f"p ≥ {a} y abanico ≤ c{int(q * 100)}", (ps >= a) & (ab <= cab)
            yield f"p ≤ {a} y abanico ≤ c{int(q * 100)}", (ps <= a) & (ab <= cab)


def _datos_mineria(d, simbolos):
    datos = {}
    for s in simbolos:
        p = _pred(d, s, 5).sort_values("fecha").iloc[::5].reset_index(drop=True)
        p["f"] = pd.to_datetime(p.fecha)
        p["abanico"] = p.r_p90 - p.r_p10
        coste = I.COSTES.get(s, I.COSTE_ACCIONES)
        dev, tst = p[p.f < pd.Timestamp(CORTE)].reset_index(drop=True), p[p.f >= pd.Timestamp(CORTE)].reset_index(drop=True)
        v = _velas(d, s)
        datos[s] = (dev, tst, X.Simulador(v, dev.f, 5, coste), X.Simulador(v, tst.f, 5, coste))
    return datos


def _minar(datos, simbolos, rng=None, solo_desarrollo=False):
    """Elige en el desarrollo y aplica en la prueba. Los cortes del abanico, SÓLO del desarrollo."""
    curvas_t, curvas_d, elegidas = {}, {}, {}
    for s in simbolos:
        dev, tst, sd, st = datos[s]
        pd_, ad, pt, at = dev.p_subida.to_numpy(), dev.abanico.to_numpy(), tst.p_subida.to_numpy(), tst.abanico.to_numpy()
        if rng is not None:                      # placebo: las salidas barajadas entre fechas, en cada periodo
            i = rng.permutation(len(pd_))
            pd_, ad = pd_[i], ad[i]
            if not solo_desarrollo:
                j = rng.permutation(len(pt))
                pt, at = pt[j], at[j]
        cortes = [np.quantile(ad, q) for q in CUANTILES]
        nombre, x = max(reglas(pd_, ad, cortes), key=lambda r: _sharpe5(_cdev(sd, r[1])))
        curvas_d[s], elegidas[s] = _cdev(sd, x), nombre
        curvas_t[s] = st.curva(dict(reglas(pt, at, cortes))[nombre])
    return curvas_d, curvas_t, elegidas


def mineria(d: pathlib.Path, simbolos: list = SIMBOLOS, placebos: int = 200) -> dict:
    datos = _datos_mineria(d, simbolos)
    sh = lambda c: X.sharpe(X.semanales(X.cartera(c)))        # noqa: E731
    cd, ct, eleg = _minar(datos, simbolos)
    bh_d = sh({s: _cdev(datos[s][2], np.ones(len(datos[s][0]))) for s in simbolos})
    bh_t = sh({s: datos[s][3].curva(np.ones(len(datos[s][1]))) for s in simbolos})
    rng = np.random.default_rng(20261028)
    plac_t = np.array([sh(_minar(datos, simbolos, rng)[1]) for _ in range(placebos)])
    rng = np.random.default_rng(7)
    plac_d = np.array([sh(_minar(datos, simbolos, rng, solo_desarrollo=True)[0]) for _ in range(placebos)])
    r = {"elegidas": eleg, "desarrollo": {"reglas": sh(cd), "mantener": bh_d, "placebo_p50": float(np.median(plac_d)),
                                          "placebo_p95": float(np.percentile(plac_d, 95))},
         "prueba": {"reglas": sh(ct), "mantener": bh_t, "placebo_p50": float(np.median(plac_t)),
                    "placebo_p95": float(np.percentile(plac_t, 95)), "p_placebo_mejor": float((plac_t >= sh(ct)).mean())},
         "curvas_prueba": {s: c for s, c in ct.items()}}
    r["aprueba"] = bool(r["prueba"]["reglas"] > bh_t and r["prueba"]["reglas"] > r["prueba"]["placebo_p95"])
    return r
