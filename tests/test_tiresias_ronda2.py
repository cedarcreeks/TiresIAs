"""TiresIAs: la segunda ronda. Cada estadístico con un caso de respuesta conocida."""
import numpy as np

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
