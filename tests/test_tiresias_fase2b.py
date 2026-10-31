"""Tests de tiresias.fase2b: las ventanas de precios de cada CUSIP, los registros del FTD y el pedido por lotes."""
import datetime as dt

import pandas as pd
import pytest

from tiresias import fase2b as F
from tiresias import gestores as G

D = dt.date


def test_la_ventana_va_del_mes_previo_a_la_entrada_hasta_el_ultimo_mes_posible():
    pos = pd.DataFrame({"cusip": ["C1", "C1", "C2"],
                        "presentado": pd.to_datetime(["2016-02-14", "2016-05-15", "2016-02-14"])})
    v = F.ventanas(pos, fin_datos=D(2016, 7, 15))
    assert v["C2"] == (D(2016, 2, 29) - F.MARGEN, D(2016, 6, 30))      # entra en marzo, como mucho 4 meses
    assert v["C1"] == (D(2016, 2, 29) - F.MARGEN, D(2016, 7, 15))      # la segunda entrada (junio) se corta en los datos
    assert G.MESES_MAX == 4


def test_registros_separa_simbolos_y_precios_y_quita_los_nan():
    ftd = pd.DataFrame({"cusip": ["A", "A", "B"], "simbolo": ["X", "XX", "Y"],
                        "fecha": pd.to_datetime(["2016-03-01", "2016-01-04", "2016-01-04"]),
                        "precio": [10.0, float("nan"), 5.0]})
    simb, prec = F.registros(ftd)
    assert simb["A"] == [(D(2016, 1, 4), "XX"), (D(2016, 3, 1), "X")]
    assert prec["A"] == [(D(2016, 3, 1), 10.0)] and prec["B"] == [(D(2016, 1, 4), 5.0)]


def test_el_pedido_agrupa_por_inicio_y_su_id_sale_del_contenido():
    # los nombres, al revés que las fechas: el lote sale por fecha de inicio, no por nombre
    rangos = {f"S{119 - i:03d}": (D(2016, 1, 1) + dt.timedelta(days=i), D(2017, 1, 1)) for i in range(120)}
    p = F.pedido(rangos, cusips=[f"C{i}" for i in range(150)])
    assert [len(b["simbolos"]) for b in p["barras"]] == [50, 50, 20]
    assert p["barras"][0]["desde"] == "2016-01-01" and p["barras"][1]["desde"] == "2016-02-20"
    assert p["barras"][0]["simbolos"][0] == "S119" and p["barras"][0]["hasta"] == "2017-01-01"
    assert len({b["id"] for b in p["barras"]}) == 3
    assert [len(a.get("cusips", a.get("simbolos"))) for a in p["acciones"]] == [100, 50, 100, 20]
    assert F.pedido(rangos, cusips=[f"C{i}" for i in range(150)]) == p                   # mismo plan, mismos id
    otro = dict(rangos, S119=(D(2015, 6, 1), D(2017, 1, 1)))
    assert F.pedido(otro, cusips=[])["barras"][0]["id"] != p["barras"][0]["id"]


def test_cobertura_de_la_traduccion_por_valor_y_trimestre():
    pos = pd.DataFrame({"cik": ["1", "1", "2"], "cusip": ["A", "B", "A"], "valor": [3.0, 1.0, 4.0],
                        "presentado": pd.to_datetime(["2016-02-14", "2016-02-14", "2016-05-15"])})
    trad = G.Traductor(pd.DataFrame({"cusip": ["A"], "simbolo": ["AA"], "fecha": pd.to_datetime(["2016-01-04"])}))
    c = F.cobertura_traduccion(pos, trad)
    assert list(c["cobertura"]) == [0.75, 1.0] and list(c["gestores"]) == [1, 1]


def _serie(ini, precios):
    fs, f = [], ini
    while len(fs) < len(precios):
        if f.weekday() < 5:
            fs.append(f)
        f += dt.timedelta(days=1)
    return {x: (p, 100) for x, p in zip(fs, precios)}


def test_revisar_da_un_estado_por_caso_y_pide_lo_que_falta():
    ini, fin = D(2016, 2, 19), D(2016, 6, 30)
    v = {c: (ini, fin) for c in ("C1", "C2", "C3", "C4", "C5")}
    simb = {"C1": [(D(2016, 1, 4), "BRKB")], "C2": [(D(2016, 1, 4), "X")], "C3": [(D(2016, 1, 4), "YY")],
            "C4": [(D(2016, 1, 4), "W")], "C5": [(D(2016, 1, 4), "OLD")]}
    s = _serie(D(2016, 2, 22), [100.0 + k for k in range(60)])               # 22-feb ... 13-may
    f_reg = sorted(s)[10]                                                    # un registro FTD con su día previo
    p_prev = s[sorted(s)[9]][0]
    prec = {"C1": [(f_reg, p_prev)], "C2": [(f_reg, p_prev)], "C3": [(f_reg, p_prev * 2)], "C4": []}
    tal = {"X": s, "YY": s, "W": s, "OLD": s}
    acciones = {"name_changes": [{"id": "n", "old_cusip": "C5", "old_symbol": "OLD", "new_symbol": "NEW",
                                  "process_date": "2016-04-01"}],
                "spin_offs": [{"id": "s", "source_cusip": "C2", "source_symbol": "X", "new_symbol": "SPUN",
                               "ex_date": "2016-03-15"}]}
    pedidos = {k: (ini - F.MARGEN, fin) for k in ("BRKB", "X", "YY", "W", "OLD")}
    r = F.revisar(v, simb, prec, tal, acciones, pedidos)
    # C1: BRKB no tiene barras → se pide BRK.B; C3: YY no cuadra → se pide Y.Y; C5: NEW, sin bajar aún
    assert r["estado"] == {"C1": "pendiente", "C2": "ok", "C3": "pendiente", "C4": "sin contraste", "C5": "pendiente"}
    assert set(r["rangos_pendientes"]) == {"BRK.B", "Y.Y", "NEW"}
    assert r["tramos"]["C5"] == [("OLD", ini, D(2016, 3, 31)), ("NEW", D(2016, 4, 1), fin)]
    assert r["ajenos"] == {("SPUN", D(2016, 3, 15))}
    # segunda pasada: BRK.B cuadra; Y.Y se pidió y no trae nada; NEW ya está
    pedidos2 = dict(pedidos, **{k: (ini - F.MARGEN, fin) for k in ("BRK.B", "Y.Y", "NEW")})
    r2 = F.revisar(v, simb, prec, dict(tal, **{"BRK.B": s, "NEW": s}), acciones, pedidos2)
    assert r2["estado"] == {"C1": "ok", "C2": "ok", "C3": "no cuadra", "C4": "sin contraste", "C5": "sin contraste"}
    assert r2["tramos"]["C1"] == [("BRK.B", ini, fin)] and r2["rangos_pendientes"] == {}
    # una forma con punto que existe pero no cuadra no se toma
    r3 = F.revisar(v, simb, prec, dict(tal, **{"BRK.B": _serie(D(2016, 2, 22), [5.0] * 60), "NEW": s}), acciones,
                   pedidos2)
    assert r3["estado"]["C1"] == "no cuadra" and r3["tramos"]["C1"] == [("BRKB", ini, fin)]


def test_de_punta_a_punta_con_datos_sinteticos(tmp_path):
    """FTD + 13F + una pasada de precios (escrita con descarga_2b y un Alpaca de mentira) → rentabilidades por CUSIP →
    juicio. Un CUSIP cuyo FTD no cuadra con el precio queda fuera; el resto entra y hay veredicto."""
    import json
    import numpy as np
    from tiresias import descarga_2b as X
    rng = np.random.default_rng(7)
    dias = pd.bdate_range("2016-01-04", "2020-12-31")
    cusips = [f"C{j:02d}" for j in range(14)]
    precios = {c: 50 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, len(dias)))) for c in cusips}
    simbolo = {c: "S" + c[1:] for c in cusips}
    precios_ftd = {c: p.copy() for c, p in precios.items()}
    precios_ftd["C13"] = precios_ftd["C13"] * 3                              # el FTD de C13 no cuadra
    filas = []
    for c in cusips:
        for k in range(1, len(dias), 15):
            filas.append((c, simbolo[c], dias[k], float(precios_ftd[c][k - 1])))
    ftd = pd.DataFrame(filas, columns=["cusip", "simbolo", "fecha", "precio"])
    pos = []
    for g in range(12):
        for p in pd.date_range("2016-02-01", "2020-08-01", freq="3MS") + pd.Timedelta(days=13):
            for j, c in enumerate(cusips[:12] if g % 2 else cusips[2:]):
                pos.append({"cik": str(g), "presentado": p, "periodo": p - pd.offsets.MonthEnd(2), "cusip": c,
                            "valor": float(1 + (j + g) % 5), "accesion": f"{g}-{p.date()}", "emisor": "x"})
    pos = pd.DataFrame(pos)
    barras = {simbolo[c]: {d.date(): (float(x), 1000) for d, x in zip(dias, precios[c])} for c in cusips}

    class Falso:
        sin_datos = []
        def barras(self, simbolos, desde, hasta, ajuste, asof=None, solos=None):
            a, h = dt.date.fromisoformat(desde), dt.date.fromisoformat(hasta)
            return {s: {f: x for f, x in barras[s].items() if a <= f <= h} for s in simbolos if s in barras}
        def acciones(self, desde, hasta, cusips=(), simbolos=()):
            return {}
    simb, _ = F.registros(ftd)
    from tiresias import precios as P
    _, rangos = P.plan(F.ventanas(pos, D(2020, 12, 31)), simb, {})
    ped = F.pedido(rangos, cusips)
    d1 = tmp_path / "p1"
    X.ejecutar(ped, d1, Falso())
    (d1 / "pedido.json").write_text(json.dumps(ped))
    r = F.rentabilidades_por_cusip(pos, ftd, [d1], D(2020, 12, 31))
    # C13 no cuadra con su símbolo: se pide la forma con punto, y sólo eso
    assert [b["simbolos"] for b in r["falta"]["barras"]] == [["S1.3"]] and r["estado"]["C00"] == "ok"
    d2 = tmp_path / "p2"
    X.ejecutar(r["falta"], d2, Falso())                                      # la forma con punto no existe
    (d2 / "pedido.json").write_text(json.dumps(r["falta"]))
    r = F.rentabilidades_por_cusip(pos, ftd, [d1, d2], D(2020, 12, 31))
    assert "falta" not in r and r["estado"]["C13"] == "no cuadra" and r["estado"]["C00"] == "ok"
    assert "C13" not in r["rent"].columns and set(r["rent"].columns) == set(cusips) - {"C13"}
    meses = pd.date_range("2016-01-31", "2020-12-31", freq="ME")
    Fac = pd.DataFrame(rng.normal(0.005, 0.03, (len(meses), 6)), index=meses, columns=G.SEIS)
    Fac["RF"] = 0.001
    sp = pd.Series(rng.normal(0.008, 0.04, len(meses)), index=meses)
    j = F.juicio(pos, r["rent"], Fac, sp, reps=5)
    assert not j["parada"]["para"] and j["parada"]["bajos"] == 0
    assert j["receta"].index.min() >= pd.Timestamp("2019-04-30") and len(j["placebo"]) == 5
    assert set(j["veredicto"]["criterios"]) == {"1_frente_al_sp500", "2_en_las_dos_mitades", "3_sobre_el_placebo_p95",
                                                "4_sobre_todos_los_gestores"} and j["veredicto"]["de"] == 4
    # los factores acaban antes que los precios (AQR, como en los datos reales): el juicio no se cae
    j2 = F.juicio(pos, r["rent"], Fac.loc[:"2020-09-30"], sp, reps=2)
    assert j2["receta"].index.max() <= pd.Timestamp("2020-09-30")
    # sin precio para casi nada, para antes de elegir a nadie
    j3 = F.juicio(pos, r["rent"][["C00", "C01"]], Fac, sp, reps=2)
    assert j3["parada"]["para"] and "receta" not in j3


def test_contraste_con_los_corporate_actions():
    simb = {"A": [(D(2016, 1, 4), "BRKB")], "B": [(D(2016, 1, 4), "OLD"), (D(2016, 6, 1), "NEW")],
            "C": [(D(2016, 1, 4), "X")]}
    acc = {"cash_dividends": [
        {"cusip": "A", "symbol": "BRK.B", "ex_date": "2016-03-01"},           # coincide sin el punto
        {"cusip": "B", "symbol": "NEW", "ex_date": "2016-05-20"},             # cerca del cambio: no se compara
        {"cusip": "B", "symbol": "NEW", "ex_date": "2016-09-01"},             # coincide
        {"cusip": "C", "symbol": "Y", "ex_date": "2016-03-01"},               # discrepa
        {"cusip": None, "symbol": "X", "ex_date": "2016-03-01"},              # sin CUSIP: no se compara
        {"cusip": "C", "symbol": "X", "ex_date": "2015-12-01"}],              # antes del primer FTD: no
        "cash_mergers": [{"acquiree_cusip": "A", "acquiree_symbol": "BRKB", "effective_date": "2016-04-01"}]}
    r = F.contraste_ca(acc, simb)
    assert r["comparados"] == 4 and r["coinciden"] == 3 and r["discrepan"] == {"C": [(D(2016, 3, 1), "Y", "X")]}


def test_mensual_yahoo_usa_el_ajustado_y_quita_el_primer_mes(tmp_path):
    import json
    ts = [int(pd.Timestamp(x, tz="UTC").timestamp()) for x in ("2020-01-30", "2020-01-31", "2020-02-28", "2020-03-31")]
    d = {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": [1, 1, 1, 1]}],
                                                              "adjclose": [{"adjclose": [99.0, 100.0, 110.0, None]}]}}]}}
    (tmp_path / "x.json").write_text(json.dumps(d))
    m = F.mensual_yahoo(tmp_path / "x.json")
    assert list(m.index) == [pd.Timestamp("2020-02-29")] and m.iloc[0] == pytest.approx(0.10)   # marzo, sin cierre


def test_resumen_de_un_juicio_que_para_no_trae_metricas():
    j = {"parada": {"para": True, "trimestres": 4, "bajos": 2,
                    "por_trimestre": pd.Series([0.9, 0.5], index=pd.PeriodIndex(["2016Q1", "2016Q2"], freq="Q"))}}
    r = F.resumen_juicio(j, pd.DataFrame({"RF": []}), pd.Series(dtype=float))
    assert r["parada"] == {"para": True, "trimestres": 4, "bajos": 2} and "veredicto" not in r
    assert r["cobertura_por_trimestre"] == {"2016Q1": 0.9, "2016Q2": 0.5}
