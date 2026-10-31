"""Fase 2A: reproducir la tabla 4 de *Buffett's Alpha* con datos públicos (el control de la fase 2).

    python -m tiresias.buffett [--datos ~/tiresias_datos/fase2/crudo] [--salida ~/tiresias_resultados/fase2]

Frazzini, Kabiller y Pedersen (NBER w19681, 2013), sección 6 y tabla 4: regresión mensual del exceso de rentabilidad de
Berkshire sobre MKT, SMB, HML y UMD (columna 1), más BAB (columna 2), más QMJ (columna 3). Aquí, con la biblioteca de
Ken French (MKT, SMB, HML, UMD y el tipo libre), la de AQR (BAB y QMJ de EE. UU.) y los cierres de BRK-A, de 1980-04 a
2011-12: el artículo usa CRSP desde 1976-11, y la serie pública de BRK-A empieza en 1980 (diferencia declarada en
docs/PLAN_FASE2.md, que también fija el criterio de abajo antes de bajar los datos).
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import pathlib

import numpy as np
import pandas as pd

DESDE, HASTA = "1980-04-30", "2011-12-31"
FACTORES = {"columna 1": ["MKT", "SMB", "HML", "UMD"], "columna 2": ["MKT", "SMB", "HML", "UMD", "BAB"],
            "columna 3": ["MKT", "SMB", "HML", "UMD", "BAB", "QMJ"]}
# Tabla 4 del artículo, Berkshire 1976-2011: (coeficiente, t). El alfa, anualizado.
PUBLICADO = {
    "columna 1": {"alfa": (0.121, 3.19), "MKT": (0.84, 11.65), "SMB": (-0.32, -3.05), "HML": (0.63, 5.35),
                  "UMD": (0.06, 0.90)},
    "columna 2": {"alfa": (0.092, 2.42), "MKT": (0.83, 11.70), "SMB": (-0.32, -3.13), "HML": (0.38, 2.79),
                  "UMD": (-0.03, -0.40), "BAB": (0.37, 3.61)},
    "columna 3": {"alfa": (0.063, 1.58), "MKT": (0.95, 10.98), "SMB": (-0.15, -1.15), "HML": (0.46, 3.28),
                  "UMD": (-0.05, -0.71), "BAB": (0.29, 2.67), "QMJ": (0.43, 2.34)},
}
TOLERANCIA = 0.15
DATOS = pathlib.Path.home() / "tiresias_datos" / "fase2" / "crudo"
SALIDA = pathlib.Path.home() / "tiresias_resultados" / "fase2"


def fin_de_mes(fechas) -> pd.DatetimeIndex:
    return pd.DatetimeIndex(fechas) + pd.offsets.MonthEnd(0)


def leer_french(texto: str) -> pd.DataFrame:
    """La primera tabla mensual de un CSV de Ken French (filas AAAAMM), en tanto por uno, con índice a fin de mes."""
    lineas = texto.splitlines()
    cab = next(i for i, l in enumerate(lineas) if l.startswith(",") and l.strip(", "))
    filas = []
    for l in lineas[cab + 1:]:
        celdas = [c.strip() for c in l.split(",")]
        if not celdas or not (len(celdas[0]) == 6 and celdas[0].isdigit()):
            break
        filas.append(celdas)
    if not filas:
        raise ValueError("no hay filas mensuales tras la cabecera")
    columnas = [c.strip() for c in lineas[cab].split(",")[1:]]
    df = pd.DataFrame([[float(x) for x in f[1:]] for f in filas], columns=columnas,
                      index=fin_de_mes(pd.to_datetime([f[0] for f in filas], format="%Y%m")))
    return df / 100.0


def leer_aqr(ruta: pathlib.Path, hoja: str, columna: str = "USA") -> pd.Series:
    """Una columna de una hoja de los ficheros de AQR (cabecera en la fila que empieza por DATE), a fin de mes."""
    import openpyxl
    ws = openpyxl.load_workbook(ruta, read_only=True, data_only=True)[hoja]
    filas = list(ws.iter_rows(values_only=True))
    cab = next(i for i, f in enumerate(filas) if f and f[0] == "DATE")
    j = list(filas[cab]).index(columna)
    datos = {}
    for f in filas[cab + 1:]:
        if not f or f[0] is None or str(f[0]).strip() == "":     # el final: celda vacía o en blanco
            break
        if f[j] is not None:
            fecha = f[0] if isinstance(f[0], dt.datetime) else dt.datetime.strptime(str(f[0]), "%m/%d/%Y")
            datos[fecha] = float(f[j])
    s = pd.Series(datos, dtype="float64").sort_index()
    s.index = fin_de_mes(s.index)
    return s


def mensual(cierres: pd.Series) -> pd.Series:
    """Rentabilidad de cada mes con el último cierre del mes; el primer mes, incompleto, no cuenta."""
    fin = cierres.groupby(fin_de_mes(cierres.index)).last()
    return fin.pct_change().iloc[1:]


def ols(y: pd.Series, X: pd.DataFrame) -> dict:
    """Mínimos cuadrados con constante: coeficientes, sus t (errores clásicos) y el R² ajustado."""
    A = np.column_stack([np.ones(len(X)), X.to_numpy()])
    b, *_ = np.linalg.lstsq(A, y.to_numpy(), rcond=None)
    e = y.to_numpy() - A @ b
    n, k = A.shape
    s2 = e @ e / (n - k)
    se = np.sqrt(np.diag(s2 * np.linalg.inv(A.T @ A)))
    r2 = 1 - (e @ e) / np.sum((y.to_numpy() - y.mean()) ** 2)
    nombres = ["alfa"] + list(X.columns)
    return {"coef": dict(zip(nombres, b.tolist())), "t": dict(zip(nombres, (b / se).tolist())), "n": int(n),
            "r2_ajustado": float(1 - (1 - r2) * (n - 1) / (n - k))}


def tabla4(datos: pd.DataFrame) -> dict:
    """Las tres columnas de Berkshire. `datos`: EXCESO (exceso de BRK sobre el tipo libre) y los seis factores."""
    out = {}
    for col, fs in FACTORES.items():
        r = ols(datos["EXCESO"], datos[fs])
        r["coef"]["alfa"] *= 12                       # anualizado, como en el artículo
        out[col] = r
    return out


def veredicto(t4: dict) -> dict:
    """Las tres de docs/PLAN_FASE2.md (2A); pasa sólo con las tres."""
    c3, pub = t4["columna 3"], PUBLICADO["columna 3"]
    crit = {
        "1_cargas_a_015": all(abs(c3["coef"][f] - pub[f][0]) <= TOLERANCIA for f in ("MKT", "HML", "BAB", "QMJ")),
        "2_bab_y_qmj_positivos_t2": all(c3["coef"][f] > 0 and c3["t"][f] >= 2 for f in ("BAB", "QMJ")),
        "3_alfa_4f_t2_y_6f_no": t4["columna 1"]["t"]["alfa"] >= 2 and c3["t"]["alfa"] < 2,
    }
    n = sum(crit.values())
    return {"criterios": crit, "cumplidos": n, "de": len(crit), "pasa": n == len(crit)}


def cargar(datos: pathlib.Path) -> pd.DataFrame:
    ff = leer_french((datos / "F-F_Research_Data_Factors.csv").read_text(encoding="latin-1"))
    mom = leer_french((datos / "F-F_Momentum_Factor.csv").read_text(encoding="latin-1"))
    bab = leer_aqr(datos / "Betting-Against-Beta-Equity-Factors-Monthly.xlsx", "BAB Factors")
    qmj = leer_aqr(datos / "Quality-Minus-Junk-Factors-Monthly.xlsx", "QMJ Factors")
    d = json.loads((datos / "BRK-A_1d.json").read_text(encoding="utf-8"))["chart"]["result"][0]
    fechas = pd.to_datetime([dt.datetime.fromtimestamp(t, dt.timezone.utc).date() for t in d["timestamp"]])
    brk = pd.Series(d["indicators"]["adjclose"][0]["adjclose"], index=fechas, dtype="float64").dropna()
    df = pd.concat({"BRK": mensual(brk), "MKT": ff["Mkt-RF"], "SMB": ff["SMB"], "HML": ff["HML"], "RF": ff["RF"],
                    "UMD": mom[mom.columns[0]], "BAB": bab, "QMJ": qmj}, axis=1, join="inner")
    df["EXCESO"] = df["BRK"] - df["RF"]
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default=str(DATOS))
    ap.add_argument("--salida", default=str(SALIDA))
    a = ap.parse_args(argv)
    df = cargar(pathlib.Path(a.datos)).loc[DESDE:HASTA]
    t4 = tabla4(df)
    v = veredicto(t4)
    out = {"periodo": [str(df.index[0].date()), str(df.index[-1].date())], "meses": len(df), "tabla4": t4,
           "publicado": PUBLICADO, "veredicto": v}
    salida = pathlib.Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "2a_control.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    buf = io.StringIO()
    buf.write(f"2A · {out['periodo'][0]} → {out['periodo'][1]}, {out['meses']} meses\n")
    for col in FACTORES:
        r, p = t4[col], PUBLICADO[col]
        celdas = " · ".join(f"{k} {r['coef'][k]:+.2f} ({r['t'][k]:+.2f}) [{p[k][0]:+.2f}]" for k in p)
        buf.write(f"{col}: {celdas} · R² aj. {r['r2_ajustado']:.2f}\n")
    buf.write(f"veredicto: {json.dumps(v, ensure_ascii=False)}\n")
    print(buf.getvalue(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
