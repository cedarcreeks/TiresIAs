"""TiresIAs: la prueba del S&P 500. Cada pieza con un caso que sabe la respuesta, y la tubería dice sí y no."""
import json

import numpy as np
import pandas as pd
import pytest

from tiresias import transversal as T


def test_rejilla_cada_5_y_con_salida():
    cal = pd.bdate_range("2024-06-24", periods=40)
    r = T.rejilla(cal, "2024-07-01", 5)
    i = [cal.get_loc(f) for f in r]
    assert r[0] == pd.Timestamp("2024-07-01") and all(b - a == 5 for a, b in zip(i, i[1:]))
    assert i[-1] + 1 + 5 <= len(cal) - 1 and i[-1] + 5 + 1 + 5 > len(cal) - 1


def test_cartera_media_de_los_primeros():
    P = np.array([[4.0, 3.0, 2.0, 1.0]])
    R = np.array([[0.10, 0.02, -0.5, -0.5]])
    assert T.cartera(P, R, 2, coste=0.0)[0] == pytest.approx(0.06)
    assert T.cartera(P, R, None, coste=0.0)[0] == pytest.approx((0.10 + 0.02 - 1.0) / 4)


def test_coste_sobre_lo_que_se_rota():
    R = np.zeros((3, 4))
    quieta = np.tile([4.0, 3.0, 2.0, 1.0], (3, 1))                      # siempre los mismos dos
    assert list(T.cartera(quieta, R, 2, coste=0.01)) == pytest.approx([-0.01, 0.0, 0.0])
    cambia = np.array([[4.0, 3.0, 2.0, 1.0], [1.0, 2.0, 3.0, 4.0], [4.0, 3.0, 2.0, 1.0]])
    assert list(T.cartera(cambia, R, 2, coste=0.01)) == pytest.approx([-0.01, -0.02, -0.02])   # vende todo y compra todo


def test_la_deriva_de_los_pesos_se_cobra():
    """Mismos dos valores, pero uno subió: volver a partes iguales rota |0,5 − 1,1/2,1| × 2."""
    P = np.tile([2.0, 1.0], (2, 1))
    R = np.array([[0.10, 0.0], [0.0, 0.0]])
    r = T.cartera(P, R, 2, coste=1.0)
    assert r[1] == pytest.approx(-2 * abs(0.5 - 0.55 / 1.05))


def test_placebo_baraja_dentro_de_cada_valor():
    P = np.array([[1.0, np.nan], [2.0, 5.0], [3.0, 6.0]])
    Q = T.barajar_por_valor(P, np.random.default_rng(0))
    assert np.isnan(Q[0, 1]) and sorted(Q[:, 0]) == [1.0, 2.0, 3.0] and sorted(Q[1:, 1]) == [5.0, 6.0]


def test_condiciones_cada_una_por_su_lado():
    ic = np.full(50, 0.05) + np.random.default_rng(1).normal(0, 0.01, 50)
    assert all(T.condiciones(ic, 1.5, 1.0, 0.95, 1.2).values())
    c = T.condiciones(ic - 0.05, 1.5, 1.0, 0.95, 1.2)
    assert not c["1 RankIC entre valores media > 0 con t > 2"]
    assert not T.condiciones(ic, 1.5, 1.0, 0.89, 1.2)["2 los 50 primeros, mejor Sharpe neto que todos con P ≥ 90 %"]
    assert not T.condiciones(ic, 1.5, 1.0, 0.95, 1.5)["3 por encima del percentil 95 del placebo"]


def _universo(d, perfecta, n=120, rng=None):
    rng = rng or np.random.default_rng(0)
    cal = pd.bdate_range("2023-06-01", "2025-06-30")
    simbolos = [f"V{k:03d}" for k in range(n)]
    for s in ["SPY"] + simbolos:
        c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(cal))))
        o = np.append(c[0], c[:-1])                                       # abre donde cerró: real = apertura a apertura
        pd.DataFrame({"open": o, "high": np.maximum(o, c), "low": np.minimum(o, c), "close": c, "volume": 1.0,
                      "adjclose": c}, index=cal).to_csv(d / f"velas_{s}.csv")
        if s == "SPY":
            continue
        filas = []
        for f in T.rejilla(cal):
            i = cal.get_loc(f)
            real = c[i + 5] / c[i] - 1
            filas.append({"fecha": str(f.date()), "r_prevista": real if perfecta else rng.normal(), "r_real": real})
        pd.DataFrame(filas).to_csv(d / f"pred_{s}_H5.csv", index=False)
    return simbolos


@pytest.mark.parametrize("perfecta", [True, False])
def test_la_tuberia_dice_que_si_y_que_no(tmp_path, perfecta):
    simbolos = _universo(tmp_path, perfecta)
    r = T.evaluar(tmp_path, ["SPY"] + simbolos, placebos=50, reps=200)
    assert r["valores_con_prediccion"] == len(simbolos)                 # el SPY no entra en el universo
    assert r["aporta"] is perfecta, r["condiciones"]
    if perfecta:
        assert r["rankic_media"] > 0.9 and r["sharpe_top"] > r["sharpe_todos"] > r["sharpe_ultimos"]
    json.dumps({k: v for k, v in r.items()})                            # se puede guardar


def test_t_sin_dispersion():
    assert T.t_media(np.full(10, 1.0)) == float("inf") and T.t_media(np.full(10, -1.0)) == float("-inf")
    assert T.t_media(np.full(10, 0.3)) > 1e10            # 0,3 no es exacto en binario: dispersión 6e-17, t enorme
    assert np.isnan(T.t_media(np.array([0.1, np.nan])))


def test_media_positiva_sin_t_no_basta():
    ic = 0.05 + np.random.default_rng(3).normal(0, 0.3, 50)          # media > 0, t ≈ 1
    assert ic.mean() > 0 and T.t_media(ic) < 2
    assert not T.condiciones(ic, 1.5, 1.0, 0.95, 1.2)["1 RankIC entre valores media > 0 con t > 2"]
