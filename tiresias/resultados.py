# -*- coding: utf-8 -*-
"""docs/RESULTADOS.md: los agregados de un veredicto, sin ningún precio (el repo es público).

    python -m tiresias.resultados --dir ~/tiresias_resultados/cinco --salida docs/RESULTADOS.md
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pandas as pd

from tiresias import metricas as X


def f(x: float, n: int = 3, signo: bool = True) -> str:
    return (f"{x:+.{n}f}" if signo else f"{x:.{n}f}").replace(".", ",").replace("-", "−")


def p(x: float, n: int = 1, signo: bool = True) -> str:
    return f(x * 100, n, signo) + " %"


def criterios(cond: dict) -> str:
    """«k de N», con k CONTADO. Unir los números de los cumplidos con «de 4» escribió «4 de 4» donde se
    cumplía uno solo, el 4.º (27-oct): un veredicto que se lee al revés."""
    si = [k.split(" ", 1)[0] for k, v in cond.items() if v]
    txt = f"{len(si)} de {len(cond)}"
    return txt + (" (" + ", ".join(f"el {k}.º" for k in si) + ")" if si else "")


def markdown(r: dict, d: pathlib.Path) -> str:
    pro, S = r["procedencia"], list(r["H5"]["por_valor"])
    L = [f"# Resultados de la F2: Kronos-small sobre {len(S)} valores ({pro['fin_ejecucion'][:10]})", "",
         f"Criterios fijados antes de medir en [PLAN.md](PLAN.md) (`8f665d0`). Predicciones con `{pro['commit']}` en CPU; "
         f"datos diarios de Yahoo descargados el {pro['dia_descarga']}, del {pro['desde']} al {pro['fin']}, {pro['N']} "
         f"trayectorias por fecha, {pro['L']} velas de historia. Aquí sólo hay agregados: ningún precio.", "",
         "**Veredicto: Kronos " + ("aporta" if any(r[H]["aporta"] for H in ("H1", "H5")) else "no aporta en ningún horizonte")
         + ".**", "",
         "| | RankIC media (IC 90 %) | Sharpe cartera Kronos | mantener | mejor ingenua | P(mejor que mantener) | placebo p95 "
         "| criterios cumplidos |", "|---|---|---|---|---|---|---|---|"]
    for H, nom in (("H1", "diario (H = 1)"), ("H5", "semanal (H = 5)")):
        h = r[H]
        L.append(f"| {nom} | {f(h['rankic']['media'])} ({f(h['rankic']['ic90'][0])} a {f(h['rankic']['ic90'][1])}) | "
                 f"{f(h['sharpe_cartera']['kronos'], 2, False)} | {f(h['sharpe_cartera']['comprar y mantener'], 2, False)} | "
                 f"{f(h['sharpe_cartera'][h['mejor_ingenua']], 2, False)} ({h['mejor_ingenua']}) | "
                 f"{f(h['p_mejor_que_mantener'], 2, False)} | {f(h['placebo_p95'], 2, False)} | {criterios(h['condiciones'])} |")
    e = r["H12_exploratorio"]
    L += ["", "Criterios: 1, RankIC media por encima de 0 con su intervalo; 2, Sharpe neto mejor que mantener y que la mejor "
          "regla ingenua, con P ≥ 90 %; 3, por encima del percentil 95 del placebo; 4, al menos 3 de 5 valores con RankIC > 0.",
          "", f"A 12 sesiones (exploratorio): RankIC media {f(e['media'])} ({f(e['ic90'][0])} a {f(e['ic90'][1])}).", "",
          "## Por valor", "",
          "| valor | RankIC 1 / 5 / 12 | cobertura 10–90 a 5 (debería ser 80 %) | CAGR Kronos semanal | mantener "
          "| operaciones/año | coste de equilibrio |", "|---|---|---|---|---|---|---|"]
    for s in S:
        q = X.sin_solape(pd.read_csv(d / f"pred_{s}_H5.csv", float_precision="round_trip"), 5)
        v5 = r["H5"]["por_valor"][s]
        ce = v5["coste_equilibrio"]
        L.append(f"| {s} | {f(r['H1']['por_valor'][s]['rankic'])} / {f(v5['rankic'])} / {f(e['por_valor'][s])} | "
                 f"{p(X.cobertura(q), 0, False)} | {p(v5['cagr_kronos'])} | {p(v5['cagr_mantener'])} | "
                 f"{v5['operaciones_año']:.0f} | {'ni gratis' if ce is None else p(ce, 2, False)} |")
    L += ["", "Costes por operación: 0,25 % en acciones y ETF y 1,49 % en bitcoin. Rentabilidad de apertura a apertura, con "
          "dividendos; «coste de equilibrio», el coste con el que Kronos igualaría a mantener (ni gratis: ni sin costes).", "",
          "**Lo más claro**: su banda del percentil 10 al 90 contiene lo real muy por debajo del 80 % nominal; Kronos dibuja "
          "futuros demasiado parecidos entre sí. Es lo primero que tratará de pulir la fase 4.", "",
          "**A su favor, y aun así no pasa**: en las acciones españolas, ~6–8 % de las aperturas de Yahoo son idénticas al "
          "cierre anterior; si son rellenos, la simulación le regala el salto de la noche esos días.", "",
          "## Reproducir", "", "```bash",
          f"python -m tiresias.correr --simbolos {' '.join(S)} --H 1 5 12 --fin {pro['fin']} --dispositivo cpu --salida <dir>",
          "python -m tiresias.informe --dir <dir> --salida <dir>/veredicto.json",
          "python -m tiresias.resultados --dir <dir> --salida docs/RESULTADOS.md", "```", "",
          "Con otro día de descarga, Yahoo puede haber revisado algún dato; con otro dispositivo, el azar del muestreo cambia "
          "(la semilla fija sólo reproduce en el mismo). Cada predicción guarda su procedencia."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--salida", required=True)
    a = ap.parse_args(argv)
    d = pathlib.Path(a.dir).expanduser()
    r = json.loads((d / "veredicto.json").read_text(encoding="utf-8"))
    pathlib.Path(a.salida).write_text(markdown(r, d), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
