"""Fase 2B: la receta de los mejores gestores 13F, elegidos sin mirar al futuro (docs/PLAN_FASE2.md, apartado 2B).

Piezas, cada una con sus tests (tests/test_tiresias_gestores.py):
  1. `leer_13f`: las posiciones de los 13F-HR originales de un conjunto de datos de la SEC (sólo acciones, sin opciones).
  2. `leer_ftd` y `Traductor`: CUSIP → símbolo **con fecha**, de los ficheros de *fails-to-deliver* de la SEC.
  3. `normalizar_nombre` y `mapa_por_nombre`: el respaldo por nombre del emisor, sin coincidencias ambiguas.
  4. `carteras`: la rentabilidad mensual que imita a cada gestor, con la cobertura mínima y el calendario declarados
     (las rentabilidades por CUSIP, de `tiresias.precios`).
  5. `receta`, `placebo` y `veredicto`: la selección por la t del alfa en 36 meses, la construcción de 2A′ para cada
     elegido, la comparación con el S&P 500, con el placebo y con «todos los gestores».
"""
from __future__ import annotations

import bisect
import re
import zipfile

import numpy as np
import pandas as pd

from tiresias import buffett as B

COBERTURA_MIN, POSICIONES_MIN = 0.90, 10
MESES_MAX = 4
VENTANA, DECIL = 36, 0.10
COSTE_ANUAL = 0.005
DIAS_POSTERIOR = 90
REPS_PLACEBO = 200
SEIS = B.SEIS


# ── 1. los 13F ─────────────────────────────────────────────────────────────
def _tsv(z: zipfile.ZipFile, nombre: str, columnas: list | None = None) -> pd.DataFrame:
    """Una tabla del conjunto (`SUBMISSION`, `COVERPAGE`, `INFOTABLE`), sea cual sea su carpeta dentro del zip, con
    las `columnas` pedidas. Falla si alguna línea no tiene tantos campos como la cabecera, o si no salen tantas filas
    como líneas: una línea partida (un salto dentro de un campo) da dos filas rotas, y contar filas no la ve."""
    miembro = next((m for m in z.namelist() if m.upper().endswith(f"{nombre}.TSV")), None)
    if miembro is None:
        raise ValueError(f"el zip no trae {nombre}.tsv")
    with z.open(miembro) as f:
        df = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False, quoting=3, encoding="latin-1",
                         usecols=columnas)
    cabecera, lineas, malas = None, 0, 0
    with z.open(miembro) as f:
        for linea in f:
            if not linea.strip():
                continue
            if cabecera is None:
                cabecera = linea.count(b"\t")
                continue
            lineas += 1
            malas += linea.count(b"\t") != cabecera
    if malas or lineas != len(df):
        raise ValueError(f"{nombre}.tsv: {malas} líneas con otro número de campos que la cabecera "
                         f"({lineas} líneas, {len(df)} filas leídas)")
    return df


def leer_13f(ruta) -> pd.DataFrame:
    """Posiciones de los 13F-HR **originales** (no enmiendas) que informan posiciones: una fila por (accesión, CUSIP)
    con `cik`, `periodo`, `presentado`, `emisor` y `valor` (suma de sus líneas). Sólo acciones (`SH`) y sin opciones.
    El valor sólo se usa para pesos dentro de cada 13F, así que el cambio de unidades de 2023 no afecta."""
    with zipfile.ZipFile(ruta) as z:
        sub, cov = _tsv(z, "SUBMISSION"), _tsv(z, "COVERPAGE", ["ACCESSION_NUMBER", "REPORTTYPE"])
        inf = _tsv(z, "INFOTABLE", ["ACCESSION_NUMBER", "NAMEOFISSUER", "CUSIP", "VALUE", "SSHPRNAMTTYPE", "PUTCALL"])
    sub = sub[sub["SUBMISSIONTYPE"].str.strip() == "13F-HR"]
    cov = cov[cov["REPORTTYPE"].str.strip().str.upper().isin({"13F HOLDINGS REPORT", "13F COMBINATION REPORT"})]
    sub = sub[sub["ACCESSION_NUMBER"].isin(set(cov["ACCESSION_NUMBER"]))]
    inf = inf[(inf["SSHPRNAMTTYPE"].str.strip().str.upper() == "SH") & (inf["PUTCALL"].str.strip() == "")]
    inf = inf.assign(valor=pd.to_numeric(inf["VALUE"].str.replace(",", ""), errors="coerce"),
                     cusip=inf["CUSIP"].str.strip().str.upper())
    inf = inf[(inf["valor"] > 0) & (inf["cusip"].str.len() == 9)]
    g = (inf.groupby(["ACCESSION_NUMBER", "cusip"], as_index=False)
            .agg(valor=("valor", "sum"), emisor=("NAMEOFISSUER", "first")))
    s = sub.assign(presentado=pd.to_datetime(sub["FILING_DATE"].str.strip(), format="%d-%b-%Y"),
                   periodo=pd.to_datetime(sub["PERIODOFREPORT"].str.strip(), format="%d-%b-%Y"),
                   cik=sub["CIK"].str.strip().str.lstrip("0"))
    # Un original por gestor y trimestre: si hubiera dos, el primero presentado (el que se sabía antes).
    s = s.sort_values("presentado").drop_duplicates(["cik", "periodo"], keep="first")
    out = g.merge(s[["ACCESSION_NUMBER", "cik", "periodo", "presentado"]], on="ACCESSION_NUMBER")
    return out.rename(columns={"ACCESSION_NUMBER": "accesion"})[
        ["accesion", "cik", "periodo", "presentado", "cusip", "emisor", "valor"]]


# ── 2. CUSIP → símbolo, con fecha ────────────────────────────────────────────
def leer_ftd(texto: str) -> pd.DataFrame:
    """Un fichero de fails-to-deliver de la SEC (`SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY|DESCRIPTION|PRICE`):
    (cusip, simbolo, fecha, precio) únicos, de las filas con fecha, CUSIP de 9 caracteres y símbolo. `precio` es, según
    la SEC, el cierre del día anterior (NaN si viene «.»); el símbolo de una clase va sin punto (BRKB por BRK.B).

    Las filas se cuentan contra la línea final del fichero («Trailer record count N») y una que no tenga sus seis
    campos hace fallar la lectura: nada se salta en silencio. Una barra dentro de la descripción no rompe la fila
    (sólo se usan los tres primeros campos). `attrs["declaradas"]`: el recuento final, o None si no lo trae."""
    filas, declaradas = [], None
    for i, linea in enumerate(texto.splitlines()):
        linea = linea.strip()
        if not linea or (i == 0 and linea.upper().startswith("SETTLEMENT DATE")):
            continue
        m = re.match(r"trailer record count\s+(\d+)", linea, re.I)
        if m:
            declaradas = int(m.group(1))
            continue
        if linea.lower().startswith("trailer"):
            continue
        partes = linea.split("|")
        if len(partes) < 6:
            raise ValueError(f"FTD, línea {i + 1} sin sus seis campos: {linea[:80]!r}")
        precio = partes[-1].strip()
        filas.append((partes[1].strip().upper(), partes[2].strip().upper(), partes[0].strip(),
                      float(precio) if re.fullmatch(r"\d+(\.\d+)?", precio) else float("nan")))
    if declaradas is not None and declaradas != len(filas):
        raise ValueError(f"FTD: {len(filas)} filas leídas y el fichero declara {declaradas}")
    df = pd.DataFrame(filas, columns=["cusip", "simbolo", "fecha", "precio"])
    df = df[df["fecha"].str.fullmatch(r"\d{8}") & (df["cusip"].str.len() == 9) & (df["simbolo"] != "")]
    out = df.assign(fecha=pd.to_datetime(df["fecha"], format="%Y%m%d")).drop_duplicates().reset_index(drop=True)
    out.attrs["declaradas"] = declaradas
    return out


class Traductor:
    """CUSIP → símbolo en una fecha: el del registro más cercano **anterior** (o el mismo día) y, si no hay, el primero
    posterior dentro de `DIAS_POSTERIOR` días."""

    def __init__(self, tabla: pd.DataFrame):
        self._por = {}
        for c, g in tabla.sort_values("fecha").groupby("cusip"):
            self._por[c] = (list(g["fecha"]), list(g["simbolo"]))

    def simbolo(self, cusip: str, fecha: pd.Timestamp):
        if cusip not in self._por:
            return None
        fechas, simbolos = self._por[cusip]
        i = bisect.bisect_right(fechas, fecha)
        if i > 0:
            return simbolos[i - 1]
        return simbolos[0] if (fechas[0] - fecha).days <= DIAS_POSTERIOR else None


# ── 3. el respaldo por nombre ──────────────────────────────────────────────
_SUFIJOS = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP", "THE",
            "COMMON", "STOCK", "SHARES", "ORDINARY", "CL", "CLASS", "COM", "NEW", "DEL", "SA", "NV", "AG", "AND"}


def normalizar_nombre(nombre: str) -> str:
    """Mayúsculas, sin puntuación ni sufijos societarios: «Apple Inc. Common Stock» → «APPLE»."""
    palabras = re.sub(r"[^A-Z0-9 ]", " ", (nombre or "").upper().replace("&", " AND ")).split()
    return " ".join(p for p in palabras if p not in _SUFIJOS)


def mapa_por_nombre(emisores: dict, activos: list) -> dict:
    """{cusip: emisor} contra [(símbolo, nombre)] (los inactivos de Alpaca): sólo las coincidencias únicas."""
    por_nombre = {}
    for s, n in activos:
        por_nombre.setdefault(normalizar_nombre(n), set()).add(s)
    out = {}
    for c, e in emisores.items():
        cand = por_nombre.get(normalizar_nombre(e), set())
        if len(cand) == 1:
            out[c] = next(iter(cand))
    return out


# ── 4. las carteras que imitan a cada gestor ──────────────────────────────
def mes_de_entrada(presentado: pd.Timestamp) -> pd.Timestamp:
    """El primer mes completo tras la presentación, como fin de mes: presentado el 14-feb → marzo (31-mar)."""
    return presentado + pd.offsets.MonthEnd(0) + pd.offsets.MonthEnd(1)


def carteras(posiciones: pd.DataFrame, rent: pd.DataFrame) -> tuple:
    """Rentabilidad mensual de cada gestor (DataFrame meses × cik) y la cobertura de cada 13F.

    `posiciones`: las de `leer_13f`. `rent`: rentabilidades mensuales (fin de mes × **CUSIP**, de `precios`): por CUSIP
    y no por símbolo, porque un símbolo se reutiliza (META fue un ETF hasta 2022). Un 13F cuenta si tiene precio en
    su primer mes el ≥ 90 % de su valor y al menos 10 posiciones; sus pesos, por valor entre las que tienen precio. Dura hasta el mes
    de entrada del siguiente 13F del gestor (exclusive), como mucho `MESES_MAX` meses. Un valor sin precio un mes (se
    retiró de bolsa) se reparte entre los demás ese mes."""
    meses = rent.index
    cols = {s: j for j, s in enumerate(rent.columns)}
    R = rent.to_numpy()
    filas, cobertura = {}, []
    for cik, g in posiciones.groupby("cik"):
        # un 13F atrasado de un periodo anterior al último ya presentado no trae una cartera nueva (se sabía otra más
        # reciente): fuera, para que no sustituya a la buena con posiciones viejas
        por_fecha = g.drop_duplicates("presentado")[["presentado", "periodo"]].sort_values("presentado")
        vigentes = por_fecha[por_fecha["periodo"] > por_fecha["periodo"].cummax().shift(1, fill_value=pd.Timestamp.min)]
        g = g[g["presentado"].isin(set(vigentes["presentado"]))]
        pres = sorted(g["presentado"].unique())
        entradas = [mes_de_entrada(pd.Timestamp(p)) for p in pres]
        for k, p in enumerate(pres):
            h = g[g["presentado"] == p]
            ini = entradas[k]
            fin = entradas[k + 1] if k + 1 < len(pres) else ini + pd.offsets.MonthEnd(MESES_MAX)
            fin = min(fin, ini + pd.offsets.MonthEnd(MESES_MAX))
            i0 = meses.searchsorted(ini)
            if i0 >= len(meses) or meses[i0] != ini:          # su primer mes no está en los precios
                cobertura.append({"cik": cik, "presentado": p, "cobertura": 0.0, "n": 0, "entra": False})
                continue
            idx = [cols.get(c) for c in h["cusip"]]
            con_precio = np.array([j is not None and not np.isnan(R[i0, j]) for j in idx], dtype=bool)
            v = h["valor"].to_numpy(dtype=float)
            cob = float(v[con_precio].sum() / v.sum()) if v.sum() > 0 else 0.0
            n = int(con_precio.sum())
            entra = cob >= COBERTURA_MIN and n >= POSICIONES_MIN
            cobertura.append({"cik": cik, "presentado": p, "cobertura": cob, "n": n, "entra": entra})
            if not entra:
                continue
            js = np.array([j for j, ok in zip(idx, con_precio) if ok])
            w = v[con_precio] / v[con_precio].sum()
            for i in range(i0, len(meses)):
                if meses[i] >= fin:
                    break
                r = R[i, js]
                ok = ~np.isnan(r)
                if ok.any():
                    filas[(meses[i], cik)] = float(np.dot(w[ok], r[ok]) / w[ok].sum())
    if filas:
        s = pd.Series(filas)
        s.index = pd.MultiIndex.from_tuples(s.index, names=["mes", "cik"])
        r_gestores = s.unstack("cik").sort_index()
    else:
        r_gestores = pd.DataFrame(index=pd.DatetimeIndex([], name="mes"))
    return r_gestores, pd.DataFrame(cobertura)


# ── 5. la selección, la receta y el veredicto ─────────────────────────────
def t_alfa(exceso: pd.Series, F: pd.DataFrame) -> float:
    r = B.ols(exceso, F[SEIS])
    return r["t"]["alfa"]


def decisiones(r_gestores: pd.DataFrame, F: pd.DataFrame, desde: str) -> list:
    """Cada fin de trimestre desde `desde`: los gestores con 36 meses de historia completos hasta esa fecha (sólo
    hasta ella), con la t de su alfa y sus parámetros de 2A′ estimados en esa ventana."""
    out = []
    finales = [d for d in r_gestores.index if d.month in (3, 6, 9, 12) and d >= pd.Timestamp(desde) - pd.offsets.MonthEnd(1)]
    for d in finales:
        ventana = r_gestores.loc[:d].iloc[-VENTANA:]
        if len(ventana) < VENTANA:
            continue
        completos = ventana.columns[ventana.notna().all()]
        info = {}
        for cik in completos:
            datos = F.loc[ventana.index].assign(EXCESO=ventana[cik] - F.loc[ventana.index, "RF"])
            info[cik] = {"t": t_alfa(datos["EXCESO"], datos), "p": B.estilo_buffett(datos)}
        out.append((d, info))
    return out


def receta(decs: list, F: pd.DataFrame, elegir) -> pd.Series:
    """El exceso mensual de la receta: en cada decisión, `elegir(info) -> [cik]`; los tres meses siguientes, la media de
    la estrategia de 2A′ de cada elegido con sus parámetros congelados en su ventana."""
    filas = {}
    for k, (d, info) in enumerate(decs):
        elegidos = elegir(info)
        if not elegidos:
            continue
        siguientes = F.loc[d:].iloc[1:4]
        if k + 1 < len(decs):
            siguientes = siguientes.loc[:decs[k + 1][0]]
        for m in siguientes.index:
            fila = siguientes.loc[[m]]
            filas[m] = float(np.mean([B.aplicar_estilo(fila, info[c]["p"]).iloc[0] for c in elegidos]))
    return pd.Series(filas).sort_index()


def elegir_decil(info: dict) -> list:
    """El decil superior por la t del alfa (al menos uno)."""
    orden = sorted(info, key=lambda c: info[c]["t"], reverse=True)
    return orden[:max(1, int(round(len(orden) * DECIL)))] if orden else []


def elegir_todos(info: dict) -> list:
    return list(info)


def elegir_azar(semilla: int):
    rng = np.random.default_rng(semilla)

    def f(info):
        n = max(1, int(round(len(info) * DECIL))) if info else 0
        return list(rng.choice(sorted(info), size=n, replace=False)) if n else []
    return f


def neto(exceso: pd.Series) -> pd.Series:
    return exceso - COSTE_ANUAL / 12


def metricas(exceso: pd.Series, rf: pd.Series) -> dict:
    total = (1 + exceso + rf.reindex(exceso.index)).cumprod()
    años = len(exceso) / 12
    return {"sharpe": float(exceso.mean() / exceso.std() * np.sqrt(12)),
            "cagr": float(total.iloc[-1] ** (1 / años) - 1), "meses": int(len(exceso))}


def veredicto(receta_neta: pd.Series, sp_exceso: pd.Series, todos_neta: pd.Series, placebo_sharpes: list,
              rf: pd.Series) -> dict:
    """Las cuatro de 2B (docs/PLAN_FASE2.md)."""
    idx = receta_neta.index.intersection(sp_exceso.index)
    r, s = receta_neta.loc[idx], sp_exceso.loc[idx]
    mitad = idx[len(idx) // 2]

    def gana(a, b):
        ma, mb = metricas(a, rf), metricas(b, rf)
        return ma["sharpe"] - mb["sharpe"] >= 0.10 and ma["cagr"] - mb["cagr"] >= 0.01
    sh = metricas(r, rf)["sharpe"]
    crit = {
        "1_frente_al_sp500": gana(r, s),
        "2_en_las_dos_mitades": gana(r.loc[:mitad - pd.offsets.MonthEnd(1)], s.loc[:mitad - pd.offsets.MonthEnd(1)])
                                and gana(r.loc[mitad:], s.loc[mitad:]),
        "3_sobre_el_placebo_p95": bool(placebo_sharpes) and sh > float(np.percentile(placebo_sharpes, 95)),
        "4_sobre_todos_los_gestores": sh - metricas(todos_neta.loc[idx], rf)["sharpe"] >= 0.05,
    }
    n = sum(crit.values())
    return {"criterios": crit, "cumplidos": n, "de": len(crit), "pasa": n == len(crit)}
