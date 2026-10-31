"""Tests de tiresias.mejores_ideas: el tilt, el filtro de activos, la cartera con su coste y el veredicto."""
import numpy as np
import pandas as pd
import pytest

from tiresias import mejores_ideas as M


def _pos(cik, presentado, valores, periodo="2023-12-31", cusips=None):
    cusips = cusips or [f"C{j}" for j in range(len(valores))]
    return pd.DataFrame({"cik": cik, "presentado": pd.Timestamp(presentado), "periodo": pd.Timestamp(periodo),
                         "cusip": cusips, "valor": valores, "accesion": f"{cik}{presentado}", "emisor": "x"})


def _rent(n=25, meses=12):
    idx = pd.date_range("2024-01-31", periods=meses, freq="ME")
    return pd.DataFrame({f"C{j}": [0.01 * (j + 1)] * meses for j in range(n)}, index=idx)


def test_la_mejor_idea_es_la_de_mayor_tilt_frente_al_mercado():
    # el gestor 1 pesa por igual 20 valores más uno (C20) que pesa el triple: su mejor idea es C20
    a = _pos("1", "2024-02-14", [1.0] * 20 + [3.0])
    # el gestor 2 pesa mucho C0, pero un gestor tipo índice muy grande hace que C0 sea casi todo el mercado:
    # para el 2, C0 está infraponderado y su mejor idea es otra
    b = _pos("2", "2024-02-14", [100.0] + [1.0] * 19 + [2.0])
    indice = _pos("ix", "2024-02-14", [1_000_000.0] + [1.0] * 20)
    i = M.ideas(pd.concat([a, b, indice]), _rent()).set_index("cik")
    assert i.loc["1", "cusip"] == "C20" and i.loc["2", "cusip"] == "C20" and i.loc["2", "tilt"] > 0
    pocos = _pos("3", "2024-02-14", [1.0] * 10)
    assert "3" not in set(M.ideas(pd.concat([a, b, pocos]), _rent())["cik"])   # menos de 20 valores


def test_solo_entra_el_cuartil_de_mayor_tilt_por_periodo():
    i = pd.DataFrame({"cik": list("abcd"), "presentado": pd.Timestamp("2024-02-14"), "cusip": "X",
                      "tilt": [0.01, 0.02, 0.03, 0.10], "periodo": pd.Timestamp("2023-12-31")})
    assert list(M.activos(i)["cik"]) == ["d"]


def test_la_cartera_a_partes_iguales_con_su_coste_de_rotacion():
    rent = _rent()
    i = pd.DataFrame({"cik": ["a", "b", "a"], "cusip": ["C0", "C9", "C4"], "tilt": 1.0, "periodo": pd.Timestamp("2023-12-31"),
                      "presentado": pd.to_datetime(["2024-02-14", "2024-02-14", "2024-05-15"])})
    r, coste = M.cartera(i, rent)
    assert r.loc["2024-03-31"] == pytest.approx((0.01 + 0.10) / 2)
    assert r.loc["2024-06-30"] == pytest.approx((0.05 + 0.10) / 2)        # a cambia de idea en junio
    assert coste.loc["2024-03-31"] == pytest.approx(M.COSTE_LADO * 1.0)    # se compra todo
    assert coste.loc["2024-06-30"] == pytest.approx(M.COSTE_LADO * 1.0)    # se vende C0 (0,5) y se compra C4 (0,5)
    assert coste.loc["2024-04-30"] == 0
    # b no presenta otro 13F: su idea dura cuatro meses (marzo a junio) y en julio sólo queda la de a
    assert r.loc["2024-07-31"] == pytest.approx(0.05)
    # una idea compartida por dos gestores pesa el doble
    i2 = pd.concat([i, pd.DataFrame({"cik": ["c"], "cusip": ["C9"], "tilt": 1.0, "periodo": pd.Timestamp("2023-12-31"),
                                     "presentado": [pd.Timestamp("2024-02-14")]})])
    r2, _ = M.cartera(i2, rent)
    assert r2.loc["2024-03-31"] == pytest.approx((0.01 + 2 * 0.10) / 3)


def test_el_veredicto_exige_las_tres():
    idx = pd.date_range("2016-01-31", periods=120, freq="ME")
    rng = np.random.default_rng(2)
    F = pd.DataFrame(rng.normal(0.005, 0.04, (120, 4)), index=idx, columns=M.CARHART)
    F["RF"] = 0.001
    buena = F["MKT"] + 0.01 + rng.normal(0, 0.005, 120)                   # alfa grande y claro
    sp = F["MKT"] + F["RF"]
    v = M.veredicto(buena, buena, sp - F["RF"], F, placebo=list(rng.normal(0.3, 0.1, 200)))
    assert v["pasa"] and v["alfa"]["t"] > 2
    mala = F["MKT"] + rng.normal(0, 0.005, 120)
    v2 = M.veredicto(mala, mala, sp - F["RF"], F, placebo=list(rng.normal(0.3, 0.1, 200)))
    assert not v2["criterios"]["1_alfa_carhart_t2"] and not v2["pasa"]


def test_el_placebo_elige_al_azar_dentro_del_13f_con_el_tilt_de_la_mejor_idea():
    a = _pos("1", "2024-02-14", [1.0] * 20 + [3.0])
    b = _pos("2", "2024-02-14", [5.0] + [1.0] * 20)
    pos = pd.concat([a, b])
    real = M.ideas(pos, _rent()).set_index("cik")
    vistos = set()
    for s in range(30):
        pl = M.ideas(pos, _rent(), semilla=s).set_index("cik")
        assert (pl["tilt"] == real["tilt"]).all()                           # mismos gestores tras el filtro
        assert set(pl.loc["1", ["cusip"]]) <= set(a["cusip"])
        vistos.add(pl.loc["1", "cusip"])
    assert len(vistos) > 5                                                  # de verdad al azar


def test_una_mejor_idea_sin_precio_al_entrar_cede_a_la_siguiente():
    a = _pos("1", "2024-02-14", [1.0] * 19 + [2.0, 3.0])                    # C20 la mayor, C19 la segunda
    rent = _rent()
    rent.loc["2024-03-31", "C20"] = np.nan                                   # sin precio en su mes de entrada
    assert M.ideas(a, rent).set_index("cik").loc["1", "cusip"] == "C19"


def test_el_placebo_rapido_elige_uno_al_azar_de_cada_13f_activo():
    pos = pd.concat([_pos("1", "2024-02-14", [1.0] * 20 + [3.0]), _pos("2", "2024-02-14", [5.0] + [1.0] * 20),
                     _pos("3", "2024-02-14", [1.0] * 21)])
    cand = M.candidatas(pos, _rent())
    reales = M.ideas(pos, _rent(), cand=cand)
    act = reales[reales["cik"].isin(["1", "2"])]                             # sólo dos activos
    pl = M.Placebo(cand, act)
    vistos = {"1": set(), "2": set()}
    for s in range(40):
        x = pl.ideas(s)
        assert sorted(x["cik"]) == ["1", "2"]                                # uno por 13F activo, y sólo de los activos
        for cik, c in zip(x["cik"], x["cusip"]):
            assert c in set(pos[pos["cik"] == cik]["cusip"])
            vistos[cik].add(c)
    assert len(vistos["1"]) > 8 and len(vistos["2"]) > 8                     # de verdad al azar
    assert pl.ideas(7).equals(pl.ideas(7))                                   # reproducible con su semilla


def test_los_placebos_en_paralelo_dan_lo_mismo_que_en_uno():
    pos = pd.concat([_pos(str(k), "2024-02-14", list(np.random.default_rng(k).random(21) + 1)) for k in range(6)])
    rent = _rent()
    cand = M.candidatas(pos, rent)
    real = M.ideas(pos, rent, cand=cand)
    rf = pd.Series(0.001, index=rent.index)
    pl = M.Placebo(cand, real)
    assert M.placebos(pl, rent, rf, reps=6, procesos=1) == M.placebos(pl, rent, rf, reps=6, procesos=3)
