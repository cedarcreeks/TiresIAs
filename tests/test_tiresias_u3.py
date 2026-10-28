"""TiresIAs: U3. Nada posterior a t entra en lo de t, y la cabeza encuentra una señal cuando la hay."""
import numpy as np
import pandas as pd
import pytest

from tiresias import modelo as M
from tiresias import u3 as U


@pytest.fixture(scope="module")
def km():
    return M.cargar("small", "cpu")


def _df(n=320, semilla=3):
    rng = np.random.default_rng(semilla)
    c = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    idx = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame({"open": c, "high": c * 1.01, "low": c * 0.99, "close": c, "volume": 1e6, "adjclose": c}, index=idx)


def test_estados_y_clasicas_no_miran_el_futuro(km):
    tok, mod = km
    df = _df()
    pos = [60, 61, 200]
    a = U.estados(tok, mod, df, pos)
    otro = df.copy()
    otro.iloc[201:, :4] *= 1.8                                       # se inventa todo lo posterior a la posición 200
    b = U.estados(tok, mod, otro, pos)
    assert a.shape == (3, mod.d_model) and np.allclose(a, b, atol=1e-5)
    ca, cb = U.clasicas(df), U.clasicas(otro)
    pd.testing.assert_frame_equal(ca.iloc[:201], cb.iloc[:201])


def test_la_cabeza_encuentra_la_senal_sembrada():
    rng = np.random.default_rng(0)
    fechas = np.repeat(np.arange(60), 150)
    senal, ruido = rng.normal(size=len(fechas)), rng.normal(size=(len(fechas), 5))
    y = U._por_fecha((senal + rng.normal(size=len(fechas)))[:, None], fechas, True)[:, 0]
    Xm = U._por_fecha(np.column_stack([senal, ruido]), fechas, True)
    alfa = U.elegir_alfa(Xm, y, fechas)
    w = U.ridge(Xm, y, alfa)
    assert U.ic_medio(Xm @ w, y, fechas) > 0.5 and abs(w[0]) > 5 * np.abs(w[1:]).max()
