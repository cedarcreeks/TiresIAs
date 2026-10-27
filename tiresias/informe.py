# -*- coding: utf-8 -*-
"""Los criterios de docs/PLAN.md sobre las predicciones guardadas por `tiresias.correr`.

    python -m tiresias.informe --dir ~/tiresias_resultados/cinco --salida docs/RESULTADOS_5.json
"""
from __future__ import annotations

import argparse
import json
import pathlib

import numpy as np
import pandas as pd

from tiresias import metricas as X

COSTES = {"BTC-EUR": 0.0149}          # el resto, 0,25 % (docs/PLAN.md); a verificar en la app
COSTE_ACCIONES = 0.0025
PASO = {1: 1, 5: 5}                   # diario y semanal


def cargar(d: pathlib.Path, simbolos: list, H: int) -> tuple:
    # round_trip: el parser rápido de read_csv yerra el último bit en ~98 % de las filas (medido)
    preds = {s: pd.read_csv(d / f"pred_{s}_H{H}.csv", float_precision="round_trip") for s in simbolos}
    velas = {s: pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
             for s in simbolos}
    return preds, velas


def condiciones(ic: dict, sh: dict, mejor: str, p_bh: float, p_ing: float, p95: float) -> dict:
    """Las cuatro de docs/PLAN.md. Un Sharpe que no se puede calcular (nan) no aprueba: toda comparación con nan
    es falsa."""
    k = sh["kronos"]
    return {"1 RankIC media > 0 con su intervalo del 90 %": bool(ic["ic90"][0] > 0),
            "2 Sharpe neto mejor que mantener y que la mejor ingenua, P ≥ 90 %":
                bool(k > sh["comprar y mantener"] and k > sh[mejor] and p_bh >= 0.9 and p_ing >= 0.9),
            "3 por encima del percentil 95 del placebo": bool(k > p95),
            "4 al menos 3 de 5 valores con RankIC > 0": sum(bool(v > 0) for v in ic["por_valor"].values()) >= 3}


def horizonte(d: pathlib.Path, simbolos: list, H: int, placebos: int = 1000, reps: int = 2000) -> dict:
    preds, velas = cargar(d, simbolos, H)
    paso = PASO[H]
    ic = X.rankic_media(preds, H, reps=reps)
    sims, dec_k, curvas = {}, {}, {k: {} for k in ("kronos", "comprar y mantener", "seguir la semana", "media de 200")}
    por_valor = {}
    for s in simbolos:
        coste = COSTES.get(s, COSTE_ACCIONES)
        dk = X.decisiones_kronos(preds[s], paso)
        dec_k[s] = dk
        sims[s] = X.Simulador(velas[s], dk.index, paso, coste)
        curvas["kronos"][s] = sims[s].curva(dk.to_numpy())
        curvas["comprar y mantener"][s] = sims[s].curva(np.ones(len(dk)))
        curvas["seguir la semana"][s] = sims[s].curva(X.decisiones_momento(velas[s], dk.index).to_numpy())
        curvas["media de 200"][s] = sims[s].curva(X.decisiones_media(velas[s], dk.index).to_numpy())
        bh = X.cagr(curvas["comprar y mantener"][s])
        por_valor[s] = {"rankic": ic["por_valor"][s], "coste": coste,
                        "cagr_kronos": X.cagr(curvas["kronos"][s]), "cagr_mantener": bh,
                        "sharpe_kronos": X.sharpe(X.semanales(curvas["kronos"][s])),
                        "sharpe_mantener": X.sharpe(X.semanales(curvas["comprar y mantener"][s])),
                        "dentro": float(dk.mean()),
                        "operaciones_año": float(np.abs(np.diff(dk.to_numpy().astype(float), prepend=0.0)).sum()
                                                 / ((dk.index[-1] - dk.index[0]).days / 365.25)),
                        "coste_equilibrio": X.coste_equilibrio(velas[s], dk, paso, bh)}
    sem = {k: X.semanales(X.cartera(v)) for k, v in curvas.items()}
    sh = {k: X.sharpe(v) for k, v in sem.items()}
    mejor = max(("seguir la semana", "media de 200"), key=lambda k: sh[k])
    p_bh, p_ing = X.p_mejor(sem["kronos"], sem["comprar y mantener"], reps), X.p_mejor(sem["kronos"], sem[mejor], reps)
    rng = np.random.default_rng(20261027)
    plac = []
    for _ in range(placebos):
        cur = {s: sims[s].curva(rng.permutation(dec_k[s].to_numpy())) for s in simbolos}
        plac.append(X.sharpe(X.semanales(X.cartera(cur))))
    p95 = float(np.nanpercentile(plac, 95))
    cond = condiciones(ic, sh, mejor, p_bh, p_ing, p95)
    return {"H": H, "paso": paso, "rankic": ic, "sharpe_cartera": sh, "mejor_ingenua": mejor,
            "p_mejor_que_mantener": p_bh, "p_mejor_que_ingenua": p_ing, "placebo_p95": p95,
            "cagr_cartera": {k: X.cagr(X.cartera(v)) for k, v in curvas.items()},
            "por_valor": por_valor, "condiciones": cond, "aporta": all(cond.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--simbolos", nargs="+", default=["IDR.MC", "ACS.MC", "SPY", "3USL.MI", "BTC-EUR"])
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    out = {"procedencia": json.loads((d / "procedencia.json").read_text(encoding="utf-8"))}
    for H in (1, 5):
        out[f"H{H}"] = horizonte(d, a.simbolos, H)
    preds12, _ = cargar(d, a.simbolos, 12)
    out["H12_exploratorio"] = X.rankic_media(preds12, 12)
    pathlib.Path(a.salida).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=float), encoding="utf-8")
    for H in (1, 5):
        r = out[f"H{H}"]
        print(f"H={H}: {'APORTA' if r['aporta'] else 'NO APORTA'} · RankIC media {r['rankic']['media']:+.3f} "
              f"[{r['rankic']['ic90'][0]:+.3f}, {r['rankic']['ic90'][1]:+.3f}] · Sharpe Kronos {r['sharpe_cartera']['kronos']:.2f} "
              f"· mantener {r['sharpe_cartera']['comprar y mantener']:.2f} · placebo p95 {r['placebo_p95']:.2f}")
        for k, v in r["condiciones"].items():
            print(f"   {'sí' if v else 'NO'} · {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
