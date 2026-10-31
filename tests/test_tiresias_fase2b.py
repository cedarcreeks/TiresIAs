"""Tests de tiresias.fase2b: las ventanas de precios de cada CUSIP, los registros del FTD y el pedido por lotes."""
import datetime as dt

import pandas as pd

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
