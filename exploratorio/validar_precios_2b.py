# -*- coding: utf-8 -*-
"""VALIDACIÓN (31-oct) de tiresias.precios antes de bajar los precios de 2B: 27 valores, 2016-2026, frente a Yahoo y a la
verdad de los spin-offs (docs/RESULTADOS_FASE2B.md, «Los precios»).

    APCA_API_KEY_ID=… APCA_API_SECRET_KEY=… python exploratorio/validar_precios_2b.py bajar --destino DIR
    python exploratorio/validar_precios_2b.py yahoo --destino DIR
    PYTHONPATH=. python exploratorio/validar_precios_2b.py comparar --datos DIR

`bajar` sólo usa la biblioteca estándar y tiresias.precios (corre donde estén las claves); `comparar`, pandas.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from tiresias import precios as P  # noqa: E402

SIMBOLOS = ("AAPL EW ISRG NVDA TSLA GOOGL AMZN WMT CMG AVGO GE JNJ MMM T IBM PFE KO XOM MSFT JPM DIS META BRK.B HD PG "
            "UNH V").split()
DESDE, HASTA = "2015-12-01", "2026-10-30"
# los spin-offs de la muestra, con la verdad: (fuente, escindida, mes)
SPINS = [("PFE", "VTRS", "2020-11"), ("T", "WBD", "2022-04"), ("GE", "GEHC", "2023-01"), ("GE", "GEV", "2024-04"),
         ("MMM", "SOLV", "2024-04"), ("GE", "WAB", "2019-02"), ("IBM", "KD", "2021-11")]
KD = ("IBM", "KD", "2021-11-04", 0.2)        # el spin-off de IBM, que no está en los corporate actions de Alpaca


def bajar(destino: pathlib.Path):
    a = P.Alpaca(os.environ["APCA_API_KEY_ID"], os.environ["APCA_API_SECRET_KEY"])
    lista = SIMBOLOS + ["FB"]
    datos = {"all": a.barras(lista, DESDE, HASTA, "all"), "raw": a.barras(lista, DESDE, HASTA, "raw"),
             "tal_cual": a.barras(lista, DESDE, HASTA, "raw", asof="-"),
             "acciones": a.acciones(DESDE, HASTA, simbolos=SIMBOLOS)}
    escindidas = {}
    for d in datos["acciones"].get("spin_offs", []) + [{"new_symbol": KD[1], "ex_date": KD[2]}]:
        b = a.barras([d["new_symbol"]], d["ex_date"], d["ex_date"], "raw", asof="-").get(d["new_symbol"], {})
        if b:
            (f, (c, _)), = b.items()
            escindidas[d["new_symbol"] + "|" + f.isoformat()] = c
    destino.mkdir(parents=True, exist_ok=True)
    ser = {m: {s: [(f.isoformat(), c, v) for f, (c, v) in sorted(x.items())] for s, x in datos[m].items()}
           for m in ("all", "raw", "tal_cual")}
    json.dump({**ser, "acciones": datos["acciones"], "escindidas": escindidas}, open(destino / "alpaca.json", "w"))
    print(f"{a.peticiones} peticiones; barras: " + ", ".join(f"{m} {sum(len(x) for x in ser[m].values())}" for m in ser)
          + f"; sin datos ni pedidos solos: {a.sin_datos}")


def yahoo(destino: pathlib.Path):
    (destino / "yahoo").mkdir(parents=True, exist_ok=True)
    p1 = int(dt.datetime(2015, 12, 1, tzinfo=dt.timezone.utc).timestamp())
    p2 = int(dt.datetime(2026, 10, 31, tzinfo=dt.timezone.utc).timestamp())
    for s in SIMBOLOS:
        t = s.replace(".", "-")
        url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{t}?period1={p1}&period2={p2}&interval=1d"
               "&events=div%2Csplit&includeAdjustedClose=true")    # range=max da barras mensuales
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        (destino / "yahoo" / f"{t}.json").write_bytes(urllib.request.urlopen(req, timeout=30).read())
        time.sleep(2)


def comparar(datos: pathlib.Path):
    import pandas as pd
    A = json.load(open(datos / "alpaca.json"))
    D = dt.date.fromisoformat
    series = {m: {s: {D(f): (c, v) for f, c, v in xs} for s, xs in A[m].items()} for m in ("all", "raw", "tal_cual")}
    cus = {}
    for v in A["acciones"].values():
        for d in v:
            if d.get("cusip") and d.get("symbol"):
                cus.setdefault(d["symbol"], d["cusip"])
    cus = {s: cus.get(s, "SIN-" + s) for s in SIMBOLOS}
    ini, fin = dt.date(2015, 12, 21), dt.date(2026, 9, 30)
    ventanas = {c: (ini, fin) for c in cus.values()}
    registros = {c: [(dt.date(2015, 12, 1), "FB" if s == "META" else s)] for s, c in cus.items()}
    cambios = {c: P.cambios_de_nombre(P.acciones_de(c, A["acciones"])) for c in cus.values()}
    por_cusip, _ = P.plan(ventanas, registros, cambios)
    acciones = {c: P.acciones_de(c, A["acciones"], por_cusip.get(c, [])) for c in cus.values()}
    ajenos = {(k.split("|")[0], D(k.split("|")[1])): c for k, c in A["escindidas"].items()}

    def yahoo_m(s):
        d = json.load(open(datos / "yahoo" / f"{s.replace('.', '-')}.json"))["chart"]["result"][0]
        x = pd.Series(d["indicators"]["adjclose"][0]["adjclose"],
                      index=pd.to_datetime(d["timestamp"], unit="s").normalize())
        return x.resample("ME").last().pct_change().loc["2016-01-31":"2026-09-30"]

    meses_spin = {}
    for src, _, mes in SPINS:
        meses_spin.setdefault(src, set()).add(mes)
    out_alpaca = None
    for nombre, ser in (("Alpaca", series), ("reconstruido (forzado)", {"all": {}, "raw": {}, "tal_cual": series["tal_cual"]})):
        out, caminos = P.rentabilidades(por_cusip, ser, acciones, ajenos, ventanas)
        out_alpaca = out_alpaca or out
        n, malos, meds = 0, 0, []
        for s, c in cus.items():
            m = pd.Series({pd.Timestamp(k): v for k, v in out.get(c, {}).items()}).sort_index()
            dd = (m - yahoo_m(s)).dropna() * 100
            dd = dd[~dd.index.strftime("%Y-%m").isin(meses_spin.get(s, set()))]
            n, malos = n + len(dd), malos + int((dd.abs() > 1).sum())
            meds.append(dd.abs().median())
        print(f"camino {nombre:24s} {pd.Series(caminos).value_counts().to_dict()}  meses-valor {n}, "
              f"mediana de |Δ| {pd.Series(meds).median():.4f} pp, meses > 1 pp: {malos}")

    # la verdad de cada spin-off: el día ex desde el precio sin ajustar, más lo escindido
    tasas = {(d["source_symbol"], d["new_symbol"]): float(d["new_rate"]) for d in A["acciones"].get("spin_offs", [])}
    tasas[KD[:2]] = KD[3]
    print("spin-off      módulo   verdad   Alpaca    Yahoo")
    for src, new, mes in SPINS:
        f_ex = next(D(k.split("|")[1]) for k in A["escindidas"] if k.startswith(new + "|"))
        raw = pd.Series({pd.Timestamp(f): c for f, c, _ in A["raw"][src]}).sort_index()
        todo = pd.Series({pd.Timestamp(f): c for f, c, _ in A["all"][src]}).sort_index()
        r = todo.pct_change()
        ex = pd.Timestamp(f_ex)
        prev = raw.index[raw.index.get_loc(ex) - 1]
        r.loc[ex] = (raw.loc[ex] + tasas[(src, new)] * A["escindidas"][f"{new}|{f_ex}"]) / raw.loc[prev] - 1
        k = pd.Timestamp(mes) + pd.offsets.MonthEnd(0)
        verdad = (1 + r[(r.index > k - pd.offsets.MonthEnd(1)) & (r.index <= k)]).prod() - 1
        alp = todo.resample("ME").last().pct_change().loc[k]
        print(f"{src}/{new:5s}  {out_alpaca[cus[src]][k.date()] * 100:8.2f} {verdad * 100:8.2f} {alp * 100:8.2f} "
              f"{yahoo_m(src).loc[k] * 100:8.2f}")

    # control negativo con barras reales: el ETF de Roundhill sin su paso a METV
    mal = [("META", D("2021-07-01"), D("2022-08-31"), series["all"]["META"], series["raw"]["META"],
            series["tal_cual"]["META"])]
    print("control: el ETF con el tramo mal →", P.serie_diaria(mal, {}, {}, D("2022-08-31"))[1])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["bajar", "yahoo", "comparar"])
    ap.add_argument("--destino", type=pathlib.Path)
    ap.add_argument("--datos", type=pathlib.Path)
    a = ap.parse_args()
    {"bajar": lambda: bajar(a.destino), "yahoo": lambda: yahoo(a.destino), "comparar": lambda: comparar(a.datos)}[a.accion]()
