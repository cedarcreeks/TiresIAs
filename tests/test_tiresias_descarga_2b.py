"""Tests de tiresias.descarga_2b: partes reanudables, lo que se queda sin datos y la lectura de vuelta."""
import datetime as dt

from tiresias import descarga_2b as X

D = dt.date


class _Alpaca:
    """Un Alpaca de mentira que apunta lo que se le pide."""

    def __init__(self, datos, sin=()):
        self.datos, self.sin, self.pedidas, self.sin_datos = datos, set(sin), [], []

    def barras(self, simbolos, desde, hasta, ajuste, asof=None, solos=None):
        self.pedidas.append(("barras", tuple(simbolos), ajuste, asof, None if solos is None else tuple(sorted(solos))))
        for s in simbolos:
            if s in self.sin:
                self.sin_datos.append((s, desde, hasta, ajuste, asof))
        return {s: self.datos[s] for s in simbolos if s in self.datos and s not in self.sin}

    def acciones(self, desde, hasta, cusips=(), simbolos=()):
        self.pedidas.append(("acciones", tuple(cusips), tuple(simbolos)))
        return {"cash_dividends": [{"id": "1", "symbol": "A"}, {"id": "2", "symbol": "B"}]}


PEDIDO = {"barras": [{"id": "l1", "simbolos": ["A", "B", "Z"], "desde": "2016-01-01", "hasta": "2016-02-01",
                      "modos": ["all", "tal_cual"]}],
          "acciones": [{"id": "c1", "cusips": ["X"], "simbolos": ["A"], "desde": "2016-01-01", "hasta": "2026-10-30"}]}


def test_ejecuta_por_partes_y_no_repite_lo_hecho(tmp_path):
    a = _Alpaca({"A": {D(2016, 1, 4): (10.0, 5)}, "B": {D(2016, 1, 4): (20.0, 0)}}, sin=["Z"])
    r = X.ejecutar(PEDIDO, tmp_path, a)
    assert r["hechas"] == 3 and r["saltadas"] == 0 and sorted(r["sin_datos"]) == [("all", "Z"), ("tal_cual", "Z")]
    # tal_cual primero, sin repetir solos; los otros modos sólo repiten los que tienen barras tal como cotizaron
    assert a.pedidas[0] == ("barras", ("A", "B", "Z"), "raw", "-", ())
    assert a.pedidas[1] == ("barras", ("A", "B", "Z"), "all", None, ("A", "B"))
    assert sorted(p.name for p in tmp_path.glob("*.gz")) == [
        "acciones_c1.json.gz", "barras_l1_all.jsonl.gz", "barras_l1_tal_cual.jsonl.gz"]
    assert not list(tmp_path.glob("*.tmp"))
    b = _Alpaca({})
    r = X.ejecutar(PEDIDO, tmp_path, b)
    assert r == {"hechas": 0, "saltadas": 3, "sin_datos": []} and b.pedidas == []


def test_lee_de_vuelta_lo_que_escribe(tmp_path):
    X.ejecutar(PEDIDO, tmp_path, _Alpaca({"A": {D(2016, 1, 4): (10.0, 5)}, "B": {D(2016, 1, 4): (20.0, 0)}}))
    assert X.leer_barras(tmp_path, "tal_cual") == {"A": {D(2016, 1, 4): (10.0, 5)}, "B": {D(2016, 1, 4): (20.0, 0)}}
    assert X.leer_barras(tmp_path, "raw") == {}
    X.ejecutar({"acciones": [{"id": "c2", "cusips": [], "simbolos": ["B"], "desde": "a", "hasta": "b"}]}, tmp_path,
               _Alpaca({}))
    acc = X.leer_acciones(tmp_path)
    assert [d["id"] for d in acc["cash_dividends"]] == ["1", "2"]               # sin duplicados entre partes


def test_al_reanudar_lee_de_su_parte_que_simbolos_tienen_barras(tmp_path):
    pedido = {"barras": [dict(PEDIDO["barras"][0], modos=["tal_cual"])]}
    X.ejecutar(pedido, tmp_path, _Alpaca({"A": {D(2016, 1, 4): (10.0, 5)}}))
    a = _Alpaca({})
    X.ejecutar(PEDIDO, tmp_path, a)                                          # ya está tal_cual: sólo pide all
    assert a.pedidas[0] == ("barras", ("A", "B", "Z"), "all", None, ("A",))
