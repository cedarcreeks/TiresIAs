# -*- coding: utf-8 -*-
"""U4, segunda implementación: las mismas cifras por otro camino, para no fiarse de una sola (29-oct).

Independiente de `u4.py` en todo lo que decide el resultado: lee las velas y las puntuaciones con pandas por fecha (no por
posición), el RankIC sale de `DataFrame.rank` y la cartera es una traducción línea a línea de `TopkDropoutStrategy.
generate_trade_decision` de Qlib (`qlib/contrib/strategy/signal_strategy.py`), con la posición en un diccionario y el
recuento de días de `Position.add_count_all`. Dos convenciones de contabilidad se pueden elegir, para medir cuánto pesan:

- `reparto`: Qlib divide el efectivo entre TODOS los que quiere comprar (`len(buy)`), aunque alguno no cotice ese día y
  no se compre; `u4.py`, sólo entre los que se pueden comprar.
- `comision`: Qlib compra `valor / precio` acciones y paga `valor × (1 + c)`; `u4.py` compra `valor × (1 − c) / precio`
  y paga `valor`.

Con las de `u4.py` las cifras tienen que coincidir; con las de Qlib, la diferencia es lo que cuesta la simplificación.

    python -m tiresias.verificar_u4 --dir <velas> --pred <predicciones>
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np
import pandas as pd

H, DESDE = 10, "2024-07-01"


def leer(d: pathlib.Path, dp: pathlib.Path) -> tuple:
    """Apertura y cierre ajustados y puntuación, en DataFrames fecha × valor sobre el calendario del SPY."""
    simbolos = [s for s in json.loads((d / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != "SPY"]
    cal = pd.read_csv(d / "velas_SPY.csv", index_col=0, parse_dates=True).index
    cal = cal[cal >= pd.Timestamp(DESDE)]
    aper, cierre, punt = {}, {}, {}
    for s in simbolos:
        v = pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")
        factor = v["adjclose"] / v["close"]
        aper[s], cierre[s] = (v["open"] * factor).reindex(cal), v["adjclose"].reindex(cal)
        p = pd.read_csv(dp / f"pred_{s}.csv", parse_dates=["fecha"], float_precision="round_trip")
        punt[s] = p.set_index("fecha")["puntuacion"].reindex(cal)
    return pd.DataFrame(aper), pd.DataFrame(cierre), pd.DataFrame(punt)


def rankic(punt: pd.DataFrame, aper: pd.DataFrame, minimo: int = 100) -> pd.Series:
    """En cada fecha t de 10 en 10: Spearman entre la puntuación de t y la apertura t+1 → t+11."""
    fechas = punt.index
    out = {}
    for i in range(0, len(fechas) - 1 - H, H):
        r = aper.iloc[i + 1 + H] / aper.iloc[i + 1] - 1.0
        par = pd.DataFrame({"s": punt.iloc[i], "r": r}).dropna()
        out[fechas[i]] = par.rank().corr().iloc[0, 1] if len(par) >= minimo else np.nan
    return pd.Series(out)


def p_t_unilateral(t: float, gl: int, pasos: int = 200_000) -> float:
    """P(T ≥ t) de una t de Student, integrando la densidad (Simpson) en vez de con la beta incompleta de `estadistica`."""
    if gl < 1 or not math.isfinite(t):
        return float("nan") if not math.isinf(t) else (0.0 if t > 0 else 1.0)
    c = math.exp(math.lgamma((gl + 1) / 2) - math.lgamma(gl / 2)) / math.sqrt(gl * math.pi)
    f = lambda x: c * (1 + x * x / gl) ** (-(gl + 1) / 2)          # noqa: E731
    a, b = 0.0, abs(t)                                               # ∫0^|t|, por simetría
    h = (b - a) / pasos
    s = f(a) + f(b) + sum((4 if k % 2 else 2) * f(a + k * h) for k in range(1, pasos))
    medio = s * h / 3
    return 0.5 - medio if t >= 0 else 0.5 + medio


def cartera_qlib(punt: pd.DataFrame, aper: pd.DataFrame, cierre: pd.DataFrame, topk: int = 50, n_drop: int = 5,
                 hold_thresh: int = 5, riesgo: float = 0.95, c_compra: float = 0.0010, c_venta: float = 0.0015,
                 reparto: str = "u4", comision: str = "u4") -> dict:
    """La cartera de `TopkDropoutStrategy`, paso a paso como Qlib. La señal del cierre de la fecha k decide las órdenes
    a la apertura de la fecha k+1; el valor se mide al cierre con el último precio conocido de cada valor."""
    fechas = punt.index
    efectivo, pos, cuenta = 1.0, {}, {}                  # acciones y días en cartera por valor
    ultimo = {}
    valores, movido = [1.0], 0.0
    for s, c in cierre.iloc[0].dropna().items():
        ultimo[s] = c
    for k in range(1, len(fechas)):
        hoy = fechas[k]
        score = punt.iloc[k - 1].dropna()
        if len(score):
            cotiza = aper.loc[hoy].notna()
            last = score.reindex(list(pos)).sort_values(ascending=False, kind="mergesort").index
            today = list(score[~score.index.isin(last)].sort_values(ascending=False, kind="mergesort").index)
            today = today[:n_drop + topk - len(last)]
            comb = score.reindex(last.union(pd.Index(today))).sort_values(ascending=False, kind="mergesort").index
            sell = last[last.isin(list(comb)[-n_drop:])]
            buy = today[:len(sell) + topk - len(last)]
            for s in list(pos):
                if not cotiza.get(s, False) or s not in sell or cuenta[s] < hold_thresh:
                    continue
                v = pos.pop(s) * aper.at[hoy, s]
                cuenta.pop(s)
                efectivo += v - v * c_venta
                movido += v
            n = len(buy) if reparto == "qlib" else sum(bool(cotiza.get(s, False)) for s in buy)
            valor = efectivo * riesgo / n if n else 0.0
            for s in buy:
                if not cotiza.get(s, False):
                    continue
                precio = aper.at[hoy, s]
                if comision == "qlib":
                    pos[s] = pos.get(s, 0.0) + valor / precio
                    efectivo -= valor * (1 + c_compra)
                else:
                    pos[s] = pos.get(s, 0.0) + valor * (1 - c_compra) / precio
                    efectivo -= valor
                cuenta.setdefault(s, 0)
                movido += valor
        for s in pos:                                     # Position.add_count_all al cerrar el día
            cuenta[s] += 1
        for s, c in cierre.loc[hoy].dropna().items():
            ultimo[s] = c
        valores.append(efectivo + sum(n_acc * ultimo[s] for s, n_acc in pos.items()))
    return {"valor": pd.Series(valores, index=fechas), "rotacion_anual": movido / (len(fechas) / 252)}


def sharpe(r: pd.Series) -> float:
    return float(r.mean() / r.std(ddof=1) * math.sqrt(252))


def verificar(d: pathlib.Path, dp: pathlib.Path) -> dict:
    aper, cierre, punt = leer(d, dp)
    ic = rankic(punt, aper).dropna()
    t = float(ic.mean() / (ic.std(ddof=1) / math.sqrt(len(ic))))
    todos = cierre.pct_change(fill_method=None).iloc[1:].mean(axis=1)
    años = (punt.index[-1] - punt.index[0]).days / 365.25
    out = {"rankic_10": {"n": len(ic), "media": float(ic.mean()), "t": t, "p": p_t_unilateral(t, len(ic) - 1)},
           "sharpe_todos": sharpe(todos), "cagr_todos": float((1 + todos).prod() ** (1 / años) - 1)}
    for reparto, comision in (("u4", "u4"), ("qlib", "qlib")):
        c = cartera_qlib(punt, aper, cierre, reparto=reparto, comision=comision)
        r = c["valor"].pct_change().dropna()
        out[f"cartera_{reparto}"] = {"sharpe": sharpe(r), "cagr": float(c["valor"].iloc[-1] ** (1 / años) - 1),
                                     "rotacion_anual": c["rotacion_anual"]}
    return out


def comparar(primaria: dict, segunda: dict) -> list:
    """(cifra, primaria, segunda, diferencia) de lo que tiene que coincidir con las convenciones de `u4.py`."""
    pares = [("RankIC medio", primaria["rankic_10"]["media"], segunda["rankic_10"]["media"]),
             ("RankIC t", primaria["rankic_10"]["t"], segunda["rankic_10"]["t"]),
             ("RankIC p", primaria["rankic_10"]["p"], segunda["rankic_10"]["p"]),
             ("RankIC n", primaria["rankic_10"]["n"], segunda["rankic_10"]["n"]),
             ("Sharpe cartera", primaria["sharpe_cartera"], segunda["cartera_u4"]["sharpe"]),
             ("CAGR cartera", primaria["cagr_cartera"], segunda["cartera_u4"]["cagr"]),
             ("rotación anual", primaria["rotacion_anual"], segunda["cartera_u4"]["rotacion_anual"]),
             ("Sharpe todos", primaria["sharpe_todos"], segunda["sharpe_todos"]),
             ("CAGR todos", primaria["cagr_todos"], segunda["cagr_todos"])]
    return [(n, a, b, abs(a - b)) for n, a, b in pares]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--tolerancia", type=float, default=1e-9)
    a = ap.parse_args(argv)
    d, dp = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.pred).expanduser()
    primaria = json.loads((dp / "u4.json").read_text(encoding="utf-8"))
    segunda = verificar(d, dp)
    (dp / "u4_segunda.json").write_text(json.dumps(segunda, indent=1), encoding="utf-8")
    filas = comparar(primaria, segunda)
    distintas = [f for f in filas if not f[3] <= a.tolerancia]
    for n, x, y, dif in filas:
        print(f"{'⛔' if (n, x, y, dif) in distintas else '✓'} {n:15} primaria {x:+.9f}  segunda {y:+.9f}  dif {dif:.1e}")
    q = segunda["cartera_qlib"]
    print(f"con las convenciones de Qlib: Sharpe {q['sharpe']:.4f}, CAGR {q['cagr']:+.4%} "
          f"(dif. con u4.py {q['sharpe'] - segunda['cartera_u4']['sharpe']:+.4f} y "
          f"{q['cagr'] - segunda['cartera_u4']['cagr']:+.4%})")
    if distintas:
        raise SystemExit(f"⛔ {len(distintas)} cifras no coinciden con la primera implementación")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
