"""Fase 2D: las mejores ideas de los gestores, veinte años después (docs/PLAN_FASE2.md, apartado 2D).

El método de Cohen, Polk y Silli (LSE FMG DP624, sección 3 y apartado 4.2): la mejor idea de cada gestor es el valor
con mayor *tilt* (su peso en la cartera menos su peso en el mercado); sólo el 25 % de gestores con mayor *tilt*; la
cartera de mejores ideas, a partes iguales. Con 13F y en la fecha pública, como en 2B.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from tiresias import buffett as B
from tiresias import gestores as G

MIN_VALORES, CUARTIL = 20, 0.75
COSTE_LADO = 0.001
CARHART = ["MKT", "SMB", "HML", "UMD"]


def pesos_mercado(pos: pd.DataFrame) -> pd.DataFrame:
    """El peso de cada CUSIP en la suma de todos los 13F de su periodo: (periodo, cusip, peso_mercado)."""
    v = pos.groupby(["periodo", "cusip"], as_index=False)["valor"].sum()
    v["peso_mercado"] = v["valor"] / v.groupby("periodo")["valor"].transform("sum")
    return v[["periodo", "cusip", "peso_mercado"]]


def candidatas(pos: pd.DataFrame, rent: pd.DataFrame, modo: str = "market") -> pd.DataFrame:
    """Las posiciones que pueden ser mejor idea, con su *tilt*: de 13F con al menos `MIN_VALORES` valores con precio en
    su mes de entrada. Vectorizado (un bucle por 13F sobre 63 M de posiciones es el patrón que tumbó la revisión de 2B).
    `modo`: «market» (peso − peso en el mercado) o «portfolio» (peso − peso de su propia cartera ponderada por mercado)."""
    p = pos.merge(pesos_mercado(pos), on=["periodo", "cusip"])
    p = p.assign(entrada=p["presentado"] + pd.offsets.MonthEnd(0) + pd.offsets.MonthEnd(1))
    largo = rent.stack().reset_index()
    largo.columns = ["entrada", "cusip", "r"]
    p = p.merge(largo[["entrada", "cusip"]], on=["entrada", "cusip"])          # sólo lo que tiene precio al entrar
    clave = ["cik", "presentado"]
    p = p[p.groupby(clave)["cusip"].transform("size") >= MIN_VALORES]
    w = p["valor"] / p.groupby(clave)["valor"].transform("sum")
    ref = p["peso_mercado"] if modo == "market" else p["peso_mercado"] / p.groupby(clave)["peso_mercado"].transform("sum")
    return p.assign(tilt=w - ref)


def ideas(pos: pd.DataFrame, rent: pd.DataFrame, modo: str = "market", semilla=None, cand=None) -> pd.DataFrame:
    """Una fila por 13F: (cik, presentado, cusip, tilt, periodo) de su mejor idea (el mayor *tilt*). Con `semilla`, el
    placebo: un valor al azar del 13F en vez de su mejor idea, con el *tilt* de su mejor idea (para que el filtro de
    activos elija a los mismos gestores)."""
    c = cand if cand is not None else candidatas(pos, rent, modo)
    clave = ["cik", "presentado"]
    maximo = c.groupby(clave)["tilt"].transform("max")
    if semilla is None:
        elegidas = c.loc[c.groupby(clave)["tilt"].idxmax()]
    else:
        azar = pd.Series(np.random.default_rng(semilla).random(len(c)), index=c.index)
        elegidas = c.loc[azar.groupby([c["cik"], c["presentado"]]).idxmax()]
    out = elegidas.assign(tilt=maximo.loc[elegidas.index])[["cik", "presentado", "cusip", "tilt", "periodo"]]
    return out.reset_index(drop=True)


def activos(ideas_df: pd.DataFrame) -> pd.DataFrame:
    """El 25 % de 13F con mayor *tilt* en su mejor idea, por periodo (los autores, para dejar fuera a los casi
    indexados)."""
    corte = ideas_df.groupby("periodo")["tilt"].transform(lambda s: s.quantile(CUARTIL))
    return ideas_df[ideas_df["tilt"] >= corte]


def cartera(ideas_df: pd.DataFrame, rent: pd.DataFrame) -> tuple:
    """(rentabilidad mensual bruta, coste mensual): cada idea entra en el primer mes completo tras su 13F y dura hasta la
    entrada del siguiente del gestor, como mucho `MESES_MAX` meses; todas a partes iguales (una idea de dos gestores
    pesa doble). Coste = `COSTE_LADO` × Σ|Δpeso| de un mes al siguiente."""
    meses = rent.index
    pesos = {}
    for cik, g in ideas_df.sort_values("presentado").groupby("cik"):
        filas = g.to_dict("records")
        entradas = [G.mes_de_entrada(pd.Timestamp(f["presentado"])) for f in filas]
        for k, f in enumerate(filas):
            ini = entradas[k]
            fin = min(entradas[k + 1] if k + 1 < len(filas) else ini + pd.offsets.MonthEnd(G.MESES_MAX),
                      ini + pd.offsets.MonthEnd(G.MESES_MAX))
            for m in meses[(meses >= ini) & (meses < fin)]:
                pesos.setdefault(m, {}).setdefault(f["cusip"], 0)
                pesos[m][f["cusip"]] += 1
    r, coste, previo = {}, {}, {}
    for m in sorted(pesos):
        cuenta = pesos[m]
        x = rent.loc[m, list(cuenta)].to_numpy(dtype=float)
        n = np.array(list(cuenta.values()), dtype=float)
        ok = ~np.isnan(x)
        if not ok.any():
            continue
        r[m] = float(np.dot(n[ok], x[ok]) / n[ok].sum())
        w = {c: k / n[ok].sum() for (c, k), o in zip(cuenta.items(), ok) if o}
        cambio = sum(abs(w.get(c, 0) - previo.get(c, 0)) for c in set(w) | set(previo))
        coste[m] = COSTE_LADO * cambio
        previo = w
    return pd.Series(r, dtype=float).sort_index(), pd.Series(coste, dtype=float).sort_index()


def alfa_carhart(exceso: pd.Series, F: pd.DataFrame) -> dict:
    """Alfa mensual de cuatro factores (MKT, SMB, HML, UMD) y su t, con errores clásicos como en el artículo."""
    idx = exceso.index.intersection(F.index)
    r = B.ols(exceso.loc[idx], F.loc[idx, CARHART])
    return {"alfa_mensual": r["coef"]["alfa"], "t": r["t"]["alfa"], "meses": r["n"]}


def veredicto(neta_ex: pd.Series, bruta_ex: pd.Series, sp_ex: pd.Series, F: pd.DataFrame, placebo: list) -> dict:
    """Los tres criterios de 2D."""
    rf = F["RF"]
    idx = neta_ex.index.intersection(sp_ex.index)
    a, s = neta_ex.loc[idx], sp_ex.loc[idx]
    mitad = idx[len(idx) // 2]

    def gana(x, y):
        mx, my = G.metricas(x, rf), G.metricas(y, rf)
        return mx["sharpe"] - my["sharpe"] >= 0.10 and mx["cagr"] - my["cagr"] >= 0.01
    al = alfa_carhart(bruta_ex, F)
    sh = G.metricas(a, rf)["sharpe"]
    crit = {"1_alfa_carhart_t2": al["alfa_mensual"] > 0 and al["t"] >= 2,
            "2_gana_al_sp500_total_y_mitades": gana(a, s) and gana(a.loc[:mitad - pd.offsets.MonthEnd(1)],
                                                                    s.loc[:mitad - pd.offsets.MonthEnd(1)])
            and gana(a.loc[mitad:], s.loc[mitad:]),
            "3_sobre_el_placebo_p95": bool(placebo) and sh > float(np.percentile(placebo, 95))}
    return {"alfa": al, "neta": G.metricas(a, rf), "sp500": G.metricas(s, rf),
            "placebo_mediana": float(np.median(placebo)) if placebo else None,
            "placebo_p95": float(np.percentile(placebo, 95)) if placebo else None,
            "criterios": crit, "cumplidos": int(sum(crit.values())), "pasa": all(crit.values())}


def ejecutar(raiz, pasadas: list, reps: int = 200) -> dict:
    """El juicio de 2D de los datos en disco: la definición principal («market») y la robustez («portfolio»)."""
    import datetime as dt
    import pathlib
    from tiresias import fase2b as F2, ingesta_2b as I
    raiz = pathlib.Path(raiz)
    cache = raiz / "derivado/rent_cusip.parquet"
    pos = I.posiciones(sorted((raiz / "derivado/13f").glob("*.parquet")))[["cik", "periodo", "presentado", "cusip", "valor"]]
    if cache.exists():
        rent = pd.read_parquet(cache)
    else:
        r = F2.rentabilidades_por_cusip(pos, pd.read_parquet(raiz / "derivado/ftd.parquet"), pasadas, dt.date(2026, 10, 30))
        rent = r["rent"]
        rent.to_parquet(cache)
    F = B.cargar(raiz / "crudo")
    sp = F2.mensual_yahoo(raiz / "crudo/SP500TR_1d.json")
    rf = F["RF"]
    out = {}
    for modo in ("market", "portfolio"):
        cand = candidatas(pos, rent, modo)
        real = activos(ideas(pos, rent, modo, cand=cand))
        bruta, coste = cartera(real, rent)
        idx = bruta.index.intersection(rf.index)
        bruta_ex, neta_ex = bruta.loc[idx] - rf.loc[idx], (bruta - coste).loc[idx] - rf.loc[idx]
        plac = []
        for s in range(reps):
            b, c = cartera(activos(ideas(pos, rent, modo, semilla=s, cand=cand)), rent)
            i2 = b.index.intersection(rf.index)
            plac.append(G.metricas((b - c).loc[i2] - rf.loc[i2], rf)["sharpe"])
        v = veredicto(neta_ex, bruta_ex, (sp - rf.reindex(sp.index)).dropna(), F, plac)
        out[modo] = {"ideas": int(len(real)), "gestores": int(real["cik"].nunique()),
                     "meses": [str(idx.min().date()), str(idx.max().date()), int(len(idx))],
                     "bruta": G.metricas(bruta_ex, rf), "coste_anual_medio": float(coste.loc[idx].mean() * 12), **v}
    return out


if __name__ == "__main__":
    import json
    import pathlib
    import sys
    casa = pathlib.Path.home()
    r = ejecutar(casa / "tiresias_datos/fase2", [pathlib.Path(x) for x in sys.argv[1:]])
    destino = casa / "tiresias_resultados/fase2/2d.json"
    destino.write_text(json.dumps(r, indent=1, default=str))
    for modo, x in r.items():
        print(modo, json.dumps({k: x[k] for k in ("ideas", "gestores", "meses", "alfa", "bruta", "neta", "sp500",
                                                  "coste_anual_medio", "placebo_mediana", "placebo_p95", "criterios",
                                                  "cumplidos")}, default=str))
