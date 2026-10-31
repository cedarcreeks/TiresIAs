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


# ── 4. la preparación, de los zips al pedido de la primera pasada ─────────────
def cobertura_traduccion(posiciones: pd.DataFrame, traductor) -> pd.DataFrame:
    """Por trimestre de presentación: la parte del valor de las posiciones con símbolo en su fecha de presentación
    (una cota superior de la cobertura con precio, que exige además el precio)."""
    pares = posiciones[["cusip", "presentado"]].drop_duplicates()
    pares = pares.assign(simbolo=[traductor.simbolo(c, p) for c, p in zip(pares["cusip"], pares["presentado"])])
    p = posiciones.merge(pares, on=["cusip", "presentado"])
    p = p.assign(trimestre=p["presentado"].dt.to_period("Q"), con=p["simbolo"].notna() * p["valor"])
    g = p.groupby("trimestre").agg(valor=("valor", "sum"), con=("con", "sum"), gestores=("cik", "nunique"),
                                   cusips=("cusip", "nunique"))
    return g.assign(cobertura=g["con"] / g["valor"])[["gestores", "cusips", "cobertura"]]


def preparar(crudo, derivado, fin_datos: dt.date) -> dict:
    """FTD y 13F de `crudo/archivo_sec/{ftd,13f}` (y `crudo/sec_directo`, si trae alguno que falte) a `derivado/`:
    `ftd.parquet`, `13f/*.parquet`, `cobertura_traduccion.csv` y `pedido_1.json`. Devuelve un resumen."""
    import json
    import pathlib
    from tiresias import ingesta_2b as I
    from tiresias import precios as P
    crudo, derivado = pathlib.Path(crudo), pathlib.Path(derivado)
    derivado.mkdir(parents=True, exist_ok=True)
    def zips(patron):
        por_nombre = {f.name: f for f in sorted((crudo / "sec_directo").glob(patron))}
        por_nombre.update({f.name: f for f in sorted((crudo / "archivo_sec").rglob(patron))})
        return list(por_nombre.values())
    tabla, informe = I.ftd(zips("cnsfails*.zip"))
    tabla.to_parquet(derivado / "ftd.parquet", index=False)
    pos = I.posiciones(I.trece_f([f for f in zips("*form13f.zip") if not f.name.startswith("2015")], derivado / "13f"))
    trad = G.Traductor(tabla)
    cob = cobertura_traduccion(pos, trad)
    cob.to_csv(derivado / "cobertura_traduccion.csv")
    simb, _ = registros(tabla)
    v = ventanas(pos, fin_datos)
    por_cusip, rangos = P.plan(v, simb, {})
    ped = pedido(rangos, sorted(por_cusip))
    (derivado / "pedido_1.json").write_text(json.dumps(ped, default=str))
    return {"ftd_ficheros": len(informe), "ftd_registros": len(tabla), "posiciones": len(pos),
            "gestores": int(pos["cik"].nunique()), "cusips": len(v), "cusips_con_tramos": len(por_cusip),
            "simbolos": len(rangos), "lotes_barras": len(ped["barras"]), "lotes_acciones": len(ped["acciones"]),
            "cobertura_min": float(cob["cobertura"].min()), "cobertura_mediana": float(cob["cobertura"].median())}


# ── 5. la revisión de una pasada: contraste con el FTD y lo que falta pedir ───
def _dentro(serie: dict, ini: dt.date, fin: dt.date) -> dict:
    return {f: x for f, x in serie.items() if ini <= f <= fin}


def revisar(ventanas_c: dict, simb: dict, prec: dict, tal_cual: dict, acciones: dict, rangos_pedidos: dict) -> dict:
    """Tras una pasada de la descarga: los tramos definitivos de cada CUSIP y lo que queda por pedir.

    1. Los tramos se recortan con los cambios de nombre de los corporate actions (el día exacto del cambio).
    2. Cada tramo se contrasta con el precio de sus registros FTD (`precios.contraste_ftd`): vale con mediana de |Δ|
       ≤ `CONTRASTE_MAX`. Si no cuadra, o el símbolo no tiene barras, se prueba la forma con punto (BRKB → BRK.B) si
       ya está bajada, y si no se pide. Un tramo sin registros con precio queda «sin contraste».
    3. Se piden también los símbolos o rangos nuevos que traen los cambios de nombre y los cierres de lo escindido y
       de los compradores en su fecha (`cierres_ajenos` de `precios.rentabilidades`).

    Devuelve {"tramos": {cusip: [(símbolo, ini, fin)]}, "estado": {cusip: estado}, "rangos_pendientes": {símbolo:
    (desde, hasta)}, "ajenos": {(símbolo, fecha)}}; estado es «ok», «sin contraste», «pendiente» o «no cuadra»."""
    from tiresias import precios as P
    tramos, estado, pendientes, ajenos = {}, {}, {}, set()
    def pedido_cubre(s, i, f):
        a, b = rangos_pedidos.get(s, (None, None))
        return a is not None and a <= i and f <= b
    def pedir(s, i, f):
        x, y = pendientes.get(s, (i, f))
        pendientes[s] = (min(x, i), max(y, f))
    def juzgar(s, regs, i, f):
        """«ok», «sin contraste», «sin datos» (pedido y vacío), «no cuadra» o «pendiente» (sin pedir aún)."""
        if not pedido_cubre(s, i - MARGEN, f):
            pedir(s, i - MARGEN, f)
            return "pendiente"
        serie = _dentro(tal_cual.get(s, {}), i - MARGEN, f)
        if not serie:
            return "sin datos"
        n, med = P.contraste_ftd(regs, serie)
        return "sin contraste" if not n else ("ok" if med <= P.CONTRASTE_MAX else "no cuadra")
    for c, (desde, hasta) in ventanas_c.items():
        acc_c = P.acciones_de(c, acciones)
        ts = P.tramos(simb.get(c, []), desde, hasta, P.cambios_de_nombre(acc_c))
        if not ts:
            continue
        finales, estados = [], []
        for s, i, f in ts:
            regs = [(d, p) for d, p in prec.get(c, []) if i <= d <= f]
            elegido, e = s, juzgar(s, regs, i, f)
            if e in ("sin datos", "no cuadra"):
                punto = P.forma_con_punto(s)
                e2 = juzgar(punto, regs, i, f) if punto else "no cuadra"
                # la forma con punto sólo vale contrastada (BRKL no es BRK.L)
                if e2 == "ok":
                    elegido, e = punto, "ok"
                else:
                    e = "pendiente" if e2 == "pendiente" else "no cuadra"
            finales.append((elegido, i, f))
            estados.append(e)
        tramos[c] = finales
        estado[c] = next((x for x in ("no cuadra", "pendiente", "sin contraste") if x in estados), "ok")
        for d in P.acciones_de(c, acciones, finales).get("spin_offs", []):
            ajenos.add((d["new_symbol"], dt.date.fromisoformat(d["ex_date"])))
        for k in ("stock_mergers", "stock_and_cash_mergers"):
            for d in P.acciones_de(c, acciones, finales).get(k, []):
                ajenos.add((d["acquirer_symbol"], dt.date.fromisoformat(d["effective_date"])))
    return {"tramos": tramos, "estado": estado, "rangos_pendientes": pendientes, "ajenos": ajenos}
