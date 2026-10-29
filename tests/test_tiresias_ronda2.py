"""TiresIAs: la segunda ronda. Cada estadístico con un caso de respuesta conocida."""
import numpy as np
import pytest

from tiresias import ronda2 as R


def _caso(n_fechas=60, n=150, semilla=0, extra=0.0):
    rng = np.random.default_rng(semilla)
    pas5, pas20 = rng.normal(size=(n_fechas, n)), rng.normal(size=(n_fechas, n))
    futuro = rng.normal(size=(n_fechas, n))
    P = -pas5 + 0.3 * pas20 + extra * futuro                    # reversión, tendencia y (si extra) algo del futuro
    return P, futuro, [pas5, pas20]


def test_pura_reversion_no_deja_residuo_util():
    P, R_, c = _caso()
    r = R.resumen_t(R.residuo_ic(P, R_, c))                     # en rangos queda un residuo, pero sin futuro dentro
    assert abs(r["media"]) < 0.05 and r["p"] > 0.01


def test_informacion_extra_se_ve_en_el_residuo():
    P, R_, c = _caso(extra=0.5)
    r = R.resumen_t(R.residuo_ic(P, R_, c))
    assert r["media"] > 0.3 and r["p"] < 1e-6


def test_ruido_no_pasa():
    rng = np.random.default_rng(5)
    P, R_, c = _caso()
    r = R.resumen_t(R.residuo_ic(P + rng.normal(size=P.shape), R_, c))
    assert abs(r["media"]) < 0.05 and r["p"] > 0.01


def test_veto_solo_retrasa_las_entradas():
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=10)
    regla = pd.Series([0, 0, 1, 1, 1, 1, 1, 0, 1, 1], index=idx).astype(bool)
    kron = pd.Series([0, 0, 0, 0, 1, 0, 0, 0, 0, 1], index=idx).astype(bool)
    v = R.con_veto(regla, kron)
    assert list(v.astype(int)) == [0, 0, 0, 0, 1, 1, 1, 0, 0, 1]   # entra el día 5 (no el 3), sale con la regla, re-entra el 10
    assert not (v & ~regla).any()                                    # nunca dentro sin la regla


def test_curva_regla_cobra_cada_cambio():
    import pandas as pd
    idx = pd.date_range("2025-01-01", periods=4)
    c = pd.Series([100.0, 100.0, 100.0, 100.0], index=idx)
    d = pd.Series([True, False, False, False], index=idx)
    assert R.curva_regla(c, d, coste=0.01).iloc[-1] == pytest.approx(0.99 * 0.99)   # entra el día 2 y sale el 3


def test_el_veredicto_exige_holm_y_el_criterio_económico():
    from tiresias import ronda2 as R
    r = {"U1": {"principal": {"p": 0.001, "p_exceso_positivo": 0.95}}, "U2": {"p": 0.5},
         "U3": {"p": 0.009, "p_mejor": 0.5}, "U4": {"rankic_10": {"p": 0.02}, "pasa_economico": True},
         "U5": {"p": 0.8, "p_mejor": 0.99}}
    f = {x["hipotesis"]: x for x in R.veredicto(r)}
    assert f["U1"]["holm"] and f["U1"]["pasa"]                       # 0,001 ≤ 0,05/5
    assert f["U3"]["holm"] and not f["U3"]["pasa"]                   # 0,009 ≤ 0,05/4, pero no cumple el económico
    assert not f["U4"]["holm"] and not f["U4"]["pasa"]               # 0,02 > 0,05/3: Holm la para aunque gane dinero
    assert not f["U5"]["pasa"] and f["U2"]["economico"] is None
