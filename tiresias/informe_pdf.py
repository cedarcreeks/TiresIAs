# -*- coding: utf-8 -*-
"""Informe en PDF de cómo predice Kronos cada valor, con un ejemplo y gráficas.

    python -m tiresias.informe_pdf --dir ~/tiresias_resultados/cinco --salida <carpeta fuera del repo>

Lee lo que dejaron `correr` (predicciones y velas), `informe` (veredicto.json) y `ejemplo` (ejemplo_H5.json).
Cada cifra se recalcula con una segunda implementación (bucles, sin las funciones de `metricas`) y, tras compilar,
se busca en el texto del PDF. El PDF lleva precios de Yahoo: se escribe fuera de este repo.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import re
import subprocess

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
import matplotlib.dates as mdates        # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from tiresias import informe as I        # noqa: E402
from tiresias import metricas as X       # noqa: E402

PDFLATEX = "/Library/TeX/texbin/pdflatex"
PDFTOTEXT = "/opt/homebrew/bin/pdftotext"
NOMBRE = "INFORME_KRONOS"
NOMBRES = {"SPY": "SPY", "3USL.MI": "3USL", "IDR.MC": "Indra", "ACS.MC": "ACS", "BTC-EUR": "bitcoin"}
COLOR = {"kronos": "#c0392b", "real": "#1f3a5f", "mantener": "#7f8c8d", "media": "#2e8b57"}
VISTAS = 20                              # velas de historia que enseña el ejemplo (de las 40 que vio)
REPO = pathlib.Path(__file__).resolve().parent.parent


# ── cifras ───────────────────────────────────────────────────────────────
class Cifras:
    """Toda cifra del texto pasa por aquí: coma decimal, signo tipográfico, y queda apuntada para buscarla en el PDF."""

    def __init__(self):
        self.emitidas: list = []

    def n(self, x, dec: int = 1, signo: bool = False) -> str:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return "---"
        v = round(float(x), dec)
        cuerpo = f"{abs(v):.{dec}f}".replace(".", ",")
        neg = v < 0                                     # round(-0.0004, 3) es -0.0, que no es < 0: sin «−0,000»
        self.emitidas.append(("−" if neg else ("+" if signo else "")) + cuerpo)
        return (r"\textminus{}" if neg else ("+" if signo else "")) + cuerpo

    def pct(self, x, dec: int = 0, signo: bool = False) -> str:
        return self.n(None if x is None else x * 100, dec, signo) + r"\,\%"

    def entero(self, x) -> str:
        return self.n(x, 0)


def coma(x: float, dec: int = 1) -> str:
    """Para el texto de las figuras (no se verifica en el PDF)."""
    return f"{x:.{dec}f}".replace(".", ",").replace("-", "−")


def tabla(columnas: str, cabecera: list, filas: list, titulo: str, nota: str = "") -> str:
    lin = [r"\begin{table}[htbp]", r"\centering", r"\footnotesize", r"\setlength{\tabcolsep}{4pt}",
           r"\rowcolors{2}{gray!9}{white}", r"\caption{" + titulo + "}",
           r"\begin{tabularx}{\textwidth}{" + columnas + "}", r"\toprule", " & ".join(cabecera) + r" \\", r"\midrule"]
    lin += [" & ".join(f) + r" \\" for f in filas]
    lin += [r"\bottomrule", r"\end{tabularx}"]
    if nota:
        lin.append(r"\par\smallskip\begin{minipage}{\textwidth}\scriptsize " + nota + r"\end{minipage}")
    lin.append(r"\end{table}")
    return "\n".join(lin)


# ── datos ────────────────────────────────────────────────────────────────
def leer_pred(d: pathlib.Path, s: str, H: int) -> pd.DataFrame:
    return pd.read_csv(d / f"pred_{s}_H{H}.csv", float_precision="round_trip").sort_values("fecha").reset_index(drop=True)


def leer_velas(d: pathlib.Path, s: str) -> pd.DataFrame:
    return pd.read_csv(d / f"velas_{s}.csv", index_col=0, parse_dates=True, float_precision="round_trip")


def diagnostico(d: pathlib.Path, s: str, reps: int = 2000) -> dict:
    out = {}
    for H in (1, 5, 12):
        q = X.sin_solape(leer_pred(d, s, H), H)
        m = X.ic_remuestreado({s: q}, reps, 0)[:, 0]
        a = X.acierto(q)
        out[H] = {"n": len(q), "rankic": X.spearman(q["r_prevista"], q["r_real"]),
                  "ic90": (float(np.nanpercentile(m, 5)), float(np.nanpercentile(m, 95))),
                  "base": a["base"], "sube_si_dice_sube": a["sube_si_dice_sube"], "sube_si_dice_baja": a["sube_si_dice_baja"],
                  "n_dice_sube": a["n_dice_sube"], "n_dice_baja": a["n_dice_baja"],
                  "cobertura": X.cobertura(q), "mae_rel": X.mae_relativo(q)}
    return out


def curvas(d: pathlib.Path, s: str, H: int) -> dict:
    """Las de `informe.horizonte`, por valor: Kronos, comprar y mantener y la media de 200, netas de costes."""
    v, p = leer_velas(d, s), leer_pred(d, s, H)
    dk = X.decisiones_kronos(p, I.PASO[H])
    sim = X.Simulador(v, dk.index, I.PASO[H], I.COSTES.get(s, I.COSTE_ACCIONES))
    return {"kronos": sim.curva(dk.to_numpy()), "comprar y mantener": sim.curva(np.ones(len(dk))),
            "media de 200": sim.curva(X.decisiones_media(v, dk.index).to_numpy())}


# ── segunda implementación, independiente ────────────────────────────────
def _rangos_medios(x: list) -> list:
    orden = sorted(range(len(x)), key=lambda i: x[i])
    r = [0.0] * len(x)
    i = 0
    while i < len(orden):
        j = i
        while j + 1 < len(orden) and x[orden[j + 1]] == x[orden[i]]:
            j += 1
        for k in range(i, j + 1):
            r[orden[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def _pearson(a: list, b: list) -> float:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return num / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def verificar(d: pathlib.Path, simbolos: list, diag: dict, verd: dict) -> tuple:
    """(comparaciones, mayor diferencia, fallos). Sin pandas en el cálculo ni funciones de `metricas`."""
    n, peor, fallos = 0, 0.0, []

    def cmp(donde, a, b):
        nonlocal n, peor
        n += 1
        dif = abs(a - b)
        peor = max(peor, dif)
        if not dif <= 1e-12:
            fallos.append(f"{donde}: {a!r} frente a {b!r}")

    for s in simbolos:
        for H in (1, 5, 12):
            filas = leer_pred(d, s, H).to_dict("records")[::H]
            prev, real = [f["r_prevista"] for f in filas], [f["r_real"] for f in filas]
            cmp(f"{s} H{H} RankIC", _pearson(_rangos_medios(prev), _rangos_medios(real)), diag[s][H]["rankic"])
            sube = [f["r_real"] > 0 for f in filas]
            dice = [f["p_subida"] > 0.5 for f in filas]
            cmp(f"{s} H{H} base", sum(sube) / len(sube), diag[s][H]["base"])
            cmp(f"{s} H{H} sube si dice sube", sum(u for u, k in zip(sube, dice) if k) / sum(dice), diag[s][H]["sube_si_dice_sube"])
            cmp(f"{s} H{H} sube si dice baja", sum(u for u, k in zip(sube, dice) if not k) / (len(dice) - sum(dice)),
                diag[s][H]["sube_si_dice_baja"])
            cmp(f"{s} H{H} cobertura", sum(f["r_p10"] <= f["r_real"] <= f["r_p90"] for f in filas) / len(filas),
                diag[s][H]["cobertura"])
            cmp(f"{s} H{H} error relativo", sum(abs(f["r_prevista"] - f["r_real"]) for f in filas)
                / sum(abs(f["r_real"]) for f in filas), diag[s][H]["mae_rel"])
        for H in (1, 5):
            v = leer_velas(d, s)
            fechas = [str(x.date()) for x in v.index]
            ap = [o * a / c for o, a, c in zip(v["open"], v["adjclose"], v["close"])]
            dec = leer_pred(d, s, H).to_dict("records")[::I.PASO[H]]
            coste = I.COSTES.get(s, I.COSTE_ACCIONES)
            pos = {}
            for f in dec:
                i = fechas.index(f["fecha"])
                for j in range(i + 1, min(i + 1 + I.PASO[H], len(fechas))):
                    pos[j] = 1.0 if f["p_subida"] > 0.5 else 0.0
            cubre = set(pos)
            ini = fechas.index(dec[0]["fecha"]) + 1
            años = (v.index[-1] - v.index[ini]).days / 365.25
            for nombre, regla in (("kronos", lambda j: pos.get(j, 0.0)), ("mantener", lambda j: 1.0 if j in cubre else 0.0)):
                eq, ant = 1.0, 0.0
                for j in range(ini, len(fechas) - 1):
                    x = regla(j)
                    eq *= 1 + x * (ap[j + 1] / ap[j] - 1) - coste * abs(x - ant)
                    ant = x
                clave = "cagr_kronos" if nombre == "kronos" else "cagr_mantener"
                cmp(f"{s} H{H} CAGR {nombre}", eq ** (1 / años) - 1, verd[f"H{H}"]["por_valor"][s][clave])
    return n, peor, fallos


# ── figuras ──────────────────────────────────────────────────────────────
def _estilo():
    plt.rcParams.update({"font.size": 8, "axes.titlesize": 9, "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.25, "legend.fontsize": 7, "legend.frameon": False})


PCT = FuncFormatter(lambda x, _: coma(x * 100, 0) + " %")


def fig_ejemplo(d: pathlib.Path, simbolos: list, ej: dict, salida: pathlib.Path):
    fig, ejes = plt.subplots(1, len(simbolos), figsize=(7.1, 3.1))
    for ax, s in zip(ejes, simbolos):
        e, v = ej["valores"][s], leer_velas(d, s)
        i = int(v.index.get_loc(pd.Timestamp(e["fecha"])))  # type: ignore[arg-type]
        hist = v["close"].iloc[i - VISTAS + 1:i + 1].to_numpy()
        xh, xf = np.arange(-VISTAS + 1, 1), np.arange(0, ej["H"] + 1)
        ax.axvspan(0, ej["H"], color="0.93", lw=0)
        ax.plot(xh, hist, color=COLOR["real"], lw=1.2)
        for k, t in enumerate(e["trayectorias"]):
            ax.plot(xf, [e["cierre"]] + t, color=COLOR["kronos"], lw=0.8, alpha=0.6, label="los 10 futuros de Kronos" if k == 0 else None)
        ax.plot(xf, [e["cierre"]] + e["reales"], color=COLOR["real"], lw=2.2, label="lo que pasó")
        r_real = e["reales"][-1] / e["cierre"] - 1
        ax.set_title(f"{NOMBRES[s]}\nprevisto {coma(e['r_prevista'] * 100)} % · real {coma(r_real * 100)} %"
                     f"\np. de subida {coma(e['p_subida'], 1)}", fontsize=7.5)
        ax.set_xticks([-VISTAS + 1, 0, ej["H"]], [str(v.index[i - VISTAS + 1].date())[5:], str(v.index[i].date())[5:],
                                                  "+" + str(ej["H"])])
    h, lab = ejes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=2)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(salida)
    plt.close(fig)


def fig_dispersion(d: pathlib.Path, simbolos: list, diag: dict, salida: pathlib.Path):
    fig, ejes = plt.subplots(1, len(simbolos), figsize=(7.1, 2.5))
    for ax, s in zip(ejes, simbolos):
        q = X.sin_solape(leer_pred(d, s, 5), 5)
        ax.scatter(q["r_prevista"], q["r_real"], s=7, color=COLOR["kronos"], alpha=0.6, lw=0)
        ax.axhline(0, color="k", lw=0.5)
        ax.axvline(0, color="k", lw=0.5)
        ax.xaxis.set_major_formatter(PCT)
        ax.yaxis.set_major_formatter(PCT)
        ax.set_title(f"{NOMBRES[s]} · RankIC {coma(diag[s][5]['rankic'], 3)}")
        ax.set_xlabel("previsto a 5 sesiones")
    ejes[0].set_ylabel("real a 5 sesiones")
    fig.tight_layout()
    fig.savefig(salida)
    plt.close(fig)


def fig_calibracion(d: pathlib.Path, simbolos: list, salida: pathlib.Path):
    fig, ejes = plt.subplots(1, len(simbolos), figsize=(7.1, 2.5), sharey=True)
    for ax, s in zip(ejes, simbolos):
        p = leer_pred(d, s, 1)
        c = X.calibracion(p)
        ax.plot([0, 1], [0, 1], color="k", lw=0.6, ls="--", label="calibración perfecta")
        ax.axhline((p["r_real"] > 0).mean(), color=COLOR["mantener"], lw=0.8, label="sube sin más")
        ax.errorbar(c.index, c["frecuencia"], yerr=[c["frecuencia"] - c["lo"], c["hi"] - c["frecuencia"]], fmt="o",
                    color=COLOR["kronos"], ms=3, lw=0.8, capsize=2, label="Kronos (IC 90 %)")
        for x, y, nn in zip(c.index, c["hi"], c["n"]):
            ax.text(x, min(y + 0.03, 1.02), str(nn), fontsize=5.5, ha="center", color="0.35")
        ax.set_xlim(-0.05, 1.05)
        ax.set_ylim(0, 1.08)
        ax.set_xticks([0, 0.25, 0.5, 0.75, 1], ["0", "0,25", "0,5", "0,75", "1"])
        ax.yaxis.set_major_formatter(PCT)
        ax.set_title(NOMBRES[s])
    ejes[1].set_xlabel("probabilidad de subida que dio Kronos (a 1 sesión)")
    ejes[0].set_ylabel("veces que subió de verdad")
    h, lab = ejes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=3)
    fig.tight_layout(rect=(0, 0.1, 1, 1))
    fig.savefig(salida)
    plt.close(fig)


def fig_patrimonio(curv: dict, simbolos: list, salida: pathlib.Path):
    fig, ejes = plt.subplots(1, len(simbolos), figsize=(7.1, 2.5))
    for ax, s in zip(ejes, simbolos):
        for k, col in (("comprar y mantener", COLOR["mantener"]), ("media de 200", COLOR["media"]), ("kronos", COLOR["kronos"])):
            ax.plot(curv[s][k].index, curv[s][k].to_numpy(), color=col, lw=1.1, label="Kronos" if k == "kronos" else k)
        ax.set_title(NOMBRES[s])
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}".replace(".", ",")))
    ejes[0].set_ylabel("valor de 1 invertido (neto)")
    h, lab = ejes[0].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=3)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(salida)
    plt.close(fig)


# ── el texto ─────────────────────────────────────────────────────────────
def _exp(x: float) -> str:
    if x == 0:
        return "0"
    m, e = f"{x:.0e}".split("e")
    return m + r"$\times10^{" + str(int(e)) + "}$"


CRITERIOS = {"1": "la RankIC media por encima de 0", "2": "mejor Sharpe que mantener y que la mejor regla ingenua",
             "3": "por encima del placebo", "4": "al menos 3 de 5 valores con RankIC positiva"}


def _criterios(cond: dict, cuando: str) -> str:
    si = [k.split(" ", 1)[0] for k, v in cond.items() if v]
    if not si:
        return cuando + " no se cumple ninguno"
    return cuando + " sólo se cumple " + " y ".join(f"el {k}.º ({CRITERIOS[k]})" for k in si)


def es_negativo(diag: dict, verd: dict, simbolos: list) -> bool:
    """El titular «no predice de forma aprovechable» sólo vale si, a 5 sesiones, ningún valor tiene la RankIC
    distinguible de 0 y ninguno rinde más operado que mantenido. Si no, el texto entero está por reescribir."""
    return all(diag[s][5]["ic90"][0] <= 0 for s in simbolos) and all(
        verd["H5"]["por_valor"][s]["cagr_kronos"] < verd["H5"]["por_valor"][s]["cagr_mantener"] for s in simbolos)


def apertura_igual(v: pd.DataFrame, desde: str) -> float:
    v = v.loc[desde:]
    return float(np.mean(v["open"].to_numpy()[1:] == v["close"].to_numpy()[:-1]))


def documento(cf: Cifras, simbolos: list, diag: dict, verd: dict, ej: dict, pro: dict, curv: dict,
              commit: str, verif: tuple, ap_igual: dict) -> str:
    años = (pd.Timestamp(pro["fin"]) - pd.Timestamp(pro["desde"])).days / 365.25
    nm = {s: NOMBRES[s] for s in simbolos}
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
\renewcommand{\arraystretch}{1.25}""")
    w.append(r"\title{Kronos sobre " + ", ".join(nm[s] for s in simbolos[:-1]) + " y " + nm[simbolos[-1]]
             + r": qué predice y qué no}")
    w.append(r"\author{TiresIAs}" + "\n" + r"\date{" + pro["fin_ejecucion"][:10] + "}")
    w.append(r"\begin{document}" + "\n" + r"\maketitle")
    n, peor, _ = verif
    w.append(r"\begin{center}\small Datos de Yahoo descargados el " + pro["dia_descarga"] + r", hasta la sesión del \textbf{"
             + pro["fin"] + r"} incluida. Predicciones con el commit \texttt{" + pro["commit"] + r"} de TiresIAs, en CPU; "
             r"este informe, con el \texttt{" + commit + r"}. " + cf.entero(n) + r" cifras recalculadas con una segunda "
             r"implementación independiente (diferencia máxima " + _exp(peor) + r").\end{center}")

    # en una frase
    w.append(r"\section{En una frase}")
    if not es_negativo(diag, verd, simbolos):
        raise SystemExit("⛔ este texto está escrito para un resultado negativo y los datos no lo son: hay que reescribirlo")
    w.append(r"\textbf{Kronos no predice de forma aprovechable estos valores.} En ninguno su acierto a 5 sesiones se "
             r"distingue del azar (el intervalo del 90~\% de su RankIC incluye el 0), y operándolo, neto de costes, rinde menos "
             r"que comprarlo y mantenerlo:")
    w.append(r"\begin{itemize}[itemsep=0.2em]")
    for s in simbolos:
        g, pv = diag[s][5], verd["H5"]["por_valor"][s]
        w.append(r"\item \textbf{" + nm[s] + r"}: RankIC a 5 sesiones " + cf.n(g["rankic"], 3, True) + " (" + cf.n(g["ic90"][0], 3, True)
                 + " a " + cf.n(g["ic90"][1], 3, True) + r"). Cuando dice «sube», sube el " + cf.pct(g["sube_si_dice_sube"])
                 + r"; cuando dice «baja», el " + cf.pct(g["sube_si_dice_baja"]) + ". Operándolo cada semana: "
                 + cf.pct(pv["cagr_kronos"], 1, True) + r" al año, frente a " + cf.pct(pv["cagr_mantener"], 1, True)
                 + r" de mantenerlo.")
    w.append(r"\end{itemize}")
    v5, v1 = verd["H5"], verd["H1"]
    otros = [NOMBRES[s] for s in v5["por_valor"] if s not in simbolos]
    w.append(r"Con todos los valores de la prueba (también " + " y ".join(otros) + r"), de los cuatro criterios fijados antes "
             r"de medir (\texttt{docs/PLAN.md}) " + _criterios(v5["condiciones"], "a 5 sesiones") + "; "
             + _criterios(v1["condiciones"], "a 1 sesión") + r". A 1 sesión, la RankIC media es "
             + cf.n(v1["rankic"]["media"], 3, True) + " (" + cf.n(v1["rankic"]["ic90"][0], 3, True) + " a "
             + cf.n(v1["rankic"]["ic90"][1], 3, True) + r"). La cartera de todos operada con Kronos cada semana tiene un "
             r"Sharpe de " + cf.n(v5["sharpe_cartera"]["kronos"], 2) + r", frente a " + cf.n(v5["sharpe_cartera"]["comprar y mantener"], 2)
             + r" de mantenerlos, y no supera al placebo (sus mismas señales barajadas: percentil 95 en "
             + cf.n(v5["placebo_p95"], 2) + ").")

    # qué es
    w.append(r"\section{Qué es Kronos y cómo se ha probado}")
    w.append(r"\textbf{Kronos} es un modelo de lenguaje para velas de bolsa. Igual que un modelo de texto convierte las "
             r"palabras en \emph{tokens} y aprende a continuar una frase, Kronos convierte cada vela (apertura, máximo, mínimo, "
             r"cierre y volumen) en \emph{tokens} y aprende a continuar la serie. Se preentrenó con datos de más de 45 bolsas "
             r"\emph{hasta junio de 2024}; por eso aquí sólo se le pregunta por lo que pasó después, del 1 de julio de 2024 al "
             + pro["fin"] + r". Es un modelo generativo: no da un número, \emph{dibuja futuros posibles}.")
    w.append(r"Cada día de ese periodo, con las 40 velas anteriores (el protocolo de su artículo), se le pidieron "
             + cf.entero(pro["N"]) + r" futuros a 1, 5 y 12 sesiones (Kronos-small, temperatura 0,6). De esos futuros salen "
             r"tres cosas: la \textbf{rentabilidad prevista} (su media), la \textbf{probabilidad de subida} (la fracción que acaba "
             r"por encima del cierre de hoy) y una \textbf{banda} del percentil 10 al 90. Al lado se apunta lo que pasó de verdad.")
    w.append(r"Las medidas, en palabras llanas:")
    w.append(r"""\begin{description}
\item[RankIC.] La correlación de rangos de Spearman entre lo previsto y lo real: si ordena bien los días buenos y los malos.
0 es no saber nada; 1, ordenarlos perfecto. Su intervalo del 90~\% (\emph{bootstrap} por bloques de 4 semanas) dice si
se distingue de 0. A 5 y 12 sesiones se usan fechas sin solape, para no contar dos veces la misma semana.
\item[Cuando dice «sube».] Cuántas veces subió de verdad cuando su probabilidad de subida pasaba de 0,5, frente a cuando no.
Si no sabe nada, las dos salen como la frecuencia con que el valor sube sin más.
\item[Cobertura.] Cuántas veces lo real cae dentro de su banda del 10 al 90~\%. Si su incertidumbre fuera honesta, el 80~\%.
\item[Error frente a «no cambia».] Su error medio dividido entre el de prever siempre 0. Menos de 1, mejor que no prever.
\end{description}""")

    # ejemplo
    w.append(r"\section{Un ejemplo}")
    f0 = ej["valores"][simbolos[0]]["fecha"]
    w.append(r"El último caso completo a " + cf.entero(ej["H"]) + r" sesiones: la predicción hecha tras el cierre del "
             + f0 + r", elegida por esa regla y no por cómo salió. Se ha rehecho con su mismo lote y su misma semilla, y la "
             r"media de sus futuros coincide \emph{exactamente} con la que se evaluó. Se ven las últimas " + cf.entero(VISTAS)
             + r" de las 40 velas que vio; en la zona gris, en rojo, los " + cf.entero(pro["N"])
             + r" futuros que dibujó y, en azul grueso, lo que pasó.")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_ejemplo.pdf}"
             r"\caption{Predicción a " + cf.entero(ej["H"]) + r" sesiones tras el cierre del " + f0 + r".}\end{figure}")
    lin = []
    for s in simbolos:
        e = ej["valores"][s]
        rr = e["reales"][-1] / e["cierre"] - 1
        acerto = (e["p_subida"] > 0.5) == (rr > 0)
        lin.append(nm[s] + r": previó " + cf.pct(e["r_prevista"], 2, True) + r" con probabilidad de subida "
                   + cf.n(e["p_subida"], 1) + r", y fue " + cf.pct(rr, 2, True) + (r" (acertó la dirección)" if acerto else
                                                                                      r" (falló la dirección)"))
    w.append("; ".join(lin) + r". Un caso no dice nada por sí solo: lo que sigue mide los " + cf.entero(diag[simbolos[0]][1]["n"])
             + r" días de " + nm[simbolos[0]] + r" y los de los demás.")
    fuera = [nm[s] for s in simbolos if not min(t[-1] for t in ej["valores"][s]["trayectorias"])
             <= ej["valores"][s]["reales"][-1] <= max(t[-1] for t in ej["valores"][s]["trayectorias"])]
    w.append((r"En este caso, el cierre real de " + " y ".join(fuera) + r" quedó fuera de todos sus futuros. "
              if fuera else r"En este caso, el cierre real quedó dentro del abanico en los tres. ")
             + r"Cuántas veces pasa eso es lo que mide la cobertura, más abajo.")

    # acierto
    w.append(r"\section{¿Acierta?}")
    filas = []
    for s in simbolos:
        for H in (1, 5, 12):
            g = diag[s][H]
            filas.append([nm[s] if H == 1 else "", cf.entero(H), cf.entero(g["n"]), cf.n(g["rankic"], 3, True),
                          cf.n(g["ic90"][0], 3, True) + " a " + cf.n(g["ic90"][1], 3, True), cf.pct(g["base"]),
                          cf.pct(g["sube_si_dice_sube"]), cf.pct(g["sube_si_dice_baja"]), cf.pct(g["cobertura"]),
                          cf.n(g["mae_rel"], 2)])
    w.append(tabla(r"p{1.1cm}rrrp{2.4cm}RRRRR",
                   ["valor", "sesiones", "casos", "RankIC", "IC 90 \\%", "sube sin más", "sube si dice «sube»",
                    "sube si dice «baja»", "cobertura (80 \\%)", "error / «no cambia»"], filas,
                   "Acierto de Kronos por valor y horizonte",
                   r"Casos: fechas sin solape (a 5 sesiones, una de cada 5). Ninguna cifra de esta tabla entra en la elección "
                   r"de nada: todo estaba fijado antes de medir."))
    sig = [(s, H) for s in simbolos for H in (1, 5, 12) if diag[s][H]["ic90"][0] > 0]
    w.append(r"\textbf{¿Ordena?} " + ("En ningún valor ni horizonte el intervalo de la RankIC queda por encima de 0." if not sig else
             "El intervalo de la RankIC queda por encima de 0 sólo en " + ", ".join(f"{nm[s]} a {H}" for s, H in sig)
             + r" sesiones, entre " + cf.entero(3 * len(simbolos)) + r" combinaciones miradas: con tantas, alguna sale por azar.")
             + r" Las RankIC están entre " + cf.n(min(diag[s][H]["rankic"] for s in simbolos for H in (1, 5, 12)), 3, True)
             + " y " + cf.n(max(diag[s][H]["rankic"] for s in simbolos for H in (1, 5, 12)), 3, True) + ".")
    cob = [diag[s][H]["cobertura"] for s in simbolos for H in (1, 5, 12)]
    if max(cob) < 0.8:
        w.append(r"\textbf{¿Sabe cuánto no sabe?} No. Su banda del 10 al 90~\% contiene lo real entre el " + cf.pct(min(cob))
                 + r" y el " + cf.pct(max(cob)) + r" de las veces, cuando debería ser el 80~\%: \emph{se cree más seguro de "
                 r"lo que es}. Es su punto flaco más claro, y el primero que se intentará pulir (fase 4 del plan: más futuros, "
                 r"otra temperatura, calibración).")
    else:
        w.append(r"\textbf{¿Sabe cuánto no sabe?} Su banda del 10 al 90~\% contiene lo real entre el " + cf.pct(min(cob))
                 + r" y el " + cf.pct(max(cob)) + r" de las veces, frente al 80~\% que debería.")
    mae = [diag[s][H]["mae_rel"] for s in simbolos for H in (1, 5, 12)]
    w.append(r"\textbf{¿Mejor que no prever?} Su error medio es entre " + cf.n(min(mae), 2) + " y " + cf.n(max(mae), 2)
             + r" veces el de decir siempre «no cambia»" + (r": nunca lo mejora." if min(mae) >= 1 else "."))
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_dispersion.pdf}"
             r"\caption{Lo previsto frente a lo real, a 5 sesiones. Si acertara, los puntos irían de abajo a la izquierda a "
             r"arriba a la derecha.}\end{figure}")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_calibracion.pdf}"
             r"\caption{¿Se cumple su probabilidad de subida? A 1 sesión, cada punto agrupa los días en que dio esa probabilidad "
             r"(encima, cuántos). Si fuera fiable, caerían sobre la diagonal; si no supiera nada, sobre la línea gris de "
             r"«sube sin más».}\end{figure}")

    # operándolo
    w.append(r"\section{¿Y operándolo?}")
    w.append(r"Como se haría a mano: tras el cierre, dentro si su probabilidad de subida pasa de 0,5; se compra o se vende a la "
             r"apertura siguiente y se mantiene 1 sesión (diario) o 5 (semanal). Con dividendos y con un coste de 0,25~\% por "
             r"operación. La comparación, con comprarlo y mantenerlo y con una regla clásica, estar dentro sólo si cierra por "
             r"encima de su media de 200 sesiones, en las mismas fechas.")
    filas = []
    for s in simbolos:
        for H, txt in ((1, "diario"), (5, "semanal")):
            pv = verd[f"H{H}"]["por_valor"][s]
            ce = pv["coste_equilibrio"]
            filas.append([nm[s] if H == 1 else "", txt, cf.pct(pv["cagr_kronos"], 1, True), cf.pct(pv["cagr_mantener"], 1, True),
                          cf.pct(X.cagr(curvas_h(curv, s, H)["media de 200"]), 1, True), cf.n(pv["sharpe_kronos"], 2),
                          cf.n(pv["sharpe_mantener"], 2), cf.entero(pv["operaciones_año"]),
                          "ni gratis" if ce is None else cf.pct(ce, 2)])
    w.append(tabla(r"p{1.1cm}lRRRRRRR",
                   ["valor", "", "Kronos", "mantener", "media 200", "Sharpe Kronos", "Sharpe mantener", "operaciones al año",
                    "coste de equilibrio"], filas, "Operándolo, neto de costes (rentabilidad anual compuesta y Sharpe)",
                   r"Coste de equilibrio: el coste por operación con el que Kronos igualaría a mantener; «ni gratis», que ni sin "
                   r"costes lo iguala. Sharpe sobre rentabilidades semanales, anualizado."))
    w.append(r"Operar a diario hace entre " + cf.entero(min(verd["H1"]["por_valor"][s]["operaciones_año"] for s in simbolos))
             + " y " + cf.entero(max(verd["H1"]["por_valor"][s]["operaciones_año"] for s in simbolos))
             + r" operaciones al año, y el coste se come lo poco que pudiera haber. A la semana son unas "
             + cf.entero(np.mean([verd["H5"]["por_valor"][s]["operaciones_año"] for s in simbolos]))
             + r", y aun así ninguno iguala a mantenerlo. Es lo esperable si no predice nada: está fuera entre el "
             + cf.pct(1 - max(verd["H5"]["por_valor"][s]["dentro"] for s in simbolos)) + " y el "
             + cf.pct(1 - min(verd["H5"]["por_valor"][s]["dentro"] for s in simbolos))
             + r" de las semanas, en un periodo en que mantenerlos rindió " + ", ".join(
                 cf.pct(verd["H5"]["por_valor"][s]["cagr_mantener"], 1, True) for s in simbolos) + r" al año.")
    w.append(r"\begin{figure}[htbp]\centering\includegraphics[width=\textwidth]{fig_patrimonio.pdf}"
             r"\caption{Operándolo cada semana, neto de costes, frente a mantener y a la media de 200.}\end{figure}")

    # qué significa
    w.append(r"\section{Qué significa y qué sigue}")
    w.append(r"\begin{itemize}[itemsep=0.2em]")
    w.append(r"\item \textbf{No usarlo para decidir} en estos valores tal cual viene. Es un resultado negativo, y útil: cierra la "
             r"pregunta para Kronos-small con su configuración publicada.")
    w.append(r"\item \textbf{Lo que se le reprocha con más claridad es la incertidumbre}: su banda es demasiado estrecha. Es lo "
             r"primero que intentará pulir TiresIAs: de julio de 2024 a junio de 2025 para desarrollar, y de julio de 2025 en "
             r"adelante, sin tocar, para una sola prueba final.")
    w.append(r"\item \textbf{Queda la prueba del S\&P 500}, la de su artículo: no predecir un valor, sino ordenar 500 entre sí. "
             r"Es otra pregunta y puede salir distinta.")
    w.append(r"\item \textbf{Un sesgo que juega a su favor}, y aun así no pasa: las aperturas de Yahoo idénticas al cierre "
             r"anterior (" + ", ".join(nm[s] + " " + cf.pct(ap_igual[s], 1) for s in simbolos) + r" de las sesiones). Si son "
             r"rellenos, la simulación le regala esos días el salto de la noche.")
    w.append(r"\item \textbf{Lo que no dice}: " + cf.n(años, 1) + r" años de muestra, en los que los tres subieron con "
             r"fuerza. Un modelo que acertara sólo en las caídas tendría pocas ocasiones de demostrarlo.")
    w.append(r"\end{itemize}")
    w.append(r"\section*{Cómo se ha comprobado}")
    w.append(r"Las predicciones no ven nada posterior a su fecha (un test inventa precios futuros y exige que no cambien). "
             r"La RankIC, el acierto, la cobertura, el error y las rentabilidades se recalcularon con bucles escritos aparte, sin "
             r"las funciones del análisis: " + cf.entero(n) + r" comparaciones, todas iguales. El ejemplo se rehízo con su lote y "
             r"su semilla y coincide al último bit. Tras compilar, cada cifra de este texto se ha buscado en el PDF.")
    w.append(r"\end{document}")
    return "\n\n".join(x for x in w if x is not None)


def curvas_h(curv: dict, s: str, H: int) -> dict:
    return curv[(s, H)]


# ── compilar y comprobar ─────────────────────────────────────────────────
def compilar(tex: pathlib.Path) -> pathlib.Path:
    pdf = tex.with_suffix(".pdf")
    pdf.unlink(missing_ok=True)
    for _ in range(2):
        subprocess.run([PDFLATEX, "-interaction=nonstopmode", "-halt-on-error", tex.name], cwd=tex.parent,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log = tex.with_suffix(".log").read_text(encoding="latin-1")
    errores = [x for x in log.splitlines() if x.startswith("! ")]
    errores += [m.group(0) for m in re.finditer(r"Overfull \\hbox \(([0-9.]+)pt too wide\)[^\n]*", log) if float(m.group(1)) > 0.5]
    if errores or not pdf.exists():
        raise SystemExit(f"⛔ LaTeX: {errores[:5]} · PDF existe: {pdf.exists()}")
    return pdf


def comprobar_pdf(pdf: pathlib.Path, emitidas: list) -> list:
    texto = subprocess.run([PDFTOTEXT, "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    texto = texto.replace(" ", " ").replace(" ", " ")
    faltan = []
    for cifra, veces in collections.Counter(emitidas).items():
        hay = len(re.findall(r"(?<![0-9,.+−])" + re.escape(cifra) + r"(?![0-9])", texto))
        if hay < veces:
            faltan.append(f"{cifra}: {hay} de {veces}")
    return faltan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--salida", required=True)
    ap.add_argument("--simbolos", nargs="+", default=["SPY", "3USL.MI", "IDR.MC"])
    ap.add_argument("--borrador", action="store_true", help="con código sin commitear; el PDF lo dice")
    a = ap.parse_args(argv)
    d, sal = pathlib.Path(a.dir).expanduser(), pathlib.Path(a.salida).expanduser().resolve()
    if REPO in sal.parents or sal == REPO:
        raise SystemExit("⛔ el PDF lleva precios de Yahoo: fuera del repo")
    sucio = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "tiresias"], capture_output=True, text=True).stdout
    if sucio.strip() and not a.borrador:
        raise SystemExit(f"⛔ cambios sin commitear en tiresias/: el informe no diría con qué código se hizo\n{sucio}")
    commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    if sucio.strip():
        commit += " + cambios sin commitear (BORRADOR)"
    pro = json.loads((d / "procedencia.json").read_text(encoding="utf-8"))
    verd = json.loads((d / "veredicto.json").read_text(encoding="utf-8"))
    ej = json.loads((d / "ejemplo_H5.json").read_text(encoding="utf-8"))
    diag = {s: diagnostico(d, s) for s in a.simbolos}
    curv = {(s, H): curvas(d, s, H) for s in a.simbolos for H in (1, 5)}
    for (s, H), c in curv.items():                       # las curvas de aquí son las del veredicto
        pv = verd[f"H{H}"]["por_valor"][s]
        if abs(X.cagr(c["kronos"]) - pv["cagr_kronos"]) > 1e-12 or abs(X.cagr(c["comprar y mantener"]) - pv["cagr_mantener"]) > 1e-12:
            raise SystemExit(f"⛔ {s} H{H}: las curvas no son las del veredicto")
    verif = verificar(d, a.simbolos, diag, verd)
    print(f"verificación: {verif[0]} comparaciones, máx dif {verif[1]:.1e}, fallos {len(verif[2])}")
    if verif[2]:
        for x in verif[2][:20]:
            print("  ⛔", x)
        return 1
    sal.mkdir(parents=True, exist_ok=True)
    _estilo()
    fig_ejemplo(d, a.simbolos, ej, sal / "fig_ejemplo.pdf")
    fig_dispersion(d, a.simbolos, diag, sal / "fig_dispersion.pdf")
    fig_calibracion(d, a.simbolos, sal / "fig_calibracion.pdf")
    fig_patrimonio({s: curv[(s, 5)] for s in a.simbolos}, a.simbolos, sal / "fig_patrimonio.pdf")
    cf = Cifras()
    tex = sal / f"{NOMBRE}.tex"
    ap_igual = {s: apertura_igual(leer_velas(d, s), pro["desde"]) for s in a.simbolos}
    tex.write_text(documento(cf, a.simbolos, diag, verd, ej, pro, curv, commit, verif, ap_igual), encoding="utf-8")
    pdf = compilar(tex)
    faltan = comprobar_pdf(pdf, cf.emitidas)
    print(f"PDF: {pdf} · {len(cf.emitidas)} cifras escritas, {len(faltan)} sin encontrar")
    for x in faltan[:20]:
        print("  ⛔", x)
    (sal / "cifras.json").write_text(json.dumps({"diagnostico": {s: {str(H): v for H, v in g.items()} for s, g in diag.items()},
                                                 "commit": commit, "predicciones": pro["commit"]},
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if faltan else 0


if __name__ == "__main__":
    raise SystemExit(main())
