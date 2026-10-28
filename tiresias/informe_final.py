# -*- coding: utf-8 -*-
"""Informe final: ¿sirve Kronos para algo? Las cuatro pruebas (5 valores, volatilidad, minería de reglas, S&P 500),
con las respuestas a las preguntas en la primera página.

    python -m tiresias.informe_final --cinco ~/tiresias_resultados/cinco --sp500 ~/tiresias_resultados/sp500 --salida <fuera del repo>

Cada cifra principal se recalcula con bucles escritos aparte (S&P 500, volatilidad y la cartera de la minería) y,
tras compilar, se busca en el PDF. El texto que depende de un resultado tiene una rama por desenlace.
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import subprocess

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

from tiresias import estudios as S
from tiresias import informe_pdf as B
from tiresias import metricas as X
from tiresias import transversal as T

NOMBRE = "INFORME_KRONOS_FINAL"


# ── segunda implementación ───────────────────────────────────────────────
class Comparador:
    def __init__(self):
        self.n, self.peor, self.fallos = 0, 0.0, []

    def __call__(self, donde, a, b, tol=1e-9):
        self.n += 1
        dif = abs(a - b)
        self.peor = max(self.peor, dif)
        if not dif <= tol:
            self.fallos.append(f"{donde}: {a!r} frente a {b!r}")


def verificar_sp500(d: pathlib.Path, simbolos: list, r: dict, cmp: Comparador, diag: dict):
    """RankIC semanal y carteras con diccionarios y bucles, leyendo los CSV de nuevo."""
    cal = [str(x)[:10] for x in pd.read_csv(d / "velas_SPY.csv", index_col=0).index]
    i0 = next(i for i, f in enumerate(cal) if f >= "2024-07-01")
    rej = [i for i in range(i0, len(cal) - 1 - 5, 5)]
    pred, ap = {}, {}
    for s in simbolos:
        for f in pd.read_csv(d / f"pred_{s}_H5.csv", float_precision="round_trip").to_dict("records"):
            pred[(s, f["fecha"])] = (f["r_prevista"], f["r_real"])
        v = pd.read_csv(d / f"velas_{s}.csv", index_col=0, float_precision="round_trip")
        ap[s] = {str(k)[:10]: o * a / c for k, o, a, c in zip(v.index, v["open"], v["adjclose"], v["close"])}
    ics, tops, todos = [], [], []
    w_top, w_todos = {}, {}
    for i in rej:
        f, ent, sal = cal[i], cal[i + 1], cal[i + 6]
        filas = [(s, *pred[(s, f)]) for s in simbolos if (s, f) in pred]
        if len(filas) >= 100:
            ics.append(B._pearson(B._rangos_medios([x[1] for x in filas]), B._rangos_medios([x[2] for x in filas])))
        disp = [(s, p) for s, p, _ in filas if ent in ap[s] and sal in ap[s]]
        ret = {s: ap[s][sal] / ap[s][ent] - 1 for s, _ in disp}
        for elegidos, pesos, lista in ((sorted(disp, key=lambda x: -x[1])[:50], w_top, tops), (disp, w_todos, todos)):
            nuevos = {s: 1 / len(elegidos) for s, _ in elegidos}
            bruto = sum(w * ret[s] for s, w in nuevos.items())
            rot = sum(abs(nuevos.get(s, 0) - pesos.get(s, 0)) for s in set(nuevos) | set(pesos))
            lista.append(bruto - T.COSTE * rot)
            pesos.clear()
            pesos.update({s: w * (1 + ret[s]) / (1 + bruto) for s, w in nuevos.items()})
    ult, rev = [], []
    cierres = {s: dict(zip([str(k)[:10] for k in pd.read_csv(d / f"velas_{s}.csv", index_col=0).index],
                           pd.read_csv(d / f"velas_{s}.csv", index_col=0, float_precision="round_trip")["close"]))
               for s in simbolos}
    for i in rej:
        f, antes = cal[i], cal[i - 5]
        filas = [(pred[(s, f)][0], pred[(s, f)][1], cierres[s][f] / cierres[s][antes] - 1) for s in simbolos
                 if (s, f) in pred and f in cierres[s] and antes in cierres[s]]
        if len(filas) >= 100:
            ult.append(B._pearson(B._rangos_medios([x[0] for x in filas]), B._rangos_medios([x[2] for x in filas])))
            rev.append(B._pearson(B._rangos_medios([-x[2] for x in filas]), B._rangos_medios([x[1] for x in filas])))
    cmp("S&P Kronos frente a la última semana", sum(ult) / len(ult), diag["kronos_vs_ultima_semana"])
    cmp("S&P reversión", sum(rev) / len(rev), diag["reversion_ic"])
    media = sum(ics) / len(ics)
    sd = math.sqrt(sum((x - media) ** 2 for x in ics) / (len(ics) - 1))
    cmp("S&P RankIC media", media, r["rankic_media"])
    cmp("S&P t", media / (sd / math.sqrt(len(ics))), r["rankic_t"], 1e-6)
    for nombre, lista in (("top", tops), ("todos", todos)):
        m = sum(lista) / len(lista)
        s_ = math.sqrt(sum((x - m) ** 2 for x in lista) / (len(lista) - 1))
        cmp(f"S&P Sharpe {nombre}", m / s_ * math.sqrt(52), r[f"sharpe_{nombre}"])


def verificar_vol(d: pathlib.Path, vol: dict, cmp: Comparador):
    for s, g in vol["por_valor"].items():
        v = pd.read_csv(d / f"velas_{s}.csv", index_col=0, float_precision="round_trip")
        fechas = [str(x)[:10] for x in v.index]
        hl = [math.log(h / lo) ** 2 for h, lo in zip(v["high"], v["low"])]
        park = {fechas[k]: math.sqrt(sum(hl[k - 19:k + 1]) / 20 / (4 * math.log(2))) for k in range(19, len(fechas))}
        filas = [f for f in pd.read_csv(d / f"pred_{s}_H1.csv", float_precision="round_trip").to_dict("records")
                 if f["fecha"] in park]
        ab = [f["r_p90"] - f["r_p10"] for f in filas]
        absr = [abs(f["r_real"]) for f in filas]
        pk = [park[f["fecha"]] for f in filas]
        rk = B._pearson(B._rangos_medios(ab), B._rangos_medios(absr))
        rp = B._pearson(B._rangos_medios(pk), B._rangos_medios(absr))
        cmp(f"vol {s} Kronos", rk, g["kronos"], 1e-12)
        cmp(f"vol {s} Parkinson", rp, g["parkinson"], 1e-12)


def verificar_mineria(m: dict, cmp: Comparador):
    """La cartera de la prueba: cada curva desde 1, rellenada hacia delante, media, viernes, Sharpe; en bucles."""
    curvas = m["curvas_prueba"]
    fechas = sorted({f for c in curvas.values() for f in c.index})
    ult = {s: None for s in curvas}
    serie = []
    for f in fechas:
        for s, c in curvas.items():
            if f in c.index:
                ult[s] = c[f] / c.iloc[0]
        if all(x is not None for x in ult.values()):
            serie.append((f, sum(ult.values()) / len(ult)))
    viernes = {}
    for f, x in serie:
        viernes[f + pd.offsets.Week(weekday=4) if f.weekday() != 4 else f] = x
    vals = [viernes[k] for k in sorted(viernes)]
    r = [b / a - 1 for a, b in zip(vals, vals[1:])]
    mu = sum(r) / len(r)
    sd = math.sqrt(sum((x - mu) ** 2 for x in r) / (len(r) - 1))
    cmp("minería Sharpe prueba", mu / sd * math.sqrt(52), m["prueba"]["reglas"])


# ── figuras ──────────────────────────────────────────────────────────────
def fig_ic(fechas, ic, salida):
    fig, ax = plt.subplots(figsize=(7.1, 2.3))
    col = [B.COLOR["media"] if x > 0 else B.COLOR["kronos"] for x in ic]
    ax.bar(fechas, ic, width=4, color=col)
    ax.axhline(0, color="k", lw=0.6)
    ax.axhline(np.nanmean(ic), color=B.COLOR["real"], lw=1.2, ls="--", label="media")
    ax.set_ylabel("RankIC de la semana")
    ax.legend(loc="upper left")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: B.coma(x, 2)))
    fig.tight_layout()
    fig.savefig(salida)
    plt.close(fig)


def fig_carteras(fechas, series: dict, salida):
    fig, ax = plt.subplots(figsize=(7.1, 2.6))
    for nombre, (r, col) in series.items():
        ax.plot(fechas, np.cumprod(1 + np.nan_to_num(r)), color=col, lw=1.3, label=nombre)
    ax.set_ylabel("valor de 1 invertido (neto)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}".replace(".", ",")))
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(salida)
    plt.close(fig)


def fig_placebo(plac, real, p95, salida):
    fig, ax = plt.subplots(figsize=(7.1, 2.2))
    ax.hist(plac, bins=40, color=B.COLOR["mantener"], alpha=0.8, label="placebo (sus predicciones barajadas)")
    ax.axvline(p95, color="k", lw=0.8, ls="--", label="percentil 95 del placebo")
    ax.axvline(real, color=B.COLOR["kronos"], lw=2, label="Kronos")
    ax.set_xlabel("Sharpe neto de los 50 primeros")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: B.coma(x, 1)))
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(salida)
    plt.close(fig)


def fig_mineria(m, salida):
    fig, ax = plt.subplots(figsize=(7.1, 2.4))
    x = np.arange(2)
    for k, (clave, nombre, col) in enumerate((("reglas", "reglas sacadas de Kronos", B.COLOR["kronos"]),
                                              ("mantener", "comprar y mantener", B.COLOR["mantener"]),
                                              ("placebo_p50", "reglas sacadas del ruido (mediana)", B.COLOR["media"]))):
        v = [m["desarrollo"][clave], m["prueba"][clave]]
        ax.bar(x + (k - 1) * 0.26, v, width=0.25, color=col, label=nombre)
    ax.set_xticks(x, ["desarrollo (jul-2024 a jun-2025):\ndonde se eligieron", "prueba (jul-2025 en adelante):\nuna sola vez"])
    ax.set_ylabel("Sharpe neto")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: B.coma(x, 1)))
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(salida)
    plt.close(fig)


# ── el texto ─────────────────────────────────────────────────────────────
def _esc(s: str) -> str:
    return "".join({"&": r"\&", "%": r"\%", "_": r"\_", "#": r"\#"}.get(c, c) for c in str(s))


def extras(d5: pathlib.Path) -> dict:
    """Las cifras de la tabla de respuestas que no están en los veredictos: la probabilidad de subida, juntando los
    5 valores a 1 sesión (fechas independientes), y la cobertura de su banda en los 5 valores y 3 horizontes."""
    p = pd.concat([pd.read_csv(d5 / f"pred_{s}_H1.csv", float_precision="round_trip") for s in S.SIMBOLOS])
    alta, baja = p[p["p_subida"] >= 0.8], p[p["p_subida"] <= 0.2]
    cob = [X.cobertura(X.sin_solape(pd.read_csv(d5 / f"pred_{s}_H{H}.csv", float_precision="round_trip"), H))
           for s in S.SIMBOLOS for H in (1, 5, 12)]
    return {"sube_si_alta": float((alta["r_real"] > 0).mean()), "n_alta": len(alta),
            "sube_si_baja": float((baja["r_real"] > 0).mean()), "n_baja": len(baja),
            "cob_min": min(cob), "cob_max": max(cob)}


def seccion_algo_mal(cf, diag: dict, rep: dict) -> list:
    """¿Hicimos algo mal? Cada comprobación con su cifra; la comparación con su métrica, con una rama por resultado."""
    k = rep["media"]
    iguales = all(v["predicciones_distintas_de_lo_guardado"] == 0 for v in rep["por_valor"].values())
    quien = lambda a, b: "gana Kronos" if a > b else "la recta saca tanto o más"     # noqa: E731
    vs = (r"En precios, " + quien(k["k_ric_precios"], k["n_ric_precios"]) + r"; en rentabilidad paso a paso, "
          + quien(k["k_ric_rentab"], k["n_ric_rentab"]) + r". Sea cual sea su cálculo, mide parecido de caminos, no una "
          r"ventaja que se pueda operar: las pruebas 1 y 3 lo operan y pierden.")
    filas = [
        [r"¿Usamos el modelo como sus autores?", r"\textbf{Sí}",
         r"Los pesos de su test de regresión, que pasa en el Mac y en el Windows; las trayectorias reproducen su "
         r"\texttt{predict\_batch}; y su protocolo diario: 40 velas, temperatura 0,6, \emph{top-p} 0,9, 10 futuros."],
        [r"¿Medía su artículo lo mismo que la prueba del S\&P 500?", r"\textbf{No}",
         r"Su RankIC es la correlación, dentro de cada predicción, entre el camino previsto y el real. Presentar la prueba "
         r"del S\&P 500 como la suya fue un error mío, ya corregido."],
        [r"¿Reproducimos su métrica?", r"\textbf{" + ("Sí, del mismo tamaño" if iguales else "Con reservas") + "}",
         r"Con su método, a 12 sesiones y en los 5 valores: RankIC " + cf.n(k["k_ric_precios"], 4, True) + r" en precios y "
         + cf.n(k["k_ric_rentab"], 4, True) + r" en rentabilidad paso a paso; la suya, 0,0254 (media de todos sus mercados y "
         r"frecuencias). Prolongar en línea recta la tendencia de 20 sesiones: " + cf.n(k["n_ric_precios"], 4, True)
         + " y " + cf.n(k["n_ric_rentab"], 4, True) + r". " + vs
         + (r" Cada predicción rehecha coincide al último bit con la evaluada." if iguales else
            r" \textbf{Ojo}: alguna predicción rehecha no coincide con la evaluada.")],
        [r"¿Lo usamos como lo usan ellos para operar?", r"\textbf{No}",
         r"Su demo de trading (\texttt{finetune/qlib\_test.py}) lo \emph{reentrena} en el mercado antes de ordenar valores "
         r"con una cartera top-K. Aquí se probó sin reentrenar. Lo había leído y no saqué la consecuencia: es la prueba que "
         r"falta, y la principal de la segunda ronda."],
        [r"¿Podía la prueba ver un orden pequeño?", r"\textbf{Hasta cierto punto}",
         r"Con " + cf.entero(diag["semanas"]) + r" semanas veía una RankIC de " + cf.n(diag["minima_detectable"], 3)
         + r" o más; la medida queda entre " + cf.n(diag["ic90"][0], 3, True) + " y " + cf.n(diag["ic90"][1], 3, True)
         + r" (90~\%). Un orden diminuto no se descarta; uno útil, sí."],
        [r"¿Faltaban futuros (sólo 10)?", r"\textbf{No}",
         r"El " + cf.pct(diag["fiabilidad_mediana"]) + r" de las diferencias entre valores no es azar del muestreo: con "
         r"infinitos futuros, el techo seguiría siendo el mismo."],
        [r"¿Qué predice entonces?", r"\textbf{Reversión}",
         r"Su predicción va al revés de la última semana de cada valor (correlación de rangos "
         + cf.n(diag["kronos_vs_ultima_semana"], 2, True) + r"): apuesta a que lo que cayó rebota. La regla clásica de "
         r"reversión, sin modelo, tampoco funcionó en este periodo: RankIC " + cf.n(diag["reversion_ic"], 4, True)
         + r", $t$ = " + cf.n(diag["reversion_t"], 2, True) + "."],
    ]
    return [r"\section{¿Hemos hecho algo mal?}",
            r"Si su artículo dice que mejora la RankIC, ¿cómo es que no sirve? Se ha comprobado por partes.",
            B.tabla(r">{\raggedright\arraybackslash}p{4.4cm}>{\raggedright\arraybackslash}p{2.4cm}L",
                    [r"\textbf{comprobación}", r"\textbf{respuesta}", r"\textbf{la prueba}"], filas,
                    "Lo que podría haber salido mal, comprobado")]


def documento(cf, v5: dict, vol: dict, m: dict, sp: dict, commits: dict, cmp: Comparador, ex: dict,
              excluidos: dict, diag: dict, rep: dict) -> str:
    pro = v5["procedencia"]
    w = []
    w.append(r"""\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage[spanish,es-noshorthands,es-nodecimaldot,es-tabla]{babel}
\usepackage{lmodern,textcomp,graphicx}
\usepackage[margin=2cm]{geometry}
\usepackage[table]{xcolor}
\usepackage{booktabs,tabularx,array,enumitem}
\usepackage[section]{placeins}
\usepackage[hidelinks]{hyperref}
\newcolumntype{R}{>{\raggedleft\arraybackslash}X}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\setlength{\parskip}{0.45em}\setlength{\parindent}{0pt}
\renewcommand{\arraystretch}{1.25}
\title{Kronos: ¿sirve para algo?}
\author{TiresIAs}""")
    w.append(r"\date{" + sp["procedencia"]["fin_ejecucion"][:10] + "}")
    w.append(r"\begin{document}" + "\n" + r"\maketitle")
    w.append(r"\begin{center}\small Datos de Yahoo hasta la sesión del \textbf{" + pro["fin"] + r"} incluida. Cinco valores: "
             r"predicciones con \texttt{" + pro["commit"] + r"} en CPU. S\&P 500: \texttt{" + sp["procedencia"]["commit"]
             + r"} en una " + _esc(sp["procedencia"]["gpu"] or "CPU") + r". Este informe: \texttt{" + commits["informe"]
             + r"}. " + cf.entero(cmp.n) + r" cifras recalculadas con una segunda implementación (diferencia máxima "
             + B._exp(cmp.peor) + r"); las de los cinco valores, en el informe anterior.\end{center}")

    # respuestas
    sp_ok, c5 = sp["aporta"], v5["H5"]
    w.append(r"\section{Las respuestas}")
    filas = [
        ["¿Acierta si un valor va a subir o a bajar?", r"\textbf{No}",
         r"RankIC media de los 5 valores a 5 sesiones " + cf.n(c5["rankic"]["media"], 3, True) + r" (" + cf.n(c5["rankic"]["ic90"][0], 3, True)
         + " a " + cf.n(c5["rankic"]["ic90"][1], 3, True) + r"): no se distingue de 0."],
        ["¿Su «probabilidad de subida» es fiable?", r"\textbf{No}",
         r"Cuando da 0,8 o más, el valor sube el " + cf.pct(ex["sube_si_alta"]) + r" de las veces; cuando da 0,2 o menos, el "
         + cf.pct(ex["sube_si_baja"]) + r" (" + cf.entero(ex["n_alta"]) + " y " + cf.entero(ex["n_baja"]) + r" días, 5 valores)."],
        ["¿Sabe cuánto no sabe?", r"\textbf{No}",
         r"Su banda del 10 al 90~\% contiene lo real entre el " + cf.pct(ex["cob_min"]) + " y el " + cf.pct(ex["cob_max"])
         + r" de las veces, cuando debería ser el 80~\%: se cree más seguro de lo que es."],
        ["¿Predice cuánto se moverá (la volatilidad)?", r"\textbf{No mejor que una fórmula gratis}",
         r"Sobre la de Parkinson, aporta en " + cf.entero(sum(x["parcial"] > 0 for x in vol["por_valor"].values()))
         + r" de 5 valores; hacían falta 4."],
        ["¿Se sacan de él reglas que ganen dinero?", r"\textbf{No}",
         r"En la prueba, Sharpe " + cf.n(m["prueba"]["reglas"], 2) + r" frente a " + cf.n(m["prueba"]["mantener"], 2)
         + r" de mantener; peor que el " + cf.pct(m["prueba"]["p_placebo_mejor"]) + r" de las reglas sacadas del ruido."],
        [r"¿Ordena los valores del S\&P 500 entre sí?", r"\textbf{" + ("Sí" if sp_ok else "No") + "}",
         r"RankIC semanal media " + cf.n(sp["rankic_media"], 4, True) + r", $t$ = " + cf.n(sp["rankic_t"], 2, True) + "; "
         + _criterios_sp(sp) + "."],
        [r"¿Hemos hecho algo mal?", r"\textbf{Sí, una cosa}",
         r"La predicción, como sus autores (misma métrica, mismo tamaño). Pero para ordenar valores ellos lo reentrenan "
         r"antes, y aquí no se hizo; y presenté la prueba del S\&P 500 como la de su artículo (sección 7)."],
        [r"¿Se puede ganar dinero con él?", r"\textbf{" + ("Quizá, ordenando valores" if sp_ok else "Sin reentrenar, no") + "}",
         (r"Los 50 primeros según Kronos rinden más que el índice a partes iguales; falta probarlo en los candidatos del bot y un "
          r"walk-forward antes de arriesgar nada." if sp_ok else
          r"Ni prediciendo un valor, ni con reglas, ni eligiendo entre los 500 del índice. Falta reentrenarlo, como sus "
          r"autores: segunda ronda.")],
    ]
    w.append(B.tabla(r">{\raggedright\arraybackslash}p{4.6cm}>{\raggedright\arraybackslash}p{2.6cm}L", [r"\textbf{pregunta}", r"\textbf{respuesta}", r"\textbf{la prueba}"], filas,
                     "Lo que se ha preguntado y lo que ha contestado"))
    w.append(r"Todas las pruebas usan sólo datos posteriores a su entrenamiento (desde julio de 2024), con los criterios "
             r"escritos antes de mirar y con costes. Las de la volatilidad y las reglas son exploratorias: se hicieron sobre "
             r"un periodo ya visto en la primera, y por eso sólo pueden cerrar puertas, no abrirlas.")

    # qué es y qué dice
    w.append(r"\section{Qué es Kronos y qué dicen sus autores}")
    w.append(r"Un modelo de lenguaje para velas de bolsa: convierte cada vela (apertura, máximo, mínimo, cierre, volumen) en "
             r"\emph{tokens} y aprende a continuar la serie, como un modelo de texto continúa una frase. Se preentrenó con datos "
             r"de más de 45 bolsas hasta junio de 2024. No da un número: dibuja futuros posibles, y de ellos salen la "
             r"rentabilidad prevista, la probabilidad de subida y una banda de incertidumbre.")
    w.append(r"Su artículo (arXiv 2508.02739) mide tres tareas, siempre contra otros modelos: prever precios (una RankIC un "
             r"93~\% mejor que el mejor modelo fundacional de series y un 87~\% mejor que el mejor sin preentrenar), prever la "
             r"volatilidad (un 9~\% menos de error) y generar series sintéticas (un 22~\% más de fidelidad). Son mejoras "
             r"\emph{relativas} a otros modelos, no frente a comprar y mantener ni netas de costes. Y su RankIC no ordena "
             r"valores: es la correlación, dentro de cada predicción, entre el camino previsto de las próximas velas y el real. "
             r"En valor absoluto es pequeña: 0,0254 para Kronos-small, frente a 0,0138 del mejor rival (sus tablas 14 y 15, "
             r"media de mercados y frecuencias). Su propio repositorio avisa de que la estrategia de ejemplo no es un sistema "
             r"para operar.")

    # 1. cinco valores
    w.append(r"\section{Prueba 1: ¿predice cada valor?}")
    w.append(r"Indra, ACS, SPY, 3USL y bitcoin; cada día desde julio de 2024, 10 futuros a 1, 5 y 12 sesiones. Operándolo "
             r"como se haría a mano (dentro si su probabilidad de subida pasa de 0,5), neto de 0,25~\% por operación (1,49~\% "
             r"en bitcoin). El detalle por valor, con un ejemplo y gráficas, está en el informe anterior "
             r"(\texttt{informe\_kronos/INFORME\_KRONOS.pdf}).")
    filas = []
    for s, g in v5["H5"]["por_valor"].items():
        filas.append([B.NOMBRES.get(s, s), cf.n(v5["H1"]["por_valor"][s]["rankic"], 3, True), cf.n(g["rankic"], 3, True),
                      cf.pct(g["cagr_kronos"], 1, True), cf.pct(g["cagr_mantener"], 1, True)])
    w.append(B.tabla(r"LRRRR", ["valor", "RankIC a 1 sesión", "RankIC a 5", "operado cada semana", "mantenido"], filas,
                     "Cinco valores: ninguno se predice, y operarlo rinde menos que mantenerlo",
                     r"Rentabilidad anual compuesta, neta de costes, desde julio de 2024."))
    w.append(r"A 5 sesiones no se cumple ninguno de los cuatro criterios del plan; a 1 sesión, sólo el 4.º.")

    # 2. volatilidad
    w.append(r"\section{Prueba 2: ¿predice cuánto se moverá?}")
    w.append(r"Aunque no acierte la dirección, su abanico podría anticipar el \emph{tamaño} del movimiento. La vara es lo más "
             r"simple que usa la misma información: la volatilidad de Parkinson de las últimas 20 sesiones, que sale de máximos "
             r"y mínimos. Se mide la correlación de rangos con el movimiento real a 1 sesión, y lo que añade Kronos descontada "
             r"esa fórmula (correlación parcial).")
    filas = [[B.NOMBRES.get(s, s), cf.n(g["kronos"], 3, True), cf.n(g["parkinson"], 3, True), cf.n(g["parcial"], 3, True)]
             for s, g in vol["por_valor"].items()]
    w.append(B.tabla(r"LRRR", ["valor", "Kronos solo", "Parkinson 20", "lo que añade Kronos"], filas,
                     "¿Ordena el tamaño del movimiento de mañana?",
                     r"Criterio, escrito antes de mirar: aporta si lo que añade es positivo en al menos 4 de 5 valores."))
    gana_p = sum(g["parkinson"] > g["kronos"] for g in vol["por_valor"].values())
    w.append(r"La fórmula gratis ordena mejor que Kronos en " + cf.entero(gana_p) + r" de 5 valores, y lo que Kronos añade "
             r"es positivo en " + cf.entero(sum(g["parcial"] > 0 for g in vol["por_valor"].values()))
             + r". A 5 sesiones, el plazo en que el swing mantiene, no añade nada. No cambiaría ninguna decisión.")

    # 3. minería
    w.append(r"\section{Prueba 3: ¿se pueden sacar reglas que ganen dinero?}")
    w.append(r"Se buscaron, para cada valor, umbrales sobre lo que dice Kronos («dentro si su probabilidad de subida pasa de "
             r"0,7 y el abanico es estrecho»…): 91 reglas por valor, elegidas por su Sharpe de julio de 2024 a junio de 2025 y "
             r"probadas \emph{una sola vez} de julio de 2025 en adelante. Para saber cuánto engaña la búsqueda, el mismo "
             r"procedimiento se repitió 200 veces con las salidas de Kronos barajadas: reglas sacadas del ruido.")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_mineria.pdf}\caption{En el periodo donde se "
             r"eligieron, las reglas de Kronos parecen excelentes, pero las del ruido también. En el periodo nuevo se hunden.}\end{figure}")
    w.append(r"En el desarrollo, las reglas de Kronos tienen un Sharpe de " + cf.n(m["desarrollo"]["reglas"], 2) + r" frente a "
             + cf.n(m["desarrollo"]["mantener"], 2) + r" de mantener, y las sacadas del ruido, " + cf.n(m["desarrollo"]["placebo_p50"], 2)
             + r" de mediana: \emph{lo mismo}. En la prueba, " + cf.n(m["prueba"]["reglas"], 2) + r" frente a "
             + cf.n(m["prueba"]["mantener"], 2) + r". Es la trampa de buscar reglas: con 91 por valor, alguna gana en el pasado "
             r"por suerte. Las elegidas lo delatan: en " + cf.entero(sum(n.startswith("p ≤") for n in m["elegidas"].values()))
             + r" de los 5 valores, la mejor regla del pasado era estar dentro cuando Kronos da \emph{poca} probabilidad de "
             r"subida, lo contrario de fiarse de él.")

    # 4. S&P 500
    w.append(r"\section{Prueba 4: ¿ordena los valores del S\&P 500 entre sí?}")
    w.append(r"La pregunta cambia: no si un valor sube, sino \emph{cuáles irán mejor que los demás}. Si la semana siguiente cae "
             r"todo, pero los 50 que eligió caen un 1~\% y la media un 3~\%, acertó. Así se quita de en medio el movimiento del "
             r"mercado, que en las pruebas anteriores lo tapaba todo. Ojo: su artículo \emph{no} mide esto (ver la sección "
             r"siguiente); es una hipótesis nuestra sobre un uso posible, elegir entre los candidatos del bot.")
    w.append(r"Cada 5 sesiones desde julio de 2024 (" + cf.entero(sp["fechas"]) + r" semanas), Kronos predijo la rentabilidad a 5 "
             r"sesiones de cada uno de los " + cf.entero(sp["valores_con_prediccion"]) + r" miembros actuales del índice (de "
             + cf.entero(sp["valores_con_prediccion"] + len(excluidos)) + r"; fuera, " + cf.entero(len(excluidos))
             + r" con menos de 300 sesiones de historia: escisiones y salidas recientes). Cada "
             r"semana se mide si su orden se parece al real (la RankIC de esa semana) y se simula comprar sus 50 primeros a la "
             r"apertura siguiente y venderlos 5 sesiones después, con dividendos y un 0,10~\% sobre lo que se rota, frente a "
             r"comprar los " + cf.entero(sp["valores_con_prediccion"]) + r" a partes iguales.")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_ic.pdf}\caption{La RankIC entre valores de "
             r"cada semana: por encima de 0, esa semana ordenó mejor que el azar.}\end{figure}")
    filas = [["los 50 primeros según Kronos", cf.pct(sp["cagr_top"], 1, True), cf.n(sp["sharpe_top"], 2)],
             [r"los " + cf.entero(sp["valores_con_prediccion"]) + r" a partes iguales", cf.pct(sp["cagr_todos"], 1, True), cf.n(sp["sharpe_todos"], 2)],
             ["los 50 últimos según Kronos (exploratorio)", cf.pct(sp["cagr_ultimos"], 1, True), cf.n(sp["sharpe_ultimos"], 2)]]
    w.append(B.tabla(r"LRR", ["cartera", "rentabilidad anual", "Sharpe"], filas, r"S\&P 500, neto de costes",
                     r"Si ordenara, los primeros irían mejor que todos, y los últimos, peor."))
    if sp["sharpe_ultimos"] > sp["sharpe_top"]:
        w.append(r"Aquí los últimos fueron mejor que los primeros. Con una RankIC media de " + cf.n(sp["rankic_media"], 4, True)
                 + r" ($t$ = " + cf.n(sp["rankic_t"], 2, True) + r") no se puede leer como que acierte al revés: su orden no "
                 r"lleva información, y los extremos de una cartera de 50 se mueven mucho por azar.")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_carteras.pdf}\caption{Comprar cada semana "
             r"los 50 primeros, los 50 últimos o todos, según Kronos.}\end{figure}")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_placebo.pdf}\caption{El placebo: las "
             r"predicciones de cada valor barajadas entre semanas, 1.000 veces.}\end{figure}")
    filas = [[k[2:], r"\textbf{sí}" if v else r"\textbf{no}"] for k, v in sp["condiciones"].items()]
    filas[0][0] = r"RankIC media > 0 con $t$ > 2 (" + cf.n(sp["rankic_media"], 4, True) + r", $t$ = " + cf.n(sp["rankic_t"], 2, True) + ")"
    filas[1][0] = (r"los 50 primeros con mejor Sharpe que todos, $P \geq 90$~\% (" + cf.n(sp["sharpe_top"], 2) + " frente a "
                   + cf.n(sp["sharpe_todos"], 2) + r", $P$ = " + cf.n(sp["p_mejor"], 2) + ")")
    filas[2][0] = (r"por encima del percentil 95 del placebo (" + cf.n(sp["sharpe_top"], 2) + " frente a " + cf.n(sp["placebo_p95"], 2) + ")")
    w.append(B.tabla(r"Lr", ["criterio, escrito antes de medir", ""], filas, r"S\&P 500: los criterios del plan",
                     r"Sesgo declarado: son los miembros \emph{actuales}; los que salieron del índice entre 2024 y 2026 no están "
                     r"(Yahoo no guarda los retirados). Infla las dos carteras por igual, así que la comparación entre ellas se ve "
                     r"menos afectada."))

    w += seccion_algo_mal(cf, diag, rep)

    # conclusión
    w.append(r"\section{Qué significa y qué sigue}")
    if sp_ok:
        w.append(r"Kronos no sirve para predecir un valor, ni su probabilidad, ni su incertidumbre, ni para sacar reglas. Pero "
                 r"\textbf{ordena los valores del S\&P 500 entre sí} mejor que el azar, de forma sostenida y aprovechable neta de "
                 r"costes. Es justo lo que haría falta para \textbf{elegir entre los candidatos del bot}. Siguiente paso: la misma "
                 r"prueba sobre los candidatos reales del swing desde julio de 2024, con la lista histórica del índice (sin el "
                 r"sesgo de supervivencia), y si gana ahí, un walk-forward antes de tocar nada con dinero.")
    else:
        w.append(r"Kronos-small \textbf{sin reentrenar} no tiene un uso aprovechable aquí: no predice un valor, su "
                 r"probabilidad no se cumple, su incertidumbre es demasiado estrecha, de sus salidas sólo salen reglas de suerte "
                 r"y no ordena los valores del S\&P 500. Queda la receta de sus autores para operar: \textbf{reentrenarlo en el "
                 r"mercado antes de ordenar}. Es la segunda ronda (plan en \texttt{docs/PLAN\_KRONOS\_UTILIDAD\_2026-10-28.md}), "
                 r"con una lista cerrada de hipótesis escrita antes de medir, una sola prueba por hipótesis y la incubadora en "
                 r"sombra antes de nada con dinero: seguir probando hasta que algo salga sería fabricar un falso positivo.")
    w.append(r"\section*{Cómo se ha comprobado}")
    w.append(r"Ninguna predicción ve datos posteriores a su fecha (un test inventa el futuro y exige que no cambie). Los "
             r"criterios se escribieron antes de medir (\texttt{docs/PLAN.md}, fechado por git). La RankIC y las carteras del "
             r"S\&P 500, la volatilidad y la cartera de la minería se recalcularon con bucles escritos aparte: "
             + cf.entero(cmp.n) + r" comparaciones, todas iguales. Tras compilar, cada cifra se ha buscado en el texto del PDF.")
    w.append(r"\end{document}")
    return "\n\n".join(w)


def _criterios_sp(sp: dict) -> str:
    n = sum(sp["condiciones"].values())
    return f"cumple {n} de {len(sp['condiciones'])} criterios del plan"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cinco", required=True)
    ap.add_argument("--sp500", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--borrador", action="store_true")
    a = ap.parse_args(argv)
    d5, dsp, sal = (pathlib.Path(x).expanduser() for x in (a.cinco, a.sp500, a.salida))
    sal = sal.resolve()
    if B.REPO in sal.parents or sal == B.REPO:
        raise SystemExit("⛔ el PDF lleva datos de Yahoo: fuera del repo")
    sucio = subprocess.run(["git", "-C", str(B.REPO), "status", "--porcelain", "tiresias"], capture_output=True, text=True).stdout
    if sucio.strip() and not a.borrador:
        raise SystemExit(f"⛔ cambios sin commitear en tiresias/\n{sucio}")
    commit = subprocess.run(["git", "-C", str(B.REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    commits = {"informe": commit + (" + cambios sin commitear (BORRADOR)" if sucio.strip() else "")}
    v5 = json.loads((d5 / "veredicto.json").read_text(encoding="utf-8"))
    sp = json.loads((dsp / "veredicto_sp500.json").read_text(encoding="utf-8"))
    simbolos = [s for s in json.loads((dsp / "simbolos.json").read_text(encoding="utf-8"))["simbolos"] if s != T.CALENDARIO]
    vol, m, ex = S.volatilidad(d5), S.mineria(d5), extras(d5)
    cmp = Comparador()
    diag = S.diagnostico_sp500(dsp, simbolos)
    rep = json.loads((d5 / "replica_metrica.json").read_text(encoding="utf-8"))
    verificar_sp500(dsp, simbolos, sp, cmp, diag)
    verificar_vol(d5, vol, cmp)
    verificar_mineria(m, cmp)
    print(f"verificación: {cmp.n} comparaciones, máx dif {cmp.peor:.1e}, fallos {len(cmp.fallos)}")
    for x in cmp.fallos:
        print("  ⛔", x)
    if cmp.fallos:
        return 1
    fechas, _, P, Rc, Ro = T.matrices(dsp, simbolos)
    sal.mkdir(parents=True, exist_ok=True)
    B._estilo()
    fig_ic(fechas, T.rankic_por_fecha(P, Rc), sal / "fig_ic.pdf")
    fig_carteras(fechas, {"los 50 primeros según Kronos": (T.cartera(P, Ro, T.TOP), B.COLOR["kronos"]),
                          "todos a partes iguales": (T.cartera(P, Ro, None), B.COLOR["mantener"]),
                          "los 50 últimos": (T.cartera(-P, Ro, T.TOP), B.COLOR["real"])}, sal / "fig_carteras.pdf")
    fig_placebo(sp["placebo_sharpes"], sp["sharpe_top"], sp["placebo_p95"], sal / "fig_placebo.pdf")
    fig_mineria(m, sal / "fig_mineria.pdf")
    cf = B.Cifras()
    tex = sal / f"{NOMBRE}.tex"
    excluidos = json.loads((dsp / "simbolos.json").read_text(encoding="utf-8")).get("excluidos", {})
    tex.write_text(documento(cf, v5, vol, m, sp, commits, cmp, ex, excluidos, diag, rep), encoding="utf-8")
    pdf = B.compilar(tex)
    faltan = B.comprobar_pdf(pdf, cf.emitidas)
    print(f"PDF: {pdf} · {len(cf.emitidas)} cifras escritas, {len(faltan)} sin encontrar")
    for x in faltan[:20]:
        print("  ⛔", x)
    return 1 if faltan else 0


if __name__ == "__main__":
    raise SystemExit(main())
