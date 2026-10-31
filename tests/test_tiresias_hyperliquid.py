"""Tests de tiresias.hyperliquid: la muestra, la descarga reanudable, el rendimiento de una ventana y la persistencia."""
import datetime as dt
import io
import json
import urllib.error

import numpy as np
import pandas as pd
import pytest

from tiresias import hyperliquid as H

D = dt.date


def _ms(f):
    return int(dt.datetime(f.year, f.month, f.day, tzinfo=dt.timezone.utc).timestamp() * 1000)


def _portfolio(puntos_av, puntos_pnl):
    return [["day", {}], ["allTime", {"accountValueHistory": [[_ms(f), str(v)] for f, v in puntos_av],
                                      "pnlHistory": [[_ms(f), str(v)] for f, v in puntos_pnl]}]]


def test_la_muestra_es_reproducible_y_no_depende_del_orden():
    filas = [{"ethAddress": f"0x{i:040x}"} for i in range(100)]
    m = H.muestra(filas, n=10, semilla=31)
    assert m == H.muestra(list(reversed(filas)), n=10, semilla=31) and len(m) == 10
    assert m != H.muestra(filas, n=10, semilla=32)


def test_el_rendimiento_no_cuenta_aportaciones_y_exige_existir_al_empezar():
    ini, fin = D(2026, 1, 1), D(2026, 6, 30)
    # aporta 100.000 en marzo (el patrimonio salta) pero su resultado sólo sube 5.000
    p = _portfolio([(D(2025, 12, 20), 50_000), (D(2026, 3, 1), 150_000), (D(2026, 6, 1), 155_000)],
                   [(D(2025, 12, 20), 1_000), (D(2026, 3, 1), 1_000), (D(2026, 6, 1), 6_000)])
    r = H.rendimiento(p, ini, fin)
    assert r["pnl"] == 5_000 and r["activa"] and r["patrimonio_ini"] == 50_000
    assert r["roi"] == pytest.approx(5_000 / np.mean([50_000, 150_000, 155_000]))
    nueva = _portfolio([(D(2026, 2, 1), 10_000)], [(D(2026, 2, 1), 0)])
    assert H.rendimiento(nueva, ini, fin) is None                         # no existía al empezar
    quieta = _portfolio([(D(2025, 12, 1), 20_000)], [(D(2025, 12, 1), 300)])
    assert not H.rendimiento(quieta, ini, fin)["activa"]


def test_la_tabla_aplica_el_universo_del_plan():
    def reg(u, pat, pnl_a, pnl_b):
        a0, b0 = H.A[0] - dt.timedelta(days=5), H.B[0] - dt.timedelta(days=5)
        return {"user": u, "portfolio": _portfolio([(a0, pat), (b0, pat)],
                                                   [(a0, 0), (b0, pnl_a), (H.B[1], pnl_a + pnl_b)])}
    t = H.tabla([reg("buena", 50_000, 5_000, 2_000), reg("pequeña", 5_000, 500, 200), reg("quieta_b", 50_000, 100, 0),
                 {"user": "error", "error": "HTTP 500"}])
    assert list(t["user"]) == ["buena"] and t["roi_a"].iloc[0] == pytest.approx(0.1)


class _Red:
    def __init__(self, respuestas):
        self.respuestas, self.pedidas = list(respuestas), []

    def __call__(self, req):
        self.pedidas.append(json.loads(req.data))
        x = self.respuestas.pop(0)
        if isinstance(x, int):
            raise urllib.error.HTTPError(req.full_url, x, "x", {}, io.BytesIO(b""))
        return json.dumps(x).encode()


def test_la_descarga_reanuda_reintenta_429_y_apunta_errores(tmp_path):
    f = tmp_path / "p.jsonl"
    red = _Red([429, [["allTime", {}]], 404])
    esperas = []
    r = H.descargar(["0xa", "0xb"], f, abrir=red, dormir=esperas.append)
    assert r == {"bajadas": 1, "errores": 1, "ya_estaban": 0} and 15 in esperas
    assert [json.loads(l)["user"] for l in f.read_text().splitlines()] == ["0xa", "0xb"]
    assert red.pedidas[0] == {"type": "portfolio", "user": "0xa"}
    red2 = _Red([[["allTime", {}]]])
    assert H.descargar(["0xa", "0xb", "0xc"], f, abrir=red2, dormir=lambda _: None)["ya_estaban"] == 2
    assert [p["user"] for p in red2.pedidas] == ["0xc"]


def test_la_persistencia_distingue_persistir_de_azar():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 400)
    t = pd.DataFrame({"roi_a": a, "roi_b": 0.6 * a + rng.normal(0, 1, 400)})
    r = H.persistencia(t, perms=2000, reps=200)
    assert r["pasa"] and r["rho"] > 0.3 and r["p"] < 0.01 and r["decil"] == 40
    t2 = pd.DataFrame({"roi_a": a, "roi_b": rng.normal(0, 1, 400)})
    r2 = H.persistencia(t2, perms=2000, reps=200)
    assert not r2["pasa"] and r2["p"] > 0.01
    assert H.spearman([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0)
