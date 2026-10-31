"""Tests de tiresias.congreso: el índice del Clerk y la descarga reanudable de las declaraciones."""
import io

import pytest
import urllib.error
import zipfile

from tiresias import congreso as C

CAB = "Prefix\tLast\tFirst\tSuffix\tFilingType\tStateDst\tYear\tFilingDate\tDocID\n"


def test_el_indice_solo_trae_las_declaraciones_de_operaciones(tmp_path):
    f = tmp_path / "2024FD.zip"
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("2024FD.txt", CAB + "Hon.\tAllen\tRichard W.\t\tP\tGA12\t2024\t1/11/2024\t20024277\n"
                                       "Hon.\tOtro\tX\t\tO\tCA01\t2024\t5/15/2024\t10059999\n")
    r = C.indice(f)
    assert r == [{"apellido": "Allen", "nombre": "Richard W.", "distrito": "GA12", "presentado": "1/11/2024",
                  "docid": "20024277", "anio": "2024"}]


class _Red:
    def __init__(self, respuestas):
        self.respuestas, self.pedidas = list(respuestas), []

    def __call__(self, req):
        self.pedidas.append(req.full_url)
        x = self.respuestas.pop(0)
        if isinstance(x, int):
            raise urllib.error.HTTPError(req.full_url, x, "x", {}, io.BytesIO(b""))
        return x


def test_la_descarga_reanuda_y_no_repite_un_404(tmp_path):
    ptrs = [{"docid": "1", "anio": "2024"}, {"docid": "2", "anio": "2024"}]
    red = _Red([b"%PDF-1", 404])
    r = C.descargar(ptrs, tmp_path, abrir=red, dormir=lambda _: None)
    assert r == {"bajados": 1, "ya_estaban": 0, "faltan": 1}
    assert (tmp_path / "2024" / "1.pdf").read_bytes() == b"%PDF-1" and red.pedidas[0].endswith("/ptr-pdfs/2024/1.pdf")
    red2 = _Red([])
    assert C.descargar(ptrs, tmp_path, abrir=red2, dormir=lambda _: None) == {"bajados": 0, "ya_estaban": 2, "faltan": 1}
    assert red2.pedidas == [] and not list(tmp_path.rglob("*.tmp"))


# Un texto sintético con el formato de `pdftotext -layout` de una PTR electrónica (sin datos reales en el repo).
PTR = """
ID         Owner Asset                                   Transaction Date                 Notification Amount
           SP         Acme Corporation (ACME) [ST]            S                 12/21/2023 01/08/2024             $1,001 - $15,000
                      F      S       : New
           JT         Beta Holdings Inc. (BETA) P                           12/14/2023 01/08/2024             $50,001 -
                      [ST]                                                                                            $100,000
                      Gamma Corp. Class B
                      (GAM.B) [ST]                            S (partial)        11/02/2023 01/08/2024             $15,001 -
           SP         Some Bond Fund [MF]                     P                 12/01/2023 01/08/2024             $1,001 - $15,000
"""


def test_las_operaciones_de_una_ptr_con_lineas_partidas():
    ops = C.operaciones(PTR)
    assert [o["ticker"] for o in ops] == ["ACME", "BETA", "GAM.B", None]
    assert [o["tipo"] for o in ops] == ["S", "P", "S", "P"]
    assert [o["clase"] for o in ops] == ["ST", "ST", "ST", "MF"]                 # el [ST] partido, a la línea de abajo
    assert ops[1]["importe_min"] == 50001 and ops[1]["importe_max"] == 100000    # el máximo partido sale del tramo
    assert ops[0]["fecha_operacion"] == "12/21/2023" and ops[0]["fecha_notificacion"] == "01/08/2024"


# El formato de 2016: mayúsculas rotas por la fuente, tipo en minúscula, días de una cifra, símbolo partido abajo.
PTR_2016 = """
           JT       aT&T Inc. (T)                               P                 10/10/2016 10/10/2016           $1,001 - $15,000
                    FIlINg sTaTus: New
           JT       Baxter International Inc. (BaX)             s                 08/31/2016 08/31/2016           $1,001 - $15,000
                    lee Enterprises, Incorporated (lEE)         s                 09/7/2016      09/7/2016        $1,001 - $15,000
           JT       Twenty-First Century Fox, Inc. - Class a P                    08/31/2016 08/31/2016           $1,001 - $15,000
                    (FOXa)
           SP       Omega Inc. (OMG) [OP]                       S (partial)       01/05/2016 01/20/2016           $15,001 - $50,000
"""


def test_el_formato_de_2016():
    ops = C.operaciones(PTR_2016)
    assert [o["ticker"] for o in ops] == ["T", "BAX", "LEE", "FOXA", "OMG"]
    assert [o["tipo"] for o in ops] == ["P", "S", "S", "P", "S"]
    assert ops[2]["fecha_operacion"] == "09/7/2016" and ops[4]["clase"] == "OP"


def test_extraer_usa_la_fecha_de_presentacion_y_cuenta_lo_que_no_se_lee(tmp_path):
    (tmp_path / "2016").mkdir()
    for d in ("1", "2"):
        (tmp_path / "2016" / f"{d}.pdf").write_bytes(b"%PDF")
    ptrs = [{"apellido": "Brooks", "nombre": "Mo", "distrito": "AL05", "presentado": "11/15/2016", "docid": "1", "anio": "2016"},
            {"apellido": "X", "nombre": "Y", "distrito": "CA01", "presentado": "11/15/2016", "docid": "2", "anio": "2016"},
            {"apellido": "Z", "nombre": "W", "distrito": "TX01", "presentado": "11/15/2016", "docid": "3", "anio": "2016"}]
    leer = lambda f: PTR_2016 if f.stem == "1" else ""                      # el 2 es papel escaneado; el 3 no está
    filas, inf = C.extraer(ptrs, tmp_path, leer=leer)
    assert inf == {"con_texto": 1, "sin_texto": 1, "sin_pdf": 1} and len(filas) == 5
    import datetime as dt
    assert {f["presentado"] for f in filas} == {dt.date(2016, 11, 15)} and filas[0]["congresista"] == "Brooks, Mo (AL05)"
    c = C.compras(filas)
    assert [x["ticker"] for x in c] == ["T", "FOXA"]                         # ni ventas ni la opción [OP]


def _r(desde, n, x):
    import datetime as dt
    out, f = {}, desde
    while len(out) < n:
        if f.weekday() < 5:
            out[f] = x
        f += dt.timedelta(days=1)
    return out


def test_la_posicion_entra_el_dia_despues_de_presentarse_y_vive_182_dias():
    import datetime as dt
    r = _r(dt.date(2020, 1, 2), 300, 0.001)
    p = C.posicion({"congresista": "A", "presentado": dt.date(2020, 1, 6), "importe_min": 15001}, r)
    assert p["entrada"] == dt.date(2020, 1, 7) and min(p["r"]) == dt.date(2020, 1, 8)     # sin la del día de entrada
    assert max(p["r"]) <= dt.date(2020, 1, 7) + dt.timedelta(days=182) and p["peso"] == (15001 + 50000) / 2
    assert p["total"] == pytest.approx(1.001 ** len(p["r"]) - 1)
    assert C.posicion({"congresista": "A", "presentado": dt.date(2030, 1, 1), "importe_min": None}, r) is None


def test_el_historial_solo_usa_tenencias_acabadas():
    import datetime as dt
    q = dt.date(2021, 12, 31)
    def pos(m, presentado, total):
        return {"miembro": m, "presentado": presentado, "salida": presentado + dt.timedelta(days=183), "total": total}
    ps = [pos("A", dt.date(2021, 3, 1), 0.1) for _ in range(5)] + [pos("A", dt.date(2021, 9, 1), 9.9)]   # acaba en 2022
    ps += [pos("B", dt.date(2021, 2, 1), 0.2) for _ in range(4)]                                         # sólo 4
    ps += [pos("C", dt.date(2019, 6, 1), 0.3) for _ in range(5)]                                         # fuera de 24 meses
    assert C.historial(ps, q) == {"A": pytest.approx(0.1)}


def test_la_cartera_copia_solo_a_los_elegidos_del_trimestre_anterior():
    import datetime as dt
    d1, d2 = dt.date(2021, 4, 5), dt.date(2021, 4, 6)
    ps = [{"miembro": "A", "presentado": dt.date(2021, 4, 1), "peso": 3.0, "r": {d1: 0.01, d2: 0.02}},
          {"miembro": "B", "presentado": dt.date(2021, 4, 1), "peso": 1.0, "r": {d1: 0.05}},
          {"miembro": "A", "presentado": dt.date(2021, 2, 1), "peso": 1.0, "r": {d1: -0.01}}]   # elegido en 2020-12? no
    s = C.cartera_diaria(ps, {dt.date(2021, 3, 31): {"A", "B"}})
    assert s[d1] == pytest.approx((3 * 0.01 + 1 * 0.05) / 4) and s[d2] == pytest.approx(0.02)
    s2 = C.cartera_diaria(ps, {dt.date(2021, 3, 31): {"A", "B"}}, ponderar=False)
    assert s2[d1] == pytest.approx((0.01 + 0.05) / 2)


def test_ventanas_de_precio_por_simbolo():
    import datetime as dt
    c = [{"ticker": "A", "presentado": dt.date(2020, 1, 15)}, {"ticker": "A", "presentado": dt.date(2021, 6, 1)},
         {"ticker": "B", "presentado": dt.date(2022, 3, 1)}]
    v = C.ventanas_precios(c, fin=dt.date(2022, 6, 30))
    assert v["A"] == (dt.date(2020, 1, 5), dt.date(2021, 6, 1) + dt.timedelta(days=192))
    assert v["B"] == (dt.date(2022, 2, 19), dt.date(2022, 6, 30))                 # nunca después del último día cerrado


def test_rentabilidades_diarias_con_la_comprobacion_de_entidad():
    import datetime as dt
    from tiresias import precios as P
    f = [dt.date(2020, 1, 2) + dt.timedelta(days=k) for k in range(5)]
    b = {d: (100.0 + k, 10) for k, d in enumerate(f)}
    otra = {d: (5.0, 10) for d in f}                                        # el símbolo hoy es de otra empresa
    series = {"all": {"A": b, "Z": otra}, "raw": {"A": b, "Z": otra}, "tal_cual": {"A": b, "Z": b}}
    r, cam = C.rentabilidades_diarias({"A": (f[0], f[-1]), "Z": (f[0], f[-1])}, series, P.IndiceAcciones({}))
    assert cam == {"A": "alpaca", "Z": "reconstruida"} and r["A"][f[1]] == pytest.approx(0.01)


def test_juicio_3c_con_un_congresista_que_acierta_y_otros_al_azar():
    """Sintético: el miembro «Bueno» compra lo que sube; el resto, ruido. El decil superior debe ser él y ganar."""
    import datetime as dt
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(3)
    dias = pd.bdate_range("2016-01-04", "2022-12-30").date
    posiciones = []
    for m in ["Bueno"] + [f"M{i}" for i in range(19)]:
        for k in range(40):
            pres = dias[rng.integers(0, len(dias) - 200)]
            ent = [d for d in dias if d > pres][0]
            r = {d: (0.002 if m == "Bueno" else rng.normal(0, 0.01)) for d in dias if ent < d <= ent + dt.timedelta(days=182)}
            posiciones.append({"miembro": m, "presentado": pres, "entrada": ent, "salida": ent + dt.timedelta(days=182),
                               "peso": 1.0, "r": r, "total": float(np.prod([1 + x for x in r.values()]) - 1)})
    trimestres = [C.fin_trimestre(d) for d in pd.date_range("2018-03-31", "2022-09-30", freq="QE").date]
    meses = pd.date_range("2016-01-31", "2022-12-31", freq="ME")
    sp = pd.Series(0.005, index=meses) + pd.Series(rng.normal(0, 0.03, len(meses)), index=meses)
    rf = pd.Series(0.001, index=meses)
    nanc = sp.loc["2021-01-31":]
    j = C.juicio(posiciones, trimestres, sp, rf, nanc, reps=20)
    assert all("Bueno" in s for s in [C.decil_superior(C.historial(posiciones, q)) for q in trimestres[2:]])
    assert j["copia"]["sharpe"] > j["placebo_p95"] and j["criterios"]["2_sobre_el_placebo_p95"]
    # el placebo es elegir al azar: 20 carteras, con una mediana de ruido (no un valor fijo ni absurdo)
    assert j["placebo_n"] == 20 and -2 < j["placebo_mediana"] < j["copia"]["sharpe"]
    assert set(j["criterios"]) == {"1_frente_al_sp500_en_las_dos_mitades", "2_sobre_el_placebo_p95", "3_sobre_nanc"}
