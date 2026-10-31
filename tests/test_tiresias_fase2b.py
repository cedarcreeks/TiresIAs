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
