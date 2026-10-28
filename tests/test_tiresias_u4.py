"""TiresIAs: U4. El simulador de TopkDropout con casos que saben la respuesta."""
import numpy as np

from tiresias import u4 as U


def _precios(T=40, J=60, semilla=0, deriva=None):
    rng = np.random.default_rng(semilla)
    r = rng.normal(0, 0.01, (T, J)) + (0 if deriva is None else deriva)
    c = 100 * np.cumprod(1 + r, axis=0)
    return c, c.copy()                                   # apertura = cierre: sin huecos


def test_sin_cambio_de_senal_no_hay_rotacion_tras_comprar():
    c, a = _precios()
    S = np.tile(np.arange(60, dtype=float), (40, 1))      # siempre el mismo orden
    r = U.topk_dropout(S, a, c, k=10, n_drop=2, c_compra=0, c_venta=0)
    assert abs(r["rotacion_anual"] * 40 / 252 - 0.95) < 1e-9     # sólo la compra inicial del 95 % del efectivo


def test_la_permanencia_impide_vender_antes_de_5_sesiones():
    c, a = _precios(T=8, J=12)
    S = np.zeros((8, 12))
    S[0, :] = np.arange(12)                               # el día 0 elige los 3 mejores: 9, 10, 11
    S[1:, :] = -np.arange(12)                             # desde el día 1 son los peores: querría venderlos ya
    r1 = U.topk_dropout(S, a, c, k=3, n_drop=3, permanencia=5, c_compra=0, c_venta=0)
    r0 = U.topk_dropout(S, a, c, k=3, n_drop=3, permanencia=1, c_compra=0, c_venta=0)
    assert r1["rotacion_anual"] < r0["rotacion_anual"]    # con permanencia, menos ventas en esos días


def test_cobra_la_compra():
    c, a = _precios(T=3, J=5)
    c[:], a[:] = 100.0, 100.0
    S = np.tile(np.arange(5, dtype=float), (3, 1))
    r = U.topk_dropout(S, a, c, k=5, n_drop=1, riesgo=1.0, c_compra=0.01, c_venta=0)
    assert abs(r["valor"][-1] - 0.99) < 1e-12


def test_puntuacion_perfecta_gana_a_todos():
    c, a = _precios(T=120, J=80, semilla=1)
    S = np.full_like(c, np.nan)
    S[:-2] = a[2:] / a[1:-1] - 1                           # la señal de t ve la apertura t+1 → t+2: la que cobra
    r = U.topk_dropout(S, a, c, k=10, n_drop=10, permanencia=1)
    todos = np.prod(1 + np.nanmean(c[1:] / c[:-1] - 1, axis=1))
    assert r["valor"][-1] > 1.5 * todos


def test_un_cierre_que_falta_no_hunde_la_cartera():
    c, a = _precios(T=10, J=6)
    S = np.tile(np.arange(6, dtype=float), (10, 1))
    base = U.topk_dropout(S, a, c, k=3, n_drop=1)["valor"]
    c2 = c.copy()
    c2[5, 5] = np.nan                                     # el mejor, en cartera, sin cierre el día 5
    hueco = U.topk_dropout(S, a, c2, k=3, n_drop=1)["valor"]
    assert hueco[5] > 0.9 * base[5]
