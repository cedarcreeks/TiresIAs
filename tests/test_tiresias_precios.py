"""Tests de tiresias.precios: los tramos de símbolo, la serie de cada CUSIP y su camino, lo mensual y la descarga."""
import datetime as dt
import io
import json
import urllib.error

import pytest

from tiresias import precios as P

D = dt.date


def _dias(ini, n):
    """n días hábiles (lunes a viernes) desde ini."""
    out, f = [], ini
    while len(out) < n:
        if f.weekday() < 5:
            out.append(f)
        f += dt.timedelta(days=1)
    return out


def _barras(fechas, cierres, volumen=1000):
    return {f: (c, volumen) for f, c in zip(fechas, cierres)}


# ── 1. tramos ────────────────────────────────────────────────────────────────
def test_tramos_toma_el_simbolo_anterior_y_abre_uno_por_cambio():
    reg = [(D(2021, 1, 15), "FB"), (D(2022, 6, 15), "META"), (D(2022, 7, 1), "META")]
    assert P.tramos(reg, D(2022, 3, 1), D(2022, 8, 31)) == [
        ("FB", D(2022, 3, 1), D(2022, 6, 14)), ("META", D(2022, 6, 15), D(2022, 8, 31))]


def test_vale_el_registro_anterior_mas_cercano():
    reg = [(D(2019, 1, 15), "VIEJO"), (D(2021, 1, 15), "FB")]
    assert P.tramos(reg, D(2022, 3, 1), D(2022, 4, 30)) == [("FB", D(2022, 3, 1), D(2022, 4, 30))]


def test_el_cambio_de_nombre_da_el_dia_exacto():
    reg = [(D(2021, 1, 15), "FB"), (D(2022, 6, 15), "META")]
    assert P.tramos(reg, D(2022, 3, 1), D(2022, 8, 31), cambios=[(D(2022, 6, 9), "FB", "META")]) == [
        ("FB", D(2022, 3, 1), D(2022, 6, 8)), ("META", D(2022, 6, 9), D(2022, 8, 31))]
    # sin registro FTD del símbolo nuevo en la ventana, el cambio lo abre
    assert P.tramos([(D(2021, 1, 15), "FB")], D(2022, 3, 1), D(2022, 8, 31),
                    cambios=[(D(2022, 6, 9), "FB", "META")])[-1] == ("META", D(2022, 6, 9), D(2022, 8, 31))


def test_sin_registro_anterior_vale_el_primero_posterior_dentro_de_90_dias():
    assert P.tramos([(D(2022, 4, 1), "X")], D(2022, 3, 1), D(2022, 5, 31))[0][0] == "X"
    assert P.tramos([(D(2022, 7, 1), "X")], D(2022, 3, 1), D(2022, 9, 30)) == []


# ── 2. la serie diaria ───────────────────────────────────────────────────────
def test_con_la_misma_entidad_usa_el_ajuste_de_alpaca():
    f = _dias(D(2024, 1, 2), 5)
    raw = _barras(f, [100, 101, 99, 99, 100])
    todo = _barras(f, [98, 99, 97, 98, 99])             # ajustado por un dividendo el día 4
    r, camino, _ = P.serie_diaria([("X", f[0], f[-1], todo, raw, raw)], {}, {}, f[-1])
    assert camino == "alpaca"
    assert r[f[3]] == pytest.approx(98 / 97 - 1)        # la del ajuste, no la de 99/99


def test_una_caida_real_en_el_camino_validado_se_queda():
    """Descartar los desplomes de verdad sesgaría al alza: el guardián sólo actúa al reconstruir."""
    f = _dias(D(2024, 1, 2), 3)
    raw = _barras(f, [50, 18, 17])                       # −64 % en un día
    r, camino, _ = P.serie_diaria([("X", f[0], f[-1], raw, raw, raw)], {}, {}, f[-1])
    assert camino == "alpaca" and r[f[1]] == pytest.approx(18 / 50 - 1)


def test_entidad_distinta_reconstruye_con_dividendos_y_splits():
    f = _dias(D(2024, 1, 2), 4)
    tal_cual = _barras(f, [100, 102, 51, 50])
    otra = _barras(f, [10, 11, 12, 13])                  # el símbolo hoy es de otra empresa
    acc = {"forward_splits": [{"ex_date": f[2].isoformat(), "old_rate": 1, "new_rate": 2}],
           "cash_dividends": [{"ex_date": f[3].isoformat(), "rate": 0.5}]}
    r, camino, _ = P.serie_diaria([("X", f[0], f[-1], otra, otra, tal_cual)], acc, {}, f[-1])
    assert camino == "reconstruida"
    assert r[f[1]] == pytest.approx(0.02)
    assert r[f[2]] == pytest.approx(51 * 2 / 102 - 1)
    assert r[f[3]] == pytest.approx((50 + 0.5) / 51 - 1)


def test_las_barras_de_volumen_0_no_cuentan_y_un_empalme_se_descarta():
    """El caso de META con asof=2021-06-01: el ETF, relleno con volumen 0, y después otra empresa."""
    f = _dias(D(2022, 1, 26), 6)
    tal_cual = {f[0]: (12.28, 900), f[1]: (12.31, 800), f[2]: (12.31, 0), f[3]: (12.31, 0), f[4]: (184.0, 9000),
                f[5]: (175.6, 9000)}
    meta = _barras(f, [294.6, 301.7, 313.3, 319.0, 184.0, 175.6])
    r, camino, crudo = P.serie_diaria([("META", f[0], f[-1], meta, meta, tal_cual)], {}, {}, f[-1])
    assert f[2] not in crudo and f[3] not in crudo
    assert camino == "descartada" and r == {}


def test_un_salto_explicado_por_un_split_no_descarta_y_uno_mal_registrado_si():
    f = _dias(D(2024, 1, 2), 3)
    tal_cual = _barras(f, [100, 25, 26])
    acc = {"forward_splits": [{"ex_date": f[1].isoformat(), "old_rate": 1, "new_rate": 4}]}
    r, camino, _ = P.serie_diaria([("X", f[0], f[-1], {}, {}, tal_cual)], acc, {}, f[-1])
    assert camino == "reconstruida" and r[f[1]] == pytest.approx(0.0)
    mal = {"forward_splits": [{"ex_date": f[1].isoformat(), "old_rate": 1, "new_rate": 2}]}   # era 4 por 1
    assert P.serie_diaria([("X", f[0], f[-1], {}, {}, tal_cual)], mal, {}, f[-1])[1] == "descartada"


def test_el_spin_off_suma_lo_escindido_su_dia_ex():
    f = _dias(D(2024, 3, 27), 4)
    raw = _barras(f, [106, 107, 91, 92])
    todo = _barras(f, [106, 107, 91, 92])                # Alpaca sin ajustar el spin-off
    acc = {"spin_offs": [{"ex_date": f[2].isoformat(), "new_symbol": "SOLV", "new_rate": 0.25, "source_rate": 1}]}
    r, camino, _ = P.serie_diaria([("MMM", f[0], f[-1], todo, raw, raw)], acc, {("SOLV", f[2]): 69.1}, f[-1])
    assert camino == "alpaca"
    assert r[f[2]] == pytest.approx((91 + 0.25 * 69.1) / 107 - 1)
    assert r[f[3]] == pytest.approx(92 / 91 - 1)


def test_la_fusion_en_efectivo_cierra_en_lo_pagado():
    f = _dias(D(2022, 10, 24), 4)
    raw = _barras(f, [52, 53, 53.5, 53.7])
    acc = {"cash_mergers": [{"effective_date": "2022-10-28", "rate": 54.2}]}
    r, _, _ = P.serie_diaria([("TWTR", f[0], f[-1], raw, raw, raw)], acc, {}, D(2022, 12, 31))
    assert r[D(2022, 10, 28)] == pytest.approx(54.2 / 53.7 - 1)


def test_la_fusion_en_acciones_vale_las_del_comprador():
    f = _dias(D(2022, 2, 7), 4)
    raw = _barras(f, [190, 192, 195, 196])
    acc = {"stock_mergers": [{"effective_date": "2022-02-14", "acquirer_symbol": "AMD", "acquirer_rate": 1.7234,
                              "acquiree_rate": 1}]}
    r, _, _ = P.serie_diaria([("XLNX", f[0], f[-1], raw, raw, raw)], acc, {("AMD", D(2022, 2, 14)): 113.0},
                             D(2022, 3, 31))
    assert r[D(2022, 2, 14)] == pytest.approx(1.7234 * 113.0 / 196 - 1)


def test_sin_dos_cierres_no_hay_serie():
    f = _dias(D(2024, 1, 2), 1)
    assert P.serie_diaria([("X", f[0], f[0], {}, {}, _barras(f, [10]))], {}, {}, f[0])[1] == "sin datos"


# ── 3. lo mensual ────────────────────────────────────────────────────────────
def test_mensual_compone_y_empieza_en_el_primer_mes():
    r = {D(2024, 1, 30): 0.10, D(2024, 2, 1): 0.10, D(2024, 2, 2): -0.05, D(2024, 3, 1): 0.02}
    m = P.mensual(r, primer_mes=D(2024, 2, 29))
    assert list(m) == [D(2024, 2, 29), D(2024, 3, 31)]
    assert m[D(2024, 2, 29)] == pytest.approx(1.10 * 0.95 - 1)


def test_fin_de_mes():
    assert P.fin_de_mes(D(2024, 2, 10)) == D(2024, 2, 29) and P.fin_de_mes(D(2023, 12, 31)) == D(2023, 12, 31)


def test_la_cota_pesimista_solo_en_una_salida_sin_fusion_y_hundida():
    crudo = {D(2023, 1, 3): 100.0, D(2023, 3, 1): 40.0}
    m = {D(2023, 3, 31): -0.2}
    assert P.salida_pesimista(m, crudo, D(2023, 6, 30), con_fusion=False)[D(2023, 3, 31)] == -1.0
    assert P.salida_pesimista(m, crudo, D(2023, 6, 30), con_fusion=True) == m
    assert P.salida_pesimista(m, crudo, D(2023, 3, 5), con_fusion=False) == m          # la ventana acaba ahí
    sano = {D(2023, 1, 3): 100.0, D(2023, 3, 1): 60.0}
    assert P.salida_pesimista(m, sano, D(2023, 6, 30), con_fusion=False) == m


# ── 4. la descarga ───────────────────────────────────────────────────────────
class _Red:
    """Un `abrir` de mentira: devuelve respuestas en orden y apunta lo que se pidió."""

    def __init__(self, respuestas):
        self.respuestas, self.pedidas = list(respuestas), []

    def __call__(self, req):
        self.pedidas.append(req)
        x = self.respuestas.pop(0)
        if isinstance(x, int):
            raise urllib.error.HTTPError(req.full_url, x, "x", {}, io.BytesIO(b""))
        if isinstance(x, tuple):                                          # (código, cuerpo)
            raise urllib.error.HTTPError(req.full_url, x[0], "x", {}, io.BytesIO(x[1].encode()))
        return json.dumps(x).encode()


def test_alpaca_pagina_y_reintenta_ante_429():
    b = lambda f, c: {"t": f + "T05:00:00Z", "c": c, "v": 10}
    red = _Red([429, {"bars": {"A": [b("2024-01-02", 1.0)]}, "next_page_token": "p2"},
                {"bars": {"A": [b("2024-01-03", 2.0)], "B": [b("2024-01-03", 3.0)]}, "next_page_token": None}])
    esperas = []
    a = P.Alpaca("CLAVE", "SECRETO", abrir=red, dormir=esperas.append)
    out = a.barras(["A", "B"], "2024-01-01", "2024-01-05", "raw", asof="-")
    assert out == {"A": {D(2024, 1, 2): (1.0, 10), D(2024, 1, 3): (2.0, 10)}, "B": {D(2024, 1, 3): (3.0, 10)}}
    assert a.peticiones == 3 and "page_token=p2" in red.pedidas[-1].full_url and "asof=-" in red.pedidas[0].full_url
    assert all("CLAVE" not in r.full_url and "SECRETO" not in r.full_url for r in red.pedidas)
    assert esperas.count(a.pausa) == 3 and 1.0 in esperas                     # la pausa, y el reintento


def test_alpaca_pide_solo_lo_que_un_lote_se_calla():
    """FB y META juntos devuelven sólo META (medido el 31-oct): FB se pide solo; lo que siga sin nada se apunta."""
    b = {"t": "2020-01-02T05:00:00Z", "c": 209.78, "v": 10}
    red = _Red([{"bars": {"META": [b]}}, {"bars": {"FB": [b]}}, {"bars": {}}])
    a = P.Alpaca("k", "s", abrir=red, dormir=lambda _: None)
    out = a.barras(["FB", "META", "NADA"], "2020-01-02", "2020-01-10", "raw")
    assert set(out) == {"FB", "META"} and a.peticiones == 3
    assert "symbols=FB&" in red.pedidas[1].full_url and "symbols=NADA&" in red.pedidas[2].full_url
    assert a.sin_datos == [("NADA", "2020-01-02", "2020-01-10", "raw", None)]
    # con solos=() no se repite ninguno, y quedan apuntados como sin datos
    red = _Red([{"bars": {"META": [b]}}])
    a = P.Alpaca("k", "s", abrir=red, dormir=lambda _: None)
    assert set(a.barras(["FB", "META"], "2020-01-02", "2020-01-10", "raw", solos=set())) == {"META"}
    assert len(red.pedidas) == 1 and [x[0] for x in a.sin_datos] == ["FB"]
    # una clave que no se pidió (XYZ por SQ) no entra, y SQ se pide solo
    red = _Red([{"bars": {"XYZ": [b], "AAPL": [b]}}, {"bars": {"SQ": [b]}}])
    out = P.Alpaca("k", "s", abrir=red, dormir=lambda _: None).barras(["SQ", "AAPL"], "2020-01-02", "2020-01-10", "raw")
    assert set(out) == {"SQ", "AAPL"} and len(red.pedidas) == 2


def test_alpaca_no_reintenta_un_403():
    red = _Red([403])
    with pytest.raises(urllib.error.HTTPError):
        P.Alpaca("k", "s", abrir=red, dormir=lambda _: None).acciones("2016-01-01", "2026-10-30", cusips=["037833100"])
    assert len(red.pedidas) == 1


def test_acciones_de_casa_por_simbolo_y_fecha_del_tramo_sin_duplicados():
    """Los dividendos de GE de 2016-2019 vienen sin CUSIP, y el spin-off de 2019 con el CUSIP de hoy."""
    todas = {"cash_dividends": [{"id": "1", "symbol": "GE", "ex_date": "2017-03-01", "cusip": None},
                                {"id": "1", "symbol": "GE", "ex_date": "2017-03-01", "cusip": None},     # repetido
                                {"id": "2", "symbol": "GE", "ex_date": "2023-03-01", "cusip": None}],    # fuera
             "spin_offs": [{"id": "3", "source_symbol": "GE", "source_cusip": "369604301", "ex_date": "2019-02-25"}]}
    a = P.acciones_de("369604103", todas, [("GE", D(2016, 1, 1), D(2021, 7, 30))])
    assert [d["id"] for d in a["cash_dividends"]] == ["1"] and [d["id"] for d in a["spin_offs"]] == ["3"]
    assert P.acciones_de("369604103", todas)["cash_dividends"] == []                    # sin tramos, sólo por CUSIP


def test_acciones_de_reparte_por_el_papel_de_cada_cusip():
    todas = {"cash_dividends": [{"cusip": "A"}, {"cusip": "B"}],
             "spin_offs": [{"source_cusip": "A", "new_cusip": "N"}],
             "cash_mergers": [{"acquiree_cusip": "B", "acquirer_cusip": "A"}],
             "name_changes": [{"old_cusip": "A", "new_cusip": "A"}]}
    a = P.acciones_de("A", todas)
    assert len(a["cash_dividends"]) == 1 and len(a["spin_offs"]) == 1 and a["cash_mergers"] == []
    assert len(a["name_changes"]) == 1 and len(P.acciones_de("B", todas)["cash_mergers"]) == 1


# ── 5. el plan y el montaje ──────────────────────────────────────────────────
def test_el_plan_une_los_rangos_de_cada_simbolo():
    reg = {"C1": [(D(2016, 1, 4), "X")], "C2": [(D(2016, 1, 4), "X"), (D(2019, 1, 2), "Y")]}
    tr, rangos = P.plan({"C1": (D(2017, 1, 1), D(2017, 6, 30)), "C2": (D(2018, 6, 1), D(2019, 6, 30))}, reg, {})
    assert rangos == {"X": (D(2017, 1, 1), D(2019, 1, 1)), "Y": (D(2019, 1, 2), D(2019, 6, 30))}
    assert [t[0] for t in tr["C2"]] == ["X", "Y"]


def test_rentabilidades_mensuales_por_cusip_con_su_camino():
    f = _dias(D(2024, 1, 25), 12)                           # del 25-ene al 9-feb
    raw = _barras(f, [100 + i for i in range(12)])
    series = {"all": {"X": raw}, "raw": {"X": raw}, "tal_cual": {"X": raw}}
    out, caminos = P.rentabilidades({"C": [("X", f[0], f[-1])]}, series, {}, {}, {"C": (f[0], f[-1])})
    assert caminos == {"C": "alpaca"}
    assert list(out["C"]) == [D(2024, 2, 29)]                # enero sólo trae sus últimos días
    ultimo_enero = max(x for x in f if x.month == 1)
    assert out["C"][D(2024, 2, 29)] == pytest.approx(raw[f[-1]][0] / raw[ultimo_enero][0] - 1)


def test_un_mes_sin_cierre_del_anterior_no_cuenta():
    """Alpaca empieza el 4-ene-2016: enero sería parcial (sin el 31-dic) y salía 2–6 pp lejos de Yahoo."""
    f = _dias(D(2016, 1, 4), 30)                            # del 4-ene a mediados de febrero
    raw = _barras(f, [100 + i for i in range(30)])
    series = {"all": {"X": raw}, "raw": {"X": raw}, "tal_cual": {"X": raw}}
    out, _ = P.rentabilidades({"C": [("X", D(2015, 12, 21), f[-1])]}, series, {}, {}, {"C": (D(2015, 12, 21), f[-1])})
    assert list(out["C"]) == [D(2016, 2, 29)]


# ── 6. la traducción, comprobada con el precio del FTD ───────────────────────
def test_forma_con_punto():
    assert P.forma_con_punto("BRKB") == "BRK.B" and P.forma_con_punto("BRK.B") is None and P.forma_con_punto("X") is None


def test_el_contraste_compara_con_el_cierre_del_dia_habil_anterior():
    f = _dias(D(2024, 1, 2), 5)                                     # 2 al 8 de enero
    tal_cual = _barras(f, [100, 101, 102, 103, 104])
    tal_cual[f[2]] = (102, 0)                                       # una barra de relleno no cuenta
    regs = [(f[1], 100.0), (f[4], 103.0), (f[3], 101.0), (f[2], float("nan"))]
    n, med = P.contraste_ftd(regs, tal_cual)
    assert n == 3 and med == pytest.approx(0.0)                     # el del 5-ene compara con el 3 (el 4 es relleno)
    n, med = P.contraste_ftd([(f[1], 50.0), (f[4], 103.0), (f[3], 101.0)], tal_cual)
    assert n == 3 and med == pytest.approx(0.0)                     # una discrepancia no mueve la mediana
    assert P.contraste_ftd([(f[1], 200.0)], tal_cual)[1] == pytest.approx(1.0)
    assert P.contraste_ftd([(f[1], float("nan"))], tal_cual) == (0, None)
    assert P.contraste_ftd([(f[3], 101.0)], tal_cual) == (1, pytest.approx(0.0))     # salta el relleno del 4-ene
    assert P.contraste_ftd([(D(2024, 2, 20), 104.0)], tal_cual) == (0, None)          # sin cierre en la semana previa


def test_un_simbolo_invalido_se_quita_y_el_resto_se_pide():
    """El FTD trae pseudosímbolos (M606SPINOFF): Alpaca da 400 a la petición entera."""
    b = {"t": "2026-06-01T04:00:00Z", "c": 10.0, "v": 5}
    red = _Red([(400, '{"message":"invalid symbol: M606SPINOFF"}'), {"bars": {"A": [b]}}])
    a = P.Alpaca("k", "s", abrir=red, dormir=lambda _: None)
    out = a.barras(["A", "M606SPINOFF"], "2026-05-21", "2026-09-30", "raw", asof="-", solos=set())
    assert set(out) == {"A"} and a.invalidos == ["M606SPINOFF"] and "symbols=A&" in red.pedidas[1].full_url
    assert ("M606SPINOFF", "2026-05-21", "2026-09-30", "raw", "-") in a.sin_datos
    # en los corporate actions, igual
    red = _Red([(400, '{"message":"invalid symbol: J118REORGPYMNT"}'), {"corporate_actions": {"x": [1]}}])
    a = P.Alpaca("k", "s", abrir=red, dormir=lambda _: None)
    assert a.acciones("2016-01-01", "2026-10-30", simbolos=["A", "J118REORGPYMNT"]) == {"x": [1]}
    assert "symbols=A" in red.pedidas[1].full_url and "J118" not in red.pedidas[1].full_url
    assert a.invalidos == ["J118REORGPYMNT"]


def test_otro_400_sigue_parando():
    red = _Red([(400, '{"message":"invalid timeframe"}')])
    with pytest.raises(urllib.error.HTTPError):
        P.Alpaca("k", "s", abrir=red, dormir=lambda _: None).barras(["A"], "2026-01-01", "2026-02-01", "raw")
    red = _Red([(400, '{"message":"invalid symbol: OTRO"}')])                # uno que no se pidió: no se oculta
    with pytest.raises(P.SimboloInvalido):
        P.Alpaca("k", "s", abrir=red, dormir=lambda _: None).barras(["A"], "2026-01-01", "2026-02-01", "raw")
