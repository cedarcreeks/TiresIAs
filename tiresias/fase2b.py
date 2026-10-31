"""Fase 2B de punta a punta, en el lado que no necesita claves (docs/PLAN_FASE2.md, apartado 2B).

  1. `ventanas`: qué fechas de precios necesita cada CUSIP, por los 13F que lo tienen y su calendario.
  2. `registros`: los registros de los FTD de cada CUSIP, (fecha, símbolo) para los tramos y (fecha, precio) para el
     contraste.
  3. `pedido`: las peticiones de barras y de corporate actions para `tiresias.descarga_2b`, en lotes con un id que sale
     de su contenido (repetir el plan no repite descargas).
"""
from __future__ import annotations

import datetime as dt
import hashlib

import pandas as pd

from tiresias import gestores as G

MARGEN = dt.timedelta(days=10)      # días del mes anterior a la entrada: el cierre de partida
LOTE_BARRAS, LOTE_ACCIONES = 50, 100


def ventanas(posiciones: pd.DataFrame, fin_datos: dt.date) -> dict:
    """{cusip: (desde, hasta)}: desde unos días antes del final del mes previo a su primera entrada (el cierre de
    partida) hasta el último día del último mes en que puede tenerse (`MESES_MAX` meses tras su última entrada)."""
    g = posiciones.groupby("cusip")["presentado"].agg(["min", "max"])
    out = {}
    for c, (pmin, pmax) in g.iterrows():
        ini = G.mes_de_entrada(pd.Timestamp(pmin))
        fin = G.mes_de_entrada(pd.Timestamp(pmax)) + pd.offsets.MonthEnd(G.MESES_MAX - 1)
        out[c] = ((ini - pd.offsets.MonthEnd(1)).date() - MARGEN, min(fin.date(), fin_datos))
    return out


def registros(ftd: pd.DataFrame) -> tuple:
    """({cusip: [(fecha, símbolo)]}, {cusip: [(fecha, precio)]}), ordenados por fecha."""
    t = ftd.sort_values(["cusip", "fecha"])
    simb, prec = {}, {}
    for c, g in t.groupby("cusip", sort=False):
        fechas = [f.date() for f in g["fecha"]]
        simb[c] = list(zip(fechas, g["simbolo"]))
        prec[c] = [(f, float(p)) for f, p in zip(fechas, g["precio"]) if p == p]
    return simb, prec


def _id(*partes) -> str:
    return hashlib.sha1(repr(partes).encode()).hexdigest()[:12]


def pedido(rangos: dict, cusips: list, modos=("all", "raw", "tal_cual"), desde_acciones="2016-01-01",
           hasta_acciones="2026-10-31") -> dict:
    """Las peticiones de `tiresias.descarga_2b`: barras en lotes de `LOTE_BARRAS` símbolos de rangos parecidos (por
    fecha de inicio), cada uno con la unión de sus rangos; corporate actions por CUSIP y por símbolo (hacen falta las
    dos: antes de 2020 Alpaca no pone CUSIP)."""
    simbolos = sorted(rangos, key=lambda s: (rangos[s][0], s))
    barras = []
    for i in range(0, len(simbolos), LOTE_BARRAS):
        lote = simbolos[i:i + LOTE_BARRAS]
        d, h = min(rangos[s][0] for s in lote).isoformat(), max(rangos[s][1] for s in lote).isoformat()
        barras.append({"id": _id(tuple(lote), d, h), "simbolos": lote, "desde": d, "hasta": h, "modos": list(modos)})
    acciones = []
    for campo, lista in (("cusips", sorted(cusips)), ("simbolos", sorted(rangos))):
        for i in range(0, len(lista), LOTE_ACCIONES):
            lote = lista[i:i + LOTE_ACCIONES]
            acciones.append({"id": _id(campo, tuple(lote)), campo: lote, "desde": desde_acciones,
                             "hasta": hasta_acciones})
    return {"barras": barras, "acciones": acciones}
